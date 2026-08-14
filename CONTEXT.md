# Time Tracker

A Python CLI to track billable time and generate client invoices.

## Language

**Client**:
A billing entity identified by a short code (e.g. `TEST`, `RET`) with contact info and a rate, tracked in `clients.json`.
_Avoid_: Customer, account

**Time Entry**:
A single logged span of work (start, end, client, notes) recorded in the time log (`time_log.csv`).
_Avoid_: Log entry, session

**Time Entry Status** (`unbilled` / `billed` / `non-billable`):
Whether a time entry has been included on an invoice yet, or is excluded from invoicing entirely. Only an `unbilled` entry can become `billed`.
_Avoid_: Payment status, paid/unpaid (reserved for Invoice Payment Status)

**Non-billable**:
A time entry (or client) explicitly excluded from invoicing rather than merely not-yet-invoiced. Distinct from `unbilled`, which just means "not invoiced yet." A client's `non_billable` flag is only the *default* applied when an entry is created; the entry's own status is the historical truth and is never re-derived, so changing the flag cannot rewrite entries already logged. Billable is the default: a client that does not declare the flag is billable. Note the deliberate spelling split — the client-record key is `non_billable`, the status value is `non-billable`.
_Avoid_: Unpaid (reserved for Invoice Payment Status), non-billed (collides with `billed`)

**Retainer**:
A client's fixed monthly fee (`retainer_rate`) covering a set number of hours (`retainer_hrs`); hours beyond that are billed at the client's hourly rate (`rate_hr`).

**Invoice**:
A bill issued to a client for a set of hours, identified by a globally unique, sequentially assigned invoice number (`invoices.json`'s `next_invoice` counter). Its artifact is the generated `.xlsx` workbook: that is what Time Tracker writes, and it is complete on its own. The PDF is a *rendering* of that workbook, produced by asking Excel to export it — so it exists only where Excel does (Windows), and its absence elsewhere is not a missing invoice.
_Avoid_: Bill (only for the generated document itself, not the concept), PDF (that is one rendering, not the invoice)

**Invoice Log**:
The authoritative record of every issued invoice (`invoices_log.csv`), one row per invoice. Separate from `invoices.json`, which only holds the Excel template config and the next-invoice-number counter.
_Avoid_: Invoice history, ledger

**Invoice Payment Status** (`unpaid` / `paid`):
Whether payment has been received for an invoice, set on the invoice's row in the Invoice Log. Distinct from Time Entry Status despite both being billing-adjacent. Not to be confused with the `invoice_status` Template Variable, which is reserved and unfilled — Time Tracker never writes payment status onto an invoice.
_Avoid_: Status (ambiguous with Time Entry Status), Invoice Status

**Invoice Template**:
The Excel workbook (`.xlsx`) an invoice is generated from. Carries both the printed layout and, on its Variables Sheet, the definitions of the Template Variables it uses.
_Avoid_: Form, blank, invoice file (reserved for a generated invoice)

**Variables Sheet**:
The worksheet inside an Invoice Template that declares that template's Template Variables — one per row: name, value, description. Replaces the external cell map that previously lived in `invoices.json`.
_Avoid_: Cell map, field map, data sheet

**Template Variable**:
A named value on a Variables Sheet, referenced from the invoice sheet by formula. Three kinds: *filled* by Time Tracker when generating an invoice, *read* by Time Tracker as template configuration (`indent`, `print_area_ul`, `print_area_lr`), or *reserved* for the template author to set by hand (`invoice_for`, `invoice_status`). A variable no template references is available, not dead.
_Avoid_: Field, cell reference, placeholder

**Invoice Counter**:
The `next_invoice` value in `invoices.json` — the number the next invoice will be assigned. The only thing that file holds. Distinct from the Invoice Log, which records invoices already issued.
_Avoid_: Invoice number (that's the assigned identity), sequence

**Setting**:
One `TT_`-prefixed configuration value. A *resolved* setting also has a Source. Some settings are *derived* (composed from other settings, like a log directory plus a filename) and cannot be set directly.
_Avoid_: Environment variable (only layer 1 is actually one), option, parameter, config key

**Config Layer**:
One place a Setting can come from. Four, highest precedence first: real `TT_*` environment variables, a `.env` in the current directory, the User Config, then built-in defaults. Layers merge *per setting*, not per file.
_Avoid_: Config file (only two layers are files), profile, scope

**User Config**:
`~/.time-tracker/.env` — the per-user Config Layer that `init` writes and every run reads regardless of the working directory. Deliberately not a bare `~/.env`, which unrelated dotenv-using tools would also read.
_Avoid_: Global config (it is per user, not per machine), settings file, dotfile

**Source**:
Which Config Layer supplied a resolved Setting: a file path, `environment`, `(default)`, or `(derived)`. Shown by `list-env`, because a four-layer waterfall that cannot be traced is undebuggable.
_Avoid_: Origin, provenance, layer (that's the thing, this is which one won)