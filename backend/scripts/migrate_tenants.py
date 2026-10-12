import argparse

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.tenancy.migrations import (
    migrate_active_tenants,
    migrate_control_database,
)
from app.tenancy.registry import (
    DatabaseTenantRegistry,
    TenantRegistryError,
    build_control_database_url,
)


def build_registry() -> DatabaseTenantRegistry:
    encryption_key: SecretStr | None = (
        settings.tenant_db_encryption_key
    )

    if encryption_key is None:
        raise TenantRegistryError(
            "TENANT_DB_ENCRYPTION_KEY is missing."
        )

    control_engine = create_engine(
        build_control_database_url(settings),
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    return DatabaseTenantRegistry(
        engine=control_engine,
        encryption_key=encryption_key,
        cache_seconds=0,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Runs the Witty Alembic migrations for all active tenants."
        )
    )
    parser.add_argument(
        "--tenant",
        help=(
            "Optionally migrate only the tenant with this code."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry = build_registry()

    try:
        migrate_control_database(registry.engine)
        tenants = registry.list_active()
        results = migrate_active_tenants(
            tenants,
            tenant_slug=args.tenant,
        )
    except (TenantRegistryError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        registry.engine.dispose()

    if not results:
        raise SystemExit(
            "No active tenants are registered."
        )

    failed = False

    for result in results:
        if result.successful:
            print(
                f"[OK] {result.tenant_slug} has been migrated."
            )
            continue

        failed = True
        print(
            f"[ERROR] {result.tenant_slug}: {result.error_type}: {result.error_message}"
        )

    if failed:
        raise SystemExit(
            "At least one tenant database could not be migrated."
        )


if __name__ == "__main__":
    main()
