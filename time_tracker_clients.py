"""Clients: the add-client, edit-client and list-clients commands.

The prompt sequence these two commands share lives in time_tracker_client_form; what is
here is choosing which client to act on, and reading and rewriting clients.json.

Leonard Wanger, 2026
"""

import json
from typing import Any

import cooked_input as ci
import typer
from prettytable import PrettyTable

from time_tracker_cli import CMDS, app
from time_tracker_client_form import (
    ClientFieldValues,
    confirm_or_reenter,
    validate_amount_flags,
)
from time_tracker_client_record import (
    CLIENT_FIELD_LABELS,
    client_field_label,
    format_client_field,
    validate_client_code,
)
from time_tracker_config import global_vars
from time_tracker_json import (
    read_json_args,
    write_json_args,
)


def prompt_for_client(clients: dict[str, Any], default: str | None = None) -> str:
    """Prompt for a client code, validated against the known clients.

    Args:
        clients: Mapping of client code to client record (from ``clients.json``).
        default: Optional default client code shown in the prompt.

    Returns:
        The selected client code (upper-cased).
    """
    customer_choices = list(clients.keys())
    customer_validator = ci.ChoiceValidator(customer_choices)
    prompt_str = f"Client ({', '.join(customer_choices)})"
    return ci.get_string(
        prompt=prompt_str,
        default=default,
        cleaners=[ci.StripCleaner(), ci.CapitalizationCleaner(style='upper')],
        validators=customer_validator,
        commands=CMDS,
    )


@app.command()
def list_clients() -> None:
    """List all clients as a table, showing all available fields."""
    clients_json_dir = global_vars["TT_CLIENTS_JSON_DIR"]
    clients = read_json_args(global_vars["TT_CLIENTS_FILE"])

    if not clients:
        print(
            f"No clients found in directory {clients_json_dir}. "
            "Add a clients.json file to that directory or change CLIENTS_JSON_DIR "
            "in your .env file to point to the correct location."
        )
        return

    print(f"Showing clients from clients.json file at location: {clients_json_dir}\n")

    # Ordered list of all known fields; collect any unknown extras at the end
    ordered_fields = list(CLIENT_FIELD_LABELS)
    for client_data in clients.values():
        for field in client_data:
            if field not in ordered_fields:
                ordered_fields.append(field)

    # Only include fields present in at least one client
    present_fields = [f for f in ordered_fields if any(f in c for c in clients.values())]

    headers = ["Code"] + [client_field_label(f) for f in present_fields]
    table = PrettyTable(field_names=headers)
    table.align = "l"

    for code, data in clients.items():
        # A False boolean is rendered blank, like an absent field: only the clients that
        # are actually non-billable should stand out in the column.
        row = [code] + [format_client_field(data.get(f, "")) for f in present_fields]
        table.add_row(row)

    print(table)


def _load_clients_for_write(clients_file: str) -> dict[str, Any]:
    """Read ``clients.json`` for a command that is going to rewrite it.

    A file that does not parse is refused rather than read loosely. These are the only
    commands that rewrite the whole file, so carrying on would overwrite a file the
    user can still repair by hand with the little that was salvaged from it.

    Args:
        clients_file: Path to ``clients.json``. A missing file is not an error - that
            is simply the first client being added.

    Returns:
        Mapping of client code to client record.

    Raises:
        typer.Exit: If the file exists but cannot be read or parsed.
    """
    try:
        return read_json_args(clients_file)
    except json.JSONDecodeError as parse_error:
        print(f"Error: {clients_file} is not valid JSON: {parse_error}")
        print("Fix the file by hand before adding or editing a client.")
        raise typer.Exit(code=1)
    except OSError as read_error:
        print(f"Error: could not read {clients_file}: {read_error}")
        raise typer.Exit(code=1)


def _write_client_record(
    clients_file: str, clients: dict[str, Any], code: str, record: dict[str, Any]
) -> None:
    """Store one client record, rewriting ``clients.json``.

    Raises:
        typer.Exit: If the file cannot be written.
    """
    clients[code] = record

    try:
        write_json_args(clients_file, clients)
    except OSError as write_error:
        print(f"Error: could not write {clients_file}: {write_error}")
        raise typer.Exit(code=1)


def _client_choice_table(clients: dict[str, Any]) -> PrettyTable:
    """Build the code/company table shown before asking which client to edit.

    The code is what has to be typed, but nobody thinks about a client by its code, so
    both are shown - the same reason the timer app's pulldown lists company names.
    """
    table = PrettyTable(field_names=["Code", "Company"])
    table.align = "l"

    for code, record in sorted(clients.items(), key=lambda item: str(item[1].get("company", item[0])).lower()):
        table.add_row([code, record.get("company", "")])

    return table


def _prompt_new_client_code(clients: dict[str, Any]) -> str:
    """Prompt for a client code that is well formed and not already taken."""
    while True:
        code = ci.get_string(
            prompt="Client code (e.g. ACME)",
            cleaners=[ci.StripCleaner(), ci.CapitalizationCleaner(style='upper')],
            commands=CMDS,
        )
        code_error = validate_client_code(code, clients, must_be_new=True)

        if code_error is None:
            return code

        print(f"Error: {code_error}")


def _select_client_to_edit(clients: dict[str, Any], client: str | None) -> str:
    """Resolve which client to edit, from ``--client`` or by asking.

    Raises:
        typer.Exit: If ``--client`` names a client that does not exist. A
            non-interactive caller cannot answer a prompt, so this fails rather than
            falling back to one - the same rule ``add-time``'s ``--client`` follows.
    """
    if client is not None:
        code = client.strip().upper()
        code_error = validate_client_code(code, clients, must_be_new=False)

        if code_error is not None:
            print(f"Error: {code_error}")
            raise typer.Exit(code=1)

        return code

    print("\nClients:\n")
    print(_client_choice_table(clients))
    print()
    return prompt_for_client(clients)


@app.command()
def add_client(
    code: str = typer.Option(None, "--code", help="Code for the new client, e.g. ACME (must not already exist)."),
    company: str = typer.Option(None, "--company", help="Company name."),
    contact: str = typer.Option(None, "--contact", help="Contact person."),
    phone: str = typer.Option(None, "--phone", help="Contact phone number."),
    addr1: str = typer.Option(None, "--addr1", help="Address line 1."),
    addr2: str = typer.Option(None, "--addr2", help="Address line 2 (city, state, zip)."),
    rate_hr: float = typer.Option(None, "--rate-hr", help="Hourly billing rate."),
    rate_day: float = typer.Option(None, "--rate-day", help="Daily billing rate."),
    retainer_hrs: float = typer.Option(None, "--retainer-hrs", help="Hours covered by the monthly retainer."),
    retainer_rate: float = typer.Option(None, "--retainer-rate", help="Fixed monthly retainer amount."),
    non_billable: bool | None = typer.Option(None, "--non-billable/--billable",
                                             help="Track this client's time without ever invoicing it."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept the current/default answer for anything not given on the command line, including the confirmation."),
) -> None:
    """Add a new client to clients.json.

    Any field flag skips its prompt; fields left out are still prompted for, so the
    command works interactively, fully non-interactively (pass the flags you need plus
    --yes), or anywhere in between. Only the fields that are actually set are written.

    The client code must be new - use ``edit-client`` to change an existing client.
    """
    clients_file = global_vars["TT_CLIENTS_FILE"]
    clients = _load_clients_for_write(clients_file)

    values = ClientFieldValues(
        company=company, contact=contact, phone=phone, addr1=addr1, addr2=addr2,
        rate_hr=rate_hr, rate_day=rate_day, retainer_hrs=retainer_hrs,
        retainer_rate=retainer_rate, non_billable=non_billable,
    )
    validate_amount_flags(values)

    try:
        if code is None:
            new_code = _prompt_new_client_code(clients)
        else:
            new_code = code.strip().upper()
            code_error = validate_client_code(new_code, clients, must_be_new=True)

            if code_error is not None:
                print(f"Error: {code_error}")
                raise typer.Exit(code=1)

        record = confirm_or_reenter(new_code, {}, values, yes)
    except ci.GetInputInterrupt:
        print("\nOperation cancelled")
        raise typer.Exit(code=1)

    _write_client_record(clients_file, clients, new_code, record)
    print(f"Added client {new_code} to {clients_file}")


@app.command()
def edit_client(
    client: str = typer.Option(None, "--client", help="Code of the client to edit (omit to pick from a list)."),
    company: str = typer.Option(None, "--company", help="Company name."),
    contact: str = typer.Option(None, "--contact", help="Contact person."),
    phone: str = typer.Option(None, "--phone", help="Contact phone number."),
    addr1: str = typer.Option(None, "--addr1", help="Address line 1."),
    addr2: str = typer.Option(None, "--addr2", help="Address line 2 (city, state, zip)."),
    rate_hr: float = typer.Option(None, "--rate-hr", help="Hourly billing rate."),
    rate_day: float = typer.Option(None, "--rate-day", help="Daily billing rate."),
    retainer_hrs: float = typer.Option(None, "--retainer-hrs", help="Hours covered by the monthly retainer."),
    retainer_rate: float = typer.Option(None, "--retainer-rate", help="Fixed monthly retainer amount."),
    non_billable: bool | None = typer.Option(None, "--non-billable/--billable",
                                             help="Track this client's time without ever invoicing it."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept the current/default answer for anything not given on the command line, including the confirmation."),
) -> None:
    """Edit an existing client in clients.json.

    Runs the same prompts as ``add-client``, offering the current values as defaults,
    and shows what is changing before writing anything.

    The client code itself cannot be changed: it is recorded in every time-log and
    invoice-log row, so renaming it would orphan that history. Everything else,
    including the company name, is editable.
    """
    clients_file = global_vars["TT_CLIENTS_FILE"]
    clients = _load_clients_for_write(clients_file)

    if not clients:
        print(f"No clients found at {clients_file}. Use `time-tracker add-client` to add one.")
        raise typer.Exit(code=1)

    values = ClientFieldValues(
        company=company, contact=contact, phone=phone, addr1=addr1, addr2=addr2,
        rate_hr=rate_hr, rate_day=rate_day, retainer_hrs=retainer_hrs,
        retainer_rate=retainer_rate, non_billable=non_billable,
    )
    validate_amount_flags(values)

    try:
        code = _select_client_to_edit(clients, client)
        existing = clients[code]
        record = confirm_or_reenter(code, existing, values, yes)

        if record == existing:
            print(f"\nNo changes to client {code}.")
            return
    except ci.GetInputInterrupt:
        print("\nOperation cancelled")
        raise typer.Exit(code=1)

    _write_client_record(clients_file, clients, code, record)
    print(f"Updated client {code} in {clients_file}")
