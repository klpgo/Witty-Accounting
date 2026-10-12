"""
Benutzer löschen (z. B. auf Verlangen nach Art. 17 DSGVO).

Gelöscht werden die Abrechnungsdaten des Benutzers – Ladevorgänge,
Grundgebühren, Kartenzuordnungen, Passwort-Links – und danach der Benutzer
selbst. Rechnungen und Stornorechnungen bleiben unverändert im Archiv: Sie
enthalten Empfänger und alle Positionsangaben als eigene Kopie, nur der
Verweis auf das Benutzerkonto wird leer.

Die Merkmale der gelöschten Ladevorgänge werden in
deleted_charging_sessions festgehalten, damit Import und Hager-Abgleich
sie nicht erneut anlegen.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.charging_session import ChargingSession
from app.models.deleted_charging_session import (
    DeletedChargingSession,
)
from app.models.invoice import Invoice, InvoiceItem
from app.models.monthly_base_fee_charge import (
    MonthlyBaseFeeCharge,
)
from app.models.password_reset_token import (
    PasswordResetToken,
)
from app.models.rfid_card_assignment import (
    RFIDCardAssignment,
)
from app.models.user import User
from app.utils.local_time import local_now


# Hindernisse, die sich mit discard_unbilled übergehen lassen
DISCARDABLE_BLOCKERS = frozenset(
    {
        "unbilled_charging_sessions",
        "unbilled_base_fees",
    }
)


class UserDeletionError(Exception):
    """Base exception for deleting users."""


class UserDeletionBlockedError(UserDeletionError):
    def __init__(self, check: "UserDeletionCheck") -> None:
        self.check = check
        super().__init__(
            "The user cannot be deleted yet: "
            + "; ".join(
                blocker.message
                for blocker in check.blocking(
                    discard_unbilled=False,
                )
            )
        )


@dataclass(frozen=True)
class DeletionBlocker:
    code: str
    count: int
    message: str
    discardable: bool = False


@dataclass
class UserDeletionCheck:
    user_id: int
    blockers: list[DeletionBlocker] = field(default_factory=list)
    charging_sessions: int = 0
    base_fees: int = 0
    rfid_assignments: int = 0
    invoices_kept: int = 0

    def blocking(
        self,
        *,
        discard_unbilled: bool,
    ) -> list[DeletionBlocker]:
        return [
            blocker
            for blocker in self.blockers
            if not (discard_unbilled and blocker.discardable)
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "can_delete": not self.blocking(discard_unbilled=False),
            "can_delete_with_discard": not self.blocking(
                discard_unbilled=True,
            ),
            "blockers": [
                {
                    "code": blocker.code,
                    "count": blocker.count,
                    "message": blocker.message,
                    "discardable": blocker.discardable,
                }
                for blocker in self.blockers
            ],
            "charging_sessions": self.charging_sessions,
            "base_fees": self.base_fees,
            "rfid_assignments": self.rfid_assignments,
            "invoices_kept": self.invoices_kept,
        }


@dataclass(frozen=True)
class UserDeletionResult:
    user_id: int
    charging_sessions: int
    base_fees: int
    rfid_assignments: int
    invoices_kept: int


def _count(db: Session, statement: Any) -> int:
    return int(db.scalar(statement) or 0)


def _assignment_ids(db: Session, user_id: int) -> list[int]:
    return list(
        db.scalars(
            select(RFIDCardAssignment.id).where(
                RFIDCardAssignment.user_id == user_id
            )
        ).all()
    )


def check_user_deletion(
    db: Session,
    *,
    user_id: int,
    acting_user_id: int | None = None,
    now: datetime | None = None,
) -> UserDeletionCheck:
    check = UserDeletionCheck(user_id=user_id)
    current_time = now or local_now()

    if acting_user_id is not None and acting_user_id == user_id:
        check.blockers.append(
            DeletionBlocker(
                code="own_account",
                count=1,
                message="You cannot delete your own account.",
            )
        )

    assignment_ids = _assignment_ids(db, user_id)
    check.rfid_assignments = len(assignment_ids)

    draft_count = _count(
        db,
        select(func.count(Invoice.id)).where(
            Invoice.user_id == user_id,
            Invoice.status == "draft",
        ),
    )

    if draft_count:
        check.blockers.append(
            DeletionBlocker(
                code="draft_invoices",
                count=draft_count,
                message=(
                    f"{draft_count} draft invoice(s) must be finalized or "
                    "deleted first."
                ),
            )
        )

    missing_pdf_count = _count(
        db,
        select(func.count(Invoice.id)).where(
            Invoice.user_id == user_id,
            Invoice.status == "finalized",
            Invoice.pdf_storage_path.is_(None),
        ),
    )

    if missing_pdf_count:
        check.blockers.append(
            DeletionBlocker(
                code="missing_invoice_pdfs",
                count=missing_pdf_count,
                message=(
                    f"{missing_pdf_count} finalized invoice(s) have no "
                    "archived PDF yet."
                ),
            )
        )

    active_assignment_count = _count(
        db,
        select(func.count(RFIDCardAssignment.id)).where(
            RFIDCardAssignment.user_id == user_id,
            or_(
                RFIDCardAssignment.valid_to.is_(None),
                RFIDCardAssignment.valid_to > current_time,
            ),
        ),
    )

    if active_assignment_count:
        check.blockers.append(
            DeletionBlocker(
                code="active_rfid_assignments",
                count=active_assignment_count,
                message=(
                    f"{active_assignment_count} RFID card assignment(s) "
                    "must be ended first."
                ),
            )
        )

    if assignment_ids:
        check.charging_sessions = _count(
            db,
            select(func.count(ChargingSession.id)).where(
                ChargingSession.rfid_assignment_id.in_(assignment_ids)
            ),
        )

        unbilled_sessions = _count(
            db,
            select(func.count(ChargingSession.id)).where(
                ChargingSession.rfid_assignment_id.in_(assignment_ids),
                ChargingSession.invoiced.is_not(True),
                ChargingSession.discarded_at.is_(None),
            ),
        )

        if unbilled_sessions:
            check.blockers.append(
                DeletionBlocker(
                    code="unbilled_charging_sessions",
                    count=unbilled_sessions,
                    message=(
                        f"{unbilled_sessions} charging session(s) have not "
                        "been billed yet."
                    ),
                    discardable=True,
                )
            )

    check.base_fees = _count(
        db,
        select(func.count(MonthlyBaseFeeCharge.id)).where(
            MonthlyBaseFeeCharge.user_id == user_id
        ),
    )

    unbilled_fees = _count(
        db,
        select(func.count(MonthlyBaseFeeCharge.id)).where(
            MonthlyBaseFeeCharge.user_id == user_id,
            MonthlyBaseFeeCharge.invoiced.is_(False),
        ),
    )

    if unbilled_fees:
        check.blockers.append(
            DeletionBlocker(
                code="unbilled_base_fees",
                count=unbilled_fees,
                message=(
                    f"{unbilled_fees} monthly base fee(s) have not been "
                    "billed yet."
                ),
                discardable=True,
            )
        )

    check.invoices_kept = _count(
        db,
        select(func.count(Invoice.id)).where(
            Invoice.user_id == user_id,
            Invoice.status == "finalized",
        ),
    )

    return check


def delete_user(
    db: Session,
    *,
    user_id: int,
    acting_user_id: int | None = None,
    discard_unbilled: bool = False,
) -> UserDeletionResult:
    """
    Löscht Abrechnungsdaten und Benutzer in einer Transaktion.
    Rechnungen bleiben erhalten (user_id wird leer).
    """
    user = db.get(User, user_id)

    if user is None:
        raise UserDeletionError(f"User {user_id} was not found.")

    check = check_user_deletion(
        db,
        user_id=user_id,
        acting_user_id=acting_user_id,
    )

    if check.blocking(discard_unbilled=discard_unbilled):
        raise UserDeletionBlockedError(check)

    assignment_ids = _assignment_ids(db, user_id)

    sessions = (
        list(
            db.scalars(
                select(ChargingSession).where(
                    ChargingSession.rfid_assignment_id.in_(assignment_ids)
                )
            ).all()
        )
        if assignment_ids
        else []
    )
    session_ids = [session.id for session in sessions]

    fee_ids = list(
        db.scalars(
            select(MonthlyBaseFeeCharge.id).where(
                MonthlyBaseFeeCharge.user_id == user_id
            )
        ).all()
    )

    try:
        for session in sessions:
            db.add(
                DeletedChargingSession(
                    hager_session_id=session.hager_session_id,
                    import_hash=session.import_hash,
                    start_time=session.start_time,
                    wallbox_id=session.wallbox_id,
                    station_id=session.station_id,
                )
            )

        # Rechnungspositionen behalten ihre eigenen Angaben
        if session_ids:
            db.execute(
                update(InvoiceItem)
                .where(InvoiceItem.charging_session_id.in_(session_ids))
                .values(charging_session_id=None)
                .execution_options(synchronize_session=False)
            )

        if fee_ids:
            db.execute(
                update(InvoiceItem)
                .where(
                    InvoiceItem.monthly_base_fee_charge_id.in_(fee_ids)
                )
                .values(monthly_base_fee_charge_id=None)
                .execution_options(synchronize_session=False)
            )

            db.execute(
                delete(MonthlyBaseFeeCharge)
                .where(MonthlyBaseFeeCharge.id.in_(fee_ids))
                .execution_options(synchronize_session=False)
            )

        if session_ids:
            db.execute(
                delete(ChargingSession)
                .where(ChargingSession.id.in_(session_ids))
                .execution_options(synchronize_session=False)
            )

        if assignment_ids:
            db.execute(
                delete(RFIDCardAssignment)
                .where(RFIDCardAssignment.id.in_(assignment_ids))
                .execution_options(synchronize_session=False)
            )

        db.execute(
            delete(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id)
            .execution_options(synchronize_session=False)
        )

        # Verweise auf den Benutzer leeren, Rechnungen bleiben
        db.execute(
            update(Invoice)
            .where(Invoice.user_id == user_id)
            .values(user_id=None)
            .execution_options(synchronize_session=False)
        )
        db.execute(
            update(Invoice)
            .where(Invoice.pdf_exported_by_user_id == user_id)
            .values(pdf_exported_by_user_id=None)
            .execution_options(synchronize_session=False)
        )
        db.execute(
            update(ChargingSession)
            .where(ChargingSession.discarded_by_user_id == user_id)
            .values(discarded_by_user_id=None)
            .execution_options(synchronize_session=False)
        )

        db.execute(
            delete(User)
            .where(User.id == user_id)
            .execution_options(synchronize_session=False)
        )

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.expire_all()

    return UserDeletionResult(
        user_id=user_id,
        charging_sessions=len(session_ids),
        base_fees=len(fee_ids),
        rfid_assignments=len(assignment_ids),
        invoices_kept=check.invoices_kept,
    )
