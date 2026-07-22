import logging

from apscheduler.schedulers.background import BackgroundScheduler


logger = logging.getLogger(__name__)


scheduler = BackgroundScheduler()


def heartbeat():

    logger.info(
        "Scheduler heartbeat"
    )


def start_scheduler() -> None:
    if scheduler.running:
        logger.info("Scheduler läuft bereits")
        return

    scheduler.add_job(
        heartbeat,
        "interval",
        seconds=60,
        id="heartbeat",
        replace_existing=True,
    )

    scheduler.start()

    logger.info("Scheduler gestartet")


def stop_scheduler() -> None:
    if not scheduler.running:
        return

    scheduler.shutdown(wait=False)

    logger.info("Scheduler gestoppt")
