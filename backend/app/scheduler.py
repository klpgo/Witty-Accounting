import logging

from apscheduler.schedulers.background import BackgroundScheduler


logger = logging.getLogger(__name__)


scheduler = BackgroundScheduler()


def heartbeat():

    logger.info(
        "Scheduler heartbeat"
    )


def start_scheduler():

    scheduler.add_job(
        heartbeat,
        "interval",
        seconds=60,
        id="heartbeat",
        replace_existing=True,
    )

    scheduler.start()

    logger.info(
        "Scheduler gestartet"
    )
