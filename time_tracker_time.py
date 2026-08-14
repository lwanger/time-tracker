"""Time entries: the add-time and list-time commands.

Leonard Wanger, 2026
"""

import datetime
import os
from typing import Any

import cooked_input as ci
import typer

from time_tracker_cli import CMDS, app, parse_cli_datetime
from time_tracker_clients import prompt_for_client
from time_tracker_config import global_vars
from time_tracker_json import read_json_args
from time_tracker_time_log import (
    STATUS_BILLED,
    STATUS_NON_BILLABLE,
    STATUS_UNBILLED,
    append_time_entry,
    build_time_table,
    default_entry_status,
    filter_time_entries,
    read_time_entries,
)


# Status filter choices for the list-time command.
STATUS_ALL = "all"
LIST_TIME_STATUS_CHOICES = (STATUS_UNBILLED, STATUS_BILLED, STATUS_NON_BILLABLE, STATUS_ALL)


def _default_status_for_client(clients: dict[str, Any], client: str | None) -> str:
    """Pick the status filter to offer as the default when listing a client's time.

    A non-billable client has no ``unbilled`` time, so offering the usual default would
    show an empty table for the one client whose entries are all non-billable.

    Args:
        clients: Mapping of client code to client record.
        client: The client code being filtered on, or ``None`` for all clients.

    Returns:
        ``non-billable`` for a non-billable client, otherwise ``unbilled``.
    """
    if client is None:
        return STATUS_UNBILLED

    return default_entry_status(clients.get(client.upper(), {}))


def _format_time_totals(entries: list[dict[str, Any]]) -> str:
    """Summarise the time in a set of entries, splitting out non-billable minutes.

    The split is added only when the set actually holds both kinds, so a listing of
    one status keeps its single, unambiguous total.

    Args:
        entries: The matched time entries to total.

    Returns:
        The total line, followed by indented billable / non-billable lines when the
        entries mix the two.
    """
    total = sum(entry['elapsed'] for entry in entries)
    non_billable = sum(entry['elapsed'] for entry in entries
                       if entry['status'] == STATUS_NON_BILLABLE)

    lines = [f"Total: {total} minutes ({total / 60:.2f} hours)"]

    if 0 < non_billable < total:
        billable = total - non_billable
        lines.append(f"  Billable:     {billable} minutes ({billable / 60:.2f} hours)")
        lines.append(f"  Non-billable: {non_billable} minutes ({non_billable / 60:.2f} hours)")

    return "\n".join(lines)


@app.command()
def list_time(
    # Optional in the annotation as well as the default: blank means "all clients", and
    # that None is assigned back to this name below.
    client: str | None = typer.Option(None, help="Only list entries for this client code (omit to be prompted; blank = all)."),
    status: str = typer.Option(None, help="Status filter: unbilled, billed, non-billable, or all. Omit to be prompted (defaults to the client's own status)."),
) -> None:
    """List time log entries as a table, filtered by client, billing status, and/or date range.

    The status filter selects ``unbilled``, ``billed``, ``non-billable``, or ``all``
    entries. When it is prompted for, the offered default follows the client being
    filtered on - ``non-billable`` for a non-billable client, ``unbilled`` otherwise.
    When the results mix billable and non-billable time, the total is broken out so
    invoiceable minutes are never read off a mixed figure.
    """
    DATE_FMT = '%Y-%m-%d %H:%M'
    time_log_file = global_vars['TT_TIME_LOG_FILE']
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

        # CLI --status takes precedence when valid; otherwise prompt, defaulting to the
        # status this client's time is actually recorded with.
        if status is not None and status.lower() in LIST_TIME_STATUS_CHOICES:
            status = status.lower()
        else:
            status = ci.get_string(
                prompt=f"Status to show ({', '.join(LIST_TIME_STATUS_CHOICES)})",
                default=_default_status_for_client(clients, client),
                cleaners=[ci.StripCleaner(), ci.CapitalizationCleaner(style='lower')],
                validators=ci.ChoiceValidator(LIST_TIME_STATUS_CHOICES),
                commands=CMDS,
            )

        first_time = ci.get_date(prompt="Earliest date / time to find (blank for no first filter)", required=False, commands=CMDS)
        last_time = ci.get_date(prompt="Latest date / time to find (blank for no latest filter)", required=False, commands=CMDS)

        if not os.path.isfile(time_log_file):
            print(f"No time log file found at {time_log_file}")
            return

        # "all" applies no status filter.
        status_filter = None if status == STATUS_ALL else status

        entries = read_time_entries(time_log_file)
        matches = filter_time_entries(entries, client=client, status=status_filter,
                                      first=first_time, last=last_time)

        if not matches:
            print("\nNo time entries found\n")
            return

        table = build_time_table(matches, date_fmt=DATE_FMT)

        # Build a title that reflects the active filters.
        scope = "time log entries" if status_filter is None else f"{status_filter} time log entries"
        if client is not None:
            scope += f" for {client}"

        # Tested positively, most specific first: "neither bound is set" as the leading
        # case leaves the later branches proving a bound is set by elimination, which
        # reads harder and which a type checker cannot follow at all.
        if first_time is not None and last_time is not None:
            title_str = f"{scope.capitalize()} between {first_time.strftime(DATE_FMT)} and {last_time.strftime(DATE_FMT)}"
        elif first_time is not None:
            title_str = f"{scope.capitalize()} after {first_time.strftime(DATE_FMT)}"
        elif last_time is not None:
            title_str = f"{scope.capitalize()} before {last_time.strftime(DATE_FMT)}"
        else:
            title_str = f"All {scope}"

        print(f"\n{title_str}:\n")
        print(table)
        print(f"\n{_format_time_totals(matches)}\n")

    except ci.GetInputInterrupt:
        print("\nOperation cancelled")


def add_time_to_log(start_dt: datetime.datetime, end_dt: datetime.datetime, elapsed_minutes: float,
                    client: str, notes: str | None = None, status: str = STATUS_UNBILLED) -> bool:
    """Append a time entry to the CSV time log.

    Returns:
        True if the entry was written, False if a write error occurred (already
        reported to stdout).
    """
    time_log_file = global_vars['TT_TIME_LOG_FILE']
    time_log_filename = global_vars['TT_TIME_LOG_FILENAME']

    try:
        append_time_entry(time_log_file, start_dt, end_dt, elapsed_minutes, client, notes, status)
    except PermissionError:
        print(f"Error: Could not write to {time_log_file}. Please ensure the file is not open in another program.")
        return False
    except OSError as file_error:
        # Narrowed from Exception: this guard is for I/O failures the user can act on -
        # file locked, disk full, bad path. A bug in the write path should raise rather
        # than be flattened into a one-line message.
        print(f"Error: Could not write to {time_log_file}: {file_error}")
        return False

    print(f"Successfully appended {elapsed_minutes:0.0f} minutes to {time_log_filename}")
    return True


@app.command()
def add_time(
    client: str = typer.Option(None, "--client", help="Client code to log time for (must exist in clients.json)."),
    date: str = typer.Option(None, "--date", help="Date of the entry (flexible format, e.g. '2026-07-23' or 'today')."),
    start: str = typer.Option(None, "--start", help="Start time of day (flexible format, e.g. '9:00 am')."),
    end: str = typer.Option(None, "--end", help="End time of day (flexible format, e.g. '5:00 pm')."),
    notes: str = typer.Option(None, "--notes", help="Notes for the entry."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt and add the entry immediately."),
    non_billable: bool | None = typer.Option(None, "--non-billable/--billable",
                                             help="Log this entry as non-billable (or billable), overriding the client's setting."),
) -> None:
    """Add a time log entry and append to the time log.

    Any of --client/--date/--start/--end/--notes may be given to skip the
    corresponding prompt on the first pass; fields left out are still prompted
    for interactively. Pass all five for a fully non-interactive call (e.g. from
    a script), and add --yes to also skip the final confirmation.

    The entry's status comes from the client's ``non_billable`` setting unless
    --non-billable or --billable overrides it for this entry alone.
    """
    max_minutes = global_vars['TT_MAX_MINUTES_CONFIRMATION']
    clients = read_json_args(global_vars['TT_CLIENTS_FILE'])

    if not clients:
        print(f"No clients found at {global_vars['TT_CLIENTS_FILE']}. Add a client before logging time.")
        raise typer.Exit(code=1)

    # --client must be a known client code; fail fast rather than falling back to a
    # prompt, since a non-interactive caller has no way to answer one.
    cli_client: str | None = None
    if client is not None:
        cli_client = client.upper()
        if cli_client not in clients:
            print(f"Error: unknown client '{client}'. Known clients: {', '.join(clients.keys())}")
            raise typer.Exit(code=1)

    cli_date = parse_cli_datetime(date, "--date") if date is not None else None
    cli_start = parse_cli_datetime(start, "--start") if start is not None else None
    cli_end = parse_cli_datetime(end, "--end") if end is not None else None

    # Defaults for the re-entry loop; updated if user rejects the confirmation.
    default_date: datetime.date = datetime.date.today()
    default_start: str | None = None
    default_end: str = datetime.datetime.now().strftime("%I:%M %p")
    default_notes: str | None = notes
    default_client: str | None = None

    # CLI flags apply only on the first pass through the loop; a re-entry (after
    # rejecting the confirmation) is always interactive.
    first_pass = True

    # TODO: add timezone
    try:
        while True:
            if first_pass and cli_client is not None:
                entry_client = cli_client
            else:
                entry_client = prompt_for_client(clients, default=default_client)

            if first_pass and cli_date is not None:
                log_date = datetime.date(cli_date.year, cli_date.month, cli_date.day)
            else:
                d = ci.get_date(prompt="Date", default=default_date, commands=CMDS)
                log_date = datetime.date(d.year, d.month, d.day)

            if first_pass and cli_start is not None:
                start_time = datetime.time(cli_start.hour, cli_start.minute)
            else:
                start_dt = ci.get_date(prompt="Start time (e.g. 9:00 am)", default=default_start, commands=CMDS)
                start_time = datetime.time(start_dt.hour, start_dt.minute)

            if first_pass and cli_end is not None:
                end_time = datetime.time(cli_end.hour, cli_end.minute)
            else:
                end_dt = ci.get_date(prompt="End time", default=default_end, commands=CMDS)
                end_time = datetime.time(end_dt.hour, end_dt.minute)

            if first_pass and notes is not None:
                entry_notes = notes
            else:
                entry_notes = ci.get_string(prompt="Notes", default=default_notes, commands=CMDS)

            start_datetime = datetime.datetime.combine(log_date, start_time)
            end_datetime = datetime.datetime.combine(log_date, end_time)

            if end_datetime > start_datetime:
                elapsed_time = end_datetime - start_datetime
            else:  # rollover past midnight
                elapsed_time = start_datetime - end_datetime

            elapsed_minutes = elapsed_time.total_seconds() / 60

            # The client's setting is only a default; the flags override it per entry.
            if non_billable is None:
                entry_status = default_entry_status(clients[entry_client])
            else:
                entry_status = STATUS_NON_BILLABLE if non_billable else STATUS_UNBILLED

            print("\n=============================================================================")
            print("Entry summary:")
            print(f"  Client:     {entry_client}")
            print(f"  Date:       {log_date.strftime('%B %d, %Y')}")
            print(f"  Start:      {start_datetime.strftime('%I:%M %p')}")
            print(f"  End:        {end_datetime.strftime('%I:%M %p')}")
            print(f"  Total time: {elapsed_minutes:.0f} min ({elapsed_minutes / 60:.2f} hrs)")
            print(f"  Status:     {entry_status}")
            print(f"  Notes:      {entry_notes}")
            if elapsed_minutes > max_minutes:
                print(f"  WARNING: {elapsed_minutes:.0f} minutes ({elapsed_minutes / 60:.2f} hrs) exceeds the {max_minutes}-minute warning threshold.")
            print("=============================================================================")
            print()

            yn = "yes" if yes else ci.get_yes_no(prompt="Add this entry to the log (y/n)?", default="Yes", commands=CMDS)
            if yn == "yes":
                if not add_time_to_log(start_datetime, end_datetime, elapsed_minutes, entry_client, entry_notes,
                                       status=entry_status):
                    raise typer.Exit(code=1)
                break

            # Preserve entered values as defaults for re-entry.
            default_client = entry_client
            default_date = log_date
            default_start = start_datetime.strftime("%I:%M %p")
            default_end = end_datetime.strftime("%I:%M %p")
            default_notes = entry_notes
            first_pass = False
            print("\nRe-enter time entry (previous values shown as defaults).\n")

    except ci.GetInputInterrupt:
        print("\nOperation cancelled")
        raise typer.Exit(code=1)
