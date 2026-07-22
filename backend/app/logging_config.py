import logging
import os
from pathlib import Path


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
