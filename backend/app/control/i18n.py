"""
Texte der Control-Oberfläche (witty-control) in Deutsch und Englisch.

Die Sprache wird über WITTY_CONTROL_LANGUAGE festgelegt (Standard: en).
Backend-Meldungen werden mit tr() übersetzt; die Seite erhält ihre Texte
über /api/i18n. Platzhalter: {name}.
"""
from __future__ import annotations

SUPPORTED_LANGUAGES = ("en", "de")
DEFAULT_LANGUAGE = "en"

MESSAGES: dict[str, dict[str, str]] = {
    # --- Anmeldung und Sitzung -------------------------------------------
    "auth.tooManyAttempts": {
        "en": "Too many sign-in attempts. Please wait a minute.",
        "de": "Zu viele Anmeldeversuche. Bitte eine Minute warten.",
    },
    "auth.wrongPassword": {
        "en": "The password is incorrect.",
        "de": "Das Passwort ist falsch.",
    },
    "auth.wrongControlPassword": {
        "en": "The control password is incorrect.",
        "de": "Das Control-Passwort ist falsch.",
    },
    "auth.passwordMissing": {
        "en": "WITTY_CONTROL_PASSWORD is missing.",
        "de": "WITTY_CONTROL_PASSWORD fehlt.",
    },
    "auth.secretInvalid": {
        "en": "WITTY_CONTROL_SESSION_SECRET is missing or shorter than 32 characters.",
        "de": "WITTY_CONTROL_SESSION_SECRET fehlt oder ist kürzer als 32 Zeichen.",
    },
    "auth.minutesInvalid": {
        "en": "WITTY_CONTROL_SESSION_MINUTES must be at least 1.",
        "de": "WITTY_CONTROL_SESSION_MINUTES muss mindestens 1 sein.",
    },
    "auth.required": {
        "en": "Sign-in required.",
        "de": "Anmeldung erforderlich.",
    },
    "auth.sessionInvalid": {
        "en": "The session is invalid.",
        "de": "Die Sitzung ist ungültig.",
    },
    "auth.sessionExpired": {
        "en": "The session has expired.",
        "de": "Die Sitzung ist abgelaufen.",
    },
    "auth.securityCheckFailed": {
        "en": "The security check failed.",
        "de": "Die Sicherheitsprüfung ist fehlgeschlagen.",
    },

    # --- Mandanten anlegen und ändern ------------------------------------
    "tenant.codeInvalid": {
        "en": "The code must start with a lowercase letter and may contain at most 32 lowercase letters, digits or underscores.",
        "de": "Das Kürzel muss mit einem Kleinbuchstaben beginnen und darf höchstens 32 Kleinbuchstaben, Ziffern oder Unterstriche enthalten.",
    },
    "tenant.nameEmpty": {
        "en": "The tenant name must not be empty.",
        "de": "Der Mandantenname darf nicht leer sein.",
    },
    "tenant.nameTooLong": {
        "en": "The tenant name may be at most 200 characters long.",
        "de": "Der Mandantenname darf höchstens 200 Zeichen lang sein.",
    },
    "tenant.archiveExists": {
        "en": "The invoice archive for this code already exists. Check and back up the existing data first.",
        "de": "Das Rechnungsarchiv für dieses Kürzel existiert bereits. Prüfe und sichere die vorhandenen Daten zuerst.",
    },
    "tenant.createFailed": {
        "en": "The tenant could not be created completely: {error}",
        "de": "Der Mandant konnte nicht vollständig angelegt werden: {error}",
    },
    "tenant.notFound": {
        "en": "The tenant was not found.",
        "de": "Der Mandant wurde nicht gefunden.",
    },
    "tenant.noCanonicalDomain": {
        "en": "The tenant has no canonical domain.",
        "de": "Der Mandant hat keine kanonische Domain.",
    },
    "tenant.hostnameTaken": {
        "en": "This host name is already registered.",
        "de": "Dieser Hostname ist bereits registriert.",
    },
    "tenant.alreadyRegistered": {
        "en": "Code, database or archive namespace are already registered.",
        "de": "Kürzel, Datenbank oder Archiv-Namespace sind bereits registriert.",
    },
    "tenant.provisionPasswordMissing": {
        "en": "TENANT_PROVISION_DB_PASSWORD is missing.",
        "de": "TENANT_PROVISION_DB_PASSWORD fehlt.",
    },
    "tenant.provisionConnectionFailed": {
        "en": "The connection with the MariaDB provisioning user failed.",
        "de": "Die Verbindung zum MariaDB-Provisionierungsbenutzer ist fehlgeschlagen.",
    },
    "tenant.operationRunning": {
        "en": "Another tenant operation is still running.",
        "de": "Eine andere Mandantenoperation ist noch aktiv.",
    },
    "tenant.databaseExists": {
        "en": "The tenant database already exists.",
        "de": "Die Mandantendatenbank existiert bereits.",
    },
    "tenant.databaseUserExists": {
        "en": "The tenant database user already exists.",
        "de": "Der Mandanten-Datenbankbenutzer existiert bereits.",
    },
    "tenant.encryptionKeyMissing": {
        "en": "TENANT_DB_ENCRYPTION_KEY is missing.",
        "de": "TENANT_DB_ENCRYPTION_KEY fehlt.",
    },
    "tenant.archivePathInvalid": {
        "en": "The archive path is invalid.",
        "de": "Der Archivpfad ist ungültig.",
    },

    # --- Mandanten löschen (Fortschritt) ---------------------------------
    "delete.confirmationMismatch": {
        "en": "The entered tenant code does not match.",
        "de": "Das eingegebene Mandantenkürzel stimmt nicht überein.",
    },
    "delete.checked": {
        "en": "Confirmation and assignment have been checked.",
        "de": "Bestätigung und Zuordnung wurden geprüft.",
    },
    "delete.locked": {
        "en": "The tenant has been locked.",
        "de": "Der Mandant wurde gesperrt.",
    },
    "delete.waitForCache": {
        "en": "Waiting until no cached tenant assignment is active any more.",
        "de": "Warte, bis keine zwischengespeicherte Mandantenzuordnung mehr aktiv ist.",
    },
    "delete.dropDatabase": {
        "en": "Deleting database {database} and database user.",
        "de": "Lösche Datenbank {database} und Datenbankbenutzer.",
    },
    "delete.databaseDropped": {
        "en": "Database and database user have been deleted.",
        "de": "Datenbank und Datenbankbenutzer wurden gelöscht.",
    },
    "delete.removeArchive": {
        "en": "Deleting the invoice archive.",
        "de": "Lösche das Rechnungsarchiv.",
    },
    "delete.archiveRemoved": {
        "en": "The invoice archive has been deleted.",
        "de": "Das Rechnungsarchiv wurde gelöscht.",
    },
    "delete.noArchive": {
        "en": "There was no invoice archive.",
        "de": "Es war kein Rechnungsarchiv vorhanden.",
    },
    "delete.incomplete": {
        "en": "The cleanup was not completed. The tenant remains locked and visible: {error}",
        "de": "Die Bereinigung wurde nicht vollständig abgeschlossen. Der Mandant bleibt gesperrt und sichtbar: {error}",
    },
    "delete.removeRegistration": {
        "en": "Removing the tenant registration.",
        "de": "Entferne die Mandantenregistrierung.",
    },
    "delete.complete": {
        "en": "The tenant has been deleted completely.",
        "de": "Der Mandant wurde vollständig gelöscht.",
    },
    "delete.namespaceMismatch": {
        "en": "The archive namespace does not match the tenant code. The automatic deletion was aborted.",
        "de": "Der Archiv-Namespace entspricht nicht dem Mandantenkürzel. Die automatische Löschung wurde abgebrochen.",
    },
    "delete.databaseMismatch": {
        "en": "Database name or database user match neither the tenant code nor the registered bootstrap database. The automatic deletion was aborted.",
        "de": "Datenbankname oder Datenbankbenutzer entsprechen weder dem Mandantenkürzel noch der registrierten Bootstrap-Datenbank. Die automatische Löschung wurde abgebrochen.",
    },
    "delete.databaseProtected": {
        "en": "The registered database or database user is protected. The automatic deletion was aborted.",
        "de": "Die registrierte Datenbank oder der Datenbankbenutzer ist geschützt. Die automatische Löschung wurde abgebrochen.",
    },
    "delete.databaseShared": {
        "en": "Database or database user are used by another tenant. The automatic deletion was aborted.",
        "de": "Datenbank oder Datenbankbenutzer werden von einem weiteren Mandanten verwendet. Die automatische Löschung wurde abgebrochen.",
    },
    "delete.failedUnexpectedly": {
        "en": "The deletion failed unexpectedly.",
        "de": "Die Löschung ist unerwartet fehlgeschlagen.",
    },
}

# Texte der Seite (index.html, app.js); Abruf über /api/i18n
UI_TEXTS: dict[str, dict[str, str]] = {
    'page.subtitle': {"en": 'Local administration', "de": 'Lokale Administration'},
    'login.eyebrow': {"en": 'Protected area', "de": 'Geschützter Bereich'},
    'login.title': {"en": 'Sign in', "de": 'Anmelden'},
    'login.hint': {"en": 'Use the control password from the server configuration.', "de": 'Verwende das Control-Passwort aus der Server-Konfiguration.'},
    'login.password': {"en": 'Password', "de": 'Passwort'},
    'login.submit': {"en": 'Sign in', "de": 'Anmelden'},
    'app.eyebrow': {"en": 'Tenant management', "de": 'Mandantenverwaltung'},
    'app.title': {"en": 'Tenants', "de": 'Mandanten'},
    'app.refresh': {"en": 'Refresh', "de": 'Aktualisieren'},
    'app.signOut': {"en": 'Sign out', "de": 'Abmelden'},
    'progress.eyebrow': {"en": 'Deleting tenant', "de": 'Mandant wird gelöscht'},
    'progress.title': {"en": 'Deletion', "de": 'Löschvorgang'},
    'progress.running': {"en": 'Running', "de": 'Läuft'},
    'progress.error': {"en": 'Error', "de": 'Fehler'},
    'progress.done': {"en": 'Done', "de": 'Fertig'},
    'progress.checking': {"en": 'Checking the deletion request …', "de": 'Löschauftrag wird geprüft …'},
    'list.eyebrow': {"en": 'Overview', "de": 'Übersicht'},
    'list.title': {"en": 'Existing tenants', "de": 'Vorhandene Mandanten'},
    'list.empty': {"en": 'No tenants yet.', "de": 'Noch keine Mandanten vorhanden.'},
    'list.hostname': {"en": 'Host name', "de": 'Hostname'},
    'list.database': {"en": 'Database', "de": 'Datenbank'},
    'list.rename': {"en": 'Change name', "de": 'Anzeigename ändern'},
    'list.changeHostname': {"en": 'Change host name', "de": 'Hostname ändern'},
    'list.lock': {"en": 'Lock', "de": 'Sperren'},
    'list.unlock': {"en": 'Unlock', "de": 'Entsperren'},
    'list.delete': {"en": 'Delete', "de": 'Löschen'},
    'list.active': {"en": 'Active', "de": 'Aktiv'},
    'list.locked': {"en": 'Locked', "de": 'Gesperrt'},
    'create.eyebrow': {"en": 'Provisioning', "de": 'Provisionierung'},
    'create.title': {"en": 'Create tenant', "de": 'Mandant anlegen'},
    'create.hint': {"en": 'Database, random database password, schema and first administrator are created automatically.', "de": 'Datenbank, zufälliges DB-Passwort, Schema und erster Admin werden automatisch angelegt.'},
    'create.code': {"en": 'Code', "de": 'Kürzel'},
    'create.codeHint': {"en": 'Also used as the unique database name.', "de": 'Wird zugleich der eindeutige Datenbankname.'},
    'create.name': {"en": 'Display name', "de": 'Anzeigename'},
    'create.hostname': {"en": 'Host name', "de": 'Hostname'},
    'create.firstAdmin': {"en": 'First administrator', "de": 'Erster Administrator'},
    'create.email': {"en": 'Email address', "de": 'E-Mail-Adresse'},
    'create.firstName': {"en": 'First name', "de": 'Vorname'},
    'create.lastName': {"en": 'Last name', "de": 'Nachname'},
    'create.password': {"en": 'Initial password', "de": 'Initialpasswort'},
    'create.passwordRepeat': {"en": 'Repeat password', "de": 'Passwort wiederholen'},
    'create.submit': {"en": 'Create tenant completely', "de": 'Mandant vollständig anlegen'},
    'create.submitting': {"en": 'Creating tenant …', "de": 'Mandant wird angelegt …'},
    'create.passwordMismatch': {"en": 'The administrator passwords do not match.', "de": 'Die Admin-Passwörter stimmen nicht überein.'},
    'create.done': {"en": 'Tenant, database and first administrator have been created.', "de": 'Mandant, Datenbank und erster Administrator wurden angelegt.'},
    'edit.eyebrow': {"en": 'Edit tenant', "de": 'Mandant bearbeiten'},
    'edit.title': {"en": 'Change display name', "de": 'Anzeigename ändern'},
    'edit.text': {"en": 'New display name for the tenant', "de": 'Neuer Anzeigename für den Mandanten'},
    'edit.done': {"en": 'The display name has been changed.', "de": 'Der Anzeigename wurde geändert.'},
    'hostname.title': {"en": 'Change host name', "de": 'Hostname ändern'},
    'hostname.text': {"en": 'New host name for the tenant', "de": 'Neuer Hostname für den Mandanten'},
    'hostname.hint': {"en": 'DNS and reverse proxy must be configured separately for the new host name.', "de": 'DNS und Reverse Proxy müssen separat auf den neuen Hostnamen eingestellt werden.'},
    'hostname.done': {"en": 'The host name has been changed.', "de": 'Der Hostname wurde geändert.'},
    'common.cancel': {"en": 'Cancel', "de": 'Abbrechen'},
    'common.save': {"en": 'Save', "de": 'Speichern'},
    'delete.eyebrow': {"en": 'Irreversible deletion', "de": 'Unwiderrufliche Löschung'},
    'delete.title': {"en": 'Delete tenant', "de": 'Mandant löschen'},
    'delete.titleNamed': {"en": 'Delete {name}', "de": '{name} löschen'},
    'delete.warning': {"en": 'Database, database user and the complete invoice archive will be deleted. Make sure that all required data has been backed up externally beforehand.', "de": 'Datenbank, Datenbankbenutzer und vollständiges Rechnungsarchiv werden gelöscht. Stelle sicher, dass alle benötigten Daten vorher extern gesichert wurden.'},
    'delete.confirmText': {"en": 'To confirm, enter the code:', "de": 'Gib zur Bestätigung das Kürzel ein:'},
    'delete.code': {"en": 'Tenant code', "de": 'Mandantenkürzel'},
    'delete.password': {"en": 'Enter the control password again', "de": 'Control-Passwort erneut eingeben'},
    'delete.submit': {"en": 'Delete permanently', "de": 'Endgültig löschen'},
    'delete.done': {"en": 'Tenant, database and invoice archive have been deleted completely.', "de": 'Mandant, Datenbank und Rechnungsarchiv wurden vollständig gelöscht.'},
    'state.locked': {"en": 'The tenant has been locked.', "de": 'Mandant wurde gesperrt.'},
    'state.unlocked': {"en": 'The tenant has been unlocked.', "de": 'Mandant wurde entsperrt.'},
    'error.request': {"en": 'The request failed.', "de": 'Die Anfrage ist fehlgeschlagen.'},
    'error.deleteStart': {"en": 'The deletion could not be started.', "de": 'Die Löschung konnte nicht gestartet werden.'},
    'error.deleteProgress': {"en": 'The deletion progress could not be received.', "de": 'Der Löschfortschritt konnte nicht empfangen werden.'},
    'error.deleteNoCompletion': {"en": 'The deletion ended without a completion message.', "de": 'Die Löschung wurde ohne Abschlussmeldung beendet.'},
}

_language = DEFAULT_LANGUAGE


def normalize_language(value: str | None) -> str:
    value = (value or "").strip().lower()[:2]
    return value if value in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def set_language(value: str | None) -> str:
    global _language
    _language = normalize_language(value)
    return _language


def current_language() -> str:
    return _language


def tr(key: str, **params: object) -> str:
    entry = MESSAGES[key]
    text = entry.get(_language) or entry[DEFAULT_LANGUAGE]
    return text.format(**params) if params else text


def ui_texts() -> dict[str, str]:
    """Texte der Seite in der eingestellten Sprache."""
    return {
        key: entry.get(_language) or entry[DEFAULT_LANGUAGE]
        for key, entry in UI_TEXTS.items()
    }
