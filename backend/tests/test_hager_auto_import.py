from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.global_settings import GlobalSettings
from app.services import hager_auto_import
from app.services.hager_auto_import import (
    STATUS_ERROR,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    check_all_tenants,
    start_if_due,
)
from app.services.hager_schedule import LOCAL_TIMEZONE
from app.services.hager_sync import HagerConnectionError
from app.tenancy.context import TenantContext


NOW = datetime(2026, 9, 24, 14, 30, tzinfo=LOCAL_TIMEZONE)


def make_tenant(tenant_id: int) -> TenantContext:
    return TenantContext(
        id=tenant_id,
        slug=f"mandant-{tenant_id}",
        name=f"Mandant {tenant_id}",
        db_host="localhost",
        db_port=3306,
        db_name=f"db{tenant_id}",
        db_user="user",
        db_password="secret",
    )


class TenantDatabases:
    """Eine SQLite-Datenbank pro Mandant."""

    def __init__(self) -> None:
        self.engines = {}

    def add(self, tenant: TenantContext, **settings) -> None:
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)

        with Session(engine) as db:
            db.add(
                GlobalSettings(
                    id=1,
                    monthly_base_fee_net=Decimal("0.0000"),
                    monthly_base_fee_vat_rate=Decimal("19.00"),
                    hager_username="user@example.com",
                    hager_password_encrypted="verschluesselt",
                    hager_installation_id="1000143617",
                    **settings,
                )
            )
            db.commit()

        self.engines[tenant.id] = engine

    def session(self, tenant: TenantContext) -> Session:
        return Session(self.engines[tenant.id])

    def settings(self, tenant: TenantContext) -> GlobalSettings:
        with Session(self.engines[tenant.id]) as db:
            settings = db.get(GlobalSettings, 1)
            db.expunge(settings)
            return settings


def run_now(fn, *args):
    fn(*args)


@pytest.fixture(autouse=True)
def fake_import(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def import_from_hager(db):
        calls.append("import")
        return {
            "read": 5,
            "imported": 2,
            "skipped": 3,
            "unknown_rfid_sessions": 0,
            "unknown_rfid_numbers": [],
            "imported_hashes": ["a" * 64, "b" * 64],
            "fetched_from": date(2026, 9, 21),
        }

    def price_charging_sessions(db, overwrite=False, import_hashes=None):
        return {"read": 2, "priced": 2, "missing_price": 0, "invalid_energy": 0}

    monkeypatch.setattr(hager_auto_import, "import_from_hager", import_from_hager)
    monkeypatch.setattr(
        hager_auto_import,
        "price_charging_sessions",
        price_charging_sessions,
    )
    hager_auto_import._running_tenants.clear()

    return calls


def test_disabled_tenant_is_not_started(fake_import) -> None:
    tenant = make_tenant(1)
    databases = TenantDatabases()
    databases.add(tenant, hager_auto_import_enabled=False)

    assert not start_if_due(tenant, NOW, databases.session, run_now)
    assert fake_import == []


def test_due_tenant_runs_and_records_success(fake_import) -> None:
    tenant = make_tenant(1)
    databases = TenantDatabases()
    databases.add(
        tenant,
        hager_auto_import_enabled=True,
        hager_auto_import_interval_hours=6,
        hager_auto_import_start_time="03:00",
    )

    assert start_if_due(tenant, NOW, databases.session, run_now)

    settings = databases.settings(tenant)
    assert fake_import == ["import"]
    assert settings.hager_auto_import_last_status == STATUS_SUCCESS
    assert settings.hager_auto_import_last_message == (
        "2 neu, 3 übersprungen (abgerufen ab 21.09.2026)"
    )
    assert settings.hager_auto_import_last_started_at == (
        NOW.astimezone(UTC).replace(tzinfo=None)
    )
    assert settings.hager_auto_import_last_finished_at is not None


def test_not_due_until_next_slot(fake_import) -> None:
    tenant = make_tenant(1)
    databases = TenantDatabases()
    databases.add(
        tenant,
        hager_auto_import_enabled=True,
        hager_auto_import_interval_hours=6,
        hager_auto_import_start_time="03:00",
    )

    assert start_if_due(tenant, NOW, databases.session, run_now)

    later = datetime(2026, 9, 24, 14, 59, tzinfo=LOCAL_TIMEZONE)
    next_slot = datetime(2026, 9, 24, 15, 0, tzinfo=LOCAL_TIMEZONE)

    assert not start_if_due(tenant, later, databases.session, run_now)
    assert start_if_due(tenant, next_slot, databases.session, run_now)
    assert fake_import == ["import", "import"]


def test_start_is_recorded_before_import_runs(fake_import) -> None:
    tenant = make_tenant(1)
    databases = TenantDatabases()
    databases.add(tenant, hager_auto_import_enabled=True)
    submitted = []

    assert start_if_due(
        tenant,
        NOW,
        databases.session,
        lambda fn, *args: submitted.append(args),
    )

    settings = databases.settings(tenant)
    assert settings.hager_auto_import_last_status == STATUS_RUNNING
    assert len(submitted) == 1
    # läuft noch -> nicht erneut starten, auch nicht zum nächsten Termin
    assert not start_if_due(
        tenant,
        datetime(2026, 9, 26, 4, 0, tzinfo=LOCAL_TIMEZONE),
        databases.session,
        run_now,
    )


def test_error_is_recorded(fake_import, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_import(db):
        raise HagerConnectionError("Anmeldung abgelehnt – E-Mail oder Passwort prüfen.")

    monkeypatch.setattr(hager_auto_import, "import_from_hager", failing_import)

    tenant = make_tenant(1)
    databases = TenantDatabases()
    databases.add(tenant, hager_auto_import_enabled=True)

    assert start_if_due(tenant, NOW, databases.session, run_now)

    settings = databases.settings(tenant)
    assert settings.hager_auto_import_last_status == STATUS_ERROR
    assert "Anmeldung abgelehnt" in settings.hager_auto_import_last_message
    assert tenant.id not in hager_auto_import._running_tenants


def test_unexpected_error_is_recorded_without_details(
    fake_import,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_import(db):
        raise KeyError("intern")

    monkeypatch.setattr(hager_auto_import, "import_from_hager", broken_import)

    tenant = make_tenant(1)
    databases = TenantDatabases()
    databases.add(tenant, hager_auto_import_enabled=True)

    start_if_due(tenant, NOW, databases.session, run_now)

    settings = databases.settings(tenant)
    assert settings.hager_auto_import_last_status == STATUS_ERROR
    assert settings.hager_auto_import_last_message == "Unerwarteter Fehler: KeyError"


def test_each_tenant_uses_its_own_schedule(fake_import) -> None:
    hourly, daily, disabled = make_tenant(1), make_tenant(2), make_tenant(3)
    databases = TenantDatabases()
    databases.add(
        hourly,
        hager_auto_import_enabled=True,
        hager_auto_import_interval_hours=1,
        hager_auto_import_last_started_at=datetime(2026, 9, 24, 11, 0, 30),
    )
    databases.add(
        daily,
        hager_auto_import_enabled=True,
        hager_auto_import_interval_hours=24,
        hager_auto_import_last_started_at=datetime(2026, 9, 24, 1, 0, 30),
    )
    databases.add(disabled, hager_auto_import_enabled=False)

    started = check_all_tenants(
        now=NOW,
        list_tenants=lambda: [hourly, daily, disabled],
        session_factory=databases.session,
        submit=run_now,
    )

    # 14:30 Ortszeit: stündlich fällig (letzter Lauf 13:00), täglich nicht
    assert started == 1
    assert databases.settings(hourly).hager_auto_import_last_status == STATUS_SUCCESS
    assert databases.settings(daily).hager_auto_import_last_status is None


def test_broken_tenant_does_not_block_others(fake_import) -> None:
    broken, healthy = make_tenant(1), make_tenant(2)
    databases = TenantDatabases()
    databases.add(healthy, hager_auto_import_enabled=True)

    def session_factory(tenant: TenantContext) -> Session:
        if tenant.id == broken.id:
            raise RuntimeError("Datenbank nicht erreichbar")
        return databases.session(tenant)

    started = check_all_tenants(
        now=NOW,
        list_tenants=lambda: [broken, healthy],
        session_factory=session_factory,
        submit=run_now,
    )

    assert started == 1
    assert databases.settings(healthy).hager_auto_import_last_status == STATUS_SUCCESS


def test_registry_error_is_handled() -> None:
    def failing_registry():
        raise RuntimeError("Kontroll-Datenbank nicht erreichbar")

    assert check_all_tenants(now=NOW, list_tenants=failing_registry) == 0
