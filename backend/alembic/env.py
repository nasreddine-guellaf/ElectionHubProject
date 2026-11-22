from alembic import context
from app import (
    auth_models,  # noqa: F401 -- enregistre les métadonnées de sécurité
    domain_models,  # noqa: F401 -- enregistre les métadonnées métier
    phase5_models,  # noqa: F401 -- enregistre les métadonnées documentaires
)
from app.config import Settings
from app.database import Base, create_db_engine
from app.models import PollingStation  # noqa: F401 -- enregistre les métadonnées

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=Settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # Les tests injectent une connexion vers leur schéma isolé.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        configure_and_run(connection)
        return
    engine = create_db_engine(Settings())
    try:
        with engine.connect() as connection:
            configure_and_run(connection)
    finally:
        engine.dispose()


def configure_and_run(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
