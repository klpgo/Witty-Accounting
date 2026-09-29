"""
Gemeinsame Test-Konfiguration.

Die Zeitzone der Anwendung kommt aus der Umgebungsvariable TZ. Die Tests
erwarten deutsche Ortszeit und müssen unabhängig davon laufen, in welcher
Zeitzone sie gestartet werden (z. B. `TZ=UTC pytest`). Deshalb wird TZ
hier fest vorgegeben – bevor die Anwendung importiert wird.
"""
import os
import time

os.environ["TZ"] = "Europe/Berlin"

if hasattr(time, "tzset"):
    time.tzset()


import pytest


@pytest.fixture(autouse=True)
def isolated_invoice_archive(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Jeder Test bekommt ein eigenes, leeres Rechnungsarchiv. So kann kein
    Test in ein echtes Archiv schreiben oder mit Dateien früherer Tests
    kollidieren. Tests, die das Archiv selbst umleiten, überschreiben das.
    """
    from app.config import settings

    monkeypatch.setattr(
        settings,
        "invoice_pdf_archive_dir",
        tmp_path_factory.mktemp("invoices"),
    )
