from app.config import settings
from app.database import Base, DATABASE_URL
from app.models import (
    import_state,
    invoice,
    password_reset_token,
)

from logging.config import fileConfig

target_metadata = Base.metadata

from sqlalchemy import create_engine, pool

from alembic import context
from alembic.util import CommandError

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    ensure_single_database_mode()

    url = (
        config.get_main_option("sqlalchemy.url")
        or DATABASE_URL
    )
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def get_database_url():
    configured_url = config.get_main_option(
        "sqlalchemy.url"
    )

    if configured_url:
        return configured_url

    return DATABASE_URL


def ensure_single_database_mode() -> None:
    """
    Im Mehrmandantenbetrieb hat jeder Mandant eine eigene Datenbank.
    Ein direktes `alembic upgrade` würde nur die Datenbank aus
    DATABASE_URL migrieren und die Mandanten auslassen – deshalb wird es
    abgebrochen. Mandanten migriert scripts.migrate_tenants (übergibt die
    Verbindung je Mandant). Ausnahme bei Bedarf:
    alembic -x allow_default_database=true upgrade head
    """
    if not settings.tenancy_enabled:
        return

    x_arguments = context.get_x_argument(as_dictionary=True)

    if str(x_arguments.get("allow_default_database", "")).lower() in {
        "1",
        "true",
        "yes",
    }:
        return

    raise CommandError(
        "Multi-tenant operation is enabled (TENANCY_ENABLED=true): "
        "alembic would only work on the database from DATABASE_URL, "
        "not on the tenant databases. To migrate the tenants, run "
        "'python -m scripts.migrate_tenants' instead, e.g. "
        "'docker compose run --rm --no-deps backend python -m "
        "scripts.migrate_tenants'."
    )


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
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

    ensure_single_database_mode()

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

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
