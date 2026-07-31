from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.auth import require_admin
from app.config import settings
from app.database import Base
from app.main import app
from app.models.global_settings import GlobalSettings


@pytest.fixture
def database_session() -> Generator[
    Session,
    None,
    None,
]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    with Session(engine) as db:
        yield db

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(
    database_session: Session,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[
        Session,
        None,
        None,
    ]:
        yield database_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def admin_client(
    client: TestClient,
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[
        require_admin
    ] = lambda: None

    try:
        yield client
    finally:
        app.dependency_overrides.pop(
            require_admin,
            None,
        )


def add_global_settings(
    db: Session,
    *,
    app_name: str = "Witty-Accounting",
    monthly_base_fee_net: Decimal = Decimal(
        "0.0000"
    ),
    monthly_base_fee_vat_rate: Decimal = Decimal(
        "19.00"
    ),
    invoice_payment_term_days: int = 0,
    invoice_issuer_name: str | None = None,
    invoice_issuer_address: str | None = None,
    invoice_tax_number: str | None = None,
    invoice_vat_id: str | None = None,
    invoice_bank_name: str | None = None,
    invoice_iban: str | None = None,
    invoice_bic: str | None = None,
    invoice_number_prefix: str = "RE",
) -> GlobalSettings:
    global_settings = GlobalSettings(
        id=1,
        app_name=app_name,
        monthly_base_fee_net=monthly_base_fee_net,
        monthly_base_fee_vat_rate=(
            monthly_base_fee_vat_rate
        ),
        invoice_payment_term_days=(
            invoice_payment_term_days
        ),
        invoice_issuer_name=invoice_issuer_name,
        invoice_issuer_address=invoice_issuer_address,
        invoice_tax_number=invoice_tax_number,
        invoice_vat_id=invoice_vat_id,
        invoice_bank_name=invoice_bank_name,
        invoice_iban=invoice_iban,
        invoice_bic=invoice_bic,
        invoice_number_prefix=invoice_number_prefix,
    )

    db.add(global_settings)
    db.commit()
    db.refresh(global_settings)

    return global_settings


def test_reads_public_application_name(
    client: TestClient,
    database_session: Session,
) -> None:
    add_global_settings(
        database_session,
        app_name="Meine Wallbox-Abrechnung",
        monthly_base_fee_net=Decimal("10.0000"),
        invoice_payment_term_days=14,
    )

    response = client.get(
        "/settings/public"
    )

    assert response.status_code == 200
    assert response.json() == {
        "app_name": "Meine Wallbox-Abrechnung",
    }


def test_public_settings_uses_configuration_fallback(
    client: TestClient,
) -> None:
    response = client.get(
        "/settings/public"
    )

    assert response.status_code == 200
    assert response.json() == {
        "app_name": settings.app_name,
    }


def test_reads_admin_settings(
    admin_client: TestClient,
    database_session: Session,
) -> None:
    add_global_settings(
        database_session,
        app_name="Wallbox Verwaltung",
        monthly_base_fee_net=Decimal("12.5000"),
        monthly_base_fee_vat_rate=Decimal("19.00"),
        invoice_payment_term_days=14,
    )

    response = admin_client.get(
        "/settings"
    )

    assert response.status_code == 200
    assert response.json() == {
        "app_name": "Wallbox Verwaltung",
        "monthly_base_fee_net": "12.5000",
        "monthly_base_fee_vat_rate": "19.00",
        "invoice_payment_term_days": 14,
        "invoice_issuer_name": None,
        "invoice_issuer_address": None,
        "invoice_tax_number": None,
        "invoice_vat_id": None,
        "invoice_bank_name": None,
        "invoice_iban": None,
        "invoice_bic": None,
        "invoice_number_prefix": "RE",
    }


def test_updates_admin_settings(
    admin_client: TestClient,
    database_session: Session,
) -> None:
    global_settings = add_global_settings(
        database_session,
    )

    response = admin_client.patch(
        "/settings",
        json={
            "app_name": "  Neue Abrechnung  ",
            "monthly_base_fee_net": "9.9900",
            "monthly_base_fee_vat_rate": "7.00",
            "invoice_payment_term_days": 21,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "app_name": "Neue Abrechnung",
        "monthly_base_fee_net": "9.9900",
        "monthly_base_fee_vat_rate": "7.00",
        "invoice_payment_term_days": 21,
        "invoice_issuer_name": None,
        "invoice_issuer_address": None,
        "invoice_tax_number": None,
        "invoice_vat_id": None,
        "invoice_bank_name": None,
        "invoice_iban": None,
        "invoice_bic": None,
        "invoice_number_prefix": "RE",
    }

    database_session.refresh(global_settings)

    assert global_settings.id == 1
    assert global_settings.app_name == (
        "Neue Abrechnung"
    )
    assert global_settings.monthly_base_fee_net == (
        Decimal("9.9900")
    )
    assert (
        global_settings.monthly_base_fee_vat_rate
        == Decimal("7.00")
    )
    assert (
        global_settings.invoice_payment_term_days
        == 21
    )


def test_rejects_invalid_admin_settings(
    admin_client: TestClient,
    database_session: Session,
) -> None:
    add_global_settings(database_session)

    invalid_payloads = [
        {
            "monthly_base_fee_net": "-0.0001",
        },
        {
            "monthly_base_fee_vat_rate": "100.01",
        },
        {
            "invoice_payment_term_days": -1,
        },
        {
            "app_name": None,
        },
    ]

    for payload in invalid_payloads:
        response = admin_client.patch(
            "/settings",
            json=payload,
        )

        assert response.status_code == 422


def test_rejects_blank_application_name(
    admin_client: TestClient,
    database_session: Session,
) -> None:
    add_global_settings(database_session)

    response = admin_client.patch(
        "/settings",
        json={
            "app_name": "   ",
        },
    )

    assert response.status_code == 422


def test_admin_settings_require_authentication(
    client: TestClient,
    database_session: Session,
) -> None:
    add_global_settings(database_session)

    get_response = client.get(
        "/settings"
    )
    patch_response = client.patch(
        "/settings",
        json={
            "app_name": "Nicht erlaubt",
        },
    )

    assert get_response.status_code == 401
    assert patch_response.status_code == 401


def test_updates_invoice_business_settings(
    admin_client: TestClient,
    database_session: Session,
) -> None:
    global_settings = add_global_settings(
        database_session,
    )

    response = admin_client.patch(
        "/settings",
        json={
            "invoice_issuer_name": (
                "  Klaus Gottschalk  "
            ),
            "invoice_issuer_address": (
                "  Musterstraße 1\n"
                "12345 Musterstadt  "
            ),
            "invoice_tax_number": (
                "  123/456/78901  "
            ),
            "invoice_vat_id": (
                "  DE123456789  "
            ),
            "invoice_bank_name": (
                "  Musterbank  "
            ),
            "invoice_iban": (
                "de89 3704 0044 0532 0130 00"
            ),
            "invoice_bic": "cobadeffxxx",
            "invoice_number_prefix": " re ",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["invoice_issuer_name"] == (
        "Klaus Gottschalk"
    )
    assert body["invoice_issuer_address"] == (
        "Musterstraße 1\n12345 Musterstadt"
    )
    assert body["invoice_tax_number"] == (
        "123/456/78901"
    )
    assert body["invoice_vat_id"] == (
        "DE123456789"
    )
    assert body["invoice_bank_name"] == (
        "Musterbank"
    )
    assert body["invoice_iban"] == (
        "DE89370400440532013000"
    )
    assert body["invoice_bic"] == (
        "COBADEFFXXX"
    )
    assert body["invoice_number_prefix"] == "RE"

    database_session.refresh(global_settings)

    assert global_settings.invoice_iban == (
        "DE89370400440532013000"
    )
    assert global_settings.invoice_bic == (
        "COBADEFFXXX"
    )
    assert (
        global_settings.invoice_number_prefix
        == "RE"
    )


def test_clears_optional_invoice_business_settings(
    admin_client: TestClient,
    database_session: Session,
) -> None:
    global_settings = add_global_settings(
        database_session,
        invoice_issuer_name="Klaus Gottschalk",
        invoice_issuer_address=(
            "Musterstraße 1\n12345 Musterstadt"
        ),
        invoice_tax_number="123/456/78901",
        invoice_vat_id="DE123456789",
        invoice_bank_name="Musterbank",
        invoice_iban="DE89370400440532013000",
        invoice_bic="COBADEFFXXX",
    )

    response = admin_client.patch(
        "/settings",
        json={
            "invoice_issuer_name": None,
            "invoice_issuer_address": None,
            "invoice_tax_number": None,
            "invoice_vat_id": None,
            "invoice_bank_name": None,
            "invoice_iban": None,
            "invoice_bic": None,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["invoice_issuer_name"] is None
    assert body["invoice_issuer_address"] is None
    assert body["invoice_tax_number"] is None
    assert body["invoice_vat_id"] is None
    assert body["invoice_bank_name"] is None
    assert body["invoice_iban"] is None
    assert body["invoice_bic"] is None
    assert body["invoice_number_prefix"] == "RE"

    database_session.refresh(global_settings)

    assert global_settings.invoice_issuer_name is None
    assert global_settings.invoice_iban is None
    assert global_settings.invoice_bic is None


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        (
            "invoice_iban",
            "DE12",
        ),
        (
            "invoice_iban",
            "DE89-3704-0044",
        ),
        (
            "invoice_bic",
            "ABC",
        ),
        (
            "invoice_bic",
            "ABCDEFGHIJ",
        ),
        (
            "invoice_number_prefix",
            "RE-2026",
        ),
        (
            "invoice_number_prefix",
            None,
        ),
    ],
)
def test_rejects_invalid_invoice_business_settings(
    admin_client: TestClient,
    database_session: Session,
    field_name: str,
    value: object,
) -> None:
    add_global_settings(database_session)

    response = admin_client.patch(
        "/settings",
        json={
            field_name: value,
        },
    )

    assert response.status_code == 422
