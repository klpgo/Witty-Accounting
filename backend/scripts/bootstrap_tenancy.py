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
    archive_namespace: str | None,
    encryption_key: SecretStr,
    allow_legacy_archive_root: bool,
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

    candidate = TenantContext(
        id=0,
        slug=slug,
        name=name,
        db_host=db_host,
        db_port=db_port,
        db_name=db_name,
        db_user=db_user,
        db_password=db_password,
        archive_namespace=archive_namespace,
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
            archive_namespace=archive_namespace,
            encryption_key=encryption_key,
            allow_legacy_archive_root=(
                allow_legacy_archive_root
            ),
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
            "Die registrierte Domain wurde einem "
            "unerwarteten Mandanten zugeordnet."
        )

    verify_tenant(resolved)
    return tenant_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bereitet die Kontroll-Datenbank vor, "
            "migriert die vorhandene Witty-Datenbank "
            "und registriert sie als ersten Mandanten."
        )
    )
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--hostname", required=True)
    parser.add_argument(
        "--db-host",
        default=settings.db_host,
        help="Standard: DB_HOST aus .env",
    )
    parser.add_argument(
        "--db-port",
        type=int,
        default=settings.db_port,
        help="Standard: DB_PORT aus .env",
    )
    parser.add_argument(
        "--db-name",
        default=settings.db_name,
        help="Standard: DB_NAME aus .env",
    )
    parser.add_argument(
        "--db-user",
        default=settings.db_user,
        help="Standard: DB_USER aus .env",
    )
    parser.add_argument(
        "--archive-namespace",
        help=(
            "Unterverzeichnis im Rechnungsarchiv."
        ),
    )
    parser.add_argument(
        "--use-legacy-archive-root",
        action="store_true",
        help=(
            "Für den bestehenden ersten Mandanten: "
            "vorhandene PDF-Pfade unverändert lassen."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    encryption_key = (
        settings.tenant_db_encryption_key
    )

    if encryption_key is None:
        raise SystemExit(
            "TENANT_DB_ENCRYPTION_KEY fehlt."
        )

    db_password = getpass(
        "Passwort des bestehenden "
        "Mandanten-DB-Benutzers: "
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
            archive_namespace=(
                args.archive_namespace
            ),
            encryption_key=encryption_key,
            allow_legacy_archive_root=(
                args.use_legacy_archive_root
            ),
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
    print("Erster Mandant wurde vorbereitet:")
    print(f"  ID:     {tenant.id}")
    print(f"  Slug:   {tenant.slug}")
    print(f"  Domain: {args.hostname}")
    print()
    print(
        "Nächster Schritt: TENANCY_ENABLED=true "
        "setzen und das Backend neu starten."
    )


if __name__ == "__main__":
    main()
