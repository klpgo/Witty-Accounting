import pytest

from app.services.password_policy import (
    PasswordPolicy,
    PasswordPolicyError,
    validate_password,
)


def test_accepts_password_matching_policy() -> None:
    validate_password(
        "Sicheres1!",
        PasswordPolicy(),
    )


@pytest.mark.parametrize(
    ("password", "expected_message"),
    [
        (
            "Kurz1!",
            "mindestens 8 Zeichen",
        ),
        (
            "sicheres1!",
            "einen Großbuchstaben",
        ),
        (
            "SICHERES1!",
            "einen Kleinbuchstaben",
        ),
        (
            "Sicheres!",
            "eine Zahl",
        ),
        (
            "Sicheres1",
            "ein Sonderzeichen",
        ),
    ],
)
def test_rejects_missing_requirement(
    password: str,
    expected_message: str,
) -> None:
    with pytest.raises(
        PasswordPolicyError,
        match=expected_message,
    ):
        validate_password(
            password,
            PasswordPolicy(),
        )


def test_respects_disabled_requirements() -> None:
    validate_password(
        "abcdefgh",
        PasswordPolicy(
            require_uppercase=False,
            require_digit=False,
            require_special=False,
        ),
    )


def test_whitespace_is_not_special_character() -> None:
    with pytest.raises(
        PasswordPolicyError,
        match="Sonderzeichen",
    ):
        validate_password(
            "Sicheres1 ",
            PasswordPolicy(),
        )
