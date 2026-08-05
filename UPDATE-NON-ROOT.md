# Witty ohne Root-Rechte ausführen

Der Anwendungscontainer läuft nach diesem Update als Benutzer `witty`.
Seine UID und GID werden in `.env` festgelegt und beim Image-Bau übernommen.

## 1. UID und GID auswählen

Wenn das Witty-Datenverzeichnis dem aktuell angemeldeten Linux-Benutzer
gehört, dessen IDs anzeigen:

```bash
id -u
id -g
```

Die ausgegebenen Zahlen in `.env` eintragen, zum Beispiel:

```env
WITTY_UID=1000
WITTY_GID=1000
```

UID oder GID `0` sind nicht erlaubt; der Image-Bau bricht dann ab.

## 2. Rechte der persistenten Verzeichnisse anpassen

Für die derzeitige Konfiguration mit
`WITTY_DATA_DIR=/srv/witty-backup` und den Beispiel-IDs `1000:1000`:

```bash
sudo install -d -o 1000 -g 1000 \
  /srv/witty-backup/logs \
  /srv/witty-backup/invoices

sudo chown -R 1000:1000 \
  /srv/witty-backup/logs \
  /srv/witty-backup/invoices
```

Die Zahlen müssen den Werten aus `.env` entsprechen. Das rekursive `chown`
ändert nur Besitzer und Gruppe der Witty-Logs und Rechnungs-PDFs; die
MariaDB-Daten liegen weiterhin im separaten Docker-Volume.

## 3. Image neu bauen und Container ersetzen

Eine Änderung von `WITTY_UID` oder `WITTY_GID` erfordert immer einen neuen
Image-Bau:

```bash
docker compose config
docker compose build --pull witty
docker compose up -d --no-deps --force-recreate witty
```

## 4. Benutzer und Schreibrechte prüfen

```bash
docker compose exec witty id

docker compose exec witty sh -c \
  'test -w /app/logs && test -w /app/data/invoices && echo "Schreibrechte in Ordnung"'

curl --fail http://127.0.0.1:8000/health
```

Bei den Beispielwerten muss `id` Folgendes enthalten:

```text
uid=1000(witty) gid=1000(witty)
```

Wenn noch die ältere dateibasierte S/MIME-Konfiguration verwendet wird,
müssen auch die beiden Secret-Dateien für die gewählte UID lesbar sein:

```bash
docker compose exec witty sh -c \
  'test -r /run/secrets/invoice-mail-signing.p12 && \
   test -r /run/secrets/invoice-mail-signing-password && \
   echo "S/MIME-Secrets lesbar"'
```

Witty benötigt für diese Secret-Dateien nur Lesezugriff und verändert sie
nicht. Bei einem über **Einstellungen → Mailserver** hochgeladenen Zertifikat
ist diese Prüfung nicht erforderlich.
