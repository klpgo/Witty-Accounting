"""
Automatischer Abruf aus der Hager Cloud pro Mandant.

Der Scheduler-Heartbeat ruft jede Minute check_all_tenants() auf. Für
jeden aktiven Mandanten wird dessen eigener Zeitplan geprüft; ist ein
Abruf fällig, wird der Start sofort in der Mandanten-Datenbank vermerkt
(damit der nächste Heartbeat ihn nicht erneut auslöst) und der Import in
einem Hintergrund-Thread ausgeführt. Ergebnis oder Fehler werden beim
Mandanten gespeichert.

Fehler eines Mandanten beeinträchtigen die anderen nicht.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.global_settings import GlobalSettings
from app.services.hager_schedule import is_due, parse_start_time
from app.services.hager_sync import (
    HagerConfigurationError,
    HagerConnectionError,
    import_from_hager,
)
from app.services.data_timezone import DataTimezoneMismatchError
from app.services.import_lock import ImportBusyError
from app.services.pricing import price_charging_sessions
from app.services.smtp_secret import SmtpSecretError
from app.tenancy.context import TenantContext
from app.utils.utc import utc_now


logger = logging.getLogger(__name__)

STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

SessionFactory = Callable[[TenantContext], Session]
Submit = Callable[..., object]

_running_tenants: set[int] = set()
_running_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor

    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="hager-import",
            )

        return _executor


def _default_session_factory(tenant: TenantContext) -> Session:
    from app.database import tenant_session_provider

    return tenant_session_provider.create_session(tenant)


def _default_tenants() -> list[TenantContext]:
    from app.tenancy.registry import tenant_registry

    return tenant_registry.list_active()


def check_all_tenants(
    now: datetime | None = None,
    list_tenants: Callable[[], list[TenantContext]] = _default_tenants,
    session_factory: SessionFactory = _default_session_factory,
    submit: Submit | None = None,
) -> int:
    """Prüft alle aktiven Mandanten. Rückgabe: Anzahl gestarteter Abrufe."""
    now = now or datetime.now(UTC)

    try:
        tenants = list_tenants()
    except Exception:
        logger.exception("Automatic Hager fetch: tenants could not be read")
        return 0

    started = 0

    for tenant in tenants:
        try:
            if start_if_due(tenant, now, session_factory, submit):
                started += 1
        except Exception:
            logger.exception(
                "Automatic Hager fetch: check for tenant %s failed",
                tenant.slug,
            )

    return started


def write_status(db: Session, **values: object) -> None:
    """Status des automatischen Abrufs als gezieltes UPDATE in einer
    frischen Transaktion (verhindert MariaDB-Fehler 1020)."""
    db.execute(
        update(GlobalSettings)
        .where(GlobalSettings.id == 1)
        .values(**values)
    )
    db.commit()


def start_if_due(
    tenant: TenantContext,
    now: datetime,
    session_factory: SessionFactory = _default_session_factory,
    submit: Submit | None = None,
) -> bool:
    with _running_lock:
        if tenant.id in _running_tenants:
            return False

    db = session_factory(tenant)

    try:
        settings = db.get(GlobalSettings, 1)

        if settings is None or not settings.hager_auto_import_enabled:
            return False

        if not is_due(
            now,
            settings.hager_auto_import_last_started_at,
            parse_start_time(settings.hager_auto_import_start_time),
            settings.hager_auto_import_interval_hours,
        ):
            return False

        # Start sofort vermerken: der nächste Heartbeat löst ihn nicht erneut
        # aus. Lesetransaktion zuerst beenden, dann gezielt aktualisieren.
        db.rollback()
        write_status(
            db,
            hager_auto_import_last_started_at=(
                now.astimezone(UTC).replace(tzinfo=None)
            ),
            hager_auto_import_last_finished_at=None,
            hager_auto_import_last_status=STATUS_RUNNING,
            hager_auto_import_last_message=None,
        )
    finally:
        db.close()

    with _running_lock:
        _running_tenants.add(tenant.id)

    logger.info("Automatic Hager fetch for tenant %s started", tenant.slug)

    try:
        (submit or _get_executor().submit)(run_import, tenant, session_factory)
    except Exception:
        with _running_lock:
            _running_tenants.discard(tenant.id)
        raise

    return True


def summarize(import_result: dict, pricing_result: dict) -> str:
    """Kurzfassung eines Laufs für die Statusanzeige (englisch)."""
    parts = [
        f"{import_result['imported']} new",
        f"{import_result['skipped']} skipped",
    ]

    if pricing_result.get("missing_price"):
        parts.append(f"{pricing_result['missing_price']} without price")

    if import_result.get("unknown_rfid_sessions"):
        parts.append(
            f"{import_result['unknown_rfid_sessions']} without card assignment"
        )

    if import_result.get("skipped_before_billing_start"):
        parts.append(
            f"{import_result['skipped_before_billing_start']} before billing start"
        )

    if import_result.get("skipped_empty"):
        parts.append(f"{import_result['skipped_empty']} without energy")

    if import_result.get("reassigned_sessions"):
        parts.append(
            f"{import_result['reassigned_sessions']} assigned retroactively"
        )

    fetched_from = import_result.get("fetched_from")
    scope = (
        f"from {fetched_from:%Y-%m-%d}"
        if fetched_from is not None
        else "in full"
    )

    return f"{', '.join(parts)} (fetched {scope})"


def run_import(
    tenant: TenantContext,
    session_factory: SessionFactory = _default_session_factory,
) -> None:
    db = session_factory(tenant)

    try:
        try:
            import_result = import_from_hager(db)
            pricing_result = price_charging_sessions(
                db=db,
                overwrite=False,
                import_hashes=set(import_result["imported_hashes"]),
            )
            status = STATUS_SUCCESS
            message = summarize(import_result, pricing_result)
        except (
            HagerConfigurationError,
            HagerConnectionError,
            ImportBusyError,
            DataTimezoneMismatchError,
            SmtpSecretError,
            ValueError,
        ) as exc:
            db.rollback()
            status = STATUS_ERROR
            message = str(exc)
        except Exception as exc:
            db.rollback()
            logger.exception(
                "Automatic Hager fetch for tenant %s: unexpected error",
                tenant.slug,
            )
            status = STATUS_ERROR
            message = f"Unexpected error: {type(exc).__name__}"

        try:
            db.commit()
        except Exception:
            db.rollback()

        write_status(
            db,
            hager_auto_import_last_finished_at=utc_now(),
            hager_auto_import_last_status=status,
            hager_auto_import_last_message=message,
        )

        log = logger.info if status == STATUS_SUCCESS else logger.warning
        log(
            "Automatic Hager fetch for tenant %s: %s",
            tenant.slug,
            message,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "Automatic Hager fetch for tenant %s: status not saved",
            tenant.slug,
        )
    finally:
        db.close()

        with _running_lock:
            _running_tenants.discard(tenant.id)


def shutdown() -> None:
    global _executor

    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None
