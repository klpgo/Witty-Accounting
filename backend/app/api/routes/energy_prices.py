from datetime import timedelta
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.models.energy_price import EnergyPrice
from app.schemas.energy_price import (
    CurrentEnergyPriceUpdate,
    EnergyPriceCreate,
    EnergyPriceEditableFrom,
    EnergyPriceRead,
    EnergyPriceUpdate,
)
from app.services.energy_price_rules import (
    EnergyPriceLockedError,
    day_start,
    editable_from,
    ensure_editable,
)

from app.schemas.pricing import PricingResult
from app.services.pricing import price_charging_sessions

from app.auth import require_admin

from app.utils.local_time import local_now

router = APIRouter(
    prefix="/energy-prices",
    tags=["energy-prices"],
)

def find_current_energy_price(
    db: Session,
) -> EnergyPrice | None:
    now = local_now()

    return db.scalar(
        select(EnergyPrice)
        .where(
            EnergyPrice.valid_from <= now
        )
        .order_by(
            EnergyPrice.valid_from.desc()
        )
        .limit(1)
    )


def energy_price_matches(
    energy_price: EnergyPrice,
    data: CurrentEnergyPriceUpdate,
) -> bool:
    return (
        energy_price.grid_price_net
        == data.grid_price_net
        and energy_price.pv_price_net
        == data.pv_price_net
        and energy_price.vat_rate
        == data.vat_rate
    )


@router.get(
    "",
    response_model=list[EnergyPriceRead],
)
def list_energy_prices(
    db: Session = Depends(get_db),
) -> list[EnergyPrice]:
    return list(
        db.scalars(
            select(EnergyPrice).order_by(
                EnergyPrice.valid_from.desc()
            )
        ).all()
    )

def check_editable(db: Session, *moments) -> None:
    try:
        ensure_editable(db, *moments)
    except EnergyPriceLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


def reprice_from(db: Session, start_from) -> None:
    """Nicht abgerechnete Ladevorgänge ab dem Zeitpunkt neu bepreisen."""
    price_charging_sessions(
        db=db,
        overwrite=True,
        start_from=start_from,
    )


@router.get(
    "/editable-from",
    response_model=EnergyPriceEditableFrom,
    dependencies=[Depends(require_admin)],
)
def read_editable_from(
    db: Session = Depends(get_db),
) -> EnergyPriceEditableFrom:
    """Frühester Zeitpunkt, ab dem Energiepreise gesetzt werden dürfen."""
    return EnergyPriceEditableFrom(editable_from=editable_from(db))


@router.get(
    "/current",
    response_model=EnergyPriceRead,
    dependencies=[Depends(require_admin)],
)
def read_current_energy_price(
    db: Session = Depends(get_db),
) -> EnergyPrice:
    energy_price = find_current_energy_price(db)

    if energy_price is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "There is no currently valid energy tariff yet."
            ),
        )

    return energy_price


@router.put(
    "/current",
    response_model=EnergyPriceRead,
    dependencies=[Depends(require_admin)],
)
def update_current_energy_price(
    data: CurrentEnergyPriceUpdate,
    db: Session = Depends(get_db),
) -> EnergyPrice:
    now = local_now()
    day_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    next_day_start = day_start + timedelta(days=1)

    current_price = find_current_energy_price(db)

    if (
        current_price is not None
        and energy_price_matches(
            current_price,
            data,
        )
    ):
        return current_price

    check_editable(db, day_start)

    today_prices = list(
        db.scalars(
            select(EnergyPrice)
            .where(
                EnergyPrice.valid_from >= day_start,
                EnergyPrice.valid_from
                < next_day_start,
            )
            .order_by(
                EnergyPrice.valid_from.desc()
            )
        ).all()
    )

    if len(today_prices) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Several energy tariffs exist for today."
            ),
        )

    if today_prices:
        today_price = today_prices[0]

        previous_price = db.scalar(
            select(EnergyPrice)
            .where(
                EnergyPrice.valid_from
                < day_start
            )
            .order_by(
                EnergyPrice.valid_from.desc()
            )
            .limit(1)
        )

        if (
            previous_price is not None
            and energy_price_matches(
                previous_price,
                data,
            )
        ):
            db.delete(today_price)
            energy_price = previous_price
        else:
            energy_price = today_price
            energy_price.valid_from = day_start
            energy_price.grid_price_net = (
                data.grid_price_net
            )
            energy_price.pv_price_net = (
                data.pv_price_net
            )
            energy_price.vat_rate = (
                data.vat_rate
            )
    else:
        energy_price = EnergyPrice(
            valid_from=day_start,
            grid_price_net=data.grid_price_net,
            pv_price_net=data.pv_price_net,
            vat_rate=data.vat_rate,
        )
        db.add(energy_price)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Today's energy tariff could not be saved because of a "
                "database conflict."
            ),
        ) from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(energy_price)
    reprice_from(db, day_start)

    return energy_price


@router.post(
    "",
    response_model=EnergyPriceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_energy_price(
    data: EnergyPriceCreate,
    db: Session = Depends(get_db),
) -> EnergyPrice:
    check_editable(db, data.valid_from)

    existing_price_id = db.scalar(
        select(EnergyPrice.id).where(
            EnergyPrice.valid_from
            == data.valid_from
        )
    )

    if existing_price_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A tariff already exists for this validity date."
            ),
        )

    energy_price = EnergyPrice(
        valid_from=data.valid_from,
        grid_price_net=data.grid_price_net,
        pv_price_net=data.pv_price_net,
        vat_rate=data.vat_rate,
    )

    db.add(energy_price)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The tariff could not be created because of a database "
                "conflict."
            ),
        ) from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(energy_price)
    reprice_from(db, energy_price.valid_from)

    return energy_price


@router.put(
    "/{price_id}",
    response_model=EnergyPriceRead,
    dependencies=[Depends(require_admin)],
)
def update_energy_price(
    price_id: int,
    data: EnergyPriceUpdate,
    db: Session = Depends(get_db),
) -> EnergyPrice:
    """
    Ändert einen Tarif (Gültigkeit ab einem Kalendertag und Preise).
    Alter und neuer Zeitpunkt dürfen nicht in einem abgerechneten Zeitraum
    liegen; danach werden die nicht abgerechneten Ladevorgänge ab dem
    früheren der beiden Zeitpunkte neu bepreist.
    """
    energy_price = db.get(EnergyPrice, price_id)

    if energy_price is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Energy tariff {price_id} was not found.",
        )

    new_valid_from = day_start(data.valid_from)
    check_editable(db, energy_price.valid_from, new_valid_from)

    other_price_id = db.scalar(
        select(EnergyPrice.id).where(
            EnergyPrice.valid_from == new_valid_from,
            EnergyPrice.id != price_id,
        )
    )

    if other_price_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A tariff already exists for this validity date.",
        )

    reprice_start = min(energy_price.valid_from, new_valid_from)
    energy_price.valid_from = new_valid_from
    energy_price.grid_price_net = data.grid_price_net
    energy_price.pv_price_net = data.pv_price_net
    energy_price.vat_rate = data.vat_rate

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The tariff could not be changed because of a database "
                "conflict."
            ),
        ) from exc

    db.refresh(energy_price)
    reprice_from(db, reprice_start)

    return energy_price


@router.post(
    "/reprice",
    response_model=PricingResult,
    dependencies=[Depends(require_admin)],
)
def reprice_charging_sessions(
    db: Session = Depends(get_db),
) -> PricingResult:
    result = price_charging_sessions(
        db=db,
        overwrite=True,
    )

    return PricingResult(**result)
