from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):

    app_name: str = "Witty-Accounting"

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


settings = Settings()
