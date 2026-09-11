from contextlib import contextmanager
import json
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.control.auth import ControlAuthenticationError, ControlAuthenticator
from app.control.main import create_control_app
from app.control.service import TenantControlError, TenantControlService
from app.tenancy.models import ControlBase, Tenant, TenantDomain
from app.tenancy.secrets import encrypt_tenant_db_password


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "db_host": "db",
        "db_name": "witty",
        "db_user": "witty",
        "db_password": "tenant-password",
        "jwt_secret_key": "x" * 32,
        "witty_control_password": "control-password",
        "witty_control_session_secret": "s" * 40,
        "tenant_db_encryption_key": Fernet.generate_key().decode("ascii"),
        "tenant_provision_db_password": "root-password",
        "tenant_registry_cache_seconds": 0,
        "invoice_pdf_archive_dir": tmp_path / "invoices",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


class DummyService:
    def __init__(self) -> None:
        self.state_calls = []
        self.name_calls = []
        self.hostname_calls = []
        self.delete_calls = []
        self.delete_error = None

    def list_tenants(self):
        return [{"id": 1, "code": "wb42", "active": True}]

    def create_tenant(self, data):
        return {"id": 2, "code": data.code}

    def set_active(self, tenant_id: int, *, active: bool):
        self.state_calls.append((tenant_id, active))

    def set_name(self, tenant_id: int, *, name: str):
        self.name_calls.append((tenant_id, name))

    def set_hostname(self, tenant_id: int, *, hostname: str):
        self.hostname_calls.append((tenant_id, hostname))

    def delete_tenant(self, tenant_id: int, *, confirmation: str, progress=None):
        self.delete_calls.append((tenant_id, confirmation))
        if self.delete_error:
            raise TenantControlError(self.delete_error)
        if progress:
            progress("validated", "Bestätigung wurde geprüft.")
            progress("complete", "Mandant wurde gelöscht.")


def test_control_login_session_csrf_and_reauthentication(tmp_path: Path) -> None:
    service = DummyService()
    app = create_control_app(make_settings(tmp_path), service=service)

    with TestClient(app) as client:
        assert client.get("/api/tenants").status_code == 401
        assert client.post(
            "/api/login", json={"password": "wrong"}
        ).status_code == 401

        login = client.post(
            "/api/login", json={"password": "control-password"}
        )
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        assert client.get("/api/tenants").status_code == 200

        assert client.put(
            "/api/tenants/1/state", json={"active": False}
        ).status_code == 403
        assert client.put(
            "/api/tenants/1/state",
            json={"active": False},
            headers={"X-Control-CSRF": csrf},
        ).status_code == 200
        assert service.state_calls == [(1, False)]

        assert client.put(
            "/api/tenants/1/name", json={"name": "Neuer Name"}
        ).status_code == 403
        assert client.put(
            "/api/tenants/1/name",
            json={"name": "Neuer Name"},
            headers={"X-Control-CSRF": csrf},
        ).status_code == 200
        assert service.name_calls == [(1, "Neuer Name")]

        assert client.put(
            "/api/tenants/1/hostname",
            json={"hostname": "neu.example.test"},
        ).status_code == 403
        assert client.put(
            "/api/tenants/1/hostname",
            json={"hostname": "neu.example.test"},
            headers={"X-Control-CSRF": csrf},
        ).status_code == 200
        assert service.hostname_calls == [(1, "neu.example.test")]

        assert client.post(
            "/api/tenants/1/delete",
            json={"confirmation": "wb42", "control_password": "wrong"},
            headers={"X-Control-CSRF": csrf},
        ).status_code == 403
        assert not service.delete_calls

        deletion = client.post(
            "/api/tenants/1/delete",
            json={
                "confirmation": "wb42",
                "control_password": "control-password",
            },
            headers={"X-Control-CSRF": csrf},
        )
        assert deletion.status_code == 200
        assert deletion.headers["content-type"].startswith(
            "application/x-ndjson"
        )
        events = [json.loads(line) for line in deletion.text.splitlines()]
        assert [event["type"] for event in events] == [
            "progress",
            "complete",
        ]
        assert service.delete_calls == [(1, "wb42")]

        service.delete_error = "Sicherheitsprüfung fehlgeschlagen."
        failed_deletion = client.post(
            "/api/tenants/1/delete",
            json={
                "confirmation": "wb42",
                "control_password": "control-password",
            },
            headers={"X-Control-CSRF": csrf},
        )
        failed_events = [
            json.loads(line) for line in failed_deletion.text.splitlines()
        ]
        assert failed_events == [
            {
                "type": "error",
                "step": "error",
                "message": "Sicherheitsprüfung fehlgeschlagen.",
            }
        ]


def test_control_session_expires() -> None:
    now = [1_000.0]
    auth = ControlAuthenticator(
        password=SecretStr("password"),
        session_secret=SecretStr("s" * 40),
        session_minutes=1,
        clock=lambda: now[0],
    )
    token, _session = auth.create_session()
    auth.verify_session(token)
    now[0] += 61

    with pytest.raises(ControlAuthenticationError, match="abgelaufen"):
        auth.verify_session(token)


@pytest.fixture
def control_engine():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ControlBase.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def add_tenant(engine, settings: Settings, *, code: str = "wb42") -> int:
    tenant = Tenant(
        slug=code,
        name="WB 42",
        active=True,
        db_host="db",
        db_port=3306,
        db_name=code,
        db_user=f"witty_{code}",
        db_password_encrypted=encrypt_tenant_db_password(
            "db-password",
            encryption_key=settings.tenant_db_encryption_key,
        ),
        archive_namespace=code,
        config_version=1,
        domains=[
            TenantDomain(hostname=f"{code}.example.test", canonical=True)
        ],
    )
    with Session(engine) as db:
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        return tenant.id


def test_delete_removes_database_user_archive_and_registration(
    tmp_path: Path,
    control_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(tmp_path)
    tenant_id = add_tenant(control_engine, settings)
    archive = settings.invoice_pdf_archive_dir / "wb42"
    archive.mkdir(parents=True)
    (archive / "invoice.pdf").write_bytes(b"test")
    service = TenantControlService(
        settings=settings,
        control_engine=control_engine,
    )
    dropped = []

    class FakeConnection:
        def close(self):
            pass

    @contextmanager
    def no_lock(_connection):
        yield

    monkeypatch.setattr(service, "_connect_admin", FakeConnection)
    monkeypatch.setattr(service, "_provision_lock", no_lock)
    monkeypatch.setattr(
        service,
        "_drop_database_and_user",
        lambda _connection, **values: dropped.append(values),
    )

    progress = []
    service.delete_tenant(
        tenant_id,
        confirmation="wb42",
        progress=lambda step, _message: progress.append(step),
    )

    assert dropped == [
        {"database_name": "wb42", "database_user": "witty_wb42"}
    ]
    assert progress == [
        "validated",
        "blocked",
        "database",
        "database_done",
        "archive",
        "archive_done",
        "registry",
        "complete",
    ]
    assert not archive.exists()
    with Session(control_engine) as db:
        assert db.scalar(select(Tenant.id)) is None


def test_delete_accepts_registered_bootstrap_database(
    tmp_path: Path,
    control_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(tmp_path)
    tenant_id = add_tenant(control_engine, settings)
    with Session(control_engine) as db:
        tenant = db.get(Tenant, tenant_id)
        tenant.db_name = settings.db_name
        tenant.db_user = settings.db_user
        db.commit()

    service = TenantControlService(
        settings=settings,
        control_engine=control_engine,
    )
    dropped = []

    class FakeConnection:
        def close(self):
            pass

    @contextmanager
    def no_lock(_connection):
        yield

    monkeypatch.setattr(service, "_connect_admin", FakeConnection)
    monkeypatch.setattr(service, "_provision_lock", no_lock)
    monkeypatch.setattr(
        service,
        "_drop_database_and_user",
        lambda _connection, **values: dropped.append(values),
    )

    service.delete_tenant(tenant_id, confirmation="wb42")

    assert dropped == [
        {"database_name": "witty", "database_user": "witty"}
    ]
    with Session(control_engine) as db:
        assert db.get(Tenant, tenant_id) is None


def test_set_name_trims_and_updates_tenant(
    tmp_path: Path,
    control_engine,
) -> None:
    settings = make_settings(tmp_path)
    tenant_id = add_tenant(control_engine, settings)
    service = TenantControlService(
        settings=settings,
        control_engine=control_engine,
    )

    service.set_name(tenant_id, name="  Witty Berlin  ")

    with Session(control_engine) as db:
        tenant = db.get(Tenant, tenant_id)
        assert tenant.name == "Witty Berlin"
        assert tenant.config_version == 2


def test_set_name_rejects_empty_name(
    tmp_path: Path,
    control_engine,
) -> None:
    settings = make_settings(tmp_path)
    tenant_id = add_tenant(control_engine, settings)
    service = TenantControlService(
        settings=settings,
        control_engine=control_engine,
    )

    with pytest.raises(TenantControlError, match="nicht leer"):
        service.set_name(tenant_id, name="   ")


def test_set_hostname_normalizes_and_updates_only_domain(
    tmp_path: Path,
    control_engine,
) -> None:
    settings = make_settings(tmp_path)
    tenant_id = add_tenant(control_engine, settings)
    service = TenantControlService(
        settings=settings,
        control_engine=control_engine,
    )

    service.set_hostname(
        tenant_id,
        hostname="  NEW.Example.Test.  ",
    )

    with Session(control_engine) as db:
        tenant = db.get(Tenant, tenant_id)
        domain = db.scalar(
            select(TenantDomain).where(
                TenantDomain.tenant_id == tenant_id,
                TenantDomain.canonical.is_(True),
            )
        )
        assert domain.hostname == "new.example.test"
        assert tenant.slug == "wb42"
        assert tenant.db_name == "wb42"
        assert tenant.db_user == "witty_wb42"
        assert tenant.archive_namespace == "wb42"
        assert tenant.config_version == 2


def test_set_hostname_rejects_registered_hostname(
    tmp_path: Path,
    control_engine,
) -> None:
    settings = make_settings(tmp_path)
    tenant_id = add_tenant(control_engine, settings)
    add_tenant(control_engine, settings, code="other")
    service = TenantControlService(
        settings=settings,
        control_engine=control_engine,
    )

    with pytest.raises(TenantControlError, match="bereits registriert"):
        service.set_hostname(
            tenant_id,
            hostname="other.example.test",
        )


def test_delete_refuses_unexpected_database_name(
    tmp_path: Path,
    control_engine,
) -> None:
    settings = make_settings(tmp_path)
    tenant_id = add_tenant(control_engine, settings)
    with Session(control_engine) as db:
        tenant = db.get(Tenant, tenant_id)
        tenant.db_name = "different"
        db.commit()

    service = TenantControlService(
        settings=settings,
        control_engine=control_engine,
    )
    with pytest.raises(TenantControlError, match="Datenbankname"):
        service.delete_tenant(tenant_id, confirmation="wb42")
