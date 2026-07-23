from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.charging_session import ChargingSession
from app.models.energy_price import EnergyPrice


COST_QUANTIZER = Decimal("0.0001")


def to_decimal(value: float | Decimal) -> Decimal:
    """
    Wandelt Zahlen ohne zusätzliche Float-Rundungsfehler in Decimal um.
    """
    return Decimal(str(value))


def round_cost(value: Decimal) -> Decimal:
    """
    Rundet Geldbeträge kaufmännisch auf vier Nachkommastellen.
    """
    return value.quantize(
        COST_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


def find_energy_price(
    db: Session,
    session: ChargingSession,
) -> EnergyPrice | None:
    """
    Ermittelt den zum Startzeitpunkt gültigen Energiepreis.
    """
    return db.scalar(
        select(EnergyPrice)
        .where(
            EnergyPrice.valid_from
            <= session.start_time
        )
        .order_by(
            EnergyPrice.valid_from.desc()
        )
        .limit(1)
    )


def price_charging_sessions(
    db: Session,
    overwrite: bool = False,
    import_hashes: set[str] | None = None,
) -> dict[str, int]:
    """
    Berechnet die Nettokosten aller noch nicht vollständig
    bepreisten Ladevorgänge.

    Bei overwrite=True werden auch bereits bepreiste Sitzungen
    neu berechnet.
    """
    statement = select(ChargingSession).order_by(
        ChargingSession.start_time
    )
    if import_hashes is not None:
        if not import_hashes:
            return {
                "read": 0,
                "priced": 0,
                "missing_price": 0,
                "invalid_energy": 0,
            }

        statement = statement.where(
            ChargingSession.import_hash.in_(
                sorted(import_hashes)
            )
        )

    if not overwrite:
        statement = statement.where(
            or_(
                ChargingSession.cost_grid_net.is_(None),
                ChargingSession.cost_pv_net.is_(None),
                ChargingSession.vat_rate.is_(None),
            )
        )

    charging_sessions = db.scalars(
        statement
    ).all()

    priced = 0
    missing_price = 0
    invalid_energy = 0

    for charging_session in charging_sessions:
        energy_total = to_decimal(
            charging_session.energy_total_kwh
        )

        energy_pv = to_decimal(
            charging_session.energy_pv_kwh
        )

        if (
            energy_total < Decimal("0")
            or energy_pv < Decimal("0")
            or energy_pv > energy_total
        ):
            invalid_energy += 1
            continue

        energy_price = find_energy_price(
            db=db,
            session=charging_session,
        )

        if energy_price is None:
            missing_price += 1
            continue

        energy_grid = energy_total - energy_pv

        charging_session.cost_grid_net = round_cost(
            energy_grid
            * to_decimal(
                energy_price.grid_price_net
            )
        )

        charging_session.cost_pv_net = round_cost(
            energy_pv
            * to_decimal(
                energy_price.pv_price_net
            )
        )

        charging_session.vat_rate = (
            energy_price.vat_rate
        )

        priced += 1

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "read": len(charging_sessions),
        "priced": priced,
        "missing_price": missing_price,
        "invalid_energy": invalid_energy,
    }
