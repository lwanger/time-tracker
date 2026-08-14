"""Tests for the mark-paid command."""

import datetime
from unittest.mock import patch

import cooked_input as ci
import pytest
import typer

import time_tracker_config
import time_tracker_invoice_log
import time_tracker_invoices


SAMPLE_LOG = (
    "InvoiceNum,Date,Client,Hours,Rate,Total,PaymentStatus,PaidDate\n"
    "101,2026-05-01,IO,10.00,100.00,1000.00,paid,2026-05-15\n"
    "102,2026-06-01,IO,5.00,100.00,500.00,unpaid,\n"
)


def _write_log(tmp_path, contents=SAMPLE_LOG):
    log = tmp_path / "invoices_log.csv"
    log.write_text(contents, encoding="utf-8")
    return log


def _gvars(log):
    return {"TT_INVOICES_LOG_FILE": str(log)}


def test_mark_paid_updates_status_and_date(tmp_path, capsys):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(log), clear=True),
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="yes"),
    ):
        time_tracker_invoices.mark_paid(inv_num=102, paid_date="2026-07-10", yes=False)

    assert "marked paid" in capsys.readouterr().out.lower()

    entries = time_tracker_invoice_log.read_invoice_log(str(log))
    updated = next(e for e in entries if e["inv_num"] == 102)
    assert updated["payment_status"] == "paid"
    assert updated["paid_date"] == "2026-07-10"


def test_mark_paid_yes_flag_skips_confirmation(tmp_path):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(log), clear=True),
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True) as mock_yn,
    ):
        time_tracker_invoices.mark_paid(inv_num=102, paid_date="2026-07-10", yes=True)

    mock_yn.assert_not_called()


def test_mark_paid_not_found_exits_nonzero(tmp_path, capsys):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(log), clear=True),
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_invoices.mark_paid(inv_num=999, paid_date="2026-07-10", yes=True)

    assert exc_info.value.exit_code == 1
    assert "not found" in capsys.readouterr().out.lower()


def test_mark_paid_already_paid_exits_nonzero(tmp_path, capsys):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(log), clear=True),
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_invoices.mark_paid(inv_num=101, paid_date="2026-07-10", yes=True)

    assert exc_info.value.exit_code == 1
    assert "already" in capsys.readouterr().out.lower()


def test_mark_paid_confirm_no_does_not_save(tmp_path, capsys):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(log), clear=True),
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="no"),
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_invoices.mark_paid(inv_num=102, paid_date="2026-07-10", yes=False)

    assert exc_info.value.exit_code == 1
    assert "cancelled" in capsys.readouterr().out.lower()

    entries = time_tracker_invoice_log.read_invoice_log(str(log))
    unchanged = next(e for e in entries if e["inv_num"] == 102)
    assert unchanged["payment_status"] == "unpaid"


def test_mark_paid_prompts_for_inv_num_and_defaults_paid_date(tmp_path):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(log), clear=True),
        patch("time_tracker_invoices.ci.get_int", autospec=True, return_value=102) as mock_int,
        patch("time_tracker_invoices.ci.get_date", autospec=True, return_value=datetime.datetime(2026, 7, 20)) as mock_date,
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="yes"),
    ):
        time_tracker_invoices.mark_paid(inv_num=None, paid_date=None, yes=False)

    mock_int.assert_called_once()
    mock_date.assert_called_once()

    entries = time_tracker_invoice_log.read_invoice_log(str(log))
    updated = next(e for e in entries if e["inv_num"] == 102)
    assert updated["paid_date"] == "2026-07-20"


def test_mark_paid_interrupt_cancelled(tmp_path, capsys):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(log), clear=True),
        patch("time_tracker_invoices.ci.get_int", autospec=True, side_effect=ci.GetInputInterrupt),
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_invoices.mark_paid(inv_num=None, paid_date=None, yes=False)

    assert exc_info.value.exit_code == 1
    assert "cancelled" in capsys.readouterr().out.lower()
