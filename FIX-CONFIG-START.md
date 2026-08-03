# Korrektur: Start ohne alte Pflichtvariablen

Dieses Update behebt den Startabbruch des gemeinsamen Witty-Containers nach
der Bereinigung der `.env`.

`SECRET_KEY` wird nicht verwendet. `INVOICE_ISSUER_NAME` und
`INVOICE_ISSUER_ADDRESS` sind nur noch optionale Fallbacks für alte
Installationen; im aktuellen System stammen diese Angaben aus den
Anwendungseinstellungen in der Datenbank.

## Einspielen

Das Archiv im Grundverzeichnis von `Witty-Accounting` entpacken:

```bash
cd ~/Witty-Accounting
tar -xzf /pfad/Witty-Accounting-config-start-fix.tar.gz
```

Danach das Image neu bauen und nur den Backend-Dienst neu erstellen:

```bash
docker compose build backend
docker compose up -d --no-deps --force-recreate backend
```

## Prüfen

```bash
docker compose ps
docker compose logs --tail=100 backend
curl --fail http://127.0.0.1:8000/health
```
