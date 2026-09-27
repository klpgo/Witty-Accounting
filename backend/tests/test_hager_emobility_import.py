from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.charging_session import ChargingSession
from app.services.hager_sync import known_wallbox_names
from app.services.importers.hager_json_importer import (
    import_charging_rows_to_db,
    parse_charging_row,
)


NAMES = {"WB-A": "WB2"}


def row(**overrides) -> dict:
    data = {
        "sessionID": "WB-A-1786536541000-12ab3c4d",
        "wallboxID": "WB-A",
        "startAt": "2026-08-12T12:09:01.000Z",
        "stopAt": "2026-08-12T12:14:03.000Z",
        "authType": "RFID",
        "authData": "de0d02a6",
        "energyAll": "188.00",
        "energySolar": "180.00",
        "status": "FINISHED",
    }
    data.update(overrides)
    return data


def create_database_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def legacy_session(**overrides) -> ChargingSession:
    """Ladevorgang aus einem früheren Import (Bridge/XLSX) ohne Wallbox-ID."""
    data = {
        "hager_session_id": "bridge-uuid-1",
        "station_id": "WB2",
        "wallbox_id": None,
        "start_time": datetime(2026, 8, 12, 14, 9, 1),
        "end_time": datetime(2026, 8, 12, 14, 14, 3),
        "rfid_number": None,
        "energy_total_kwh": 0.188,
        "energy_pv_kwh": 0.18,
        "invoiced": False,
        "invoice_id": None,
        "import_hash": "x" * 64,
        "source": "json",
    }
    data.update(overrides)
    return ChargingSession(**data)


# --------------------------------------------------------------------------
# Umrechnung
# --------------------------------------------------------------------------
def test_parse_converts_wh_to_kwh_and_utc_to_local_time() -> None:
    parsed = parse_charging_row(row(), NAMES)

    assert parsed["energy_total_kwh"] == pytest.approx(0.188)
    assert parsed["energy_pv_kwh"] == pytest.approx(0.18)
    assert parsed["start_time"] == datetime(2026, 8, 12, 14, 9, 1)
    assert parsed["end_time"] == datetime(2026, 8, 12, 14, 14, 3)
    assert parsed["rfid"] == "DE0D02A6"
    assert parsed["station_id"] == "WB2"
    assert parsed["wallbox_id"] == "WB-A"
    assert parsed["hager_session_id"] == "WB-A-1786536541000-12ab3c4d"
    assert parsed["source"] == "hager"


def test_parse_unknown_wallbox_uses_id() -> None:
    parsed = parse_charging_row(row(wallboxID="C7Hk"), NAMES)

    assert parsed["station_id"] == "ID: C7Hk"


def test_parse_without_card() -> None:
    assert parse_charging_row(row(authType="NONE", authData=""), NAMES)["rfid"] is None


def test_parse_running_session_is_skipped() -> None:
    assert parse_charging_row(row(stopAt=None), NAMES) is None


# --------------------------------------------------------------------------
# Import und Dublettenprüfung
# --------------------------------------------------------------------------
def test_import_stores_new_session_with_wallbox_id() -> None:
    with create_database_session() as db:
        result = import_charging_rows_to_db(db, [row()], NAMES)

        stored = db.scalar(select(ChargingSession))
        assert result["imported"] == 1
        assert stored.wallbox_id == "WB-A"
        assert stored.station_id == "WB2"
        assert stored.energy_total_kwh == pytest.approx(0.188)
        assert stored.rfid_number == "DE0D02A6"


def test_reimport_is_skipped() -> None:
    with create_database_session() as db:
        import_charging_rows_to_db(db, [row()], NAMES)
        result = import_charging_rows_to_db(db, [row()], NAMES)

        assert result["imported"] == 0
        assert result["skipped"] == 1


def test_legacy_bridge_session_is_recognized_and_backfilled() -> None:
    with create_database_session() as db:
        db.add(legacy_session())
        db.commit()

        result = import_charging_rows_to_db(db, [row()], NAMES)

        sessions = db.scalars(select(ChargingSession)).all()
        assert result["imported"] == 0
        assert len(sessions) == 1
        assert sessions[0].wallbox_id == "WB-A"
        assert sessions[0].rfid_number == "DE0D02A6"
        # bisherige Hager-ID bleibt erhalten
        assert sessions[0].hager_session_id == "bridge-uuid-1"


def test_legacy_session_of_replaced_wallbox_is_recognized() -> None:
    """Früher "witty plus 5", heute unbekannt ("ID: …"): einziger
    Ladevorgang zu dieser Sekunde -> derselbe."""
    with create_database_session() as db:
        db.add(legacy_session(station_id="witty plus 5"))
        db.commit()

        result = import_charging_rows_to_db(
            db,
            [row(wallboxID="C4Pku")],
            NAMES,
        )

        stored = db.scalars(select(ChargingSession)).all()
        assert result["imported"] == 0
        assert len(stored) == 1
        assert stored[0].station_id == "witty plus 5"
        assert stored[0].wallbox_id == "C4Pku"


def test_same_second_at_other_wallbox_is_not_a_duplicate() -> None:
    with create_database_session() as db:
        db.add(legacy_session(station_id="WB3", hager_session_id="b-1", import_hash="a" * 64))
        db.add(legacy_session(station_id="WB4", hager_session_id="b-2", import_hash="b" * 64))
        db.commit()

        result = import_charging_rows_to_db(db, [row()], NAMES)

        assert result["imported"] == 1


def test_invoiced_legacy_session_is_not_changed() -> None:
    with create_database_session() as db:
        db.add(legacy_session(invoiced=True))
        db.commit()

        result = import_charging_rows_to_db(db, [row()], NAMES)

        stored = db.scalar(select(ChargingSession))
        assert result["imported"] == 0
        assert stored.wallbox_id is None
        assert stored.rfid_number is None


def test_known_wallbox_names_keep_names_of_replaced_devices() -> None:
    with create_database_session() as db:
        db.add(legacy_session(wallbox_id="C4Pku", station_id="witty plus 5"))
        db.add(
            legacy_session(
                wallbox_id="C7Hk",
                station_id="ID: C7Hk",
                hager_session_id="b-2",
                import_hash="b" * 64,
                start_time=datetime(2026, 8, 13, 10, 0),
            )
        )
        db.commit()

        assert known_wallbox_names(db) == {"C4Pku": "witty plus 5"}


# --------------------------------------------------------------------------
# Import-Regeln und verworfene Vorgänge
# --------------------------------------------------------------------------
from datetime import date
from decimal import Decimal

from app.models.global_settings import GlobalSettings
from app.services.pricing import price_charging_sessions
from app.services.rfid_reassignment import reassign_open_sessions


def add_settings(db: Session, **values) -> None:
    db.add(
        GlobalSettings(
            id=1,
            monthly_base_fee_net=Decimal("0.0000"),
            monthly_base_fee_vat_rate=Decimal("19.00"),
            **values,
        )
    )
    db.commit()


def test_sessions_before_billing_start_are_not_imported() -> None:
    with create_database_session() as db:
        add_settings(db, billing_start_date=date(2026, 8, 13))

        result = import_charging_rows_to_db(
            db,
            [
                row(),  # 12.08.
                row(sessionID="late", startAt="2026-08-13T08:00:00.000Z",
                    stopAt="2026-08-13T09:00:00.000Z"),
            ],
            NAMES,
        )

        assert result["imported"] == 1
        assert result["skipped_before_billing_start"] == 1
        assert result["skipped"] == 0


def test_empty_sessions_are_skipped_when_configured() -> None:
    with create_database_session() as db:
        add_settings(db, import_skip_empty_sessions=True)

        result = import_charging_rows_to_db(
            db,
            [
                row(),
                row(sessionID="empty", energyAll="0.00", energySolar="0.00",
                    startAt="2026-08-12T11:00:00.000Z",
                    stopAt="2026-08-12T11:01:00.000Z"),
            ],
            NAMES,
        )

        assert result["imported"] == 1
        assert result["skipped_empty"] == 1


def test_empty_sessions_are_imported_by_default() -> None:
    with create_database_session() as db:
        add_settings(db)

        result = import_charging_rows_to_db(
            db,
            [row(energyAll="0.00", energySolar="0.00")],
            NAMES,
        )

        assert result["imported"] == 1


def test_discarded_session_is_not_imported_again() -> None:
    with create_database_session() as db:
        import_charging_rows_to_db(db, [row()], NAMES)
        stored = db.scalar(select(ChargingSession))
        stored.discarded_at = datetime(2026, 9, 1, 12, 0)
        db.commit()

        result = import_charging_rows_to_db(db, [row()], NAMES)

        assert result["imported"] == 0
        assert result["skipped"] == 1
        assert len(db.scalars(select(ChargingSession)).all()) == 1


def test_discarded_sessions_are_not_priced_or_reassigned() -> None:
    with create_database_session() as db:
        db.add(
            legacy_session(
                rfid_number="DE0D02A6",
                discarded_at=datetime(2026, 9, 1, 12, 0),
            )
        )
        db.commit()

        assert price_charging_sessions(db)["read"] == 0
        assert reassign_open_sessions(db) == 0
