"""
Sperre für Importe: pro Mandanten-Datenbank läuft immer nur ein Import
gleichzeitig (automatischer Abruf, manueller Abruf, Datei-Import).

Zwei gleichzeitige Importe könnten sonst dieselben Ladevorgänge einfügen
wollen oder sich beim Fortschreiben des Abrufstands in global_settings
gegenseitig blockieren. Witty läuft mit einem Prozess; eine Sperre im
Arbeitsspeicher genügt deshalb.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


DEFAULT_TIMEOUT_SECONDS = 300.0

_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


class ImportBusyError(RuntimeError):
    """Ein anderer Import dieses Mandanten läuft noch."""


def lock_key(db: Session) -> str:
    """Schlüssel der Mandanten-Datenbank (Treiber, Host, Port, Name)."""
    get_bind = getattr(db, "get_bind", None)

    if get_bind is None:
        return "default"

    bind = get_bind()
    url = getattr(bind, "url", None)

    # SQLite im Arbeitsspeicher (Tests): jede Engine ist eine eigene Datenbank
    if url is None or url.database in (None, "", ":memory:"):
        return f"engine-{id(bind)}"

    return url.render_as_string(hide_password=True)


@contextmanager
def import_lock(
    db: Session,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Iterator[None]:
    key = lock_key(db)

    with _guard:
        lock = _locks.setdefault(key, threading.Lock())

    if not lock.acquire(timeout=timeout):
        raise ImportBusyError(
            "Ein anderer Import läuft noch. Bitte in einigen Minuten "
            "erneut versuchen."
        )

    try:
        yield
    finally:
        lock.release()
