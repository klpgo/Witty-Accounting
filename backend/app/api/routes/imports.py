from pathlib import Path
from shutil import copyfileobj
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.schemas.import_result import ImportResult
from app.services.importers.xlsx_importer import import_xlsx_to_db


router = APIRouter(
    prefix="/imports",
    tags=["imports"],
)


@router.post(
    "/xlsx",
    response_model=ImportResult,
)
def upload_xlsx(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImportResult:
    filename = file.filename or ""

    if Path(filename).suffix.lower() != ".xlsx":
        raise HTTPException(
            status_code=400,
            detail="Es werden ausschließlich XLSX-Dateien unterstützt.",
        )

    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            suffix=".xlsx",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            copyfileobj(
                file.file,
                temporary_file,
            )

        result = import_xlsx_to_db(
            db=db,
            path=temporary_path,
        )

        return ImportResult(**result)

    except (
        InvalidFileException,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Die XLSX-Datei konnte nicht importiert werden: {exc}",
        ) from exc

    finally:
        file.file.close()

        if temporary_path is not None:
            temporary_path.unlink(
                missing_ok=True,
            )
