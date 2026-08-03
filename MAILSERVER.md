# Mailserver-Konfiguration

## Empfohlen: SMTP-Server des Providers

Die Mailserverdaten werden in Witty unter **Einstellungen → Mailserver**
gepflegt. Für einen Provider mit SMTP-Submission werden üblicherweise folgende
Werte verwendet:

```text
SMTP-Host:        vom Provider angegebener Servername
SMTP-Port:        587
STARTTLS:         aktiviert
SMTP-Benutzer:    vom Provider angegebener Benutzername
SMTP-Passwort:    Mailbox- oder App-Passwort
Absenderadresse:  eine beim Provider zulässige Adresse
```

Danach sollte über die Einstellungsseite eine Test-E-Mail versendet werden.
Witty unterstützt derzeit STARTTLS, aber noch kein implizites TLS auf Port 465.

Bei Verwendung des Provider-Servers ist `host.docker.internal` nicht nötig.
Der Eintrag in `docker-compose.yml` kann jedoch als lokale Ausweichmöglichkeit
bestehen bleiben.

## Alternative: Postfix auf dem Docker-Host

Der Compose-Eintrag

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

stellt nur die Namensauflösung zur Host-Gateway-Adresse bereit. Postfix muss
zusätzlich auf dieser Docker-Bridge-Adresse lauschen, Verbindungen aus dem
konkreten Compose-Netz erlauben und die Host-Firewall muss TCP-Port 25 von
diesem Netz zulassen. Erst dann kann Witty mit diesen Werten senden:

```text
SMTP-Host:  host.docker.internal
SMTP-Port:  25
STARTTLS:   deaktiviert, sofern Postfix lokal kein STARTTLS anbietet
```

Das Docker-Netz darf nicht pauschal als Relay für beliebige Absender oder
Ziele geöffnet werden. Die genaue Postfix-Konfiguration hängt von der
Bridge-Adresse und dem von Compose angelegten Subnetz ab.
