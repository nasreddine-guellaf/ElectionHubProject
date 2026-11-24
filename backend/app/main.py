import logging
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth_api import router as auth_router
from app.auth_models import Account
from app.config import Settings
from app.database import create_db_engine, get_session
from app.document_api import router as document_router
from app.domain_api import router as domain_router
from app.domain_models import Report
from app.incident_api import router as incident_router
from app.models import PollingStation
from app.object_storage import create_object_storage
from app.otp_api import LocalSmsSender
from app.otp_api import router as otp_router
from app.schemas import HealthRead, PollingStationPage, PollingStationRead
from app.station_api import router as station_router
from app.validation_api import router as validation_router

logger = logging.getLogger(__name__)
SCHEMA_VERSION = "0005_incidents"
DbSession = Annotated[Session, Depends(get_session)]


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings()
    db_engine = engine if engine is not None else create_db_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if engine is None:
            db_engine.dispose()

    app = FastAPI(
        title="ElectionHub — Démonstration locale",
        description="Données fictives uniquement. Aucun vote électronique. "
        "Sessions, rôles serveur, validation humaine et stockage documentaire privé.",
        version="0.5.0",
        lifespan=lifespan,
    )
    app.state.engine = db_engine
    app.state.settings = settings
    app.state.sms_sender = LocalSmsSender(settings.mock_sms_directory)
    app.state.object_storage = create_object_storage(settings)
    app.include_router(domain_router)
    app.include_router(auth_router)
    app.include_router(otp_router)
    app.include_router(validation_router)
    app.include_router(station_router)
    app.include_router(document_router)
    app.include_router(incident_router)

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return JSONResponse(
            status_code=409, content={"detail": "Conflit de données ou référence utilisée."}
        )

    @app.exception_handler(RequestValidationError)
    async def request_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": "Requête invalide : vérifiez les champs, types et valeurs."},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        # Ne jamais journaliser la connexion, les paramètres SQL ou le détail de l'exception.
        logger.warning("Base de données indisponible (%s)", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Base de données indisponible."})

    @app.get("/health", response_model=HealthRead, tags=["État"])
    def health(session: DbSession):
        version = session.scalar(text("SELECT version_num FROM alembic_version"))
        if version != SCHEMA_VERSION:
            raise HTTPException(503, "Migration de base de données requise.")
        # Vérifie aussi que la table métier est lisible.
        session.execute(select(PollingStation.id).limit(1))
        session.execute(select(Report.id).limit(1))
        session.execute(select(Account.user_id).limit(1))
        return HealthRead(schema_version=version, environment=settings.app_env)

    @app.get("/api/v1/polling-stations", response_model=PollingStationPage, tags=["Bureaux"])
    def list_stations(
        session: DbSession,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        stations = session.scalars(
            select(PollingStation).order_by(PollingStation.code).offset(offset).limit(limit)
        ).all()
        total = session.scalar(select(func.count()).select_from(PollingStation))
        return PollingStationPage(
            items=[PollingStationRead.model_validate(station) for station in stations],
            total=total,
            limit=limit,
            offset=offset,
        )

    @app.get(
        "/api/v1/polling-stations/{station_id}",
        response_model=PollingStationRead,
        tags=["Bureaux"],
    )
    def get_station(station_id: UUID, session: DbSession):
        station = session.get(PollingStation, station_id)
        if station is None:
            raise HTTPException(404, "Bureau de vote introuvable.")
        return station

    return app
