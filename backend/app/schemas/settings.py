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

OptionalShortText = Annotated[
    str,
    Field(
        min_length=1,
        max_length=255,
    ),
]

OptionalAddress = Annotated[
    str,
    Field(
        min_length=1,
        max_length=500,
    ),
]

OptionalIdentifier = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
    ),
]

InvoiceIban = Annotated[
    str,
    Field(
        min_length=15,
        max_length=34,
        pattern=r"^[A-Z0-9]+$",
    ),
]

InvoiceBic = Annotated[
    str,
    Field(
        pattern=r"^[A-Z0-9]{8}([A-Z0-9]{3})?$",
    ),
]

InvoiceNumberPrefix = Annotated[
    str,
    Field(
        min_length=1,
        max_length=20,
        pattern=r"^[A-Z0-9]+$",
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
    invoice_issuer_name: str | None
    invoice_issuer_address: str | None
    invoice_tax_number: str | None
    invoice_vat_id: str | None
    invoice_bank_name: str | None
    invoice_iban: str | None
    invoice_bic: str | None
    invoice_number_prefix: str


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
    invoice_issuer_name: OptionalShortText | None = None
    invoice_issuer_address: OptionalAddress | None = None
    invoice_tax_number: OptionalIdentifier | None = None
    invoice_vat_id: OptionalIdentifier | None = None
    invoice_bank_name: OptionalShortText | None = None
    invoice_iban: InvoiceIban | None = None
    invoice_bic: InvoiceBic | None = None
    invoice_number_prefix: (
        InvoiceNumberPrefix | None
    ) = None

    @field_validator(
        "app_name",
        "monthly_base_fee_net",
        "monthly_base_fee_vat_rate",
        "invoice_payment_term_days",
        "invoice_number_prefix",
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

    @field_validator(
        "invoice_issuer_name",
        "invoice_issuer_address",
        "invoice_tax_number",
        "invoice_vat_id",
        "invoice_bank_name",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        normalized = value.strip()

        return normalized or None

    @field_validator(
        "invoice_iban",
        mode="before",
    )
    @classmethod
    def normalize_iban(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        normalized = "".join(
            value.split()
        ).upper()

        return normalized or None

    @field_validator(
        "invoice_bic",
        "invoice_number_prefix",
        mode="before",
    )
    @classmethod
    def normalize_uppercase_identifier(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        normalized = value.strip().upper()

        return normalized or None
