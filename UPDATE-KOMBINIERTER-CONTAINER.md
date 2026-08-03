# Update: Frontend und Backend in einem Container

Dieses Update wird im Grundverzeichnis von `Witty-Accounting` eingespielt.
Es enthält keine `.env`, keine Secrets, keine Uploads und keine Datenbankdaten.

## Voraussetzung

In `.env` muss zusätzlich ein eigenes MariaDB-Root-Passwort stehen:

```env
DB_ROOT_PASSWORD=ein-anderes-sehr-sicheres-passwort
```

Bereits verwendete Werte für `DB_PASSWORD`, `JWT_SECRET_KEY` und
`SMTP_SETTINGS_ENCRYPTION_KEY` dürfen bei einem bestehenden System nicht
geändert werden.

## Update einspielen

Das Archiv im Projektverzeichnis entpacken und anschließend ausführen:

```bash
docker compose config
docker compose build --pull backend
docker compose up -d
```

## Prüfung

```bash
docker compose ps
docker compose logs --tail=100 backend
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/
```

Der Build muss eine Node-Stufe `frontend-build` und eine Python-Stufe
`runtime` anzeigen. Das React-Frontend wird anschließend direkt unter `/`
ausgeliefert; die API liegt unter `/api`, der Healthcheck bleibt unter
`/health`.
