# Cross-platform, with PDF export left Windows-only

Time Tracker runs on Windows, Linux and macOS. One command behaves differently
across them: `invoice` renders its PDF only on Windows, and elsewhere writes the
`.xlsx` alone, prints a notice and exits 0.

## Why the asymmetry exists

The invoice is a spreadsheet, not a document with a spreadsheet attached. The
template's invoice sheet carries the layout and reads every value by formula from
its `Variables` sheet (see
`0003-self-describing-invoice-template.md`); Time Tracker writes only the
variables. Nothing in the file is *displayable* until something recalculates
those formulas and paginates the result.

openpyxl, which writes the workbook, does neither — it is a file format library
with no formula engine and no layout engine. So the PDF is produced by asking the
one program that has both, Excel, to open the workbook it just wrote and export
it. That goes through COM, which is Windows.

The distinction that follows is the load-bearing one: **the `.xlsx` is the
invoice and the PDF is a rendering of it.** Off Windows the invoice is generated,
logged, and its time entries marked billed, exactly as on Windows. What is
missing is one rendering of a complete artifact, which the user can produce by
opening the workbook and printing it. Treating that as a failure — refusing to
run, or exiting non-zero — would misdescribe what happened and would strand the
invoice-log row and the billed entries.

## Considered options

**Windows-only, and say so.** Honest, and it was a real candidate: it is where
the tool was developed, and every dependency but one is portable anyway. Rejected
because a Python CLI whose only Windows-specific behaviour is one export step
should not exclude two platforms over it. The cost of portability turned out to
be a function-local import and a dependency marker.

**LibreOffice as a headless fallback.** The obvious portable renderer, and the
one thing that made this decision non-trivial. Rejected on fidelity that cannot
be verified rather than on principle: an invoice is sent to a client and is
sometimes the only document they see from you, so a layout that is *nearly*
right is worse than no PDF at all — it goes out unnoticed. Confirming it was
right would mean visually diffing every template a user might design, on a
renderer whose behaviour with Excel print areas, page setup and embedded images
is nobody's contract. A notice pointing at a workbook the user opens themselves
makes the gap visible instead of hiding it behind an approximation.

**Rendering the PDF directly.** Reimplementing Excel's formula evaluation and
pagination for arbitrary user-designed templates, which is a project, not a
feature.

## Consequences

`pywin32` is declared with an environment marker (`sys_platform == 'win32'`), so
it is not installed elsewhere and its absence is not an error. `export_pdf`
imports it inside the function rather than at module scope, so every other
function in the invoice module imports on every platform; `pdf_export_supported()`
is the single place the platform question is asked.

Every COM failure is converted to `InvoiceExportError` at the boundary, including
one raised while shutting Excel down, so no caller has to be able to name a
`pywin32` exception type it may not have.

The portability claim is verified by CI rather than asserted: the test matrix
runs on Ubuntu, Windows and macOS across the three supported Python versions.
Since the Windows-only path cannot be exercised on two of them, the tests that
cover PDF export pin `sys.platform` and inject fake `pywintypes` /
`win32com.client` modules, and one test binds `win32com` to `None` to prove the
dependency is genuinely optional.
