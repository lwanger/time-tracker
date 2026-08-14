"""The Invoice Log CSV: the authoritative record of every invoice issued.

One row per invoice, carrying what it was billed at when it was issued - so a later
rate change cannot rewrite history - plus whether it has been paid.

Leonard Wanger, 2026
"""

import csv
import os
from typing import Any

from prettytable import PrettyTable


# Invoice-log CSV schema (column order matters - rows are written/read positionally).
INVOICE_LOG_HEADER = ["InvoiceNum", "Date", "Client", "Hours", "Rate", "Total", "PaymentStatus", "PaidDate"]
PAYMENT_STATUS_UNPAID = "unpaid"
PAYMENT_STATUS_PAID = "paid"

def parse_invoice_log_entry(row: list[str]) -> dict[str, Any]:
    """Parse a single invoice-log CSV row into an invoice-log-entry dict.

    Args:
        row: A CSV row of the form
            ``[inv_num, date, client, hours, rate, total, payment_status, paid_date]``.

    Returns:
        A dict with keys ``inv_num`` (``int``), ``date``/``client``/``payment_status``
        (``str``), ``hours``/``rate``/``total`` (``float``), and ``paid_date``
        (``str``, or ``None`` when blank).
    """
    return {
        'inv_num': int(row[0]),
        'date': row[1],
        'client': row[2],
        'hours': float(row[3]),
        'rate': float(row[4]),
        'total': float(row[5]),
        'payment_status': row[6],
        'paid_date': row[7] or None,
    }


def _invoice_log_entry_to_row(entry: dict[str, Any]) -> list[str]:
    """Serialize an invoice-log-entry dict back to a CSV row in schema order."""
    return [
        str(entry['inv_num']),
        entry['date'],
        entry['client'],
        f"{entry['hours']:.2f}",
        f"{entry['rate']:.2f}",
        f"{entry['total']:.2f}",
        entry['payment_status'],
        entry['paid_date'] or "",
    ]


def read_invoice_log(invoice_log_file: str) -> list[dict[str, Any]]:
    """Read all invoice entries from the invoice-log CSV.

    Args:
        invoice_log_file: Path to the invoice-log CSV file.

    Returns:
        A list of invoice-log-entry dicts (see :func:`parse_invoice_log_entry`).
        Returns an empty list when the file does not exist.
    """
    if not os.path.isfile(invoice_log_file):
        return []

    entries: list[dict[str, Any]] = []
    with open(invoice_log_file, "r", newline="", encoding="utf-8") as f:
        csv_r = csv.reader(f)
        next(csv_r, None)  # skip header row
        for row in csv_r:
            if row:  # skip blank trailing lines
                entries.append(parse_invoice_log_entry(row))

    return entries


def write_invoice_log(invoice_log_file: str, entries: list[dict[str, Any]]) -> None:
    """Rewrite the entire invoice-log CSV (header + rows) from entry dicts.

    Args:
        invoice_log_file: Path to the invoice-log CSV file.
        entries: Invoice-log-entry dicts to persist, in the desired order.
    """
    with open(invoice_log_file, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(INVOICE_LOG_HEADER)
        for entry in entries:
            writer.writerow(_invoice_log_entry_to_row(entry))


def append_invoice_log_entry(invoice_log_file: str, inv_num: int, date: str, client: str,
                             hours: float, rate: float, total: float) -> None:
    """Append a newly issued invoice to the invoice-log CSV with status ``unpaid``.

    Writes the header row when the file does not yet exist, then appends one row
    in :data:`INVOICE_LOG_HEADER` order.

    Args:
        invoice_log_file: Path to the invoice-log CSV file.
        inv_num: The invoice number.
        date: Invoice creation date, as an ISO date string.
        client: Client code the invoice was issued to.
        hours: Hours billed on the invoice.
        rate: The client's hourly rate at the time of invoicing.
        total: The total dollar amount due.

    Raises:
        OSError: If the invoice-log file cannot be written.
    """
    file_exists = os.path.isfile(invoice_log_file)

    with open(invoice_log_file, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)

        if not file_exists:
            writer.writerow(INVOICE_LOG_HEADER)

        writer.writerow([inv_num, date, client, f"{hours:.2f}", f"{rate:.2f}", f"{total:.2f}", PAYMENT_STATUS_UNPAID, ""])


def filter_invoice_log(entries: list[dict[str, Any]], client: str | None = None,
                       status: str | None = None) -> list[dict[str, Any]]:
    """Filter invoice-log entries by client and/or payment status.

    Args:
        entries: Invoice-log entries to filter.
        client: When given, keep only entries whose client matches (case-insensitive).
        status: When ``"paid"`` or ``"unpaid"``, keep only entries with that payment
            status. ``None`` (or any other value) applies no status filter.

    Returns:
        The matching entries, preserving input order.
    """
    client_upper = client.upper() if client is not None else None
    status_filter = status if status in (PAYMENT_STATUS_PAID, PAYMENT_STATUS_UNPAID) else None
    result: list[dict[str, Any]] = []

    for entry in entries:
        if client_upper is not None and entry['client'].upper() != client_upper:
            continue
        if status_filter is not None and entry['payment_status'] != status_filter:
            continue
        result.append(entry)

    return result


def build_invoice_table(entries: list[dict[str, Any]]) -> PrettyTable:
    """Build a PrettyTable of invoice-log entries for display.

    Args:
        entries: Invoice-log entries to render.

    Returns:
        A populated :class:`PrettyTable` (the caller prints any title/total).
    """
    table = PrettyTable(field_names=["Invoice #", "Date", "Client", "Hours", "Rate", "Total", "Payment Status", "Paid Date"])
    table.align["Invoice #"] = "r"
    table.align["Date"] = "l"
    table.align["Client"] = "l"
    table.align["Hours"] = "r"
    table.align["Rate"] = "r"
    table.align["Total"] = "r"
    table.align["Payment Status"] = "l"
    table.align["Paid Date"] = "l"

    for entry in entries:
        table.add_row([
            entry['inv_num'],
            entry['date'],
            entry['client'],
            f"{entry['hours']:.2f}",
            f"${entry['rate']:.2f}",
            f"${entry['total']:.2f}",
            entry['payment_status'],
            entry['paid_date'] or "",
        ])

    return table


def mark_invoice_paid(invoice_log_file: str, inv_num: int, paid_date: str) -> None:
    """Mark the given invoice as paid and rewrite the invoice log.

    Assumes the caller has already verified ``inv_num`` exists in the log and is
    currently unpaid.

    Args:
        invoice_log_file: Path to the invoice-log CSV file.
        inv_num: Invoice number to mark paid.
        paid_date: Date payment was received, as an ISO date string.
    """
    entries = read_invoice_log(invoice_log_file)

    for entry in entries:
        if entry['inv_num'] == inv_num:
            entry['payment_status'] = PAYMENT_STATUS_PAID
            entry['paid_date'] = paid_date
            break

    write_invoice_log(invoice_log_file, entries)
