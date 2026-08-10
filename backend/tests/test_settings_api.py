from collections.abc import Generator
import base64
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import (
    get_db,
    get_tenant_context,
)
from app.auth import require_admin
from app.config import settings
from app.database import Base
from app.main import app
from app.models.global_settings import GlobalSettings
from app.models.user import User
from app.tenancy.context import TenantContext

from app.services.invoice_email import (
    InvoiceEmailConfigurationError,
    InvoiceEmailDeliveryError,
    SmtpTestEmailResult,
)

from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.services.smtp_secret import (
    decrypt_smime_password,
    decrypt_smtp_password,
)

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
    app.dependency_overrides[
        get_tenant_context
    ] = lambda: TenantContext(
        id=42,
        slug="testmandant",
        name="Witty Testmandant",
        db_host="db",
        db_port=3306,
        db_name="testmandant",
        db_user="testmandant",
        db_password="not-used",
        archive_namespace="testmandant",
        canonical_hostname="test.example.de",
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def admin_client(
    client: TestClient,
) -> Generator[TestClient, None, None]:
    admin_user = User(
        email="admin@example.test",
        password_hash="not-used",
        first_name="Admin",
        last_name="User",
        is_admin=True,
        active=True,
    )

    app.dependency_overrides[
        require_admin
    ] = lambda: admin_user

    try:
        yield client
    finally:
        app.dependency_overrides.pop(
            require_admin,
            None,
        )


@pytest.fixture
def smtp_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    encryption_key = (
        Fernet.generate_key().decode("ascii")
    )

    monkeypatch.setattr(
        settings,
        "smtp_settings_encryption_key",
        SecretStr(encryption_key),
    )

    return encryption_key


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
    postal_delivery_fee_net: Decimal = Decimal(
        "0.0000"
    ),
    billing_start_date: date | None = None,
    invoice_payment_term_days: int = 0,
    invoice_issuer_name: str | None = None,
    invoice_issuer_address: str | None = None,
    invoice_tax_number: str | None = None,
    invoice_vat_id: str | None = None,
    invoice_bank_name: str | None = None,
    invoice_iban: str | None = None,
    invoice_bic: str | None = None,
    invoice_number_prefix: str = "RE",
    invoice_pdf_format: str = "standard",
    dashboard_note: str | None = None,
    frontend_base_url: str = (
        "http://localhost:5173"
    ),
    password_reset_token_expire_minutes: int = 60,
) -> GlobalSettings:
    global_settings = GlobalSettings(
        id=1,
        app_name=app_name,
        monthly_base_fee_net=monthly_base_fee_net,
        monthly_base_fee_vat_rate=(
            monthly_base_fee_vat_rate
        ),
        postal_delivery_fee_net=(
            postal_delivery_fee_net
        ),
        billing_start_date=billing_start_date,
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
        invoice_pdf_format=invoice_pdf_format,
        dashboard_note=dashboard_note,
        frontend_base_url=frontend_base_url,
        password_reset_token_expire_minutes=(
            password_reset_token_expire_minutes
        ),
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
        "/api/settings/public"
    )

    assert response.status_code == 200
    assert response.json() == {
        "app_name": "Meine Wallbox-Abrechnung",
        "tenant_name": "Witty Testmandant",
    }


def test_public_settings_uses_configuration_fallback(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/settings/public"
    )

    assert response.status_code == 200
    assert response.json() == {
        "app_name": settings.app_name,
        "tenant_name": "Witty Testmandant",
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
        "/api/settings"
    )

    assert response.status_code == 200
    assert response.json() == {
        "app_name": "Wallbox Verwaltung",
        "maintenance_mode": False,
        "dashboard_note": None,
        "monthly_base_fee_net": "12.5000",
        "monthly_base_fee_vat_rate": "19.00",
        "postal_delivery_fee_net": "0.0000",
        "billing_start_date": None,
        "invoice_payment_term_days": 14,
        "invoice_issuer_name": None,
        "invoice_issuer_address": None,
        "invoice_tax_number": None,
        "invoice_vat_id": None,
        "invoice_bank_name": None,
        "invoice_iban": None,
        "invoice_bic": None,
        "invoice_number_prefix": "RE",
        "invoice_pdf_format": "standard",
        "password_min_length": 8,
        "password_require_uppercase": True,
        "password_require_lowercase": True,
        "password_require_digit": True,
        "password_require_special": True,
        "frontend_base_url": (
            "http://localhost:5173"
        ),
        "password_reset_token_expire_minutes": 60,
    }


def test_updates_admin_settings(
    admin_client: TestClient,
    database_session: Session,
) -> None:
    global_settings = add_global_settings(
        database_session,
    )

    response = admin_client.patch(
        "/api/settings",
        json={
            "app_name": "  Neue Abrechnung  ",
            "monthly_base_fee_net": "9.9900",
            "monthly_base_fee_vat_rate": "7.00",
            "postal_delivery_fee_net": "1.6000",
            "billing_start_date": "2026-07-01",
            "invoice_payment_term_days": 21,
            "dashboard_note": "  Wartung am Freitag  ",
            "frontend_base_url": (
                " https://witty.example.test/app/ "
            ),
            "password_reset_token_expire_minutes": 90,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "app_name": "Neue Abrechnung",
        "maintenance_mode": False,
        "dashboard_note": "Wartung am Freitag",
        "monthly_base_fee_net": "9.9900",
        "monthly_base_fee_vat_rate": "7.00",
        "postal_delivery_fee_net": "1.6000",
        "billing_start_date": "2026-07-01",
        "invoice_payment_term_days": 21,
        "invoice_issuer_name": None,
        "invoice_issuer_address": None,
        "invoice_tax_number": None,
        "invoice_vat_id": None,
        "invoice_bank_name": None,
        "invoice_iban": None,
        "invoice_bic": None,
        "invoice_number_prefix": "RE",
        "invoice_pdf_format": "standard",
        "password_min_length": 8,
        "password_require_uppercase": True,
        "password_require_lowercase": True,
        "password_require_digit": True,
        "password_require_special": True,
        "frontend_base_url": (
            "https://witty.example.test/app"
        ),
        "password_reset_token_expire_minutes": 90,
    }

    database_session.refresh(global_settings)

    assert global_settings.id == 1
    assert global_settings.app_name == (
        "Neue Abrechnung"
    )
    assert global_settings.dashboard_note == (
        "Wartung am Freitag"
    )
    assert global_settings.monthly_base_fee_net == (
        Decimal("9.9900")
    )
    assert (
        global_settings.monthly_base_fee_vat_rate
        == Decimal("7.00")
    )
    assert (
        global_settings.postal_delivery_fee_net
        == Decimal("1.6000")
    )
    assert global_settings.billing_start_date == date(
        2026,
        7,
        1,
    )
    assert (
        global_settings.invoice_payment_term_days
        == 21
    )
    assert global_settings.frontend_base_url == (
        "https://witty.example.test/app"
    )
    assert (
        global_settings
        .password_reset_token_expire_minutes
        == 90
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
            "postal_delivery_fee_net": "-0.0001",
        },
        {
            "billing_start_date": "2026-02-30",
        },
        {
            "invoice_payment_term_days": -1,
        },
        {
            "app_name": None,
        },
        {
            "dashboard_note": "x" * 4001,
        },
        {
            "frontend_base_url": "ftp://example.test",
        },
        {
            "frontend_base_url": (
                "https://user@example.test"
            ),
        },
        {
            "password_reset_token_expire_minutes": 0,
        },
        {
            "password_reset_token_expire_minutes": 10081,
        },
    ]

    for payload in invalid_payloads:
        response = admin_client.patch(
            "/api/settings",
            json=payload,
        )

        assert response.status_code == 422


def test_clears_billing_start_date(
    admin_client: TestClient,
    database_session: Session,
) -> None:
    global_settings = add_global_settings(
        database_session,
        billing_start_date=date(2026, 7, 1),
    )

    response = admin_client.patch(
        "/api/settings",
        json={
            "billing_start_date": None,
        },
    )

    assert response.status_code == 200
    assert response.json()[
        "billing_start_date"
    ] is None

    database_session.refresh(global_settings)
    assert global_settings.billing_start_date is None


def test_rejects_blank_application_name(
    admin_client: TestClient,
    database_session: Session,
) -> None:
    add_global_settings(database_session)

    response = admin_client.patch(
        "/api/settings",
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
        "/api/settings"
    )
    patch_response = client.patch(
        "/api/settings",
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
        "/api/settings",
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
            "invoice_pdf_format": "pdfa-2b",
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
    assert body["invoice_pdf_format"] == "pdfa-2b"

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
    assert (
        global_settings.invoice_pdf_format
        == "pdfa-2b"
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
        "/api/settings",
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
        (
            "invoice_pdf_format",
            "pdfa-3b",
        ),
        (
            "invoice_pdf_format",
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
        "/api/settings",
        json={
            field_name: value,
        },
    )

    assert response.status_code == 422


def test_updates_smtp_settings_and_encrypts_password(
    admin_client: TestClient,
    database_session: Session,
    smtp_encryption_key: str,
) -> None:
    del smtp_encryption_key

    global_settings = add_global_settings(
        database_session,
    )

    response = admin_client.patch(
        "/api/settings/smtp",
        json={
            "smtp_use_database_settings": True,
            "mail_sending_enabled": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_timeout_seconds": "15.00",
            "smtp_starttls": True,
            "smtp_username": "mailer@example.com",
            "smtp_password": "very-secret-password",
            "mail_from_address": "billing@example.com",
            "mail_from_name": "Witty Accounting",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["smtp_use_database_settings"] is True
    assert body["smtp_host"] == "smtp.example.com"
    assert body["smtp_port"] == 587
    assert body["smtp_starttls"] is True
    assert body["smtp_username"] == (
        "mailer@example.com"
    )
    assert body["smtp_password_configured"] is True

    assert "smtp_password" not in body
    assert "smtp_password_encrypted" not in body
    assert "very-secret-password" not in (
        response.text
    )

    database_session.refresh(global_settings)

    encrypted_password = (
        global_settings.smtp_password_encrypted
    )

    assert encrypted_password is not None
    assert encrypted_password != (
        "very-secret-password"
    )
    assert decrypt_smtp_password(
        encrypted_password
    ) == "very-secret-password"


def test_keeps_existing_smtp_password(
    admin_client: TestClient,
    database_session: Session,
    smtp_encryption_key: str,
) -> None:
    del smtp_encryption_key

    global_settings = add_global_settings(
        database_session,
    )

    initial_response = admin_client.patch(
        "/api/settings/smtp",
        json={
            "smtp_use_database_settings": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_timeout_seconds": "15.00",
            "smtp_starttls": True,
            "smtp_password": "existing-password",
            "mail_from_address": "billing@example.com",
            "mail_from_name": "Witty Accounting",
        },
    )

    assert initial_response.status_code == 200

    database_session.refresh(global_settings)

    original_ciphertext = (
        global_settings.smtp_password_encrypted
    )

    response = admin_client.patch(
        "/api/settings/smtp",
        json={
            "smtp_host": "smtp2.example.com",
            "smtp_password": "",
        },
    )

    assert response.status_code == 200
    assert response.json()[
        "smtp_password_configured"
    ] is True

    database_session.refresh(global_settings)

    assert (
        global_settings.smtp_password_encrypted
        == original_ciphertext
    )



def test_clears_existing_smtp_password(
    admin_client: TestClient,
    database_session: Session,
    smtp_encryption_key: str,
) -> None:
    del smtp_encryption_key

    global_settings = add_global_settings(
        database_session,
    )

    initial_response = admin_client.patch(
        "/api/settings/smtp",
        json={
            "smtp_use_database_settings": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_timeout_seconds": "15.00",
            "smtp_starttls": True,
            "smtp_password": "existing-password",
            "mail_from_address": "billing@example.com",
            "mail_from_name": "Witty Accounting",
        },
    )

    assert initial_response.status_code == 200

    response = admin_client.patch(
        "/api/settings/smtp",
        json={
            "clear_smtp_password": True,
        },
    )

    assert response.status_code == 200
    assert response.json()[
        "smtp_password_configured"
    ] is False

    database_session.refresh(global_settings)

    assert (
        global_settings.smtp_password_encrypted
        is None
    )


def test_uploads_and_encrypts_smime_settings(
    admin_client: TestClient,
    database_session: Session,
    smtp_encryption_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del smtp_encryption_key

    global_settings = add_global_settings(
        database_session,
    )
    certificate_data = b"test-pkcs12-data"
    validation_calls: list[
        tuple[bytes, str, str]
    ] = []

    def fake_validate_smime_material(
        *,
        pkcs12_data: bytes,
        password: str,
        sender_email: str,
    ) -> None:
        validation_calls.append(
            (
                pkcs12_data,
                password,
                sender_email,
            )
        )

    monkeypatch.setattr(
        "app.api.routes.settings."
        "validate_smime_material",
        fake_validate_smime_material,
    )

    response = admin_client.patch(
        "/api/settings/smtp",
        json={
            "smtp_use_database_settings": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_timeout_seconds": "15.00",
            "smtp_starttls": True,
            "mail_from_address": (
                "billing@example.com"
            ),
            "mail_from_name": "Witty Accounting",
            "mail_smime_enabled": True,
            "smime_pkcs12_base64": (
                base64.b64encode(
                    certificate_data
                ).decode("ascii")
            ),
            "smime_pkcs12_filename": (
                "private/signing.p12"
            ),
            "smime_password": (
                "certificate-password"
            ),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["mail_smime_enabled"] is True
    assert body[
        "smime_certificate_configured"
    ] is True
    assert body[
        "smime_certificate_filename"
    ] == "signing.p12"
    assert body[
        "smime_certificate_source"
    ] == "upload"
    assert body[
        "smime_password_configured"
    ] is True
    assert "certificate-password" not in response.text
    assert "test-pkcs12-data" not in response.text

    assert validation_calls == [
        (
            certificate_data,
            "certificate-password",
            "billing@example.com",
        )
    ]

    database_session.refresh(global_settings)

    assert (
        global_settings.mail_smime_pkcs12_data
        == certificate_data
    )
    assert (
        global_settings.mail_smime_pkcs12_filename
        == "signing.p12"
    )

    encrypted_password = (
        global_settings
        .mail_smime_pkcs12_password_encrypted
    )

    assert encrypted_password is not None
    assert decrypt_smime_password(
        encrypted_password
    ) == "certificate-password"


def test_rejects_smime_upload_without_password(
    admin_client: TestClient,
    database_session: Session,
) -> None:
    add_global_settings(database_session)

    response = admin_client.patch(
        "/api/settings/smtp",
        json={
            "smime_pkcs12_base64": (
                base64.b64encode(
                    b"test-pkcs12-data"
                ).decode("ascii")
            ),
            "smime_pkcs12_filename": "signing.p12",
        },
    )

    assert response.status_code == 422
    assert "Passwort" in response.json()["detail"]


def test_sends_smime_test_email_to_admin(
    admin_client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_recipient: list[str] = []

    def fake_send_smime_test_email(
        db: Session,
        *,
        recipient_email: str,
    ) -> SmtpTestEmailResult:
        assert db is database_session
        captured_recipient.append(recipient_email)

        return SmtpTestEmailResult(
            recipient_email=recipient_email,
            subject="Witty-Accounting S/MIME-Test",
        )

    monkeypatch.setattr(
        "app.api.routes.settings."
        "send_smime_test_email",
        fake_send_smime_test_email,
    )

    response = admin_client.post(
        "/api/settings/smtp/smime/test"
    )

    assert response.status_code == 200
    assert response.json() == {
        "recipient_email": "admin@example.test",
        "subject": "Witty-Accounting S/MIME-Test",
    }
    assert captured_recipient == [
        "admin@example.test"
    ]


def test_sends_smtp_test_email_to_admin(
    admin_client: TestClient,
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_recipient: list[str] = []

    def fake_send_smtp_test_email(
        db: Session,
        *,
        recipient_email: str,
    ) -> SmtpTestEmailResult:
        assert db is database_session

        captured_recipient.append(
            recipient_email
        )

        return SmtpTestEmailResult(
            recipient_email=recipient_email,
            subject=(
                "Witty-Accounting Mailserver-Test"
            ),
        )

    monkeypatch.setattr(
        "app.api.routes.settings."
        "send_smtp_test_email",
        fake_send_smtp_test_email,
    )

    response = admin_client.post(
        "/api/settings/smtp/test"
    )

    assert response.status_code == 200
    assert response.json() == {
        "recipient_email": "admin@example.test",
        "subject": (
            "Witty-Accounting Mailserver-Test"
        ),
    }
    assert captured_recipient == [
        "admin@example.test"
    ]


def test_smtp_test_reports_configuration_error(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_smtp_test(
        db: Session,
        *,
        recipient_email: str,
    ) -> SmtpTestEmailResult:
        raise InvoiceEmailConfigurationError(
            "Der E-Mail-Versand ist deaktiviert."
        )

    monkeypatch.setattr(
        "app.api.routes.settings."
        "send_smtp_test_email",
        fail_smtp_test,
    )

    response = admin_client.post(
        "/api/settings/smtp/test"
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Der E-Mail-Versand ist deaktiviert."
        ),
    }


def test_smtp_test_reports_delivery_error(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_smtp_test(
        db: Session,
        *,
        recipient_email: str,
    ) -> SmtpTestEmailResult:
        raise InvoiceEmailDeliveryError(
            "Die SMTP-Testnachricht konnte "
            "nicht versendet werden."
        )

    monkeypatch.setattr(
        "app.api.routes.settings."
        "send_smtp_test_email",
        fail_smtp_test,
    )

    response = admin_client.post(
        "/api/settings/smtp/test"
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": (
            "Die SMTP-Testnachricht konnte "
            "nicht versendet werden."
        ),
    }


def test_updates_maintenance_mode(
    admin_client: TestClient,
    database_session: Session,
) -> None:
    global_settings = add_global_settings(
        database_session,
    )

    response = admin_client.patch(
        "/api/settings",
        json={
            "maintenance_mode": True,
        },
    )

    assert response.status_code == 200
    assert response.json()[
        "maintenance_mode"
    ] is True

    database_session.refresh(global_settings)

    assert global_settings.maintenance_mode is True
