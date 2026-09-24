from collections.abc import Generator
from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import get_db
from app.auth import require_admin
from app.main import app
from app.services.hager_sync import (
    HagerConfigurationError,
    HagerConnectionError,
)


def override_get_db() -> Generator[object, None, None]:
    yield object()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = lambda: None

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def fake_pricing(
    db: Any,
    overwrite: bool = False,
    import_hashes: set[str] | None = None,
) -> dict[str, int]:
    return {
        "read": len(import_hashes or ()),
        "priced": len(import_hashes or ()),
        "missing_price": 0,
        "invalid_energy": 0,
    }


def test_hager_connection_test_returns_summary(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.hager_settings.check_connection",
        lambda db: {
            "sessions": 75,
            "latest_session_start": datetime(2026, 7, 15, 11, 26, 37),
        },
    )

    response = client.post("/api/settings/hager/test")

    assert response.status_code == 200
    assert response.json() == {
        "sessions": 75,
        "latest_session_start": "2026-07-15T11:26:37",
    }


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (HagerConfigurationError("fehlt: Passwort"), 422),
        (HagerConnectionError("Anmeldung abgelehnt"), 502),
    ],
)
def test_hager_connection_test_maps_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
) -> None:
    def fail(db: Any) -> None:
        raise error

    monkeypatch.setattr(
        "app.api.routes.hager_settings.check_connection",
        fail,
    )

    response = client.post("/api/settings/hager/test")

    assert response.status_code == status_code
    assert response.json()["detail"] == str(error)


def test_import_hager_without_body_imports_everything(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple] = []

    def fake_import(db: Any, date_from=None, date_to=None, fetch_all=False) -> dict[str, Any]:
        calls.append((date_from, date_to, fetch_all))
        return {
            "read": 3,
            "imported": 1,
            "skipped": 2,
            "unknown_rfid_sessions": 0,
            "unknown_rfid_numbers": [],
            "imported_hashes": ["a" * 64],
        }

    monkeypatch.setattr("app.api.routes.imports.import_from_hager", fake_import)
    monkeypatch.setattr("app.api.routes.imports.price_charging_sessions", fake_pricing)

    response = client.post("/api/imports/hager")

    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert response.json()["priced"] == 1
    assert calls == [(None, None, False)]


def test_import_hager_passes_date_range(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple] = []

    def fake_import(db: Any, date_from=None, date_to=None, fetch_all=False) -> dict[str, Any]:
        calls.append((str(date_from), str(date_to)))
        return {
            "read": 0,
            "imported": 0,
            "skipped": 0,
            "unknown_rfid_sessions": 0,
            "unknown_rfid_numbers": [],
            "imported_hashes": [],
        }

    monkeypatch.setattr("app.api.routes.imports.import_from_hager", fake_import)
    monkeypatch.setattr("app.api.routes.imports.price_charging_sessions", fake_pricing)

    response = client.post(
        "/api/imports/hager",
        json={"date_from": "2026-08-01", "date_to": "2026-08-31"},
    )

    assert response.status_code == 200
    assert calls == [("2026-08-01", "2026-08-31")]


def test_import_hager_rejects_inverted_range(client: TestClient) -> None:
    response = client.post(
        "/api/imports/hager",
        json={"date_from": "2026-09-01", "date_to": "2026-08-01"},
    )

    assert response.status_code == 422


def test_import_hager_connection_error_returns_502(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(db: Any, date_from=None, date_to=None, fetch_all=False) -> None:
        raise HagerConnectionError("Hager flow ist nicht erreichbar: ConnectTimeout")

    monkeypatch.setattr("app.api.routes.imports.import_from_hager", fail)

    response = client.post("/api/imports/hager")

    assert response.status_code == 502
    assert "nicht erreichbar" in response.json()["detail"]


def test_import_hager_fetch_all(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []

    def fake_import(db: Any, date_from=None, date_to=None, fetch_all=False) -> dict[str, Any]:
        calls.append(fetch_all)
        return {
            "read": 0,
            "imported": 0,
            "skipped": 0,
            "unknown_rfid_sessions": 0,
            "unknown_rfid_numbers": [],
            "imported_hashes": [],
            "fetched_from": None,
        }

    monkeypatch.setattr("app.api.routes.imports.import_from_hager", fake_import)
    monkeypatch.setattr("app.api.routes.imports.price_charging_sessions", fake_pricing)

    response = client.post("/api/imports/hager", json={"fetch_all": True})

    assert response.status_code == 200
    assert response.json()["fetched_from"] is None
    assert calls == [True]


def test_import_hager_fetch_all_with_range_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/imports/hager",
        json={"fetch_all": True, "date_from": "2026-08-01"},
    )

    assert response.status_code == 422
