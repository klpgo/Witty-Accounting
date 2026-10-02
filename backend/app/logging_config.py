import logging
import os
from pathlib import Path


NOISY_HTTP_LOGGERS = ("httpx", "httpcore")


def setup_logging() -> None:
    log_dir = Path(
        os.getenv(
            "LOG_DIR",
            Path.cwd() / "logs",
        )
    )

    log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_file = log_dir / "witty-accounting.log"

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s: "
            "%(message)s"
        ),
        handlers=[
            logging.FileHandler(
                log_file,
                encoding="utf-8",
            ),
            logging.StreamHandler(),
        ],
    )

    # httpx protokolliert auf INFO jede Anfrage mit vollständiger URL –
    # beim Hager-Login stünden damit Anmeldeparameter (OAuth-Code,
    # Session-Codes, SAML-Anfrage) im Log. Witty protokolliert die
    # relevanten Schritte selbst, nur mit Host und Pfad.
    for noisy_logger in NOISY_HTTP_LOGGERS:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
