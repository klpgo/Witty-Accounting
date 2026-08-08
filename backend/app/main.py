import logging
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.exceptions import (
    HTTPException as StarletteHTTPException,
)
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.api.routes.auth import router as auth_router
from app.api.routes.energy_prices import (
    router as energy_prices_router,
)
from app.api.routes.rfid_cards import (
    assignment_router,
    router as rfid_cards_router,
)
from app.api.routes.charging_sessions import (
    router as charging_sessions_router,
)
from app.api.routes.dashboard import (
    router as dashboard_router,
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
from app.version import BACKEND_VERSION


setup_logging()

logger = logging.getLogger(__name__)

API_PREFIX = "/api"
FRONTEND_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "frontend"
)


class SPAStaticFiles(StaticFiles):
    """Serve Vite files and fall back to index.html for SPA routes."""

    async def get_response(
        self,
        path: str,
        scope: Scope,
    ) -> Response:
        try:
            response = await super().get_response(
                path,
                scope,
            )
        except StarletteHTTPException as exc:
            if (
                exc.status_code != 404
                or not self._is_spa_route(path)
            ):
                raise

            response = await super().get_response(
                "index.html",
                scope,
            )

        if (
            response.status_code == 404
            and self._is_spa_route(path)
        ):
            response = await super().get_response(
                "index.html",
                scope,
            )

        if (
            response.status_code == 200
            and path.startswith("assets/")
        ):
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable"
            )

        return response

    @staticmethod
    def _is_spa_route(path: str) -> bool:
        if path == "api" or path.startswith("api/"):
            return False

        return not PurePosixPath(path).suffix


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()

    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title="Witty Accounting",
    version=BACKEND_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(imports_router)
api_router.include_router(assignment_router)
api_router.include_router(energy_prices_router)
api_router.include_router(auth_router)
api_router.include_router(invoices_router)
api_router.include_router(users_router)
api_router.include_router(rfid_cards_router)
api_router.include_router(settings_router)
api_router.include_router(charging_sessions_router)
api_router.include_router(dashboard_router)
app.include_router(api_router)


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


if FRONTEND_DIRECTORY.is_dir():
    app.mount(
        "/",
        SPAStaticFiles(
            directory=FRONTEND_DIRECTORY,
            html=True,
        ),
        name="frontend",
    )
else:
    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "application": "Witty Accounting",
            "status": "running",
        }
