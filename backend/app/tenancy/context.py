from dataclasses import dataclass, field

from sqlalchemy.engine import URL


@dataclass(frozen=True)
class TenantContext:
    """Resolved tenant configuration for one unit of work."""

    id: int
    slug: str
    name: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str = field(repr=False)
    archive_namespace: str | None = None
    canonical_hostname: str | None = None
    config_version: int = 1

    def database_url(self) -> URL:
        return URL.create(
            drivername="mysql+pymysql",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    def connection_fingerprint(
        self,
    ) -> tuple[object, ...]:
        return (
            self.config_version,
            self.db_host,
            self.db_port,
            self.db_name,
            self.db_user,
            self.db_password,
        )
