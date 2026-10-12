from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import Base
from app.models.global_settings import GlobalSettings
from app.services.data_timezone import (
    DataTimezoneMismatchError,
    ensure_data_timezone,
)
from app.utils.local_time import TIMEZONE_NAME


REQUIRED = {
    "db_host": "db",
    "db_name": "witty",
    "db_user": "witty",
    "db_password": "geheim",
    "jwt_secret_key": "x" * 32,
}


def settings_session(**values) -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(
        GlobalSettings(
            id=1,
            monthly_base_fee_net=Decimal("0.0000"),
            monthly_base_fee_vat_rate=Decimal("19.00"),
            **values,
        )
    )
    db.commit()
    return db


# --------------------------------------------------------------------------
# Einstellung aus TZ
# --------------------------------------------------------------------------
def test_tests_run_with_berlin_time() -> None:
    assert TIMEZONE_NAME == "Europe/Berlin"


def test_timezone_is_read_from_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Europe/Vienna")

    assert Settings(_env_file=None, **REQUIRED).timezone == "Europe/Vienna"


def test_default_is_berlin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TZ", raising=False)

    assert Settings(_env_file=None, **REQUIRED).timezone == "Europe/Berlin"


def test_leading_colon_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", ":Europe/Berlin")

    assert Settings(_env_file=None, **REQUIRED).timezone == "Europe/Berlin"


def test_invalid_timezone_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Mitteleuropa")

    with pytest.raises(ValueError, match="Invalid time zone"):
        Settings(_env_file=None, **REQUIRED)


# --------------------------------------------------------------------------
# Schutz vor einem Wechsel
# --------------------------------------------------------------------------
def test_first_import_records_timezone() -> None:
    db = settings_session()

    ensure_data_timezone(db, "Europe/Berlin")

    assert db.get(GlobalSettings, 1).data_timezone == "Europe/Berlin"


def test_same_timezone_is_accepted() -> None:
    db = settings_session(data_timezone="Europe/Berlin")

    ensure_data_timezone(db, "Europe/Berlin")


def test_changed_timezone_is_rejected() -> None:
    db = settings_session(data_timezone="Europe/Berlin")

    with pytest.raises(DataTimezoneMismatchError, match="Europe/Berlin"):
        ensure_data_timezone(db, "UTC")

    assert db.get(GlobalSettings, 1).data_timezone == "Europe/Berlin"


def test_json_file_import_is_rejected_after_timezone_change(tmp_path) -> None:
    from app.services.importers.hager_json_importer import import_json_to_db

    db = settings_session(data_timezone="UTC")
    path = tmp_path / "sessions.json"
    path.write_text('{"sessions": []}', encoding="utf-8")

    with pytest.raises(DataTimezoneMismatchError):
        import_json_to_db(db, path)


def test_json_file_import_records_timezone(tmp_path) -> None:
    from app.services.importers.hager_json_importer import import_json_to_db

    db = settings_session()
    path = tmp_path / "sessions.json"
    path.write_text('{"sessions": []}', encoding="utf-8")

    import_json_to_db(db, path)

    assert db.get(GlobalSettings, 1).data_timezone == TIMEZONE_NAME
