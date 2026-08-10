from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):

    app_name: str = "Witty-Accounting"

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://dock.kgem.de:5173",
    ]

    db_host: str
    db_port: int = 3306
    db_name: str

    db_user: str
    db_password: str

    tenancy_enabled: bool = False

    control_db_host: str | None = None
    control_db_port: int = 3306
    control_db_name: str | None = None
    control_db_user: str | None = None
    control_db_password: SecretStr | None = None

    tenant_db_encryption_key: SecretStr | None = None
    tenant_registry_cache_seconds: int = 30
    tenant_engine_cache_size: int = 20

    witty_control_password: SecretStr | None = None
    witty_control_session_secret: SecretStr | None = None
    witty_control_session_minutes: int = 30

    tenant_provision_db_host: str | None = None
    tenant_provision_db_port: int | None = None
    tenant_provision_db_user: str = "root"
    tenant_provision_db_password: SecretStr | None = None
    tenant_provision_db_allowed_host: str = "%"

    log_level: str = "INFO"

    jwt_secret_key: SecretStr

    frontend_base_url: str = "http://localhost:5173"
    password_reset_token_expire_minutes: int = 60

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        # The project-level .env is shared with Docker Compose and therefore
        # also contains deployment-only values such as DB_ROOT_PASSWORD and
        # WITTY_UID.  They are intentionally not application settings.
        extra="ignore",
    )

    # Legacy fallbacks for installations that have not yet moved the
    # invoice issuer data into GlobalSettings.  They must not prevent the
    # application from starting when the database-backed settings are used.
    invoice_issuer_name: str | None = None
    invoice_issuer_address: str | None = None
    invoice_tax_number: str | None = None
    invoice_vat_id: str | None = None
    invoice_payment_term_days: int = 0

    invoice_pdf_archive_dir: Path = Path(
        "data/invoices"
    )

    ghostscript_executable: str = "gs"
    pdfa_icc_profile_path: Path = Path(
        "/usr/share/color/icc/ghostscript/srgb.icc"
    )
    pdfa_conversion_timeout_seconds: float = 30.0

    smtp_host: str = "host.docker.internal"
    smtp_port: int = 25
    smtp_timeout_seconds: float = 10.0
    smtp_starttls: bool = False

    mail_from_address: str = ""
    mail_from_name: str = "Witty-Accounting"

    mail_smime_enabled: bool = False
    mail_smime_pkcs12_path: Path | None = None
    mail_smime_pkcs12_password_file: (
        Path | None
    ) = None
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None

    smtp_settings_encryption_key: (
        SecretStr | None
    ) = None


settings = Settings()
