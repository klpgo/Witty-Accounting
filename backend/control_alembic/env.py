from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings
from app.tenancy.models import ControlBase
from app.tenancy.registry import (
    build_control_database_url,
)


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = ControlBase.metadata


def get_database_url():
    configured_url = config.get_main_option(
        "sqlalchemy.url"
    )

    if configured_url:
        return configured_url

    return build_control_database_url(settings)


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied_connection = config.attributes.get(
        "connection"
    )

    if supplied_connection is not None:
        context.configure(
            connection=supplied_connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()

        return

    connectable = create_engine(
        get_database_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
