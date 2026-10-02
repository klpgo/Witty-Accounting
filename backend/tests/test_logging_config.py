import logging
from pathlib import Path

import pytest

from app.logging_config import NOISY_HTTP_LOGGERS, setup_logging


def test_http_client_request_logging_is_suppressed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    previous = {
        name: logging.getLogger(name).level
        for name in NOISY_HTTP_LOGGERS
    }
    monkeypatch.setenv("LOG_DIR", str(tmp_path))

    try:
        setup_logging()

        for name in NOISY_HTTP_LOGGERS:
            http_logger = logging.getLogger(name)
            # keine INFO-Zeilen mit vollständigen URLs
            assert not http_logger.isEnabledFor(logging.INFO)
            assert http_logger.isEnabledFor(logging.WARNING)
    finally:
        for name, level in previous.items():
            logging.getLogger(name).setLevel(level)
