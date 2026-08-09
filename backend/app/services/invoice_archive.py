from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models.global_settings import GlobalSettings
from app.models.invoice import Invoice
from app.services.invoice_pdf import build_invoice_pdf
from app.services.invoice_pdfa import (
    InvoicePdfAError,
    PDF_FORMAT_PDFA_2B,
    PDF_FORMAT_STANDARD,
    SUPPORTED_PDF_FORMATS,
    convert_to_pdfa_2b,
)
from app.utils.utc import utc_now


SAFE_INVOICE_NUMBER = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$"
)
SAFE_ARCHIVE_NAMESPACE = re.compile(
    r"^[a-z0-9][a-z0-9_-]{0,99}$"
)


class InvoiceArchiveError(Exception):
    """Base exception for invoice PDF archiving."""


class InvoiceArchiveNotFoundError(
    InvoiceArchiveError
):
    """Raised when the invoice does not exist."""


class InvoiceArchiveMetadataError(
    InvoiceArchiveError
):
    """Raised when archive metadata is incomplete."""


class InvoicePdfIntegrityError(
    InvoiceArchiveError
):
    """Raised when an archived PDF was altered."""


class UnsafeInvoiceNumberError(
    InvoiceArchiveError
):
    """Raised when an invoice number is unsafe."""


@dataclass(frozen=True)
class ArchivedInvoicePdf:
    absolute_path: Path
    relative_path: str
    sha256: str
    size_bytes: int
    created_at: datetime


def calculate_sha256(data: bytes) -> str:
    return sha256(data).hexdigest()


def get_archive_root(
    archive_root: Path | None,
    *,
    db: Session | None = None,
) -> Path:
    configured_root = (
        archive_root
        if archive_root is not None
        else settings.invoice_pdf_archive_dir
    )

    resolved_root = (
        Path(configured_root)
        .expanduser()
        .resolve()
    )

    if archive_root is not None or db is None:
        return resolved_root

    tenant = db.info.get("tenant")

    if tenant is None:
        if settings.tenancy_enabled:
            raise InvoiceArchiveMetadataError(
                "Beim Zugriff auf das "
                "Rechnungsarchiv fehlt der "
                "Mandantenkontext."
            )

        return resolved_root

    namespace = tenant.archive_namespace

    if namespace is None:
        return resolved_root

    if not SAFE_ARCHIVE_NAMESPACE.fullmatch(
        namespace
    ):
        raise InvoiceArchiveMetadataError(
            "Der konfigurierte Mandanten-Pfad für "
            "das Rechnungsarchiv ist ungültig."
        )

    return (resolved_root / namespace).resolve()


def resolve_archive_path(
    archive_root: Path,
    relative_path: str,
) -> Path:
    relative = Path(relative_path)

    if relative.is_absolute() or ".." in relative.parts:
        raise InvoiceArchiveMetadataError(
            "Der gespeicherte PDF-Pfad ist ungültig."
        )

    absolute_path = (
        archive_root / relative
    ).resolve()

    if not absolute_path.is_relative_to(
        archive_root
    ):
        raise InvoiceArchiveMetadataError(
            "Der gespeicherte PDF-Pfad liegt "
            "außerhalb des Archivs."
        )

    return absolute_path


def create_relative_path(
    invoice: Invoice,
) -> str:
    if invoice.issue_date is None:
        raise InvoiceArchiveMetadataError(
            "Das Rechnungsdatum fehlt."
        )

    if not invoice.invoice_number:
        raise InvoiceArchiveMetadataError(
            "Die Rechnungsnummer fehlt."
        )

    if not SAFE_INVOICE_NUMBER.fullmatch(
        invoice.invoice_number
    ):
        raise UnsafeInvoiceNumberError(
            "Die Rechnungsnummer enthält "
            "unzulässige Zeichen."
        )

    return (
        Path(
            str(invoice.issue_date.year),
            f"{invoice.invoice_number}.pdf",
        )
        .as_posix()
    )


def write_atomically(
    target_path: Path,
    data: bytes,
) -> None:
    target_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(
                temporary_file.name
            )

            temporary_file.write(data)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(
            temporary_path,
            target_path,
        )

    except Exception:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

        raise


def verify_archived_file(
    *,
    absolute_path: Path,
    expected_sha256: str,
    expected_size_bytes: int,
) -> None:
    if not absolute_path.is_file():
        raise InvoicePdfIntegrityError(
            "Die archivierte PDF-Datei fehlt."
        )

    data = absolute_path.read_bytes()

    if len(data) != expected_size_bytes:
        raise InvoicePdfIntegrityError(
            "Die Größe der archivierten "
            "PDF-Datei stimmt nicht."
        )

    if calculate_sha256(data) != expected_sha256:
        raise InvoicePdfIntegrityError(
            "Die SHA-256-Prüfsumme der "
            "archivierten PDF-Datei stimmt nicht."
        )


def archived_result(
    invoice: Invoice,
    archive_root: Path,
) -> ArchivedInvoicePdf:
    if (
        invoice.pdf_storage_path is None
        or invoice.pdf_sha256 is None
        or invoice.pdf_size_bytes is None
        or invoice.pdf_created_at is None
    ):
        raise InvoiceArchiveMetadataError(
            "Die PDF-Archivmetadaten sind "
            "unvollständig."
        )

    absolute_path = resolve_archive_path(
        archive_root,
        invoice.pdf_storage_path,
    )

    verify_archived_file(
        absolute_path=absolute_path,
        expected_sha256=invoice.pdf_sha256,
        expected_size_bytes=(
            invoice.pdf_size_bytes
        ),
    )

    return ArchivedInvoicePdf(
        absolute_path=absolute_path,
        relative_path=(
            invoice.pdf_storage_path
        ),
        sha256=invoice.pdf_sha256,
        size_bytes=invoice.pdf_size_bytes,
        created_at=invoice.pdf_created_at,
    )


def archive_invoice_pdf(
    db: Session,
    *,
    invoice_id: int,
    archive_root: Path | None = None,
) -> ArchivedInvoicePdf:
    invoice = db.scalar(
        select(Invoice)
        .options(
            selectinload(Invoice.items),
            selectinload(Invoice.original_invoice),
        )
        .where(Invoice.id == invoice_id)
        .with_for_update()
    )

    if invoice is None:
        raise InvoiceArchiveNotFoundError(
            f"Rechnung {invoice_id} "
            "wurde nicht gefunden."
        )

    resolved_root = get_archive_root(
        archive_root,
        db=db,
    )

    archive_metadata = (
        invoice.pdf_storage_path,
        invoice.pdf_sha256,
        invoice.pdf_size_bytes,
        invoice.pdf_created_at,
    )

    has_any_metadata = any(
        value is not None
        for value in archive_metadata
    )

    has_all_metadata = all(
        value is not None
        for value in archive_metadata
    )

    if has_any_metadata and not has_all_metadata:
        raise InvoiceArchiveMetadataError(
            "Die PDF-Archivmetadaten sind "
            "nur teilweise gesetzt."
        )

    if has_all_metadata:
        return archived_result(
            invoice,
            resolved_root,
        )

    global_settings = db.get(
        GlobalSettings,
        1,
    )
    pdf_format = (
        global_settings.invoice_pdf_format
        if global_settings is not None
        else PDF_FORMAT_STANDARD
    )

    if pdf_format not in SUPPORTED_PDF_FORMATS:
        raise InvoiceArchiveMetadataError(
            "Das konfigurierte Rechnungsformat ist "
            "ungültig."
        )

    pdf_bytes = build_invoice_pdf(invoice)

    if pdf_format == PDF_FORMAT_PDFA_2B:
        try:
            pdf_bytes = convert_to_pdfa_2b(
                pdf_bytes
            )
        except InvoicePdfAError as exc:
            raise InvoiceArchiveError(
                str(exc)
            ) from exc
    pdf_sha256 = calculate_sha256(pdf_bytes)
    pdf_size_bytes = len(pdf_bytes)

    relative_path = create_relative_path(
        invoice
    )
    absolute_path = resolve_archive_path(
        resolved_root,
        relative_path,
    )

    created_new_file = False

    if absolute_path.exists():
        existing_data = (
            absolute_path.read_bytes()
        )

        if (
            len(existing_data) != pdf_size_bytes
            or calculate_sha256(existing_data)
            != pdf_sha256
        ):
            raise InvoicePdfIntegrityError(
                "Am vorgesehenen Archivpfad "
                "existiert bereits eine andere Datei."
            )
    else:
        write_atomically(
            absolute_path,
            pdf_bytes,
        )
        created_new_file = True

    created_at = utc_now()

    invoice.pdf_storage_path = relative_path
    invoice.pdf_sha256 = pdf_sha256
    invoice.pdf_size_bytes = pdf_size_bytes
    invoice.pdf_created_at = created_at

    try:
        db.commit()
    except Exception:
        db.rollback()

        if (
            created_new_file
            and absolute_path.exists()
        ):
            absolute_path.unlink()

        raise

    db.refresh(invoice)

    return ArchivedInvoicePdf(
        absolute_path=absolute_path,
        relative_path=relative_path,
        sha256=pdf_sha256,
        size_bytes=pdf_size_bytes,
        created_at=created_at,
    )


def get_archived_invoice_pdf(
    db: Session,
    *,
    invoice_id: int,
    archive_root: Path | None = None,
) -> ArchivedInvoicePdf:
    invoice = db.get(
        Invoice,
        invoice_id,
    )

    if invoice is None:
        raise InvoiceArchiveNotFoundError(
            f"Rechnung {invoice_id} "
            "wurde nicht gefunden."
        )

    return archived_result(
        invoice,
        get_archive_root(
            archive_root,
            db=db,
        ),
    )
