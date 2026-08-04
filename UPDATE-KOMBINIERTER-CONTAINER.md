# Update: Frontend und Backend in einem Container

Dieses Update wird im Grundverzeichnis von `Witty-Accounting` eingespielt.
Es enthält keine `.env`, keine Secrets, keine Uploads und keine Datenbankdaten.

## Voraussetzung

In `.env` muss zusätzlich ein eigenes MariaDB-Root-Passwort stehen:

```env
DB_ROOT_PASSWORD=ein-anderes-sehr-sicheres-passwort
```

Außerdem werden UID und GID des nicht privilegierten Containerbenutzers
`witty` festgelegt. Normalerweise werden dafür die IDs des Linux-Benutzers
verwendet, dem das Witty-Datenverzeichnis gehört:

```bash
id -u
id -g
```

Die ausgegebenen Zahlen werden in `.env` eingetragen, zum Beispiel:

```env
WITTY_UID=1000
WITTY_GID=1000
```

UID und GID `0` sind nicht erlaubt.

Bereits verwendete Werte für `DB_PASSWORD`, `JWT_SECRET_KEY` und
`SMTP_SETTINGS_ENCRYPTION_KEY` dürfen bei einem bestehenden System nicht
geändert werden.

## Update einspielen

Das Archiv im Projektverzeichnis entpacken und anschließend ausführen:

```bash
docker compose config
docker compose build --pull witty
```

Vor dem Start müssen die eingebundenen Verzeichnisse der gewählten UID und
GID gehören. Bei `WITTY_DATA_DIR=/srv/witty-data`, `WITTY_UID=1000` und
`WITTY_GID=1000` geschieht das beispielsweise so:

```bash
sudo install -d -o 1000 -g 1000 \
  /srv/witty-data/logs \
  /srv/witty-data/invoices
```

Danach wird der Container gestartet:

```bash
docker compose up -d
```

## Prüfung

```bash
docker compose ps
docker compose logs --tail=100 witty
docker compose exec witty id
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/
```

`docker compose exec witty id` muss den Benutzer und die Gruppe `witty`
mit den in `.env` festgelegten IDs ausgeben und darf nicht `uid=0(root)`
anzeigen.

Der Build muss eine Node-Stufe `frontend-build` und eine Python-Stufe
`runtime` anzeigen. Das React-Frontend wird anschließend direkt unter `/`
ausgeliefert; die API liegt unter `/api`, der Healthcheck bleibt unter
`/health`.
