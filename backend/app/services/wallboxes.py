"""
Namen der Wallboxen.

Jede Wallbox-ID, die in Ladevorgängen vorkommt, hat einen Eintrag. Der
angezeigte Name ist der eigene Name, sonst der Name aus der Hager Cloud,
sonst die Kurzform der ID ("ID: ..XXXXX"). Er wird als Stationsname in die
Ladevorgänge übernommen; Rechnungen speichern ihn beim Anlegen.
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.charging_session import ChargingSession
from app.models.invoice import Invoice, InvoiceItem
from app.models.wallbox import Wallbox

FALLBACK_SUFFIX_LENGTH = 5


def fallback_name(wallbox_id: str) -> str:
    """Kurzform der technischen ID, z. B. "ID: ..Uydb3"."""
    return f"ID: ..{wallbox_id[-FALLBACK_SUFFIX_LENGTH:]}"


def display_name(wallbox: Wallbox) -> str:
    return wallbox.custom_name or wallbox.hager_name or fallback_name(wallbox.wallbox_id)


def ensure_wallboxes(db: Session, wallbox_ids: Iterable[str]) -> None:
    """Legt für unbekannte Wallbox-IDs einen Eintrag ohne Namen an."""
    wanted = {wallbox_id for wallbox_id in wallbox_ids if wallbox_id}

    if not wanted:
        return

    known = set(
        db.scalars(select(Wallbox.wallbox_id).where(Wallbox.wallbox_id.in_(wanted)))
    )

    for wallbox_id in sorted(wanted - known):
        db.add(Wallbox(wallbox_id=wallbox_id))

    db.flush()


def update_hager_names(db: Session, names: dict[str, str]) -> None:
    """Übernimmt die Namen aus der Hager Cloud (ohne eigene Namen zu ändern)."""
    ensure_wallboxes(db, names)

    for wallbox in db.scalars(select(Wallbox).where(Wallbox.wallbox_id.in_(list(names)))):
        name = (names.get(wallbox.wallbox_id) or "").strip() or None

        if name and name != wallbox.hager_name:
            wallbox.hager_name = name[:100]

    db.flush()


def display_names(db: Session) -> dict[str, str]:
    """{Wallbox-ID: angezeigter Name} für alle bekannten Wallboxen."""
    return {wallbox.wallbox_id: display_name(wallbox) for wallbox in db.scalars(select(Wallbox))}


def apply_name_to_open_sessions(db: Session, wallbox: Wallbox) -> int:
    """
    Setzt den angezeigten Namen bei allen noch nicht abgerechneten
    Ladevorgängen dieser Wallbox, auch bei solchen aus stornierten Rechnungen.
    Abgerechnete Ladevorgänge und solche in Rechnungsentwürfen bleiben
    unverändert.
    """
    # Ladevorgänge aus stornierten Rechnungen sind wieder offen, stehen aber
    # noch in deren Positionen – ausgenommen sind deshalb nur Entwürfe
    in_draft = (
        select(InvoiceItem.charging_session_id)
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .where(
            Invoice.status == "draft",
            InvoiceItem.charging_session_id.is_not(None),
        )
    )
    result = db.execute(
        update(ChargingSession)
        .where(
            ChargingSession.wallbox_id == wallbox.wallbox_id,
            ChargingSession.invoiced.is_(False),
            ChargingSession.id.not_in(in_draft),
        )
        .values(station_id=display_name(wallbox))
        .execution_options(synchronize_session=False)
    )

    return int(result.rowcount or 0)


def wallbox_id_of(charging_session: ChargingSession) -> str | None:
    """
    Wallbox-ID eines Ladevorgangs: gespeichert oder – bei älteren Daten –
    aus einem Stationsnamen der Form "ID: <vollständige ID>" gelesen.
    """
    if charging_session.wallbox_id:
        return charging_session.wallbox_id

    station = charging_session.station_id or ""

    if station.startswith("ID: ") and not station.startswith("ID: .."):
        candidate = station[len("ID: "):].strip()
        if candidate and " " not in candidate:
            return candidate

    return None


def refresh_station_names(
    db: Session,
    charging_sessions: Iterable[ChargingSession],
) -> None:
    """
    Setzt den aktuellen Namen der Wallbox als Stationsnamen, bevor die
    Ladevorgänge abgerechnet werden. So wirkt ein geänderter oder neu
    vergebener Name auch bei Ladevorgängen, die zwischenzeitlich in einer
    (stornierten) Rechnung standen.
    """
    sessions = list(charging_sessions)
    ids = {wallbox_id_of(session) for session in sessions} - {None}

    if not ids:
        return

    ensure_wallboxes(db, ids)
    names = display_names(db)

    for session in sessions:
        wallbox_id = wallbox_id_of(session)

        if wallbox_id is None:
            continue

        session.wallbox_id = wallbox_id
        session.station_id = names.get(wallbox_id) or fallback_name(wallbox_id)

    db.flush()
