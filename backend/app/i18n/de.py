"""
Deutsche Texte für Rechnungen, Rechnungs-PDF und Rechnungs-E-Mails.

Referenzsprache: jeder Schlüssel muss auch in en.py vorhanden sein
(tests/test_i18n.py prüft das). Platzhalter: {name}.
"""

MESSAGES: dict[str, str] = {
    # Monatsnamen
    "month.1": "Januar",
    "month.2": "Februar",
    "month.3": "März",
    "month.4": "April",
    "month.5": "Mai",
    "month.6": "Juni",
    "month.7": "Juli",
    "month.8": "August",
    "month.9": "September",
    "month.10": "Oktober",
    "month.11": "November",
    "month.12": "Dezember",

    # Positionsbeschreibungen (beim Anlegen der Rechnung erzeugt)
    "item.chargingSession": "Ladevorgang {start} an {station}",
    "item.monthlyFee": "Monatsgebühr Ladekarte {card} - {month} {year}{proration}",
    "item.proration": " (anteilig {days}/{total} Tage)",
    "item.postage": "Briefporto",
    "item.cancellation": "Storno zu {description}",

    # Rechnungs-PDF
    "pdf.footer.invoice": "Elektronisch erstellte Rechnung",
    "pdf.footer.cancellation": "Elektronisch erstellter Stornobeleg",
    "pdf.page": "Seite {page} von {pages}",
    "pdf.title.invoice": "Ladestromrechnung",
    "pdf.title.cancellation": "Ladestromrechnung – Storno",
    "pdf.invoiceDate": "Rechnungsdatum",
    "pdf.cancellationDate": "Stornodatum",
    "pdf.invoiceNumber": "Rechnungsnummer",
    "pdf.cancellationNumber": "Stornonummer",
    "pdf.invoiceAmount": "Rechnungsbetrag",
    "pdf.cancellationAmount": "Stornobetrag",
    "pdf.paymentTerms": "Zahlungsbedingung",
    "pdf.note": "Hinweis",
    "pdf.bankDetails": "Bankverbindung",
    "pdf.phone": "Tel.",
    "pdf.taxNumber": "Steuernummer: ",
    "pdf.vatId": "USt-IdNr.: ",
    "pdf.servicePeriod": "Leistungszeitraum",
    "pdf.originalInvoice": "Originalrechnung",
    "pdf.cancellationReason": "Stornierungsgrund",
    "pdf.col.position": "Pos.",
    "pdf.col.date": "Datum",
    "pdf.col.station": "WB",
    "pdf.col.energyTotal": "Gesamt<br/>kWh",
    "pdf.col.energyGrid": "Netz<br/>kWh",
    "pdf.col.energyPv": "PV<br/>kWh",
    "pdf.col.gridPrice": "Netzpreis<br/>{currency}/kWh",
    "pdf.col.pvPrice": "PV-Preis<br/>{currency}/kWh",
    "pdf.col.net": "Netto<br/>{currency}",
    "pdf.col.vat": "USt.<br/>%",
    "pdf.col.gross": "Brutto<br/>{currency}",
    "pdf.totals.net": "Nettobetrag",
    "pdf.totals.vat": "Umsatzsteuer",
    "pdf.payment.cancellation": (
        "Dieser Stornobeleg hebt die zugehörige Rechnung vollständig auf. "
        "Für den Stornobeleg besteht kein Zahlungsziel."
    ),
    "pdf.payment.immediately": "Der Rechnungsbetrag ist sofort (bis {date}) ohne Abzug fällig.",
    "pdf.payment.inDays": "Der Rechnungsbetrag ist innerhalb von {days} Tagen (bis {date}) ohne Abzug fällig.",
    "pdf.girocodeCaption": "Für Ihre Banking-App",
    "pdf.closing.invoice": "Vielen Dank. Bitte bewahren Sie diese Rechnung für Ihre Unterlagen auf.",
    "pdf.closing.cancellation": "Bitte bewahren Sie diesen Stornobeleg zusammen mit der Originalrechnung auf.",

    # Rechnungsentwurf (automatische Abrechnung)
    "pdf.title.invoiceDraft": "Ladestromrechnung – Entwurf",
    "pdf.draftWatermark": "ENTWURF",
    "pdf.draftPending": "folgt",
    "pdf.footer.draft": "Rechnungsentwurf zur Prüfung – keine Rechnung im Sinne des UStG",
    "pdf.payment.draft": (
        "Zahlungsziel: {days} Tage ab Rechnungsdatum. Bitte noch nicht "
        "überweisen – die verbindliche Rechnung folgt."
    ),
    "pdf.payment.draftImmediately": (
        "Zahlbar sofort ab Rechnungsdatum. Bitte noch nicht überweisen – "
        "die verbindliche Rechnung folgt."
    ),
    "pdf.closing.draft": (
        "Bitte prüfen Sie diesen Entwurf. Rechnungsnummer und Rechnungsdatum "
        "werden bei der Finalisierung vergeben."
    ),

    # Prüf-E-Mail an den Kunden
    "email.review.subject": "Rechnungsentwurf zur Prüfung – Leistungszeitraum {period}",
    "email.review.intro": (
        "für den Leistungszeitraum {period} haben wir einen Entwurf Ihrer "
        "Ladestrom-Rechnung über {amount} erstellt. Bitte prüfen Sie ihn "
        "nach der Anmeldung im Portal:"
    ),
    "email.review.deadline": (
        "Ohne Rückmeldung wird die Rechnung am {date} verbindlich erstellt "
        "und Ihnen zugestellt. Haben Sie bis dahin Fragen oder Einwände, "
        "wählen Sie beim Entwurf „Nachfrage zum Rechnungsentwurf“."
    ),

    # Hinweise der automatischen Abrechnung an den Rechnungssteller
    "billing.waiting.subject": "Automatische Abrechnung wartet auf Ladedaten ({period})",
    "billing.waiting.body": (
        "die Rechnungsentwürfe für den Leistungszeitraum {period} wurden noch "
        "nicht erstellt, weil die Ladevorgänge aus der Hager Cloud noch nicht "
        "bis zum Ende des Zeitraums abgerufen wurden (letzter erfolgreicher "
        "Abruf: {last_fetch}).\n\nBitte den automatischen Abruf prüfen. Die "
        "Entwürfe werden erstellt, sobald ein Abruf erfolgreich war."
    ),
    "billing.never": "noch nie",
    "billing.drafts.subject": "Automatische Abrechnung: Rechnungsentwürfe für {period}",
    "billing.drafts.body": (
        "für den Leistungszeitraum {period} wurden {count} Rechnungsentwürfe "
        "erstellt und den Kunden zur Prüfung gesendet. Ohne Nachfrage werden "
        "sie am {date} finalisiert und zugestellt."
    ),
    "billing.drafts.none": (
        "für den Leistungszeitraum {period} wurden keine Rechnungsentwürfe "
        "erstellt."
    ),
    "billing.section.skipped": "Nicht abgerechnet:",
    "billing.section.notifyFailed": (
        "Prüf-E-Mail konnte nicht gesendet werden (weitere Versuche folgen; "
        "ohne zugestellte Prüf-E-Mail wird nicht automatisch finalisiert):"
    ),
    "billing.reason.existingDraft": "es gibt bereits den Entwurf #{id} für diesen Zeitraum",
    "billing.finalized.subject": "Automatische Abrechnung: {count} Rechnung(en) finalisiert",
    "billing.finalized.body": (
        "folgende Rechnungsentwürfe wurden nach Ablauf der Prüffrist "
        "finalisiert:"
    ),
    "billing.section.sent": "Per E-Mail zugestellt:",
    "billing.section.postal": "Bitte per Post versenden:",
    "billing.section.failed": "Fehler (bitte im Portal prüfen):",
    "billing.inquiry.subject": "Rechnungsentwurf zurückgestellt – {name}",
    "billing.inquiry.body": (
        "{name} ({email}) hat eine Nachfrage zum Rechnungsentwurf #{id} "
        "(Leistungszeitraum {period}, {amount}) gestellt. Der Entwurf wurde "
        "zurückgestellt und wird nicht automatisch finalisiert.\n\nDer Kunde "
        "wurde gebeten, sich per E-Mail an {contact} zu wenden. Nach der "
        "Klärung bitte den Entwurf im Portal finalisieren oder löschen und "
        "neu erstellen:"
    ),
    "billing.link": "Im Portal öffnen:",

    # Rechnungs-E-Mail
    "email.subject.invoice": "Rechnung {number}",
    "email.subject.cancellation": "Stornorechnung {number}",
    "email.greeting": "Guten Tag,",
    "email.portal.invoice": "Ihre Ladestrom-Rechnung {number} steht im Portal zum Download bereit:",
    "email.portal.cancellation": "Ihre Ladestrom-Stornorechnung {number} steht im Portal zum Download bereit:",
    "email.attachment.invoice": "im Anhang erhalten Sie Ihre Ladestrom-Rechnung {number} als PDF-Datei.",
    "email.attachment.cancellation": "im Anhang erhalten Sie Ihre Ladestrom-Stornorechnung {number} als PDF-Datei.",
    "email.closing": "Mit freundlichen Grüßen",

    # Konto-E-Mails (zweisprachig: Deutsch oben, Englisch darunter)
    "email.englishBelow": "(English version below)",
    "account.greeting.named": "Guten Tag {name},",
    "account.invitation.subject": "Ihr Zugang zu {app}",
    "account.invitation.intro": (
        "für Sie wurde ein Benutzerkonto bei {app} angelegt. Legen Sie über "
        "den folgenden Link Ihr persönliches Passwort fest:"
    ),
    "account.reset.subject": "Passwort für {app} zurücksetzen",
    "account.reset.intro": "über den folgenden Link können Sie ein neues Passwort festlegen:",
    "account.linkValidity": (
        "Der Link ist einmalig und {minutes} Minuten gültig. Falls Sie diese "
        "Nachricht nicht angefordert haben, können Sie sie ignorieren."
    ),

    # Test-E-Mails
    "test.smtp.subject": "Mailserver-Test",
    "test.smtp.body": "diese Testnachricht bestätigt, dass die Mailserver-Einstellungen funktionieren.",
    "test.smime.subject": "S/MIME-Test",
    "test.smime.body": (
        "diese signierte Testnachricht bestätigt, dass die "
        "S/MIME-Einstellungen funktionieren."
    ),
}
