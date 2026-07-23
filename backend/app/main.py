import logging

from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine
from app.logging_config import setup_logging
from app.scheduler import start_scheduler

from app.api.routes.imports import router as imports_router

from app.scheduler import start_scheduler, stop_scheduler

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.scheduler import start_scheduler, stop_scheduler

from app.api.routes.energy_prices import (
    router as energy_prices_router,
)


setup_logging()

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()

    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title="Witty Accounting",
    lifespan=lifespan,
)

app.include_router(imports_router)

app.include_router(energy_prices_router)


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
