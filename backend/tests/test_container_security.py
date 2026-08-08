from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_compose_passes_configurable_witty_uid_and_gid() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(
        encoding="utf-8"
    )

    assert 'WITTY_UID: "${WITTY_UID:-1000}"' in compose
    assert 'WITTY_GID: "${WITTY_GID:-1000}"' in compose


def test_runtime_image_uses_non_root_witty_user() -> None:
    dockerfile = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "ARG WITTY_UID=1000" in dockerfile
    assert "ARG WITTY_GID=1000" in dockerfile
    assert 'test "${WITTY_UID}" -gt 0' in dockerfile
    assert 'test "${WITTY_GID}" -gt 0' in dockerfile
    assert "USER witty:witty" in dockerfile


def test_example_environment_documents_witty_uid_and_gid() -> None:
    example = (PROJECT_ROOT / ".env.example").read_text(
        encoding="utf-8"
    )

    assert "WITTY_UID=1000" in example
    assert "WITTY_GID=1000" in example
