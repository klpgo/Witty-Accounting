import json
from datetime import datetime
from pathlib import Path

import pytest

from app.services.importers.hager_json_importer import (
    extract_session_items,
    import_json,
    parse_session,
    parse_utc_to_local,
    station_label,
)


def make_item(**overrides):
    session = {
        "id": "cbe8e0d1-3224-480c-9d2f-579b4b8bd4e5",
        "kwh": 12.345,
        "status": "COMPLETED",
        "start_date_time": "2026-07-15T09:26:37Z",
        "end_date_time": "2026-07-15T11:27:30Z",
    }
    session.update(overrides.pop("session", {}))
    item = {
        "session": session,
        "emobilitySessionId": "HB-1784107597909",
        "wallboxId": "HBgvt8tTxAczTHd2hfTHMj",
        "wallboxName": "WB5",
        "emobilityToken": "de0d02a6",
        "energySolar": 1.5,
        "status": "FINISHED",
    }
    item.update(overrides)
    return item


def test_parse_utc_to_local_summer_and_winter_time() -> None:
    assert parse_utc_to_local(
        "2026-07-15T09:26:37Z", "x"
    ) == datetime(2026, 7, 15, 11, 26, 37)
    assert parse_utc_to_local(
        "2026-01-15T09:26:37Z", "x"
    ) == datetime(2026, 1, 15, 10, 26, 37)


def test_parse_utc_to_local_month_boundary() -> None:
    # 31.07. 22:30 UTC ist bereits der 01.08. in Deutschland
    assert parse_utc_to_local(
        "2026-07-31T22:30:00Z", "x"
    ) == datetime(2026, 8, 1, 0, 30, 0)


def test_parse_session_maps_fields() -> None:
    parsed = parse_session(make_item())

    assert parsed is not None
    assert parsed["hager_session_id"] == (
        "cbe8e0d1-3224-480c-9d2f-579b4b8bd4e5"
    )
    assert parsed["start_time"] == datetime(2026, 7, 15, 11, 26, 37)
    assert parsed["end_time"] == datetime(2026, 7, 15, 13, 27, 30)
    assert parsed["station_id"] == "WB5"
    assert parsed["rfid"] == "DE0D02A6"
    assert parsed["energy_total_kwh"] == pytest.approx(12.345)
    assert parsed["energy_pv_kwh"] == pytest.approx(1.5)
    assert parsed["source"] == "json"
    assert len(parsed["import_hash"]) == 64


def test_parse_session_without_token() -> None:
    parsed = parse_session(make_item(emobilityToken=None))

    assert parsed is not None
    assert parsed["rfid"] is None


def test_parse_session_running_returns_none() -> None:
    assert parse_session(
        make_item(session={"end_date_time": None})
    ) is None


def test_parse_session_falls_back_to_emobility_session_id() -> None:
    parsed = parse_session(make_item(session={"id": None}))

    assert parsed is not None
    assert parsed["hager_session_id"] == "HB-1784107597909"


def test_station_label_falls_back_to_wallbox_id() -> None:
    assert station_label(
        {"wallboxName": None, "wallboxId": "C4Pku"}
    ) == "ID: C4Pku"


def test_station_label_missing_raises() -> None:
    with pytest.raises(ValueError, match="Ladestation"):
        station_label({})


def test_extract_session_items_supports_all_formats() -> None:
    item = make_item()

    assert extract_session_items([item]) == [item]
    assert extract_session_items({"sessions": [item]}) == [item]
    assert extract_session_items({"content": [item]}) == [item]

    with pytest.raises(ValueError, match="Unbekanntes JSON-Format"):
        extract_session_items({"foo": []})


def test_import_json_reads_file_and_counts_running(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sessions.json"
    path.write_text(
        json.dumps(
            {
                "sessions": [
                    make_item(),
                    make_item(session={
                        "id": "running",
                        "end_date_time": None,
                    }),
                ]
            }
        ),
        encoding="utf-8",
    )

    sessions, running = import_json(path)

    assert len(sessions) == 1
    assert running == 1


def test_import_json_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{kein json", encoding="utf-8")

    with pytest.raises(ValueError, match="kein gültiges JSON"):
        import_json(path)


def test_import_json_reports_session_index(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps([make_item(session={"start_date_time": "gestern"})]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Session 1"):
        import_json(path)
