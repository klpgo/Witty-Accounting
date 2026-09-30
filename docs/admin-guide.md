# Witty-Accounting – Administrator Guide

This guide describes how to install and set up Witty-Accounting, how charging
sessions get into Witty (automatic sync with the Hager Cloud or XLSX upload),
how to run the monthly billing and how to back up and restore the data.

Menu items and buttons are quoted as they appear in the English user
interface. Switch your own interface language under **My account → Language**
if needed. Multi-tenant operation is covered separately in
[multi-tenancy.md](multi-tenancy.md).

**Contents**

1. [Installation](#1-installation)
2. [Initial setup](#2-initial-setup)
3. [Synchronization with the Hager Cloud](#3-synchronization-with-the-hager-cloud)
4. [XLSX upload](#4-xlsx-upload)
5. [Monthly billing](#5-monthly-billing)
6. [Backup and restore](#6-backup-and-restore)
7. [Updates](#7-updates)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Installation

### 1.1 Requirements

- Linux host with Docker including the compose plugin, and git
- Internet access for the build and for the Hager Cloud
- A domain name and a reverse proxy with HTTPS if Witty is to be reachable
  from the internet

### 1.2 Get the source

```bash
git clone https://github.com/klpgo/Witty-Accounting
cd Witty-Accounting
```

### 1.3 Configure `.env`

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` and set at least these values:

| Variable | Purpose |
|---|---|
| `DB_PASSWORD` | Password of the Witty database user |
| `DB_ROOT_PASSWORD` | MariaDB root password (different from `DB_PASSWORD`) |
| `JWT_SECRET_KEY` | Signing key for sign-ins, at least 32 bytes |
| `SMTP_SETTINGS_ENCRYPTION_KEY` | Fernet key that encrypts stored passwords (mail server, S/MIME, Hager Cloud) |
| `TZ` | Time zone of the installation, e.g. `Europe/Berlin` |
| `WITTY_UID`, `WITTY_GID` | User and group the container runs as |

Generate the keys:

```bash
# JWT_SECRET_KEY
openssl rand -base64 48

# SMTP_SETTINGS_ENCRYPTION_KEY
docker run --rm python:3.12-slim sh -c \
  "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
```

> **Important**
> - Charging sessions are stored in the local time of `TZ`. **Do not change
>   `TZ` after the first import.** Witty remembers the time zone of the data
>   and rejects imports if it no longer matches.
> - Keep a copy of `SMTP_SETTINGS_ENCRYPTION_KEY` in a safe place. Without it,
>   the stored passwords cannot be decrypted after a restore.

### 1.4 Create the host directories

```bash
sudo mkdir -p /srv/witty/logs /srv/witty/invoices /srv/witty/secrets /srv/witty/backup
sudo chown -R <WITTY_UID>:<WITTY_GID> /srv/witty
```

| Directory | Content |
|---|---|
| `/srv/witty/invoices` | Invoice archive (PDFs) – must be kept permanently |
| `/srv/witty/logs` | Application logs |
| `/srv/witty/secrets` | Optional SFTP key files (read-only in the container) |
| `/srv/witty/backup` | Target for local backups (see [section 6](#6-backup-and-restore)) |

### 1.5 Build and start

```bash
docker compose build
docker compose up -d
```

This starts the database container `witty-db` and the application container
`witty` on port 8000.

### 1.6 Create the database schema

The schema is created and updated with migrations, also on a new
installation:

```bash
docker compose run --rm --no-deps backend alembic upgrade head
```

### 1.7 Create the first administrator

```bash
docker compose run --rm --no-deps \
  -v "$PWD/backend/scripts:/app/scripts:ro" \
  backend python -m scripts.create_admin
```

The script asks for the email address, first and last name and the password
(twice). This only works for the first administrator; all further users are
created in the application.

### 1.8 Access

Open `http://<docker-host>:8000` and sign in with the administrator account.
For access from the internet, put a reverse proxy with HTTPS in front of
port 8000 and do not expose port 8000 directly.

---

## 2. Initial setup

Work through the settings in the following order. All settings are under
**Settings** unless stated otherwise.

### 2.1 General

- **Application name** – shown as the browser title and in emails.
- **Default language** – language for users without their own choice and for
  the sign-in pages. Users can override it under **My account**.
- **Girocode on invoices** – adds an EPC payment QR code to new invoice PDFs.
  Requires the bank details below and the currency EUR.

### 2.2 Invoice issuer and bank details

Enter name, address, phone (optional), tax number and/or VAT ID, bank name,
IBAN and BIC. These values are copied into every new invoice draft; later
changes do not affect invoices that already exist.

### 2.3 Billing

| Setting | Notes |
|---|---|
| **Number and date format** | Format of numbers, dates and amounts in the interface and on new invoices |
| **Currency** | Cannot be changed after the first invoice has been created |
| **Billing start date** | Charging sessions before this date are never imported or billed |
| Monthly base fee (net) | Per assigned charging card and month, charged pro rata for partial months |
| VAT on base fee and postage | In percent |
| Postage (net) | Charged only for users with postal delivery and only if greater than 0 |
| Payment term in days | Added to the invoice date when finalizing |
| Invoice number prefix | For example `RE` results in `RE-2026-000001` |
| Invoice format | Standard PDF or PDF/A-2b |

Click **Save settings**.

### 2.4 Energy prices

Enter the net prices per kWh for grid and PV electricity and the VAT rate,
then click **Save energy prices**. A price change takes effect from the day it
is saved; the previous prices remain valid for earlier charging sessions.

### 2.5 Dashboard and access

- **Note to users** – a message shown on everyone's dashboard, e.g. the next
  billing date.
- **Maintenance mode** – only administrators can sign in.

### 2.6 Password rules

Define the minimum length and required character types. Set the
**Public frontend address** to the URL under which users reach Witty
(e.g. `https://wallbox.example.org`). It is used in invitation and
password-reset emails – without it, the links in these emails do not work.

### 2.7 Mail server and S/MIME signature

Enter the SMTP host, port, encryption, credentials, sender name and sender
address and click **Save mail settings**. Use **Test mail server** to send a
test email to your own address.

Optionally upload a PKCS#12 certificate (`.p12` or `.pfx`) with its password
to sign outgoing emails, and check it with **Test S/MIME**.

### 2.8 Invoice export via SFTP (optional)

Finalized invoices can be exported to an SFTP server by an administrator.
Place the client key and the host key list on the host:

```bash
/srv/witty/secrets/invoice-export-key           # private key, mode 0600
/srv/witty/secrets/invoice-export-known-hosts   # created with ssh-keyscan
```

```bash
ssh-keyscan -p 22 sftp.example.org > /srv/witty/secrets/invoice-export-known-hosts
```

Verify the fingerprint independently. Both files must be readable by
`WITTY_UID`/`WITTY_GID`. Then enter host, port, user and target directory,
tick **Enable SFTP invoice export** and use **Test connection**.

### 2.9 Hager Cloud

1. Enter **Username (email)** and **Password** of the Hager Cloud account.
2. Enter **Installation ID** and **Serial number**. Both are part of the
   address in the Hager web interface:
   `https://flow.hager.com/e-mobility/<installation-id>/<serial-number>/…`
3. Click **Save Hager credentials**, then **Test connection**. On success,
   the date of the latest charging session is shown.
4. Under **Import rules**, decide whether charging sessions without energy
   (0 kWh), e.g. aborted or unauthorized sessions, should be skipped. This is
   recommended; the rule applies to all import paths.
5. Under **Automatic fetch**, tick **Enable automatic fetch** and set the
   schedule, for example **Every 24 hours**, **Starting at** `02:00` for a
   nightly sync.

See [section 3](#3-synchronization-with-the-hager-cloud) for how the
synchronization works.

### 2.10 Users

Under **Users → New user**, enter name, email address, address, invoice
delivery (email, post or portal download) and optionally the language, then
click **Create user**. The user receives an email with a one-time link to set
a personal password. The address is printed on the invoices.

### 2.11 Charging cards and assignments

Under **Charging cards → New RFID card**, create each card with its RFID
number exactly as it appears in the Hager data (e.g. `6AA972EA`) and a
description, then click **Create card**.

Select the card and add a **New assignment** to a user:

- **Valid from** must be on or before the first charging session that is to
  be billed to this user.
- **Valid to** stays empty for an open-ended assignment. To hand a card over
  to another user, end the current assignment and create a new one.
- The optional note (e.g. a licence plate) appears on the invoice.

Charging sessions that were imported before a matching assignment existed are
assigned automatically as soon as the assignment is created, as long as they
have not been billed yet.

---

## 3. Synchronization with the Hager Cloud

### 3.1 How it works

Witty fetches the charging sessions of all wallboxes of the installation from
the Hager Cloud. Each fetch:

- starts from the **last successful fetch minus 3 days** (overlap), but never
  before the **billing start date**; the very first fetch starts at the
  billing start date,
- skips charging sessions that already exist, so repeated fetches are safe,
- skips sessions that are still running; they are picked up by the next fetch,
- prices the new sessions and assigns them to users via their charging cards,
- assigns older, unassigned sessions retroactively if a matching card
  assignment exists in the meantime.

Only one import runs at a time. A manual fetch started during an automatic
fetch waits until the automatic fetch has finished.

### 3.2 Automatic fetch

When enabled (see [2.9](#29-hager-cloud)), the fetch runs on the configured
schedule. **Settings → Hager Cloud** shows the **Next fetch**, the
**Last successful fetch**, the **Last automatic fetch** and its **Result**,
e.g. `3 new, 12 skipped (fetched from 2026-09-26)`.

### 3.3 Manual fetch

Under **Data import → Fetch from the Hager Cloud**:

| Input | Effect |
|---|---|
| No dates | Everything new since the last successful fetch (as the automatic fetch) |
| **From (optional)** / **To (optional)** | Only this period, not before the billing start date; does not change the last successful fetch |
| **Fetch all charging sessions from the billing start** | Full reconciliation, e.g. after a longer outage or when the billing start date has been moved back |

Click **Fetch from the Hager Cloud now**.

### 3.4 Import result

| Field | Meaning |
|---|---|
| Read | Charging sessions received |
| Newly imported | New sessions stored |
| Skipped | Sessions that already existed |
| Priced | New sessions with a price |
| Without price | No energy price valid at the session date – add or correct the energy prices |
| Invalid energy | Implausible energy values in the source data |
| Without card assignment | See below |

**Unassigned RFID cards** lists the RFID numbers that could not be assigned,
grouped by cause:

- **Card not created** – create the card under **Charging cards**.
- **No user assignment at the time of charging** – create an assignment with
  a suitable **Valid from** date.
- **Card deactivated** – activate the card if the sessions are to be billed.

The sessions are stored with their RFID number and are assigned
automatically once the cause has been resolved.

---

## 4. XLSX upload

The XLSX upload is an alternative to the synchronization, e.g. for historical
data or if the Hager Cloud cannot be reached.

### 4.1 Export from the Hager web interface

Export the charging sessions of the desired period from the Hager web
interface as an XLSX file. **Set the Hager web interface to German before
exporting.** Witty expects the German column headers in this order:

| # | Column |
|---|---|
| 1 | Startdatum |
| 2 | Status |
| 3 | Dauer |
| 4 | Gesamte Energie (kWh) |
| 5 | MID-zertifiziert |
| 6 | Solarstrom (kWh) |
| 7 | Solares Verhältnis |
| 8 | Authentifizierung |
| 9 | Ladestation |

### 4.2 Upload

1. Open **Data import → Import from file**.
2. Click **Choose file** and select the `.xlsx` file (at most 10 MB).
3. Click **Import file** and check the import result (see
   [3.4](#34-import-result)).

The same rules apply as for the synchronization: nothing before the billing
start date, optionally no sessions without energy, and existing sessions are
skipped – also if they were fetched from the Hager Cloud before. Uploading the
same file twice is therefore harmless.

A JSON file created with the `hager-fetch` tool can be imported the same way.

---

## 5. Monthly billing

1. **Check the data.** Under **Charging sessions**, check that all sessions
   of the month are present, assigned and priced. Discard test or faulty
   sessions that must not be billed: select them and click
   **Discard selection**.
2. **Create drafts.** Under **Invoices → Create draft**, select the user and
   the service period and click **Create draft**. The period end is
   exclusive: for September enter 1 September 00:00 to 1 October 00:00. The
   form suggests the current month. The draft contains all billable
   charging sessions, the monthly base fees and, for postal delivery, the
   postage.
3. **Finalize.** Open the draft, check it and click
   **Finalize invoice bindingly**. The invoice receives its number, becomes
   unchangeable and is archived as PDF. Invoices are created in the language
   of the recipient.
4. **Deliver.** Depending on the user's delivery method, click
   **Send by email** or **Send download notification**, or print the PDF with
   **Print PDF** for postal delivery. Optionally use **Export PDF via SFTP**.
5. **Corrections.** A finalized invoice is never changed. Open it and click
   **Cancel invoice**, enter a reason, then finalize the cancellation draft with
   **Finalize cancellation invoice bindingly**. The charging sessions become
   billable again and can be included in a new, corrected invoice.

---

## 6. Backup and restore

### 6.1 What to back up

| Item | Location | Why |
|---|---|---|
| Database | Container `witty-db` | All master data, charging sessions and invoices |
| Invoice archive | `/srv/witty/invoices` | The archived invoice PDFs |
| Configuration | `.env` | Passwords and keys, in particular `SMTP_SETTINGS_ENCRYPTION_KEY` |
| Secrets | `/srv/witty/secrets` | SFTP key files, if used |

Database and invoice archive belong together: back them up at the same time.
Invoices are subject to statutory retention periods – keep the backups
accordingly and store at least one copy outside the Docker host.

### 6.2 Create a backup

```bash
BACKUP_DIR=/srv/witty/backup
STAMP=$(date +%F)

# Database (all databases, consistent snapshot)
docker exec witty-db sh -c \
  'exec mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines --all-databases' \
  | gzip > "$BACKUP_DIR/witty-db-$STAMP.sql.gz"

# Invoice archive, configuration and secrets
tar czf "$BACKUP_DIR/witty-files-$STAMP.tar.gz" \
  -C /srv/witty invoices secrets \
  -C "$PWD" .env
```

Run the commands in the Witty directory (where `.env` is located). Protect the
backup files: they contain passwords and personal data.

To run the backup nightly, save the commands as a script, e.g.
`/usr/local/bin/witty-backup.sh`, and add it to root's crontab:

```cron
30 3 * * * cd /path/to/Witty-Accounting && /usr/local/bin/witty-backup.sh
```

Schedule it after the nightly Hager fetch. Remove old local backups
regularly, e.g. with `find /srv/witty/backup -mtime +30 -delete`, after they
have been copied off the host.

### 6.3 Restore

1. Stop the application, keep the database running:
   ```bash
   docker compose stop backend
   ```
2. Restore the database:
   ```bash
   gunzip -c /srv/witty/backup/witty-db-<date>.sql.gz \
     | docker exec -i witty-db sh -c 'exec mariadb -u root -p"$MARIADB_ROOT_PASSWORD"'
   ```
3. Restore the files and the ownership:
   ```bash
   sudo tar xzf /srv/witty/backup/witty-files-<date>.tar.gz -C /srv/witty invoices secrets
   sudo chown -R <WITTY_UID>:<WITTY_GID> /srv/witty/invoices /srv/witty/secrets
   ```
   Restore `.env` from the same archive if the configuration was lost. Use the
   original `SMTP_SETTINGS_ENCRYPTION_KEY` and `TZ`.
4. Start the application and apply migrations if the backup is from an older
   version:
   ```bash
   docker compose up -d
   docker compose run --rm --no-deps backend alembic upgrade head
   ```
5. Sign in and check a few invoices: **Download PDF** must work for finalized
   invoices.

Test the restore procedure on a separate system from time to time.

---

## 7. Updates

```bash
# create a backup first (section 6.2)
git pull
docker compose build
docker compose up -d
docker compose run --rm --no-deps backend alembic upgrade head
```

In multi-tenant operation, use
`docker compose run --rm --no-deps backend python -m scripts.migrate_tenants`
instead of the last command.

---

## 8. Troubleshooting

Server messages are always in English. Logs are available with
`docker compose logs -f backend` and in `/srv/witty/logs`.

| Message or symptom | Cause and solution |
|---|---|
| *Sign-in rejected – please check email and password.* | The Hager Cloud credentials are wrong. Correct them under **Settings → Hager Cloud**. |
| *Hager Cloud is not reachable: …* | Network problem or Hager Cloud outage. The next fetch catches up automatically thanks to the 3-day overlap. |
| *Another import is still running.* | Wait until the running import has finished and try again. |
| *The data of this tenant is stored in the time zone …* | `TZ` was changed. Set it back to the stored value in `.env` and restart the container. |
| *A different file already exists at the intended archive path.* | The archive contains a PDF from another database state (e.g. after a reset). Move the conflicting file out of `/srv/witty/invoices` and generate the PDF again. |
| Charging sessions without price | No energy price valid at the session date. Correct the energy prices. |
| Charging sessions without card assignment | See [3.4](#34-import-result). |
| Invitation links do not work | Set the **Public frontend address** under **Settings → Password rules**. |
| Emails are not sent | Check the settings with **Test mail server**; see the logs for details. |
