from collections.abc import Generator

from cryptography.fernet import Fernet
from pydantic import SecretStr
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.tenancy.models import ControlBase
from app.tenancy.registry import (
    DatabaseTenantRegistry,
)
from scripts.register_tenant import (
    TenantRegistrationError,
    register_tenant,
)


@pytest.fixture
def control_db() -> Generator[
    Session,
    None,
    None,
]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )
    ControlBase.metadata.create_all(engine)

    with Session(engine) as db:
        yield db

    ControlBase.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def encryption_key() -> SecretStr:
    return SecretStr(
        Fernet.generate_key().decode("ascii")
    )


def test_registers_existing_tenant_database(
    control_db: Session,
    encryption_key: SecretStr,
) -> None:
    tenant_model = register_tenant(
        control_db,
        slug="Kunde-A",
        name="Kunde A",
        hostname="KUNDE-A.WITTY.EXAMPLE.",
        db_host="mariadb",
        db_port=3306,
        db_name="witty_kunde_a",
        db_user="witty_kunde_a",
        db_password="tenant-password",
        encryption_key=encryption_key,
    )
    registry = DatabaseTenantRegistry(
        engine=control_db.get_bind(),
        encryption_key=encryption_key,
    )

    tenant = registry.resolve(
        "kunde-a.witty.example"
    )

    assert tenant.id == tenant_model.id
    assert tenant.slug == "kunde-a"
    assert tenant.db_password == "tenant-password"


def test_rejects_duplicate_domain(
    control_db: Session,
    encryption_key: SecretStr,
) -> None:
    arguments = {
        "name": "Kunde A",
        "hostname": "kunde-a.witty.example",
        "db_host": "mariadb",
        "db_port": 3306,
        "db_name": "witty_kunde_a",
        "db_user": "witty_kunde_a",
        "db_password": "tenant-password",
        "encryption_key": encryption_key,
    }
    register_tenant(
        control_db,
        slug="kunde-a",
        **arguments,
    )

    with pytest.raises(
        TenantRegistrationError,
        match="Domain ist bereits",
    ):
        register_tenant(
            control_db,
            slug="kunde-b",
            **arguments,
        )


def test_archive_namespace_is_derived_from_slug(
    control_db: Session,
    encryption_key: SecretStr,
) -> None:
    tenant = register_tenant(
        control_db,
        slug="Existing",
        name="Existing",
        hostname="existing.witty.example",
        db_host="mariadb",
        db_port=3306,
        db_name="witty_existing",
        db_user="witty_existing",
        db_password="tenant-password",
        encryption_key=encryption_key,
    )

    assert tenant.archive_namespace == "existing"
