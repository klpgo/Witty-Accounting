import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes.auth import router as auth_router
from app.api.routes.energy_prices import (
    router as energy_prices_router,
)
from app.api.routes.rfid_cards import (
    assignment_router,
    router as rfid_cards_router,
)
from app.api.routes.imports import router as imports_router
from app.api.routes.invoices import (
    router as invoices_router,
)
from app.api.routes.users import (
    router as users_router,
)
from app.api.routes.settings import (
    router as settings_router,
)
from app.config import settings
from app.database import engine
from app.logging_config import setup_logging
from app.scheduler import (
    start_scheduler,
    stop_scheduler,
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(imports_router)
app.include_router(assignment_router)
app.include_router(energy_prices_router)
app.include_router(auth_router)
app.include_router(invoices_router)
app.include_router(users_router)
app.include_router(rfid_cards_router)
app.include_router(settings_router)

@app.get("/")
def root() -> dict[str, str]:
    return {
        "application": "Witty Accounting",
        "status": "running",
    }


@app.get("/health")
def health() -> dict[str, str]:
    database = "ok"

    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )
    except Exception:
        logger.exception(
            "Database health check failed."
        )
        database = "error"

    return {
        "status": "ok",
        "database": database,
        "scheduler": "running",
    }
