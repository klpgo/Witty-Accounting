from io import BytesIO
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from pypdf import PdfReader

from app.config import settings


PDF_FORMAT_STANDARD = "standard"
PDF_FORMAT_PDFA_2B = "pdfa-2b"
SUPPORTED_PDF_FORMATS = {
    PDF_FORMAT_STANDARD,
    PDF_FORMAT_PDFA_2B,
}


class InvoicePdfAError(Exception):
    """Raised when PDF/A-2b creation fails."""


def validate_pdfa_2b_structure(
    pdf_bytes: bytes,
) -> None:
    """Check the PDF/A markers produced by Ghostscript.

    Ghostscript enforces PDF/A compatibility while writing. This
    additional check prevents a conversion result without the required
    output intent or PDF/A-2b XMP declaration from being archived.
    """

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        root = reader.trailer["/Root"]

        output_intents = root.get("/OutputIntents")

        if not output_intents:
            raise InvoicePdfAError(
                "Der PDF/A-Ausgabefarbraum fehlt."
            )

        output_intent = output_intents[0].get_object()

        if (
            output_intent.get("/S") != "/GTS_PDFA1"
            or output_intent.get(
                "/DestOutputProfile"
            )
            is None
        ):
            raise InvoicePdfAError(
                "Der PDF/A-Ausgabefarbraum ist ungültig."
            )

        metadata = root.get("/Metadata")

        if metadata is None:
            raise InvoicePdfAError(
                "Die PDF/A-Metadaten fehlen."
            )

        xmp = metadata.get_object().get_data()

        has_part_2 = (
            b"pdfaid:part='2'" in xmp
            or b'pdfaid:part="2"' in xmp
        )
        has_conformance_b = (
            b"pdfaid:conformance='B'" in xmp
            or b'pdfaid:conformance="B"' in xmp
        )

        if not has_part_2 or not has_conformance_b:
            raise InvoicePdfAError(
                "Die PDF/A-2b-Kennzeichnung fehlt."
            )

    except InvoicePdfAError:
        raise
    except Exception as exc:
        raise InvoicePdfAError(
            "Die erzeugte PDF/A-Datei konnte nicht "
            "geprüft werden."
        ) from exc


def convert_to_pdfa_2b(
    pdf_bytes: bytes,
) -> bytes:
    if not pdf_bytes.startswith(b"%PDF-"):
        raise InvoicePdfAError(
            "Das Ausgangsdokument ist keine PDF-Datei."
        )

    executable = shutil.which(
        settings.ghostscript_executable
    )

    if executable is None:
        raise InvoicePdfAError(
            "Ghostscript wurde nicht gefunden."
        )

    icc_profile = Path(
        settings.pdfa_icc_profile_path
    ).expanduser()

    if not icc_profile.is_file():
        raise InvoicePdfAError(
            "Das sRGB-Farbprofil für PDF/A wurde "
            "nicht gefunden."
        )

    with TemporaryDirectory(
        prefix="witty-pdfa-"
    ) as temporary_directory:
        directory = Path(temporary_directory)
        source_path = directory / "source.pdf"
        target_path = directory / "invoice-pdfa.pdf"
        local_profile = directory / "srgb.icc"

        source_path.write_bytes(pdf_bytes)
        shutil.copyfile(
            icc_profile,
            local_profile,
        )

        command = [
            executable,
            "-dPDFA=2",
            "-dBATCH",
            "-dNOPAUSE",
            "-dSAFER",
            "-dPDFSTOPONERROR",
            "-sDEVICE=pdfwrite",
            "-dPDFACompatibilityPolicy=1",
            "-sColorConversionStrategy=RGB",
            "-sProcessColorModel=DeviceRGB",
            "-dEmbedAllFonts=true",
            "-dSubsetFonts=true",
            "--permit-file-read=srgb.icc",
            f"-sOutputFile={target_path}",
            "PDFA_def.ps",
            str(source_path),
        ]

        try:
            result = subprocess.run(
                command,
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=(
                    settings
                    .pdfa_conversion_timeout_seconds
                ),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise InvoicePdfAError(
                "Die PDF/A-Erzeugung hat das "
                "Zeitlimit überschritten."
            ) from exc
        except OSError as exc:
            raise InvoicePdfAError(
                "Ghostscript konnte nicht gestartet "
                "werden."
            ) from exc

        if result.returncode != 0:
            detail = (
                result.stderr.strip()
                or result.stdout.strip()
                or "unbekannter Fehler"
            )
            raise InvoicePdfAError(
                "Die PDF/A-Erzeugung ist "
                f"fehlgeschlagen: {detail}"
            )

        if not target_path.is_file():
            raise InvoicePdfAError(
                "Ghostscript hat keine PDF/A-Datei "
                "erzeugt."
            )

        converted_pdf = target_path.read_bytes()

    validate_pdfa_2b_structure(converted_pdf)

    return converted_pdf
