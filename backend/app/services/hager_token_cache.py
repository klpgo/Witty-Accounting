"""
Zwischenspeicher für Hager-Tokens – ausschließlich im Arbeitsspeicher.

Tokens werden weder in der Datenbank noch auf der Platte abgelegt. Nach
einem Neustart des Containers ist der Cache leer, und beim nächsten Abruf
wird neu angemeldet.

Reihenfolge beim Anfordern eines Zugriffstokens:
    1. Zugriffstoken aus dem Cache, solange es noch länger als
       ACCESS_MARGIN_SECONDS gültig ist
    2. sonst Erneuerung über das Re-Auth-Token (liefert auch ein neues
       Re-Auth-Token), solange dieses noch länger als
       REAUTH_MARGIN_SECONDS gültig ist
    3. sonst – oder wenn die Erneuerung scheitert – vollständige
       Anmeldung mit E-Mail und Passwort
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import jwt

from app.services import hager_client
from app.services.hager_client import HagerLoginError, HagerTokens


logger = logging.getLogger(__name__)

# Zugriffstoken gilt 10 Minuten -> 1 Minute vor Ablauf erneuern
ACCESS_MARGIN_SECONDS = 60
# Re-Auth-Token gilt 30 Tage -> 1 Stunde vor Ablauf neu anmelden
REAUTH_MARGIN_SECONDS = 3600


def token_expiry(token: str) -> float | None:
    """Ablaufzeitpunkt (Unix-Zeit) aus dem JWT, ohne Signaturprüfung.
    Die Tokens werden nur weitergereicht, nicht als Vertrauensbasis
    genutzt."""
    try:
        payload = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
            },
        )
    except jwt.PyJWTError:
        return None

    exp = payload.get("exp")

    return float(exp) if isinstance(exp, (int, float)) else None


@dataclass
class CachedTokens:
    tokens: HagerTokens
    access_expires_at: float
    reauth_expires_at: float


CacheKey = tuple[str, str]


class HagerTokenCache:
    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        login: Callable[..., HagerTokens] | None = None,
        refresh: Callable[[str], HagerTokens] | None = None,
    ) -> None:
        self._clock = clock
        # zur Laufzeit auflösen, damit Tests hager_client ersetzen können
        self._login = login or (lambda *a, **k: hager_client.login(*a, **k))
        self._refresh = refresh or (lambda token: hager_client.refresh(token))
        self._entries: dict[CacheKey, CachedTokens] = {}
        self._key_locks: dict[CacheKey, threading.Lock] = {}
        self._guard = threading.Lock()

    @staticmethod
    def _key(username: str, password: str) -> CacheKey:
        # Passwort nur als Hash im Schlüssel: nach einer Passwortänderung
        # wird automatisch neu angemeldet
        return (
            username.strip().lower(),
            hashlib.sha256(password.encode("utf-8")).hexdigest(),
        )

    def _lock_for(self, key: CacheKey) -> threading.Lock:
        with self._guard:
            return self._key_locks.setdefault(key, threading.Lock())

    def _store(self, key: CacheKey, tokens: HagerTokens) -> None:
        now = self._clock()
        # Ohne lesbares Ablaufdatum wird das Token nicht wiederverwendet
        self._entries[key] = CachedTokens(
            tokens=tokens,
            access_expires_at=token_expiry(tokens.token) or now,
            reauth_expires_at=token_expiry(tokens.reauth_token) or now,
        )

    def get_access_token(
        self,
        username: str,
        password: str,
        force_login: bool = False,
    ) -> str:
        key = self._key(username, password)

        # Pro Zugang nur eine Anmeldung gleichzeitig
        with self._lock_for(key):
            now = self._clock()
            entry = None if force_login else self._entries.get(key)

            if entry and entry.access_expires_at - now > ACCESS_MARGIN_SECONDS:
                logger.info(
                    "Hager: Zugriffstoken aus dem Cache verwendet "
                    "(noch %.0f s gültig)",
                    entry.access_expires_at - now,
                )
                return entry.tokens.token

            tokens: HagerTokens | None = None

            if entry and entry.reauth_expires_at - now > REAUTH_MARGIN_SECONDS:
                try:
                    tokens = self._refresh(entry.tokens.reauth_token)
                    logger.info("Hager: Token über Re-Auth erneuert")
                except (HagerLoginError, httpx.HTTPError) as exc:
                    logger.warning(
                        "Hager: Token-Erneuerung fehlgeschlagen (%s), "
                        "melde neu an",
                        type(exc).__name__,
                    )

            if tokens is None:
                tokens = self._login(username, password)
                logger.info("Hager: neu angemeldet")

            self._store(key, tokens)

            return tokens.token

    def invalidate(self, username: str | None = None) -> None:
        """Verwirft Tokens eines Benutzers (oder alle)."""
        with self._guard:
            if username is None:
                self._entries.clear()
                return

            normalized = username.strip().lower()

            for key in [k for k in self._entries if k[0] == normalized]:
                del self._entries[key]


# Prozessweiter Cache (uvicorn läuft mit einem Worker)
token_cache = HagerTokenCache()
