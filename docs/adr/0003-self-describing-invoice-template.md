# Invoice templates describe their own variables

The cell map lived in `invoices.json` as a `template` object of 21 name-to-cell entries
(`"invoice_num": "C5"`), read by `make_invoice()` as `ws[template['invoice_num']]`. That
map is only valid for one spreadsheet layout, so moving a box on the invoice silently
produced wrong invoices, and editing a template meant hand-editing JSON. We moved the
map *into* the template: each invoice `.xlsx` carries a `Variables` worksheet declaring
its own variables (column A name, column B value, column C description), and the invoice
sheet references them by formula (`=Variables!B3`). Excel maintains those references when
cells move, so layout edits can no longer desync from the map. `invoices.json` keeps only
`next_invoice`; the template path moves to `TT_TEMPLATE_FILE` in `.env`, and `indent` /
`print_area_ul` / `print_area_lr` move onto the variables sheet as template-read settings.

This inverts the contract. It is no longer "the template must define these 21 cells" but
"Time Tracker fills every variable it knows; each template references whichever it wants."
Unreferenced variables are therefore normal and expected, not dead — which is why the
four names nothing had ever used (`invoice_for`, `invoice_status`,
`invoice_rate_per_hour`, `invoice_rate_per_day`) were kept rather than deleted, and why
the vocabulary was *expanded* at the same time with values `make_invoice()` already
computed and discarded (`invoice_total`, `invoice_period`, `invoice_hours`, retainer and
overage amounts, and the client's rates). Someone else's template may want data ours
doesn't print.

## Considered options

**Excel defined names** (Name Manager) instead of a variables sheet. Mechanically simpler
— Time Tracker would write straight into the named cell with no second sheet, no formula
indirection and no recalculation dependency. Rejected on discoverability: a defined name
is invisible to anyone who doesn't already know to open Name Manager, and the entire
point of the change is making templates editable by a casual Excel user. A worksheet you
can open and read wins on exactly that criterion.

**Generating `invoices.json` (with its cell map) from a dict literal in code**, as part of
the `init` command. Rejected because it would put the 21 cell references in a third place
— `init`'s source, alongside every `invoices.json` on disk — with the code copy silently
governing all new installs. The repo already demonstrated this failure mode: `invoices.json`
and `docs/invoices.json` held duplicate 21-key maps, three copies of the blank `.xlsx`
existed (two byte-identical, one older and different), and `docs/invoices.json` had drifted
to carry live production state (`next_invoice: 102`). Templates are therefore *copied* from
a shipped `time_tracker_templates/` data package, never generated.

## Consequences

Missing variables must fail loudly rather than silently produce a blank invoice, so a
required core (`invoice_num`, `invoice_date`, `cust_company`, `cust_contact`,
`print_area_ul`, `print_area_lr`) is validated before any file is written; absence of any
other name is legitimate and passes without warning. Existing templates do not work
unchanged — each needs a `Variables` sheet added and its invoice cells converted to
formulas. This is a hard break, accepted because the tool has a single user.
