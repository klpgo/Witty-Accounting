# Update: Direkter Link zu „Meine Daten“

Dieses Update entfernt „Meine Daten“ aus der Hauptnavigation. Die Seite ist
jetzt direkt über den Benutzernamen rechts oben erreichbar und steht allen
angemeldeten Benutzern einschließlich Administratoren zur Verfügung. Es wird
kein Untermenü mehr geöffnet.

## Einspielen

Das Archiv im Wurzelverzeichnis des Projekts entpacken:

```bash
cd ~/Witty-Accounting
tar -xzf /pfad/Witty-Accounting-benutzerlink-update.tar.gz
```

Anschließend das Image neu bauen und den Dienst neu erstellen:

```bash
docker compose build witty
docker compose up -d --no-deps --force-recreate witty
```

## Prüfen

```bash
docker compose ps
curl --fail http://127.0.0.1:8000/health
```

Nach der Anmeldung öffnet ein Klick auf den Benutzernamen beziehungsweise die
E-Mail-Adresse rechts oben unmittelbar die Seite „Meine Daten“. Dies gilt für
normale Benutzer und Administratoren. Der Button „Abmelden“ bleibt daneben
unverändert verfügbar.
