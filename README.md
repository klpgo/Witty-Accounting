# Witty-Accounting

Billing portal for electric vehicle charging with Hager witty wallboxes.
Charging sessions are fetched from the Hager Cloud, assigned to users via
their RFID cards, priced and billed.

Licensed under the MIT License.

## Features

**Charging data**
- Automatic fetch of charging sessions from the Hager Cloud on a configurable
  schedule, manual fetch and full reconciliation
- Import from the Hager XLSX export or JSON (hager-fetch) as an alternative
- Duplicate detection; sessions before the billing start and, optionally,
  sessions without energy are not imported; sessions can be discarded

**Users and RFID cards**
- RFID cards with time-bound user assignments; sessions without an
  assignment are matched retroactively once the assignment exists
- Users and administrators, invitation by email, configurable password
  policy, maintenance mode and messages on the dashboard

**Billing**
- Energy prices for grid and PV electricity with validity dates, monthly base
  fee per card (pro rata) and optional postage for postal delivery
- Invoice drafts, binding finalization and cancellation invoices with
  sequential numbers
- PDF or PDF/A-2b, archived with checksum; optional Girocode (EPC QR code)
- Delivery by email (SMTP, optional S/MIME signature), by post or as a
  download notification for the portal; optional export via SFTP

**Languages and regional settings**
- User interface in German and English: default per installation, choice
  per user
- Invoices, invoice PDFs and invoice emails in the recipient's language
- Number, date and currency format configurable; time zone from `TZ`
- Server and error messages in English

**Operation**
- One container (FastAPI backend and React frontend) plus MariaDB
- Optional multi-tenancy with a separate database and archive per tenant,
  managed with the local `witty-control` service
  (see the [administrator guide](docs/admin-guide.md#7-multi-tenant-operation))

## Requirements

A Linux host with Docker including the compose plugin, git and internet
access for the build.

## Installation

The steps below cover a single installation. For the initial setup,
synchronization, XLSX upload, billing, backup and multi-tenant operation, see
the [administrator guide](docs/admin-guide.md).

### 1. Get the source

```bash
git clone https://github.com/klpgo/Witty-Accounting
cd Witty-Accounting
```

### 2. Configure `.env`

```bash
cp .env.example .env
```

Set at least the following values:

| Variable | Purpose |
|---|---|
| `DB_PASSWORD`, `DB_ROOT_PASSWORD` | MariaDB passwords (two different values) |
| `JWT_SECRET_KEY` | Signing key for sign-ins, at least 32 bytes |
| `SMTP_SETTINGS_ENCRYPTION_KEY` | Fernet key for stored passwords (mail, Hager Cloud) |
| `TZ` | Time zone of the installation, e.g. `Europe/Berlin` |
| `WITTY_UID`, `WITTY_GID` | User and group the container runs as |

Generate the keys with:

```bash
openssl rand -base64 48        # JWT_SECRET_KEY
docker run --rm python:3.12-slim sh -c \
  "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                               # SMTP_SETTINGS_ENCRYPTION_KEY
```

> **Note:** Charging sessions are stored in the local time of `TZ`. Do not
> change `TZ` after the first import – Witty rejects imports if it no longer
> matches the stored data. Keep `SMTP_SETTINGS_ENCRYPTION_KEY` safe: without
> it, stored passwords cannot be decrypted.

### 3. Create the host directories

```bash
sudo mkdir -p /srv/witty/logs /srv/witty/invoices /srv/witty/secrets
sudo chown -R <WITTY_UID>:<WITTY_GID> /srv/witty
```

The invoice archive in `/srv/witty/invoices` must be kept permanently and
included in your backups. `/srv/witty/secrets` holds the optional SFTP key
files (`invoice-export-key`, `invoice-export-known-hosts`).

### 4. Build and start

```bash
docker compose build
docker compose up -d
```

### 5. Create the database schema

```bash
docker compose run --rm --no-deps backend alembic upgrade head
```

### 6. Create the first administrator

```bash
docker compose run --rm --no-deps \
  -v "$PWD/backend/scripts:/app/scripts:ro" \
  backend python -m scripts.create_admin
```

Further users and administrators are created in the application.

### 7. Open the application

Open `http://<docker-host>:8000` in the browser and sign in. Configure the
invoice issuer, bank details, prices, mail server and the Hager Cloud access
under **Settings**. For access from the internet, use a reverse proxy with
HTTPS in front of port 8000.

## Update

```bash
git pull
docker compose build
docker compose up -d
docker compose run --rm --no-deps backend alembic upgrade head
```

In multi-tenant operation, run the migrations for all tenants instead:

```bash
docker compose run --rm --no-deps backend python -m scripts.migrate_tenants
```

## Backup

Back up the MariaDB volume `witty-mariadb-data` (or a regular database dump),
the invoice archive `/srv/witty/invoices` and the `.env` file.
