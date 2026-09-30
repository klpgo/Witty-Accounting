import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.import_lock import ImportBusyError, import_lock, lock_key


def memory_session() -> Session:
    return Session(create_engine("sqlite+pysqlite:///:memory:"))


def test_second_import_waits_and_gives_up_after_timeout() -> None:
    db = memory_session()
    acquired = threading.Event()
    release = threading.Event()

    def first_import() -> None:
        with import_lock(db):
            acquired.set()
            release.wait(5)

    worker = threading.Thread(target=first_import)
    worker.start()
    acquired.wait(5)

    with pytest.raises(ImportBusyError, match="Another import"):
        with import_lock(db, timeout=0.1):
            pass

    release.set()
    worker.join(5)

    # nach dem Ende des ersten Imports ist die Sperre wieder frei
    with import_lock(db, timeout=0.1):
        pass


def test_lock_is_released_after_error() -> None:
    db = memory_session()

    with pytest.raises(RuntimeError):
        with import_lock(db):
            raise RuntimeError("Import fehlgeschlagen")

    with import_lock(db, timeout=0.1):
        pass


def test_separate_databases_do_not_block_each_other() -> None:
    first, second = memory_session(), memory_session()

    assert lock_key(first) != lock_key(second)

    with import_lock(first):
        with import_lock(second, timeout=0.1):
            pass


def test_same_database_url_shares_the_lock() -> None:
    engine_a = create_engine("mysql+pymysql://u:geheim@db:3306/witty_wb42")
    engine_b = create_engine("mysql+pymysql://u:geheim@db:3306/witty_wb42")

    key = lock_key(Session(engine_a))

    assert key == lock_key(Session(engine_b))
    assert "geheim" not in key


def test_placeholder_without_database_gets_default_key() -> None:
    assert lock_key(object()) == "default"
