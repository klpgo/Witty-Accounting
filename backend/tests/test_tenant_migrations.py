from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.tenancy.context import TenantContext
from app.tenancy.migrations import (
    APPLICATION_ALEMBIC_CONFIG,
    CONTROL_ALEMBIC_CONFIG,
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


def test_girocode_migration_defaults_off_and_preserves_existing_settings() -> None:
    engine = create_engine("sqlite+pysqlite://")
    config = Config(str(APPLICATION_ALEMBIC_CONFIG))

    try:
        with engine.connect() as connection:
            connection.execute(text(
                "CREATE TABLE global_settings "
                "(id INTEGER PRIMARY KEY, app_name VARCHAR(255) NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO global_settings VALUES (1, 'Existing installation')"
            ))
            connection.commit()
            config.attributes["connection"] = connection
            command.stamp(config, "9c8a7b6d5e4f")

            upgrade_connection(
                connection,
                config_path=APPLICATION_ALEMBIC_CONFIG,
                revision="d71c9a4e6b20",
            )
            assert connection.execute(text(
                "SELECT app_name, invoice_girocode_enabled "
                "FROM global_settings WHERE id = 1"
            )).one() == ("Existing installation", 0)
            columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("global_settings")
            }
            assert not columns["invoice_girocode_enabled"]["nullable"]

            connection.execute(text(
                "INSERT INTO global_settings (id, app_name) VALUES (2, 'New row')"
            ))
            assert connection.scalar(text(
                "SELECT invoice_girocode_enabled FROM global_settings WHERE id = 2"
            )) == 0
            connection.commit()

            command.downgrade(config, "9c8a7b6d5e4f")
            assert "invoice_girocode_enabled" not in {
                column["name"]
                for column in inspect(connection).get_columns("global_settings")
            }
            assert connection.scalar(text(
                "SELECT app_name FROM global_settings WHERE id = 1"
            )) == "Existing installation"
    finally:
        engine.dispose()


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


def test_control_migration_backfills_archive_namespace(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "control.sqlite"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}"
    )

    try:
        with engine.connect() as connection:
            upgrade_connection(
                connection,
                config_path=CONTROL_ALEMBIC_CONFIG,
                revision="6f3ce20d8f51",
            )
            connection.execute(
                text(
                    "INSERT INTO tenants ("
                    "id, slug, name, active, db_host, "
                    "db_port, db_name, db_user, "
                    "db_password_encrypted, "
                    "archive_namespace, config_version"
                    ") VALUES ("
                    "1, 'wb42', 'WB42', 1, 'db', 3306, "
                    "'witty', 'witty', 'encrypted', "
                    "NULL, 1)"
                )
            )
            connection.commit()

            upgrade_connection(
                connection,
                config_path=CONTROL_ALEMBIC_CONFIG,
            )

            namespace = connection.scalar(
                text(
                    "SELECT archive_namespace "
                    "FROM tenants WHERE slug = 'wb42'"
                )
            )
            columns = {
                column["name"]: column
                for column in inspect(
                    connection
                ).get_columns("tenants")
            }

        assert namespace == "wb42"
        assert not columns[
            "archive_namespace"
        ]["nullable"]
    finally:
        engine.dispose()
