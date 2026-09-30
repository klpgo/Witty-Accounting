"""
Verwerfen und Wiederherstellen von Ladevorgängen.

Ein verworfener Ladevorgang bleibt in der Datenbank, damit ihn die
Dublettenprüfung weiterhin erkennt und ein erneuter Abruf ihn nicht
zurückholt. Er wird nicht angezeigt, nicht bepreist, nicht nachträglich
zugeordnet und nicht abgerechnet. Zeitpunkt, Benutzer und Grund werden
festgehalten.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.charging_session import ChargingSession
from app.models.invoice import InvoiceItem
from app.utils.utc import utc_now


class ChargingSessionNotFoundError(LookupError):
    pass


class DiscardNotAllowedError(ValueError):
    pass


def load_sessions(db: Session, session_ids: list[int]) -> list[ChargingSession]:
    unique_ids = sorted(set(session_ids))
    sessions = db.scalars(
        select(ChargingSession).where(ChargingSession.id.in_(unique_ids))
    ).all()

    missing = sorted(set(unique_ids) - {s.id for s in sessions})

    if missing:
        raise ChargingSessionNotFoundError(
            "Charging sessions not found: " + ", ".join(map(str, missing))
        )

    return list(sessions)


def blocking_reason(db: Session, charging_session: ChargingSession) -> str | None:
    if charging_session.invoiced or charging_session.invoice_id is not None:
        return "already billed"

    in_invoice = db.scalar(
        select(InvoiceItem.id)
        .where(InvoiceItem.charging_session_id == charging_session.id)
        .limit(1)
    )

    if in_invoice is not None:
        return "contained in an invoice draft"

    return None


def discard_sessions(
    db: Session,
    session_ids: list[int],
    user_id: int | None,
    reason: str | None = None,
) -> int:
    """Verwirft die Ladevorgänge. Alle oder keiner: Ist einer nicht
    verwerfbar, wird nichts geändert."""
    sessions = load_sessions(db, session_ids)
    problems = [
        f"#{s.id} ({problem})"
        for s in sessions
        if s.discarded_at is None and (problem := blocking_reason(db, s))
    ]

    if problems:
        raise DiscardNotAllowedError(
            "The following charging sessions cannot be discarded: "
            + ", ".join(problems)
        )

    timestamp = utc_now()
    reason = (reason or "").strip() or None
    changed = 0

    for charging_session in sessions:
        if charging_session.discarded_at is not None:
            continue

        charging_session.discarded_at = timestamp
        charging_session.discarded_by_user_id = user_id
        charging_session.discard_reason = reason
        changed += 1

    db.commit()

    return changed


def restore_sessions(db: Session, session_ids: list[int]) -> int:
    """Hebt das Verwerfen auf. Fehlende Zuordnungen werden danach wie
    üblich nachgeholt, Preise beim Rechnungsentwurf berechnet."""
    from app.services.rfid_reassignment import reassign_open_sessions

    sessions = load_sessions(db, session_ids)
    changed = 0

    for charging_session in sessions:
        if charging_session.discarded_at is None:
            continue

        charging_session.discarded_at = None
        charging_session.discarded_by_user_id = None
        charging_session.discard_reason = None
        changed += 1

    db.flush()
    reassign_open_sessions(db)
    db.commit()

    return changed
