"""The client record: the fields a client has, and the rules for reading them.

One client's entry in clients.json. The file is hand-edited and not schema-checked,
so everything here treats a record as untrusted input: an unrecognised field is data
to preserve, and a flag that is not a real boolean is reported rather than believed.

Leonard Wanger, 2026
"""

import logging
import re
from collections.abc import Iterable
from typing import Any


logger = logging.getLogger(__name__)


# The client-record key is snake_case to match rate_hr / retainer_hrs, while the CSV
# status value above is hyphenated. The two spellings are deliberate, not a typo.
CLIENT_NON_BILLABLE_KEY = "non_billable"

# Every client-record field Time Trackerknows, and how it is labelled. This order is both
# the column order list-clients renders and the key order add-client/edit-client write,
# so a record reads the same however it was created. A record may still carry fields
# that are not here: clients.json is hand-edited, and an unknown field is someone's
# data, so it is shown and preserved rather than dropped (see merge_client_record).
CLIENT_FIELD_LABELS: dict[str, str] = {
    "company":       "Company",
    "contact":       "Contact",
    "phone":         "Phone",
    "addr1":         "Address 1",
    "addr2":         "Address 2",
    CLIENT_NON_BILLABLE_KEY: "Non-billable",
    "rate_hr":       "Rate/Hr",
    "rate_day":      "Rate/Day",
    "retainer_hrs":  "Retained Hrs",
    "retainer_rate": "Retained Rate",
}

# The two fields making up a retainer agreement. They travel together: a client has a
# retainer only when both are set, and clearing one clears the other.
RETAINER_FIELDS = ("retainer_hrs", "retainer_rate")

# A client code keys the record in clients.json, is recorded verbatim in every time-log
# and invoice-log row, and is listed comma-separated in the client prompts. Restricting
# it to these characters keeps all three unambiguous.
CLIENT_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")

def is_non_billable_client(client_record: dict[str, Any]) -> bool:
    """Report whether a client's work is excluded from invoicing.

    Billable is the default: a record without the key, or with it set to ``false``, is
    billable. Only a real JSON ``true`` marks a client non-billable, because
    ``clients.json`` is hand-edited and unvalidated - a quoted ``"false"`` is truthy in
    Python and would otherwise silently make a paying client uninvoiceable.

    Args:
        client_record: A client record from ``clients.json``.

    Returns:
        ``True`` only when the record sets ``non_billable`` to the boolean ``true``.
    """
    flag = client_record.get(CLIENT_NON_BILLABLE_KEY, False)

    if isinstance(flag, bool):
        return flag

    logger.warning(
        "Ignoring %s for client %r: expected true or false, got %r. Treating the client "
        "as billable.",
        CLIENT_NON_BILLABLE_KEY,
        client_record.get("company", "<unnamed>"),
        flag,
    )
    return False

def client_field_label(name: str) -> str:
    """Label one client-record field for display.

    A field Time Trackerdoes not know is title-cased rather than hidden, so a hand-added
    ``email`` shows up as ``Email``.

    Args:
        name: The field's key in the client record.

    Returns:
        The label to head a column or name a row with.
    """
    return CLIENT_FIELD_LABELS.get(name, name.replace("_", " ").title())


def format_client_field(value: Any) -> Any:
    """Render one client-record value for display in a table.

    Args:
        value: The raw value from the client record, or ``""`` when absent.

    Returns:
        ``Yes``/``""`` for a boolean, so a flag reads as a mark rather than as
        ``True``/``False``; every other value unchanged.
    """
    if isinstance(value, bool):
        return "Yes" if value else ""

    return value


def has_retainer(client_record: dict[str, Any]) -> bool:
    """Report whether a client bills on a monthly retainer.

    Both fields are needed. A record carrying only one of them has an incomplete
    agreement and is billed hourly, which is what the invoice math has always done.

    Args:
        client_record: A client record from ``clients.json``.

    Returns:
        ``True`` when both ``retainer_hrs`` and ``retainer_rate`` are set.
    """
    return all(client_record.get(name) is not None for name in RETAINER_FIELDS)


def validate_client_code(code: str, clients: dict[str, Any], must_be_new: bool) -> str | None:
    """Check a client code is well formed and either free or known.

    Args:
        code: The code to check, already stripped and upper-cased.
        clients: Mapping of client code to client record.
        must_be_new: ``True`` when adding a client, where the code must not exist yet;
            ``False`` when editing one, where it must.

    Returns:
        A message naming the problem, or ``None`` when the code is usable.
    """
    if not code:
        return "a client code is required."

    if not CLIENT_CODE_RE.match(code):
        return (
            f"invalid client code {code!r} - use letters, digits, '-' and '_' only, "
            f"starting with a letter or digit."
        )

    if must_be_new and code in clients:
        return f"client {code} already exists - use `time-tracker edit-client --client {code}` to change it."

    if not must_be_new and code not in clients:
        return f"unknown client {code}. Known clients: {', '.join(clients) or 'none'}"

    return None


def merge_client_record(
    existing: dict[str, Any], updates: dict[str, Any], removed: Iterable[str] = ()
) -> dict[str, Any]:
    """Build the client record to store, applying updates to an existing one.

    Known fields come out in :data:`CLIENT_FIELD_LABELS` order, so a record reads the
    same whichever command wrote it. Any *other* key the record carries is kept, at the
    end: ``clients.json`` is hand-edited, so a field Time Trackerdoes not recognise is the
    user's data and an edit must not silently drop it.

    Args:
        existing: The current record, or ``{}`` when adding a client.
        updates: Field values to set. A ``None`` value means "not supplied" and leaves
            any existing value alone - use ``removed`` to clear a field.
        removed: Fields to drop, e.g. the retainer pair for a client that no longer
            has one.

    Returns:
        A new record. ``existing`` is not modified.
    """
    merged = {**existing, **{name: value for name, value in updates.items() if value is not None}}

    for name in removed:
        merged.pop(name, None)

    ordered = {name: merged[name] for name in CLIENT_FIELD_LABELS if name in merged}
    extras = {name: value for name, value in merged.items() if name not in CLIENT_FIELD_LABELS}
    return {**ordered, **extras}

