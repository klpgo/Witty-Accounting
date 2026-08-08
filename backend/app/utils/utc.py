from datetime import UTC, datetime


def utc_now() -> datetime:
    """
    Liefert die aktuelle UTC-Zeit ohne tzinfo.

    MariaDB DATETIME speichert keine Zeitzoneninformation.
    """
    return datetime.now(UTC).replace(tzinfo=None)
