# A client's non-billable flag defaults an entry's status; the entry records the truth

Time entries could only be `unbilled` or `billed`, so work that will never be invoiced —
pro-bono clients, internal projects, admin — either sat in the unbilled pool waiting to be
invoiced or was never logged. We added a third Time Entry Status, `non-billable`, and an
optional `"non_billable": true` on the client record. The client flag is consulted *only
when an entry is created* (`add-time`, the timer app); the status written into the time log
is the historical truth and is never re-derived from the client record. `add-time` takes
`--non-billable` / `--billable` to override the default for one entry. Billable remains the
default: a record without the key, or with it `false`, is billable, so every existing
`clients.json` keeps working untouched.

This mirrors the snapshot discipline the invoice log already uses for `Rate`, which is
stored at issue time so editing a client's rate cannot change what an issued invoice
charged. A client's billable relationship is at least as mutable as its rate — pro-bono
becomes paid, a paying client becomes an internal project — and history must not move
underneath it.

## Considered options

**Deriving the status from the client flag at read time**, with no third status value.
Rejected because flipping the flag would silently rewrite months of history: rows already
`billed` would start reading as non-billable, and previously non-billable rows would appear
in the billing candidate set. It would also force `filter_time_entries()` — today a pure
function over parsed CSV rows — to take the client mapping, coupling the time-log reader to
`clients.json`.

**A per-entry status only**, with nothing on the client record. Rejected because the whole
point is a client whose work is never billed; requiring a flag on every entry is friction
that will eventually be forgotten, and a forgotten flag silently produces an invoiceable
row.

**Spelling it `non-billed`.** Rejected because it contains `billed` as a substring, which
makes every existing `"billed" in output` assertion — and any future log grep — ambiguous.
`non-billable` contains only `billable`, which nothing tests for.

## Consequences

`mark_entries_billed()` now tests for `status == unbilled` rather than
`status != billed`. The old negative predicate meant "anything not already billed", so a
non-billable row sharing a `(start, end, client)` key with a billed one would have been
silently swept onto an invoice, and any status added later would have been billable by
default. A blank or hand-edited garbage status is consequently no longer promoted to
`billed` either — strictly safer, and only reachable by editing the CSV by hand.

`invoice` refuses a non-billable client immediately after resolving it, before the invoice
number is chosen and before any file is written, so nothing is left to clean up and no
number is burned. Rates are therefore optional on such a client, which also closed a
pre-existing bug: `rate_hr` was first read by the invoice-log append, which runs *after*
the `.xlsx` and `.pdf` are written, so a missing rate raised a bare `KeyError` and orphaned
both files. `make_invoice()` now raises `ClientRateError` before opening the template.

`list-time` gained the status as a filter choice, and breaks its total into billable and
non-billable lines when — and only when — the matched entries mix the two, so invoiceable
minutes are never read off a mixed figure.
