# Witty-Accounting – Administrator Guide

This guide describes how to install and set up Witty-Accounting, how charging
sessions get into Witty (automatic sync with the Hager Cloud or XLSX upload),
how to run the monthly billing and how to back up and restore the data.

Menu items and buttons are quoted as they appear in the English user
interface. Switch your own interface language under **My account → Language**
if needed. Running several independent tenants on one installation is
described in [section 7](#7-multi-tenant-operation).

**Contents**

1. [Installation](#1-installation)
2. [Initial setup](#2-initial-setup)
3. [Synchronization with the Hager Cloud](#3-synchronization-with-the-hager-cloud)
4. [XLSX upload](#4-xlsx-upload)
5. [Monthly billing](#5-monthly-billing)
6. [Backup and restore](#6-backup-and-restore)
7. [Multi-tenant operation](#7-multi-tenant-operation)
8. [Updates](#8-updates)
9. [Troubleshooting](#9-troubleshooting)

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

Energy prices are tariffs with a validity date. Each tariff applies from 00:00
on its **Valid from** date until the next tariff starts. The list shows all
tariffs; the one in effect today is marked as current.

- **New tariff:** enter the **Valid from** date, the net prices per kWh for
  grid and PV electricity and the VAT rate, then click **Save tariff**. A date
  in the future is possible, e.g. for an announced price change.
- **Change a tariff:** click **Edit** next to it.
- **Past dates** are only accepted if no invoice exists from that date on
  (drafts included). Tariffs within an invoiced period are marked as *billed*
  and cannot be changed; the page shows the earliest possible date. To correct
  a period covered by a draft, delete the draft first.

After saving, all charging sessions from the tariff's date on that have not
been billed yet are recalculated automatically.

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

> **Recommendation: use a separate user with read-only access.** Witty only
> reads charging sessions and wallbox names, so read access is sufficient.
> Invite an additional user to your installation in the Hager web interface,
> give it read-only permissions and use its credentials in Witty instead of
> your own account. Your own password is then not stored in Witty, and the
> access can be revoked at any time without affecting your account.

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
  be billed to this user. It is preset to today, 00:00; usually only the date
  needs to be changed.
- **Valid to** stays empty for an open-ended assignment. To hand a card over
  to another user, end the current assignment and create a new one.
- The optional note (e.g. a licence plate) appears on the invoice.

The monthly base fee is charged per day of the assignment. An assignment
starting at 00:00 includes that whole day. A time of day is only needed when a
card is handed over during the day: the day of the handover then counts for
the previous assignment, the new one starts on the following day.

The start of an assignment can be changed as long as nothing of it has been
billed (no charging session or base fee in an invoice or draft).

Charging sessions that were imported before a matching assignment existed are
assigned automatically as soon as the assignment is created, as long as they
have not been billed yet.

### 2.12 Wallbox names

Under **Settings → Wallboxes**, all wallboxes that appear in charging sessions
are listed with their name from the Hager Cloud. The name printed on invoices
is:

1. the **custom name**, if one is entered,
2. otherwise the **name in the Hager Cloud**,
3. otherwise a short form of the technical ID, e.g. `ID: ..Uydb3`.

A replaced wallbox often has no name in the Hager Cloud. Enter a custom name
and click **Save**; it is applied to all charging sessions of this wallbox that
have not been billed yet. Invoices already created keep their names.

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

## 7. Multi-tenant operation

### 7.1 Overview

In multi-tenant operation, one Witty installation serves several independent
tenants, for example several residential complexes. All tenants share the
application and the MariaDB server, but each tenant has

- its own database with its own users, settings, charging data and invoices,
- its own invoice archive in `/srv/witty/invoices/<tenant code>/`,
- its own domain, e.g. `wallbox42.example.org`.

Witty determines the tenant from the host name of each request. The domains
are registered in the central control database `witty_control`; requests for
unknown host names get no access to any tenant.

Tenants are managed with the control service `witty-control`, a separate
container with its own web interface on port 8001. Docker publishes this port
only on `127.0.0.1` of the Docker host. **Never make it reachable through a
reverse proxy or a firewall rule.**

The mode is set in `.env`:

| `TENANCY_ENABLED` | Mode |
|---|---|
| `false` | Single installation with one database (sections 1 to 6) |
| `true` | Multi-tenant operation |

### 7.2 Set up a new multi-tenant installation

1. **Prepare the installation** as described in sections
   [1.2](#12-get-the-source) to [1.4](#14-create-the-host-directories): get the
   source, configure `.env` and create the host directories. Skip sections 1.6
   and 1.7 – the database schema and the first administrator are created for
   each tenant by the control service.

2. **Build the images and start the database:**
   ```bash
   docker compose build
   docker compose --profile control build control
   docker compose up -d db
   ```

3. **Create the control database:**
   ```bash
   docker compose run --rm --no-deps backend python -m scripts.create_control_database
   ```
   The tool asks for the MariaDB root password (`DB_ROOT_PASSWORD`) and for a
   new password for the user `witty_control`. This user only receives rights
   on the control database.

4. **Complete `.env`:**
   ```dotenv
   TENANCY_ENABLED=true
   CONTROL_DB_HOST=db
   CONTROL_DB_PORT=3306
   CONTROL_DB_NAME=witty_control
   CONTROL_DB_USER=witty_control
   CONTROL_DB_PASSWORD=<password from step 3>
   TENANT_DB_ENCRYPTION_KEY=<Fernet key>
   TENANT_REGISTRY_CACHE_SECONDS=30
   TENANT_ENGINE_CACHE_SIZE=20
   WITTY_CONTROL_PASSWORD=<password for the control interface>
   WITTY_CONTROL_SESSION_SECRET=<at least 32 random characters>
   WITTY_CONTROL_LANGUAGE=en
   ```
   Generate `TENANT_DB_ENCRYPTION_KEY` with the same command as
   `SMTP_SETTINGS_ENCRYPTION_KEY` (see [1.3](#13-configure-env)) and the session
   secret with `openssl rand -hex 32`.

   | Variable | Purpose |
   |---|---|
   | `WITTY_CONTROL_PASSWORD` | Password for signing in to the control interface |
   | `WITTY_CONTROL_SESSION_SECRET` | Signing key for control sessions, at least 32 characters |
   | `WITTY_CONTROL_LANGUAGE` | Language of the control interface and its messages: `en` (default) or `de` |
   | `WITTY_CONTROL_SESSION_MINUTES` | Optional: session duration in minutes (default 30) |
   | `WITTY_CONTROL_PORT` | Optional: local port of the control interface (default 8001) |

   After changing one of these values, recreate the control service with
   `docker compose --profile control up -d --force-recreate control`.

   > `TENANT_DB_ENCRYPTION_KEY` encrypts the database passwords of all
   > tenants. Keep it safe and include `.env` in your backups – without the key,
   > Witty cannot access the tenant databases. `DB_NAME`, `DB_USER` and
   > `DB_PASSWORD` remain required in `.env`, but are not used by the tenants.

5. **Create the schema of the control database:**
   ```bash
   docker compose run --rm --no-deps backend python -m scripts.migrate_tenants
   ```
   As no tenant exists yet, the command ends with the message
   *"No active tenants are registered."* This is expected at this point.

6. **Start Witty and the control service:**
   ```bash
   docker compose up -d
   docker compose --profile control up -d control
   ```

7. **Open the control interface.** On the Docker host, open
   `http://127.0.0.1:8001`. From another computer, use an SSH tunnel:
   ```bash
   ssh -L 8001:127.0.0.1:8001 <user>@<docker-host>
   ```
   and open `http://localhost:8001`. Sign in with `WITTY_CONTROL_PASSWORD`.

8. **Create the first tenant** with:
   - **Code** – a short identifier such as `wb42`; it is used as the name of
     the tenant database and of the archive directory,
   - **Name** – e.g. the name of the residential complex,
   - **Host name** – the domain under which the tenant reaches Witty,
   - **First administrator** – email address, first and last name, password.

   The control service creates the database with its own database user and a
   random password (stored encrypted), creates the schema and the first
   administrator, and registers the domain.

9. **Route the domain** to Witty: the DNS entry points to the Docker host,
   and the reverse proxy forwards HTTPS requests to port 8000. The reverse
   proxy must pass on the original host name, e.g. with nginx
   `proxy_set_header Host $host;` – otherwise Witty cannot determine the tenant.

10. **Sign in** at `https://<domain>` with the tenant's administrator and
    continue with [section 2](#2-initial-setup). Every tenant has its own
    settings, Hager Cloud access, users and charging cards.

Repeat steps 8 to 10 for each further tenant.

### 7.3 Manage tenants

In the control interface, tenants can be created, renamed, assigned to a
different domain, locked and unlocked, and deleted.

- **Locking** a tenant blocks all sign-ins for this tenant; its data remains
  unchanged. Unlocking restores access.
- **Deleting** a tenant removes its registration, database, database user and
  invoice archive. **This cannot be undone.** Back up the tenant first (see
  [section 6](#6-backup-and-restore)). If the deletion fails partway, the
  tenant remains locked so that the deletion can be repeated once the cause
  has been fixed.

### 7.4 Convert an existing installation

This section describes how an installation running as a single installation
(`TENANCY_ENABLED=false`) becomes the first tenant of a multi-tenant
installation. Database and invoice archive are taken over unchanged.

`TENANCY_ENABLED` stays `false` throughout the preparation, so the running
Witty keeps working as before. Multi-tenant operation is switched on only
after the control database, the migration, the registration and the
connection test have succeeded. **Create a backup before you start** (see
[section 6.2](#62-create-a-backup)).

1. **Build the images and start the database:**
   ```bash
   docker compose build
   docker compose --profile control build control
   docker compose up -d db
   ```

2. **Create the control database** as in [7.2](#72-set-up-a-new-multi-tenant-installation),
   step 3.

3. **Complete `.env`** as in 7.2, step 4, but keep `TENANCY_ENABLED=false`
   for now.

4. **Register the existing installation as the first tenant:**
   ```bash
   docker compose run --rm --no-deps backend python -m scripts.bootstrap_tenancy \
     --slug <tenant code> \
     --name "<tenant name>" \
     --hostname <domain>
   ```
   The connection to the existing database is taken from `DB_HOST`,
   `DB_PORT`, `DB_NAME` and `DB_USER` in `.env`; other values can be given
   with `--db-host`, `--db-port`, `--db-name` and `--db-user`. The tool

   1. updates the schema of the control database,
   2. migrates the existing Witty database to the current version,
   3. tests the connection to it,
   4. registers the tenant and its domain (the database password is stored
      encrypted),
   5. checks the domain resolution and the database connection again.

   If an error occurs before the registration, nothing changes and the
   installation keeps running as a single installation. The tool never
   displays database passwords.

5. **Move the invoice archive** into the directory of the tenant. Stop the
   backend first so that no invoice is created or downloaded meanwhile:
   ```bash
   docker compose stop backend
   sudo mkdir -p /srv/witty/invoices/<tenant code>
   sudo find /srv/witty/invoices -mindepth 1 -maxdepth 1 ! -name <tenant code> \
     -exec mv -t /srv/witty/invoices/<tenant code>/ {} +
   sudo chown -R <WITTY_UID>:<WITTY_GID> /srv/witty/invoices
   ```
   The PDF paths stored in the database are relative and remain valid.

6. **Switch on multi-tenant operation:** set `TENANCY_ENABLED=true` in `.env`
   and recreate the backend:
   ```bash
   docker compose up -d --force-recreate backend
   docker compose logs --tail=100 backend
   ```
   From now on, Witty can only be reached under the registered domain.

7. To manage further tenants, start the control service as in 7.2, steps 6
   and 7.

### 7.5 Register an existing database manually

The control service creates new tenants including their database. If a
tenant database already exists and is migrated to the current version, it can
also be registered directly:

```bash
docker compose run --rm --no-deps backend python -m scripts.register_tenant \
  --slug <tenant code> \
  --name "<tenant name>" \
  --hostname <domain> \
  --db-host db \
  --db-port 3306 \
  --db-name <tenant database> \
  --db-user <tenant database user>
```

The archive directory is always derived from the tenant code.

### 7.6 Updates and backup

After installing a new version, migrate the control database and all active
tenant databases with one command:

```bash
docker compose run --rm --no-deps backend python -m scripts.migrate_tenants
```

An error in one tenant does not stop the migration of the others; the command
then ends with an error status and lists the affected tenants. Use
`--tenant <tenant code>` to migrate a single tenant. Rebuild and restart the
control service as well:

```bash
docker compose --profile control up -d --build control
```

The backup in [section 6](#6-backup-and-restore) already covers multi-tenant
operation: the database dump includes the control database and all tenant
databases, the archive includes all tenant directories, and `.env` contains
`TENANT_DB_ENCRYPTION_KEY`.

---

## 8. Updates

```bash
# create a backup first (section 6.2)
git pull
docker compose build
docker compose up -d
docker compose run --rm --no-deps backend alembic upgrade head
```

In multi-tenant operation, use
`docker compose run --rm --no-deps backend python -m scripts.migrate_tenants`
instead of the last command and update the control service as well (see
[section 7.6](#76-updates-and-backup)).

---

## 9. Troubleshooting

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
