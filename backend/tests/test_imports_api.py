from collections.abc import Generator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import get_db
from app.main import app

from app.auth import require_admin


def override_get_db() -> Generator[object, None, None]:
    yield object()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    def override_require_admin() -> None:
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[
        require_admin
    ] = override_require_admin


    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_upload_xlsx_returns_import_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import_calls = 0

    def fake_import(
        db: Any,
        path: str | Path,
    ) -> dict[str, Any]:
        nonlocal import_calls
        import_calls += 1

        temporary_path = Path(path)

        assert temporary_path.exists()
        assert temporary_path.suffix == ".xlsx"

        return {
            "read": 2,
            "imported": 2,
            "skipped": 0,
            "unknown_rfid_sessions": 1,
            "unknown_rfid_numbers": ["ABC123"],
            "imported_hashes": [
                "a" * 64,
                "b" * 64,
            ],
        }

    def fake_pricing(
        db: Any,
        overwrite: bool = False,
        import_hashes: set[str] | None = None,
    ) -> dict[str, int]:
        assert overwrite is False
        assert import_hashes == {
            "a" * 64,
            "b" * 64,
        }

        return {
            "read": 2,
            "priced": 2,
            "missing_price": 0,
            "invalid_energy": 0,
        }

    monkeypatch.setattr(
        "app.api.routes.imports.import_xlsx_to_db",
        fake_import,
    )

    monkeypatch.setattr(
        "app.api.routes.imports.price_charging_sessions",
        fake_pricing,
    )

    response = client.post(
        "/api/imports/xlsx",
        files={
            "file": (
                "hager-export.xlsx",
                b"test-content",
                (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            )
        },
    )

    assert response.status_code == 200, response.text
    assert import_calls == 1
    assert response.json() == {
        "read": 2,
        "imported": 2,
        "skipped": 0,
        "unknown_rfid_sessions": 1,
        "unknown_rfid_numbers": ["ABC123"],
        "priced": 2,
        "missing_price": 0,
        "invalid_energy": 0,
    }


def test_upload_rejects_non_xlsx_file(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/imports/xlsx",
        files={
            "file": (
                "export.csv",
                b"some,data",
                "text/csv",
            )
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": (
            "Es werden ausschließlich XLSX-Dateien unterstützt."
        )
    }

def test_upload_rejects_empty_xlsx(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/imports/xlsx",
        files={
            "file": (
                "empty.xlsx",
                b"",
                (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            )
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Die hochgeladene Datei ist leer."
    }


def test_upload_rejects_oversized_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.imports.MAX_UPLOAD_SIZE_BYTES",
        8,
    )

    response = client.post(
        "/api/imports/xlsx",
        files={
            "file": (
                "large.xlsx",
                b"123456789",
                (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            )
        },
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": (
            "Die XLSX-Datei ist zu groß. "
            "Maximal erlaubt sind 10 MB."
        )
    }


def test_upload_rejects_corrupt_xlsx(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/imports/xlsx",
        files={
            "file": (
                "corrupt.xlsx",
                b"Das ist keine XLSX-Datei",
                (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"].startswith(
        "Die XLSX-Datei konnte nicht importiert werden:"
    )


