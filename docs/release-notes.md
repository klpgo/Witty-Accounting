# Release notes

## 2.0.0

Witty-Accounting 2.0.0 brings automatic synchronization with the Hager Cloud,
a fully bilingual application (German and English), invoices in the
recipient's language, configurable regional settings and a consolidated
database schema. This release combines all changes since 1.2.0, including the
interim versions on the `develop` branch up to 1.5.0.

### Highlights

- **Automatic sync with the Hager Cloud** – charging sessions of all
  wallboxes are fetched on a configurable schedule, e.g. every night.
- **German and English** – the user interface is fully translated; every user
  chooses a language, with a default per installation.
- **Invoices in the recipient's language** – invoice line items, PDF and
  invoice email follow the language of the recipient.
- **Regional settings** – number, date and currency format are configurable;
  the time zone is taken from `TZ`.
- **New documentation** – a concise README and an administrator guide
  covering installation, setup, synchronization, XLSX upload, billing,
  backup and multi-tenant operation.

### New features

**Charging data and synchronization**

- Direct fetch of charging sessions from the Hager Cloud without a browser:
  sign-in, token cache with automatic renewal and re-login on failure.
- Data source is the E3/DC e-mobility interface, which covers all wallboxes of
  an installation including replaced devices.
- Automatic fetch on a schedule ("every N hours starting at HH:MM"); missed
  runs are caught up. Status of the last and next run in the settings.
- Incremental fetch from the last successful fetch with a three-day overlap;
  full reconciliation and fetching a specific period on demand.
- Import rules: charging sessions before the billing start date are never
  imported; optionally, sessions without energy (0 kWh) are skipped.
- JSON import (output of `hager-fetch`) in addition to the XLSX import.
- Imports are serialized per tenant – a manual fetch waits for a running
  automatic fetch.

**Charging sessions and RFID cards**

- RFID numbers are stored with each charging session; sessions that could not
  be assigned are assigned retroactively once a matching card assignment
  exists. The import result explains the cause per RFID number.
- Charging sessions can be discarded (e.g. test charges) and restored; a
  discarded session is not priced, billed or imported again.
- Charging sessions page with statistics (loaded, billed, not billed,
  discarded) and a compact period column.
- Wallbox IDs are stored with each session; names of replaced wallboxes are
  kept.

**Billing and invoices**

- Invoice language is stored with each invoice (recipient's language, otherwise
  the default language); cancellations keep the language of the original
  invoice. Regenerated PDFs are identical to the original.
- Locale and currency are stored with each invoice; table headers in the PDF
  use the invoice currency.
- Energy prices are tariffs with a validity date and can be created in
  advance or changed afterwards, as long as no invoice exists from that date
  on; unbilled charging sessions are recalculated automatically.
- Invoice line items are listed chronologically: each month's base fee
  followed by that month's charging sessions.
- Wallbox names: custom names per wallbox, otherwise the name from the Hager
  Cloud, otherwise a short form of the ID ("ID: ..XXXXX"); long station names
  wrap within their column in the PDF.
- Button to generate a missing PDF for a finalized invoice.
- The service period on invoices shows the last day of service (inclusive).

**Languages and regional settings**

- User interface in German and English: default language per installation,
  personal language per user (profile and user management).
- Number and date format (de-DE, de-AT, de-CH, en-GB, en-US) and currency
  (EUR, CHF, GBP, USD) are configurable. The currency cannot be changed once
  invoices exist; the Girocode requires EUR.
- The time zone of the installation is taken from `TZ`. Witty records the time
  zone of the stored data and rejects imports if `TZ` is changed later.
- Account emails (invitation, password reset) and test emails are bilingual:
  German first, English below.

**Administration and operation**

- Hager Cloud settings: credentials (password stored encrypted), installation
  ID, serial number, connection test, import rules and schedule.
- Natural sort order for charging cards; invoices sorted with drafts first.
- New card assignments start at 00:00 by default. The first day of an
  assignment is only excluded from the base fee when the card is handed over
  from another assignment during that day.
- The start of a card assignment can be changed as long as nothing of it has
  been billed.
- Two-line header: the navigation no longer wraps in either language.

### Changes

- **Server messages are in English.** Error and status messages returned by
  the API, as well as log messages, are now English. The user interface,
  invoices, PDFs and emails are localized as described above.
- The Hager integration is labelled "Hager Cloud" throughout the application.
- "Rechnungsaussteller" is now "Rechnungssteller"; the dashboard section
  "Mitteilung der Administration" is now "Nachrichten".
- **Database migrations consolidated:** the 41 migrations up to 1.5.0 are
  replaced by a single baseline migration that creates the complete schema.
  The schema is identical; this was verified by comparing both on MariaDB.

### Fixes

- Concurrent imports could fail with MariaDB error 1020 ("Record has changed
  since last read"); status updates are now written in separate transactions.
- HTTP client logs no longer contain URLs with sign-in parameters.
- Error messages after finalizing an invoice remain visible.
- Hard-coded German date and number formats in several places now follow the
  configured format.
- Tests can no longer write into a real invoice archive.
- A base fee from a deleted draft or a cancelled invoice kept its old amount
  in the next draft; unbilled base fees are now recalculated.
- Station names on invoices are determined when the draft is created, so
  renamed wallboxes also apply to sessions from cancelled invoices.

### Upgrade notes

**Before upgrading, create a backup** of the database, the invoice archive and
`.env` (see [admin-guide.md](admin-guide.md#6-backup-and-restore)).

1. **Versions older than 1.5.0** must first be upgraded to 1.5.0 and migrated
   with `alembic upgrade head`. The consolidated baseline migration cannot
   upgrade databases that are older than 1.5.0.
2. **Set `TZ`** in `.env` (e.g. `TZ=Europe/Berlin`) if it is not set yet. Do
   not change it afterwards.
3. Build, start and migrate:
   ```bash
   docker compose build
   docker compose up -d
   docker compose run --rm --no-deps backend alembic upgrade head
   ```
   In multi-tenant operation, use
   `docker compose run --rm --no-deps backend python -m scripts.migrate_tenants`.
   Databases on the 1.5.0 schema are already on revision `e5c7a9b1d3f2` and
   need no migration.
4. **Hager Cloud:** enter username, password, installation ID and serial
   number under *Settings → Hager Cloud*, test the connection and enable the
   automatic fetch.
5. Optionally choose the default language, number and date format and
   currency under *Settings*.

**Note for API clients:** error messages in API responses are now English.
Clients that evaluate the message text must be adapted; evaluating the HTTP
status code is recommended.
