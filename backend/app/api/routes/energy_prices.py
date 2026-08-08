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
    EnergyPriceRead,
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
                "Es ist noch kein aktuell gültiger "
                "Energietarif vorhanden."
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
                "Für den heutigen Tag existieren "
                "mehrere Energietarife."
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
                "Der heutige Energietarif konnte "
                "wegen eines Datenbankkonflikts "
                "nicht gespeichert werden."
            ),
        ) from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(energy_price)

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
                "Für diesen Gültigkeitszeitpunkt "
                "existiert bereits ein Tarif."
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
                "Der Tarif konnte wegen eines "
                "Datenbankkonflikts nicht angelegt werden."
            ),
        ) from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(energy_price)

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
