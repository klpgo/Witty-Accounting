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
    status,
)
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.schemas.import_result import ImportResult
from app.services.importers.xlsx_importer import import_xlsx_to_db
from app.services.importers.hager_json_importer import (
    import_json_to_db,
)
from app.schemas.hager_settings import HagerImportRequest
from app.services.hager_sync import (
    HagerConfigurationError,
    HagerConnectionError,
    import_from_hager,
)
from app.services.smtp_secret import SmtpSecretError

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
    file_label: str = "XLSX-Datei",
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
                    f"Die {file_label} ist zu groß. "
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

        return build_import_result(
            db,
            import_result,
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


def build_import_result(
    db: Session,
    import_result: dict[str, object],
) -> ImportResult:
    pricing_result = price_charging_sessions(
        db=db,
        overwrite=False,
        import_hashes=set(
            import_result["imported_hashes"]
        ),
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
        unknown_rfid_cards=list(
            import_result.get("unknown_rfid_cards", [])
        ),
        inactive_rfid_cards=list(
            import_result.get("inactive_rfid_cards", [])
        ),
        unassigned_rfid_numbers=list(
            import_result.get("unassigned_rfid_numbers", [])
        ),
        backfilled_rfid_numbers=int(
            import_result.get("backfilled_rfid_numbers", 0)
        ),
        reassigned_sessions=int(
            import_result.get("reassigned_sessions", 0)
        ),
        fetched_from=import_result.get("fetched_from"),
    )


@router.post(
    "/json",
    response_model=ImportResult,
    dependencies=[Depends(require_admin)],
)
def upload_json(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImportResult:
    """Importiert Hager-Ladevorgänge aus einer JSON-Datei
    (Ausgabe von hager-fetch oder Antwort der Hager-API)."""
    filename = file.filename or ""

    if Path(filename).suffix.lower() != ".json":
        raise HTTPException(
            status_code=400,
            detail=(
                "Es werden ausschließlich "
                "JSON-Dateien unterstützt."
            ),
        )

    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            suffix=".json",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(
                temporary_file.name
            )

            uploaded_size = save_upload_with_limit(
                file=file,
                destination=temporary_file,
                file_label="JSON-Datei",
            )

        if uploaded_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Die hochgeladene Datei ist leer.",
            )

        return build_import_result(
            db,
            import_json_to_db(
                db=db,
                path=temporary_path,
            ),
        )

    except HTTPException:
        raise

    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Die JSON-Datei konnte nicht "
                f"importiert werden: {exc}"
            ),
        ) from exc

    finally:
        file.file.close()

        if temporary_path is not None:
            temporary_path.unlink(
                missing_ok=True,
            )


@router.post(
    "/hager",
    response_model=ImportResult,
    dependencies=[Depends(require_admin)],
)
def import_hager(
    request: HagerImportRequest | None = None,
    db: Session = Depends(get_db),
) -> ImportResult:
    """Ruft Ladevorgänge direkt aus Hager flow ab und importiert
    sie. Ohne Zeitraum ab dem Cut-off (letzter erfolgreicher Abruf
    minus 3 Tage), mit fetch_all vollständig."""
    request = request or HagerImportRequest()

    try:
        import_result = import_from_hager(
            db,
            date_from=request.date_from,
            date_to=request.date_to,
            fetch_all=request.fetch_all,
        )
    except HagerConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except HagerConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except SmtpSecretError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Die Daten aus Hager flow konnten nicht "
                f"importiert werden: {exc}"
            ),
        ) from exc

    return build_import_result(db, import_result)
