import argparse
from getpass import getpass
import re

import pymysql


SAFE_IDENTIFIER = re.compile(
    r"^[A-Za-z0-9_]{1,64}$"
)


class ControlDatabaseCreationError(RuntimeError):
    """The control database could not be created safely."""


def validate_identifier(
    value: str,
    *,
    field_name: str,
) -> str:
    if not SAFE_IDENTIFIER.fullmatch(value):
        raise ControlDatabaseCreationError(
            f"{field_name} may only contain letters, digits and "
            "underscores."
        )

    return value


def create_control_database(
    connection,
    *,
    database_name: str,
    control_user: str,
    control_password: str,
    allowed_host: str,
) -> None:
    database_name = validate_identifier(
        database_name,
        field_name="Database name",
    )
    control_user = validate_identifier(
        control_user,
        field_name="Database user",
    )

    if not control_password:
        raise ControlDatabaseCreationError(
            "The password of the control database user must not be empty."
        )

    if not allowed_host or any(
        character in allowed_host
        for character in "'\"`\\"
    ):
        raise ControlDatabaseCreationError(
            "The allowed database host is invalid."
        )

    quoted_database = f"`{database_name}`"

    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE DATABASE IF NOT EXISTS "
            f"{quoted_database} "
            "CHARACTER SET utf8mb4 "
            "COLLATE utf8mb4_unicode_ci"
        )
        cursor.execute(
            "CREATE USER IF NOT EXISTS %s@%s "
            "IDENTIFIED BY %s",
            (
                control_user,
                allowed_host,
                control_password,
            ),
        )
        cursor.execute(
            "ALTER USER %s@%s IDENTIFIED BY %s",
            (
                control_user,
                allowed_host,
                control_password,
            ),
        )
        cursor.execute(
            "GRANT ALL PRIVILEGES ON "
            f"{quoted_database}.* TO %s@%s",
            (control_user, allowed_host),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Creates the central Witty control database and its "
            "restricted MariaDB user."
        )
    )
    parser.add_argument(
        "--admin-host",
        default="db",
    )
    parser.add_argument(
        "--admin-port",
        type=int,
        default=3306,
    )
    parser.add_argument(
        "--admin-user",
        default="root",
    )
    parser.add_argument(
        "--database-name",
        default="witty_control",
    )
    parser.add_argument(
        "--control-user",
        default="witty_control",
    )
    parser.add_argument(
        "--allowed-host",
        default="%",
        help=(
            "MariaDB host part of the control user."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.admin_port < 1 or args.admin_port > 65535:
        raise SystemExit(
            "The MariaDB admin port is invalid."
        )

    admin_password = getpass(
        "MariaDB admin password: "
    )
    control_password = getpass(
        "New password for the control database: "
    )
    confirmation = getpass(
        "Repeat the password for the control database: "
    )

    if control_password != confirmation:
        raise SystemExit(
            "The passwords do not match."
        )

    try:
        connection = pymysql.connect(
            host=args.admin_host,
            port=args.admin_port,
            user=args.admin_user,
            password=admin_password,
            autocommit=True,
        )
    except pymysql.MySQLError as exc:
        raise SystemExit(
            "The connection as MariaDB administrator failed."
        ) from exc

    try:
        create_control_database(
            connection,
            database_name=args.database_name,
            control_user=args.control_user,
            control_password=control_password,
            allowed_host=args.allowed_host,
        )
    except ControlDatabaseCreationError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        connection.close()

    print()
    print(
        f"Control database {args.database_name} has been prepared."
    )
    print(
        "Now enter the same control database password as "
        "CONTROL_DB_PASSWORD in .env."
    )


if __name__ == "__main__":
    main()
