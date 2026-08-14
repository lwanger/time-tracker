"""Generating an invoice: the amounts, the template variables, the .xlsx and the PDF.

Leonard Wanger, 2026
"""

import datetime
import sys
from pathlib import Path
from typing import Any

import cooked_input as ci
import openpyxl as xl

from time_tracker_cli import CMDS
from time_tracker_client_record import has_retainer
from time_tracker_template import (
    read_template_setting,
    read_template_variable_rows,
    validate_template_variables,
    write_template_variables,
)


class InvoiceExportError(Exception):
    """Excel could not turn a generated invoice workbook into a PDF.

    Raised in place of the raw ``pywintypes.com_error`` so callers get a readable
    message and do not have to depend on win32 specifics.
    """


class ClientRateError(Exception):
    """A client being invoiced has no hourly rate to bill at.

    Raised before any file is written. Without it the missing rate surfaces as a bare
    ``KeyError`` from the invoice-log append, which runs *after* the .xlsx and .pdf
    exist and would leave both behind with no log row.
    """


def previous_month(today: datetime.date) -> tuple[int, int]:
    """Return the ``(year, month)`` of the month before ``today``.

    Invoices bill the previous month, so December wraps to the prior year.
    """
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def pdf_export_supported() -> bool:
    """Whether this platform can render an invoice workbook to PDF.

    The export drives Excel over COM (see :func:`export_pdf`), which exists only on
    Windows. Read at call time rather than frozen at import, so a test can monkeypatch
    ``sys.platform``.
    """
    return sys.platform == "win32"


def _quit_excel(excel: Any, workbook: Any) -> None:
    """Shut down the Excel process :func:`export_pdf` started, whatever happened.

    DispatchEx starts a dedicated Excel process, which otherwise survives as an
    invisible orphan. The inner finally keeps a failing ``Close()`` from skipping the
    ``Quit()``. Either argument may be ``None`` if the failure came before it existed.
    """
    try:
        if workbook is not None:
            workbook.Close(SaveChanges=False)
    finally:
        if excel is not None:
            excel.Quit()


def export_pdf(filename: str, print_area: tuple[str, str], pdf_fname: str) -> None:
    """Export a generated invoice workbook to PDF via Excel. Windows only.

    Goes through Excel itself (rather than a pure-Python writer) so the invoice
    sheet's formula references to the variables sheet are recalculated.

    Args:
        filename: Path to the saved .xlsx invoice.
        print_area: ``(upper_left, lower_right)`` cells bounding the printable area.
        pdf_fname: Path to write the PDF to.

    Raises:
        InvoiceExportError: If Excel cannot open the workbook or write the PDF. The
            message is the COM error alone; callers add their own context, so nothing
            outside this function has to know about win32 error shapes.
    """
    # Imported here rather than at module scope: pywin32 is a Windows-only dependency
    # (pyproject marks it sys_platform == 'win32'), and every other function in this
    # module has to import on Linux and macOS. Guarded by pdf_export_supported().
    # Unresolvable to a type checker either way - off Windows the modules are absent, and
    # on Windows pywintypes is assembled at runtime, so com_error has no static existence.
    from pywintypes import com_error  # ty: ignore[unresolved-import]
    from win32com.client import DispatchEx  # ty: ignore[unresolved-import]

    # Excel resolves a relative path against its own working directory, not Python's,
    # so always hand it an absolute one - TT_INV_SAVE_DIR defaults to "./invoices".
    workbook_path = str(Path(filename).resolve())

    excel = None
    workbook = None

    # The outer try converts every com_error, including one raised while shutting Excel
    # down, so no win32 exception can reach a caller that may not even have pywin32.
    try:
        try:
            # Inside the try because a machine without Excel fails right here, and that
            # is the same failure to a caller as a workbook that will not open.
            excel = DispatchEx('Excel.Application')

            # No modal dialog may block a run driven over COM, and UpdateLinks=0 stops
            # Excel chasing an external reference that slipped past template validation.
            excel.DisplayAlerts = False
            excel.Visible = False
            workbook = excel.Workbooks.Open(workbook_path, UpdateLinks=0)

            # Export the invoice sheet alone. Exporting the workbook would append the
            # Variables sheet - rates, retainer terms - to the PDF sent to the client.
            sheet = workbook.Worksheets(1)
            sheet.PageSetup.PrintArea = ":".join(print_area)
            sheet.ExportAsFixedFormat(Type=0, Filename=pdf_fname, OpenAfterPublish=True)
        finally:
            _quit_excel(excel, workbook)
    except com_error as excel_error:
        raise InvoiceExportError(str(excel_error)) from excel_error


def compute_invoice_total(cust: dict[str, Any], inv_hrs: float) -> float:
    """Compute the total amount due for an invoice.

    For a retainer client (``retainer_hrs``/``retainer_rate`` present), the total
    is the flat retainer fee plus any hours worked beyond ``retainer_hrs`` at the
    client's hourly rate. For a plain hourly client, it's ``inv_hrs`` times the
    hourly rate.

    Args:
        cust: The client record (from ``clients.json``).
        inv_hrs: Hours worked being invoiced.

    Returns:
        The total dollar amount due.
    """
    hourly_rate = cust['rate_hr']

    try:
        retainer_hrs = cust['retainer_hrs']
        retainer_rate = cust['retainer_rate']
    except KeyError:
        return inv_hrs * hourly_rate

    hourly_hrs = max(inv_hrs - retainer_hrs, 0)
    return retainer_rate + hourly_hrs * hourly_rate


def build_invoice_line_items(
    cust: dict[str, Any], inv_hrs: float, total: float, period: str, indent: str
) -> dict[str, Any]:
    """Build the description/amount line items for an invoice, retainer-aware.

    A retainer client gets a heading line plus a retained-services line, and an
    additional-hours line only when hours exceed the retainer. A plain hourly client
    gets a single line carrying the whole total.

    Hours are rendered to one decimal place. They arrive as a sum of logged minutes
    divided by 60, so an unformatted value reads "20.533333333333335 hours".

    Args:
        cust: The client record (from ``clients.json``).
        inv_hrs: Hours being invoiced.
        total: Total amount due, from :func:`compute_invoice_total`.
        period: Billing period, e.g. ``"May 2026"``.
        indent: Leading whitespace for sub-lines, from the template's ``indent``.

    Returns:
        Variable name to value for the line-item variables that apply.
    """
    hourly_rate = cust['rate_hr']

    if not has_retainer(cust):
        return {
            'invoice_desc1': f'Hourly consulting services - {period} '
                             f'({inv_hrs:.1f} hours @ ${hourly_rate:.2f}/hr)',
            'invoice_amt1': total,
        }

    # Read past the guard, and by subscript: has_retainer() has established both keys
    # are there, so a .get() would only re-open a case that is already closed.
    retainer_hrs = cust['retainer_hrs']
    retainer_rate = cust['retainer_rate']

    line_items: dict[str, Any] = {
        'invoice_desc1': f'Consulting services - {period}',
        'invoice_desc2': f'{indent}Retained services - 1st {retainer_hrs:.1f} hours '
                         f'@ fixed rate of ${retainer_rate:.2f}/mo',
        'invoice_amt2': retainer_rate,
    }

    overage_hrs = max(inv_hrs - retainer_hrs, 0)
    if overage_hrs > 0:
        line_items['invoice_desc3'] = (f'{indent}Additional hours - {overage_hrs:.1f} hours '
                                       f'@ ${hourly_rate:.2f}/hr')
        line_items['invoice_amt3'] = total - retainer_rate

    return line_items


def build_invoice_variables(
    cust: dict[str, Any],
    client_code: str,
    inv_num: int,
    inv_hrs: float,
    indent: str = "",
    today: datetime.date | None = None,
) -> dict[str, Any]:
    """Build every template variable Time Tracker can fill for one invoice.

    Values are returned for the whole vocabulary regardless of what any given
    template references; :func:`write_template_variables` drops the ones a template
    does not declare. ``None`` means "leave blank" (e.g. retainer amounts for an
    hourly client).

    Args:
        cust: The client record (from ``clients.json``).
        client_code: The client's short code, e.g. ``"RET"``.
        inv_num: Invoice number being issued.
        inv_hrs: Hours being invoiced.
        indent: Leading whitespace for sub-lines, from the template's ``indent``.
        today: Issue date; defaults to today. Injectable for tests.

    Returns:
        Variable name to value.
    """
    today = today or datetime.date.today()
    year, month = previous_month(today)
    period = datetime.date(year, month, 1).strftime('%B %Y')

    total = compute_invoice_total(cust, inv_hrs)
    is_retainer = has_retainer(cust)

    # The cust_* variables below report whatever the record holds, even a half-written
    # retainer, so they keep using .get(). The arithmetic subscripts instead: inside the
    # guard both keys exist, and a value that may be None has no business in a sum.
    retainer_hrs = cust.get('retainer_hrs')
    retainer_rate = cust.get('retainer_rate')

    if is_retainer:
        overage_hrs = max(inv_hrs - cust['retainer_hrs'], 0)
        overage_amount = (total - cust['retainer_rate']) if overage_hrs else None
    else:
        overage_hrs = 0
        overage_amount = None

    values: dict[str, Any] = {
        'invoice_num': inv_num,
        'invoice_date': today.strftime('%B %d, %Y'),
        'invoice_period': period,
        'invoice_total': total,
        'invoice_hours': inv_hrs,
        'invoice_year': year,
        'invoice_month': month,
        'invoice_rate_per_hour': cust['rate_hr'],
        'invoice_rate_per_day': cust.get('rate_day'),
        'invoice_retainer_amount': retainer_rate if is_retainer else None,
        'invoice_overage_hours': overage_hrs or None,
        'invoice_overage_amount': overage_amount,
        'cust_code': client_code,
        'cust_company': cust['company'],
        'cust_contact': cust['contact'],
        'cust_addr1': cust.get('addr1'),
        'cust_addr2': cust.get('addr2'),
        # Bare number: the template concatenates its own "Phone: " label.
        'cust_phone': cust.get('phone'),
        'cust_retainer_hrs': retainer_hrs,
        'cust_retainer_rate': retainer_rate,
    }

    values.update(build_invoice_line_items(cust, inv_hrs, total, period, indent))
    return values


def resolve_invoice_client(
    clients: dict[str, Any], client_name: str | None
) -> tuple[dict[str, Any], str]:
    """Resolve the client to bill, prompting when not given or not recognised.

    Args:
        clients: Mapping of client code to client record.
        client_name: Client code, or ``None`` to prompt.

    Returns:
        A ``(client_record, client_code)`` pair.
    """
    if client_name is not None and client_name in clients:
        return clients[client_name], client_name

    customer_choices = list(clients.keys())
    prompt_str = f"Customer ({', '.join(customer_choices)})"
    client_code = ci.get_string(
        prompt=prompt_str,
        cleaners=[ci.StripCleaner(), ci.CapitalizationCleaner(style='upper')],
        validators=ci.ChoiceValidator(customer_choices),
        commands=CMDS,
    )
    return clients[client_code], client_code


def make_invoice(template_file: str, clients: dict[str, Any], inv_num: int, client_name: str | None = None,
                 inv_hrs: float | None = None, inv_save_dir: str = "./invoices") -> Path:
    """Generate an invoice from a self-describing template, as .xlsx and PDF.

    The PDF is written only where Excel can be driven over COM, i.e. on Windows. Off
    Windows the .xlsx alone is produced and no error is raised - the workbook is the
    invoice, and the PDF a rendering of it - so the caller reports that to the user.

    Args:
        template_file: Path to the invoice template workbook.
        clients: Mapping of client code to client record.
        inv_num: Invoice number to issue.
        client_name: Client code to bill; prompts when omitted.
        inv_hrs: Hours to bill; prompts when omitted.
        inv_save_dir: Directory to write the .xlsx and .pdf into.

    Returns:
        Path to the .xlsx that was written. The workbook is saved before the PDF is
        exported, so the caller needs this to clean up if the export fails.

    Raises:
        TemplateError: If the template lacks its variables sheet, a required variable,
            or links to another workbook.
        ClientRateError: If the client has no ``rate_hr`` to bill at.
    """
    cust, client_code = resolve_invoice_client(clients, client_name)

    # Checked here, before any workbook is opened or written: the rate is not read
    # until the invoice-log append, by which point both the .xlsx and the .pdf exist.
    if 'rate_hr' not in cust:
        raise ClientRateError(
            f"client {client_code} has no 'rate_hr' in clients.json, so there is no rate "
            f"to invoice at"
        )

    if inv_hrs is None:
        inv_hrs = ci.get_float(prompt="Hours worked this month: ", minimum=0.01, maximum=500, commands=CMDS)

    workbook = xl.load_workbook(template_file)
    variable_rows = read_template_variable_rows(workbook)
    validate_template_variables(workbook, variable_rows, template_file)

    indent = read_template_setting(workbook, variable_rows, 'indent', default='')
    values = build_invoice_variables(cust, client_code, inv_num, inv_hrs, indent=indent)
    write_template_variables(workbook, variable_rows, values)

    year, month = previous_month(datetime.date.today())
    save_name = 'Invoice {} - {}-{:2} - {}.xlsx'.format(inv_num, year, month, cust['company'])
    invoice_path = Path(inv_save_dir) / save_name
    workbook.save(str(invoice_path))

    # Nothing left to do off Windows: the .xlsx is written and there is no Excel to
    # render it with, which is not a failure and leaves nothing to clean up.
    if not pdf_export_supported():
        return invoice_path

    print_area = (
        read_template_setting(workbook, variable_rows, 'print_area_ul'),
        read_template_setting(workbook, variable_rows, 'print_area_lr'),
    )
    try:
        export_pdf(str(invoice_path), print_area, str(invoice_path.with_suffix('.pdf')))
    except InvoiceExportError as export_error:
        # The workbook is already on disk. Remove it so it cannot be mistaken for a
        # finished invoice, and so retrying with the same number starts clean.
        invoice_path.unlink(missing_ok=True)
        raise InvoiceExportError(
            f"Excel could not export invoice {inv_num} to PDF: {export_error}"
        ) from export_error

    return invoice_path
