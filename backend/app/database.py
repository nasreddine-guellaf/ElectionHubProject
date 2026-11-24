from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import Settings


class Base(DeclarativeBase):
    pass


def create_db_engine(settings: Settings) -> Engine:
    connect_args: dict[str, str | int] = {
        "connect_timeout": settings.postgres_connect_timeout_seconds,
        "sslmode": settings.postgres_sslmode,
    }
    if settings.postgres_sslrootcert is not None:
        connect_args["sslrootcert"] = str(settings.postgres_sslrootcert)
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout=settings.postgres_pool_timeout_seconds,
        pool_recycle=settings.postgres_pool_recycle_seconds,
        connect_args=connect_args,
        hide_parameters=True,
    )


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session
