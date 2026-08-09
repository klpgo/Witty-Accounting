from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import SecretStr
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import database as database_module
from app.config import Settings
from app.database import TenantSessionProvider
from app.services import invoice_archive
from app.tenancy.context import TenantContext
from app.tenancy.models import (
    ControlBase,
    Tenant,
    TenantDomain,
)
from app.tenancy.registry import (
    DatabaseTenantRegistry,
    LegacyTenantRegistry,
    TenantNotFoundError,
    TenantRegistryError,
    build_tenant_registry,
    normalize_hostname,
)
from app.tenancy.secrets import (
    encrypt_tenant_db_password,
)


@pytest.fixture
def control_engine():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )
    ControlBase.metadata.create_all(engine)

    try:
        yield engine
    finally:
        ControlBase.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def tenant_encryption_key() -> SecretStr:
    return SecretStr(
        Fernet.generate_key().decode("ascii")
    )


def add_tenant(
    db: Session,
    *,
    encryption_key: SecretStr,
    hostname: str = "kunde-a.witty.example",
    active: bool = True,
) -> Tenant:
    tenant = Tenant(
        slug="kunde-a",
        name="Kunde A",
        active=active,
        db_host="mariadb",
        db_port=3306,
        db_name="witty_kunde_a",
        db_user="witty_kunde_a",
        db_password_encrypted=(
            encrypt_tenant_db_password(
                "tenant-password",
                encryption_key=encryption_key,
            )
        ),
        archive_namespace="kunde-a",
        config_version=3,
    )
    tenant.domains.extend(
        [
            TenantDomain(
                hostname=hostname,
                canonical=True,
            ),
            TenantDomain(
                hostname="alias.witty.example",
                canonical=False,
            ),
        ]
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def test_normalizes_hostname() -> None:
    assert normalize_hostname(
        "KUNDE-A.WITTY.EXAMPLE."
    ) == "kunde-a.witty.example"


def test_registry_resolves_domain_and_decrypts_database_password(
    control_engine,
    tenant_encryption_key: SecretStr,
) -> None:
    with Session(control_engine) as db:
        tenant_model = add_tenant(
            db,
            encryption_key=tenant_encryption_key,
        )
        tenant_id = tenant_model.id

    registry = DatabaseTenantRegistry(
        engine=control_engine,
        encryption_key=tenant_encryption_key,
        cache_seconds=30,
    )

    tenant = registry.resolve(
        "KUNDE-A.WITTY.EXAMPLE."
    )

    assert tenant.id == tenant_id
    assert tenant.slug == "kunde-a"
    assert tenant.db_name == "witty_kunde_a"
    assert tenant.db_password == "tenant-password"
    assert tenant.archive_namespace == "kunde-a"
    assert tenant.canonical_hostname == (
        "kunde-a.witty.example"
    )
    assert tenant.config_version == 3
    assert registry.get_by_id(tenant_id) == tenant
    assert registry.list_active() == [tenant]


def test_registry_resolves_alias_to_canonical_domain(
    control_engine,
    tenant_encryption_key: SecretStr,
) -> None:
    with Session(control_engine) as db:
        add_tenant(
            db,
            encryption_key=tenant_encryption_key,
        )

    registry = DatabaseTenantRegistry(
        engine=control_engine,
        encryption_key=tenant_encryption_key,
    )

    tenant = registry.resolve(
        "alias.witty.example"
    )

    assert tenant.canonical_hostname == (
        "kunde-a.witty.example"
    )


@pytest.mark.parametrize(
    ("hostname", "active"),
    [
        ("unknown.witty.example", True),
        ("kunde-a.witty.example", False),
    ],
)
def test_registry_rejects_unknown_or_inactive_tenant(
    control_engine,
    tenant_encryption_key: SecretStr,
    hostname: str,
    active: bool,
) -> None:
    with Session(control_engine) as db:
        add_tenant(
            db,
            encryption_key=tenant_encryption_key,
            active=active,
        )

    registry = DatabaseTenantRegistry(
        engine=control_engine,
        encryption_key=tenant_encryption_key,
    )

    with pytest.raises(TenantNotFoundError):
        registry.resolve(hostname)


def make_settings(**overrides) -> Settings:
    values = {
        "db_host": "db",
        "db_name": "witty_accounting",
        "db_user": "witty",
        "db_password": "test-password",
        "jwt_secret_key": "x" * 32,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_legacy_registry_preserves_single_tenant_mode() -> None:
    registry = LegacyTenantRegistry(
        make_settings()
    )

    first = registry.resolve("localhost")
    second = registry.resolve(
        "any-old-host.example"
    )

    assert first == second
    assert first.archive_namespace is None
    assert first.db_name == "witty_accounting"


def test_enabled_tenancy_requires_control_configuration() -> None:
    with pytest.raises(
        TenantRegistryError,
        match="TENANT_DB_ENCRYPTION_KEY",
    ):
        build_tenant_registry(
            make_settings(tenancy_enabled=True)
        )


def test_session_provider_uses_separate_engines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_engines = []

    def create_sqlite_engine(_url, **_kwargs):
        database_path = (
            tmp_path
            / f"tenant-{len(created_engines)}.db"
        )
        created_engine = create_engine(
            f"sqlite+pysqlite:///{database_path}"
        )
        created_engines.append(created_engine)
        return created_engine

    monkeypatch.setattr(
        database_module,
        "create_engine",
        create_sqlite_engine,
    )
    provider = TenantSessionProvider(
        max_cached_engines=2
    )
    first_tenant = TenantContext(
        id=10,
        slug="a",
        name="A",
        db_host="db",
        db_port=3306,
        db_name="a",
        db_user="a",
        db_password="secret-a",
        archive_namespace="a",
    )
    second_tenant = TenantContext(
        id=20,
        slug="b",
        name="B",
        db_host="db",
        db_port=3306,
        db_name="b",
        db_user="b",
        db_password="secret-b",
        archive_namespace="b",
    )

    with provider.create_session(
        first_tenant
    ) as first_db:
        first_db.execute(
            text("CREATE TABLE marker (value TEXT)")
        )
        first_db.execute(
            text(
                "INSERT INTO marker (value) "
                "VALUES ('tenant-a')"
            )
        )
        first_db.commit()
        assert first_db.info["tenant"] == (
            first_tenant
        )

    with provider.create_session(
        second_tenant
    ) as second_db:
        with pytest.raises(SQLAlchemyError):
            second_db.execute(
                text("SELECT value FROM marker")
            ).scalar_one()

    assert len(created_engines) == 2
    assert provider.get_engine(first_tenant) is (
        created_engines[0]
    )
    provider.dispose()


def test_archive_root_uses_tenant_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = TenantContext(
        id=10,
        slug="kunde-a",
        name="Kunde A",
        db_host="db",
        db_port=3306,
        db_name="a",
        db_user="a",
        db_password="secret",
        archive_namespace="kunde-a",
    )
    db = Session()
    db.info["tenant"] = tenant
    monkeypatch.setattr(
        invoice_archive.settings,
        "invoice_pdf_archive_dir",
        tmp_path,
    )

    assert invoice_archive.get_archive_root(
        None,
        db=db,
    ) == (tmp_path / "kunde-a").resolve()
