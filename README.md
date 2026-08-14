# Time Tracker

*Time Tracker* is a Python CLI tool for tracking time and creating monthly client invoices.
Time is logged via CLI commands (*add-time*), or the included *timer-app* GUI tool. 
Invoices are generated as Excel spreadsheets and exported to PDF, with invoices are 
logged to a CSV file. Configuration and data live in JSON files (`clients.json`, 
`invoices.json`) and environment settings (`.env`).

This is a light-weight, file-based tool that is good for personal use with a small 
number of invoices.

Project home: <https://github.com/lwanger/time-tracker>

Author: Leonard Wanger, 2026


## Platform support

Time Tracker runs on **Windows, Linux and macOS**, on **Python 3.12, 3.13 and 3.14**.
Every combination is exercised by CI.

One command is not uniformly portable. `invoice` writes the invoice as an Excel
workbook and then asks Excel to render that workbook to PDF, which goes through COM
and so only happens on Windows. Everywhere else the command does everything else it
normally does — writes the `.xlsx`, appends the invoice-log row, marks the time
entries `billed` — then prints:

```
PDF export requires Excel on Windows - open and print <path to the .xlsx>
```

and exits 0. **The `.xlsx` is the invoice; the PDF is a rendering of it.** Off Windows
you have a complete invoice and can produce the PDF by opening the workbook and
printing it. The reasoning, including why LibreOffice was not used as a fallback, is in
`docs/adr/0008-cross-platform-with-windows-only-pdf.md`.

`pywin32` is only installed on Windows (it is declared with an environment marker), so
nothing about the install is Windows-specific either.

## Known limitations

* **PDF export needs Excel on Windows**, as above. Everything else is pure Python.
* **The invoice template is an Excel workbook.** Designing your own means having
  something that can edit `.xlsx` with formulas — see
  [Designing your own invoice](#invoice-template). Time Tracker never rewrites the
  template's layout, only the values on its `Variables` sheet.
* **Data files are read and written whole, with no locking.** Two Time Tracker
  processes writing at once can lose a change. This is a single-user tool.
* **Client codes cannot be renamed.** The code is recorded in every time-log and
  invoice-log row, so `edit-client` deliberately refuses to change it; there is no
  migration path for the history it would orphan.
* **An invoice cannot be voided or reissued.** A number that already appears in the
  invoice log is a hard error, and there is no command to undo one
  (`docs/adr/0002-invoice-number-hard-error-void-deferred.md`).
* **The timer GUI's window is verified by hand.** Its pure helpers are unit-tested;
  the tkinter view is not (see [Coverage](#coverage)).

## Install

Note: to avoid having to use the command: *uv run* to run *time-tracker* and *timer-app*,
use *uv tool install*

```
 uv tool install --editable . 
 uv tool update-shell
``` 

This allows running them with just the tool name:

```time-tracker list-clients
```timer-app

`tt` is installed as a short alias for `time-tracker`, so `tt list-clients` and
`tt add-time` do the same thing as the full name.

## Upgrading from `invoicer`

This tool was called *invoicer* through 0.2.0. The 0.3.0 rename changed the command
name, the module names and the per-user config location, but no data formats — your
`clients.json`, `invoices.json` and CSV logs are read exactly as before.

**Move your data directory before re-running `init`.** The old config at
`~/.invoicer/.env` is no longer read, and `init`'s default data directory moved from
`~/invoicer` to `~/time-tracker`. If you re-run `init` without moving anything, it
seeds an *empty* set of data files at the new default and writes a config pointing at
them — leaving your real invoices, clients and next-invoice counter behind in
`~/invoicer`, still on disk but no longer used.

Either move the directory to match the new default:

```
mv ~/invoicer ~/time-tracker
time-tracker init
```

or keep your data where it is and point `init` at it (`--log-dir` too, if your CSV
logs live somewhere other than the data directory):

```
time-tracker init --data-dir ~/invoicer --log-dir ~/invoicer/time_logs
```

Then confirm with `time-tracker list-env` that every path resolves to your real data,
and `time-tracker list-clients` that your clients still parse. The old `~/.invoicer/`
directory can be deleted once you have.

## Setup

Run `time-tracker init` once after installing:

```
time-tracker init
```

It prompts for two directories — one for your invoices and JSON data files, one for
the time-log and invoice-log CSVs — then:

* creates them if they do not exist,
* copies the blank invoice template into the data directory,
* seeds `invoices.json` with the starting invoice number you choose (default 1),
* seeds `clients.json` with a `SAMPLE` client record to copy,
* writes `~/.time-tracker/.env` so every run finds this setup regardless of the current
  working directory.

**Existing data files are never overwritten.** Re-running `init` to change a directory
reports the files it kept, along with the current next-invoice number, and rewrites only
the `.env`. Pass `--force` to overwrite data files — note that replacing `invoices.json`
resets the invoice counter, and duplicate invoice numbers are a hard error.

**A customized setup survives a re-run.** `init` preserves anything you have already
configured rather than resetting it to a default that points somewhere else:

* a renamed or relocated `clients.json`, `invoices.json` or template stays where it is —
  no placeholder is seeded at the default path to compete with it,
* a split layout (clients or invoices JSON kept outside the data directory) is not
  collapsed onto the data directory,
* a renamed time log, a renamed invoice log and a changed warning threshold are written
  through to the new config.

Settings you have *not* customized are left commented out in the generated file, showing
the value they resolve to, so they keep tracking the built-in defaults.

Flags for every prompt, so the command can be scripted:

| Flag | Purpose |
| --- | --- |
| `--data-dir` | Invoices, `clients.json`, `invoices.json` |
| `--log-dir` | `time_log.csv`, `invoices_log.csv` |
| `--clients-dir` / `--invoices-dir` | Split these out from the data directory |
| `--next-invoice` | Starting invoice number (fresh setup only) |
| `--advanced` | Also prompt for the clients and invoices directories |
| `--force` | Overwrite existing data files |
| `--yes` / `-y` | Accept all defaults without prompting |

Two things still have to be done by hand, and `init` prints both when it finishes:

1. **Customize the template** — 
replace the issuer details (your business name, address
   and phone) on the invoice sheet. They are static text, not variables. See
   [Invoice template](#invoice-template).
2. **Add your clients** — edit `clients.json`, copying the `SAMPLE` record.

Then check the result with `time-tracker list-env` and `time-tracker list-clients`.

## Configuration

Settings are `TT_`-prefixed environment variables. They resolve through four layers,
**merged per setting** — a layer that supplies one value does not suppress the others:

| Precedence | Layer | Use |
| --- | --- | --- |
| 1 (highest) | Real `TT_*` environment variables | One-off overrides |
| 2 | `.env` in the current directory | Per-project or per-checkout overrides |
| 3 | `~/.time-tracker/.env` | Your normal setup, written by `time-tracker init` |
| 4 (lowest) | Built-in defaults | Relative paths under the current directory |

`time-tracker list-env` shows every resolved value **and the layer it came from**, which is
the way to answer "why is it using that path?":

```
| Variable         | Value                     | Setting               | Source                     |
| TT_INV_SAVE_DIR  | D:/work/invoices          | Invoice Save Directory | C:\Users\me\.time-tracker\.env |
| TT_TIME_LOG_FILE | D:/work/logs/time_log.csv | Time Log File Path     | (derived)                  |
```

`(default)` means no layer set it; `(derived)` means it is composed from other settings
(a directory plus a filename) and is not settable on its own. Setting a derived value
directly has no effect, so Time Tracker warns and names what to set instead:

```
Warning: TT_TIME_LOG_FILE is set in C:\Users\me\.time-tracker\.env but is computed from
other settings, so it is ignored - set TT_LOG_SAVE_DIR and TT_TIME_LOG_FILENAME instead.
```

The per-user file is `~/.time-tracker/.env` rather than a bare `~/.env`, because any
dotenv-using tool run from a directory below your home directory would pick that up.
Paths in it are written with forward slashes: dotenv treats a backslash inside a quoted
value as an escape sequence, and Windows accepts forward slashes everywhere.

| Setting | Default | Meaning |
| --- | --- | --- |
| `TT_INV_SAVE_DIR` | `./invoices` | Where generated invoices are written |
| `TT_LOG_SAVE_DIR` | `./time_logs` | Where the time and invoice logs live |
| `TT_CLIENTS_JSON_DIR` | `TT_INV_SAVE_DIR` | Directory holding `clients.json` |
| `TT_INVOICES_JSON_DIR` | `TT_INV_SAVE_DIR` | Directory holding `invoices.json` |
| `TT_CLIENTS_FILE` | `<clients dir>/clients.json` | Full path, if it is not in that directory |
| `TT_INVOICES_FILE` | `<invoices dir>/invoices.json` | Full path, if it is not in that directory |
| `TT_TEMPLATE_FILE` | `<invoices dir>/Invoice - blank.xlsx` | The invoice template |
| `TT_TIME_LOG_FILENAME` | `time_log.csv` | Time-log filename within the log directory |
| `TT_INVOICES_LOG_FILENAME` | `invoices_log.csv` | Invoice-log filename within the log directory |
| `TT_MAX_MINUTES_CONFIRMATION` | `240` | `add-time` asks twice above this many minutes |

## Commands

| Command | Description |
| --- | --- |
| `init` | Set up directories, seed the data files and write the configuration (see [Setup](#setup)) |
| `invoice` | Create an invoice for a client from its unbilled time entries (spreadsheet + PDF), logging it to the invoice log |
| `add-time` | Add a time-log entry for a client (with confirmation), optionally non-billable |
| `list-time` | List time-log entries (filter by client / status / date range) and total the hours |
| `list-invoices` | List logged invoices (filter by client / payment status) and total the amount |
| `mark-paid` | Mark a logged invoice as paid |
| `add-client` | Add a client to `clients.json` (prompted and confirmed) |
| `edit-client` | Change an existing client's details or rates |
| `list-clients` | List all clients as a table |
| `list-env` | Show the resolved settings and which config layer supplied each one |
| `set-next-inv` | Show and update the next invoice number |

Any prompt can be cancelled by entering `/cancel`. Run `time-tracker --version` to print
the version.

## Data files

Configuration was originally a single `args.json`; it is now split into `clients.json`
(client records) and `invoices.json` (the next invoice number). The invoice template is
a separate Excel file that describes its own fields. The locations of all of these are
resolved from the environment (see `list-env`).

### `clients.json`

A mapping of client code to a record of client fields. Each record requires the core
fields below; the `retainer_*` fields are optional and, when present, bill a fixed
monthly retainer for the first *N* hours with any additional hours charged at the
hourly rate.

```json
{
  "TEST": {
    "company": "FakeCo",
    "contact": "Fake Client",
    "phone": "(123) 456-8900",
    "addr1": "Fake addr1",
    "addr2": "Fake City, FS 00000",
    "rate_hr": 100,
    "rate_day": 800
  },
  "RET": {
    "company": "Retainer Corp",
    "contact": "Retainer Contact",
    "phone": "(555) 000-0001",
    "addr1": "100 Retainer Blvd",
    "addr2": "Chicago, IL 60601",
    "rate_hr": 100,
    "rate_day": 800,
    "retainer_hrs": 20,
    "retainer_rate": 1500
  },
  "PRO": {
    "company": "Pro Bono Inc",
    "contact": "Pro Bono Contact",
    "phone": "(555) 000-0002",
    "addr1": "1 Volunteer Way",
    "addr2": "Springfield, IL 62701",
    "non_billable": true
  }
}
```

| Field | Required | Description |
| --- | --- | --- |
| `company` | yes | Client company name |
| `contact` | yes | Contact person |
| `phone` | no | Contact phone number |
| `addr1`, `addr2` | no | Two address lines |
| `rate_hr` | yes\* | Hourly billing rate |
| `rate_day` | no | Daily billing rate |
| `retainer_hrs` | no | Hours covered by a fixed monthly retainer |
| `retainer_rate` | no | Fixed monthly retainer amount |
| `non_billable` | no | `true` to track this client's time without ever invoicing it |

\* Not needed on a non-billable client, which is never invoiced.

An optional field a template does not reference can simply be left out; the invoice
sheet's `IF(...<>"")` guards handle the blank. `add-client` writes only the fields you
actually set, for the same reason.

**Non-billable clients.** Setting `"non_billable": true` means the client's time is logged
and reported like anyone else's, but never billed: new entries are recorded as
`non-billable` instead of `unbilled`, they are never offered when creating an invoice, and
`invoice` refuses the client outright. Use it for pro-bono work, internal projects or
admin time you still want a record of.

The flag is **opt-in and only a default**. A client that does not declare it is billable,
exactly as before, so an existing `clients.json` needs no change. And because the flag is
read only when an entry is created, turning it on or off later never rewrites time already
logged — each entry keeps the status it was recorded with.

#### Adding and editing clients

`clients.json` can be edited by hand, but `add-client` and `edit-client` do it with
validation and a confirmation step:

```bash
time-tracker add-client                  # prompts for every field
time-tracker edit-client                 # pick a client from a list, then edit it
time-tracker edit-client --client TEST   # or name it up front
```

Both walk the same sequence — company, whether the client is billable, contact details,
rates, then retainer — and only write the fields that are actually set, so records stay
as terse as the hand-written ones. Two questions gate the rest: a **non-billable** client
is not asked for rates (it is never invoiced), and the retainer pair is asked for only if
you say the client has one. `edit-client` offers the current values as defaults and shows
what is changing before writing anything.

Answering *no* at the final confirmation does not throw the answers away: it offers
another pass with everything you just entered as the defaults, so a single wrong field is
a matter of retyping that one. Declining that second offer is what cancels.

Every field has a flag, so either command can be scripted. Anything not given is prompted
for; `--yes` accepts the current or default answer for the rest, including the final
confirmation:

```bash
time-tracker add-client --code ACME --company "Acme Inc" --contact "Jane Roe" \
    --rate-hr 150 --yes
time-tracker add-client --code PRO --company "Pro Bono Inc" --contact "Pat" \
    --non-billable --yes
time-tracker edit-client --client ACME --rate-hr 17.50 --yes
```

Rates are stored as entered, so `$17.50/hr` round-trips exactly.

Three things the commands deliberately will not do:

- **Change a client's code.** It is recorded in every time-log and invoice-log row, so
  renaming it would orphan that history. Everything else, the company name included, is
  editable.
- **Clear an optional field.** Pressing enter keeps the current value; removing `phone`
  or `addr2` altogether is still a hand edit. The exceptions are the two that have a
  yes/no gate: answering *no* to the retainer question drops `retainer_hrs` and
  `retainer_rate` together, and answering *yes* to "is this client billable" removes
  `non_billable`.
- **Rewrite a file it could not read.** A `clients.json` that does not parse is reported
  and left alone, rather than being replaced by whatever could be salvaged from it.

Fields Time Tracker does not recognise are preserved: the file is yours, and an edit will not
drop a key it has no opinion about.

### `invoices.json`

Holds only the next invoice number, used as the default when creating an invoice and
advanced automatically afterwards. `set-next-inv` shows and changes it.

```json
{"next_invoice": 102}
```

Earlier versions also stored a `template` object mapping invoice fields to spreadsheet
cell references. That map now lives inside the template itself (see below); a leftover
`template` key is ignored.

### How an invoice is produced

Invoices are generated from Excel workbooks whose path comes from
`TT_TEMPLATE_FILE`. The first page of the template contains the formatted invoice with
formulas referencing fields in the second sheet (`Variables`.) The `Variables` sheet lists 
every value Time Tracker can supply.

Invoices are created by copying the template to a new file and filling in the values
for the invoice (e.g. client, date, hours, amount, etc.) 

The `.xlsx` written this way is the invoice. Exporting it to PDF is a separate step
that goes through Excel (over COM) and so happens only on Windows; elsewhere the
command writes the workbook and says so. See [Platform support](#platform-support).

### Invoice template

The `Variables` sheet has three columns — `Variable` (A), `Value` (B), `Description`
(C) — one variable per row, with `[ ... ]` section headers separating groups. Rows whose
name cell is not a bare lowercase identifier are ignored, so headers and blank spacer
rows are free to move around.

To show a value on your invoice, set the cell to `=Variables!B<row>`. Guarding it keeps
an unused variable from printing as `0`:

```
C5   =IF(Variables!B3<>"",Variables!B3,"<inv #>")
C31  =Variables!B6
```

#### Designing your own invoice

The shipped template is a deliberately plain example, not a house style. Since the
invoice sheet reaches every value through a `=Variables!B<row>` formula, the design is
entirely yours: move fields around, restyle them, add a logo or letterhead, add columns,
drop the lines you do not bill on. Time Tracker only ever writes into the `Variables` sheet,
so it neither knows nor cares what the invoice sheet looks like.

What has to stay true for it to keep working:

* **The invoice sheet comes first.** The PDF export takes worksheet 1; keep the invoice
  sheet leftmost and `Variables` after it.
* **The variables sheet stays named `Variables`**, with names in column A, values in
  column B, descriptions in column C. Rows may move freely — lookups are by name.
* **Variable names are fixed.** Rename one and Time Tracker stops filling it. Rows whose
  column A is not a bare lowercase identifier are ignored, so `[ ... ]` section headers
  and blank spacers can be added or moved at will.
* **Update `print_area_lr`** whenever your layout grows past the old print area, or the
  PDF will be clipped.
* **Format cells, not values.** Time Tracker writes raw numbers and hours; apply currency
  and number formats in Excel to the cells that display them.
* **Do not build a template by copying sheets in from another workbook.** Excel records
  an external link, the formulas then read the *source* workbook and Excel refuses to
  open the generated invoice. Time Tracker detects this and refuses up front; repair an
  affected template with
  `python tools/repair_template_external_links.py "<template.xlsx>"`.

**Variables Time Tracker fills in**

| Variable | Description |
| --- | --- |
| `invoice_num`&nbsp;\*, `invoice_date`&nbsp;\* | Invoice number and issue date |
| `invoice_period` | Billing period being invoiced, e.g. `May 2026` |
| `invoice_year`, `invoice_month` | Year and month number of that period |
| `invoice_total` | Total amount due |
| `invoice_hours` | Hours billed |
| `invoice_rate_per_hour`, `invoice_rate_per_day` | The client's rates |
| `invoice_desc1..3`, `invoice_amt1..3` | Line-item descriptions and amounts |
| `invoice_retainer_amount` | Retainer portion of the total (retainer clients) |
| `invoice_overage_hours`, `invoice_overage_amount` | Hours beyond the retainer, and their value |
| `cust_code` | The client's short code, e.g. `RET` |
| `cust_company`&nbsp;\*, `cust_contact`&nbsp;\* | Client company and contact name |
| `cust_addr1`, `cust_addr2`, `cust_phone` | Client address and phone (phone is unlabelled — add any `Phone:` prefix in the template) |
| `cust_retainer_hrs`, `cust_retainer_rate` | The client's retainer terms |

**Variables you set yourself** — Time Tracker never overwrites these:

| Variable | Description |
| --- | --- |
| `invoice_for` | Free-text "for" line |
| `invoice_status` | Status text to print on the invoice |

**Template settings** — read by Time Tracker, not written:

| Variable | Description |
| --- | --- |
| `indent` | Leading whitespace prefixed to the retainer sub-lines Time Tracker writes into `invoice_desc2`/`invoice_desc3` |
| `print_area_ul`&nbsp;\*, `print_area_lr`&nbsp;\* | Upper-left / lower-right cells of the PDF print area |

\* Required. If any starred variable is missing — or the `Variables` sheet itself is —
`invoice` reports exactly what is absent and exits without writing any file. Every
other variable is optional: a template uses whichever it needs, and the rest are simply
left blank.

Your own business details (name, address, phone) are **plain text on the invoice
sheet**, not variables. Edit them directly in the spreadsheet.

A starter template ships in `time_tracker_templates/`, alongside an `invoices.json` seed;
`init` copies it into your data directory. To run more than one design — a different
look per client, say — keep each as its own `.xlsx` and point `TT_TEMPLATE_FILE` at the
one you want, either in `.env` or as a one-off environment variable for a single
`invoice` run.

### Time log (CSV)

`add-time`, `list-time`, and `invoice` read and write a CSV time log with the columns
`Start,End,Elapsed,Client,Status,Notes`. `Start` and `End` are ISO 8601 timestamps,
`Elapsed` is the duration in whole minutes, `Client` is a client code from
`clients.json`, and `Status` is one of:

| Status | Meaning |
| --- | --- |
| `unbilled` | Not invoiced **yet** — the pool `invoice` bills from |
| `billed` | Already included on an invoice |
| `non-billable` | Excluded from invoicing entirely; never offered to `invoice` |

```csv
Start,End,Elapsed,Client,Status,Notes
2026-05-01T09:00:00,2026-05-01T10:30:00,90,TEST,billed,May work
2026-06-02T13:00:00,2026-06-02T14:00:00,60,TEST,unbilled,June work
2026-06-16T09:00:00,2026-06-16T10:30:00,90,PRO,non-billable,Pro bono board meeting
```

`add-time` prompts for the client (validated against `clients.json`) and records new
entries as `unbilled`, or as `non-billable` when the client is marked
[non-billable](#clientsjson). `--non-billable` / `--billable` override that for a single
entry — to log unbillable time against a paying client, or to bill one item for an
otherwise non-billable one. Either way the status is shown in the summary before you
confirm.

```bash
time-tracker add-time --client TEST --non-billable   # this entry only, not billed
time-tracker add-time --client PRO --billable        # bill this one after all
```

`list-time` filters by billing status: `unbilled`, `billed`, `non-billable`, or `all`.
Supply it with `--status` or, when omitted, choose it at the prompt. The client can be
given with `--client` or, when omitted, is prompted for and validated against
`clients.json` (blank = all clients). A date range is always prompted for.

The status offered at the prompt **follows the client**: `non-billable` for a
non-billable client, `unbilled` for everyone else. Otherwise listing a pro-bono client
would default to the one status its time is never recorded with, and show an empty table.
`--status` always overrides it.

```bash
time-tracker list-time --client TEST --status billed        # TEST's billed entries
time-tracker list-time --status non-billable                # what was never billable
time-tracker list-time --status all                         # all clients, every status
time-tracker list-time                                      # prompts for client and status
```

When the results mix billable and non-billable time, the total is broken out so
invoiceable minutes are never read off a mixed figure:

```
Total: 180 minutes (3.00 hours)
  Billable:     150 minutes (2.50 hours)
  Non-billable: 30 minutes (0.50 hours)
```

### Billing time with `invoice`

By default `invoice` bills a client from its **unbilled** time entries:

1. Pick the client (and invoice number). A non-billable client is refused here, before
   the number is chosen and before any file is written. The invoice number must not
   already exist in the invoice log; a duplicate is a hard error, before any files are
   generated.
2. Choose to bill *all* unbilled entries, or a date-range subset. `non-billable` entries
   are never among the candidates, even for a billable client, and are never marked
   `billed`.
3. The selected entries and the computed total hours are shown for confirmation.
4. On accept, the invoice is generated, logged to the invoice log as `unpaid`, and
   those entries are marked `billed` in the time log.

Passing `--inv-hrs N` skips the time-entry flow and bills `N` hours directly (the
entries are left untouched).

### Invoice log (CSV)

`invoice`, `list-invoices`, and `mark-paid` read and write a single shared CSV invoice
log (not one file per client) with the columns
`InvoiceNum,Date,Client,Hours,Rate,Total,PaymentStatus,PaidDate`. `Rate` is the
client's hourly rate at the time of invoicing; `Total` is the full amount due
(retainer-aware, computed once and reused for both the spreadsheet and this log).
`PaymentStatus` is `unpaid` or `paid`; `PaidDate` is blank until `mark-paid` sets it.

```csv
InvoiceNum,Date,Client,Hours,Rate,Total,PaymentStatus,PaidDate
102,2026-06-01,TEST,10.00,100.00,1000.00,unpaid,
101,2026-05-01,TEST,8.00,100.00,800.00,paid,2026-05-20
```

`mark-paid` looks up an invoice by number (`--inv-num`, or prompted) and sets it to
`paid` with a `--paid-date` (or prompted, defaulting to today). It hard-errors if the
invoice number isn't found or is already paid.

`list-invoices` filters by payment status: `unpaid` (default), `paid`, or `all`
(`--status`, or prompted), and by client (`--client`, or prompted; blank = all
clients).

```bash
time-tracker mark-paid --inv-num 102 --paid-date 2026-07-15
time-tracker list-invoices --status unpaid          # who owes money
time-tracker list-invoices --client TEST --status all
```

## Timer app

`timer_app.py` is a standalone tkinter GUI for tracking work *as it happens* and
appending it to the **same** time log (and using the same `.env` configuration)
as Time Tracker. New entries are saved as `unbilled`, exactly like `add-time` — or as
`non-billable` when the selected client is marked non-billable, in which case the
stop-confirmation dialog says so before the entry is written.

```bash
uv run timer_app.py                              # open the timer
uv run timer_app.py --client IO --notes "Bugs"   # pre-fill client and notes
```

The optional `--client` / `--notes` flags pre-fill the UI; the timer is **not**
started automatically. An unknown `--client` is reported and left unselected.

### Window

- A **client** dropdown (populated from `clients.json`), listing each client as
  `Company Name (CODE)` — for example `FakeCo (TEST)` — sorted by company name. The
  code shown in parentheses is what gets written to the time log's `Client` column
  and what `--client` takes; a client with no `company` is listed by its code alone.
- A large **elapsed-time** readout in `HH:MM`, refreshed once a minute.
- **Start** / **Stop** buttons.
- A one-line **notes** field with an `✕` button to its right that clears it.

**Start** records the start time and begins the timer (the client cannot be
changed while running). **Stop** shows the total and asks whether to add the
entry to the time log; either way the timer resets to `00:00` while keeping the
selected client and notes so the next entry can reuse them.

While the timer is running it gives two visual cues: the elapsed-time readout
turns **green** and the window/taskbar title shows **`Time Tracker Timer — running`**.

When you stop, the confirmation dialog warns about entries that are **under a
minute** or have **no notes**; an entry with no notes defaults the dialog to
*No* so you can cancel and add notes before saving.

The title bar and taskbar use the app's stopwatch icon, shipped as the
multi-resolution `timer.ico` in the project root, with the PNGs under `assets/`
as a fallback on the platforms Tk cannot load an `.ico` on — which is everywhere
but Windows, and is why those PNGs are part of the repository. The app falls back
to Tk's default icon if neither is present.

### Menu bar

| Menu | Items |
| --- | --- |
| **File** | `Settings…` (shows the resolved `.env` paths: time-log filename, log save directory, clients file), `Exit` (prompts to save a running entry) |
| **Timer** | `Start` (Ctrl+S), `Stop` (Ctrl+T), `Clear Notes` |
| **Help** | `About` (app name, version, author, copyright, project URL) |

> The choice of tkinter (over Flet, Toga, PySide6/Qt, and JavaScript) is
> documented in `docs/ui_framework_comparison.md`. It adds no new dependencies.

## Code layout

Two layers. The **command** modules are grouped by the thing they act on, each
registering its own commands on the Typer app in `time_tracker_cli`, so adding a command
means editing one module and `time_tracker.py` only has to import it. Underneath, one
module per **thing Time Tracker stores or produces** — none of them import a command
module, so they can be read and tested on their own.

| Command module | Holds |
| --- | --- |
| `time_tracker.py` | The `time-tracker` entry point: load the config, then hand off to Typer |
| `time_tracker_cli.py` | The Typer app itself, `--version`, the `/help` and `/cancel` prompt commands, shared date parsing |
| `time_tracker_config.py` | The settings waterfall, the resolved values every command reads, and `list-env` |
| `time_tracker_clients.py` | `add-client`, `edit-client`, `list-clients` |
| `time_tracker_client_form.py` | The prompt sequence the first two share: which fields are asked for, and the confirmation |
| `time_tracker_time.py` | `add-time`, `list-time` |
| `time_tracker_invoices.py` | `invoice`, `list-invoices`, `mark-paid`, `set-next-inv` |
| `time_tracker_init.py` | `init` |
| `timer_app.py` | The standalone timer GUI (see [Timer app](#timer-app)) |

| Data module | Holds |
| --- | --- |
| `time_tracker_json.py` | Reading and writing `clients.json` and `invoices.json` |
| `time_tracker_client_record.py` | One client's record: its fields, their labels, validation and merging |
| `time_tracker_time_log.py` | The time-log CSV: its schema, and reading, filtering and writing entries |
| `time_tracker_invoice_log.py` | The invoice-log CSV: the record of every invoice issued, and its payment status |
| `time_tracker_template.py` | The invoice template's Variables sheet: reading, validating and filling it in |
| `time_tracker_invoice.py` | Generating an invoice: the amounts, the template values, the `.xlsx` and the PDF |

Nothing imports `time_tracker.py`; the dependencies run one way, from the command modules
down to the data modules, so there is no cycle. `time_tracker_invoice.py` is the one data
module that still prompts (for hours, when they are not supplied), which is why it
reaches back to `time_tracker_cli` for the prompt commands.

## Testing

Tests use `pytest` and live in the `tests/` directory, which has its own `.env` and
sample JSON/CSV data. Everything needed to run them is in the `dev` dependency group,
so `uv sync` then:

```bash
uv run pytest
```

There is one test module per source module. Each patches the module it exercises —
`patch("time_tracker_clients.read_json_args")` rather than a name on `time_tracker`. The
resolved settings are the exception: they are one dict shared by every module, so tests
patch its *contents* with `patch.dict(time_tracker_config.global_vars, ..., clear=True)`.
Fixtures used by more than one module (the sample clients, the template builders) live
in `tests/conftest.py`.

Two of them are contract tests rather than tests of behaviour, and both exist because
something once changed underneath the suite without a single test noticing.
`test_config_keys.py` parametrizes over every settable setting, so a newly added one
fails until it is handled everywhere. `test_cooked_input_contract.py` walks the source
for every real `cooked_input` call and binds it against the installed package's
signatures, so a renamed keyword or changed arity is caught on the next dependency
bump instead of at a prompt.

### Continuous integration

`.github/workflows/ci.yml` runs the suite on **Ubuntu, Windows and macOS** across
**Python 3.12, 3.13 and 3.14** — nine jobs, installed from `uv.lock` with
`uv sync --locked`, so a dependency edited without re-locking cannot reach a green
run. A separate job gates style and annotations (`ruff check`), types (`ty check`),
coverage, and known vulnerabilities in the runtime dependencies (`pip-audit`).

### Coverage

Run the suite with coverage measuring the application modules (the source list lives
in `pyproject.toml`):

```bash
uv run pytest --cov --cov-report=term-missing
```

Current coverage (447 tests passing):

| Module | Statements | Missing | Coverage |
| --- | ---: | ---: | ---: |
| `time_tracker.py` | 28 | 0 | 100% |
| `time_tracker_cli.py` | 36 | 0 | 100% |
| `time_tracker_client_form.py` | 113 | 0 | 100% |
| `time_tracker_client_record.py` | 40 | 0 | 100% |
| `time_tracker_clients.py` | 119 | 0 | 100% |
| `time_tracker_config.py` | 86 | 0 | 100% |
| `time_tracker_init.py` | 150 | 0 | 100% |
| `time_tracker_invoice.py` | 110 | 0 | 100% |
| `time_tracker_invoice_log.py` | 67 | 0 | 100% |
| `time_tracker_invoices.py` | 173 | 0 | 100% |
| `time_tracker_json.py` | 13 | 0 | 100% |
| `time_tracker_template.py` | 46 | 0 | 100% |
| `time_tracker_time.py` | 157 | 0 | 100% |
| `time_tracker_time_log.py` | 89 | 0 | 100% |
| `tools/repair_template_external_links.py` | 86 | 0 | 100% |
| **TOTAL** | **1313** | **0** | **100%** |

CI gates coverage at 99% — a ratchet below the current figure, not a target. The timer
GUI is the deliberate exclusion: `timer_app.py` is not in the measured source list, its
tkinter view is verified by hand, and its pure helpers are unit-tested in
`tests/test_timer_app.py`.

## Author

Leonard Wanger — 2015, 2026.

## License

Released under the [MIT License](LICENSE) — Copyright (c) 2015-2026 Leonard Wanger.
Use it, fork it, ship it inside something commercial; the only obligation is that
the copyright notice travels with it.

The application icon is product branding, not part of the copyright grant.
