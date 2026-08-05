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

## S/MIME-Signatur

Das PKCS#12-Zertifikat (`.p12` oder `.pfx`) und sein Passwort werden ebenfalls
unter **Einstellungen → Mailserver** gepflegt. Das Zertifikat wird beim
Speichern geprüft; dabei müssen der private Schlüssel, die Zertifikatszwecke,
die Gültigkeit und die E-Mail-Adresse des Zertifikats zur konfigurierten
Absenderadresse passen.

Da die PKCS#12-Datei den privaten Schlüssel enthält, darf sie nur bei lokaler
Nutzung oder über eine verschlüsselte HTTPS-Verbindung hochgeladen werden. Das
Zertifikat bleibt passwortgeschützt in der Datenbank; das Passwort wird mit
`SMTP_SETTINGS_ENCRYPTION_KEY` zusätzlich verschlüsselt gespeichert.
Der Schlüssel muss vor dem Speichern gesetzt sein und darf bei Updates nicht
geändert werden. Er kann beispielsweise so erzeugt werden:

```bash
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Nach dem Speichern sendet **S/MIME testen** eine signierte Testnachricht an den
angemeldeten Administrator. Dieser Test funktioniert auch, solange
**E-Mails mit S/MIME signieren** noch deaktiviert ist. **Mailserver testen**
bleibt dagegen bewusst unsigniert und prüft nur den SMTP-Versand.

Die bisherigen Einstellungen `MAIL_SMIME_PKCS12_PATH` und
`MAIL_SMIME_PKCS12_PASSWORD_FILE` bleiben als Rückfallweg für vorhandene
Installationen erhalten. Sobald ein Zertifikat über die Webseite gespeichert
wurde, wird dieses verwendet.

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
