from datetime import date, datetime
from decimal import Decimal
import errno
from hashlib import sha256
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models.global_settings import GlobalSettings
from app.models.invoice import Invoice
from app.services import invoice_export
from app.services.invoice_export import (
    InvoiceExportAlreadyExistsError,
    InvoiceExportStateError,
    export_invoice_pdf,
)


class FakeSSHClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSFTPClient:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.directories = {"/exports"}
        self.closed = False

    def stat(self, path: str):
        if path in self.directories:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o755,
                st_size=0,
            )

        if path in self.files:
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o644,
                st_size=len(self.files[path]),
            )

        raise OSError(errno.ENOENT, "not found")

    def mkdir(self, path: str) -> None:
        self.directories.add(path)

    def putfo(
        self,
        source,
        remote_path: str,
        *,
        file_size: int,
        confirm: bool,
    ):
        assert confirm is True
        data = source.read()
        assert len(data) == file_size
        self.files[remote_path] = data
        return SimpleNamespace(st_size=len(data))

    def rename(
        self,
        source: str,
        destination: str,
    ) -> None:
        if destination in self.files:
            raise OSError(errno.EEXIST, "exists")
        self.files[destination] = self.files.pop(
            source
        )

    def remove(self, path: str) -> None:
        del self.files[path]

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def database_session():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        yield db

    Base.metadata.drop_all(engine)
    engine.dispose()


def configure_export(
    db: Session,
    *,
    private_key: Path,
    known_hosts: Path,
) -> None:
    private_key.write_text("private-key")
    known_hosts.write_text("known-host")

    settings.invoice_export_sftp_private_key_path = (
        private_key
    )
    settings.invoice_export_sftp_known_hosts_path = (
        known_hosts
    )

    db.add(
        GlobalSettings(
            id=1,
            invoice_export_sftp_enabled=True,
            invoice_export_sftp_host=(
                "sftp.example.test"
            ),
            invoice_export_sftp_port=22,
            invoice_export_sftp_username="export",
            invoice_export_sftp_directory=(
                "/exports"
            ),
        )
    )
    db.commit()


def create_invoice_with_archive(
    db: Session,
    archive_root: Path,
    *,
    status: str = "finalized",
) -> tuple[Invoice, bytes]:
    data = b"%PDF-1.7\ninvoice-export-test"
    archive_path = (
        archive_root / "2026" / "RE-2026-000001.pdf"
    )
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(data)

    invoice = Invoice(
        invoice_number=(
            "RE-2026-000001"
            if status == "finalized"
            else None
        ),
        document_type="invoice",
        user_id=1,
        issuer_name="Witty GmbH",
        issuer_address="Testweg 1",
        recipient_name="Test Empfänger",
        recipient_address="Musterweg 2",
        status=status,
        issue_date=(
            date(2026, 8, 16)
            if status == "finalized"
            else None
        ),
        due_date=date(2026, 8, 30),
        service_period_start=datetime(2026, 7, 1),
        service_period_end=datetime(2026, 8, 1),
        currency="EUR",
        total_net=Decimal("10.00"),
        vat_amount=Decimal("1.90"),
        total_gross=Decimal("11.90"),
        finalized_at=(
            datetime(2026, 8, 16, 10, 0)
            if status == "finalized"
            else None
        ),
        pdf_storage_path="2026/RE-2026-000001.pdf",
        pdf_sha256=sha256(data).hexdigest(),
        pdf_size_bytes=len(data),
        pdf_created_at=datetime(2026, 8, 16, 10, 1),
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice, data


def test_exports_archived_pdf_atomically_and_records_audit(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(
        settings,
        "invoice_pdf_archive_dir",
        archive_root,
    )
    configure_export(
        database_session,
        private_key=tmp_path / "key",
        known_hosts=tmp_path / "known-hosts",
    )
    invoice, pdf_data = create_invoice_with_archive(
        database_session,
        archive_root,
    )
    fake_ssh = FakeSSHClient()
    fake_sftp = FakeSFTPClient()
    monkeypatch.setattr(
        invoice_export,
        "open_sftp_connection",
        lambda configuration: (fake_ssh, fake_sftp),
    )

    result = export_invoice_pdf(
        database_session,
        invoice_id=invoice.id,
        admin_user_id=99,
    )

    remote_path = (
        "/exports/2026/RE-2026-000001.pdf"
    )
    assert result.remote_path == remote_path
    assert fake_sftp.files == {
        remote_path: pdf_data,
    }
    assert fake_ssh.closed is True
    assert fake_sftp.closed is True

    database_session.refresh(invoice)
    assert invoice.pdf_exported_at == result.exported_at
    assert invoice.pdf_exported_by_user_id == 99
    assert invoice.pdf_export_remote_path == remote_path


def test_does_not_overwrite_existing_remote_invoice(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(
        settings,
        "invoice_pdf_archive_dir",
        archive_root,
    )
    configure_export(
        database_session,
        private_key=tmp_path / "key",
        known_hosts=tmp_path / "known-hosts",
    )
    invoice, _ = create_invoice_with_archive(
        database_session,
        archive_root,
    )
    fake_sftp = FakeSFTPClient()
    remote_path = (
        "/exports/2026/RE-2026-000001.pdf"
    )
    fake_sftp.directories.add("/exports/2026")
    fake_sftp.files[remote_path] = b"existing"
    monkeypatch.setattr(
        invoice_export,
        "open_sftp_connection",
        lambda configuration: (
            FakeSSHClient(),
            fake_sftp,
        ),
    )

    with pytest.raises(
        InvoiceExportAlreadyExistsError
    ):
        export_invoice_pdf(
            database_session,
            invoice_id=invoice.id,
            admin_user_id=99,
        )

    assert fake_sftp.files[remote_path] == b"existing"


def test_rejects_invoice_draft_before_connecting(
    database_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(
        settings,
        "invoice_pdf_archive_dir",
        archive_root,
    )
    configure_export(
        database_session,
        private_key=tmp_path / "key",
        known_hosts=tmp_path / "known-hosts",
    )
    invoice, _ = create_invoice_with_archive(
        database_session,
        archive_root,
        status="draft",
    )

    with pytest.raises(InvoiceExportStateError):
        export_invoice_pdf(
            database_session,
            invoice_id=invoice.id,
            admin_user_id=99,
        )
