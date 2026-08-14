"""Tests for the external-link repair script."""

import re
import shutil
import zipfile

import openpyxl
import pytest

import time_tracker_template
import time_tracker_templates
from tools import repair_template_external_links as repair


# A minimal package shaped like the one Excel writes for a workbook that links to
# another: the externalBook names rId1 while only rId2 is declared, which is exactly
# the dangling relationship openpyxl re-emits and Excel then refuses to open.
WORKBOOK_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<sheets><sheet name="Simple Invoice" sheetId="1" r:id="rId1"/>'
    '<sheet name="Variables" sheetId="2" r:id="rId2"/></sheets>'
    '<externalReferences><externalReference r:id="rId3"/></externalReferences>'
    '</workbook>'
)

WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" Target="externalLinks/externalLink1.xml"/>'
    '</Relationships>'
)

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/externalLinks/externalLink1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.externalLink+xml"/>'
    '</Types>'
)


def _sheet_xml(sheet_name: str = "Variables") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        f'<row r="10"><c r="A10"><f>IF([1]{sheet_name}!B23&lt;&gt;"",[1]{sheet_name}!B23,"")</f></c></row>'
        '<row r="20"><c r="A20"><f>IF(Variables!B10&lt;&gt;"",Variables!B10,"")</f></c></row>'
        '</sheetData></worksheet>'
    )


def _linked_template(tmp_path, sheet_name: str = "Variables"):
    """Write an .xlsx package carrying an external link to another workbook."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "linked.xlsx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("xl/workbook.xml", WORKBOOK_XML)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml(sheet_name))
        archive.writestr("xl/externalLinks/externalLink1.xml", "<externalLink/>")
        archive.writestr("xl/externalLinks/_rels/externalLink1.xml.rels", "<Relationships/>")
        archive.writestr("xl/printerSettings/printerSettings1.bin", b"\x00binary\x00")
    return path


def _parts(path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_repair_removes_every_trace_of_the_external_link(tmp_path):
    template = _linked_template(tmp_path)

    assert repair.repair_template(template) is True

    parts = _parts(template)
    assert not [name for name in parts if name.startswith("xl/externalLinks/")]
    assert b"externalReferences" not in parts["xl/workbook.xml"]
    assert b"externalLink" not in parts["xl/_rels/workbook.xml.rels"]
    assert b"externalLinks" not in parts["[Content_Types].xml"]


def test_repair_repoints_formulas_at_the_local_sheet(tmp_path):
    template = _linked_template(tmp_path)

    repair.repair_template(template)

    sheet = _parts(template)["xl/worksheets/sheet1.xml"].decode("utf-8")
    assert not re.search(r"\[\d+\]", sheet)
    assert 'IF(Variables!B23&lt;&gt;"",Variables!B23,"")' in sheet
    # The already-local formula is untouched.
    assert 'IF(Variables!B10&lt;&gt;"",Variables!B10,"")' in sheet


def test_repair_preserves_parts_openpyxl_would_drop(tmp_path):
    template = _linked_template(tmp_path)

    repair.repair_template(template)

    assert _parts(template)["xl/printerSettings/printerSettings1.bin"] == b"\x00binary\x00"


def test_repair_writes_a_backup_alongside(tmp_path):
    template = _linked_template(tmp_path)
    before = template.read_bytes()

    repair.repair_template(template)

    backup = template.with_suffix(template.suffix + ".bak")
    assert backup.read_bytes() == before


def test_repair_can_skip_the_backup(tmp_path):
    template = _linked_template(tmp_path)

    repair.repair_template(template, make_backup=False)

    assert not template.with_suffix(template.suffix + ".bak").exists()


def test_repair_is_a_no_op_on_a_clean_template(tmp_path):
    template = tmp_path / "clean.xlsx"
    shutil.copy(time_tracker_templates.template_path(), template)
    before = template.read_bytes()

    assert repair.repair_template(template) is False

    assert template.read_bytes() == before
    assert not template.with_suffix(template.suffix + ".bak").exists()


def test_repair_is_idempotent(tmp_path):
    template = _linked_template(tmp_path)
    repair.repair_template(template, make_backup=False)
    once = template.read_bytes()

    assert repair.repair_template(template, make_backup=False) is False
    assert template.read_bytes() == once


def test_repair_refuses_a_reference_to_an_unknown_sheet(tmp_path):
    """Rewriting is only safe because the linked sheet exists locally by that name."""
    template = _linked_template(tmp_path, sheet_name="Rates")
    before = template.read_bytes()

    with pytest.raises(repair.RepairError, match="Rates"):
        repair.repair_template(template)

    assert template.read_bytes() == before, "a refused template must not be modified"


def test_repair_rejects_a_missing_file(tmp_path):
    with pytest.raises(repair.RepairError, match="no such file"):
        repair.repair_template(tmp_path / "absent.xlsx")


def test_repair_rejects_a_file_that_is_not_an_xlsx(tmp_path):
    not_a_workbook = tmp_path / "notes.xlsx"
    not_a_workbook.write_text("plain text", encoding="utf-8")

    with pytest.raises(repair.RepairError, match="not a readable .xlsx"):
        repair.repair_template(not_a_workbook)


def test_repaired_template_passes_time_tracker_validation(tmp_path):
    """End to end: a linked real template is rejected before repair and accepted after."""
    template = tmp_path / "LPC Invoice - blank.xlsx"
    shutil.copy(time_tracker_templates.template_path(), template)

    # Graft an external link onto the shipped template so the fixture is a real one.
    parts = _parts(template)
    sheet_name = next(name for name in parts if re.match(r"xl/worksheets/sheet\d+\.xml$", name))
    parts[sheet_name] = parts[sheet_name].replace(b"Variables!", b"[1]Variables!")
    parts["xl/workbook.xml"] = parts["xl/workbook.xml"].replace(
        b"</workbook>", b'<externalReferences><externalReference r:id="rId99"/></externalReferences></workbook>',
    )
    parts["xl/_rels/workbook.xml.rels"] = parts["xl/_rels/workbook.xml.rels"].replace(
        b"</Relationships>",
        b'<Relationship Id="rId99" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink"'
        b' Target="externalLinks/externalLink1.xml"/></Relationships>',
    )
    parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
        b"</Types>",
        b'<Override PartName="/xl/externalLinks/externalLink1.xml"'
        b' ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.externalLink+xml"/></Types>',
    )
    parts["xl/externalLinks/externalLink1.xml"] = (
        b'<externalLink xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        b' xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        b'<externalBook r:id="rId1"/></externalLink>'
    )
    parts["xl/externalLinks/_rels/externalLink1.xml.rels"] = (
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLinkPath"'
        b' Target="other.xlsx" TargetMode="External"/></Relationships>'
    )
    repair.write_parts(template, parts)

    linked = openpyxl.load_workbook(template)
    rows = time_tracker_template.read_template_variable_rows(linked)
    with pytest.raises(time_tracker_template.TemplateError, match="links to another workbook"):
        time_tracker_template.validate_template_variables(linked, rows, str(template))

    assert repair.repair_template(template, make_backup=False) is True

    repaired = openpyxl.load_workbook(template)
    rows = time_tracker_template.read_template_variable_rows(repaired)
    time_tracker_template.validate_template_variables(repaired, rows, str(template))  # does not raise
    assert repaired._external_links == []


def test_main_reports_failure_for_an_unrepairable_template(tmp_path):
    template = _linked_template(tmp_path, sheet_name="Rates")

    assert repair.main([str(template)]) == 1


def test_main_repairs_every_template_given(tmp_path):
    first = _linked_template(tmp_path)
    second = _linked_template(tmp_path / "sub")

    assert repair.main([str(first), str(second), "--no-backup"]) == 0

    for template in (first, second):
        assert not [name for name in _parts(template) if name.startswith("xl/externalLinks/")]
