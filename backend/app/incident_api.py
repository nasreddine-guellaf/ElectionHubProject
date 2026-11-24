"""Incidents fictifs et photographies privées rattachés aux révisions de PV."""

import hashlib
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select

from app.document_api import clean_filename, current_revision, revision_for_report
from app.object_storage import StorageError
from app.phase5_models import IncidentAttachment, ReportIncident
from app.phase5_schemas import IncidentAttachmentRead, IncidentInput, IncidentRead
from app.security import Authenticated, Db, Principal, audit, roles

Agent = Annotated[Principal, Depends(roles("AGENT"))]
router = APIRouter(prefix="/api/v1/reports", tags=["Incidents et photographies privées"])

PHOTO_TYPES = {
    "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": (".jpg", b"\xff\xd8\xff"),
}


def incident_for_revision(session, revision_id: UUID, incident_id: UUID) -> ReportIncident:
    incident = session.get(ReportIncident, incident_id)
    if incident is None or incident.revision_id != revision_id:
        raise HTTPException(404, "Incident introuvable.")
    return incident


@router.get(
    "/{report_id}/revisions/{number}/incidents",
    response_model=list[IncidentRead],
)
def incidents(report_id: UUID, number: int, actor: Authenticated, session: Db):
    _, revision = revision_for_report(session, report_id, number, actor)
    return session.scalars(
        select(ReportIncident)
        .where(ReportIncident.revision_id == revision.id)
        .order_by(ReportIncident.created_at, ReportIncident.id)
    ).all()


@router.post(
    "/{report_id}/revisions/{number}/incidents",
    response_model=IncidentRead,
    status_code=201,
)
def report_incident(
    report_id: UUID,
    number: int,
    data: IncidentInput,
    actor: Agent,
    session: Db,
):
    report, revision = current_revision(session, report_id, number, actor)
    if report.created_by != actor.id:
        raise HTTPException(403, "Seul l'auteur peut déclarer un incident sur ce dossier.")
    if revision.status != "DRAFT":
        raise HTTPException(409, "Les incidents sont ajoutés uniquement au brouillon courant.")
    if revision.edit_version != data.expected_version:
        raise HTTPException(409, "Version obsolète : rechargez le PV.")
    incident = ReportIncident(
        revision_id=revision.id,
        created_by=actor.id,
        category=data.category,
        description=data.description,
    )
    session.add(incident)
    audit(session, "INCIDENT_REPORTED", actor.id, resource=str(incident.id))
    session.commit()
    session.refresh(incident)
    return incident


@router.post(
    "/{report_id}/revisions/{number}/incidents/{incident_id}/attachments",
    response_model=IncidentAttachmentRead,
    status_code=201,
)
async def upload_incident_photo(
    report_id: UUID,
    number: int,
    incident_id: UUID,
    request: Request,
    session: Db,
    actor: Agent,
    expected_version: Annotated[int, Form(ge=1)],
    file: Annotated[UploadFile, File()],
):
    report, revision = current_revision(session, report_id, number, actor)
    incident = incident_for_revision(session, revision.id, incident_id)
    if report.created_by != actor.id or incident.created_by != actor.id:
        raise HTTPException(403, "Seul l'auteur peut ajouter une photographie à cet incident.")
    if revision.status != "DRAFT":
        raise HTTPException(409, "Les photographies sont ajoutées uniquement au brouillon courant.")
    if revision.edit_version != expected_version:
        raise HTTPException(409, "Version obsolète : rechargez le PV.")
    if file.content_type not in PHOTO_TYPES:
        raise HTTPException(415, "Formats autorisés pour un incident : JPEG et PNG.")
    content = await file.read(request.app.state.settings.object_upload_max_bytes + 1)
    if not content:
        raise HTTPException(422, "Le fichier est vide.")
    if len(content) > request.app.state.settings.object_upload_max_bytes:
        raise HTTPException(413, "Le fichier dépasse la taille maximale autorisée.")
    suffix, signature = PHOTO_TYPES[file.content_type]
    if not content.startswith(signature):
        raise HTTPException(422, "Le contenu de la photographie ne correspond pas à son format.")

    attachment_id = uuid4()
    object_key = f"incidents/{report.id}/revisions/{number}/{incident.id}/{attachment_id}{suffix}"
    storage = request.app.state.object_storage
    try:
        storage.put(
            object_key,
            content,
            file.content_type,
            {"incident-id": str(incident.id), "attachment-id": str(attachment_id)},
        )
    except StorageError as exc:
        raise HTTPException(503, "Le stockage des photographies est indisponible.") from exc
    try:
        attachment = IncidentAttachment(
            id=attachment_id,
            incident_id=incident.id,
            uploaded_by=actor.id,
            object_key=object_key,
            original_filename=clean_filename(file.filename),
            media_type=file.content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            storage_provider=storage.provider,
        )
        session.add(attachment)
        audit(session, "INCIDENT_PHOTO_UPLOADED", actor.id, resource=str(attachment_id))
        session.commit()
        session.refresh(attachment)
        return attachment
    except Exception:
        session.rollback()
        storage.delete(object_key)
        raise


@router.get(
    "/{report_id}/revisions/{number}/incidents/{incident_id}/attachments/{attachment_id}/content"
)
def download_incident_photo(
    report_id: UUID,
    number: int,
    incident_id: UUID,
    attachment_id: UUID,
    request: Request,
    actor: Authenticated,
    session: Db,
):
    _, revision = revision_for_report(session, report_id, number, actor)
    incident_for_revision(session, revision.id, incident_id)
    attachment = session.get(IncidentAttachment, attachment_id)
    if attachment is None or attachment.incident_id != incident_id:
        raise HTTPException(404, "Photographie d'incident introuvable.")
    try:
        content = request.app.state.object_storage.get(attachment.object_key)
    except StorageError as exc:
        raise HTTPException(503, "La photographie est indisponible.") from exc
    return Response(
        content,
        media_type=attachment.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{attachment.original_filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/{report_id}/revisions/{number}/incidents/{incident_id}/attachments/{attachment_id}",
    status_code=204,
)
def delete_incident_photo(
    report_id: UUID,
    number: int,
    incident_id: UUID,
    attachment_id: UUID,
    request: Request,
    actor: Agent,
    session: Db,
):
    report, revision = current_revision(session, report_id, number, actor)
    incident = incident_for_revision(session, revision.id, incident_id)
    if (
        report.created_by != actor.id
        or incident.created_by != actor.id
        or revision.status != "DRAFT"
    ):
        raise HTTPException(409, "La suppression exige le brouillon courant de son auteur.")
    attachment = session.get(IncidentAttachment, attachment_id)
    if attachment is None or attachment.incident_id != incident.id:
        raise HTTPException(404, "Photographie d'incident introuvable.")
    try:
        request.app.state.object_storage.delete(attachment.object_key)
    except StorageError as exc:
        raise HTTPException(503, "La suppression de la photographie a échoué.") from exc
    session.delete(attachment)
    audit(session, "INCIDENT_PHOTO_DELETED", actor.id, resource=str(attachment_id))
    session.commit()
    return Response(status_code=204)
