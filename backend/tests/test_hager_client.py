from urllib.parse import parse_qs

import httpx
import pytest

from app.services import hager_client


SAML_VALUE = "PHNhbWxwOlJlc3BvbnNl" * 20
ASSERT_URL = (
    "https://e3dc.e3dc.com/auth-saml/service-providers/hager/assert"
)
KEYCLOAK_URL = (
    "https://auth.hagerenergy.com/realms/customer/broker/"
    "after-post-broker-login"
)
LOGIN_PAGE = (
    "https://login.hager.com/interaction/v2/uid/login?client_id=c"
)
LOGIN_FORM = (
    '<form method="post" action="/interaction/v2/uid/login?client_id=c">'
    '<input type="email" name="email">'
    '<input type="password" name="password">'
    "</form>"
)


def make_login_transport(password: str = "richtig") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        cookies = request.headers.get("cookie", "")

        if url.startswith(hager_client.E3DC_SAML_LOGIN):
            assert request.url.params["app"] == "hager"
            return httpx.Response(
                302,
                headers={"location": "https://auth.hagerenergy.com/realms/customer/protocol/saml?SAMLRequest=x"},
            )

        if "protocol/saml" in url:
            return httpx.Response(
                303,
                headers={
                    "location": LOGIN_PAGE,
                    "set-cookie": "AUTH_SESSION_ID=kc; Path=/realms/customer/",
                },
            )

        if url == LOGIN_PAGE and request.method == "GET":
            return httpx.Response(
                200,
                text=LOGIN_FORM,
                headers={"set-cookie": "_interaction=abc; Path=/"},
            )

        if url == LOGIN_PAGE and request.method == "POST":
            assert "_interaction=abc" in cookies
            form = parse_qs(request.content.decode())

            if form["password"] != [password] or form["email"] != ["user@example.com"]:
                return httpx.Response(200, text=LOGIN_FORM)

            return httpx.Response(302, headers={"location": KEYCLOAK_URL})

        if url == KEYCLOAK_URL:
            assert "AUTH_SESSION_ID=kc" in cookies
            return httpx.Response(
                200,
                text=(
                    '<body onload="document.forms[0].submit()">'
                    f'<form method="post" action="{ASSERT_URL}">'
                    f'<input type="hidden" name="SAMLResponse" value="{SAML_VALUE}"/>'
                    "</form></body>"
                ),
            )

        if url == ASSERT_URL:
            assert parse_qs(request.content.decode())["SAMLResponse"] == [SAML_VALUE]
            return httpx.Response(
                302,
                headers={
                    "location": (
                        "https://flow.hager.com/login?samlKey=hager"
                        "&token=ACCESS&reAuthToken=REAUTH&staticToken="
                    )
                },
            )

        raise AssertionError(f"Unerwarteter Aufruf: {request.method} {url}")

    return httpx.MockTransport(handler)


def test_login_follows_saml_chain_and_returns_tokens() -> None:
    tokens = hager_client.login(
        "user@example.com",
        "richtig",
        transport=make_login_transport(),
    )

    assert tokens.token == "ACCESS"
    assert tokens.reauth_token == "REAUTH"


def test_login_with_wrong_password_raises() -> None:
    with pytest.raises(hager_client.HagerLoginError, match="abgelehnt"):
        hager_client.login(
            "user@example.com",
            "falsch",
            transport=make_login_transport(),
        )


def test_login_requires_credentials() -> None:
    with pytest.raises(hager_client.HagerLoginError):
        hager_client.login("", "", transport=make_login_transport())


def test_refresh_returns_new_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == hager_client.E3DC_REAUTH
        assert b'name="reAuthToken"' in request.content
        return httpx.Response(200, json={"token": "T2", "reAuthToken": "R2"})

    tokens = hager_client.refresh("R1", transport=httpx.MockTransport(handler))

    assert (tokens.token, tokens.reauth_token) == ("T2", "R2")


def test_refresh_error_raises() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(401))

    with pytest.raises(hager_client.HagerLoginError):
        hager_client.refresh("R1", transport=transport)


def test_fetch_sessions_reads_all_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer ACCESS"
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={"content": [{"page": page}], "last": page == 1},
        )

    items = hager_client.fetch_sessions(
        "ACCESS",
        "1000143617",
        transport=httpx.MockTransport(handler),
    )

    assert items == [{"page": 0}, {"page": 1}]


def test_fetch_sessions_http_error_raises() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(401))

    with pytest.raises(hager_client.HagerApiError, match="HTTP 401"):
        hager_client.fetch_sessions("ACCESS", "1", transport=transport)


@pytest.mark.parametrize(
    "page",
    [
        f'<FORM METHOD="POST" ACTION="{ASSERT_URL}"><INPUT TYPE="HIDDEN" NAME="SAMLResponse" VALUE="{SAML_VALUE}"/></FORM>',
        f"<form action='{ASSERT_URL}'></form><input value='{SAML_VALUE}' type=hidden name='SAMLResponse'>",
        f'<script>post("{ASSERT_URL}", {{SAMLResponse: "{SAML_VALUE}"}})</script>',
    ],
)
def test_find_saml_post_variants(page: str) -> None:
    result = hager_client.find_saml_post(page, KEYCLOAK_URL)

    assert result is not None
    assert result[0] == ASSERT_URL
    assert result[1]["SAMLResponse"] == SAML_VALUE


def test_describe_page_hides_values() -> None:
    description = hager_client.describe_page(
        f"<title>Weiter</title><p>{SAML_VALUE}</p>"
        f'<script>x="SAMLResponse";y="{SAML_VALUE}"</script>'
    )

    assert "Weiter" in description
    assert SAML_VALUE[:16] not in description


def test_fetch_sessions_401_raises_unauthorized() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(401))

    with pytest.raises(hager_client.HagerUnauthorizedError):
        hager_client.fetch_sessions("ACCESS", "1", transport=transport)


# --------------------------------------------------------------------------
# Früher Abbruch am Cut-off
# --------------------------------------------------------------------------
from datetime import UTC, datetime


def session_at(day: int, hour: int = 12) -> dict:
    return {"session": {"start_date_time": f"2026-09-{day:02d}T{hour:02d}:00:00Z"}}


def paged_transport(pages: list[list[dict]], requested: list[int]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        requested.append(page)
        return httpx.Response(
            200,
            json={
                "content": pages[page],
                "last": page == len(pages) - 1,
                "totalElements": sum(len(p) for p in pages),
            },
        )

    return httpx.MockTransport(handler)


DESCENDING_PAGES = [
    [session_at(24), session_at(23), session_at(22)],
    [session_at(21), session_at(20), session_at(19)],
    [session_at(18), session_at(17), session_at(16)],
]


def test_fetch_stops_after_page_reaching_cutoff() -> None:
    requested: list[int] = []

    items = hager_client.fetch_sessions(
        "ACCESS",
        "1",
        stop_before=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
        transport=paged_transport(DESCENDING_PAGES, requested),
    )

    # Seite 1 reicht bis 19.09. zurück -> Seite 2 wird nicht mehr geholt
    assert requested == [0, 1]
    assert len(items) == 6


def test_fetch_without_cutoff_reads_all_pages() -> None:
    requested: list[int] = []

    items = hager_client.fetch_sessions(
        "ACCESS",
        "1",
        transport=paged_transport(DESCENDING_PAGES, requested),
    )

    assert requested == [0, 1, 2]
    assert len(items) == 9


def test_fetch_reads_all_pages_if_not_sorted() -> None:
    unsorted = [
        [session_at(24), session_at(19), session_at(22)],
        [session_at(21), session_at(20), session_at(18)],
        [session_at(23), session_at(17), session_at(16)],
    ]
    requested: list[int] = []

    hager_client.fetch_sessions(
        "ACCESS",
        "1",
        stop_before=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
        transport=paged_transport(unsorted, requested),
    )

    assert requested == [0, 1, 2]


def test_fetch_max_pages_and_info() -> None:
    requested: list[int] = []
    info: dict = {}

    items = hager_client.fetch_sessions(
        "ACCESS",
        "1",
        max_pages=1,
        info=info,
        transport=paged_transport(DESCENDING_PAGES, requested),
    )

    assert requested == [0]
    assert len(items) == 3
    assert info == {"pages": 1, "total_elements": 9}
