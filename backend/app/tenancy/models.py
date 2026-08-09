from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class ControlBase(DeclarativeBase):
    pass


ID_TYPE = BigInteger().with_variant(
    Integer,
    "sqlite",
)


class Tenant(ControlBase):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(
        ID_TYPE,
        primary_key=True,
        autoincrement=True,
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    db_host: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    db_port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3306,
    )
    db_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    db_user: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    db_password_encrypted: Mapped[str] = (
        mapped_column(
            String(1000),
            nullable=False,
        )
    )
    archive_namespace: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
    )
    config_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    domains: Mapped[list["TenantDomain"]] = (
        relationship(
            back_populates="tenant",
            cascade="all, delete-orphan",
        )
    )


class TenantDomain(ControlBase):
    __tablename__ = "tenant_domains"

    id: Mapped[int] = mapped_column(
        ID_TYPE,
        primary_key=True,
        autoincrement=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey(
            "tenants.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    hostname: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )
    canonical: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    tenant: Mapped[Tenant] = relationship(
        back_populates="domains",
    )
