from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.tenancy.models import (
    ControlBase,
    Tenant,
    TenantDomain,
)
from scripts.bootstrap_tenancy import (
    bootstrap_existing_tenant,
    parse_args,
)


def test_bootstrap_cli_uses_existing_database_settings(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "bootstrap_tenancy",
            "--slug",
            "WB42",
            "--name",
            "Am Wolfsberg 42",
            "--hostname",
            " wb42.witty.kgem.de ",
        ],
    )

    args = parse_args()

    assert args.db_host == "db"
    assert args.db_port == 3306
    assert args.db_name == "witty"
    assert args.db_user == "witty"


def test_bootstrap_migrates_before_registering() -> None:
    control_engine = create_engine(
        "sqlite+pysqlite://"
    )
    encryption_key = SecretStr(
        Fernet.generate_key().decode("ascii")
    )
    stages = []

    def migrate_control(engine) -> None:
        stages.append("control")
        ControlBase.metadata.create_all(engine)

    def migrate_tenant(tenant) -> None:
        stages.append(f"migrate:{tenant.slug}")

        with Session(control_engine) as db:
            assert db.scalar(
                select(Tenant.id)
            ) is None

    def verify_tenant(tenant) -> None:
        stages.append(f"verify:{tenant.slug}")

    try:
        tenant = bootstrap_existing_tenant(
            control_engine,
            slug="existing",
            name="Existing Tenant",
            hostname="existing.witty.example",
            db_host="db",
            db_port=3306,
            db_name="witty_accounting",
            db_user="witty",
            db_password="tenant-password",
            encryption_key=encryption_key,
            migrate_control=migrate_control,
            migrate_tenant=migrate_tenant,
            verify_tenant=verify_tenant,
        )

        with Session(control_engine) as db:
            domain = db.scalar(
                select(TenantDomain)
            )

            assert db.scalar(
                select(Tenant.slug)
            ) == "existing"
            assert domain is not None
            assert domain.hostname == (
                "existing.witty.example"
            )

        assert tenant.slug == "existing"
        assert tenant.archive_namespace == "existing"
        assert stages == [
            "control",
            "migrate:existing",
            "verify:existing",
            "verify:existing",
        ]
    finally:
        ControlBase.metadata.drop_all(
            control_engine
        )
        control_engine.dispose()
