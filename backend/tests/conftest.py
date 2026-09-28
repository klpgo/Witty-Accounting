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
