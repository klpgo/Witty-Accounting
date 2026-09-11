from decimal import Decimal

import pytest

from app.services.invoice_girocode import (
    GirocodeError,
    build_girocode_payload,
)


def payment_data(**overrides: object) -> dict:
    return {
        "beneficiary": "Müller & Söhne GmbH",
        "iban": "DE89370400440532013000",
        "bic": "COBADEFFXXX",
        "amount": Decimal("123.45"),
        "reference": "RE-2026-000001",
        **overrides,
    }


def test_builds_epc_version_002_payload() -> None:
    payload = build_girocode_payload(**payment_data())

    assert payload == (
        "BCD\n002\n1\nSCT\nCOBADEFFXXX\n"
        "Müller & Söhne GmbH\nDE89370400440532013000\n"
        "EUR123.45\n\n\nRE-2026-000001"
    )
    assert not payload.endswith("\n")


def test_normalizes_bank_details_and_supports_empty_eea_bic() -> None:
    payload = build_girocode_payload(**payment_data(
        beneficiary="  Müller & Söhne GmbH  ",
        iban="de89 3704 0044 0532 0130 00",
        bic=None,
    ))

    assert payload.split("\n")[4:8] == [
        "",
        "Müller & Söhne GmbH",
        "DE89370400440532013000",
        "EUR123.45",
    ]


@pytest.mark.parametrize("amount", ["0.01", "999999999.99"])
def test_accepts_epc_amount_boundaries(amount: str) -> None:
    payload = build_girocode_payload(**payment_data(
        amount=Decimal(amount),
    ))

    assert payload.split("\n")[7] == f"EUR{amount}"


@pytest.mark.parametrize(
    "amount",
    ["0", "-0.01", "0.001", "1.001", "1000000000", "NaN", "Infinity"],
)
def test_rejects_invalid_amounts(amount: str) -> None:
    with pytest.raises(GirocodeError, match="Betrag"):
        build_girocode_payload(**payment_data(amount=Decimal(amount)))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"beneficiary": None}, "Name"),
        ({"beneficiary": "A" * 71}, "Name"),
        ({"beneficiary": "Name\nEUR999.99"}, "einzeilig"),
        ({"beneficiary": "Name\x00"}, "einzeilig"),
        ({"iban": None}, "IBAN"),
        ({"iban": "DE89370400440532013001"}, "Prüfziffer"),
        ({"iban": "123456789012345"}, "IBAN"),
        ({"bic": "12345678"}, "BIC"),
        ({"currency": "USD"}, "EUR"),
        ({"reference": ""}, "Rechnungsnummer"),
        ({"reference": "A" * 141}, "Rechnungsnummer"),
        ({"reference": "RE-1\r\nEUR999.99"}, "einzeilig"),
    ],
)
def test_rejects_invalid_payment_data(
    overrides: dict,
    message: str,
) -> None:
    with pytest.raises(GirocodeError, match=message):
        build_girocode_payload(**payment_data(**overrides))


def test_requires_bic_for_non_eea_account() -> None:
    data = payment_data(iban="CH9300762011623852957", bic=None)
    with pytest.raises(GirocodeError, match="EWR"):
        build_girocode_payload(**data)

    data["bic"] = "UBSWCHZH80A"
    assert "\nUBSWCHZH80A\n" in build_girocode_payload(**data)


def test_limits_payload_by_utf8_bytes_instead_of_characters() -> None:
    data = payment_data(beneficiary="Ä" * 70, reference="R")
    initial = build_girocode_payload(**data)
    reference_length = 332 - len(initial.encode("utf-8"))
    data["reference"] = "R" * reference_length
    payload = build_girocode_payload(**data)

    assert len(payload.encode("utf-8")) == 331
    assert len(payload) < 331

    data["reference"] += "R"
    with pytest.raises(GirocodeError, match="331 UTF-8-Bytes"):
        build_girocode_payload(**data)
