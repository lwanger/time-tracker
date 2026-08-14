# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-13

The first public release. Everything below 1.0.0 was developed privately, so this
entry covers every change since 0.3.0 rather than only the work done to publish.

### Added

- **`init` command and a four-layer configuration waterfall.** `time-tracker init`
  creates the directories, copies the invoice template, seeds `clients.json` and
  `invoices.json`, and writes `~/.time-tracker/.env` so every run finds the setup
  regardless of the working directory. Settings resolve through four layers, **merged
  per setting**: real `TT_*` environment variables, a `.env` in the current directory,
  the per-user config, then built-in defaults. `list-env` shows the resolved value
  *and* which layer supplied it, because a waterfall that cannot be traced is
  undebuggable. Every prompt has a flag, plus `--yes`, so the command can be scripted.
  See `docs/adr/0004-config-resolution-waterfall.md`.
- **The invoice template now describes itself.** Each template `.xlsx` carries a
  `Variables` worksheet (name, value, description); the invoice sheet references it by
  formula, so Excel keeps the references correct when cells move. This replaces the
  external cell map that used to live in `invoices.json`, which is now just the
  next-invoice counter. Eleven computed values that previously had no way to reach the
  page were added, `invoice_total` most importantly. Generating an invoice hard-errors
  naming *every* missing required variable before writing any file. See
  `docs/adr/0003-self-describing-invoice-template.md`.
- **An invoice log.** A single shared `invoices_log.csv` records every invoice issued —
  `InvoiceNum, Date, Client, Hours, Rate, Total, PaymentStatus, PaidDate` — with `Rate`
  and `Total` snapshotted at issue time. `invoice` appends a row as `unpaid` and refuses
  a number that already appears in the log. New `mark-paid` and `list-invoices`
  commands. See `docs/adr/0001-shared-invoice-log-file.md` and
  `docs/adr/0002-invoice-number-hard-error-void-deferred.md`.
- **`add-client` and `edit-client`.** `clients.json` was the one data file with no
  command behind it — the file every other command validates against was the file
  nothing validated on the way in. Both walk one shared prompt sequence and write only
  the fields actually set. A non-billable client is never asked for rates; the retainer
  pair is asked for together, and ending a retainer drops both keys, so half an
  agreement can never be billed as a whole one. Every field has a flag. Three
  deliberate refusals: the client code cannot be changed (it is recorded in every log
  row), a field Time Tracker does not recognise is preserved rather than dropped, and a
  `clients.json` that does not parse is refused rather than read loosely.
- **Non-billable clients and time entries.** A third time-entry status, `non-billable`,
  plus an optional `"non_billable": true` on the client record for time that will never
  be invoiced. The client flag is only the *default applied when an entry is created*;
  the entry's own status is the historical truth and is never re-derived, so changing
  the flag cannot rewrite months of history. `add-time` gained
  `--non-billable/--billable`, `list-time` gained the filter and splits its total when
  results mix, and `list-clients` grows a `Non-billable` column only when some client
  declares the flag. See `docs/adr/0005-non-billable-clients-and-time-entries.md`.
- **Standalone timer GUI (`timer-app`).** A small tkinter window for tracking work as
  it happens, sharing the same time log and configuration as the CLI: a client
  dropdown, an `HH:MM` readout, Start/Stop, a notes field, and a menu bar. Stopping
  shows the total and asks whether to save, warning about entries under a minute or
  with no notes. The client dropdown lists `Company Name (CODE)` sorted by company,
  since a bare code is an internal key rather than how anyone thinks about a client.
  The framework comparison behind the choice is in `docs/ui_framework_comparison.md`.
- **`time-tracker` and `timer-app` are installable console commands** (`uv tool install
  --editable .`), with `tt` as a short alias for `time-tracker`.
- **Client and billing status on time entries.** The time-log CSV schema is
  `Start,End,Elapsed,Client,Status,Notes`. `add-time` prompts for a client validated
  against `clients.json`; `list-time` filters by client and by status; `invoice` bills
  a client's unbilled entries — all of them or a date-range subset — shows them for
  confirmation, and marks them `billed` once the invoice is written.
- **Flags on every prompt in `add-time` and `set-next-inv`**, plus `--yes`, so both run
  unattended. Every failure path exits non-zero.

### Changed

- **Windows, Linux and macOS are all supported**, on Python 3.12, 3.13 and 3.14. One
  command is not uniformly portable: `invoice` renders its PDF through Excel over COM,
  so off Windows it writes the `.xlsx`, logs it, marks the entries billed, prints a
  notice and exits 0. The `.xlsx` *is* the invoice; the PDF is a rendering of it. See
  `docs/adr/0008-cross-platform-with-windows-only-pdf.md`.
- **`pywin32` is now a Windows-only dependency**, declared with an environment marker,
  and imported inside the one function that uses it.
- **The timer GUI requires tkinter to be installed**, which Debian, Ubuntu, Fedora and
  Homebrew all package separately from Python itself. The CLI does not import it, so
  every command works without Tk; only `timer-app` needs it. See the README.
- **The GUI is `Time Tracker Timer`.** The `LPC` product branding is retired from
  everything user-visible; the icon files are now `timer.ico` and `assets/**/timer-*.png`.
  `docs/adr/0006-mit-license-and-copyright-holder.md` carries an amendment note.
- **`requires-python` is now `>=3.12`** — what Ubuntu LTS and most Homebrew installs
  have. Nothing in the code needs anything newer.
- **Configuration keys carry a `TT_` prefix**, so it is clear which settings belong to
  this tool.
- **The code is organised by what it holds rather than by part of speech.** Two files
  of 2,155 and 1,179 lines became a module per command area (`time_tracker_clients`,
  `time_tracker_time`, `time_tracker_invoices`, `time_tracker_init`) over a module per
  thing the tool stores or produces (`time_tracker_json`, `time_tracker_client_record`,
  `time_tracker_time_log`, `time_tracker_invoice_log`, `time_tracker_template`,
  `time_tracker_invoice`). No data module imports a command module, so the dependencies
  run one way and each file can be read on its own. The test suite split the same way,
  one module per source module.
- **Rejecting a client confirmation now offers another pass** with the entered values
  as defaults, instead of discarding nine good answers because of one bad one.
- **`list-time`'s status filter defaults to what the chosen client's time is actually
  recorded as** — `non-billable` for a non-billable client, `unbilled` otherwise —
  rather than always defaulting to a filter that could only ever return nothing.
- `init` writes indented JSON, since these files are read and diffed by people.
- The README documents how a template becomes an invoice, and what does and does not
  constrain a template of your own design.

### Fixed

- **`init` could silently undo a customized setup.** It wrote a hand-maintained
  *subset* of settings, so anything nobody remembered reverted to a default pointing
  somewhere else — a relocated invoice counter restarting numbering at 1, a shared
  client list hidden behind a seeded sample, a split layout collapsed onto the data
  directory. The default is now inverted: every settable setting that differs from what
  `init`'s own choices would produce is written through, so omission cannot drop
  anything. Guarded by contract tests that parametrize over every setting.
- **Setting a derived value (`TT_TIME_LOG_FILE`, `TT_INVOICES_LOG_FILE`) was silently
  ignored.** Time Tracker now warns, naming the layer it was set in and what to set
  instead.
- **A stray backtick printed on retainer invoices.** The shipped template stored the
  `indent` variable as a literal backtick plus spaces — a mix-up with Excel's
  text-force prefix, which is an apostrophe and is not stored as data. Hourly clients
  were unaffected, which is why nothing had caught it.
- **`mark_entries_billed()` tested "not already billed"**, so a `non-billable` row
  sharing a start/end/client key with a billed one could be swept onto an invoice. It
  now tests for `unbilled` positively.
- **A client with no `rate_hr` orphaned both invoice files.** The rate was first read
  by the invoice-log append, which runs *after* the `.xlsx` and PDF are written, so a
  bare `KeyError` left both on disk with nothing recorded. Both `invoice` and
  `make_invoice()` now refuse before anything is written.
- **A non-numeric `TT_MAX_MINUTES_CONFIRMATION` blew up inside `add-time`.** It now
  raises at load time naming the file to fix — except for `init` itself, which must
  stay reachable to rewrite the bad value.
- An empty setting (`TT_FOO=`) counts as unset and falls through to the next layer,
  instead of blanking a path.

### Internal

These are not user-visible, but they are why the release is trusted.

- **Continuous integration**: the suite runs on Ubuntu, Windows and macOS across Python
  3.12, 3.13 and 3.14, installed from the lockfile with `uv sync --locked`. A separate
  job gates `ruff check` (including missing annotations), `ty check`, coverage, and
  `pip-audit` over the runtime dependencies.
- **448 tests, 100% coverage** of the measured modules, up from 370 at 99%. One is
  Windows-only and skips elsewhere: it asserts that a backslash and a forward slash
  spell the same path, which is true only where the backslash is a separator.
- **Two contract tests**, both written after something changed underneath the suite
  without a single test noticing: one parametrizes over every settable configuration
  key, the other binds every real `cooked_input` call site in the source against the
  installed package's signatures.
- `cooked_input` was fixed upstream and the pin moved to `0.7.0`, which removes the
  `veryprettytable` dependency and its import-time syntax warnings.

## 0.3.0 - 2026-08-05

### Added

- **Released under the MIT License.** The project previously had no license, which
  under default copyright meant nobody could legally use it. The copyright holder is
  Leonard Wanger personally rather than LP Consulting, and every byline and notice in
  the tree now uses that one name. `LPC` remains the product branding (`LPC Timer`,
  the application icon), which the copyright grant does not cover. See
  `docs/adr/0006-mit-license-and-copyright-holder.md`.

### Changed

- **Renamed the project from `invoicer` to `time-tracker`.** The tool had broadened
  well past invoice generation — it tracks time, manages clients, and keeps a time
  log and an invoice log — so the name no longer described it. No data formats
  changed: `clients.json`, `invoices.json` and the CSV logs are read as before, and
  the `TT_*` configuration keys are unchanged.
- The console command is now `time-tracker`, with `tt` installed as a short alias.
  The distribution is `time-tracker`, and every `invoicer_*.py` module is now
  `time_tracker_*.py`.
- The per-user config moved from `~/.invoicer/.env` to `~/.time-tracker/.env`. The
  old location is **not** read as a fallback; re-run `init` to write the new one.
- `init`'s default data directory moved from `~/invoicer` to `~/time-tracker`.
- The shipped invoice template's `Variables` sheet now names Time Tracker in its
  section headers and descriptions. Only the descriptive text changed — no variable
  name, cell or formula moved.

### Upgrading

Move `~/invoicer` to `~/time-tracker` (or pass `init --data-dir`/`--log-dir` pointing
at the old location) **before** re-running `init`. Re-running it without doing so
seeds an empty data set at the new default and writes a config pointing at that,
leaving your real invoices and next-invoice counter unused in `~/invoicer`. See
"Upgrading from `invoicer`" in `README.md`.

## 0.2.0 - 2026-06-09

### Added

- `set-next-inv` command to view and update the next invoice number.
- `list-env` command to display the current environment settings as a table.
- `list-clients` command to list all clients (and their fields) as a table.
- Confirmation step in `add-time` showing the date, start/end times, and total
  before logging, with re-entry (previous values as defaults) when rejected.
- Application version number and `--version` / `-V` flag.
- pytest test suite with its own `tests/` environment and sample data, reaching
  100% coverage of `invoicer.py` and `invoicer_funcs.py`; coverage results and
  data-file formats documented in `README.md`.

### Changed

- `list-time` output is now rendered as a table with a date-range total.
- Split the legacy `args.json` into `clients.json` (client data) and
  `invoices.json` (invoice template and next invoice number).
- Configuration is now loaded from `.env` (via python-dotenv) instead of
  `CONSTANTS.py`.
- Added type hints across all functions and methods.
- Replaced `readme.txt` with a Markdown `README.md`.

[1.0.0]: https://github.com/lwanger/time-tracker/releases/tag/v1.0.0

Releases 0.2.0 and 0.3.0 predate this repository and have no tags here: the project
was developed privately and its public history begins at 1.0.0. They are documented
above because the work is in the released code, not because it can be checked out.
See `docs/adr/0007-fresh-public-history.md`.