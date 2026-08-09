from pathlib import Path

import pytest

from app.tenancy.context import TenantContext
from app.tenancy.migrations import (
    migrate_active_tenants,
    upgrade_connection,
)


def make_tenant(
    tenant_id: int,
    slug: str,
) -> TenantContext:
    return TenantContext(
        id=tenant_id,
        slug=slug,
        name=slug,
        db_host="db",
        db_port=3306,
        db_name=f"witty_{slug}",
        db_user=slug,
        db_password="secret",
        archive_namespace=slug,
        canonical_hostname=(
            f"{slug}.witty.example"
        ),
    )


def test_migrates_all_tenants_and_reports_partial_failure() -> None:
    migrated = []

    def migrate(tenant: TenantContext) -> None:
        migrated.append(tenant.slug)

        if tenant.slug == "broken":
            raise RuntimeError("database unavailable")

    results = migrate_active_tenants(
        [
            make_tenant(1, "first"),
            make_tenant(2, "broken"),
            make_tenant(3, "last"),
        ],
        migrate=migrate,
    )

    assert migrated == ["first", "broken", "last"]
    assert [
        result.successful
        for result in results
    ] == [True, False, True]
    assert results[1].error_type == "RuntimeError"


def test_can_migrate_only_one_tenant() -> None:
    migrated = []

    results = migrate_active_tenants(
        [
            make_tenant(1, "first"),
            make_tenant(2, "second"),
        ],
        tenant_slug="second",
        migrate=lambda tenant: migrated.append(
            tenant.slug
        ),
    )

    assert migrated == ["second"]
    assert len(results) == 1
    assert results[0].tenant_slug == "second"


def test_rejects_unknown_tenant_filter() -> None:
    with pytest.raises(
        ValueError,
        match="nicht gefunden",
    ):
        migrate_active_tenants(
            [make_tenant(1, "first")],
            tenant_slug="unknown",
        )


def test_upgrade_uses_supplied_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def upgrade(config, revision):
        calls.append(
            (
                config.attributes["connection"],
                revision,
            )
        )

    monkeypatch.setattr(
        "app.tenancy.migrations.command.upgrade",
        upgrade,
    )
    connection = object()

    upgrade_connection(
        connection,
        config_path=Path("alembic.ini"),
    )

    assert calls == [(connection, "head")]
