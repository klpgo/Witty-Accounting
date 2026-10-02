from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


PriceDecimal = Annotated[
    Decimal,
    Field(
        ge=Decimal("0"),
        max_digits=10,
        decimal_places=4,
    ),
]

VatDecimal = Annotated[
    Decimal,
    Field(
        ge=Decimal("0"),
        le=Decimal("100"),
        max_digits=5,
        decimal_places=2,
    ),
]


class EnergyPriceCreate(BaseModel):
    valid_from: datetime
    grid_price_net: PriceDecimal
    pv_price_net: PriceDecimal
    vat_rate: VatDecimal


class CurrentEnergyPriceUpdate(BaseModel):
    grid_price_net: PriceDecimal
    pv_price_net: PriceDecimal
    vat_rate: VatDecimal


class EnergyPriceRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    valid_from: datetime
    grid_price_net: Decimal
    pv_price_net: Decimal
    vat_rate: Decimal
    created_at: datetime
    updated_at: datetime


class EnergyPriceUpdate(BaseModel):
    """Ändern eines Tarifs: Gültigkeit ab einem Kalendertag (00:00 Uhr)."""
    valid_from: date
    grid_price_net: PriceDecimal
    pv_price_net: PriceDecimal
    vat_rate: VatDecimal


class EnergyPriceEditableFrom(BaseModel):
    # None, solange es keine Rechnung gibt (alle Zeitpunkte erlaubt)
    editable_from: datetime | None
