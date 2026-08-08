from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile
from app.services.pricing import price_charging_sessions

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.schemas.import_result import ImportResult
from app.services.importers.xlsx_importer import import_xlsx_to_db

from app.auth import require_admin


MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024


router = APIRouter(
    prefix="/imports",
    tags=["imports"],
)


def save_upload_with_limit(
    file: UploadFile,
    destination,
) -> int:
    """
    Speichert einen Upload blockweise und bricht bei Überschreitung
    des Größenlimits ab.
    """
    total_size = 0

    while True:
        chunk = file.file.read(
            UPLOAD_CHUNK_SIZE_BYTES
        )

        if not chunk:
            break

        total_size += len(chunk)

        if total_size > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Die XLSX-Datei ist zu groß. "
                    "Maximal erlaubt sind 10 MB."
                ),
            )

        destination.write(chunk)

    return total_size


@router.post(
    "/xlsx",
    response_model=ImportResult,
    dependencies=[Depends(require_admin)],
)


def upload_xlsx(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImportResult:
    filename = file.filename or ""

    if Path(filename).suffix.lower() != ".xlsx":
        raise HTTPException(
            status_code=400,
            detail=(
                "Es werden ausschließlich "
                "XLSX-Dateien unterstützt."
            ),
        )

    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            suffix=".xlsx",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(
                temporary_file.name
            )

            uploaded_size = save_upload_with_limit(
                file=file,
                destination=temporary_file,
            )

        if uploaded_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Die hochgeladene Datei ist leer.",
            )

        import_result = import_xlsx_to_db(
            db=db,
            path=temporary_path,
        )

        imported_hashes = set(
            import_result["imported_hashes"]
        )

        pricing_result = price_charging_sessions(
            db=db,
            overwrite=False,
            import_hashes=imported_hashes,
        )

        return ImportResult(
            read=int(import_result["read"]),
            imported=int(import_result["imported"]),
            skipped=int(import_result["skipped"]),
            unknown_rfid_sessions=int(
                import_result["unknown_rfid_sessions"]
            ),
            unknown_rfid_numbers=list(
                import_result["unknown_rfid_numbers"]
            ),
            priced=pricing_result["priced"],
            missing_price=pricing_result["missing_price"],
            invalid_energy=pricing_result["invalid_energy"],
        )

    except HTTPException:
        raise

    except (
        BadZipFile,
        InvalidFileException,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Die XLSX-Datei konnte nicht "
                f"importiert werden: {exc}"
            ),
        ) from exc

    finally:
        file.file.close()

        if temporary_path is not None:
            temporary_path.unlink(
                missing_ok=True,
            )
