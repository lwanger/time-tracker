"""Strip stale external-workbook links out of an invoice template.

A template copied from another workbook inherits an Excel "external link": formulas
that read ``[1]Variables!B22`` point at the *source* workbook's Variables sheet rather
than the template's own. That breaks Time Tracker two ways:

1. openpyxl cannot round-trip the link. Excel writes the link's relationships as
   ``rId1`` (relative path) plus an ``xxl21:alternateUrls`` ``rId2`` (absolute URL);
   openpyxl keeps only ``rId2`` but still emits ``<externalBook r:id="rId1">``. The
   saved package references a relationship that does not exist, and Excel refuses to
   open it - surfacing through COM as "Open method of Workbooks class failed".
2. Even in a valid package the linked cells resolve against the wrong workbook, so
   the invoice silently shows stale values instead of the client being billed.

This works at the zip level rather than through openpyxl so that everything else in
the package - letterhead graphics, styles, ``printerSettings*.bin``, ``calcChain.xml``,
``customXml/`` - is copied through byte-for-byte. openpyxl would drop several of those.

Usage:
    python tools/repair_template_external_links.py TEMPLATE [TEMPLATE ...]
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Final


logger = logging.getLogger(__name__)

EXTERNAL_LINKS_PREFIX: Final = "xl/externalLinks/"
WORKBOOK_PART: Final = "xl/workbook.xml"
WORKBOOK_RELS_PART: Final = "xl/_rels/workbook.xml.rels"
CONTENT_TYPES_PART: Final = "[Content_Types].xml"
WORKSHEET_PART_RE: Final = re.compile(r"^xl/worksheets/sheet\d+\.xml$")

# An external reference in a formula: "[1]Variables!B22", "'[2]Some Sheet'!A1".
EXTERNAL_REF_RE: Final = re.compile(r"\[(\d+)\]([A-Za-z_][A-Za-z0-9_ ]*)!")

# The only cross-workbook target this repair knows how to rewrite. A template that
# links to a *different* sheet is out of scope - see check_external_refs_are_local.
LOCAL_SHEET_NAME: Final = "Variables"

EXTERNAL_REFERENCES_RE: Final = re.compile(r"<externalReferences>.*?</externalReferences>", re.DOTALL)
EXTERNAL_LINK_REL_RE: Final = re.compile(
    r"<Relationship\b[^>]*?/relationships/externalLink\"[^>]*?/>"
)
EXTERNAL_LINK_OVERRIDE_RE: Final = re.compile(
    r"<Override\b[^>]*?PartName=\"/xl/externalLinks/[^\"]*\"[^>]*?/>"
)


class RepairError(Exception):
    """Raised when a template cannot be repaired safely."""


def find_external_refs(worksheet_xml: str) -> set[str]:
    """Return the distinct sheet names referenced through an external workbook.

    Args:
        worksheet_xml: Raw XML of an ``xl/worksheets/sheetN.xml`` part.

    Returns:
        Sheet names appearing as ``[N]<sheet>!`` in the part's formulas.
    """
    return {match.group(2).strip() for match in EXTERNAL_REF_RE.finditer(worksheet_xml)}


def check_external_refs_are_local(parts: dict[str, bytes], template: Path) -> None:
    """Refuse to repair a template whose external refs are not the local Variables sheet.

    Rewriting ``[1]Variables!`` to ``Variables!`` is only correct because the linked
    workbook is a copy of this one, so the sheet exists locally under the same name.
    Any other target would need a human to decide what it should become.

    Args:
        parts: Package part name to raw bytes.
        template: Path to the template, for the error message.

    Raises:
        RepairError: If a formula references a sheet other than ``Variables``.
    """
    foreign: set[str] = set()

    for name, data in parts.items():
        if WORKSHEET_PART_RE.match(name):
            foreign |= find_external_refs(data.decode("utf-8")) - {LOCAL_SHEET_NAME}

    if foreign:
        raise RepairError(
            f"{template}: external references to {', '.join(sorted(foreign))} - this "
            f"script only rewrites references to the local '{LOCAL_SHEET_NAME}' sheet. "
            f"Fix these by hand in Excel."
        )


def rewrite_worksheet(worksheet_xml: str) -> str:
    """Point external formula references at the workbook's own sheet.

    Args:
        worksheet_xml: Raw XML of a worksheet part.

    Returns:
        The XML with every ``[N]Sheet!`` prefix reduced to ``Sheet!``.
    """
    return EXTERNAL_REF_RE.sub(r"\2!", worksheet_xml)


def strip_external_link_parts(parts: dict[str, bytes]) -> dict[str, bytes]:
    """Remove every trace of the external link from a package's parts.

    Drops the ``xl/externalLinks/`` parts themselves and the three places that refer
    to them: the workbook's ``<externalReferences>``, the workbook relationship, and
    the content-type override.

    Args:
        parts: Package part name to raw bytes.

    Returns:
        A new mapping with the external link removed. Ordering is preserved so the
        rewritten package keeps the original part order.
    """
    repaired: dict[str, bytes] = {}

    for name, data in parts.items():
        if name.startswith(EXTERNAL_LINKS_PREFIX):
            continue

        if WORKSHEET_PART_RE.match(name):
            data = rewrite_worksheet(data.decode("utf-8")).encode("utf-8")
        elif name == WORKBOOK_PART:
            data = EXTERNAL_REFERENCES_RE.sub("", data.decode("utf-8")).encode("utf-8")
        elif name == WORKBOOK_RELS_PART:
            data = EXTERNAL_LINK_REL_RE.sub("", data.decode("utf-8")).encode("utf-8")
        elif name == CONTENT_TYPES_PART:
            data = EXTERNAL_LINK_OVERRIDE_RE.sub("", data.decode("utf-8")).encode("utf-8")

        repaired[name] = data

    return repaired


def read_parts(template: Path) -> dict[str, bytes]:
    """Read every part of an .xlsx package, preserving order.

    Args:
        template: Path to the .xlsx file.

    Returns:
        Mapping of part name to raw bytes.
    """
    with zipfile.ZipFile(template) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def write_parts(template: Path, parts: dict[str, bytes]) -> None:
    """Write parts back out as a deflated .xlsx package.

    Args:
        template: Path to write to.
        parts: Mapping of part name to raw bytes.
    """
    with zipfile.ZipFile(template, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def repair_template(template: Path, make_backup: bool = True) -> bool:
    """Strip the external link from one template, in place.

    Args:
        template: Path to the template workbook.
        make_backup: Write a ``.bak`` copy alongside before modifying.

    Returns:
        ``True`` if the template was modified, ``False`` if it had no external link.

    Raises:
        RepairError: If the template is missing, is not a valid .xlsx, or references
            a sheet this script will not rewrite.
    """
    if not template.is_file():
        raise RepairError(f"{template}: no such file")

    try:
        parts = read_parts(template)
    except zipfile.BadZipFile as bad_zip:
        raise RepairError(f"{template}: not a readable .xlsx ({bad_zip})") from bad_zip

    if not any(name.startswith(EXTERNAL_LINKS_PREFIX) for name in parts):
        logger.info("%s: no external links, nothing to do", template)
        return False

    check_external_refs_are_local(parts, template)

    if make_backup:
        backup = template.with_suffix(template.suffix + ".bak")
        shutil.copy2(template, backup)
        logger.info("%s: backed up to %s", template, backup.name)

    write_parts(template, strip_external_link_parts(parts))
    logger.info("%s: external link removed", template)
    return True


def main(argv: list[str] | None = None) -> int:
    """Repair each template named on the command line.

    Args:
        argv: Argument list, defaulting to ``sys.argv[1:]``.

    Returns:
        Process exit code: 0 on success, 1 if any template could not be repaired.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("templates", nargs="+", type=Path, help="template .xlsx files to repair")
    parser.add_argument("--no-backup", action="store_true", help="do not write a .bak copy")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    exit_code = 0
    for template in args.templates:
        try:
            repair_template(template, make_backup=not args.no_backup)
        except RepairError as repair_error:
            logger.error("error: %s", repair_error)
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
