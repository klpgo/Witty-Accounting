from pathlib import Path

from app.config import Settings


def test_legacy_invoice_environment_values_are_optional() -> None:
    settings = Settings(
        db_host="db",
        db_name="witty_accounting",
        db_user="witty",
        db_password="test-password",
        jwt_secret_key="x" * 32,
        _env_file=None,
    )

    assert settings.invoice_issuer_name is None
    assert settings.invoice_issuer_address is None


def test_compose_only_environment_values_are_ignored(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "DB_HOST=db",
                "DB_NAME=witty_accounting",
                "DB_USER=witty",
                "DB_PASSWORD=test-password",
                f"JWT_SECRET_KEY={'x' * 32}",
                "DB_ROOT_PASSWORD=root-password",
                "WITTY_UID=1000",
                "WITTY_GID=1000",
                "WITTY_DATA_DIR=/srv/witty",
                "WITTY_BIND_ADDRESS=0.0.0.0",
                "WITTY_PORT=8000",
            )
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.db_host == "db"
    assert settings.db_name == "witty_accounting"
