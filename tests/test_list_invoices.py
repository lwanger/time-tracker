"""Tests for the list-invoices command."""

from unittest.mock import patch

import cooked_input as ci

import time_tracker_config
import time_tracker_invoices


SAMPLE_LOG = (
    "InvoiceNum,Date,Client,Hours,Rate,Total,PaymentStatus,PaidDate\n"
    "101,2026-05-01,IO,10.00,100.00,1000.00,paid,2026-05-15\n"
    "102,2026-06-02,IO,5.00,100.00,500.00,unpaid,\n"
)

RICH_LOG = SAMPLE_LOG + "103,2026-06-03,ACME,20.00,150.00,3000.00,unpaid,\n"

CLIENTS = {"IO": {"company": "IO Inc"}, "ACME": {"company": "Acme"}}


def _write_log(tmp_path, contents=SAMPLE_LOG):
    log = tmp_path / "invoices_log.csv"
    log.write_text(contents, encoding="utf-8")
    return log


def _gvars(tmp_path, invoice_log):
    return {"TT_INVOICES_LOG_FILE": str(invoice_log), "TT_CLIENTS_FILE": str(tmp_path / "clients.json")}


def test_list_invoices_no_file_reports_missing(tmp_path, capsys):
    missing = tmp_path / "nope.csv"
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, missing), clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=CLIENTS),
    ):
        time_tracker_invoices.list_invoices(client="IO", status="all")

    assert "No invoice log file found" in capsys.readouterr().out


def test_list_invoices_lists_all_entries(tmp_path, capsys):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=CLIENTS),
        patch("time_tracker_invoices.ci.get_string", autospec=True, return_value=""),
    ):
        time_tracker_invoices.list_invoices(client=None, status="all")

    output = capsys.readouterr().out
    assert "All invoices" in output
    assert "101" in output
    assert "102" in output
    assert "1500.00" in output  # 1000 + 500 total


def test_list_invoices_defaults_to_unpaid_only(tmp_path, capsys):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=CLIENTS),
        patch("time_tracker_invoices.ci.get_string", autospec=True, return_value=""),
    ):
        time_tracker_invoices.list_invoices(client=None, status="unpaid")

    output = capsys.readouterr().out
    assert "unpaid" in output.lower()
    assert "102" in output
    assert "101" not in output  # paid, excluded


def test_list_invoices_paid_only(tmp_path, capsys):
    log = _write_log(tmp_path, RICH_LOG)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=CLIENTS),
    ):
        time_tracker_invoices.list_invoices(client="", status="paid")

    output = capsys.readouterr().out
    assert "paid invoices" in output.lower()
    assert "101" in output
    assert "102" not in output
    assert "103" not in output


def test_list_invoices_filters_by_client_cli_option(tmp_path, capsys):
    log = _write_log(tmp_path, RICH_LOG)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=CLIENTS),
    ):
        time_tracker_invoices.list_invoices(client="IO", status="all")

    output = capsys.readouterr().out
    assert "invoices for IO" in output
    assert "101" in output
    assert "103" not in output


def test_list_invoices_interactive_client_prompt(tmp_path, capsys):
    log = _write_log(tmp_path, RICH_LOG)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=CLIENTS),
        patch("time_tracker_invoices.ci.get_string", autospec=True, return_value="ACME"),
    ):
        time_tracker_invoices.list_invoices(client=None, status="all")

    output = capsys.readouterr().out
    assert "103" in output
    assert "101" not in output


def test_list_invoices_interactive_status_prompt(tmp_path, capsys):
    log = _write_log(tmp_path, RICH_LOG)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_invoices.ci.get_string", autospec=True, side_effect=["", "paid"]),
        patch("time_tracker_invoices.read_json_args", return_value=CLIENTS),
    ):
        time_tracker_invoices.list_invoices(client=None, status=None)

    output = capsys.readouterr().out
    assert "101" in output
    assert "102" not in output


def test_list_invoices_no_matching_rows(tmp_path, capsys):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=CLIENTS),
    ):
        time_tracker_invoices.list_invoices(client="ACME", status="all")

    assert "No invoices found" in capsys.readouterr().out


def test_list_invoices_cancelled_on_interrupt(tmp_path, capsys):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=CLIENTS),
        patch("time_tracker_invoices.ci.get_string", autospec=True, side_effect=ci.GetInputInterrupt),
    ):
        time_tracker_invoices.list_invoices(client=None, status="all")

    assert "cancelled" in capsys.readouterr().out.lower()