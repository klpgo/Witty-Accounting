from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


AppName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=255,
    ),
]

BaseFeeDecimal = Annotated[
    Decimal,
    Field(
        ge=Decimal("0"),
        max_digits=12,
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

PaymentTermDays = Annotated[
    int,
    Field(
        ge=0,
        le=3650,
    ),
]


class PublicSettingsResponse(BaseModel):
    app_name: str


class GlobalSettingsResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    app_name: str
    monthly_base_fee_net: Decimal
    monthly_base_fee_vat_rate: Decimal
    invoice_payment_term_days: int


class GlobalSettingsUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    app_name: AppName | None = None
    monthly_base_fee_net: BaseFeeDecimal | None = None
    monthly_base_fee_vat_rate: VatDecimal | None = None
    invoice_payment_term_days: (
        PaymentTermDays | None
    ) = None

    @field_validator(
        "app_name",
        "monthly_base_fee_net",
        "monthly_base_fee_vat_rate",
        "invoice_payment_term_days",
        mode="before",
    )
    @classmethod
    def reject_explicit_null(
        cls,
        value: object,
    ) -> object:
        if value is None:
            raise ValueError(
                "Der Einstellungswert darf nicht null sein."
            )

        return value

    @field_validator("app_name")
    @classmethod
    def normalize_app_name(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Der Anwendungsname darf nicht leer sein."
            )

        return normalized
