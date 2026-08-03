# Compose-Dienst von `backend` zu `witty` umbenennen

Dieses Update ändert nur den Namen des gemeinsamen Anwendungsdienstes. Der
Quellordner `backend/`, das Dockerfile und das Image
`witty-accounting:local` behalten ihre bisherigen Namen.

Das Archiv wird im Grundverzeichnis von `Witty-Accounting` entpackt. Danach:

```bash
docker compose config --services
docker compose up -d --build --remove-orphans
```

Die Dienstausgabe muss anschließend lauten:

```text
db
witty
```

Status und Protokolle werden nun so geprüft:

```bash
docker compose ps
docker compose logs --tail=100 witty
curl --fail http://127.0.0.1:8000/health
```

`--remove-orphans` entfernt den alten, nun nicht mehr definierten
Compose-Dienst `backend`. Das MariaDB-Volume und dessen Daten werden dadurch
nicht gelöscht.
