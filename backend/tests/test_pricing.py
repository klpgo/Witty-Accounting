from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.charging_session import ChargingSession
from app.models.energy_price import EnergyPrice
from app.services.pricing import price_charging_sessions


def create_database_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
    )

    Base.metadata.create_all(engine)

    return Session(engine)


def create_charging_session(
    db: Session,
    *,
    start_time: datetime,
    energy_total_kwh: float,
    energy_pv_kwh: float,
    import_hash: str,
) -> ChargingSession:
    charging_session = ChargingSession(
        hager_session_id=None,
        station_id="WB2",
        start_time=start_time,
        end_time=start_time,
        rfid_card_id=None,
        energy_total_kwh=energy_total_kwh,
        energy_pv_kwh=energy_pv_kwh,
        cost_grid_net=None,
        cost_pv_net=None,
        vat_rate=None,
        invoiced=False,
        invoice_id=None,
        import_hash=import_hash,
        source="xlsx",
    )

    db.add(charging_session)
    db.commit()

    return charging_session


def test_price_charging_session() -> None:
    with create_database_session() as db:
        db.add(
            EnergyPrice(
                valid_from=datetime(
                    2026,
                    1,
                    1,
                ),
                grid_price_net=Decimal("0.3000"),
                pv_price_net=Decimal("0.1000"),
                vat_rate=Decimal("19.00"),
            )
        )

        create_charging_session(
            db,
            start_time=datetime(
                2026,
                6,
                17,
                10,
                0,
            ),
            energy_total_kwh=10.0,
            energy_pv_kwh=4.0,
            import_hash="a" * 64,
        )

        result = price_charging_sessions(db)

        assert result == {
            "read": 1,
            "priced": 1,
            "missing_price": 0,
            "invalid_energy": 0,
        }

        charging_session = db.scalar(
            select(ChargingSession)
        )

        assert charging_session is not None
        assert charging_session.cost_grid_net == Decimal(
            "1.8000"
        )
        assert charging_session.cost_pv_net == Decimal(
            "0.4000"
        )
        assert charging_session.vat_rate == Decimal(
            "19.00"
        )

def test_prices_only_selected_import_hashes() -> None:
    with create_database_session() as db:
        db.add(
            EnergyPrice(
                valid_from=datetime(2026, 1, 1),
                grid_price_net=Decimal("0.3000"),
                pv_price_net=Decimal("0.1000"),
                vat_rate=Decimal("19.00"),
            )
        )

        first_hash = "e" * 64
        second_hash = "f" * 64

        create_charging_session(
            db,
            start_time=datetime(2026, 6, 17, 10, 0),
            energy_total_kwh=1.0,
            energy_pv_kwh=0.0,
            import_hash=first_hash,
        )

        create_charging_session(
            db,
            start_time=datetime(2026, 6, 17, 11, 0),
            energy_total_kwh=1.0,
            energy_pv_kwh=0.0,
            import_hash=second_hash,
        )

        result = price_charging_sessions(
            db=db,
            import_hashes={first_hash},
        )

        assert result["read"] == 1
        assert result["priced"] == 1

        sessions = db.scalars(
            select(ChargingSession).order_by(
                ChargingSession.start_time
            )
        ).all()

        assert sessions[0].cost_grid_net == Decimal(
            "0.3000"
        )
        assert sessions[1].cost_grid_net is None


def test_uses_latest_valid_energy_price() -> None:
    with create_database_session() as db:
        db.add_all(
            [
                EnergyPrice(
                    valid_from=datetime(
                        2026,
                        1,
                        1,
                    ),
                    grid_price_net=Decimal("0.3000"),
                    pv_price_net=Decimal("0.1000"),
                    vat_rate=Decimal("19.00"),
                ),
                EnergyPrice(
                    valid_from=datetime(
                        2026,
                        6,
                        1,
                    ),
                    grid_price_net=Decimal("0.4000"),
                    pv_price_net=Decimal("0.2000"),
                    vat_rate=Decimal("19.00"),
                ),
            ]
        )

        create_charging_session(
            db,
            start_time=datetime(
                2026,
                6,
                17,
                10,
                0,
            ),
            energy_total_kwh=2.0,
            energy_pv_kwh=0.5,
            import_hash="b" * 64,
        )

        result = price_charging_sessions(db)

        assert result["priced"] == 1

        charging_session = db.scalar(
            select(ChargingSession)
        )

        assert charging_session is not None
        assert charging_session.cost_grid_net == Decimal(
            "0.6000"
        )
        assert charging_session.cost_pv_net == Decimal(
            "0.1000"
        )


def test_reports_missing_energy_price() -> None:
    with create_database_session() as db:
        create_charging_session(
            db,
            start_time=datetime(
                2026,
                6,
                17,
                10,
                0,
            ),
            energy_total_kwh=2.0,
            energy_pv_kwh=0.5,
            import_hash="c" * 64,
        )

        result = price_charging_sessions(db)

        assert result == {
            "read": 1,
            "priced": 0,
            "missing_price": 1,
            "invalid_energy": 0,
        }


def test_rejects_pv_energy_above_total_energy() -> None:
    with create_database_session() as db:
        db.add(
            EnergyPrice(
                valid_from=datetime(
                    2026,
                    1,
                    1,
                ),
                grid_price_net=Decimal("0.3000"),
                pv_price_net=Decimal("0.1000"),
                vat_rate=Decimal("19.00"),
            )
        )

        create_charging_session(
            db,
            start_time=datetime(
                2026,
                6,
                17,
                10,
                0,
            ),
            energy_total_kwh=1.0,
            energy_pv_kwh=2.0,
            import_hash="d" * 64,
        )

        result = price_charging_sessions(db)

        assert result["priced"] == 0
        assert result["invalid_energy"] == 1
