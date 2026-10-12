from dataclasses import dataclass
from datetime import datetime
import errno
from pathlib import Path, PurePosixPath
import stat
from uuid import uuid4

import paramiko
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.global_settings import GlobalSettings
from app.models.invoice import Invoice
from app.services.invoice_archive import (
    InvoiceArchiveError,
    get_archived_invoice_pdf,
)
from app.utils.utc import utc_now


class InvoiceExportError(Exception):
    """Base exception for SFTP invoice export."""


class InvoiceExportConfigurationError(
    InvoiceExportError
):
    """Raised when SFTP export is not configured."""


class InvoiceExportConnectionError(
    InvoiceExportError
):
    """Raised when the SFTP server cannot be used."""


class InvoiceExportNotFoundError(
    InvoiceExportError
):
    """Raised when the invoice does not exist."""


class InvoiceExportStateError(
    InvoiceExportError
):
    """Raised when an invoice cannot be exported."""


class InvoiceExportAlreadyExistsError(
    InvoiceExportError
):
    """Raised when the remote PDF already exists."""


@dataclass(frozen=True)
class SftpInvoiceExportConfiguration:
    host: str
    port: int
    username: str
    directory: str
    private_key_path: Path
    known_hosts_path: Path
    timeout_seconds: float


@dataclass(frozen=True)
class InvoiceExportResult:
    remote_path: str
    exported_at: datetime


def invoice_export_secret_status() -> tuple[
    bool,
    bool,
]:
    return (
        settings
        .invoice_export_sftp_private_key_path
        .expanduser()
        .is_file(),
        settings
        .invoice_export_sftp_known_hosts_path
        .expanduser()
        .is_file(),
    )


def get_sftp_configuration(
    db: Session,
) -> SftpInvoiceExportConfiguration:
    global_settings = db.get(GlobalSettings, 1)

    if global_settings is None:
        raise InvoiceExportConfigurationError(
            "The global settings were not found."
        )

    if not global_settings.invoice_export_sftp_enabled:
        raise InvoiceExportConfigurationError(
            "The SFTP invoice export is not enabled."
        )

    required_values = {
        "SFTP host": (
            global_settings.invoice_export_sftp_host
        ),
        "SFTP user": (
            global_settings
            .invoice_export_sftp_username
        ),
        "SFTP target directory": (
            global_settings
            .invoice_export_sftp_directory
        ),
    }
    missing = [
        name
        for name, value in required_values.items()
        if value is None or not value.strip()
    ]

    if missing:
        raise InvoiceExportConfigurationError(
            "The SFTP settings are incomplete: "
            + ", ".join(missing)
        )

    private_key_path = (
        settings
        .invoice_export_sftp_private_key_path
        .expanduser()
        .resolve()
    )
    known_hosts_path = (
        settings
        .invoice_export_sftp_known_hosts_path
        .expanduser()
        .resolve()
    )

    if not private_key_path.is_file():
        raise InvoiceExportConfigurationError(
            "The private key for the SFTP export is not set up."
        )

    if not known_hosts_path.is_file():
        raise InvoiceExportConfigurationError(
            "The known_hosts file for the SFTP export is not set up."
        )

    return SftpInvoiceExportConfiguration(
        host=str(required_values["SFTP host"]),
        port=(
            global_settings.invoice_export_sftp_port
        ),
        username=str(
            required_values["SFTP user"]
        ),
        directory=str(
            required_values[
                "SFTP target directory"
            ]
        ),
        private_key_path=private_key_path,
        known_hosts_path=known_hosts_path,
        timeout_seconds=(
            settings
            .invoice_export_sftp_timeout_seconds
        ),
    )


def open_sftp_connection(
    configuration: SftpInvoiceExportConfiguration,
) -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
    ssh_client = paramiko.SSHClient()

    try:
        ssh_client.load_host_keys(
            str(configuration.known_hosts_path)
        )
        ssh_client.set_missing_host_key_policy(
            paramiko.RejectPolicy()
        )
        ssh_client.connect(
            hostname=configuration.host,
            port=configuration.port,
            username=configuration.username,
            key_filename=str(
                configuration.private_key_path
            ),
            timeout=configuration.timeout_seconds,
            banner_timeout=(
                configuration.timeout_seconds
            ),
            auth_timeout=(
                configuration.timeout_seconds
            ),
            allow_agent=False,
            look_for_keys=False,
        )
        return ssh_client, ssh_client.open_sftp()
    except Exception as exc:
        ssh_client.close()
        raise InvoiceExportConnectionError(
            "The SFTP connection could not be established. Please check "
            "host, key and known_hosts."
        ) from exc


def _remote_path_exists(
    sftp: paramiko.SFTPClient,
    path: str,
) -> bool:
    try:
        sftp.stat(path)
        return True
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return False
        raise


def _require_remote_directory(
    sftp: paramiko.SFTPClient,
    path: str,
) -> None:
    try:
        attributes = sftp.stat(path)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            raise InvoiceExportConfigurationError(
                "The configured SFTP target directory does not exist."
            ) from exc
        raise

    if not stat.S_ISDIR(attributes.st_mode or 0):
        raise InvoiceExportConfigurationError(
            "The configured SFTP target path is not a directory."
        )


def _ensure_year_directory(
    sftp: paramiko.SFTPClient,
    path: str,
) -> None:
    if _remote_path_exists(sftp, path):
        _require_remote_directory(sftp, path)
        return

    try:
        sftp.mkdir(path)
    except OSError as exc:
        raise InvoiceExportConnectionError(
            "The year directory could not be created on the SFTP server."
        ) from exc


def test_sftp_connection(
    db: Session,
) -> SftpInvoiceExportConfiguration:
    configuration = get_sftp_configuration(db)
    ssh_client: paramiko.SSHClient | None = None
    sftp: paramiko.SFTPClient | None = None

    try:
        ssh_client, sftp = open_sftp_connection(
            configuration
        )
        _require_remote_directory(
            sftp,
            configuration.directory,
        )
        return configuration
    except InvoiceExportError:
        raise
    except Exception as exc:
        raise InvoiceExportConnectionError(
            "The SFTP target directory could not be read."
        ) from exc
    finally:
        if sftp is not None:
            sftp.close()
        if ssh_client is not None:
            ssh_client.close()


def export_invoice_pdf(
    db: Session,
    *,
    invoice_id: int,
    admin_user_id: int | None,
) -> InvoiceExportResult:
    invoice = db.scalar(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .with_for_update()
    )

    if invoice is None:
        raise InvoiceExportNotFoundError(
            f"Invoice {invoice_id} was not found."
        )

    if invoice.status != "finalized":
        raise InvoiceExportStateError(
            "Only finalized invoices can be exported."
        )

    if (
        invoice.invoice_number is None
        or invoice.issue_date is None
    ):
        raise InvoiceExportStateError(
            "Invoice number or invoice date is missing."
        )

    try:
        archived_pdf = get_archived_invoice_pdf(
            db,
            invoice_id=invoice.id,
        )
    except InvoiceArchiveError as exc:
        raise InvoiceExportStateError(str(exc)) from exc

    configuration = get_sftp_configuration(db)
    year_directory = str(
        PurePosixPath(configuration.directory)
        / str(invoice.issue_date.year)
    )
    remote_path = str(
        PurePosixPath(year_directory)
        / f"{invoice.invoice_number}.pdf"
    )
    temporary_path = (
        f"{remote_path}.part-{uuid4().hex}"
    )

    ssh_client: paramiko.SSHClient | None = None
    sftp: paramiko.SFTPClient | None = None
    uploaded = False

    try:
        ssh_client, sftp = open_sftp_connection(
            configuration
        )
        _require_remote_directory(
            sftp,
            configuration.directory,
        )
        _ensure_year_directory(
            sftp,
            year_directory,
        )

        if _remote_path_exists(sftp, remote_path):
            raise InvoiceExportAlreadyExistsError(
                "The invoice already exists in the SFTP target directory and "
                "was not overwritten."
            )

        with archived_pdf.absolute_path.open(
            "rb"
        ) as source:
            attributes = sftp.putfo(
                source,
                temporary_path,
                file_size=archived_pdf.size_bytes,
                confirm=True,
            )

        if attributes.st_size != archived_pdf.size_bytes:
            raise InvoiceExportConnectionError(
                "The transferred PDF has an unexpected size on the SFTP "
                "server."
            )

        sftp.rename(temporary_path, remote_path)
        uploaded = True

        exported_at = utc_now()
        invoice.pdf_exported_at = exported_at
        invoice.pdf_exported_by_user_id = (
            admin_user_id
        )
        invoice.pdf_export_remote_path = remote_path

        try:
            db.commit()
        except Exception:
            db.rollback()

            try:
                sftp.remove(remote_path)
                uploaded = False
            except Exception:
                pass

            raise

        return InvoiceExportResult(
            remote_path=remote_path,
            exported_at=exported_at,
        )
    except InvoiceExportError:
        raise
    except Exception as exc:
        raise InvoiceExportConnectionError(
            "The PDF invoice could not be exported via SFTP."
        ) from exc
    finally:
        if sftp is not None:
            if not uploaded:
                try:
                    if _remote_path_exists(
                        sftp,
                        temporary_path,
                    ):
                        sftp.remove(temporary_path)
                except Exception:
                    pass
            sftp.close()
        if ssh_client is not None:
            ssh_client.close()
