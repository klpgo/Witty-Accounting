import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging():

    os.makedirs(
        "/app/logs",
        exist_ok=True
    )

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


    file_handler = RotatingFileHandler(
        "/app/logs/backend.log",
        maxBytes=10_000_000,
        backupCount=5
    )

    file_handler.setFormatter(formatter)


    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)


    root = logging.getLogger()

    root.setLevel(logging.INFO)

    root.addHandler(file_handler)
    root.addHandler(console_handler)
