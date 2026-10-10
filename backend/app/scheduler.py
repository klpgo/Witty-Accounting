import logging

from apscheduler.schedulers.background import BackgroundScheduler


logger = logging.getLogger(__name__)


scheduler = BackgroundScheduler()


def heartbeat():

    logger.info(
        "Scheduler heartbeat"
    )

    # Zeitpläne der Mandanten prüfen und fällige Hager-Abrufe starten
    from app.services.hager_auto_import import check_all_tenants

    check_all_tenants()

    # Automatische Abrechnung: fällige Läufe, Finalisierungen und
    # E-Mail-Wiederholungen der Mandanten
    from app.services import auto_billing

    auto_billing.check_all_tenants()


def start_scheduler() -> None:
    if scheduler.running:
        logger.info("Scheduler is already running")
        return

    scheduler.add_job(
        heartbeat,
        "interval",
        seconds=60,
        id="heartbeat",
        replace_existing=True,
    )

    scheduler.start()

    logger.info("Scheduler started")


def stop_scheduler() -> None:
    if not scheduler.running:
        return

    scheduler.shutdown(wait=False)

    from app.services.hager_auto_import import shutdown

    shutdown()

    from app.services import auto_billing

    auto_billing.shutdown()

    logger.info("Scheduler stopped")
