import logging
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import (
    HTTPException as StarletteHTTPException,
)
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.api.routes.auth import router as auth_router
from app.api.routes.auto_billing import router as auto_billing_router
from app.api.routes.wallboxes import router as wallboxes_router
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
from app.api.routes.retention import router as retention_router
from app.api.routes.hager_settings import (
    router as hager_settings_router,
)
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
from app.errors import error_content, validation_error_code
from app.database import (
    engine,
    tenant_session_provider,
)
from app.logging_config import setup_logging
from app.scheduler import (
    start_scheduler,
    stop_scheduler,
)
from app.version import BACKEND_VERSION
from app.tenancy.registry import tenant_registry


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
        tenant_session_provider.dispose()

        registry_engine = getattr(
            tenant_registry,
            "engine",
            None,
        )

        if registry_engine is not None:
            registry_engine.dispose()


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



@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> Response:
    """Fehlermeldung mit Code, damit die Oberfläche sie übersetzen kann."""

    if exc.status_code in (204, 304):
        return Response(
            status_code=exc.status_code,
            headers=exc.headers,
        )

    content = (
        error_content(exc.detail)
        if isinstance(exc.detail, str)
        else {"detail": exc.detail}
    )

    return JSONResponse(
        content=jsonable_encoder(content),
        status_code=exc.status_code,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Eingabefehler wie bisher, je Fehler zusätzlich mit Code."""

    errors = exc.errors()
    detail = jsonable_encoder(errors)

    for raw, encoded in zip(errors, detail):
        if isinstance(encoded, dict):
            encoded.update(validation_error_code(raw))

    return JSONResponse(
        content={"detail": detail},
        status_code=422,
    )


api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(imports_router)
api_router.include_router(assignment_router)
api_router.include_router(energy_prices_router)
api_router.include_router(auth_router)
api_router.include_router(invoices_router)
api_router.include_router(users_router)
api_router.include_router(rfid_cards_router)
api_router.include_router(hager_settings_router)
api_router.include_router(settings_router)
api_router.include_router(charging_sessions_router)
api_router.include_router(dashboard_router)
api_router.include_router(wallboxes_router)
api_router.include_router(retention_router)
api_router.include_router(auto_billing_router)
app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    database = "ok"

    health_engine = getattr(
        tenant_registry,
        "engine",
        engine,
    )

    try:
        with health_engine.connect() as connection:
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
