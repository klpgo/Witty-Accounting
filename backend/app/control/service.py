from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import re
import secrets
import shutil
import time
from typing import Callable, Iterator

import pymysql
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.tenancy.context import TenantContext
from app.tenancy.migrations import migrate_tenant_database
from app.tenancy.models import Tenant, TenantDomain
from app.tenancy.registry import TenantRegistryError, normalize_hostname
from app.control.i18n import tr
from scripts.create_admin import create_first_admin_with_values
from scripts.register_tenant import register_tenant


SAFE_TENANT_CODE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
PROVISION_LOCK_NAME = "witty-control-tenant-provision"
DeletionProgress = Callable[[str, str], None]


class TenantControlError(RuntimeError):
    """A tenant lifecycle operation could not be completed safely."""


@dataclass(frozen=True)
class TenantCreateData:
    code: str
    name: str
    hostname: str
    admin_email: str
    admin_first_name: str
    admin_last_name: str
    admin_password: str


def validate_tenant_code(value: str) -> str:
    code = value.strip().lower()

    if not SAFE_TENANT_CODE.fullmatch(code):
        raise TenantControlError(
            tr("tenant.codeInvalid")
        )

    return code


def tenant_database_user(code: str) -> str:
    return f"witty_{validate_tenant_code(code)}"


class TenantControlService:
    def __init__(
        self,
        *,
        settings: Settings,
        control_engine: Engine,
        sleep=time.sleep,
    ) -> None:
        self.settings = settings
        self.control_engine = control_engine
        self._sleep = sleep

    def list_tenants(self) -> list[dict[str, object]]:
        with Session(self.control_engine) as db:
            tenants = db.scalars(
                select(Tenant)
                .options(selectinload(Tenant.domains))
                .order_by(Tenant.slug)
            ).all()

            return [
                {
                    "id": tenant.id,
                    "code": tenant.slug,
                    "name": tenant.name,
                    "active": tenant.active,
                    "hostname": next(
                        (
                            domain.hostname
                            for domain in tenant.domains
                            if domain.canonical
                        ),
                        "",
                    ),
                    "db_name": tenant.db_name,
                    "archive_namespace": tenant.archive_namespace,
                }
                for tenant in tenants
            ]

    def create_tenant(self, data: TenantCreateData) -> dict[str, object]:
        code = validate_tenant_code(data.code)
        hostname = normalize_hostname(data.hostname)
        name = data.name.strip()

        if not name:
            raise TenantControlError(tr("tenant.nameEmpty"))

        db_user = tenant_database_user(code)
        db_password = secrets.token_urlsafe(36)
        archive_path = self._archive_path(code)

        self._ensure_control_values_are_free(code, hostname)

        if archive_path.exists():
            raise TenantControlError(
                tr("tenant.archiveExists")
            )

        admin_connection = self._connect_admin()
        database_created = False
        user_created = False
        archive_created = False

        try:
            with self._provision_lock(admin_connection):
                self._ensure_database_values_are_free(
                    admin_connection,
                    database_name=code,
                    database_user=db_user,
                )
                self._create_database_and_user(
                    admin_connection,
                    database_name=code,
                    database_user=db_user,
                    database_password=db_password,
                )
                database_created = True
                user_created = True

                candidate = self._tenant_context(
                    code=code,
                    name=name,
                    hostname=hostname,
                    database_user=db_user,
                    database_password=db_password,
                )
                migrate_tenant_database(candidate)
                self._create_first_admin(candidate, data)

                archive_path.mkdir(parents=True, exist_ok=False)
                archive_created = True

                with Session(self.control_engine) as db:
                    tenant = register_tenant(
                        db,
                        slug=code,
                        name=name,
                        hostname=hostname,
                        db_host=candidate.db_host,
                        db_port=candidate.db_port,
                        db_name=code,
                        db_user=db_user,
                        db_password=db_password,
                        encryption_key=self._encryption_key(),
                    )
                    tenant_id = tenant.id
        except Exception as exc:
            if archive_created:
                shutil.rmtree(archive_path)
            if database_created or user_created:
                self._drop_database_and_user(
                    admin_connection,
                    database_name=code,
                    database_user=db_user,
                )
            if isinstance(exc, TenantControlError):
                raise
            raise TenantControlError(
                tr("tenant.createFailed", error=exc)
            ) from exc
        finally:
            admin_connection.close()

        return {
            "id": tenant_id,
            "code": code,
            "name": name,
            "hostname": hostname,
            "db_name": code,
        }

    def set_active(self, tenant_id: int, *, active: bool) -> None:
        with Session(self.control_engine) as db:
            tenant = db.get(Tenant, tenant_id)

            if tenant is None:
                raise TenantControlError(tr("tenant.notFound"))

            tenant.active = active
            tenant.config_version += 1
            db.commit()

    def set_name(self, tenant_id: int, *, name: str) -> None:
        normalized_name = name.strip()

        if not normalized_name:
            raise TenantControlError(tr("tenant.nameEmpty"))
        if len(normalized_name) > 200:
            raise TenantControlError(
                tr("tenant.nameTooLong")
            )

        with Session(self.control_engine) as db:
            tenant = db.get(Tenant, tenant_id)

            if tenant is None:
                raise TenantControlError(tr("tenant.notFound"))

            tenant.name = normalized_name
            tenant.config_version += 1
            db.commit()

    def set_hostname(self, tenant_id: int, *, hostname: str) -> None:
        try:
            normalized_hostname = normalize_hostname(hostname)
        except TenantRegistryError as exc:
            raise TenantControlError(str(exc)) from exc

        with Session(self.control_engine) as db:
            tenant = db.scalar(
                select(Tenant)
                .options(selectinload(Tenant.domains))
                .where(Tenant.id == tenant_id)
            )

            if tenant is None:
                raise TenantControlError(tr("tenant.notFound"))

            canonical_domain = next(
                (
                    domain
                    for domain in tenant.domains
                    if domain.canonical
                ),
                None,
            )
            if canonical_domain is None:
                raise TenantControlError(
                    tr("tenant.noCanonicalDomain")
                )

            if canonical_domain.hostname == normalized_hostname:
                return

            conflict = db.scalar(
                select(TenantDomain.id).where(
                    TenantDomain.hostname == normalized_hostname,
                    TenantDomain.id != canonical_domain.id,
                )
            )
            if conflict is not None:
                raise TenantControlError(
                    tr("tenant.hostnameTaken")
                )

            canonical_domain.hostname = normalized_hostname
            tenant.config_version += 1
            db.commit()

    def delete_tenant(
        self,
        tenant_id: int,
        *,
        confirmation: str,
        progress: DeletionProgress | None = None,
    ) -> None:
        report = progress or (lambda _step, _message: None)

        with Session(self.control_engine) as db:
            tenant = db.get(Tenant, tenant_id)

            if tenant is None:
                raise TenantControlError(tr("tenant.notFound"))

            code = validate_tenant_code(tenant.slug)

            if not secrets.compare_digest(
                confirmation.strip().encode("utf-8"),
                code.encode("utf-8"),
            ):
                raise TenantControlError(
                    tr("delete.confirmationMismatch")
                )

            database_name, database_user = self._deletion_database_values(
                db,
                tenant=tenant,
                code=code,
            )
            report("validated", tr("delete.checked"))

            tenant.active = False
            tenant.config_version += 1
            db.commit()
            report("blocked", tr("delete.locked"))

        # The application backend is a separate process and can still hold a
        # registry entry until its configured TTL expires. Wait before the
        # destructive steps so new requests can no longer reach the tenant.
        if self.settings.tenant_registry_cache_seconds > 0:
            report(
                "waiting",
                tr("delete.waitForCache"),
            )
            self._sleep(self.settings.tenant_registry_cache_seconds + 1)

        admin_connection = self._connect_admin()

        try:
            with self._provision_lock(admin_connection):
                report(
                    "database",
                    tr("delete.dropDatabase", database=database_name),
                )
                self._drop_database_and_user(
                    admin_connection,
                    database_name=database_name,
                    database_user=database_user,
                )
                report(
                    "database_done",
                    tr("delete.databaseDropped"),
                )
                archive_path = self._archive_path(code)
                if archive_path.exists():
                    report("archive", tr("delete.removeArchive"))
                    shutil.rmtree(archive_path)
                    report("archive_done", tr("delete.archiveRemoved"))
                else:
                    report(
                        "archive_done",
                        tr("delete.noArchive"),
                    )
        except Exception as exc:
            raise TenantControlError(
                tr("delete.incomplete", error=exc)
            ) from exc
        finally:
            admin_connection.close()

        report("registry", tr("delete.removeRegistration"))
        with Session(self.control_engine) as db:
            tenant = db.get(Tenant, tenant_id)
            if tenant is not None:
                db.delete(tenant)
                db.commit()
        report("complete", tr("delete.complete"))

    def _deletion_database_values(
        self,
        db: Session,
        *,
        tenant: Tenant,
        code: str,
    ) -> tuple[str, str]:
        database_name = tenant.db_name
        database_user = tenant.db_user

        if tenant.archive_namespace != code:
            raise TenantControlError(
                tr("delete.namespaceMismatch")
            )

        regular_values = (
            database_name == code
            and database_user == tenant_database_user(code)
        )
        bootstrap_values = (
            tenant.db_host == self.settings.db_host
            and tenant.db_port == self.settings.db_port
            and database_name == self.settings.db_name
            and database_user == self.settings.db_user
        )

        if not regular_values and not bootstrap_values:
            raise TenantControlError(
                tr("delete.databaseMismatch")
            )

        database_name = validate_tenant_code(database_name)
        protected_databases = {
            "information_schema",
            "mysql",
            "performance_schema",
            "sys",
        }
        if self.settings.control_db_name:
            protected_databases.add(self.settings.control_db_name)

        protected_users = {self.settings.tenant_provision_db_user}
        if self.settings.control_db_user:
            protected_users.add(self.settings.control_db_user)

        if (
            database_name in protected_databases
            or database_user in protected_users
        ):
            raise TenantControlError(
                tr("delete.databaseProtected")
            )

        shared_registration = db.scalar(
            select(Tenant.id).where(
                Tenant.id != tenant.id,
                (Tenant.db_name == database_name)
                | (Tenant.db_user == database_user),
            )
        )
        if shared_registration is not None:
            raise TenantControlError(
                tr("delete.databaseShared")
            )

        return database_name, database_user

    def _ensure_control_values_are_free(self, code: str, hostname: str) -> None:
        with Session(self.control_engine) as db:
            conflict = db.scalar(
                select(Tenant.id).where(
                    (Tenant.slug == code)
                    | (Tenant.db_name == code)
                    | (Tenant.archive_namespace == code)
                )
            )
            if conflict is not None:
                raise TenantControlError(
                    tr("tenant.alreadyRegistered")
                )

            domain_conflict = db.scalar(
                select(TenantDomain.id).where(TenantDomain.hostname == hostname)
            )
            if domain_conflict is not None:
                raise TenantControlError(tr("tenant.hostnameTaken"))

    def _connect_admin(self):
        password = self.settings.tenant_provision_db_password
        if password is None:
            raise TenantControlError(tr("tenant.provisionPasswordMissing"))

        try:
            return pymysql.connect(
                host=(
                    self.settings.tenant_provision_db_host
                    or self.settings.db_host
                ),
                port=(
                    self.settings.tenant_provision_db_port
                    or self.settings.db_port
                ),
                user=self.settings.tenant_provision_db_user,
                password=password.get_secret_value(),
                autocommit=True,
            )
        except pymysql.MySQLError as exc:
            raise TenantControlError(
                tr("tenant.provisionConnectionFailed")
            ) from exc

    @contextmanager
    def _provision_lock(self, connection) -> Iterator[None]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 10)", (PROVISION_LOCK_NAME,))
            if cursor.fetchone()[0] != 1:
                raise TenantControlError(
                    tr("tenant.operationRunning")
                )
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (PROVISION_LOCK_NAME,))

    def _ensure_database_values_are_free(
        self, connection, *, database_name: str, database_user: str
    ) -> None:
        allowed_host = self.settings.tenant_provision_db_allowed_host
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
                "WHERE SCHEMA_NAME = %s",
                (database_name,),
            )
            if cursor.fetchone() is not None:
                raise TenantControlError(tr("tenant.databaseExists"))

            cursor.execute(
                "SELECT User FROM mysql.user WHERE User = %s AND Host = %s",
                (database_user, allowed_host),
            )
            if cursor.fetchone() is not None:
                raise TenantControlError(
                    tr("tenant.databaseUserExists")
                )

    def _create_database_and_user(
        self,
        connection,
        *,
        database_name: str,
        database_user: str,
        database_password: str,
    ) -> None:
        quoted_database = f"`{validate_tenant_code(database_name)}`"
        allowed_host = self.settings.tenant_provision_db_allowed_host
        database_created = False
        user_created = False
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE {quoted_database} CHARACTER SET utf8mb4 "
                    "COLLATE utf8mb4_unicode_ci"
                )
                database_created = True
                cursor.execute(
                    "CREATE USER %s@%s IDENTIFIED BY %s",
                    (database_user, allowed_host, database_password),
                )
                user_created = True
                cursor.execute(
                    f"GRANT ALL PRIVILEGES ON {quoted_database}.* TO %s@%s",
                    (database_user, allowed_host),
                )
        except Exception:
            with connection.cursor() as cursor:
                if user_created:
                    cursor.execute(
                        "DROP USER IF EXISTS %s@%s",
                        (database_user, allowed_host),
                    )
                if database_created:
                    cursor.execute(f"DROP DATABASE IF EXISTS {quoted_database}")
            raise

    def _drop_database_and_user(
        self, connection, *, database_name: str, database_user: str
    ) -> None:
        quoted_database = f"`{validate_tenant_code(database_name)}`"
        allowed_host = self.settings.tenant_provision_db_allowed_host
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS {quoted_database}")
            cursor.execute(
                "DROP USER IF EXISTS %s@%s",
                (database_user, allowed_host),
            )

    def _tenant_context(
        self,
        *,
        code: str,
        name: str,
        hostname: str,
        database_user: str,
        database_password: str,
    ) -> TenantContext:
        return TenantContext(
            id=0,
            slug=code,
            name=name,
            db_host=(
                self.settings.tenant_provision_db_host or self.settings.db_host
            ),
            db_port=(
                self.settings.tenant_provision_db_port or self.settings.db_port
            ),
            db_name=code,
            db_user=database_user,
            db_password=database_password,
            archive_namespace=code,
            canonical_hostname=hostname,
        )

    def _create_first_admin(
        self, tenant: TenantContext, data: TenantCreateData
    ) -> None:
        tenant_engine = create_engine(
            tenant.database_url(),
            pool_pre_ping=True,
            poolclass=NullPool,
        )
        try:
            with Session(tenant_engine) as db:
                create_first_admin_with_values(
                    db,
                    email=data.admin_email,
                    first_name=data.admin_first_name,
                    last_name=data.admin_last_name,
                    password=data.admin_password,
                )
        finally:
            tenant_engine.dispose()

    def _encryption_key(self) -> SecretStr:
        key = self.settings.tenant_db_encryption_key
        if key is None:
            raise TenantControlError(tr("tenant.encryptionKeyMissing"))
        return key

    def _archive_path(self, code: str) -> Path:
        root = self.settings.invoice_pdf_archive_dir.resolve()
        path = (root / validate_tenant_code(code)).resolve()

        if path.parent != root:
            raise TenantControlError(tr("tenant.archivePathInvalid"))

        return path
