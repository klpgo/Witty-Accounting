"""EPC069-12 payment data for SEPA credit transfer QR codes (Girocode)."""

from decimal import Decimal
import re


# EPC version 002 permits an omitted BIC for payments within the EEA.
EEA_COUNTRY_CODES = frozenset(
    "AT BE BG HR CY CZ DK EE FI FR DE GR HU IS IE IT "
    "LV LI LT LU MT NL NO PL PT RO SK SI ES SE".split()
)
MAX_PAYLOAD_BYTES = 331


class GirocodeError(ValueError):
    """Raised when payment data cannot be encoded as a valid Girocode."""


def validate_text(
    value: str | None,
    *,
    label: str,
    max_length: int,
) -> str:
    normalized = (value or "").strip()
    if (
        not normalized
        or len(normalized) > max_length
        or not normalized.isprintable()
    ):
        raise GirocodeError(
            f"Girocode: {label} must be a single line with 1 to {max_length}"
            " characters."
        )
    return normalized


def validate_girocode_bank_details(
    *,
    beneficiary: str | None,
    iban: str | None,
    bic: str | None,
) -> tuple[str, str, str]:
    name = validate_text(
        beneficiary,
        label="The name of the invoice issuer",
        max_length=70,
    )
    normalized_iban = "".join((iban or "").split()).upper()
    if not re.fullmatch(
        r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}",
        normalized_iban,
    ):
        raise GirocodeError(
            "Girocode: A valid IBAN is required."
        )

    rearranged_iban = normalized_iban[4:] + normalized_iban[:4]
    checksum_digits = "".join(
        str(ord(character) - ord("A") + 10)
        if character.isalpha()
        else character
        for character in rearranged_iban
    )
    if int(checksum_digits) % 97 != 1:
        raise GirocodeError(
            "Girocode: The IBAN check digits are invalid."
        )

    normalized_bic = (bic or "").strip().upper()
    if normalized_bic and not re.fullmatch(
        r"[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?",
        normalized_bic,
    ):
        raise GirocodeError(
            "Girocode: The BIC must consist of 8 or 11 valid characters."
        )
    if (
        not normalized_bic
        and normalized_iban[:2] not in EEA_COUNTRY_CODES
    ):
        raise GirocodeError(
            "Girocode: A BIC is required for bank accounts outside the "
            "EEA."
        )

    return name, normalized_iban, normalized_bic


def build_girocode_payload(
    *,
    beneficiary: str | None,
    iban: str | None,
    bic: str | None,
    amount: Decimal,
    reference: str,
    currency: str = "EUR",
) -> str:
    name, normalized_iban, normalized_bic = (
        validate_girocode_bank_details(
            beneficiary=beneficiary,
            iban=iban,
            bic=bic,
        )
    )
    if currency != "EUR":
        raise GirocodeError(
            "Girocode: Only payments in EUR are supported."
        )
    if (
        not amount.is_finite()
        or not Decimal("0.01") <= amount <= Decimal("999999999.99")
        or amount != amount.quantize(Decimal("0.01"))
    ):
        raise GirocodeError(
            "Girocode: The amount must be between 0.01 and "
            "999,999,999.99 EUR and may have at most two decimal places."
        )
    remittance = validate_text(
        reference,
        label="The invoice number",
        max_length=140,
    )
    # UTF-8, EPC version 002, unstructured remittance information.
    # Empty fields keep their positions; the last field has no trailing LF.
    payload = "\n".join(
        [
            "BCD",
            "002",
            "1",
            "SCT",
            normalized_bic,
            name,
            normalized_iban,
            f"EUR{amount:.2f}",
            "",  # Purpose code
            "",  # Structured creditor reference
            remittance,
        ]
    )
    if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise GirocodeError(
            "Girocode: The payment data exceeds the permitted 331 UTF-8 "
            "bytes."
        )
    return payload
