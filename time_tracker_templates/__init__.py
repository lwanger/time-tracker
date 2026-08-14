"""Starter files copied into a new Time Tracker setup.

A package rather than a bare data directory so the files can be located with
``importlib.resources.files()``, which resolves identically from a source
checkout and from a ``uv tool install``. Nothing here is imported for its code -
the package exists to carry the data.

Contents:
    ``Invoice - blank.xlsx``: the canonical invoice template. Its ``Variables``
        worksheet declares the template variables Time Tracker fills; the invoice
        sheet references them by formula. Issuer details (business name, address,
        phone) are deliberately static placeholder text for the user to edit.
    ``invoices.seed.json``: a fresh invoice counter.
"""

from importlib.resources import files
from pathlib import Path


TEMPLATE_FILENAME = "Invoice - blank.xlsx"
INVOICES_SEED_FILENAME = "invoices.seed.json"


def template_path() -> Path:
    """Return the path to the shipped blank invoice template."""
    return Path(str(files(__name__) / TEMPLATE_FILENAME))


def invoices_seed_path() -> Path:
    """Return the path to the shipped ``invoices.json`` seed."""
    return Path(str(files(__name__) / INVOICES_SEED_FILENAME))
