from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import SPAStaticFiles, app


def build_static_test_app(
    directory: Path,
) -> FastAPI:
    test_app = FastAPI()
    test_app.mount(
        "/",
        SPAStaticFiles(
            directory=directory,
            html=True,
        ),
    )
    return test_app


def test_backend_routes_use_api_prefix() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/auth/token" in paths
    assert "/api/invoices" in paths
    assert "/auth/token" not in paths
    assert "/invoices" not in paths


def test_spa_route_returns_index(
    tmp_path: Path,
) -> None:
    (tmp_path / "index.html").write_text(
        "<html>Witty frontend</html>",
        encoding="utf-8",
    )

    with TestClient(
        build_static_test_app(tmp_path)
    ) as client:
        response = client.get("/invoices/42")

    assert response.status_code == 200
    assert response.text == (
        "<html>Witty frontend</html>"
    )


def test_spa_does_not_hide_unknown_api_route(
    tmp_path: Path,
) -> None:
    (tmp_path / "index.html").write_text(
        "<html>Witty frontend</html>",
        encoding="utf-8",
    )

    with TestClient(
        build_static_test_app(tmp_path)
    ) as client:
        response = client.get("/api/unknown")

    assert response.status_code == 404


def test_versioned_assets_are_cached(
    tmp_path: Path,
) -> None:
    assets_directory = tmp_path / "assets"
    assets_directory.mkdir()
    (tmp_path / "index.html").write_text(
        "<html>Witty frontend</html>",
        encoding="utf-8",
    )
    (assets_directory / "app-123.js").write_text(
        "console.log('witty')",
        encoding="utf-8",
    )

    with TestClient(
        build_static_test_app(tmp_path)
    ) as client:
        response = client.get(
            "/assets/app-123.js"
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == (
        "public, max-age=31536000, immutable"
    )
