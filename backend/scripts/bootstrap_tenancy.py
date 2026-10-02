import argparse
from collections.abc import Callable
from getpass import getpass

from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.config import settings
from app.tenancy.context import TenantContext
from app.tenancy.migrations import (
    migrate_control_database,
    migrate_tenant_database,
)
from app.tenancy.registry import (
    DatabaseTenantRegistry,
    TenantRegistryError,
    build_control_database_url,
)
from scripts.register_tenant import (
    TenantRegistrationError,
    register_tenant,
    validate_slug,
)


class TenancyBootstrapError(RuntimeError):
    """The first tenant could not be prepared safely."""


def verify_tenant_database(
    tenant: TenantContext,
) -> None:
    tenant_engine = create_engine(
        tenant.database_url(),
        pool_pre_ping=True,
        poolclass=NullPool,
    )

    try:
        with tenant_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        tenant_engine.dispose()


def bootstrap_existing_tenant(
    control_engine: Engine,
    *,
    slug: str,
    name: str,
    hostname: str,
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_password: str,
    encryption_key: SecretStr,
    migrate_control: Callable[
        [Engine], None
    ] = migrate_control_database,
    migrate_tenant: Callable[
        [TenantContext], None
    ] = migrate_tenant_database,
    verify_tenant: Callable[
        [TenantContext], None
    ] = verify_tenant_database,
):
    migrate_control(control_engine)
    normalized_slug = validate_slug(
        slug,
        field_name="Slug",
    )

    candidate = TenantContext(
        id=0,
        slug=normalized_slug,
        name=name,
        db_host=db_host,
        db_port=db_port,
        db_name=db_name,
        db_user=db_user,
        db_password=db_password,
        archive_namespace=normalized_slug,
        canonical_hostname=hostname,
    )

    # The existing business database is migrated and checked
    # before it becomes reachable through tenant routing.
    migrate_tenant(candidate)
    verify_tenant(candidate)

    with Session(control_engine) as db:
        tenant_model = register_tenant(
            db,
            slug=slug,
            name=name,
            hostname=hostname,
            db_host=db_host,
            db_port=db_port,
            db_name=db_name,
            db_user=db_user,
            db_password=db_password,
            encryption_key=encryption_key,
        )
        tenant_id = tenant_model.id

    registry = DatabaseTenantRegistry(
        engine=control_engine,
        encryption_key=encryption_key,
        cache_seconds=0,
    )
    resolved = registry.resolve(hostname)

    if resolved.id != tenant_id:
        raise TenancyBootstrapError(
            "The registered domain resolves to an unexpected tenant."
        )

    verify_tenant(resolved)
    return tenant_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepares the control database, migrates the existing Witty "
            "database and registers it as the first tenant."
        )
    )
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--hostname", required=True)
    parser.add_argument(
        "--db-host",
        default=settings.db_host,
        help="Default: DB_HOST from .env",
    )
    parser.add_argument(
        "--db-port",
        type=int,
        default=settings.db_port,
        help="Default: DB_PORT from .env",
    )
    parser.add_argument(
        "--db-name",
        default=settings.db_name,
        help="Default: DB_NAME from .env",
    )
    parser.add_argument(
        "--db-user",
        default=settings.db_user,
        help="Default: DB_USER from .env",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    encryption_key = (
        settings.tenant_db_encryption_key
    )

    if encryption_key is None:
        raise SystemExit(
            "TENANT_DB_ENCRYPTION_KEY is missing."
        )

    db_password = getpass(
        "Password of the existing tenant database user: "
    )
    control_engine = create_engine(
        build_control_database_url(settings),
        pool_pre_ping=True,
        poolclass=NullPool,
    )

    try:
        tenant = bootstrap_existing_tenant(
            control_engine,
            slug=args.slug,
            name=args.name,
            hostname=args.hostname,
            db_host=args.db_host,
            db_port=args.db_port,
            db_name=args.db_name,
            db_user=args.db_user,
            db_password=db_password,
            encryption_key=encryption_key,
        )
    except (
        TenantRegistrationError,
        TenantRegistryError,
        TenancyBootstrapError,
    ) as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        control_engine.dispose()

    print()
    print("First tenant has been prepared:")
    print(f"  ID:     {tenant.id}")
    print(f"  Slug:   {tenant.slug}")
    print(f"  Domain: {args.hostname}")
    print()
    print(
        "Next step: set TENANCY_ENABLED=true and restart the backend."
    )


if __name__ == "__main__":
    main()
