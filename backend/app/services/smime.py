from copy import deepcopy
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import (
    hashes,
    serialization,
)
from cryptography.hazmat.primitives.asymmetric import (
    ec,
    rsa,
)
from cryptography.hazmat.primitives.serialization import (
    pkcs12,
    pkcs7,
)
from cryptography.x509.oid import (
    ExtendedKeyUsageOID,
    NameOID,
)


class SmimeSigningError(Exception):
    """Die Nachricht konnte nicht signiert werden."""


OUTER_MESSAGE_HEADERS = (
    "From",
    "To",
    "Cc",
    "Reply-To",
    "Subject",
    "Date",
    "Message-ID",
)


def read_pkcs12_password(
    password_file: Path,
) -> bytes:
    try:
        password = password_file.read_bytes()
    except OSError as exc:
        raise SmimeSigningError(
            "The S/MIME password file could not be read."
        ) from exc

    password = password.rstrip(b"\r\n")

    if not password:
        raise SmimeSigningError(
            "The S/MIME password file is empty."
        )

    return password


def certificate_email_addresses(
    certificate: x509.Certificate,
) -> set[str]:
    addresses = {
        attribute.value.strip().lower()
        for attribute in certificate.subject
        .get_attributes_for_oid(
            NameOID.EMAIL_ADDRESS
        )
        if attribute.value.strip()
    }

    try:
        subject_alternative_name = (
            certificate.extensions
            .get_extension_for_class(
                x509.SubjectAlternativeName
            )
            .value
        )
    except x509.ExtensionNotFound:
        subject_alternative_name = None

    if subject_alternative_name is not None:
        addresses.update(
            address.strip().lower()
            for address in (
                subject_alternative_name
                .get_values_for_type(
                    x509.RFC822Name
                )
            )
            if address.strip()
        )

    return addresses


def validate_signing_material(
    *,
    private_key: object,
    certificate: x509.Certificate,
    sender_email: str,
) -> None:
    if not isinstance(
        private_key,
        (
            rsa.RSAPrivateKey,
            ec.EllipticCurvePrivateKey,
        ),
    ):
        raise SmimeSigningError(
            "The S/MIME private key type is not supported."
        )

    now = datetime.now(timezone.utc)

    if now < certificate.not_valid_before_utc:
        raise SmimeSigningError(
            "The S/MIME certificate is not yet valid."
        )

    if now > certificate.not_valid_after_utc:
        raise SmimeSigningError(
            "The S/MIME certificate has expired."
        )

    normalized_sender = sender_email.strip().lower()

    if (
        normalized_sender
        not in certificate_email_addresses(
            certificate
        )
    ):
        raise SmimeSigningError(
            "The configured sender address does not match the S/MIME "
            "certificate."
        )

    try:
        extended_key_usage = (
            certificate.extensions
            .get_extension_for_class(
                x509.ExtendedKeyUsage
            )
            .value
        )
    except x509.ExtensionNotFound as exc:
        raise SmimeSigningError(
            "The S/MIME certificate lacks the Extended Key Usage "
            "extension."
        ) from exc

    if (
        ExtendedKeyUsageOID.EMAIL_PROTECTION
        not in extended_key_usage
    ):
        raise SmimeSigningError(
            "The certificate is not approved for email protection."
        )

    try:
        key_usage = (
            certificate.extensions
            .get_extension_for_class(
                x509.KeyUsage
            )
            .value
        )
    except x509.ExtensionNotFound as exc:
        raise SmimeSigningError(
            "The S/MIME certificate lacks the Key Usage extension."
        ) from exc

    if not key_usage.digital_signature:
        raise SmimeSigningError(
            "The certificate is not approved for digital signatures."
        )

    private_public_key = (
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=(
                serialization.PublicFormat
                .SubjectPublicKeyInfo
            ),
        )
    )

    certificate_public_key = (
        certificate.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=(
                serialization.PublicFormat
                .SubjectPublicKeyInfo
            ),
        )
    )

    if private_public_key != certificate_public_key:
        raise SmimeSigningError(
            "The private key does not match the S/MIME certificate."
        )


def load_signing_material(
    *,
    pkcs12_path: Path,
    password_file: Path,
    sender_email: str,
) -> tuple[
    object,
    x509.Certificate,
    tuple[x509.Certificate, ...],
]:
    try:
        pkcs12_data = pkcs12_path.read_bytes()
    except OSError as exc:
        raise SmimeSigningError(
            "The S/MIME PKCS#12 file could not be read."
        ) from exc

    password = read_pkcs12_password(
        password_file
    )

    return load_signing_material_from_data(
        pkcs12_data=pkcs12_data,
        password=password,
        sender_email=sender_email,
    )


def load_signing_material_from_data(
    *,
    pkcs12_data: bytes,
    password: bytes,
    sender_email: str,
) -> tuple[
    object,
    x509.Certificate,
    tuple[x509.Certificate, ...],
]:
    if not pkcs12_data:
        raise SmimeSigningError(
            "The S/MIME PKCS#12 file is empty."
        )

    if not password:
        raise SmimeSigningError(
            "The S/MIME password is empty."
        )

    try:
        (
            private_key,
            certificate,
            additional_certificates,
        ) = pkcs12.load_key_and_certificates(
            pkcs12_data,
            password,
        )
    except (
        OSError,
        TypeError,
        ValueError,
        UnsupportedAlgorithm,
    ) as exc:
        raise SmimeSigningError(
            "The S/MIME PKCS#12 file could not be loaded."
        ) from exc

    if private_key is None:
        raise SmimeSigningError(
            "The S/MIME PKCS#12 file contains no private key."
        )

    if certificate is None:
        raise SmimeSigningError(
            "The S/MIME PKCS#12 file contains no sender certificate."
        )

    validate_signing_material(
        private_key=private_key,
        certificate=certificate,
        sender_email=sender_email,
    )

    return (
        private_key,
        certificate,
        tuple(additional_certificates or ()),
    )


def create_signed_content(
    *,
    message: EmailMessage,
    private_key: object,
    certificate: x509.Certificate,
    additional_certificates: tuple[
        x509.Certificate,
        ...,
    ],
) -> bytes:
    content_message = deepcopy(message)

    for header_name in OUTER_MESSAGE_HEADERS:
        if header_name in content_message:
            del content_message[header_name]

    content_bytes = content_message.as_bytes(
        policy=policy.SMTP
    )

    builder = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(content_bytes)
        .add_signer(
            certificate,
            private_key,
            hashes.SHA256(),
        )
    )

    for additional_certificate in (
        additional_certificates
    ):
        builder = builder.add_certificate(
            additional_certificate
        )

    try:
        return builder.sign(
            serialization.Encoding.SMIME,
            [
                pkcs7.PKCS7Options
                .DetachedSignature,
            ],
        )
    except (
        TypeError,
        ValueError,
        UnsupportedAlgorithm,
    ) as exc:
        raise SmimeSigningError(
            "The S/MIME signature could not be created."
        ) from exc


def sign_message(
    *,
    message: EmailMessage,
    sender_email: str,
    pkcs12_path: Path,
    password_file: Path,
) -> bytes:
    (
        private_key,
        certificate,
        additional_certificates,
    ) = load_signing_material(
        pkcs12_path=pkcs12_path,
        password_file=password_file,
        sender_email=sender_email,
    )

    return sign_message_with_material(
        message=message,
        private_key=private_key,
        certificate=certificate,
        additional_certificates=(
            additional_certificates
        ),
    )


def sign_message_from_data(
    *,
    message: EmailMessage,
    sender_email: str,
    pkcs12_data: bytes,
    password: bytes,
) -> bytes:
    (
        private_key,
        certificate,
        additional_certificates,
    ) = load_signing_material_from_data(
        pkcs12_data=pkcs12_data,
        password=password,
        sender_email=sender_email,
    )

    return sign_message_with_material(
        message=message,
        private_key=private_key,
        certificate=certificate,
        additional_certificates=(
            additional_certificates
        ),
    )


def sign_message_with_material(
    *,
    message: EmailMessage,
    private_key: object,
    certificate: x509.Certificate,
    additional_certificates: tuple[
        x509.Certificate,
        ...,
    ],
) -> bytes:
    signed_content = create_signed_content(
        message=message,
        private_key=private_key,
        certificate=certificate,
        additional_certificates=(
            additional_certificates
        ),
    )

    outer_message = EmailMessage(
        policy=policy.SMTP
    )

    for header_name in OUTER_MESSAGE_HEADERS:
        header_value = message.get(header_name)

        if header_value is not None:
            outer_message[header_name] = (
                header_value
            )

    outer_bytes = outer_message.as_bytes(
        policy=policy.SMTP
    )

    header_separator = b"\r\n\r\n"

    if header_separator not in outer_bytes:
        raise SmimeSigningError(
            "The outer mail headers could not be created."
        )

    outer_headers, _, _ = outer_bytes.partition(
        header_separator
    )

    return (
        outer_headers
        + b"\r\n"
        + signed_content
    )
