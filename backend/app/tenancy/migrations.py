from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.pool import NullPool

from app.tenancy.context import TenantContext


BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
APPLICATION_ALEMBIC_CONFIG = (
    BACKEND_DIRECTORY / "alembic.ini"
)
CONTROL_ALEMBIC_CONFIG = (
    BACKEND_DIRECTORY / "control_alembic.ini"
)


@dataclass(frozen=True)
class TenantMigrationResult:
    tenant_id: int
    tenant_slug: str
    successful: bool
    error_type: str | None = None
    error_message: str | None = None


def upgrade_connection(
    connection: Connection,
    *,
    config_path: Path,
    revision: str = "head",
) -> None:
    config = Config(str(config_path))
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


def migrate_engine(
    migration_engine: Engine,
    *,
    config_path: Path,
    revision: str = "head",
) -> None:
    with migration_engine.connect() as connection:
        upgrade_connection(
            connection,
            config_path=config_path,
            revision=revision,
        )


def migrate_control_database(
    control_engine: Engine,
) -> None:
    migrate_engine(
        control_engine,
        config_path=CONTROL_ALEMBIC_CONFIG,
    )


def migrate_tenant_database(
    tenant: TenantContext,
) -> None:
    tenant_engine = create_engine(
        tenant.database_url(),
        pool_pre_ping=True,
        poolclass=NullPool,
    )

    try:
        migrate_engine(
            tenant_engine,
            config_path=(
                APPLICATION_ALEMBIC_CONFIG
            ),
        )
    finally:
        tenant_engine.dispose()


def migrate_active_tenants(
    tenants: list[TenantContext],
    *,
    tenant_slug: str | None = None,
    migrate: Callable[
        [TenantContext],
        None,
    ] = migrate_tenant_database,
) -> list[TenantMigrationResult]:
    selected_tenants = [
        tenant
        for tenant in tenants
        if (
            tenant_slug is None
            or tenant.slug == tenant_slug
        )
    ]

    if tenant_slug is not None and not selected_tenants:
        raise ValueError(
            "Der angegebene aktive Mandant wurde "
            "nicht gefunden."
        )

    results: list[TenantMigrationResult] = []

    for tenant in selected_tenants:
        try:
            migrate(tenant)
        except Exception as exc:
            results.append(
                TenantMigrationResult(
                    tenant_id=tenant.id,
                    tenant_slug=tenant.slug,
                    successful=False,
                    error_type=(
                        type(exc).__name__
                    ),
                    error_message=str(exc),
                )
            )
            continue

        results.append(
            TenantMigrationResult(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                successful=True,
            )
        )

    return results
