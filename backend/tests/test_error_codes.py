"""Fehlercodes: jede Meldung hat einen Code und Texte in beiden Sprachen."""
import re
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import (
    ERROR_MESSAGES,
    VALIDATION_CODES,
    error_content,
    match_error,
    validation_error_code,
)
from app.main import (
    http_exception_handler,
    validation_exception_handler,
)
from app.services.password_policy import (
    PasswordPolicy,
    PasswordPolicyError,
    validate_password,
)
from tests.error_message_scan import scan_error_messages

I18N_DIRECTORY = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n"
)

_PLACEHOLDER = re.compile(r"\{(\w*)\}")


def normalize(template: str) -> str:
    return _PLACEHOLDER.sub("{}", template)


def catalog_by_shape() -> dict[str, str]:
    return {
        normalize(template): code
        for code, template in ERROR_MESSAGES.items()
    }


def test_every_backend_message_has_a_code() -> None:
    shapes = catalog_by_shape()
    missing = [
        f"{path}: {template!r}"
        for template, path in scan_error_messages().items()
        if template not in shapes
    ]

    assert missing == [], (
        "Neue Fehlermeldungen brauchen einen Eintrag in "
        "app/errors.py (ERROR_MESSAGES):\n" + "\n".join(missing)
    )


def test_messages_are_matched_to_their_own_code() -> None:
    shapes = catalog_by_shape()

    for template in scan_error_messages():
        sample = template.replace("{}", "42")
        coded = match_error(sample)

        assert coded is not None, sample
        assert coded["code"] == shapes[template], sample


def test_more_specific_messages_win() -> None:
    assert match_error("Invoice draft 7 was not found.") == {
        "code": "autoBilling.draftNotFound",
        "params": {"id": "7"},
    }
    assert match_error("Invoice 7 was not found.") == {
        "code": "invoice.notFound",
        "params": {"id": "7"},
    }
    assert match_error("sessionID missing")["code"] == (
        "importJson.sessionIdKeyMissing"
    )
    assert match_error("startTime missing") == {
        "code": "importJson.fieldMissing",
        "params": {"field": "startTime"},
    }


def test_nested_causes_get_their_own_code() -> None:
    coded = match_error(
        "The XLSX file could not be imported: "
        "Error in XLSX row 3: Invalid duration format: 1h"
    )

    assert coded == {
        "code": "import.xlsxFailed",
        "params": {
            "error": {
                "code": "importXlsx.rowError",
                "params": {
                    "row": "3",
                    "error": {
                        "code": "importXlsx.invalidDuration",
                        "params": {"duration": "1h"},
                    },
                },
            },
        },
    }


def test_unknown_causes_stay_text() -> None:
    coded = match_error(
        "The JSON file could not be imported: something unexpected"
    )

    assert coded == {
        "code": "import.jsonFailed",
        "params": {"error": "something unexpected"},
    }


def test_unknown_message_has_no_code() -> None:
    assert match_error("Something completely different.") is None
    assert error_content("Something completely different.") == {
        "detail": "Something completely different.",
    }


def test_password_requirements_become_a_list() -> None:
    with pytest.raises(PasswordPolicyError) as raised:
        validate_password("abcdefgh", PasswordPolicy(min_length=12))

    assert match_error(str(raised.value)) == {
        "code": "password.requirements",
        "params": {
            "requirements": [
                {"code": "password.minLength", "params": {"count": "12"}},
                {"code": "password.uppercase", "params": {}},
                {"code": "password.digit", "params": {}},
                {"code": "password.special", "params": {}},
            ],
        },
    }

    with pytest.raises(PasswordPolicyError) as raised:
        validate_password("Abcdefgh1", PasswordPolicy())

    assert match_error(str(raised.value)) == {
        "code": "password.requirements",
        "params": {
            "requirements": [{"code": "password.special", "params": {}}],
        },
    }


def test_validation_errors_without_own_message() -> None:
    assert validation_error_code(
        {"type": "missing", "loc": ("body", "grace_days")}
    ) == {"code": "validation.missing", "params": {"field": "grace_days"}}

    assert validation_error_code(
        {
            "type": "less_than_equal",
            "loc": ("body", "review_days"),
            "ctx": {"le": 60},
        }
    ) == {
        "code": "validation.lessEqual",
        "params": {"field": "review_days", "max": "60"},
    }

    assert validation_error_code(
        {"type": "int_parsing", "loc": ("body", "cutoff_day")}
    ) == {"code": "validation.invalid", "params": {"field": "cutoff_day"}}


def test_stored_messages_carry_codes() -> None:
    from app.schemas.auto_billing import BillingRunSkipped

    entry = BillingRunSkipped(
        name="Kunde",
        reason="error",
        message="No address is stored for the invoice recipient.",
    )

    assert entry.model_dump()["message_code"] == {
        "code": "invoicing.recipientAddressMissing",
        "params": {},
    }
    assert BillingRunSkipped(
        name="Kunde",
        reason="existing_draft",
    ).model_dump()["message_code"] is None


def test_hager_summary_is_split_into_parts() -> None:
    assert match_error(
        "3 new, 0 skipped, 2 without price (fetched from 2026-10-01)"
    ) == {
        "code": "hagerImport.summary",
        "params": {
            "parts": [
                {"code": "hagerImport.new", "params": {"count": "3"}},
                {"code": "hagerImport.skipped", "params": {"count": "0"}},
                {"code": "hagerImport.withoutPrice", "params": {"count": "2"}},
            ],
            "scope": {
                "code": "hagerImport.scopeFrom",
                "params": {"date": "2026-10-01"},
            },
        },
    }


# --- Antworten der API -----------------------------------------------------


class _Payload(BaseModel):
    email: str
    days: int = Field(ge=1, le=60)

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("The email address is invalid.")

        return value


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )

    @app.get("/invoices/{invoice_id}")
    def get_invoice(invoice_id: int) -> None:
        raise HTTPException(
            status_code=404,
            detail=f"Invoice {invoice_id} was not found.",
            headers={"X-Test": "1"},
        )

    @app.get("/unknown")
    def unknown() -> None:
        raise HTTPException(status_code=409, detail="Not in the catalog.")

    @app.post("/payload")
    def payload(body: _Payload) -> None:
        return None

    return TestClient(app)


def test_http_errors_carry_code_and_params(client: TestClient) -> None:
    response = client.get("/invoices/12")

    assert response.status_code == 404
    assert response.headers["X-Test"] == "1"
    assert response.json() == {
        "detail": "Invoice 12 was not found.",
        "code": "invoice.notFound",
        "params": {"id": "12"},
    }


def test_unknown_http_errors_keep_detail_only(client: TestClient) -> None:
    response = client.get("/unknown")

    assert response.status_code == 409
    assert response.json() == {"detail": "Not in the catalog."}


def test_framework_errors_carry_code(client: TestClient) -> None:
    response = client.get("/missing-route")

    assert response.status_code == 404
    assert response.json()["code"] == "http.notFound"


def test_validation_errors_carry_codes(client: TestClient) -> None:
    response = client.post("/payload", json={"email": "x", "days": 99})

    assert response.status_code == 422

    detail = response.json()["detail"]

    assert [(item["code"], item["params"]) for item in detail] == [
        ("auth.emailInvalid", {}),
        ("validation.lessEqual", {"field": "days", "max": "60"}),
    ]
    # Pydantic-Felder bleiben erhalten
    assert detail[0]["msg"] == "Value error, The email address is invalid."
    assert detail[1]["loc"] == ["body", "days"]


# --- Texte in der Oberfläche -----------------------------------------------

# zusätzlich nur in der Oberfläche
FRONTEND_ONLY_CODES = {"requestFailed"}


def frontend_messages(language: str) -> dict[str, str]:
    path = I18N_DIRECTORY / f"{language}.ts"

    if not path.is_file():
        pytest.skip("Die Sprachdateien der Oberfläche fehlen.")

    pattern = re.compile(
        r"^\s*'apiError\.([\w.]+)':\s*'((?:[^'\\]|\\.)*)',\s*$",
        re.MULTILINE,
    )

    return {
        code: text
        for code, text in pattern.findall(path.read_text(encoding="utf-8"))
    }


@pytest.mark.parametrize("language", ["de", "en"])
def test_frontend_has_text_for_every_code(language: str) -> None:
    messages = frontend_messages(language)
    expected = set(ERROR_MESSAGES) | VALIDATION_CODES | FRONTEND_ONLY_CODES

    assert sorted(expected - set(messages)) == []
    assert sorted(set(messages) - expected) == []


@pytest.mark.parametrize("language", ["de", "en"])
def test_frontend_texts_use_only_known_params(language: str) -> None:
    messages = frontend_messages(language)

    for code, template in ERROR_MESSAGES.items():
        allowed = set(_PLACEHOLDER.findall(template))
        used = set(_PLACEHOLDER.findall(messages[code]))

        assert used <= allowed, (language, code, used - allowed)
