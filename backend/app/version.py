from importlib.metadata import (
    PackageNotFoundError,
    version,
)


try:
    BACKEND_VERSION = version(
        "witty-accounting"
    )
except PackageNotFoundError:
    BACKEND_VERSION = "0.1.0"
