"""
Hager-flow-Client: Anmeldung und Abruf der Ladesessions ohne Browser.

Ablauf (aus der Aufzeichnung von `discover-login` abgeleitet):
  1. E3/DC-SAML-Login  -> Keycloak (auth.hagerenergy.com) -> login.hager.com
  2. Formular auf login.hager.com mit den Feldern email/password absenden
  3. Weiterleitungen zurück zu Keycloak; dessen Seite enthält ein Formular,
     das die SAMLResponse an E3/DC schickt
  4. E3/DC antwortet mit einer Weiterleitung auf flow.hager.com/login,
     deren URL das Zugriffstoken (ca. 10 min) und das Re-Auth-Token
     (30 Tage) enthält
  5. re-auth liefert jederzeit ein neues Token-Paar

Das Modul gibt niemals Passwörter oder Tokens aus.
"""
from __future__ import annotations

import html as html_lib
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx

DEFAULT_SAML_APP = "hager"
E3DC_SAML_LOGIN = "https://e3dc.e3dc.com/auth-saml/service-providers/hager/login"
E3DC_REAUTH = "https://e3dc.e3dc.com/auth-saml/re-auth"
BRIDGE_API = "https://hager-bridge.production.production.eks.e3dc.com/hager-bridge/v1"
FLOW_ORIGIN = "https://flow.hager.com"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
TIMEOUT = httpx.Timeout(30.0)

logger = logging.getLogger(__name__)
PAGE_SIZE = 100
MAX_PAGES = 500


class HagerLoginError(RuntimeError):
    """Anmeldung fehlgeschlagen (falsche Zugangsdaten oder geänderter Ablauf)."""


class HagerApiError(RuntimeError):
    """Fehler beim Abruf der Daten."""


class HagerUnauthorizedError(HagerApiError):
    """Zugriffstoken abgelehnt (abgelaufen oder ungültig)."""


@dataclass
class HagerTokens:
    token: str          # Zugriffstoken für die API (kurzlebig)
    reauth_token: str   # zum Erneuern (30 Tage)


# --------------------------------------------------------------------------
# HTML-Formulare auslesen (ohne zusätzliche Bibliothek)
# --------------------------------------------------------------------------
class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict] = []
        self._current: dict | None = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "form":
            self._current = {
                "action": attributes.get("action") or "",
                "method": (attributes.get("method") or "get").upper(),
                "fields": {},
            }
            self.forms.append(self._current)
        elif tag in ("input", "textarea") and self._current is not None:
            name = attributes.get("name")
            if name:
                self._current["fields"][name] = attributes.get("value") or ""

    def handle_endtag(self, tag):
        if tag == "form":
            self._current = None


def parse_forms(html: str) -> list[dict]:
    parser = _FormParser()
    parser.feed(html)
    return parser.forms


def _describe(url: str | httpx.URL) -> str:
    parts = urlsplit(str(url))
    return f"{parts.netloc}{parts.path}"


# --------------------------------------------------------------------------
# SAML-Antwort finden – Formular, rohes HTML oder JavaScript
# --------------------------------------------------------------------------
_LONG_TOKEN = re.compile(r"[A-Za-z0-9+/=_\-]{16,}")


def _attr(tag: str, name: str) -> str | None:
    match = re.search(rf"""\b{name}\s*=\s*(["'])(.*?)\1""", tag, re.I | re.S)
    return html_lib.unescape(match.group(2)) if match else None


def find_saml_post(page_html: str, page_url: str) -> tuple[str, dict] | None:
    """Liefert (Ziel-URL, Felder) für den SAML-POST oder None."""
    # 1. regulär als Formular
    for form in parse_forms(page_html):
        if "SAMLResponse" in form["fields"] and form["action"]:
            return urljoin(page_url, form["action"]), form["fields"]

    # 2. rohes HTML, unabhängig von Verschachtelung und Attributreihenfolge
    fields: dict[str, str] = {}
    for tag in re.findall(r"<input\b[^>]*>", page_html, re.I | re.S):
        name = _attr(tag, "name")
        if name in ("SAMLResponse", "RelayState"):
            fields[name] = _attr(tag, "value") or ""

    # 3. Werte in JavaScript, z. B. SAMLResponse: "..." oder "SAMLResponse", "..."
    if "SAMLResponse" not in fields:
        match = re.search(
            r"""SAMLResponse["']?\s*[:=,]\s*["']([A-Za-z0-9+/=]{100,})["']""", page_html
        )
        if match:
            fields["SAMLResponse"] = match.group(1)

    if "SAMLResponse" not in fields:
        return None

    action = None
    form_tag = re.search(r"<form\b[^>]*>", page_html, re.I | re.S)
    if form_tag:
        action = _attr(form_tag.group(0), "action")
    if not action:
        match = re.search(r"""(https://[^"'\s<>]*auth-saml/[^"'\s<>]*assert)""", page_html)
        action = match.group(1) if match else None
    if not action:
        return None
    return urljoin(page_url, action), fields


def describe_page(page_html: str) -> str:
    """Aufbau einer Seite ohne Werte – für Fehlermeldungen."""
    title = re.search(r"<title[^>]*>(.*?)</title>", page_html, re.I | re.S)
    lines = [f"Titel: {title.group(1).strip() if title else '-'}",
             f"Länge: {len(page_html)} Zeichen, <script>-Tags: {len(re.findall(r'<script', page_html, re.I))}",
             f"'SAMLResponse' im Text: {'ja' if 'SAMLResponse' in page_html else 'nein'}"]
    for form in parse_forms(page_html):
        target = urlsplit(form["action"])
        lines.append(f"Formular {form['method']} {target.netloc}{target.path} Felder: "
                     f"{', '.join(form['fields']) or '-'}")
    idx = page_html.find("SAMLResponse")
    if idx >= 0:
        context = _LONG_TOKEN.sub("<…>", page_html[max(0, idx - 80): idx + 40])
        lines.append("Kontext: " + " ".join(context.split()))
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", page_html, flags=re.I | re.S)
    text = _LONG_TOKEN.sub("<…>", html_lib.unescape(re.sub(r"<[^>]+>", " ", text)))
    lines.append("Sichtbarer Text: " + " ".join(text.split())[:300])
    return "\n      ".join(lines)


# --------------------------------------------------------------------------
# Anmeldung und Token-Erneuerung
# --------------------------------------------------------------------------
def login(
    email: str,
    password: str,
    saml_app: str = DEFAULT_SAML_APP,
    log: Callable[[str], None] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> HagerTokens:
    """Vollständige Anmeldung mit E-Mail und Passwort.
    Ohne `log` werden die Schritte unter dem Logger dieses Moduls
    protokolliert (nur Host und Pfad, keine Parameter)."""
    log = log or logger.info
    if not email or not password:
        raise HagerLoginError("E-Mail und Passwort sind erforderlich.")

    with httpx.Client(
        follow_redirects=True,
        timeout=TIMEOUT,
        transport=transport,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
    ) as client:
        # 1. SAML-Login starten, Weiterleitungen bis zur Hager-Anmeldeseite folgen
        response = client.get(E3DC_SAML_LOGIN, params={"app": saml_app})
        log(f"Anmeldeseite: HTTP {response.status_code} {_describe(response.url)}")
        if response.status_code != 200:
            raise HagerLoginError(f"Anmeldeseite nicht erreichbar (HTTP {response.status_code}).")

        # 2. Formular mit email/password absenden
        login_forms = [f for f in parse_forms(response.text) if "password" in f["fields"]]
        if login_forms:
            form = login_forms[0]
            action = urljoin(str(response.url), form["action"] or str(response.url))
            data = dict(form["fields"])
        elif urlsplit(str(response.url)).path.endswith("/login"):
            # Formular wird per JavaScript erzeugt -> direkt an die Seite posten
            action, data = str(response.url), {}
        else:
            raise HagerLoginError(
                f"Kein Anmeldeformular gefunden auf {_describe(response.url)}."
            )
        data.update({"email": email, "password": password})

        response = client.post(action, data=data)
        log(f"Nach Anmeldung: HTTP {response.status_code} {_describe(response.url)}")

        # 3. Keycloak-Seite mit der SAML-Antwort
        saml_post = find_saml_post(response.text, str(response.url))
        if saml_post is None:
            if any("password" in f["fields"] for f in parse_forms(response.text)) or \
                    "login.hager.com" in str(response.url):
                raise HagerLoginError("Anmeldung abgelehnt – E-Mail oder Passwort prüfen.")
            raise HagerLoginError(
                f"Keine SAML-Antwort auf {_describe(response.url)} (HTTP {response.status_code}).\n"
                f"      {describe_page(response.text)}"
            )

        target, fields = saml_post
        log(f"SAML-Antwort gefunden, sende an {_describe(target)}")
        # 4. SAMLResponse an E3/DC; die Weiterleitung selbst enthält die Tokens
        response = client.post(target, data=fields, follow_redirects=False)
        location = response.headers.get("location", "")
        log(f"SAML-Antwort: HTTP {response.status_code} -> {_describe(location)}")

    params = dict(parse_qsl(urlsplit(location).query))
    if not params.get("token") or not params.get("reAuthToken"):
        raise HagerLoginError(
            "Die Anmeldung lieferte keine Tokens – der Ablauf hat sich eventuell geändert."
        )
    return HagerTokens(token=params["token"], reauth_token=params["reAuthToken"])


def refresh(
    reauth_token: str,
    transport: httpx.BaseTransport | None = None,
) -> HagerTokens:
    """Neues Token-Paar über das Re-Auth-Token (ohne Passwort)."""
    with httpx.Client(timeout=TIMEOUT, transport=transport) as client:
        response = client.post(
            E3DC_REAUTH,
            files={"reAuthToken": (None, reauth_token)},
            headers={"User-Agent": USER_AGENT, "Origin": FLOW_ORIGIN, "Referer": FLOW_ORIGIN + "/"},
        )
    if response.status_code != 200:
        raise HagerLoginError(f"Token-Erneuerung fehlgeschlagen (HTTP {response.status_code}).")
    data = response.json()
    if not data.get("token") or not data.get("reAuthToken"):
        raise HagerLoginError("Token-Erneuerung lieferte keine Tokens.")
    return HagerTokens(token=data["token"], reauth_token=data["reAuthToken"])


# --------------------------------------------------------------------------
# Datenabruf
# --------------------------------------------------------------------------
def session_start_utc(item: dict) -> datetime | None:
    """Startzeit einer Session als UTC-Zeitpunkt, None wenn nicht lesbar."""
    session = item.get("session") if isinstance(item, dict) else None
    value = session.get("start_date_time") if isinstance(session, dict) else None

    if not isinstance(value, str):
        return None

    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def fetch_sessions(
    token: str,
    installation_id: str,
    stop_before: datetime | None = None,
    max_pages: int | None = None,
    info: dict | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """
    Ladesessions der Installation, seitenweise.

    stop_before: Die API liefert die neuesten Sessions zuerst. Sobald
        eine Seite nur noch bis vor diesen Zeitpunkt zurückreicht, wird
        nicht weiter geblättert. Ist eine Seite nicht absteigend
        sortiert, werden zur Sicherheit alle Seiten abgerufen.
    max_pages: höchstens so viele Seiten abrufen.
    info: erhält "total_elements" und "pages" (Anzahl abgerufener Seiten).
    """
    url = f"{BRIDGE_API}/sessions/installation/{installation_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "Origin": FLOW_ORIGIN,
        "Referer": FLOW_ORIGIN + "/",
    }
    items: list[dict] = []
    early_stop = stop_before is not None
    previous_oldest: datetime | None = None

    with httpx.Client(timeout=TIMEOUT, headers=headers, transport=transport) as client:
        for page in range(MAX_PAGES):
            started = time.monotonic()
            try:
                response = client.get(url, params={"page": page, "size": PAGE_SIZE})
            except httpx.TimeoutException:
                logger.warning(
                    "Hager: Sessions-API Seite %s ohne Antwort nach %.1f s",
                    page,
                    time.monotonic() - started,
                )
                raise
            logger.info(
                "Hager: Sessions-API Seite %s: HTTP %s in %.1f s",
                page,
                response.status_code,
                time.monotonic() - started,
            )
            if response.status_code in (401, 403):
                raise HagerUnauthorizedError(
                    f"Sessions-API Seite {page}: HTTP {response.status_code}"
                )
            if response.status_code != 200:
                raise HagerApiError(
                    f"Sessions-API Seite {page}: HTTP {response.status_code}"
                )
            data = response.json()
            content = data.get("content") or []
            items.extend(content)

            if info is not None:
                info["pages"] = page + 1
                if page == 0:
                    info["total_elements"] = data.get("totalElements")

            if data.get("last", True) or not content:
                return items

            if max_pages is not None and page + 1 >= max_pages:
                return items

            if early_stop:
                starts = [session_start_utc(item) for item in content]
                ordered = (
                    all(start is not None for start in starts)
                    and all(a >= b for a, b in zip(starts, starts[1:]))
                    and (previous_oldest is None or starts[0] <= previous_oldest)
                )

                if not ordered:
                    logger.warning(
                        "Hager: Sessions nicht absteigend sortiert – "
                        "rufe zur Sicherheit alle Seiten ab"
                    )
                    early_stop = False
                else:
                    previous_oldest = starts[-1]

                    if starts[-1] < stop_before:
                        logger.info(
                            "Hager: Abruf nach Seite %s beendet, ältere "
                            "Ladevorgänge liegen vor dem Cut-off",
                            page,
                        )
                        return items
    raise HagerApiError(f"Mehr als {MAX_PAGES} Seiten – Abbruch.")
