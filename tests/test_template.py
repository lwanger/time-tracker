"""Tests for the invoice-template helpers in time_tracker_template."""

from unittest.mock import MagicMock

import pytest

import time_tracker_template
from conftest import REQUIRED_ROWS, build_template_workbook


# --------------------------------------------------------------------------- #
# Template variables sheet
# --------------------------------------------------------------------------- #
def test_read_template_variable_rows_maps_names_to_rows():
    workbook = build_template_workbook((("invoice_num", None), ("cust_company", None)))

    assert time_tracker_template.read_template_variable_rows(workbook) == {"invoice_num": 2, "cust_company": 3}


def test_read_template_variable_rows_skips_section_headers_and_blanks():
    workbook = build_template_workbook((
        ("[ Filled by Time Tracker ]", None),
        ("invoice_num", None),
        ("", None),
        ("[ Template settings ]", None),
        ("indent", "  "),
    ))

    assert set(time_tracker_template.read_template_variable_rows(workbook)) == {"invoice_num", "indent"}


def test_read_template_variable_rows_without_variables_sheet_raises():
    workbook = build_template_workbook(sheet_name="Simple Invoice")

    with pytest.raises(time_tracker_template.TemplateError, match="no 'Variables' worksheet"):
        time_tracker_template.read_template_variable_rows(workbook)


def test_read_template_setting_returns_value_or_default():
    workbook = build_template_workbook((("indent", "     "),))
    rows = time_tracker_template.read_template_variable_rows(workbook)

    assert time_tracker_template.read_template_setting(workbook, rows, "indent") == "     "
    assert time_tracker_template.read_template_setting(workbook, rows, "absent", default="fallback") == "fallback"


def test_validate_template_variables_accepts_complete_template():
    workbook = build_template_workbook()
    rows = time_tracker_template.read_template_variable_rows(workbook)

    time_tracker_template.validate_template_variables(workbook, rows, "t.xlsx")  # does not raise


def test_validate_template_variables_names_every_missing_variable():
    workbook = build_template_workbook((
        ("invoice_num", None), ("print_area_ul", "A1"), ("print_area_lr", "C1"),
    ))
    rows = time_tracker_template.read_template_variable_rows(workbook)

    with pytest.raises(time_tracker_template.TemplateError) as excinfo:
        time_tracker_template.validate_template_variables(workbook, rows, "t.xlsx")

    message = str(excinfo.value)
    assert all(name in message for name in ("invoice_date", "cust_company", "cust_contact"))


def test_validate_template_variables_rejects_blank_print_area():
    workbook = build_template_workbook(tuple((name, None) for name, _ in REQUIRED_ROWS))
    rows = time_tracker_template.read_template_variable_rows(workbook)

    with pytest.raises(time_tracker_template.TemplateError, match="no value for"):
        time_tracker_template.validate_template_variables(workbook, rows, "t.xlsx")


def test_validate_template_variables_rejects_external_links():
    """A linked template produces a workbook Excel refuses to open - reject it first."""
    workbook = build_template_workbook()
    rows = time_tracker_template.read_template_variable_rows(workbook)
    link = MagicMock()
    link.file_link.Target = "https://example.invalid/Invoice%20-%20blank.xlsx"
    workbook._external_links = [link]

    with pytest.raises(time_tracker_template.TemplateError) as excinfo:
        time_tracker_template.validate_template_variables(workbook, rows, "t.xlsx")

    message = str(excinfo.value)
    assert "links to another workbook" in message
    assert "https://example.invalid/Invoice%20-%20blank.xlsx" in message
    assert "repair_template_external_links.py" in message


def test_write_template_variables_ignores_undeclared_names():
    workbook = build_template_workbook((("invoice_num", None), ("cust_company", None)))
    rows = time_tracker_template.read_template_variable_rows(workbook)

    time_tracker_template.write_template_variables(
        workbook, rows, {"invoice_num": 42, "cust_company": "FakeCo", "not_in_template": "ignored"}
    )

    sheet = workbook[time_tracker_template.VARIABLES_SHEET_NAME]
    assert sheet.cell(row=2, column=2).value == 42
    assert sheet.cell(row=3, column=2).value == "FakeCo"


def test_write_template_variables_leaves_none_blank():
    workbook = build_template_workbook((("invoice_retainer_amount", None),))
    rows = time_tracker_template.read_template_variable_rows(workbook)

    time_tracker_template.write_template_variables(workbook, rows, {"invoice_retainer_amount": None})

    assert workbook[time_tracker_template.VARIABLES_SHEET_NAME].cell(row=2, column=2).value is None
