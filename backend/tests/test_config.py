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
