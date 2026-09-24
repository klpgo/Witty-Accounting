import httpx
import jwt
import pytest

from app.services.hager_client import HagerLoginError, HagerTokens
from app.services.hager_token_cache import (
    ACCESS_MARGIN_SECONDS,
    REAUTH_MARGIN_SECONDS,
    HagerTokenCache,
    token_expiry,
)


START = 1_800_000_000.0
ACCESS_LIFETIME = 600          # 10 Minuten
REAUTH_LIFETIME = 30 * 86400   # 30 Tage


def make_token(exp: float | None, label: str) -> str:
    payload = {"label": label}
    if exp is not None:
        payload["exp"] = int(exp)
    return jwt.encode(payload, "test-key-mit-ausreichender-laenge-32b", algorithm="HS256")


class FakeHager:
    def __init__(self, clock: "Clock") -> None:
        self.clock = clock
        self.logins = 0
        self.refreshes = 0
        self.fail_refresh = False
        self.omit_exp = False

    def _tokens(self, label: str) -> HagerTokens:
        now = self.clock()
        return HagerTokens(
            token=make_token(None if self.omit_exp else now + ACCESS_LIFETIME, label),
            reauth_token=make_token(None if self.omit_exp else now + REAUTH_LIFETIME, label),
        )

    def login(self, username: str, password: str, log=None) -> HagerTokens:
        self.logins += 1
        return self._tokens(f"login-{self.logins}")

    def refresh(self, reauth_token: str) -> HagerTokens:
        self.refreshes += 1
        if self.fail_refresh:
            raise HagerLoginError("abgelehnt")
        return self._tokens(f"refresh-{self.refreshes}")


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def cache_setup() -> tuple[HagerTokenCache, FakeHager, Clock]:
    clock = Clock()
    hager = FakeHager(clock)
    cache = HagerTokenCache(clock=clock, login=hager.login, refresh=hager.refresh)
    return cache, hager, clock


def test_token_expiry_reads_exp_without_signature_check() -> None:
    assert token_expiry(make_token(START + 10, "x")) == START + 10
    assert token_expiry(make_token(None, "x")) is None
    assert token_expiry("kein-jwt") is None


def test_first_call_logs_in_and_second_reuses(cache_setup) -> None:
    cache, hager, clock = cache_setup

    first = cache.get_access_token("user@example.com", "pw")
    clock.now += 60
    second = cache.get_access_token("User@Example.com ", "pw")

    assert first == second
    assert (hager.logins, hager.refreshes) == (1, 0)


def test_refreshes_shortly_before_access_token_expires(cache_setup) -> None:
    cache, hager, clock = cache_setup

    first = cache.get_access_token("user@example.com", "pw")
    clock.now += ACCESS_LIFETIME - ACCESS_MARGIN_SECONDS + 1
    second = cache.get_access_token("user@example.com", "pw")

    assert second != first
    assert (hager.logins, hager.refreshes) == (1, 1)


def test_still_reused_just_before_margin(cache_setup) -> None:
    cache, hager, clock = cache_setup

    cache.get_access_token("user@example.com", "pw")
    clock.now += ACCESS_LIFETIME - ACCESS_MARGIN_SECONDS - 1
    cache.get_access_token("user@example.com", "pw")

    assert (hager.logins, hager.refreshes) == (1, 0)


def test_refresh_keeps_session_alive_with_new_reauth_token(cache_setup) -> None:
    cache, hager, clock = cache_setup

    cache.get_access_token("user@example.com", "pw")

    # 60 Tage lang täglich abrufen: das Re-Auth-Token wird jedes Mal
    # verlängert, eine erneute Anmeldung ist nicht nötig
    for _ in range(60):
        clock.now += 86400
        cache.get_access_token("user@example.com", "pw")

    assert hager.logins == 1
    assert hager.refreshes == 60


def test_login_when_reauth_token_nearly_expired(cache_setup) -> None:
    cache, hager, clock = cache_setup

    cache.get_access_token("user@example.com", "pw")
    clock.now += REAUTH_LIFETIME - REAUTH_MARGIN_SECONDS + 1
    cache.get_access_token("user@example.com", "pw")

    assert (hager.logins, hager.refreshes) == (2, 0)


def test_login_when_refresh_fails(cache_setup) -> None:
    cache, hager, clock = cache_setup

    cache.get_access_token("user@example.com", "pw")
    hager.fail_refresh = True
    clock.now += ACCESS_LIFETIME
    cache.get_access_token("user@example.com", "pw")

    assert (hager.logins, hager.refreshes) == (2, 1)


def test_login_when_refresh_has_network_error(cache_setup) -> None:
    cache, hager, clock = cache_setup

    def broken_refresh(token: str) -> HagerTokens:
        raise httpx.ConnectTimeout("timeout")

    cache._refresh = broken_refresh
    cache.get_access_token("user@example.com", "pw")
    clock.now += ACCESS_LIFETIME
    cache.get_access_token("user@example.com", "pw")

    assert hager.logins == 2


def test_force_login_ignores_cache(cache_setup) -> None:
    cache, hager, _clock = cache_setup

    cache.get_access_token("user@example.com", "pw")
    cache.get_access_token("user@example.com", "pw", force_login=True)

    assert hager.logins == 2


def test_changed_password_logs_in_again(cache_setup) -> None:
    cache, hager, _clock = cache_setup

    cache.get_access_token("user@example.com", "alt")
    cache.get_access_token("user@example.com", "neu")

    assert hager.logins == 2


def test_invalidate_user(cache_setup) -> None:
    cache, hager, _clock = cache_setup

    cache.get_access_token("user@example.com", "pw")
    cache.invalidate("USER@example.com")
    cache.get_access_token("user@example.com", "pw")

    assert hager.logins == 2


def test_tokens_without_expiry_are_not_reused(cache_setup) -> None:
    cache, hager, _clock = cache_setup
    hager.omit_exp = True

    cache.get_access_token("user@example.com", "pw")
    cache.get_access_token("user@example.com", "pw")

    assert (hager.logins, hager.refreshes) == (2, 0)


def test_fresh_cache_is_empty() -> None:
    clock = Clock()
    hager = FakeHager(clock)

    HagerTokenCache(clock=clock, login=hager.login, refresh=hager.refresh) \
        .get_access_token("user@example.com", "pw")
    # neuer Cache = Neustart des Containers
    HagerTokenCache(clock=clock, login=hager.login, refresh=hager.refresh) \
        .get_access_token("user@example.com", "pw")

    assert hager.logins == 2
