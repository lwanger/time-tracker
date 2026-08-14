# Hard error on duplicate invoice numbers; voiding deferred

`invoice` lets the user type any invoice number at the prompt, so once invoices are
logged to `invoices_log.csv`, a duplicate `InvoiceNum` is possible (typo, or
re-running after a mistake). We chose to hard-error on any duplicate rather than warn
and allow reuse, so `InvoiceNum` remains an unambiguous identity for `mark-paid` to
look up. We considered a "void an invoice, then reissue" flow for correcting mistakes,
but rejected it for now: `mark_entries_billed()` does not record which invoice number
billed a given time entry (it matches by `(start, end, client)` only), so an automatic
void-and-revert-to-unbilled flow isn't possible without first adding an `InvoiceNum`
link to the time log — a larger change. Voiding is deferred to its own future TODO
item. For now, a duplicate-number mistake is corrected by simply picking a different,
unused number.
