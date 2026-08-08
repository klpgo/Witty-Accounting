from datetime import datetime
from zoneinfo import ZoneInfo


LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")


def local_now() -> datetime:
    """
    Liefert die aktuelle lokale Zeit ohne tzinfo.

    Die importierten Hager-Zeitstempel werden ebenfalls
    als lokale, naive DATETIME-Werte gespeichert.
    """
    return datetime.now(
        LOCAL_TIMEZONE
    ).replace(tzinfo=None)
