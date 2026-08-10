from collections import defaultdict, deque
from pathlib import Path
import time

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.config import Settings, settings
from app.control.auth import (
    ControlAuthenticationError,
    ControlAuthenticator,
    ControlSession,
)
from app.control.service import (
    TenantControlError,
    TenantControlService,
    TenantCreateData,
)
from app.tenancy.registry import build_control_database_url


COOKIE_NAME = "witty_control_session"
STATIC_DIRECTORY = Path(__file__).with_name("static")


class LoginRequest(BaseModel):
    password: str


class TenantCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    hostname: str = Field(min_length=1, max_length=253)
    admin_email: str = Field(min_length=3, max_length=255)
    admin_first_name: str = Field(min_length=1, max_length=100)
    admin_last_name: str = Field(min_length=1, max_length=100)
    admin_password: str = Field(min_length=1, max_length=1024)


class TenantStateRequest(BaseModel):
    active: bool


class TenantNameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TenantDeleteRequest(BaseModel):
    confirmation: str
    control_password: str


class LoginLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client: str) -> None:
        now = time.monotonic()
        attempts = self._attempts[client]
        while attempts and attempts[0] < now - 60:
            attempts.popleft()
        if len(attempts) >= 5:
            raise HTTPException(
                status_code=429,
                detail="Zu viele Anmeldeversuche. Bitte eine Minute warten.",
            )

    def failed(self, client: str) -> None:
        self._attempts[client].append(time.monotonic())

    def succeeded(self, client: str) -> None:
        self._attempts.pop(client, None)


def create_control_app(
    app_settings: Settings,
    *,
    service: TenantControlService | None = None,
    authenticator: ControlAuthenticator | None = None,
) -> FastAPI:
    auth = authenticator or ControlAuthenticator(
        password=app_settings.witty_control_password,
        session_secret=app_settings.witty_control_session_secret,
        session_minutes=app_settings.witty_control_session_minutes,
    )

    owned_engine = None
    if service is None:
        owned_engine = create_engine(
            build_control_database_url(app_settings),
            pool_pre_ping=True,
            poolclass=NullPool,
        )
        service = TenantControlService(
            settings=app_settings,
            control_engine=owned_engine,
        )

    tenant_service = service
    limiter = LoginLimiter()
    app = FastAPI(
        title="Witty Control",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.control_engine = owned_engine

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def current_session(
        session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    ) -> ControlSession:
        try:
            return auth.verify_session(session_token)
        except ControlAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def mutation_session(
        session: ControlSession = Depends(current_session),
        csrf: str | None = Header(default=None, alias="X-Control-CSRF"),
    ) -> ControlSession:
        try:
            auth.verify_csrf(session, csrf)
        except ControlAuthenticationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return session

    @app.exception_handler(TenantControlError)
    async def tenant_error_handler(_request: Request, exc: TenantControlError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.post("/api/login")
    def login(payload: LoginRequest, request: Request, response: Response):
        client = request.client.host if request.client else "local"
        limiter.check(client)
        if not auth.check_password(payload.password):
            limiter.failed(client)
            raise HTTPException(status_code=401, detail="Das Passwort ist falsch.")

        limiter.succeeded(client)
        token, session = auth.create_session()
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=auth.max_age,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
        return {"csrf_token": session.csrf_token, "expires_at": session.expires_at}

    @app.get("/api/session")
    def session_info(session: ControlSession = Depends(current_session)):
        return {"csrf_token": session.csrf_token, "expires_at": session.expires_at}

    @app.post("/api/logout")
    def logout(response: Response, _session=Depends(mutation_session)):
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"ok": True}

    @app.get("/api/tenants")
    def list_tenants(_session=Depends(current_session)):
        return tenant_service.list_tenants()

    @app.post("/api/tenants", status_code=201)
    def create_tenant(
        payload: TenantCreateRequest,
        _session=Depends(mutation_session),
    ):
        return tenant_service.create_tenant(TenantCreateData(**payload.model_dump()))

    @app.put("/api/tenants/{tenant_id}/state")
    def set_tenant_state(
        tenant_id: int,
        payload: TenantStateRequest,
        _session=Depends(mutation_session),
    ):
        tenant_service.set_active(tenant_id, active=payload.active)
        return {"ok": True}

    @app.put("/api/tenants/{tenant_id}/name")
    def set_tenant_name(
        tenant_id: int,
        payload: TenantNameRequest,
        _session=Depends(mutation_session),
    ):
        tenant_service.set_name(tenant_id, name=payload.name)
        return {"ok": True}

    @app.post("/api/tenants/{tenant_id}/delete")
    def delete_tenant(
        tenant_id: int,
        payload: TenantDeleteRequest,
        _session=Depends(mutation_session),
    ):
        if not auth.check_password(payload.control_password):
            raise HTTPException(status_code=403, detail="Das Control-Passwort ist falsch.")
        tenant_service.delete_tenant(
            tenant_id,
            confirmation=payload.confirmation,
        )
        return {"ok": True}

    app.mount("/assets", StaticFiles(directory=STATIC_DIRECTORY), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        return FileResponse(STATIC_DIRECTORY / "index.html")

    return app


def create_app() -> FastAPI:
    return create_control_app(settings)
