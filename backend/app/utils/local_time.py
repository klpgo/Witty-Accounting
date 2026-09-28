from datetime import datetime
from zoneinfo import ZoneInfo


from app.config import settings

# Zeitzone der Instanz (Umgebungsvariable TZ, Standard Europe/Berlin)
TIMEZONE_NAME = settings.timezone
LOCAL_TIMEZONE = ZoneInfo(TIMEZONE_NAME)


def local_now() -> datetime:
    """
    Liefert die aktuelle lokale Zeit ohne tzinfo.

    Die importierten Hager-Zeitstempel werden ebenfalls
    als lokale, naive DATETIME-Werte gespeichert.
    """
    return datetime.now(
        LOCAL_TIMEZONE
    ).replace(tzinfo=None)
