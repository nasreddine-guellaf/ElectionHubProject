"""Téléversement et lecture autorisée des justificatifs privés de PV."""

import hashlib
import re
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select

from app.domain_models import ReportRevision
from app.object_storage import StorageError
from app.phase5_models import ReportDocument
from app.phase5_schemas import DocumentRead
from app.security import Authenticated, Db, Principal, accessible_report, audit, roles

Agent = Annotated[Principal, Depends(roles("AGENT"))]
router = APIRouter(prefix="/api/v1/reports", tags=["Pièces justificatives privées"])

FILE_TYPES = {
    "application/pdf": (".pdf", b"%PDF-"),
    "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": (".jpg", b"\xff\xd8\xff"),
}


def revision_for_report(session, report_id, number, actor):
    report = accessible_report(session, report_id, actor)
    revision = session.scalar(
        select(ReportRevision).where(
            ReportRevision.report_id == report_id,
            ReportRevision.revision_number == number,
        )
    )
    if revision is None:
        raise HTTPException(404, "Révision introuvable.")
    return report, revision


def current_revision(session, report_id, number, actor):
    report, revision = revision_for_report(session, report_id, number, actor)
    if report.current_revision != number:
        raise HTTPException(409, "Cette révision n'est plus la révision courante.")
    return report, revision


def clean_filename(name: str | None) -> str:
    value = Path(name or "document").name.strip()[:255]
    return re.sub(r"[^A-Za-z0-9._ -]", "_", value) or "document"


@router.get("/{report_id}/revisions/{number}/documents", response_model=list[DocumentRead])
def documents(report_id: UUID, number: int, actor: Authenticated, session: Db):
    report = accessible_report(session, report_id, actor)
    revision = session.scalar(
        select(ReportRevision).where(
            ReportRevision.report_id == report.id, ReportRevision.revision_number == number
        )
    )
    if revision is None:
        raise HTTPException(404, "Révision introuvable.")
    return session.scalars(
        select(ReportDocument)
        .where(ReportDocument.revision_id == revision.id)
        .order_by(ReportDocument.created_at, ReportDocument.id)
    ).all()


@router.post(
    "/{report_id}/revisions/{number}/documents",
    response_model=DocumentRead,
    status_code=201,
)
async def upload_document(
    report_id: UUID,
    number: int,
    request: Request,
    session: Db,
    actor: Agent,
    expected_version: Annotated[int, Form(ge=1)],
    file: Annotated[UploadFile, File()],
):
    report, revision = current_revision(session, report_id, number, actor)
    if report.created_by != actor.id:
        raise HTTPException(403, "Seul l'auteur peut ajouter une pièce à ce dossier.")
    if revision.status != "DRAFT":
        raise HTTPException(409, "Les pièces sont modifiables uniquement sur un brouillon.")
    if revision.edit_version != expected_version:
        raise HTTPException(409, "Version obsolète : rechargez le PV.")
    if file.content_type not in FILE_TYPES:
        raise HTTPException(415, "Formats autorisés : PDF, JPEG et PNG.")
    content = await file.read(request.app.state.settings.object_upload_max_bytes + 1)
    if not content:
        raise HTTPException(422, "Le fichier est vide.")
    if len(content) > request.app.state.settings.object_upload_max_bytes:
        raise HTTPException(413, "Le fichier dépasse la taille maximale autorisée.")
    suffix, signature = FILE_TYPES[file.content_type]
    if not content.startswith(signature):
        raise HTTPException(422, "Le contenu du fichier ne correspond pas à son format.")

    document_id = uuid4()
    object_key = f"reports/{report.id}/revisions/{number}/{document_id}{suffix}"
    storage = request.app.state.object_storage
    try:
        storage.put(
            object_key,
            content,
            file.content_type,
            {"document-id": str(document_id), "revision-id": str(revision.id)},
        )
    except StorageError as exc:
        raise HTTPException(503, "Le stockage documentaire est indisponible.") from exc
    try:
        document = ReportDocument(
            id=document_id,
            revision_id=revision.id,
            uploaded_by=actor.id,
            object_key=object_key,
            original_filename=clean_filename(file.filename),
            media_type=file.content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            storage_provider=storage.provider,
        )
        session.add(document)
        audit(session, "DOCUMENT_UPLOADED", actor.id, resource=str(document_id))
        session.commit()
        session.refresh(document)
        return document
    except Exception:
        session.rollback()
        storage.delete(object_key)
        raise


@router.get("/{report_id}/revisions/{number}/documents/{document_id}/content")
def download_document(
    report_id: UUID,
    number: int,
    document_id: UUID,
    request: Request,
    actor: Authenticated,
    session: Db,
):
    _, revision = revision_for_report(session, report_id, number, actor)
    document = session.get(ReportDocument, document_id)
    if document is None or document.revision_id != revision.id:
        raise HTTPException(404, "Pièce justificative introuvable.")
    try:
        content = request.app.state.object_storage.get(document.object_key)
    except StorageError as exc:
        raise HTTPException(503, "La pièce justificative est indisponible.") from exc
    return Response(
        content,
        media_type=document.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.original_filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{report_id}/revisions/{number}/documents/{document_id}", status_code=204)
def delete_document(
    report_id: UUID,
    number: int,
    document_id: UUID,
    request: Request,
    actor: Agent,
    session: Db,
):
    report, revision = current_revision(session, report_id, number, actor)
    if report.created_by != actor.id or revision.status != "DRAFT":
        raise HTTPException(409, "La suppression exige le brouillon courant de son auteur.")
    document = session.get(ReportDocument, document_id)
    if document is None or document.revision_id != revision.id:
        raise HTTPException(404, "Pièce justificative introuvable.")
    try:
        request.app.state.object_storage.delete(document.object_key)
    except StorageError as exc:
        raise HTTPException(503, "La suppression de la pièce a échoué.") from exc
    session.delete(document)
    audit(session, "DOCUMENT_DELETED", actor.id, resource=str(document_id))
    session.commit()
    return Response(status_code=204)
