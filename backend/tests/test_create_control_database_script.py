import pytest

from scripts.create_control_database import (
    ControlDatabaseCreationError,
    create_control_database,
)


class FakeCursor:
    def __init__(self) -> None:
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(
        self,
        statement: str,
        parameters=None,
    ) -> None:
        self.calls.append((statement, parameters))


class FakeConnection:
    def __init__(self) -> None:
        self.fake_cursor = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.fake_cursor


def test_creates_database_user_and_grants() -> None:
    connection = FakeConnection()

    create_control_database(
        connection,
        database_name="witty_control",
        control_user="witty_control",
        control_password="secret",
        allowed_host="%",
    )

    statements = [
        call[0]
        for call in connection.fake_cursor.calls
    ]

    assert len(statements) == 4
    assert statements[0].startswith(
        "CREATE DATABASE IF NOT EXISTS "
        "`witty_control`"
    )
    assert statements[-1].startswith(
        "GRANT ALL PRIVILEGES ON "
        "`witty_control`.*"
    )
    assert "secret" not in " ".join(statements)


@pytest.mark.parametrize(
    ("database_name", "control_user"),
    [
        ("witty-control", "witty_control"),
        ("witty_control", "witty;root"),
    ],
)
def test_rejects_unsafe_identifiers(
    database_name: str,
    control_user: str,
) -> None:
    with pytest.raises(
        ControlDatabaseCreationError,
    ):
        create_control_database(
            FakeConnection(),
            database_name=database_name,
            control_user=control_user,
            control_password="secret",
            allowed_host="%",
        )
