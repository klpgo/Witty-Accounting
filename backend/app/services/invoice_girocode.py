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
            f"Girocode: {label} muss einzeilig sein und "
            f"1 bis {max_length} Zeichen enthalten."
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
        label="Der Name des Rechnungsausstellers",
        max_length=70,
    )
    normalized_iban = "".join((iban or "").split()).upper()
    if not re.fullmatch(
        r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}",
        normalized_iban,
    ):
        raise GirocodeError(
            "Girocode: Eine gültige IBAN ist erforderlich."
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
            "Girocode: Die Prüfziffer der IBAN ist ungültig."
        )

    normalized_bic = (bic or "").strip().upper()
    if normalized_bic and not re.fullmatch(
        r"[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?",
        normalized_bic,
    ):
        raise GirocodeError(
            "Girocode: Die BIC muss aus 8 oder 11 "
            "gültigen Zeichen bestehen."
        )
    if (
        not normalized_bic
        and normalized_iban[:2] not in EEA_COUNTRY_CODES
    ):
        raise GirocodeError(
            "Girocode: Für Bankverbindungen außerhalb "
            "des EWR ist eine BIC erforderlich."
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
            "Girocode: Es werden nur Zahlungen in EUR unterstützt."
        )
    if (
        not amount.is_finite()
        or not Decimal("0.01") <= amount <= Decimal("999999999.99")
        or amount != amount.quantize(Decimal("0.01"))
    ):
        raise GirocodeError(
            "Girocode: Der Betrag muss zwischen 0,01 und "
            "999.999.999,99 EUR liegen und darf höchstens "
            "zwei Nachkommastellen haben."
        )
    remittance = validate_text(
        reference,
        label="Die Rechnungsnummer",
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
            "Girocode: Die Zahlungsdaten überschreiten "
            "die zulässigen 331 UTF-8-Bytes."
        )
    return payload
