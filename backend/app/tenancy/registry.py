from dataclasses import dataclass
from threading import RLock
from time import monotonic

from pydantic import SecretStr
from sqlalchemy import (
    Engine,
    URL,
    create_engine,
    select,
)
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.tenancy.context import TenantContext
from app.tenancy.models import Tenant, TenantDomain
from app.tenancy.secrets import (
    decrypt_tenant_db_password,
)


class TenantRegistryError(RuntimeError):
    """The tenant registry is unavailable or invalid."""


class TenantNotFoundError(TenantRegistryError):
    """No active tenant is registered for a hostname."""


def normalize_hostname(hostname: str) -> str:
    value = hostname.strip().rstrip(".")

    if not value:
        raise TenantNotFoundError(
            "Der Mandanten-Hostname fehlt."
        )

    try:
        normalized = value.encode("idna").decode(
            "ascii"
        )
    except UnicodeError as exc:
        raise TenantNotFoundError(
            "Der Mandanten-Hostname ist ungültig."
        ) from exc

    normalized = normalized.lower()

    if len(normalized) > 253 or any(
        not label
        or len(label) > 63
        for label in normalized.split(".")
    ):
        raise TenantNotFoundError(
            "Der Mandanten-Hostname ist ungültig."
        )

    return normalized


class LegacyTenantRegistry:
    """Single-tenant compatibility registry."""

    def __init__(
        self,
        app_settings: Settings,
    ) -> None:
        self._tenant = TenantContext(
            id=1,
            slug="default",
            name=app_settings.app_name,
            db_host=app_settings.db_host,
            db_port=app_settings.db_port,
            db_name=app_settings.db_name,
            db_user=app_settings.db_user,
            db_password=app_settings.db_password,
            archive_namespace=None,
            canonical_hostname=None,
        )

    def resolve(
        self,
        hostname: str,
    ) -> TenantContext:
        # The old deployment accepted every Host header. Keep
        # that behaviour until tenancy is explicitly enabled.
        return self._tenant

    def get_by_id(
        self,
        tenant_id: int,
    ) -> TenantContext:
        if tenant_id != self._tenant.id:
            raise TenantNotFoundError(
                "Der Mandant ist unbekannt."
            )

        return self._tenant

    def list_active(self) -> list[TenantContext]:
        return [self._tenant]


@dataclass(frozen=True)
class CachedTenant:
    expires_at: float
    tenant: TenantContext


class DatabaseTenantRegistry:
    """Resolve domains through the central control database."""

    def __init__(
        self,
        *,
        engine: Engine,
        encryption_key: SecretStr,
        cache_seconds: int = 30,
    ) -> None:
        if cache_seconds < 0:
            raise ValueError(
                "cache_seconds darf nicht negativ sein."
            )

        self.engine = engine
        self.encryption_key = encryption_key
        self.cache_seconds = cache_seconds
        self._cache: dict[str, CachedTenant] = {}
        self._lock = RLock()

    def resolve(
        self,
        hostname: str,
    ) -> TenantContext:
        normalized = normalize_hostname(hostname)
        now = monotonic()

        with self._lock:
            cached = self._cache.get(normalized)

            if (
                cached is not None
                and cached.expires_at >= now
            ):
                return cached.tenant

        with Session(self.engine) as db:
            row = db.execute(
                select(Tenant, TenantDomain)
                .join(
                    TenantDomain,
                    TenantDomain.tenant_id
                    == Tenant.id,
                )
                .where(
                    TenantDomain.hostname
                    == normalized,
                    Tenant.active.is_(True),
                )
            ).one_or_none()

            if row is None:
                raise TenantNotFoundError(
                    "Für diesen Host ist kein aktiver "
                    "Mandant registriert."
                )

            tenant_model, domain_model = row

            tenant = self._build_context(
                db,
                tenant_model,
                fallback_hostname=(
                    domain_model.hostname
                ),
            )

        with self._lock:
            self._cache[normalized] = CachedTenant(
                expires_at=(
                    now + self.cache_seconds
                ),
                tenant=tenant,
            )

        return tenant

    def get_by_id(
        self,
        tenant_id: int,
    ) -> TenantContext:
        with Session(self.engine) as db:
            tenant_model = db.scalar(
                select(Tenant).where(
                    Tenant.id == tenant_id,
                    Tenant.active.is_(True),
                )
            )

            if tenant_model is None:
                raise TenantNotFoundError(
                    "Der Mandant ist unbekannt oder "
                    "inaktiv."
                )

            return self._build_context(
                db,
                tenant_model,
            )

    def list_active(self) -> list[TenantContext]:
        with Session(self.engine) as db:
            tenant_models = db.scalars(
                select(Tenant)
                .where(Tenant.active.is_(True))
                .order_by(Tenant.id)
            ).all()

            return [
                self._build_context(
                    db,
                    tenant_model,
                )
                for tenant_model in tenant_models
            ]

    def _build_context(
        self,
        db: Session,
        tenant_model: Tenant,
        *,
        fallback_hostname: str | None = None,
    ) -> TenantContext:
        canonical_hostname = db.scalar(
            select(TenantDomain.hostname)
            .where(
                TenantDomain.tenant_id
                == tenant_model.id,
                TenantDomain.canonical.is_(True),
            )
        )

        if canonical_hostname is None:
            canonical_hostname = fallback_hostname

        if canonical_hostname is None:
            raise TenantRegistryError(
                f"Mandant {tenant_model.id} hat keine "
                "kanonische Domain."
            )

        if tenant_model.archive_namespace is None:
            raise TenantRegistryError(
                f"Mandant {tenant_model.id} hat keinen "
                "Archiv-Namespace."
            )

        return TenantContext(
            id=tenant_model.id,
            slug=tenant_model.slug,
            name=tenant_model.name,
            db_host=tenant_model.db_host,
            db_port=tenant_model.db_port,
            db_name=tenant_model.db_name,
            db_user=tenant_model.db_user,
            db_password=(
                decrypt_tenant_db_password(
                    tenant_model
                    .db_password_encrypted,
                    encryption_key=(
                        self.encryption_key
                    ),
                )
            ),
            archive_namespace=(
                tenant_model.archive_namespace
            ),
            canonical_hostname=canonical_hostname,
            config_version=(
                tenant_model.config_version
            ),
        )

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()


def build_control_database_url(
    app_settings: Settings,
) -> URL:
    required_values = {
        "CONTROL_DB_HOST": (
            app_settings.control_db_host
        ),
        "CONTROL_DB_NAME": (
            app_settings.control_db_name
        ),
        "CONTROL_DB_USER": (
            app_settings.control_db_user
        ),
        "CONTROL_DB_PASSWORD": (
            app_settings.control_db_password
        ),
    }
    missing = [
        name
        for name, value in required_values.items()
        if value is None
    ]

    if missing:
        raise TenantRegistryError(
            "Mandantenfähigkeit ist aktiviert, aber "
            "folgende Einstellungen fehlen: "
            + ", ".join(missing)
        )

    password = app_settings.control_db_password
    assert password is not None

    return URL.create(
        drivername="mysql+pymysql",
        username=app_settings.control_db_user,
        password=password.get_secret_value(),
        host=app_settings.control_db_host,
        port=app_settings.control_db_port,
        database=app_settings.control_db_name,
    )


def build_tenant_registry(
    app_settings: Settings,
):
    if not app_settings.tenancy_enabled:
        return LegacyTenantRegistry(app_settings)

    encryption_key = (
        app_settings.tenant_db_encryption_key
    )

    if encryption_key is None:
        raise TenantRegistryError(
            "Mandantenfähigkeit ist aktiviert, aber "
            "TENANT_DB_ENCRYPTION_KEY fehlt."
        )

    control_engine = create_engine(
        build_control_database_url(app_settings),
        pool_pre_ping=True,
        pool_recycle=3600,
    )

    return DatabaseTenantRegistry(
        engine=control_engine,
        encryption_key=encryption_key,
        cache_seconds=(
            app_settings
            .tenant_registry_cache_seconds
        ),
    )


tenant_registry = build_tenant_registry(settings)
