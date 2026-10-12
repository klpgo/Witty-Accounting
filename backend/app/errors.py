"""Fehlercodes für Meldungen an die Oberfläche.

Das Backend formuliert seine Fehlermeldungen auf Englisch (für Logs, Tests
und API-Clients). Damit die Oberfläche sie in der Sprache des Benutzers
anzeigen kann, ordnet dieses Modul jeder Meldung einen Code mit Parametern
zu. Die Antwort enthält dann zusätzlich zu ``detail``:

    {"detail": "Invoice 12 was not found.",
     "code": "invoice.notFound", "params": {"id": "12"}}

Die Oberfläche holt den Text zum Code aus ihren Sprachdateien
(``apiError.<code>`` in ``frontend/src/i18n/de.ts`` und ``en.ts``).

Neue Fehlermeldungen brauchen einen Eintrag in ``ERROR_MESSAGES`` und in
beiden Sprachdateien; ``tests/test_error_codes.py`` prüft das.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

# Code -> englische Vorlage. Platzhalter {name} werden zu Parametern.
ERROR_MESSAGES: dict[str, str] = {
    # Anmeldung, Mandant, Rechte
    "tenant.locked": "This tenant is locked.",
    "tenant.unknown": "Unknown tenant.",
    "auth.invalidCredentials": "Email address or password is incorrect.",
    "auth.maintenance": "Maintenance mode is active. Only administrators can sign in at the moment.",
    "auth.linkInvalid": "The link is invalid, has expired or has already been used.",
    "auth.credentialsNotValidated": "Credentials could not be validated.",
    "auth.adminRequired": "Administrator rights required.",
    "auth.jwtSecretTooShort": "JWT_SECRET_KEY is shorter than 32 bytes.",
    "auth.tokenTenantMissing": "The tenant context is missing when creating a token.",
    "auth.emailInvalid": "The email address is invalid.",
    "auth.notAuthenticated": "Not authenticated",

    # Allgemeine Fehler des Frameworks
    "http.notFound": "Not Found",
    "http.methodNotAllowed": "Method Not Allowed",
    "http.internalServerError": "Internal Server Error",

    # Globale Einstellungen
    "settings.notFound": "The global settings were not found.",
    "settings.currencyLocked": "The currency can no longer be changed because invoices already exist.",
    "settings.girocodeEuroOnly": "The Girocode is only possible with the currency EUR. Please disable the Girocode or choose EUR.",
    "settings.vatSwitchBlocked": "VAT can only be switched on or off while no invoice or cancellation drafts exist. Please finalize or delete the open drafts first.",
    "settings.issuerEmailRequired": "The email address of the invoice issuer is required while automatic billing is enabled.",
    "settings.issuerEmailInvalid": "The email address of the invoice issuer is not valid.",
    "settings.valueNull": "The setting value must not be null.",
    "settings.appNameEmpty": "The application name must not be empty.",
    "settings.frontendUrlInvalid": "The public frontend address must be a complete HTTP or HTTPS URL without credentials, parameters or fragment.",

    # Automatische Abrechnung
    "autoBilling.needsIssuerEmail": "Automatic billing needs the email address of the invoice issuer (Settings, invoice issuer).",
    "autoBilling.draftNotFound": "Invoice draft {id} was not found.",
    "autoBilling.inquiryNotPossible": "A question about this draft is no longer possible.",
    "autoBilling.noRecipientEmail": "No recipient email address is available.",
    "autoBilling.noCustomerEmail": "No email address is stored for the customer.",
    "autoBilling.noNotificationAddress": "No notification address is configured for automatic billing.",
    "autoBilling.interval": "The interval must be weekly, monthly or quarterly.",
    "autoBilling.weeklyCutoffDay": "For weekly billing the cutoff day must be a weekday between 1 (Monday) and 7 (Sunday).",
    "autoBilling.monthlyCutoffDay": "The cutoff day must be between 1 and 28, or 0 for the last day of the month.",

    # Energietarife
    "energyPrice.noCurrent": "There is no currently valid energy tariff yet.",
    "energyPrice.severalToday": "Several energy tariffs exist for today.",
    "energyPrice.duplicateDate": "A tariff already exists for this validity date.",
    "energyPrice.notFound": "Energy tariff {id} was not found.",
    "energyPrice.todayConflict": "Today's energy tariff could not be saved because of a database conflict.",
    "energyPrice.createConflict": "The tariff could not be created because of a database conflict.",
    "energyPrice.updateConflict": "The tariff could not be changed because of a database conflict.",
    "energyPrice.beforeBoundary": "Energy prices can only be set from {boundary} onwards, because invoices exist up to this date.",

    # Hager-Einstellungen
    "hager.autoFetchIncomplete": "For automatic fetching, username, password, installation ID and serial number must be saved.",
    "hager.installationIdDigits": "The installation ID may only contain digits.",
    "hager.serialNumberDigits": "The serial number may only contain digits.",
    "hager.fullFetchNoPeriod": "No period can be specified for a full fetch.",
    "hager.startAfterEnd": "The start date is after the end date.",
    "hager.noFetchTime": "No fetch time found.",
    "hager.timeFormat": "The start time must be given in the format HH:MM.",
    "hager.intervalHours": "The interval must be between 1 and 24 hours.",
    "hager.emptyPassword": "An empty Hager password cannot be encrypted.",
    "hager.passwordDecrypt": "The saved Hager password could not be decrypted.",
    "hager.notReachable": "Hager Cloud is not reachable: {error}",

    # Hager-Client
    "hagerClient.tooManyPages": "More than {pages} pages – aborting.",
    "hagerClient.credentialsRequired": "Email and password are required.",
    "hagerClient.noTokens": "The sign-in returned no tokens – the flow may have changed.",
    "hagerClient.tokenRenewalFailed": "Token renewal failed (HTTP {status}).",
    "hagerClient.tokenRenewalNoTokens": "The token renewal returned no tokens.",
    "hagerClient.unexpectedFormat": "E-Mobility-API: unerwartetes Antwortformat.",
    "hagerClient.columnLengths": "E-Mobility API: columns of different length ({lengths}).",
    "hagerClient.wallboxListHttp": "Wallbox-Liste: HTTP {status}",
    "hagerClient.signInPageUnreachable": "Sign-in page not reachable (HTTP {status}).",
    "hagerClient.noSamlResponse": "No SAML response at {url} (HTTP {status}).\n      {page}",
    "hagerClient.noSignInForm": "No sign-in form found at {url}.",
    "hagerClient.signInRejected": "Sign-in rejected – please check email and password.",
    "hagerClient.pageHttp": "E-Mobility API page {page}: HTTP {status}",

    # Importe
    "import.onlyXlsx": "Only XLSX files are supported.",
    "import.onlyJson": "Only JSON files are supported.",
    "import.fileTooLarge": "The {type} file is too large. The maximum is 10 MB.",
    "import.fileEmpty": "The uploaded file is empty.",
    "import.xlsxFailed": "The XLSX file could not be imported: {error}",
    "import.jsonFailed": "The JSON file could not be imported: {error}",
    "import.hagerFailed": "The data from the Hager Cloud could not be imported: {error}",
    "import.locked": "Another import is still running. Please try again in a few minutes.",

    # JSON-Import
    "importJson.stationMissing": "charging station missing",
    "importJson.invalidEntries": "The JSON file contains invalid session entries.",
    "importJson.fieldMissing": "{field} missing",
    "importJson.sessionFieldMissing": "field 'session' missing",
    "importJson.sessionIdMissing": "session ID missing",
    "importJson.endBeforeStart": "end time is before the start time",
    "importJson.sessionIdKeyMissing": "sessionID missing",
    "importJson.wallboxIdMissing": "wallboxID missing",
    "importJson.fileNotFound": "JSON file not found: {path}",
    "importJson.invalidTimestamp": "Invalid timestamp in {field}: {value}",
    "importJson.invalidNumber": "Invalid numeric value in {field}: {value}",
    "importJson.invalidJson": "The file is not valid JSON: {error}",
    "importJson.unknownFormat": "Unknown JSON format: expected the output of hager-fetch or a response of the Hager API.",
    "importJson.chargingSessionError": "Error in charging session {index}: {error}",
    "importJson.sessionError": "Error in session {index}: {error}",

    # XLSX-Import
    "importXlsx.noHeader": "The XLSX file has no header row",
    "importXlsx.durationMissing": "duration missing",
    "importXlsx.invalidDuration": "Invalid duration format: {duration}",
    "importXlsx.startDateMissing": "start date missing",
    "importXlsx.fileNotFound": "XLSX file not found: {path}",
    "importXlsx.notAFile": "The given path is not a file: {path}",
    "importXlsx.tooFewColumns": "XLSX row {row} contains only {count} instead of 9 columns",
    "importXlsx.rowError": "Error in XLSX row {row}: {error}",

    # Rechnungen (Routen)
    "invoice.notFound": "Invoice {id} was not found.",
    "invoice.onlyDraftDeletable": "Only a draft can be deleted.",
    "invoice.draftPdfOnlyDrafts": "Only invoice drafts can be shown as a draft PDF.",
    "invoice.finalizedArchiveFailed": "The invoice was finalized, but PDF archiving failed: {error}",
    "invoice.noArchivedPdf": "No PDF has been archived for this invoice yet.",
    "invoice.cancellationArchiveFailed": "The cancellation was finalized, but PDF archiving failed: {error}",

    # RFID-Karten
    "rfid.cardNotFound": "RFID card {id} was not found.",
    "rfid.assignmentNotFound": "RFID assignment {id} was not found.",
    "rfid.numberInUse": "This RFID number is already in use.",
    "rfid.endBeforeStart": "The end of the assignment must be after its start.",
    "rfid.userLocked": "The user of an RFID assignment that is already in use cannot be changed.",
    "rfid.startLocked": "The start of an RFID assignment that has already been billed cannot be changed.",
    "rfid.periodExcludesSessions": "The new period no longer contains all related charging sessions.",
    "rfid.assignmentConflict": "The RFID assignment could not be changed because of a data conflict.",
    "rfid.numberEmpty": "The RFID number must not be empty.",
    "rfid.activeEmpty": "The active status must not be empty.",
    "rfid.userEmpty": "The user must not be empty.",
    "rfid.startEmpty": "The start of the assignment must not be empty.",
    "rfid.severalAssignments": "Several user assignments apply to RFID card {number} at {at}.",
    "rfid.overlap": "The assignment period overlaps with an existing assignment of this RFID card.",

    # Benutzer
    "user.notFound": "User {id} was not found.",
    "user.deliveryMethod": "Please choose exactly one invoice delivery method: email, post or manual portal download.",
    "user.emailInUse": "This email address is already in use.",
    "user.currentPasswordWrong": "The current password is incorrect.",
    "user.invitationFailed": "The user could not be created because the invitation email could not be sent.",
    "user.valueEmpty": "The value must not be empty.",
    "user.emailEmpty": "The email address must not be empty.",
    "password.requirements": "The password must contain {requirements}.",
    "password.minLength": "at least {count} characters",
    "password.uppercase": "an uppercase letter",
    "password.lowercase": "a lowercase letter",
    "password.digit": "a digit",
    "password.special": "a special character",
    "password.resetSmimeFailed": "The email could not be signed with S/MIME.",

    # Wallboxen
    "wallbox.notFound": "Wallbox {id} was not found.",

    # Konfiguration und Betrieb
    "config.invalidTimezone": "Invalid time zone '{value}'. Expected an IANA name such as Europe/Berlin (environment variable TZ).",
    "config.maxCachedEngines": "max_cached_engines must be at least 1.",
    "config.timezoneMismatch": "The data of this tenant is stored in the time zone {stored}, but {configured} is configured. Please set TZ for the container back to {stored} – changing the time zone would shift all stored times.",

    # SFTP-Export
    "sftp.privateKeyMissing": "The private key for the SFTP export is not set up.",
    "sftp.knownHostsMissing": "The known_hosts file for the SFTP export is not set up.",
    "sftp.valueNull": "The SFTP setting value must not be null.",
    "sftp.hostInvalid": "The SFTP host must be a host name or an IP address without a scheme.",
    "sftp.directoryInvalid": "The SFTP target directory must be an absolute path without '..'.",
    "sftp.disabled": "The SFTP invoice export is not enabled.",
    "sftp.targetNotDirectory": "The configured SFTP target path is not a directory.",
    "sftp.onlyFinalized": "Only finalized invoices can be exported.",
    "sftp.numberOrDateMissing": "Invoice number or invoice date is missing.",
    "sftp.connectionFailed": "The SFTP connection could not be established. Please check host, key and known_hosts.",
    "sftp.yearDirectoryFailed": "The year directory could not be created on the SFTP server.",
    "sftp.directoryUnreadable": "The SFTP target directory could not be read.",
    "sftp.alreadyExists": "The invoice already exists in the SFTP target directory and was not overwritten.",
    "sftp.sizeMismatch": "The transferred PDF has an unexpected size on the SFTP server.",
    "sftp.exportFailed": "The PDF invoice could not be exported via SFTP.",
    "sftp.directoryMissing": "The configured SFTP target directory does not exist.",

    # S/MIME-Upload und -Einstellungen
    "smime.uploadEmpty": "The uploaded S/MIME file is empty.",
    "smime.uploadTooLarge": "The S/MIME file may be at most 65,535 bytes.",
    "smime.uploadType": "The S/MIME certificate must be a .p12 or .pfx file.",
    "smime.passwordRequired": "A password is required for the S/MIME certificate.",
    "smime.uploadInvalid": "The uploaded S/MIME file is invalid.",
    "smime.uploadBeforeActivate": "An S/MIME certificate with password must be uploaded before activating.",
    "smime.savedPasswordUnusable": "The saved S/MIME password could not be used.",
    "smime.setAndDelete": "The S/MIME certificate cannot be set and deleted at the same time.",
    "smime.fileNameMissing": "The file name of the S/MIME certificate is missing.",
    "smime.fileNameWithoutCertificate": "An S/MIME file name may only be sent together with a certificate.",
    "smime.pkcs12PathMissing": "The path to the S/MIME PKCS#12 file is not configured.",
    "smime.passwordPathMissing": "The path to the S/MIME password file is not configured.",
    "smime.pkcs12ConfiguredUnreadable": "The configured S/MIME PKCS#12 file could not be read.",
    "smime.storedIncomplete": "The stored S/MIME certificate and S/MIME password are incomplete.",
    "smime.passwordFileEmpty": "The S/MIME password file is empty.",
    "smime.keyTypeUnsupported": "The S/MIME private key type is not supported.",
    "smime.notYetValid": "The S/MIME certificate is not yet valid.",
    "smime.expired": "The S/MIME certificate has expired.",
    "smime.senderMismatch": "The configured sender address does not match the S/MIME certificate.",
    "smime.notEmailProtection": "The certificate is not approved for email protection.",
    "smime.notDigitalSignature": "The certificate is not approved for digital signatures.",
    "smime.keyMismatch": "The private key does not match the S/MIME certificate.",
    "smime.pkcs12Empty": "The S/MIME PKCS#12 file is empty.",
    "smime.passwordEmpty": "The S/MIME password is empty.",
    "smime.noPrivateKey": "The S/MIME PKCS#12 file contains no private key.",
    "smime.noCertificate": "The S/MIME PKCS#12 file contains no sender certificate.",
    "smime.outerHeadersFailed": "The outer mail headers could not be created.",
    "smime.passwordFileUnreadable": "The S/MIME password file could not be read.",
    "smime.noExtendedKeyUsage": "The S/MIME certificate lacks the Extended Key Usage extension.",
    "smime.noKeyUsage": "The S/MIME certificate lacks the Key Usage extension.",
    "smime.pkcs12Unreadable": "The S/MIME PKCS#12 file could not be read.",
    "smime.pkcs12LoadFailed": "The S/MIME PKCS#12 file could not be loaded.",
    "smime.signatureFailed": "The S/MIME signature could not be created.",

    # SMTP und E-Mail-Versand
    "smtp.valueNull": "The SMTP setting value must not be null.",
    "smtp.passwordSetAndDelete": "The SMTP password cannot be set and deleted at the same time.",
    "smtp.keyMissing": "The encryption key for mail settings is not configured.",
    "smtp.emptyPassword": "An empty SMTP password cannot be encrypted.",
    "smtp.emptySmimePassword": "An empty S/MIME password cannot be encrypted.",
    "smtp.keyInvalid": "The encryption key for mail settings is invalid.",
    "smtp.passwordDecrypt": "The saved SMTP password could not be decrypted.",
    "smtp.smimePasswordDecrypt": "The saved S/MIME password could not be decrypted.",
    "email.disabled": "Email delivery is disabled.",
    "email.hostMissing": "The SMTP host is not configured.",
    "email.portMissing": "The SMTP port is not configured.",
    "email.timeoutMissing": "The SMTP timeout is not configured.",
    "email.senderAddressMissing": "The sender address is not configured.",
    "email.senderNameMissing": "The sender name is not configured.",
    "email.passwordMissing": "No password is configured for the SMTP username.",
    "email.usernameMissing": "No username is configured for the SMTP password.",
    "email.noAdminEmail": "No email address is stored for the administrator.",
    "email.smimeIncomplete": "The S/MIME configuration is incomplete.",
    "email.onlyFinalized": "Only finalized invoices can be sent by email.",
    "email.noInvoiceNumber": "The invoice has no invoice number.",
    "email.noUser": "No user is assigned to the invoice.",
    "email.postalDelivery": "Postal delivery is selected for this user.",
    "email.noUserEmail": "No email address is stored for the user.",
    "email.smtpTestFailed": "The SMTP test message could not be sent.",
    "email.smimeTestSendFailed": "The S/MIME test message could not be sent.",
    "email.invoiceSendFailed": "The invoice could not be sent by email.",
    "email.passwordEmailFailed": "The password email could not be sent.",
    "email.reviewEmailFailed": "The review email could not be sent.",
    "email.autoBillingNotificationFailed": "The notification for automatic billing could not be sent.",
    "email.smimeTestFailed": "The S/MIME test message could not be signed: {error}",
    "email.smimeInvoiceFailed": "The invoice could not be signed with S/MIME: {error}",
    "email.pdfUnavailable": "The archived invoice PDF is not available: {error}",
    "email.savedPasswordUnusable": "The saved SMTP password could not be used.",

    # Rechnungsarchiv
    "archive.tenantPathInvalid": "The configured tenant path for the invoice archive is invalid.",
    "archive.pathInvalid": "The stored PDF path is invalid.",
    "archive.pathOutside": "The stored PDF path is outside the archive.",
    "archive.dateMissing": "The invoice date is missing.",
    "archive.numberMissing": "The invoice number is missing.",
    "archive.numberInvalid": "The invoice number contains invalid characters.",
    "archive.fileMissing": "The archived PDF file is missing.",
    "archive.sizeMismatch": "The size of the archived PDF file does not match.",
    "archive.checksumMismatch": "The SHA-256 checksum of the archived PDF file does not match.",
    "archive.metadataIncomplete": "The PDF archive metadata is incomplete.",
    "archive.metadataPartial": "The PDF archive metadata is only partially set.",
    "archive.formatInvalid": "The configured invoice format is invalid.",
    "archive.tenantMissing": "The tenant context is missing when accessing the invoice archive.",
    "archive.namespaceMissing": "The tenant's archive namespace is missing when accessing the invoice archive.",
    "archive.otherFileExists": "A different file already exists at the intended archive path.",

    # Stornierung
    "cancellation.reasonRequired": "A reason for the cancellation is required.",
    "cancellation.onlyRegular": "Only a regular invoice can be cancelled.",
    "cancellation.onlyFinalized": "Only a finalized invoice can be cancelled.",
    "cancellation.customerDeleted": "The customer account of this invoice has been deleted, so it can no longer be cancelled in Witty.",
    "cancellation.exists": "A cancellation already exists for this invoice.",
    "cancellation.notFound": "Cancellation {id} was not found.",
    "cancellation.onlyCancellationDocument": "Only a cancellation document can be finalized with this function.",
    "cancellation.onlyDraft": "Only a cancellation draft can be finalized.",
    "cancellation.noOriginal": "No original invoice is assigned to the cancellation.",
    "cancellation.originalNotFinalized": "The original invoice is not finalized.",
    "cancellation.dateBeforeInvoice": "The cancellation date must not be before the invoice date.",
    "cancellation.noItems": "A cancellation without line items cannot be finalized.",
    "cancellation.unknownItemType": "The original line item {id} has the unknown type {type}.",
    "cancellation.draftLoadFailed": "The cancellation draft could not be loaded.",
    "cancellation.itemNoOriginal": "A cancellation line item has no related original line item.",
    "cancellation.itemOtherInvoice": "A cancellation line item does not refer to the original invoice.",
    "cancellation.itemTypeMismatch": "The type of the cancellation line item does not match the original line item.",
    "cancellation.finalizedLoadFailed": "The finalized cancellation could not be loaded.",
    "cancellation.numberFormat": "The last cancellation number has an invalid format.",
    "cancellation.noSession": "No charging session is assigned to the original line item.",
    "cancellation.sessionReassigned": "The charging session is no longer assigned to the original invoice.",
    "cancellation.noBaseFee": "No base fee is assigned to the original line item.",
    "cancellation.baseFeeMismatch": "The cancellation line item does not refer to the base fee of the original line item.",
    "cancellation.baseFeeReassigned": "The base fee is no longer assigned to the original invoice.",

    # Girocode
    "girocode.fieldInvalid": "Girocode: {label} must be a single line with 1 to {max} characters.",
    "girocode.issuerNameInvalid": "Girocode: The name of the invoice issuer must be a single line with 1 to {max} characters.",
    "girocode.invoiceNumberInvalid": "Girocode: The invoice number must be a single line with 1 to {max} characters.",
    "girocode.ibanRequired": "Girocode: A valid IBAN is required.",
    "girocode.ibanCheckDigits": "Girocode: The IBAN check digits are invalid.",
    "girocode.bicInvalid": "Girocode: The BIC must consist of 8 or 11 valid characters.",
    "girocode.bicRequired": "Girocode: A BIC is required for bank accounts outside the EEA.",
    "girocode.euroOnly": "Girocode: Only payments in EUR are supported.",
    "girocode.amountInvalid": "Girocode: The amount must be between 0.01 and 999,999,999.99 EUR and may have at most two decimal places.",
    "girocode.tooLong": "Girocode: The payment data exceeds the permitted 331 UTF-8 bytes.",

    # Rechnungs-PDF
    "pdf.issuerMissing": "The invoice issuer is missing.",
    "pdf.issuerAddressMissing": "The issuer's address is missing.",
    "pdf.recipientMissing": "The invoice recipient is missing.",
    "pdf.recipientAddressMissing": "The recipient's address is missing.",
    "pdf.noItems": "The invoice has no line items.",
    "pdf.draftOnly": "Only invoice drafts can be generated as a draft PDF.",
    "pdf.finalizedOnly": "Only finalized invoices can be generated as PDF.",
    "pdf.dueDateMissing": "The payment due date is missing.",
    "pdf.unknownItemType": "Invoice line item {id} has the unknown type {type}.",
    "pdf.chargingDataMissing": "Billing-relevant data is missing for charging line item {id}.",

    # PDF/A
    "pdfa.notPdf": "The source document is not a PDF file.",
    "pdfa.ghostscriptMissing": "Ghostscript was not found.",
    "pdfa.colourProfileMissing": "The sRGB colour profile for PDF/A was not found.",
    "pdfa.outputIntentMissing": "The PDF/A output intent is missing.",
    "pdfa.outputIntentInvalid": "The PDF/A output intent is invalid.",
    "pdfa.metadataMissing": "The PDF/A metadata is missing.",
    "pdfa.identificationMissing": "The PDF/A-2b identification is missing.",
    "pdfa.checkFailed": "The generated PDF/A file could not be checked.",
    "pdfa.generationFailed": "PDF/A generation failed: {error}",
    "pdfa.noOutput": "Ghostscript did not create a PDF/A file.",
    "pdfa.timeout": "PDF/A generation exceeded the time limit.",
    "pdfa.ghostscriptStartFailed": "Ghostscript could not be started.",

    # Aufbewahrung
    "retention.periodRange": "The retention period must be between {min} and {max} years.",
    "retention.confirmationMismatch": "The confirmation does not match the year to be deleted.",
    "retention.notExpired": "The retention period for {year} has not expired yet (latest year that can be deleted: {cutoff}).",
    "retention.nothingToDelete": "There are no invoices from {year} to delete.",

    # Rechnungserstellung
    "invoicing.periodEndBeforeStart": "The end of the service period must be after its start.",
    "invoicing.nothingBillable": "No billable charging sessions or base fees were found for this user and period.",
    "invoicing.recipientAddressMissing": "No address is stored for the invoice recipient.",
    "invoicing.issuerNameMissing": "No name is configured for the invoice issuer.",
    "invoicing.issuerAddressMissing": "No address is configured for the invoice issuer.",
    "invoicing.taxIdMissing": "A tax number or VAT ID must be configured for the invoice issuer.",
    "invoicing.alreadyFinalized": "Invoice {id} is already finalized.",
    "invoicing.noItems": "An invoice without line items cannot be finalized.",
    "invoicing.paymentTermNegative": "The configured payment term must not be negative.",
    "invoicing.dueBeforeIssue": "The payment due date must not be before the invoice date.",
    "invoicing.baseFeeOtherUser": "The stored base fee for RFID card {card} and month {month} is assigned to another user.",
    "invoicing.beforeBillingStart": "The selected service period lies entirely before the billing start date {date}. Charging sessions and base fees before this date are not billed.",
    "invoicing.noTariff": "No valid tariff for charging session {id}.",
    "invoicing.invalidEnergy": "Invalid energy values for charging session {id}.",
    "invoicing.noTariffAt": "No valid tariff for charging session {id} on {start}.",
    "invoicing.itemNoSession": "No charging session is assigned to charging line item {id}.",
    "invoicing.sessionInvoiced": "Charging session {id} has already been invoiced.",
    "invoicing.itemNoBaseFee": "No base fee is assigned to base fee line item {id}.",
    "invoicing.baseFeeReassigned": "Base fee {id} is no longer assigned to this invoice draft.",

    # Mandanten
    "tenancy.activeNotFound": "The given active tenant was not found.",
    "tenancy.hostMissing": "The tenant host name is missing.",
    "tenancy.hostInvalid": "The tenant host name is invalid.",
    "tenancy.keyMissingMulti": "Multi-tenancy is enabled, but TENANT_DB_ENCRYPTION_KEY is missing.",
    "tenancy.unknown": "The tenant is unknown.",
    "tenancy.cacheSeconds": "cache_seconds must not be negative.",
    "tenancy.noDomain": "Tenant {id} has no canonical domain.",
    "tenancy.noNamespace": "Tenant {id} has no archive namespace.",
    "tenancy.noTenantForHost": "No tenant is registered for this host.",
    "tenancy.locked": "The tenant is locked.",
    "tenancy.unknownOrInactive": "The tenant is unknown or inactive.",
    "tenancy.keyMissing": "TENANT_DB_ENCRYPTION_KEY is not configured.",
    "tenancy.emptyPassword": "An empty tenant database password cannot be encrypted.",
    "tenancy.keyInvalid": "TENANT_DB_ENCRYPTION_KEY is invalid.",
    "tenancy.passwordDecrypt": "The tenant database password could not be decrypted.",

    # Gespeicherte Statusmeldungen (automatischer Abruf, Abrechnung)
    "hagerImport.summary": "{parts} (fetched {scope})",
    "hagerImport.scopeFrom": "from {date}",
    "hagerImport.scopeFull": "in full",
    "hagerImport.new": "{count} new",
    "hagerImport.skipped": "{count} skipped",
    "hagerImport.withoutPrice": "{count} without price",
    "hagerImport.withoutAssignment": "{count} without card assignment",
    "hagerImport.beforeBillingStart": "{count} before billing start",
    "hagerImport.withoutEnergy": "{count} without energy",
    "hagerImport.reassigned": "{count} assigned retroactively",
    "status.unexpectedError": "Unexpected error: {error}",
    "autoBilling.noUserAccount": "No user account is assigned.",
}

# Parameter, die selbst eine Meldung enthalten (z. B. die Ursache hinter
# "could not be imported: …") und deshalb ebenfalls einen Code bekommen
_NESTED_PARAMS = frozenset({"error", "scope"})


def _split_conjunction(text: str) -> list[str]:
    # "a digit, a lowercase letter and a special character"
    head, separator, last = text.rpartition(" and ")

    if not separator:
        return [text]

    return [*head.split(", "), last]


def _split_comma(text: str) -> list[str]:
    # "3 new, 2 skipped"
    return text.split(", ")


# Parameter mit einer Aufzählung; jeder Eintrag bekommt einen Code
_LIST_PARAMS = {
    "requirements": _split_conjunction,
    "parts": _split_comma,
}

_MAX_DEPTH = 3

_PLACEHOLDER = re.compile(r"\{(\w+)\}")

# Pydantic-Fehlertyp -> (Code, {Parameter: Schlüssel im Kontext})
_VALIDATION_TYPES: dict[str, tuple[str, dict[str, str]]] = {
    "missing": ("validation.missing", {}),
    "string_too_long": ("validation.tooLong", {"max": "max_length"}),
    "string_too_short": ("validation.tooShort", {"min": "min_length"}),
    "too_long": ("validation.tooLong", {"max": "max_length"}),
    "too_short": ("validation.tooShort", {"min": "min_length"}),
    "greater_than_equal": ("validation.greaterEqual", {"min": "ge"}),
    "greater_than": ("validation.greater", {"min": "gt"}),
    "less_than_equal": ("validation.lessEqual", {"max": "le"}),
    "less_than": ("validation.less", {"max": "lt"}),
}

_VALIDATION_PREFIXES = ("Value error, ", "Assertion failed, ")


@dataclass(frozen=True)
class _Pattern:
    code: str
    regex: re.Pattern[str]
    names: tuple[str, ...]
    # Länge des festen Textes: spezifischere Vorlagen werden zuerst geprüft
    weight: int


def _compile(code: str, template: str) -> _Pattern:
    parts: list[str] = []
    names: list[str] = []
    position = 0

    for match in _PLACEHOLDER.finditer(template):
        parts.append(re.escape(template[position:match.start()]))
        name = match.group(1)

        if name in names:
            parts.append(f"(?P={name})")
        else:
            parts.append(f"(?P<{name}>.+?)")
            names.append(name)

        position = match.end()

    parts.append(re.escape(template[position:]))

    return _Pattern(
        code=code,
        regex=re.compile("".join(parts), re.DOTALL),
        names=tuple(names),
        weight=len(_PLACEHOLDER.sub("", template)),
    )


@lru_cache(maxsize=1)
def _patterns() -> tuple[_Pattern, ...]:
    return tuple(
        sorted(
            (
                _compile(code, template)
                for code, template in ERROR_MESSAGES.items()
            ),
            key=lambda pattern: pattern.weight,
            reverse=True,
        )
    )


def match_error(message: str, _depth: int = 0) -> dict[str, Any] | None:
    """Liefert {"code", "params"} zu einer Meldung oder None."""

    text = message.strip()

    for pattern in _patterns():
        match = pattern.regex.fullmatch(text)

        if match is None:
            continue

        params: dict[str, Any] = {}

        for name in pattern.names:
            value = match.group(name)

            if name in _LIST_PARAMS:
                items = [
                    match_error(item, _depth + 1)
                    for item in _LIST_PARAMS[name](value)
                ]

                params[name] = (
                    items if all(item is not None for item in items) else value
                )
            elif name in _NESTED_PARAMS and _depth < _MAX_DEPTH:
                params[name] = match_error(value, _depth + 1) or value
            else:
                params[name] = value

        return {"code": pattern.code, "params": params}

    return None


def error_content(detail: str) -> dict[str, Any]:
    """Antwort für eine Fehlermeldung: detail und, wenn bekannt, Code."""

    content: dict[str, Any] = {"detail": detail}
    coded = match_error(detail)

    if coded is not None:
        content.update(coded)

    return content


def message_code(message: str | None) -> dict[str, Any] | None:
    """Code zu einer gespeicherten Meldung (Status, letzter Fehler)."""

    if not message:
        return None

    return match_error(message)


def validation_error_code(error: dict[str, Any]) -> dict[str, Any]:
    """Code und Parameter für einen Fehler aus der Prüfung der Eingaben."""

    location = [
        str(part)
        for part in error.get("loc", ())
        if part not in ("body", "query", "path")
    ]
    field = location[-1] if location else ""
    context = error.get("ctx") or {}

    if error.get("type") in ("value_error", "assertion_error"):
        cause = context.get("error")
        message = str(cause) if cause is not None else str(error.get("msg", ""))

        for prefix in _VALIDATION_PREFIXES:
            if message.startswith(prefix):
                message = message[len(prefix):]

        coded = match_error(message)

        if coded is not None:
            return coded

    code, mapping = _VALIDATION_TYPES.get(
        str(error.get("type")),
        ("validation.invalid", {}),
    )
    params: dict[str, Any] = {"field": field}

    for name, key in mapping.items():
        if key in context:
            params[name] = str(context[key])

    return {"code": code, "params": params}


# Codes für Eingabefehler ohne eigene Meldung (siehe validation_error_code)
VALIDATION_CODES: frozenset[str] = frozenset(
    {code for code, _ in _VALIDATION_TYPES.values()} | {"validation.invalid"}
)
