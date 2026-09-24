from datetime import date, datetime

from app.services.hager_sync import (
    filter_by_local_date,
    session_local_start,
)


def item(start: str) -> dict:
    return {"session": {"start_date_time": start}}


def test_session_local_start_converts_to_local_time() -> None:
    assert session_local_start(
        item("2026-07-31T22:30:00Z")
    ) == datetime(2026, 8, 1, 0, 30)


def test_session_local_start_invalid_returns_none() -> None:
    assert session_local_start({"session": {}}) is None
    assert session_local_start({}) is None


def test_filter_by_local_date_uses_local_day() -> None:
    items = [
        item("2026-07-31T21:30:00Z"),  # 31.07. 23:30 lokal
        item("2026-07-31T22:30:00Z"),  # 01.08. 00:30 lokal
        item("2026-08-31T21:59:00Z"),  # 31.08. 23:59 lokal
        item("2026-08-31T22:00:00Z"),  # 01.09. 00:00 lokal
    ]

    selected = filter_by_local_date(
        items,
        date(2026, 8, 1),
        date(2026, 8, 31),
    )

    assert selected == items[1:3]


def test_filter_without_range_returns_all() -> None:
    items = [item("2026-07-31T21:30:00Z")]

    assert filter_by_local_date(items, None, None) is items


# --------------------------------------------------------------------------
# Abruf mit Token-Cache
# --------------------------------------------------------------------------
import pytest

from app.services import hager_client, hager_sync
from app.services.hager_sync import (
    HagerAccess,
    HagerConnectionError,
    fetch_all_sessions,
)


ACCESS = HagerAccess(
    username="user@example.com",
    password="pw",
    installation_id="1000143617",
)


class FakeCache:
    def __init__(self) -> None:
        self.calls: list[bool] = []

    def get_access_token(self, username, password, force_login=False):
        self.calls.append(force_login)
        return "fresh" if force_login else "cached"

    def invalidate(self, username=None):
        self.invalidated = username


def test_fetch_uses_cached_token(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = FakeCache()
    monkeypatch.setattr(hager_sync, "token_cache", cache)
    monkeypatch.setattr(
        hager_client,
        "fetch_sessions",
        lambda token, installation_id: [{"token": token}],
    )

    assert fetch_all_sessions(ACCESS) == [{"token": "cached"}]
    assert cache.calls == [False]


def test_fetch_retries_once_with_new_login_on_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = FakeCache()

    def fake_fetch(token, installation_id):
        if token == "cached":
            raise hager_client.HagerUnauthorizedError("HTTP 401")
        return [{"token": token}]

    monkeypatch.setattr(hager_sync, "token_cache", cache)
    monkeypatch.setattr(hager_client, "fetch_sessions", fake_fetch)

    assert fetch_all_sessions(ACCESS) == [{"token": "fresh"}]
    assert cache.calls == [False, True]


def test_fetch_gives_up_after_second_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def always_401(token, installation_id):
        raise hager_client.HagerUnauthorizedError("HTTP 401")

    monkeypatch.setattr(hager_sync, "token_cache", FakeCache())
    monkeypatch.setattr(hager_client, "fetch_sessions", always_401)

    with pytest.raises(HagerConnectionError, match="401"):
        fetch_all_sessions(ACCESS)


def test_connection_check_forces_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = FakeCache()
    monkeypatch.setattr(hager_sync, "token_cache", cache)
    monkeypatch.setattr(hager_sync, "load_access", lambda db: ACCESS)
    options: dict = {}

    def fake_fetch(token, installation_id, **kwargs):
        options.update(kwargs)
        kwargs["info"]["total_elements"] = 250
        return [item("2026-07-15T09:26:37Z")]

    monkeypatch.setattr(hager_client, "fetch_sessions", fake_fetch)

    result = hager_sync.check_connection(db=None)

    # nur erste Seite, Gesamtzahl aus der API
    assert options["max_pages"] == 1
    assert result == {
        "sessions": 250,
        "latest_session_start": datetime(2026, 7, 15, 11, 26, 37),
    }
    assert cache.calls == [True]


def test_fetch_retries_once_with_new_login_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    cache = FakeCache()

    def fake_fetch(token, installation_id):
        if token == "cached":
            raise httpx.ReadTimeout("keine Antwort")
        return [{"token": token}]

    monkeypatch.setattr(hager_sync, "token_cache", cache)
    monkeypatch.setattr(hager_client, "fetch_sessions", fake_fetch)

    assert fetch_all_sessions(ACCESS) == [{"token": "fresh"}]
    assert cache.calls == [False, True]


def test_fetch_reports_timeout_after_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    def always_timeout(token, installation_id):
        raise httpx.ReadTimeout("keine Antwort")

    monkeypatch.setattr(hager_sync, "token_cache", FakeCache())
    monkeypatch.setattr(hager_client, "fetch_sessions", always_timeout)

    with pytest.raises(HagerConnectionError, match="ReadTimeout"):
        fetch_all_sessions(ACCESS)


# --------------------------------------------------------------------------
# Cut-off
# --------------------------------------------------------------------------
from datetime import UTC
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.global_settings import GlobalSettings
from app.services.hager_sync import (
    determine_cutoff,
    import_from_hager,
    local_day_start,
)


def test_cutoff_without_history_is_none() -> None:
    assert determine_cutoff(None, None) is None


def test_cutoff_is_last_fetch_minus_three_days() -> None:
    # 24.09. 01:30 UTC = 24.09. 03:30 Ortszeit -> 21.09.
    assert determine_cutoff(datetime(2026, 9, 24, 1, 30), None) == date(2026, 9, 21)


def test_cutoff_never_before_billing_start() -> None:
    assert determine_cutoff(
        datetime(2026, 9, 24, 1, 30),
        date(2026, 9, 23),
    ) == date(2026, 9, 23)
    assert determine_cutoff(None, date(2026, 6, 1)) == date(2026, 6, 1)


def test_local_day_start_is_midnight_local_time() -> None:
    assert local_day_start(date(2026, 9, 21)) == datetime(2026, 9, 20, 22, 0, tzinfo=UTC)


@pytest.fixture
def sync_db(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fetched: list[dict] = []
    imported: list[list] = []

    def fake_fetch_all_sessions(access, force_login=False, **options):
        fetched.append(options)
        return [
            item("2026-09-23T10:00:00Z"),
            item("2026-09-18T10:00:00Z"),
        ]

    def fake_import_items(db, items):
        imported.append(items)
        return {"read": len(items), "imported": len(items), "skipped": 0}

    monkeypatch.setattr(hager_sync, "load_access", lambda db: ACCESS)
    monkeypatch.setattr(hager_sync, "fetch_all_sessions", fake_fetch_all_sessions)
    monkeypatch.setattr(hager_sync, "import_items_to_db", fake_import_items)

    with Session(engine) as db:
        db.add(
            GlobalSettings(
                id=1,
                monthly_base_fee_net=Decimal("0.0000"),
                monthly_base_fee_vat_rate=Decimal("19.00"),
                hager_last_successful_fetch_at=datetime(2026, 9, 24, 1, 30),
            )
        )
        db.commit()
        yield db, fetched, imported

    engine.dispose()


def test_import_uses_cutoff_and_updates_last_fetch(sync_db) -> None:
    db, fetched, imported = sync_db

    result = import_from_hager(db)

    assert result["fetched_from"] == date(2026, 9, 21)
    assert fetched[0]["stop_before"] == local_day_start(date(2026, 9, 21))
    # Session vom 18.09. liegt vor dem Cut-off
    assert len(imported[0]) == 1
    assert db.get(GlobalSettings, 1).hager_last_successful_fetch_at > datetime(
        2026, 9, 24, 1, 30
    )


def test_import_fetch_all_has_no_cutoff(sync_db) -> None:
    db, fetched, imported = sync_db

    result = import_from_hager(db, fetch_all=True)

    assert result["fetched_from"] is None
    assert fetched[0]["stop_before"] is None
    assert len(imported[0]) == 2


def test_import_with_range_keeps_last_fetch(sync_db) -> None:
    db, fetched, imported = sync_db

    result = import_from_hager(
        db,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 20),
    )

    assert result["fetched_from"] == date(2026, 9, 1)
    assert fetched[0]["stop_before"] == local_day_start(date(2026, 9, 1))
    assert len(imported[0]) == 1
    assert db.get(GlobalSettings, 1).hager_last_successful_fetch_at == datetime(
        2026, 9, 24, 1, 30
    )


def test_failed_import_keeps_last_fetch(sync_db, monkeypatch: pytest.MonkeyPatch) -> None:
    db, _fetched, _imported = sync_db

    def failing_fetch(access, force_login=False, **options):
        raise HagerConnectionError("Hager flow ist nicht erreichbar: ReadTimeout")

    monkeypatch.setattr(hager_sync, "fetch_all_sessions", failing_fetch)

    with pytest.raises(HagerConnectionError):
        import_from_hager(db)

    assert db.get(GlobalSettings, 1).hager_last_successful_fetch_at == datetime(
        2026, 9, 24, 1, 30
    )
