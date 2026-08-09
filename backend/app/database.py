from collections import OrderedDict
from threading import RLock

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)

from app.config import settings
from app.tenancy.context import TenantContext


DEFAULT_TENANT = TenantContext(
    id=1,
    slug="default",
    name=settings.app_name,
    db_host=settings.db_host,
    db_port=settings.db_port,
    db_name=settings.db_name,
    db_user=settings.db_user,
    db_password=settings.db_password,
    archive_namespace=None,
    canonical_hostname=None,
)

DATABASE_URL = DEFAULT_TENANT.database_url().render_as_string(
    hide_password=False
)


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


class TenantSessionProvider:
    """Maintain bounded SQLAlchemy pools per tenant."""

    def __init__(
        self,
        *,
        max_cached_engines: int = 20,
    ) -> None:
        if max_cached_engines < 1:
            raise ValueError(
                "max_cached_engines muss mindestens "
                "1 sein."
            )

        self.max_cached_engines = (
            max_cached_engines
        )
        self._engines: OrderedDict[
            int,
            tuple[tuple[object, ...], Engine],
        ] = OrderedDict()
        self._lock = RLock()

    def register_engine(
        self,
        tenant: TenantContext,
        tenant_engine: Engine,
    ) -> None:
        with self._lock:
            self._engines[tenant.id] = (
                tenant.connection_fingerprint(),
                tenant_engine,
            )

    def get_engine(
        self,
        tenant: TenantContext,
    ) -> Engine:
        fingerprint = (
            tenant.connection_fingerprint()
        )

        with self._lock:
            cached = self._engines.get(tenant.id)

            if (
                cached is not None
                and cached[0] == fingerprint
            ):
                self._engines.move_to_end(
                    tenant.id
                )
                return cached[1]

            tenant_engine = create_engine(
                tenant.database_url(),
                pool_pre_ping=True,
                pool_recycle=3600,
            )

            if cached is not None:
                cached[1].dispose()

            self._engines[tenant.id] = (
                fingerprint,
                tenant_engine,
            )
            self._engines.move_to_end(
                tenant.id
            )

            while (
                len(self._engines)
                > self.max_cached_engines
            ):
                _, (_, evicted_engine) = (
                    self._engines.popitem(
                        last=False
                    )
                )
                evicted_engine.dispose()

            return tenant_engine

    def create_session(
        self,
        tenant: TenantContext,
    ) -> Session:
        tenant_engine = self.get_engine(tenant)
        db = Session(
            tenant_engine,
            autoflush=False,
            expire_on_commit=True,
        )
        db.info["tenant"] = tenant
        return db

    def dispose(self) -> None:
        with self._lock:
            for _, tenant_engine in (
                self._engines.values()
            ):
                tenant_engine.dispose()

            self._engines.clear()


tenant_session_provider = TenantSessionProvider(
    max_cached_engines=(
        settings.tenant_engine_cache_size
    )
)

if not settings.tenancy_enabled:
    tenant_session_provider.register_engine(
        DEFAULT_TENANT,
        engine,
    )
