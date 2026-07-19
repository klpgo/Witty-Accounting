import logging

from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine
from app.logging_config import setup_logging
from app.scheduler import start_scheduler


setup_logging()

logger = logging.getLogger(__name__)


app = FastAPI(
    title="Witty Accounting"
)


@app.on_event("startup")
def startup():

    logger.info(
        "Backend gestartet"
    )

    start_scheduler()


@app.get("/")
def root():

    return {
        "application": "Witty Accounting",
        "status": "running",
    }


@app.get("/health")
def health():

    database = "ok"

    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )

    except Exception:
        database = "error"


    return {
        "status": "ok",
        "database": database,
        "scheduler": "running",
    }
