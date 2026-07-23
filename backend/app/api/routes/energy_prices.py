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
    EnergyPriceCreate,
    EnergyPriceRead,
)


router = APIRouter(
    prefix="/energy-prices",
    tags=["energy-prices"],
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


@router.post(
    "",
    response_model=EnergyPriceRead,
    status_code=status.HTTP_201_CREATED,
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
