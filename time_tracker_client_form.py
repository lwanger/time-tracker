"""The client-record form: collecting one client's fields and confirming them.

``add-client`` and ``edit-client`` differ only in where the starting values come
from and what happens to the finished record, so the whole question-and-answer part
lives here: which fields are asked for, in what order, which of them a flag or an
existing value can answer, and what the confirmation shows.

Leonard Wanger, 2026
"""

from dataclasses import dataclass
from typing import Any

import cooked_input as ci
import typer
from prettytable import PrettyTable

from time_tracker_cli import CMDS
from time_tracker_client_record import (
    CLIENT_FIELD_LABELS,
    CLIENT_NON_BILLABLE_KEY,
    RETAINER_FIELDS,
    client_field_label,
    format_client_field,
    has_retainer,
    is_non_billable_client,
    merge_client_record,
)


@dataclass(frozen=True)
class ClientFieldValues:
    """Client-record field values supplied on the command line.

    Every field is optional; an omitted one is prompted for. Both ``add-client`` and
    ``edit-client`` fill this in and hand it to the same prompt sequence, so the two
    cannot drift apart in what they ask or how they validate it.
    """

    company: str | None = None
    contact: str | None = None
    phone: str | None = None
    addr1: str | None = None
    addr2: str | None = None
    rate_hr: float | None = None
    rate_day: float | None = None
    retainer_hrs: float | None = None
    retainer_rate: float | None = None
    non_billable: bool | None = None


# Money and hours fields. Their prompts validate the input; their flags are checked
# before any prompting starts, so a bad one fails before the first question.
CLIENT_AMOUNT_FIELDS = ("rate_hr", "rate_day", *RETAINER_FIELDS)


def validate_amount_flags(values: ClientFieldValues) -> None:
    """Reject a negative amount given on the command line.

    The prompts apply the same minimum, but a flag skips its prompt - so without this
    a negative rate would reach the confirmation table and then clients.json.

    Raises:
        typer.Exit: If any amount flag is negative.
    """
    for name in CLIENT_AMOUNT_FIELDS:
        amount = getattr(values, name)
        if amount is not None and amount < 0:
            print(f"Error: --{name.replace('_', '-')} must not be negative (got {amount}).")
            raise typer.Exit(code=1)


def _skip_prompt(current: Any, required: bool, yes: bool) -> bool:
    """Report whether ``--yes`` can answer a field prompt on the user's behalf.

    ``--yes`` means "take the answer you would have offered me". A field with an
    existing value has one, and an optional field's is blank - so neither is worth
    stopping a scripted run for. A *required* field being added has no answer to take,
    so it is still asked, exactly as an omitted ``add-time`` flag is.

    Args:
        current: The record's existing value, or ``None`` when there is none.
        required: Whether a blank answer would be refused.
        yes: Whether ``--yes`` was given.

    Returns:
        ``True`` when ``current`` should be used without prompting.
    """
    return yes and (current is not None or not required)


def _client_text_field(
    flag_value: str | None, prompt: str, current: Any, required: bool, yes: bool
) -> str | None:
    """Resolve one text field from its flag, or prompt for it.

    Args:
        flag_value: Value from the command line; skips the prompt when given.
        prompt: Prompt text.
        current: The record's existing value, offered as the default when editing.
        required: Whether a blank answer is refused.
        yes: Accept ``current`` without prompting where possible.

    Returns:
        The value, or ``None`` when an optional field is left blank.
    """
    if flag_value is not None:
        return flag_value.strip() or None

    if _skip_prompt(current, required, yes):
        return current

    return ci.get_string(
        prompt=prompt, default=current, required=required,
        cleaners=[ci.StripCleaner()], commands=CMDS,
    )


def _client_amount_field(
    flag_value: float | None, prompt: str, current: Any, required: bool, yes: bool
) -> float | None:
    """Resolve one money/hours field from its flag, or prompt for it.

    Amounts stay floating point: a rate is money, so ``$17.50/hr`` has to survive the
    round trip, and a rate that merely happens to be whole is no different in kind.

    Args:
        flag_value: Value from the command line; skips the prompt when given.
        prompt: Prompt text.
        current: The record's existing value, offered as the default when editing.
        required: Whether a blank answer is refused.
        yes: Accept ``current`` without prompting where possible.

    Returns:
        The amount, or ``None`` when an optional field is left blank.
    """
    if flag_value is not None:
        return flag_value

    if _skip_prompt(current, required, yes):
        return current

    return ci.get_float(
        prompt=prompt, default=current, required=required, minimum=0, commands=CMDS,
    )


def _resolve_non_billable(values: ClientFieldValues, existing: dict[str, Any], yes: bool) -> bool:
    """Decide whether the client's time is ever invoiced.

    Asked early, because the answer decides whether the rate fields are asked for at
    all - a non-billable client has no rate to bill at.

    Args:
        values: Field values from the command line.
        existing: The current record, or ``{}`` when adding.
        yes: Take the default answer without asking.

    Returns:
        ``True`` when the client is non-billable.
    """
    if values.non_billable is not None:
        return values.non_billable

    currently = is_non_billable_client(existing)
    if yes:
        return currently

    answer = ci.get_yes_no(
        prompt="Is this client billable (y/n)?",
        default="No" if currently else "Yes",
        commands=CMDS,
    )
    return answer == "no"


def _prompt_contact_fields(
    values: ClientFieldValues, existing: dict[str, Any], yes: bool
) -> dict[str, Any]:
    """Collect the contact block: contact name, phone and the two address lines.

    Only the contact name is required - it is a template variable an invoice cannot be
    generated without. The rest are written only when given.
    """
    return {
        "contact": _client_text_field(values.contact, "Contact name", existing.get("contact"), True, yes),
        "phone": _client_text_field(values.phone, "Phone", existing.get("phone"), False, yes),
        "addr1": _client_text_field(values.addr1, "Address line 1", existing.get("addr1"), False, yes),
        "addr2": _client_text_field(values.addr2, "Address line 2 (city, state, zip)", existing.get("addr2"), False, yes),
    }


def _prompt_rate_fields(
    values: ClientFieldValues, existing: dict[str, Any], non_billable: bool, yes: bool
) -> dict[str, Any]:
    """Collect the billing rates, unless the client is never invoiced.

    A non-billable client is not asked: ``invoice`` refuses it outright, so there is no
    rate to set. Rates given explicitly on the command line are still honoured, and any
    rate already on the record is left alone rather than dropped - flipping a client to
    non-billable must not throw away the rate it had when it was billable.
    """
    if non_billable:
        return {"rate_hr": values.rate_hr, "rate_day": values.rate_day}

    return {
        "rate_hr": _client_amount_field(values.rate_hr, "Hourly rate ($)", existing.get("rate_hr"), True, yes),
        "rate_day": _client_amount_field(values.rate_day, "Daily rate ($)", existing.get("rate_day"), False, yes),
    }


def _prompt_retainer_fields(
    values: ClientFieldValues, existing: dict[str, Any], yes: bool
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Collect the retainer pair, gated on whether the client has a retainer at all.

    Returns the fields to set *and* the fields to clear: answering "no" for a client
    that currently has a retainer is the only way to end one, and it has to drop both
    keys - half an agreement would be billed as if it were whole.

    Args:
        values: Field values from the command line. Either retainer flag answers the
            gate, since asking for one only to be asked whether it exists is silly.
        existing: The current record, or ``{}`` when adding.
        yes: Take the default answer without asking.

    Returns:
        A ``(fields_to_set, fields_to_clear)`` pair.
    """
    flagged = values.retainer_hrs is not None or values.retainer_rate is not None
    currently = has_retainer(existing)

    if flagged:
        wants_retainer = True
    elif yes:
        wants_retainer = currently
    else:
        wants_retainer = ci.get_yes_no(
            prompt="Does this client have a monthly retainer (y/n)?",
            default="Yes" if currently else "No",
            commands=CMDS,
        ) == "yes"

    if not wants_retainer:
        return {}, RETAINER_FIELDS

    return {
        "retainer_hrs": _client_amount_field(
            values.retainer_hrs, "Retainer hours per month", existing.get("retainer_hrs"), True, yes),
        "retainer_rate": _client_amount_field(
            values.retainer_rate, "Retainer monthly fee ($)", existing.get("retainer_rate"), True, yes),
    }, ()


def _collect_client_record(
    existing: dict[str, Any], values: ClientFieldValues, yes: bool
) -> dict[str, Any]:
    """Run the whole prompt sequence and build the record to store.

    Order: company, then whether the client is billable (which decides whether the
    rates are asked for), then contact details, rates and finally the retainer.

    Args:
        existing: The current record, or ``{}`` when adding a client.
        values: Field values from the command line.
        yes: Answer every prompt that has a current or default value to offer,
            leaving only a required field of a *new* client to be asked for.

    Returns:
        The complete record to write, holding only the fields that are actually set.
    """
    updates: dict[str, Any] = {
        "company": _client_text_field(values.company, "Company name", existing.get("company"), True, yes),
    }
    non_billable = _resolve_non_billable(values, existing, yes)

    updates.update(_prompt_contact_fields(values, existing, yes))
    updates.update(_prompt_rate_fields(values, existing, non_billable, yes))

    retainer_updates, cleared = _prompt_retainer_fields(values, existing, yes)
    updates.update(retainer_updates)

    # Only a real `true` is written, and a client turned back to billable loses the key
    # entirely - a record should say what is unusual about a client, not restate the
    # default. See is_non_billable_client for why a stray "false" is worth avoiding.
    updates[CLIENT_NON_BILLABLE_KEY] = True if non_billable else None
    removed = (*cleared, *(() if non_billable else (CLIENT_NON_BILLABLE_KEY,)))

    return merge_client_record(existing, updates, removed)


def _client_field_order(existing: dict[str, Any], record: dict[str, Any]) -> list[str]:
    """List the fields to show for a record: the known ones in order, then any extras."""
    known = [name for name in CLIENT_FIELD_LABELS if name in record or name in existing]
    extras = [name for name in {**existing, **record} if name not in CLIENT_FIELD_LABELS]
    return known + extras


def _client_summary_table(existing: dict[str, Any], record: dict[str, Any]) -> PrettyTable:
    """Build the confirmation table for a client record.

    An edit shows what each field is changing *from*, so confirming the change does not
    depend on remembering the old values, and marks the rows that actually differ.

    Args:
        existing: The current record, or ``{}`` when adding a client.
        record: The record about to be written.

    Returns:
        A populated :class:`PrettyTable`.
    """
    editing = bool(existing)
    table = PrettyTable(field_names=["Field", "Current", "New", ""] if editing else ["Field", "Value"])
    table.align = "l"

    for name in _client_field_order(existing, record):
        label = client_field_label(name)
        new_value = format_client_field(record.get(name, ""))

        if not editing:
            table.add_row([label, new_value])
            continue

        old_value = format_client_field(existing.get(name, ""))
        table.add_row([label, old_value, new_value, "" if old_value == new_value else "*"])

    return table


def _confirm_client_record(
    code: str, existing: dict[str, Any], record: dict[str, Any], yes: bool
) -> bool:
    """Show the record that is about to be written and ask whether to save it."""
    print(f"\n{'Changes to' if existing else 'New'} client {code}:\n")
    print(_client_summary_table(existing, record))
    if existing:
        print("\n(* = changed)")
    print()

    if yes:
        return True

    prompt = f"Save changes to client {code} (y/n)?" if existing else f"Add client {code} (y/n)?"
    return ci.get_yes_no(prompt=prompt, default="Yes", commands=CMDS) == "yes"


def confirm_or_reenter(
    code: str, stored: dict[str, Any], values: ClientFieldValues, yes: bool
) -> dict[str, Any]:
    """Collect a client record, confirm it, and offer to re-enter it when rejected.

    Refusing to save usually means one answer came out wrong, not that the other nine
    should be typed again - so the answers just given become the defaults for another
    pass, exactly as an existing record's values are the defaults when editing. Only
    declining to change anything cancels.

    A re-entry pass is always interactive: the command-line flags had their say on the
    first pass, and re-applying them would keep re-supplying the value being corrected.

    Args:
        code: The client code, for the prompts and the summary heading.
        stored: The record as it is on disk, or ``{}`` when adding. It stays the
            "Current" column throughout, so an edit is always shown against the saved
            record rather than against the previous attempt.
        values: Field values from the command line.
        yes: Skip the confirmation entirely.

    Returns:
        The record to save.

    Raises:
        typer.Exit: If the user declines both to save the record and to change it.
    """
    record = _collect_client_record(stored, values, yes)

    while True:
        # An edit that changes nothing has nothing to confirm - the caller says so.
        if record == stored or _confirm_client_record(code, stored, record, yes):
            return record

        change = ci.get_yes_no(prompt="Change your answers (y/n)?", default="Yes", commands=CMDS)
        if change != "yes":
            print("Operation cancelled")
            raise typer.Exit(code=1)

        print("\nRe-entering client details (previous answers shown as defaults).\n")
        # The previous attempt becomes the base: it already carries the fields a skipped
        # group left alone, so a second pass cannot quietly drop what the first kept.
        record = _collect_client_record(record, ClientFieldValues(), False)

