"""Invoices: the invoice, list-invoices, mark-paid and set-next-inv commands.

Leonard Wanger, 2026
"""

import datetime
import os
from typing import Any

import cooked_input as ci
import typer

from time_tracker_cli import CMDS, app, parse_cli_datetime
from time_tracker_client_record import is_non_billable_client
from time_tracker_clients import prompt_for_client
from time_tracker_config import global_vars
from time_tracker_invoice import (
    ClientRateError,
    InvoiceExportError,
    compute_invoice_total,
    make_invoice,
    pdf_export_supported,
)
from time_tracker_invoice_log import (
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_UNPAID,
    append_invoice_log_entry,
    build_invoice_table,
    filter_invoice_log,
    mark_invoice_paid,
    read_invoice_log,
)
from time_tracker_json import (
    read_json_args,
    write_json_args,
)
from time_tracker_template import TemplateError
from time_tracker_time_log import (
    STATUS_UNBILLED,
    build_time_table,
    filter_time_entries,
    mark_entries_billed,
    read_time_entries,
)


# Payment-status filter choices for the list-invoices command.
PAYMENT_STATUS_ALL = "all"
LIST_INVOICES_STATUS_CHOICES = (PAYMENT_STATUS_UNPAID, PAYMENT_STATUS_PAID, PAYMENT_STATUS_ALL)


def _select_billable_entries(client: str) -> list[dict[str, Any]] | None:
    """Choose the unbilled time entries to bill for a client.

    Shows the client's unbilled entries with their total and offers to bill them
    all; if declined, bills a confirmed date-range subset instead.

    Args:
        client: The client code to bill.

    Returns:
        The accepted entries, or ``None`` if there is nothing to bill or the
        user rejects the selection.
    """
    entries = read_time_entries(global_vars['TT_TIME_LOG_FILE'])
    unbilled = filter_time_entries(entries, client=client, status=STATUS_UNBILLED)

    if not unbilled:
        print(f"\nNo unbilled time entries found for {client}.\n")
        return None

    # Show all unbilled entries and their total before asking to bill them.
    unbilled_minutes = sum(entry['elapsed'] for entry in unbilled)
    print(f"\nUnbilled entries for {client}:\n")
    print(build_time_table(unbilled))
    print(f"\nTotal: {unbilled_minutes} minutes ({unbilled_minutes / 60:.2f} hours)\n")

    bill_all = ci.get_yes_no(
        prompt=f"Bill all {len(unbilled)} unbilled entries for {client} ({unbilled_minutes / 60:.2f} hours) (y/n)?",
        default="Yes", commands=CMDS,
    )
    if bill_all == "yes":
        return unbilled

    # Otherwise bill a date-range subset and confirm the selection.
    first_time = ci.get_date(prompt="Start date of entries to bill", commands=CMDS)
    last_time = ci.get_date(prompt="End date of entries to bill", commands=CMDS)
    selected = filter_time_entries(unbilled, first=first_time, last=last_time)

    if not selected:
        print("\nNo unbilled entries in that date range.\n")
        return None

    total_minutes = sum(entry['elapsed'] for entry in selected)
    print(f"\nEntries to bill for {client}:\n")
    print(build_time_table(selected))
    print(f"\nTotal: {total_minutes} minutes ({total_minutes / 60:.2f} hours)\n")

    accept = ci.get_yes_no(
        prompt=f"Create invoice for these {len(selected)} entries ({total_minutes / 60:.2f} hours) (y/n)?",
        default="Yes", commands=CMDS,
    )

    return selected if accept == "yes" else None


@app.command()
def invoice(inv_num: int = typer.Option(default=None, help="Invoice number to create"),
            client: str = typer.Option(default=None, help="Client to bill"),
            inv_hrs: float = typer.Option(default=None, help="Hours worked this month (skips time-entry billing)")) -> None:
    """
    Create an invoice and save as an Excel spreadsheet and a PDF file.

    By default the billable hours are derived from the client's unbilled time
    entries (all of them, or a date-range subset) and those entries are marked
    billed once the invoice is created. Passing ``--inv-hrs`` skips that flow and
    bills the given hours directly.
    """

    # get data from JSON files for the client and invoice templates
    clients = read_json_args(global_vars['TT_CLIENTS_FILE'])
    inv_data = read_json_args(global_vars['TT_INVOICES_FILE'])

    if not clients:
        print(f"No clients found at {global_vars['TT_CLIENTS_FILE']}.")
        return

    try:
        # Resolve the client up front so we can find its unbilled time entries.
        if client is not None and client.upper() in clients:
            client = client.upper()
        else:
            client = prompt_for_client(clients)
        cust = clients[client]

        # Refuse before the invoice number is chosen and before any file is written, so
        # a non-billable client leaves nothing behind to clean up and burns no number.
        if is_non_billable_client(cust):
            print(f"Error: client {client} is non-billable, so its time is not invoiced.")
            print("Remove 'non_billable' from its record in clients.json to bill it.")
            raise typer.Exit(code=1)

        if inv_num is None:
            prompt_str = f"Invoice # ({inv_data['next_invoice']}): "
            inv_num = ci.get_int(prompt=prompt_str, validators=ci.RangeValidator(100, None), default=inv_data['next_invoice'], commands=CMDS)

        # An invoice number must be unique in the invoice log; check before doing
        # any real work so a duplicate is rejected before files are generated.
        if any(entry['inv_num'] == inv_num for entry in read_invoice_log(global_vars['TT_INVOICES_LOG_FILE'])):
            print(f"Error: invoice #{inv_num} already exists in the invoice log ({global_vars['TT_INVOICES_LOG_FILE']}).")
            raise typer.Exit(code=1)

        # Manual override: --inv-hrs bypasses time-entry selection (legacy behavior).
        selected_entries: list[dict[str, Any]] | None = None
        if inv_hrs is None:
            selected_entries = _select_billable_entries(client)
            if selected_entries is None:
                print("Operation cancelled")
                return
            inv_hrs = sum(entry['elapsed'] for entry in selected_entries) / 60

        print(f"Creating invoice {inv_num}")
        try:
            invoice_path = make_invoice(global_vars['TT_TEMPLATE_FILE'], clients, inv_num=inv_num, client_name=client,
                                        inv_hrs=inv_hrs, inv_save_dir=global_vars['TT_INV_SAVE_DIR'])
        except (TemplateError, ClientRateError) as invoice_error:
            # Both are raised before any file is written, so nothing needs cleaning up.
            print(f"Error: {invoice_error}")
            raise typer.Exit(code=1)
        except InvoiceExportError as export_error:
            # make_invoice has already removed the .xlsx it wrote. Exiting here leaves
            # the invoice log, the time entries and next_invoice untouched, so the
            # same invoice number can simply be retried.
            print(f"Error: {export_error}")
            raise typer.Exit(code=1)

        # The .xlsx is the invoice; the PDF is a rendering of it that only Excel can
        # make. Off Windows the invoice is still complete, so this is a notice and not
        # an error - the log row, the billed entries and next_invoice all follow.
        if not pdf_export_supported():
            print(f"PDF export requires Excel on Windows - open and print {invoice_path}")

        append_invoice_log_entry(
            global_vars['TT_INVOICES_LOG_FILE'],
            inv_num=inv_num,
            date=datetime.date.today().isoformat(),
            client=client,
            hours=inv_hrs,
            rate=cust['rate_hr'],
            total=compute_invoice_total(cust, inv_hrs),
        )

        # Mark the billed entries in the time log (time-entry-driven flow only).
        if selected_entries:
            billed = mark_entries_billed(global_vars['TT_TIME_LOG_FILE'], selected_entries)
            print(f"Marked {billed} time entr{'y' if billed == 1 else 'ies'} as billed.")

        # update the next invoice number in the JSON file
        inv_data['next_invoice'] = inv_num + 1
        write_json_args(global_vars['TT_INVOICES_FILE'], inv_data)
    except ci.GetInputInterrupt:
        print("\nOperation cancelled")


@app.command()
def list_invoices(
    # Optional in the annotation as well as the default: blank means "all clients", and
    # that None is assigned back to this name below.
    client: str | None = typer.Option(None, help="Only list invoices for this client code (omit to be prompted; blank = all)."),
    status: str = typer.Option(None, help="Payment status filter: unpaid, paid, or all. Omit to be prompted (default unpaid)."),
) -> None:
    """List invoices from the invoice log as a table, filtered by client and/or payment status."""
    invoice_log_file = global_vars['TT_INVOICES_LOG_FILE']
    clients = read_json_args(global_vars['TT_CLIENTS_FILE'])

    try:
        # CLI --client takes precedence; otherwise prompt, accepting only a known
        # client code or blank (blank = all clients).
        if client is None:
            choices = list(clients.keys())
            client = ci.get_string(
                prompt=f"Client to filter by ({', '.join(choices)}; blank for all)",
                required=False,
                cleaners=[ci.StripCleaner(), ci.CapitalizationCleaner(style='upper')],
                validators=ci.ChoiceValidator(choices),
                commands=CMDS,
            )
        client = client or None

        # CLI --status takes precedence when valid; otherwise prompt (default unpaid).
        if status is not None and status.lower() in LIST_INVOICES_STATUS_CHOICES:
            status = status.lower()
        else:
            status = ci.get_string(
                prompt=f"Payment status to show ({', '.join(LIST_INVOICES_STATUS_CHOICES)})",
                default=PAYMENT_STATUS_UNPAID,
                cleaners=[ci.StripCleaner(), ci.CapitalizationCleaner(style='lower')],
                validators=ci.ChoiceValidator(LIST_INVOICES_STATUS_CHOICES),
                commands=CMDS,
            )

        if not os.path.isfile(invoice_log_file):
            print(f"No invoice log file found at {invoice_log_file}")
            return

        # "all" applies no status filter.
        status_filter = None if status == PAYMENT_STATUS_ALL else status

        entries = read_invoice_log(invoice_log_file)
        matches = filter_invoice_log(entries, client=client, status=status_filter)

        if not matches:
            print("\nNo invoices found\n")
            return

        total_amount = sum(entry['total'] for entry in matches)
        table = build_invoice_table(matches)

        # Build a title that reflects the active filters.
        scope = "invoices" if status_filter is None else f"{status_filter} invoices"
        if client is not None:
            scope += f" for {client}"
        title_str = f"All {scope}" if status_filter is None else scope.capitalize()

        print(f"\n{title_str}:\n")
        print(table)
        print(f"\nTotal: ${total_amount:.2f}\n")

    except ci.GetInputInterrupt:
        print("\nOperation cancelled")


@app.command()
def set_next_inv(
    number: int = typer.Option(None, "--number", help="New next invoice number to set (omit to be prompted)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt and set the number immediately."),
) -> None:
    """Show the current next invoice number and update it in invoices.json."""
    invoices_file = global_vars["TT_INVOICES_FILE"]
    inv_data = read_json_args(invoices_file)

    if not inv_data:
        print(f"No invoices data found at {invoices_file}")
        raise typer.Exit(code=1)

    current = inv_data["next_invoice"]
    print(f"Current next invoice number: {current}")

    if number is not None and number < 1:
        print(f"Error: --number must be at least 1 (got {number}).")
        raise typer.Exit(code=1)

    try:
        new_number = number if number is not None else ci.get_int(
            prompt="New next invoice number",
            validators=ci.RangeValidator(1, None),
            default=current,
            commands=CMDS,
        )

        yn = "yes" if yes else ci.get_yes_no(
            prompt=f"Set next invoice number to {new_number} (y/n)?",
            default="Yes",
            commands=CMDS,
        )

        if yn == "yes":
            inv_data["next_invoice"] = new_number
            write_json_args(invoices_file, inv_data)
            print(f"Next invoice number updated to {new_number}")
        else:
            print("Operation cancelled")
            raise typer.Exit(code=1)

    except ci.GetInputInterrupt:
        print("\nOperation cancelled")
        raise typer.Exit(code=1)


@app.command()
def mark_paid(
    inv_num: int = typer.Option(None, "--inv-num", help="Invoice number to mark as paid (omit to be prompted)."),
    paid_date: str = typer.Option(None, "--paid-date", help="Date payment was received (flexible format; omit to be prompted, default today)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt and mark it paid immediately."),
) -> None:
    """Mark a logged invoice as paid."""
    invoice_log_file = global_vars['TT_INVOICES_LOG_FILE']

    try:
        if inv_num is None:
            inv_num = ci.get_int(prompt="Invoice # to mark paid", validators=ci.RangeValidator(100, None), commands=CMDS)

        entries = read_invoice_log(invoice_log_file)
        target = next((entry for entry in entries if entry['inv_num'] == inv_num), None)

        if target is None:
            print(f"Error: invoice #{inv_num} not found in the invoice log ({invoice_log_file}).")
            raise typer.Exit(code=1)

        if target['payment_status'] == PAYMENT_STATUS_PAID:
            print(f"Error: invoice #{inv_num} is already marked paid (paid {target['paid_date']}).")
            raise typer.Exit(code=1)

        if paid_date is not None:
            resolved_paid_date = parse_cli_datetime(paid_date, "--paid-date").date().isoformat()
        else:
            d = ci.get_date(prompt="Paid date", default=datetime.date.today(), commands=CMDS)
            resolved_paid_date = datetime.date(d.year, d.month, d.day).isoformat()

        print(f"Invoice #{inv_num}  Client: {target['client']}  Total: ${target['total']:.2f}")
        yn = "yes" if yes else ci.get_yes_no(
            prompt=f"Mark invoice #{inv_num} as paid on {resolved_paid_date} (y/n)?",
            default="Yes",
            commands=CMDS,
        )

        if yn != "yes":
            print("Operation cancelled")
            raise typer.Exit(code=1)

        mark_invoice_paid(invoice_log_file, inv_num, resolved_paid_date)
        print(f"Invoice #{inv_num} marked paid.")

    except ci.GetInputInterrupt:
        print("\nOperation cancelled")
        raise typer.Exit(code=1)

