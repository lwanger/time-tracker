"""The Time Log CSV: its schema, and reading, filtering and writing time entries.

Leonard Wanger, 2026
"""

import csv
import datetime
import os
from typing import Any

from prettytable import PrettyTable

from time_tracker_client_record import is_non_billable_client


# Time-log CSV schema (column order matters - rows are written/read positionally).
TIME_LOG_HEADER = ["Start", "End", "Elapsed", "Client", "Status", "Notes"]
STATUS_BILLED = "billed"
STATUS_UNBILLED = "unbilled"

# Work that will never be invoiced (pro-bono, internal projects, admin), as opposed to
# STATUS_UNBILLED, which only means "not invoiced yet". See
# docs/adr/0005-non-billable-clients-and-time-entries.md.
STATUS_NON_BILLABLE = "non-billable"

# Every status a time entry may carry. Filtering is a positive whitelist, so a status
# added here without being handled downstream shows up as an unfiltered result rather
# than a crash - see filter_time_entries.
TIME_ENTRY_STATUSES = (STATUS_UNBILLED, STATUS_BILLED, STATUS_NON_BILLABLE)

def default_entry_status(client_record: dict[str, Any]) -> str:
    """Pick the status a new time entry gets for a client.

    The client's flag is only ever a *default*, applied when the entry is created. An
    entry's recorded status is the historical truth and is never re-derived, so changing
    a client's flag later cannot rewrite entries already logged.

    Args:
        client_record: A client record from ``clients.json``.

    Returns:
        ``non-billable`` for a non-billable client, otherwise ``unbilled``.
    """
    return STATUS_NON_BILLABLE if is_non_billable_client(client_record) else STATUS_UNBILLED

def parse_time_entry(row: list[str]) -> dict[str, Any]:
    """Parse a single time-log CSV row into a time-entry dict.

    Args:
        row: A CSV row of the form
            ``[start, end, elapsed, client, status, notes]``.

    Returns:
        A dict with keys ``start``/``end`` (``datetime``), ``elapsed`` (``int``
        minutes), and ``client``/``status``/``notes`` (``str``).
    """
    start_dt = datetime.datetime.fromisoformat(row[0])
    end_dt = datetime.datetime.fromisoformat(row[1])

    result = {
        'start': start_dt,
        'end': end_dt,
        'elapsed': int(row[2]),
        'client': row[3],
        'status': row[4],
        'notes': row[5],
    }
    return result


def read_time_entries(time_log_file: str) -> list[dict[str, Any]]:
    """Read all time entries from the CSV time log.

    Args:
        time_log_file: Path to the time-log CSV file.

    Returns:
        A list of time-entry dicts (see :func:`parse_time_entry`). Returns an
        empty list when the file does not exist.
    """
    if not os.path.isfile(time_log_file):
        return []

    entries: list[dict[str, Any]] = []
    with open(time_log_file, "r", newline="", encoding="utf-8") as f:
        csv_r = csv.reader(f)
        next(csv_r, None)  # skip header row
        for row in csv_r:
            if row:  # skip blank trailing lines
                entries.append(parse_time_entry(row))

    return entries


def filter_time_entries(entries: list[dict[str, Any]], client: str | None = None,
                        status: str | None = None, first: datetime.datetime | None = None,
                        last: datetime.datetime | None = None) -> list[dict[str, Any]]:
    """Filter time entries by client, billing status, and/or date range.

    Args:
        entries: Time-entry dicts to filter.
        client: When given, keep only entries whose client matches (case-insensitive).
        status: When one of :data:`TIME_ENTRY_STATUSES`, keep only entries with that
            status. ``None`` (or any other value, such as ``"all"``) applies no status
            filter.
        first: When given, keep only entries whose ``start`` is at or after this time.
        last: When given, keep only entries whose ``end`` is at or before this time.

    Returns:
        The matching entries, preserving input order.
    """
    client_upper = client.upper() if client is not None else None
    status_filter = status if status in TIME_ENTRY_STATUSES else None
    result: list[dict[str, Any]] = []

    for entry in entries:
        if client_upper is not None and entry['client'].upper() != client_upper:
            continue
        if status_filter is not None and entry['status'] != status_filter:
            continue
        if first is not None and entry['start'] < first:
            continue
        if last is not None and entry['end'] > last:
            continue
        result.append(entry)

    return result


def build_time_table(entries: list[dict[str, Any]], date_fmt: str = '%Y-%m-%d %H:%M') -> PrettyTable:
    """Build a PrettyTable of time entries for display.

    Args:
        entries: Time-entry dicts to render.
        date_fmt: ``strftime`` format used for the Start/End columns.

    Returns:
        A populated :class:`PrettyTable` (the caller prints any title/total).
    """
    table = PrettyTable(field_names=["Start", "End", "Min", "Client", "Status", "Notes"])
    table.align["Start"] = "l"
    table.align["End"] = "l"
    table.align["Min"] = "r"
    table.align["Client"] = "l"
    table.align["Status"] = "l"
    table.align["Notes"] = "l"

    for entry in entries:
        table.add_row([
            entry['start'].strftime(date_fmt),
            entry['end'].strftime(date_fmt),
            entry['elapsed'],
            entry['client'],
            entry['status'],
            entry['notes'],
        ])

    return table


def _entry_to_row(entry: dict[str, Any]) -> list[str]:
    """Serialize a time-entry dict back to a CSV row in schema order."""
    return [
        entry['start'].isoformat(timespec='seconds'),
        entry['end'].isoformat(timespec='seconds'),
        f"{entry['elapsed']:0.0f}" if not isinstance(entry['elapsed'], str) else entry['elapsed'],
        entry['client'],
        entry['status'],
        entry['notes'],
    ]


def write_time_entries(time_log_file: str, entries: list[dict[str, Any]]) -> None:
    """Rewrite the entire time-log CSV (header + rows) from entry dicts.

    Args:
        time_log_file: Path to the time-log CSV file.
        entries: Time-entry dicts to persist, in the desired order.
    """
    with open(time_log_file, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(TIME_LOG_HEADER)
        for entry in entries:
            writer.writerow(_entry_to_row(entry))


def mark_entries_billed(time_log_file: str, entries_to_bill: list[dict[str, Any]]) -> int:
    """Mark matching time entries as billed and rewrite the time log.

    Entries are matched by their ``(start, end, client)`` identity, so a row sharing
    that key with one of ``entries_to_bill`` has its status flipped to ``billed``.

    Only an ``unbilled`` row may become ``billed``. Testing for that status positively
    rather than for "not already billed" keeps a ``non-billable`` row - which can share
    a key with a billed one - from being swept onto an invoice, and keeps any status
    added later from silently becoming billable.

    Args:
        time_log_file: Path to the time-log CSV file.
        entries_to_bill: The entries that were invoiced and should be marked billed.

    Returns:
        The number of rows whose status was changed to ``billed``.
    """
    keys_to_bill = {(e['start'], e['end'], e['client']) for e in entries_to_bill}
    all_entries = read_time_entries(time_log_file)

    changed = 0
    for entry in all_entries:
        key = (entry['start'], entry['end'], entry['client'])
        if key in keys_to_bill and entry['status'] == STATUS_UNBILLED:
            entry['status'] = STATUS_BILLED
            changed += 1

    write_time_entries(time_log_file, all_entries)
    return changed


def append_time_entry(time_log_file: str, start_dt: datetime.datetime, end_dt: datetime.datetime,
                      elapsed_minutes: float, client: str, notes: str | None = None,
                      status: str = STATUS_UNBILLED) -> None:
    """Append a single time entry to the CSV time log.

    Writes the header row when the file does not yet exist, then appends one row
    in :data:`TIME_LOG_HEADER` order. This is the shared persistence path used by
    both the ``add-time`` CLI command and the standalone timer app.

    Args:
        time_log_file: Path to the time-log CSV file.
        start_dt: Entry start timestamp.
        end_dt: Entry end timestamp.
        elapsed_minutes: Duration in minutes (stored as a whole number).
        client: Client code the entry belongs to.
        notes: Optional free-text notes (stored as an empty string when ``None``).
        status: Billing status, ``unbilled`` by default.

    Raises:
        OSError: If the time-log file cannot be written.
    """
    file_exists = os.path.isfile(time_log_file)
    start_iso = start_dt.isoformat(timespec='seconds')
    end_iso = end_dt.isoformat(timespec='seconds')
    log_notes = notes if notes is not None else ""
    elapsed_str = f'{elapsed_minutes:0.0f}'

    with open(time_log_file, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)

        if not file_exists:
            writer.writerow(TIME_LOG_HEADER)

        writer.writerow([start_iso, end_iso, elapsed_str, client, status, log_notes])

def print_row(row: dict[str, Any]) -> None:
    start_str = row['start'].strftime('%Y-%m-%d %H:%M:%S')
    end_str = row['end'].strftime('%Y-%m-%d %H:%M:%S')
    print(f"{start_str}\t{end_str}\t{row['elapsed']}\t{row['client']}\t{row['status']}\t{row['notes']}")
