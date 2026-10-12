from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.global_settings import GlobalSettings


class PasswordPolicyError(ValueError):
    """Das neue Passwort erfüllt die Regeln nicht."""


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int = 8
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = True


def load_password_policy(
    db: Session,
) -> PasswordPolicy:
    global_settings = db.get(
        GlobalSettings,
        1,
    )

    if global_settings is None:
        return PasswordPolicy()

    return PasswordPolicy(
        min_length=(
            global_settings.password_min_length
        ),
        require_uppercase=(
            global_settings
            .password_require_uppercase
        ),
        require_lowercase=(
            global_settings
            .password_require_lowercase
        ),
        require_digit=(
            global_settings.password_require_digit
        ),
        require_special=(
            global_settings
            .password_require_special
        ),
    )


def validate_password(
    password: str,
    policy: PasswordPolicy,
) -> None:
    missing_requirements: list[str] = []

    if len(password) < policy.min_length:
        missing_requirements.append(
            f"at least {policy.min_length} characters"
        )

    if (
        policy.require_uppercase
        and not any(
            character.isupper()
            for character in password
        )
    ):
        missing_requirements.append(
            "an uppercase letter"
        )

    if (
        policy.require_lowercase
        and not any(
            character.islower()
            for character in password
        )
    ):
        missing_requirements.append(
            "a lowercase letter"
        )

    if (
        policy.require_digit
        and not any(
            character.isdigit()
            for character in password
        )
    ):
        missing_requirements.append(
            "a digit"
        )

    if (
        policy.require_special
        and not any(
            not character.isalnum()
            and not character.isspace()
            for character in password
        )
    ):
        missing_requirements.append(
            "a special character"
        )

    if not missing_requirements:
        return

    if len(missing_requirements) == 1:
        requirements_text = (
            missing_requirements[0]
        )
    else:
        requirements_text = (
            ", ".join(missing_requirements[:-1])
            + " and "
            + missing_requirements[-1]
        )

    raise PasswordPolicyError(
        f"The password must contain {requirements_text}."
    )
