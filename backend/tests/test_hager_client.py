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


def test_login_logs_steps_without_parameters(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO", logger="app.services.hager_client"):
        hager_client.login(
            "user@example.com",
            "richtig",
            transport=make_login_transport(),
        )

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "app.services.hager_client"
    ]

    assert any("Anmeldeseite" in message for message in messages)
    text = "\n".join(messages)
    # nur Host und Pfad: keine Query-Parameter, Tokens oder SAML-Daten
    assert "?" not in text
    assert "client_id" not in text
    assert SAML_VALUE not in text
    assert "ACCESS" not in text and "REAUTH" not in text


# --------------------------------------------------------------------------
# E-Mobility-Endpunkt: spaltenweise Antwort, neueste zuerst, Blättern
# --------------------------------------------------------------------------
from datetime import UTC, datetime


def charging_row(day: int, hour: int = 12) -> dict:
    return {
        "sessionID": f"S-{day:02d}-{hour:02d}",
        "wallboxID": "WB-A",
        "startAt": f"2026-09-{day:02d}T{hour:02d}:00:00.000Z",
    }


def as_columns(rows: list[dict]) -> dict:
    keys = rows[0].keys() if rows else ["sessionID", "wallboxID", "startAt"]
    return {key: [row[key] for row in rows] for key in keys}


def emobility_transport(
    pages: list[list[dict]],
    requested: list[dict],
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/e-mobility/322329007044/charging"
        assert request.headers["authorization"] == "Bearer ACCESS"
        params = dict(request.url.params)
        requested.append(params)
        page = int(params["offset"]) // int(params["limit"])
        rows = pages[page] if page < len(pages) else []
        return httpx.Response(200, json=as_columns(rows))

    return httpx.MockTransport(handler)


def full_pages(days: list[list[int]]) -> list[list[dict]]:
    return [[charging_row(day) for day in page] for page in days]


def test_columns_to_rows() -> None:
    assert hager_client.columns_to_rows(
        {"id": [1, 2], "startAt": ["a", "b"]}
    ) == [{"id": 1, "startAt": "a"}, {"id": 2, "startAt": "b"}]
    assert hager_client.columns_to_rows({}) == []

    with pytest.raises(hager_client.HagerApiError, match="unterschiedlich lang"):
        hager_client.columns_to_rows({"id": [1, 2], "startAt": ["a"]})


def test_fetch_requests_newest_first_and_stops_at_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hager_client, "PAGE_SIZE", 3)
    requested: list[dict] = []

    rows = hager_client.fetch_charging_sessions(
        "ACCESS",
        "322329007044",
        stop_before=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
        transport=emobility_transport(
            full_pages([[24, 23, 22], [21, 20, 19], [18, 17, 16]]),
            requested,
        ),
    )

    assert requested[0] == {"sort": "-startAt", "limit": "3", "offset": "0"}
    # Seite 2 reicht bis 19.09. zurück -> Seite 3 wird nicht geholt
    assert [r["offset"] for r in requested] == ["0", "3"]
    assert len(rows) == 6


def test_fetch_stops_at_last_partial_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hager_client, "PAGE_SIZE", 3)
    requested: list[dict] = []
    info: dict = {}

    rows = hager_client.fetch_charging_sessions(
        "ACCESS",
        "322329007044",
        info=info,
        transport=emobility_transport(
            full_pages([[24, 23, 22], [21, 20]]),
            requested,
        ),
    )

    assert len(rows) == 5
    assert info == {"pages": 2, "rows": 5}


def test_fetch_reads_all_pages_if_not_sorted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hager_client, "PAGE_SIZE", 3)
    requested: list[dict] = []

    hager_client.fetch_charging_sessions(
        "ACCESS",
        "322329007044",
        stop_before=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
        transport=emobility_transport(
            full_pages([[24, 19, 22], [21, 20, 18], [23, 17]]),
            requested,
        ),
    )

    assert [r["offset"] for r in requested] == ["0", "3", "6"]


def test_fetch_max_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hager_client, "PAGE_SIZE", 3)
    requested: list[dict] = []

    rows = hager_client.fetch_charging_sessions(
        "ACCESS",
        "322329007044",
        max_pages=1,
        transport=emobility_transport(
            full_pages([[24, 23, 22], [21, 20, 19]]),
            requested,
        ),
    )

    assert len(requested) == 1
    assert len(rows) == 3


@pytest.mark.parametrize(
    ("status_code", "error"),
    [
        (401, hager_client.HagerUnauthorizedError),
        (403, hager_client.HagerUnauthorizedError),
        (400, hager_client.HagerApiError),
    ],
)
def test_fetch_http_errors(status_code: int, error: type) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code))

    with pytest.raises(error, match=f"HTTP {status_code}"):
        hager_client.fetch_charging_sessions(
            "ACCESS",
            "322329007044",
            transport=transport,
        )


def test_fetch_wallbox_names() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/wallbox/wallboxes/1000143617/active")
        return httpx.Response(
            200,
            json=[
                {"wallboxId": "WB-A", "wallboxName": "WB2"},
                {"wallboxId": "WB-B", "wallboxName": " "},
                {"wallboxName": "ohne ID"},
            ],
        )

    assert hager_client.fetch_wallbox_names(
        "ACCESS",
        "1000143617",
        transport=httpx.MockTransport(handler),
    ) == {"WB-A": "WB2"}

