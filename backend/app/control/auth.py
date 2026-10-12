from dataclasses import dataclass
import base64
import hashlib
import hmac
import secrets
import time
from collections.abc import Callable

from pydantic import SecretStr

from app.control.i18n import tr


class ControlAuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ControlSession:
    csrf_token: str
    expires_at: int


class ControlAuthenticator:
    def __init__(
        self,
        *,
        password: SecretStr | None,
        session_secret: SecretStr | None,
        session_minutes: int = 30,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if password is None or not password.get_secret_value():
            raise ControlAuthenticationError(tr("auth.passwordMissing"))
        if session_secret is None or len(session_secret.get_secret_value()) < 32:
            raise ControlAuthenticationError(
                tr("auth.secretInvalid")
            )
        if session_minutes < 1:
            raise ControlAuthenticationError(
                tr("auth.minutesInvalid")
            )

        self._password = password.get_secret_value()
        self._secret = session_secret.get_secret_value().encode("utf-8")
        self._lifetime = session_minutes * 60
        self._clock = clock

    @property
    def max_age(self) -> int:
        return self._lifetime

    def check_password(self, candidate: str) -> bool:
        return hmac.compare_digest(
            candidate.encode("utf-8"),
            self._password.encode("utf-8"),
        )

    def create_session(self) -> tuple[str, ControlSession]:
        issued_at = int(self._clock())
        csrf_token = secrets.token_urlsafe(24)
        payload = f"{issued_at}.{csrf_token}"
        signature = hmac.new(
            self._secret,
            payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii")
        token = f"{payload}.{encoded_signature}"
        return token, ControlSession(
            csrf_token=csrf_token,
            expires_at=issued_at + self._lifetime,
        )

    def verify_session(self, token: str | None) -> ControlSession:
        if not token:
            raise ControlAuthenticationError(tr("auth.required"))

        try:
            issued_text, csrf_token, signature = token.split(".", 2)
            issued_at = int(issued_text)
        except (TypeError, ValueError) as exc:
            raise ControlAuthenticationError(tr("auth.sessionInvalid")) from exc

        payload = f"{issued_at}.{csrf_token}"
        expected = base64.urlsafe_b64encode(
            hmac.new(
                self._secret,
                payload.encode("ascii"),
                hashlib.sha256,
            ).digest()
        ).decode("ascii")

        now = int(self._clock())
        if not hmac.compare_digest(signature, expected):
            raise ControlAuthenticationError(tr("auth.sessionInvalid"))
        if issued_at > now + 30 or now - issued_at > self._lifetime:
            raise ControlAuthenticationError(tr("auth.sessionExpired"))

        return ControlSession(
            csrf_token=csrf_token,
            expires_at=issued_at + self._lifetime,
        )

    @staticmethod
    def verify_csrf(session: ControlSession, candidate: str | None) -> None:
        if not candidate or not hmac.compare_digest(
            candidate, session.csrf_token
        ):
            raise ControlAuthenticationError(tr("auth.securityCheckFailed"))
