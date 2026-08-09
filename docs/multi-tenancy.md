# Witty-Mandantenbetrieb aktivieren

Witty verwendet im Mandantenbetrieb ein gemeinsames Frontend und Backend,
aber eine eigene MariaDB-Datenbank je Mandant. Die Domain wird in der
zentralen Datenbank `witty_control` exakt einem Mandanten zugeordnet.

Diese Anleitung aktiviert zuerst die bereits vorhandene Witty-Datenbank als
ersten Mandanten. Das bisherige Rechnungsarchiv wird unverändert übernommen.

## Sicherheitsprinzip des Ablaufs

`TENANCY_ENABLED` bleibt während der gesamten Vorbereitung auf `false`. Das
laufende Witty arbeitet daher weiter wie bisher. Erst nachdem Kontroll-DB,
Migration, Registrierung und Verbindungstest erfolgreich waren, wird der
Mandantenbetrieb eingeschaltet.

Vor Beginn sollte ein aktuelles Backup der bestehenden MariaDB-Datenbank und
des Rechnungsarchivs vorhanden sein.

## 1. Neues Backend bauen

```bash
docker compose --env-file .env build backend
docker compose --env-file .env up -d db
```

## 2. Kontroll-Datenbank anlegen

Das folgende administrative Werkzeug fragt das MariaDB-Root-Passwort und ein
neues Passwort für den Benutzer `witty_control` verdeckt ab. Der Benutzer
erhält ausschließlich Rechte auf die Kontroll-Datenbank.

```bash
docker compose --env-file .env run --rm --no-deps \
  backend python -m scripts.create_control_database
```

Falls MariaDB den Root-Zugriff aus dem Backend-Container nicht zulässt, kann
die Datenbank alternativ direkt in MariaDB angelegt werden. Das Backend selbst
benötigt später keine Root-Rechte.

## 3. `.env` vorbereiten

Zunächst einen Fernet-Schlüssel erzeugen:

```bash
docker compose --env-file .env run --rm --no-deps \
  backend python -c \
  "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Danach folgende Werte in `.env` ergänzen. Das Passwort ist dasselbe, das in
Schritt 2 für `witty_control` vergeben wurde. Der Fernet-Schlüssel muss sicher
aufbewahrt und zusammen mit der Installation gesichert werden. Ohne ihn lassen
sich die hinterlegten Mandanten-DB-Passwörter nicht mehr entschlüsseln.

```dotenv
TENANCY_ENABLED=false
CONTROL_DB_HOST=db
CONTROL_DB_PORT=3306
CONTROL_DB_NAME=witty_control
CONTROL_DB_USER=witty_control
CONTROL_DB_PASSWORD=<Kontroll-DB-Passwort>
TENANT_DB_ENCRYPTION_KEY=<Fernet-Schlüssel>
TENANT_REGISTRY_CACHE_SECONDS=30
TENANT_ENGINE_CACHE_SIZE=20
```

## 4. Bestehenden Mandanten vorbereiten

Die Angaben für die bestehende Datenbank werden automatisch aus `DB_HOST`,
`DB_PORT`, `DB_NAME` und `DB_USER` in der `.env` übernommen. Für den ersten
Mandanten wird mit `--use-legacy-archive-root` das bisherige Rechnungsarchiv
ohne Verschieben weiterverwendet.

```bash
docker compose --env-file .env run --rm --no-deps \
  backend python -m scripts.bootstrap_tenancy \
  --slug <mandanten-kuerzel> \
  --name "<Mandantenname>" \
  --hostname <witty-domain> \
  --use-legacy-archive-root
```

Abweichende Datenbankwerte können weiterhin explizit mit `--db-host`,
`--db-port`, `--db-name` und `--db-user` angegeben werden.

Das Werkzeug führt in dieser Reihenfolge aus:

1. Schema der Kontroll-Datenbank aktualisieren.
2. Vorhandene Witty-Datenbank auf den aktuellen Alembic-Stand bringen.
3. Verbindung zur vorhandenen Datenbank prüfen.
4. Mandant und Domain registrieren; das DB-Passwort wird verschlüsselt.
5. Domain-Auflösung und Datenbankverbindung erneut prüfen.

Bei einem Fehler vor der Registrierung bleibt der Host weiterhin im bisherigen
Einzelmandantenbetrieb. Das Werkzeug zeigt keine Datenbankpasswörter an.

## 5. Mandantenbetrieb einschalten

Erst nach der Erfolgsmeldung aus Schritt 4 wird in `.env` geändert:

```dotenv
TENANCY_ENABLED=true
```

Danach das Backend neu erzeugen:

```bash
docker compose --env-file .env up -d --force-recreate backend
docker compose --env-file .env logs --tail=100 backend
```

Die Anmeldung muss anschließend über die in Schritt 4 registrierte Domain
erfolgen. Unbekannte Hostnamen erhalten keinen Zugriff auf eine
Mandantendatenbank.

## Migrationen bei späteren Updates

Nach dem Einspielen einer neuen Witty-Version werden zuerst die Kontroll-DB und
anschließend alle aktiven Mandantendatenbanken migriert:

```bash
docker compose --env-file .env run --rm --no-deps \
  backend python -m scripts.migrate_tenants
```

Ein Fehler bei einem Mandanten stoppt die Migration der übrigen Mandanten
nicht. Das Kommando endet trotzdem mit einem Fehlerstatus und führt die
betroffenen Mandanten eindeutig auf. Für eine einzelne Datenbank kann optional
`--tenant <slug>` verwendet werden.
