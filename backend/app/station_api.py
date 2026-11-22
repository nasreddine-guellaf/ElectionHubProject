"""Gestion du référentiel des bureaux, réservée aux administrateurs."""

from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.domain_schemas import Code, Count, Input, Name
from app.domain_service import require
from app.models import PollingStation
from app.schemas import PollingStationRead
from app.security import Admin, Db, audit

router = APIRouter(prefix="/api/v1/polling-stations", tags=["Administration des bureaux"])


class StationInput(Input):
    code: Code
    name: Name
    registered_voters: Count


@router.post("", response_model=PollingStationRead, status_code=201)
def create_station(data: StationInput, actor: Admin, session: Db):
    station = PollingStation(**data.model_dump())
    session.add(station)
    session.flush()
    audit(session, "STATION_CREATED", actor.id, resource=str(station.id))
    session.commit()
    return station


@router.put("/{station_id}", response_model=PollingStationRead)
def update_station(station_id: UUID, data: StationInput, actor: Admin, session: Db):
    station = session.scalar(
        select(PollingStation).where(PollingStation.id == station_id).with_for_update()
    )
    if station is None:
        station = require(session, PollingStation, station_id)
    for key, value in data.model_dump().items():
        setattr(station, key, value)
    # Les effectifs ElectionStation / ReportRevision sont des instantanés indépendants.
    audit(session, "STATION_UPDATED", actor.id, resource=str(station_id))
    session.commit()
    return station


@router.delete("/{station_id}", status_code=204)
def delete_station(station_id: UUID, actor: Admin, session: Db):
    station = require(session, PollingStation, station_id)
    session.delete(station)
    # Les clés étrangères interdisent la suppression d'un bureau utilisé.
    audit(session, "STATION_DELETED", actor.id, resource=str(station_id))
    session.commit()
    return Response(status_code=204)
