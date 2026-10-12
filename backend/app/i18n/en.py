"""English texts for invoices, the invoice PDF and invoice emails."""

MESSAGES: dict[str, str] = {
    "month.1": "January",
    "month.2": "February",
    "month.3": "March",
    "month.4": "April",
    "month.5": "May",
    "month.6": "June",
    "month.7": "July",
    "month.8": "August",
    "month.9": "September",
    "month.10": "October",
    "month.11": "November",
    "month.12": "December",

    "item.chargingSession": "Charging session {start} at {station}",
    "item.monthlyFee": "Monthly fee charging card {card} - {month} {year}{proration}",
    "item.proration": " (pro rata {days}/{total} days)",
    "item.postage": "Postage",
    "item.cancellation": "Cancellation of {description}",

    "pdf.footer.invoice": "Electronically generated invoice",
    "pdf.footer.cancellation": "Electronically generated cancellation document",
    "pdf.page": "Page {page} of {pages}",
    "pdf.title.invoice": "Charging invoice",
    "pdf.title.cancellation": "Charging invoice – cancellation",
    "pdf.invoiceDate": "Invoice date",
    "pdf.cancellationDate": "Cancellation date",
    "pdf.invoiceNumber": "Invoice number",
    "pdf.cancellationNumber": "Cancellation number",
    "pdf.invoiceAmount": "Invoice amount",
    "pdf.cancellationAmount": "Cancellation amount",
    "pdf.paymentTerms": "Payment terms",
    "pdf.note": "Note",
    "pdf.bankDetails": "Bank details",
    "pdf.phone": "Phone",
    "pdf.email": "Email",
    "pdf.taxNumber": "Tax number: ",
    "pdf.vatId": "VAT ID: ",
    "pdf.servicePeriod": "Service period",
    "pdf.originalInvoice": "Original invoice",
    "pdf.cancellationReason": "Reason for cancellation",
    "pdf.col.position": "Pos.",
    "pdf.col.date": "Date",
    "pdf.col.station": "Station",
    "pdf.col.energyTotal": "Total<br/>kWh",
    "pdf.col.energyGrid": "Grid<br/>kWh",
    "pdf.col.energyPv": "PV<br/>kWh",
    "pdf.col.gridPrice": "Grid price<br/>{currency}/kWh",
    "pdf.col.pvPrice": "PV price<br/>{currency}/kWh",
    "pdf.col.amount": "Amount<br/>{currency}",
    "pdf.col.net": "Net<br/>{currency}",
    "pdf.col.vat": "VAT<br/>%",
    "pdf.col.gross": "Gross<br/>{currency}",
    "pdf.totals.net": "Net amount",
    "pdf.totals.vat": "VAT",
    "pdf.payment.cancellation": (
        "This cancellation document fully cancels the related invoice. "
        "No payment is due for this cancellation document."
    ),
    "pdf.payment.immediately": "The invoice amount is due immediately (by {date}) without deduction.",
    "pdf.payment.inDays": "The invoice amount is due within {days} days (by {date}) without deduction.",
    "pdf.girocodeCaption": "For your banking app",
    "pdf.closing.invoice": "Thank you. Please keep this invoice for your records.",
    "pdf.closing.cancellation": "Please keep this cancellation document together with the original invoice.",

    "pdf.title.invoiceDraft": "Charging invoice – draft",
    "pdf.draftWatermark": "DRAFT",
    "pdf.draftPending": "to follow",
    "pdf.footer.draft": "Invoice draft for review – not a valid invoice for tax purposes",
    "pdf.payment.draft": (
        "Payment term: {days} days from the invoice date. Please do not pay "
        "yet – the binding invoice will follow."
    ),
    "pdf.payment.draftImmediately": (
        "Payable immediately from the invoice date. Please do not pay yet – "
        "the binding invoice will follow."
    ),
    "pdf.closing.draft": (
        "Please review this draft. The invoice number and invoice date are "
        "assigned when the invoice is finalized."
    ),

    "email.review.subject": "Invoice draft for review – service period {period}",
    "email.review.intro": (
        "we have prepared a draft of your charging invoice for the service "
        "period {period} amounting to {amount}. Please review it after "
        "signing in to the portal:"
    ),
    "email.review.deadline": (
        "Unless we hear from you, the invoice will be issued on {date} and "
        "sent to you. If you have questions or objections before then, "
        "choose “Question about the invoice draft” on the draft."
    ),

    "billing.waiting.subject": "Automatic billing is waiting for charging data ({period})",
    "billing.waiting.body": (
        "the invoice drafts for the service period {period} have not been "
        "created yet because the charging sessions have not been fetched from "
        "the Hager Cloud up to the end of the period (last successful fetch: "
        "{last_fetch}).\n\nPlease check the automatic fetch. The drafts will "
        "be created as soon as a fetch has succeeded."
    ),
    "billing.never": "never",
    "billing.drafts.subject": "Automatic billing: invoice drafts for {period}",
    "billing.drafts.body": (
        "{count} invoice drafts were created for the service period {period} "
        "and sent to the customers for review. Unless a customer raises a "
        "question, they will be finalized and delivered on {date}."
    ),
    "billing.drafts.none": (
        "no invoice drafts were created for the service period {period}."
    ),
    "billing.section.skipped": "Not billed:",
    "billing.section.notifyFailed": (
        "The review email could not be sent (further attempts will follow; "
        "drafts are not finalized automatically without a delivered review "
        "email):"
    ),
    "billing.reason.existingDraft": "draft #{id} already exists for this period",
    "billing.finalized.subject": "Automatic billing: {count} invoice(s) finalized",
    "billing.finalized.body": (
        "the following invoice drafts were finalized after the review period:"
    ),
    "billing.section.sent": "Delivered by email:",
    "billing.section.postal": "Please send by post:",
    "billing.section.failed": "Errors (please check in the portal):",
    "billing.inquiry.subject": "Invoice draft put on hold – {name}",
    "billing.inquiry.body": (
        "{name} ({email}) has raised a question about invoice draft #{id} "
        "(service period {period}, {amount}). The draft has been put on hold "
        "and will not be finalized automatically.\n\nThe customer was asked "
        "to contact {contact} by email. Once resolved, please finalize the "
        "draft in the portal, or delete and recreate it:"
    ),
    "billing.link": "Open in the portal:",

    "email.subject.invoice": "Invoice {number}",
    "email.subject.cancellation": "Cancellation invoice {number}",
    "email.greeting": "Hello,",
    "email.portal.invoice": "Your charging invoice {number} is available for download in the portal:",
    "email.portal.cancellation": "Your charging cancellation invoice {number} is available for download in the portal:",
    "email.attachment.invoice": "Please find attached your charging invoice {number} as a PDF file.",
    "email.attachment.cancellation": "Please find attached your charging cancellation invoice {number} as a PDF file.",
    "email.closing": "Kind regards",

    "email.englishBelow": "(English version below)",
    "account.greeting.named": "Hello {name},",
    "account.invitation.subject": "Your access to {app}",
    "account.invitation.intro": (
        "An account has been created for you at {app}. Please set your "
        "personal password using the following link:"
    ),
    "account.reset.subject": "Reset your password for {app}",
    "account.reset.intro": "You can set a new password using the following link:",
    "account.linkValidity": (
        "The link can be used once and is valid for {minutes} minutes. If you "
        "did not request this message, you can ignore it."
    ),

    "test.smtp.subject": "mail server test",
    "test.smtp.body": "This test message confirms that the mail server settings work.",
    "test.smime.subject": "S/MIME test",
    "test.smime.body": "This signed test message confirms that the S/MIME settings work.",
}
