from collections.abc import Generator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import get_db
from app.auth import require_admin
from app.main import app


def override_get_db() -> Generator[object, None, None]:
    yield object()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = lambda: None

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_upload_json_returns_import_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import(db: Any, path: str | Path) -> dict[str, Any]:
        assert Path(path).suffix == ".json"
        assert Path(path).exists()

        return {
            "read": 3,
            "imported": 2,
            "skipped": 1,
            "unknown_rfid_sessions": 0,
            "unknown_rfid_numbers": [],
            "imported_hashes": ["a" * 64, "b" * 64],
        }

    def fake_pricing(
        db: Any,
        overwrite: bool = False,
        import_hashes: set[str] | None = None,
    ) -> dict[str, int]:
        assert import_hashes == {"a" * 64, "b" * 64}

        return {
            "read": 2,
            "priced": 2,
            "missing_price": 0,
            "invalid_energy": 0,
        }

    monkeypatch.setattr(
        "app.api.routes.imports.import_json_to_db",
        fake_import,
    )
    monkeypatch.setattr(
        "app.api.routes.imports.price_charging_sessions",
        fake_pricing,
    )

    response = client.post(
        "/api/imports/json",
        files={"file": ("sessions.json", b'{"sessions": []}', "application/json")},
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 2
    assert response.json()["priced"] == 2


def test_upload_json_rejects_other_extensions(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/imports/json",
        files={"file": ("sessions.txt", b"{}", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Es werden ausschließlich JSON-Dateien unterstützt."
    )


def test_upload_json_invalid_content_returns_400(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import(db: Any, path: str | Path) -> dict[str, Any]:
        raise ValueError("Die Datei ist kein gültiges JSON")

    monkeypatch.setattr(
        "app.api.routes.imports.import_json_to_db",
        fake_import,
    )

    response = client.post(
        "/api/imports/json",
        files={"file": ("sessions.json", b"{kaputt", "application/json")},
    )

    assert response.status_code == 400
    assert "kein gültiges JSON" in response.json()["detail"]
