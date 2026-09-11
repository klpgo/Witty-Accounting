import argparse
from getpass import getpass
import re

from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.tenancy.models import Tenant, TenantDomain
from app.tenancy.registry import (
    build_control_database_url,
    normalize_hostname,
)
from app.tenancy.secrets import (
    encrypt_tenant_db_password,
)


SAFE_TENANT_SLUG = re.compile(
    r"^[a-z0-9][a-z0-9_-]{0,99}$"
)


class TenantRegistrationError(RuntimeError):
    """The tenant cannot be registered safely."""


def validate_slug(
    value: str,
    *,
    field_name: str,
) -> str:
    normalized = value.strip().lower()

    if not SAFE_TENANT_SLUG.fullmatch(normalized):
        raise TenantRegistrationError(
            f"{field_name} darf nur Kleinbuchstaben, "
            "Ziffern, Unterstriche und Bindestriche "
            "enthalten."
        )

    return normalized


def register_tenant(
    db: Session,
    *,
    slug: str,
    name: str,
    hostname: str,
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_password: str,
    encryption_key: SecretStr | None,
) -> Tenant:
    normalized_slug = validate_slug(
        slug,
        field_name="Slug",
    )
    normalized_hostname = normalize_hostname(
        hostname
    )
    normalized_name = name.strip()

    if not normalized_name:
        raise TenantRegistrationError(
            "Der Mandantenname darf nicht leer sein."
        )

    if db_port < 1 or db_port > 65535:
        raise TenantRegistrationError(
            "Der Datenbank-Port ist ungültig."
        )

    database_values = {
        "DB-Host": db_host.strip(),
        "DB-Name": db_name.strip(),
        "DB-Benutzer": db_user.strip(),
    }

    for field_name, field_value in (
        database_values.items()
    ):
        if not field_value:
            raise TenantRegistrationError(
                f"{field_name} darf nicht leer sein."
            )

    existing_tenant = db.scalar(
        select(Tenant.id).where(
            Tenant.slug == normalized_slug
        )
    )
    existing_domain = db.scalar(
        select(TenantDomain.id).where(
            TenantDomain.hostname
            == normalized_hostname
        )
    )

    if existing_tenant is not None:
        raise TenantRegistrationError(
            "Dieser Mandanten-Slug ist bereits "
            "registriert."
        )

    if existing_domain is not None:
        raise TenantRegistrationError(
            "Diese Domain ist bereits registriert."
        )

    tenant = Tenant(
        slug=normalized_slug,
        name=normalized_name,
        active=True,
        db_host=database_values["DB-Host"],
        db_port=db_port,
        db_name=database_values["DB-Name"],
        db_user=database_values["DB-Benutzer"],
        db_password_encrypted=(
            encrypt_tenant_db_password(
                db_password,
                encryption_key=encryption_key,
            )
        ),
        archive_namespace=normalized_slug,
        config_version=1,
        domains=[
            TenantDomain(
                hostname=normalized_hostname,
                canonical=True,
            )
        ],
    )
    db.add(tenant)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(tenant)
    return tenant


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Registriert eine vorhandene "
            "Mandantendatenbank in witty_control."
        )
    )
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--db-host", required=True)
    parser.add_argument(
        "--db-port",
        type=int,
        default=3306,
    )
    parser.add_argument("--db-name", required=True)
    parser.add_argument("--db-user", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_password = getpass(
        "Passwort des Mandanten-DB-Benutzers: "
    )
    control_engine = create_engine(
        build_control_database_url(settings),
        pool_pre_ping=True,
    )

    try:
        with Session(control_engine) as db:
            tenant = register_tenant(
                db,
                slug=args.slug,
                name=args.name,
                hostname=args.hostname,
                db_host=args.db_host,
                db_port=args.db_port,
                db_name=args.db_name,
                db_user=args.db_user,
                db_password=db_password,
                encryption_key=(
                    settings
                    .tenant_db_encryption_key
                ),
            )
    except TenantRegistrationError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        control_engine.dispose()

    print(
        "Mandant registriert: "
        f"{tenant.id} ({tenant.slug})"
    )


if __name__ == "__main__":
    main()
