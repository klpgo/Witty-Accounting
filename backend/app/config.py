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

    secret_key: str

    log_level: str = "INFO"

    jwt_secret_key: SecretStr

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )

    invoice_issuer_name: str
    invoice_issuer_address: str
    invoice_tax_number: str | None = None
    invoice_vat_id: str | None = None
    invoice_payment_term_days: int = 0

    invoice_pdf_archive_dir: Path = Path(
        "data/invoices"
    )

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
