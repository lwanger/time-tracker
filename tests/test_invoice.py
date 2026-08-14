"""Tests for the invoice command's time-entry-driven billing flow."""

import datetime
import sys
from unittest.mock import patch

import cooked_input as ci
import pytest
import typer

import time_tracker_config
import time_tracker_invoice
import time_tracker_invoice_log
import time_tracker_invoices
import time_tracker_template
import time_tracker_time_log


CLIENTS = {"IO": {"company": "IO Inc", "rate_hr": 100}}
# invoices.json holds only the counter now; the template path comes from TT_TEMPLATE_FILE.
INV_DATA = {"next_invoice": 105}

LOG_WITH_UNBILLED = (
    "Start,End,Elapsed,Client,Status,Notes\n"
    "2026-06-01T09:00:00,2026-06-01T10:00:00,60,IO,unbilled,A\n"
    "2026-06-02T09:00:00,2026-06-02T11:00:00,120,IO,unbilled,B\n"
    "2026-05-01T09:00:00,2026-05-01T10:00:00,60,IO,billed,old\n"
)


def _setup(tmp_path, contents=LOG_WITH_UNBILLED):
    log = tmp_path / "time_log.csv"
    log.write_text(contents, encoding="utf-8")
    gvars = {
        "TT_TIME_LOG_FILE": str(log),
        "TT_CLIENTS_FILE": "clients.json",
        "TT_INVOICES_FILE": "invoices.json",
        "TT_INVOICES_LOG_FILE": str(tmp_path / "invoices_log.csv"),
        "TT_INV_SAVE_DIR": str(tmp_path),
        "TT_TEMPLATE_FILE": str(tmp_path / "Invoice - blank.xlsx"),
    }
    return log, gvars


CLIENTS_WITH_NON_BILLABLE = {
    "IO": {"company": "IO Inc", "rate_hr": 100},
    # A non-billable client needs no rate: it is never invoiced.
    "PRO": {"company": "Pro Bono Inc", "non_billable": True},
}

LOG_WITH_NON_BILLABLE = (
    "Start,End,Elapsed,Client,Status,Notes\n"
    "2026-06-01T09:00:00,2026-06-01T10:00:00,60,IO,unbilled,A\n"
    "2026-06-02T09:00:00,2026-06-02T11:00:00,120,IO,non-billable,Internal admin\n"
)


def test_invoice_non_billable_client_hard_errors(tmp_path, capsys):
    _log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS_WITH_NON_BILLABLE, INV_DATA]),
        patch("time_tracker_invoices.make_invoice") as mock_make,
        pytest.raises(typer.Exit) as excinfo,
    ):
        time_tracker_invoices.invoice(inv_num=105, client="PRO", inv_hrs=1)

    assert excinfo.value.exit_code == 1
    mock_make.assert_not_called()
    assert "non-billable" in capsys.readouterr().out


def test_invoice_non_billable_client_errors_before_choosing_a_number(tmp_path):
    """The refusal must land before the invoice number is chosen, so none is burned."""
    _log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS_WITH_NON_BILLABLE, INV_DATA]),
        patch("time_tracker_invoices.ci.get_int", autospec=True) as mock_get_int,
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.make_invoice"),
        pytest.raises(typer.Exit),
    ):
        time_tracker_invoices.invoice(inv_num=None, client="PRO", inv_hrs=1)

    mock_get_int.assert_not_called()
    mock_write.assert_not_called()
    assert not (tmp_path / "invoices_log.csv").exists()


def test_invoice_skips_non_billable_entries_of_a_billable_client(tmp_path):
    """A billable client's non-billable time is neither billed nor marked."""
    log, gvars = _setup(tmp_path, LOG_WITH_NON_BILLABLE)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS_WITH_NON_BILLABLE, INV_DATA]),
        patch("time_tracker_invoices.write_json_args"),
        patch("time_tracker_invoices.make_invoice") as mock_make,
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="yes"),
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    # Only the 60-minute unbilled entry is billable; the 120-minute one is excluded.
    assert mock_make.call_args.kwargs["inv_hrs"] == 1.0

    after = time_tracker_time_log.read_time_entries(str(log))
    assert [e["status"] for e in after] == ["billed", "non-billable"]


def test_invoice_bill_all_marks_entries_billed(tmp_path):
    log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.make_invoice") as mock_make,
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="yes"),  # bill all (shown + confirmed)
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    # 60 + 120 = 180 minutes = 3.0 hours
    assert mock_make.call_args.kwargs["inv_hrs"] == 3.0
    mock_write.assert_called_once()

    after = time_tracker_time_log.read_time_entries(str(log))
    assert all(e["status"] == "billed" for e in after)  # both IO unbilled now billed


def test_invoice_date_range_bills_subset(tmp_path):
    log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.write_json_args"),
        patch("time_tracker_invoices.make_invoice") as mock_make,
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, side_effect=["no", "yes"]),  # not all, accept
        patch("time_tracker_invoices.ci.get_date", autospec=True, side_effect=[
            datetime.datetime(2026, 6, 1, 0, 0),
            datetime.datetime(2026, 6, 1, 23, 59),
        ]),
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    # Only entry A (60 min) falls in the range -> 1.0 hour
    assert mock_make.call_args.kwargs["inv_hrs"] == 1.0

    after = time_tracker_time_log.read_time_entries(str(log))
    billed_notes = {e["notes"] for e in after if e["status"] == "billed"}
    assert "A" in billed_notes
    assert "B" not in billed_notes  # out of range, still unbilled


def test_invoice_date_range_with_no_matches(tmp_path, capsys):
    _log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.make_invoice") as mock_make,
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, side_effect=["no"]),  # not all -> ask dates
        patch("time_tracker_invoices.ci.get_date", autospec=True, side_effect=[
            datetime.datetime(2027, 1, 1, 0, 0),
            datetime.datetime(2027, 12, 31, 0, 0),
        ]),
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    assert "No unbilled entries in that date range" in capsys.readouterr().out
    mock_make.assert_not_called()


def test_invoice_reject_date_range_does_not_bill(tmp_path, capsys):
    log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.make_invoice") as mock_make,
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, side_effect=["no", "no"]),  # not all, then reject subset
        patch("time_tracker_invoices.ci.get_date", autospec=True, side_effect=[
            datetime.datetime(2026, 6, 1, 0, 0),
            datetime.datetime(2026, 6, 30, 23, 59),
        ]),
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    mock_make.assert_not_called()
    mock_write.assert_not_called()
    assert "cancelled" in capsys.readouterr().out.lower()

    after = time_tracker_time_log.read_time_entries(str(log))
    assert sum(1 for e in after if e["status"] == "unbilled") == 2  # unchanged


def test_invoice_no_unbilled_entries(tmp_path, capsys):
    billed_only = (
        "Start,End,Elapsed,Client,Status,Notes\n"
        "2026-05-01T09:00:00,2026-05-01T10:00:00,60,IO,billed,done\n"
    )
    _log, gvars = _setup(tmp_path, billed_only)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.make_invoice") as mock_make,
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True) as mock_yn,
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    assert "No unbilled time entries" in capsys.readouterr().out
    mock_make.assert_not_called()
    mock_yn.assert_not_called()


def _invoice_all_unbilled(tmp_path, gvars, invoice_path):
    """Run `invoice` over IO's unbilled entries with make_invoice stubbed out."""
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.make_invoice", return_value=invoice_path),
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="yes"),
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    return mock_write


def test_invoice_off_windows_writes_the_xlsx_and_says_so(tmp_path, monkeypatch, capsys):
    """Off Windows only the PDF rendering is missing; the invoice itself is complete.

    Excel over COM is what recalculates the invoice sheet's formulas, so the PDF is
    Windows-only by design - but the .xlsx is the invoice, and everything that follows
    generating it (the log row, the billed entries, next_invoice) must still happen.
    """
    log, gvars = _setup(tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    invoice_path = tmp_path / "Invoice 105 - 2026- 6 - IO Inc.xlsx"

    mock_write = _invoice_all_unbilled(tmp_path, gvars, invoice_path)

    out = capsys.readouterr().out
    assert "PDF export requires Excel on Windows" in out
    assert str(invoice_path) in out

    logged = time_tracker_invoice_log.read_invoice_log(gvars["TT_INVOICES_LOG_FILE"])
    assert [entry["inv_num"] for entry in logged] == [105]

    after = time_tracker_time_log.read_time_entries(str(log))
    assert all(entry["status"] == "billed" for entry in after)
    mock_write.assert_called_once()  # next_invoice still advanced


def test_invoice_on_windows_says_nothing_about_the_pdf(tmp_path, monkeypatch, capsys):
    """The notice is the one output difference, so Windows output stays as it was."""
    _log, gvars = _setup(tmp_path)
    monkeypatch.setattr(sys, "platform", "win32")

    _invoice_all_unbilled(tmp_path, gvars, tmp_path / "Invoice 105.xlsx")

    assert "PDF export requires" not in capsys.readouterr().out


def test_invoice_manual_hours_override_skips_selection(tmp_path):
    log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.make_invoice") as mock_make,
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=10)

    assert mock_make.call_args.kwargs["inv_hrs"] == 10
    mock_write.assert_called_once()

    # Nothing billed: the override skips the time-entry flow entirely.
    after = time_tracker_time_log.read_time_entries(str(log))
    assert sum(1 for e in after if e["status"] == "unbilled") == 2


def test_invoice_prompts_for_client_and_invoice_number(tmp_path):
    _log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.write_json_args"),
        patch("time_tracker_invoices.make_invoice") as mock_make,
        patch("time_tracker_invoices.prompt_for_client", return_value="IO") as mock_client,
        patch("time_tracker_invoices.ci.get_int", autospec=True, return_value=200) as mock_int,
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="yes"),  # bill all
    ):
        time_tracker_invoices.invoice(inv_num=None, client=None, inv_hrs=None)

    mock_client.assert_called_once()
    mock_int.assert_called_once()
    assert mock_make.call_args.kwargs["inv_num"] == 200


def test_invoice_no_clients_aborts(tmp_path, capsys):
    _log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[{}, {}]),
        patch("time_tracker_invoices.make_invoice") as mock_make,
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    assert "No clients found" in capsys.readouterr().out
    mock_make.assert_not_called()


def test_invoice_cancelled_on_interrupt(tmp_path, capsys):
    _log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, side_effect=ci.GetInputInterrupt),
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    assert "cancelled" in capsys.readouterr().out.lower()


# --------------------------------------------------------------------------- #
# invoice command - invoice log
# --------------------------------------------------------------------------- #
def test_invoice_duplicate_number_hard_errors(tmp_path, capsys):
    _log, gvars = _setup(tmp_path)
    invoice_log = tmp_path / "invoices_log.csv"
    invoice_log.write_text(
        "InvoiceNum,Date,Client,Hours,Rate,Total,PaymentStatus,PaidDate\n"
        "105,2026-06-01,IO,10.00,100.00,1000.00,unpaid,\n",
        encoding="utf-8",
    )
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.make_invoice") as mock_make,
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    assert exc_info.value.exit_code == 1
    assert "already exists" in capsys.readouterr().out
    mock_make.assert_not_called()


def test_invoice_appends_to_invoice_log(tmp_path):
    _log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.write_json_args"),
        patch("time_tracker_invoices.make_invoice"),
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="yes"),  # bill all
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    logged = time_tracker_invoice_log.read_invoice_log(gvars["TT_INVOICES_LOG_FILE"])
    assert len(logged) == 1
    entry = logged[0]
    assert entry["inv_num"] == 105
    assert entry["client"] == "IO"
    assert entry["hours"] == 3.0  # 60 + 120 minutes = 3.0 hours
    assert entry["rate"] == 100.0
    assert entry["total"] == 300.0
    assert entry["payment_status"] == "unpaid"
    assert entry["paid_date"] is None


def test_invoice_bad_template_exits_without_logging_or_billing(tmp_path, capsys):
    """A template error is raised before any file is written, so nothing must change."""
    _log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.make_invoice", side_effect=time_tracker_template.TemplateError("no 'Variables' worksheet")),
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="yes"),  # bill all
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    assert exc_info.value.exit_code == 1
    assert "no 'Variables' worksheet" in capsys.readouterr().out

    # The counter must not advance and nothing may reach the invoice log.
    mock_write.assert_not_called()
    assert time_tracker_invoice_log.read_invoice_log(gvars["TT_INVOICES_LOG_FILE"]) == []


def test_invoice_failed_pdf_export_exits_without_logging_or_billing(tmp_path, capsys):
    """make_invoice removes its .xlsx, so the same number can be retried cleanly."""
    log, gvars = _setup(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[CLIENTS, INV_DATA]),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.make_invoice",
              side_effect=time_tracker_invoice.InvoiceExportError("Excel could not export invoice 105 to PDF")),
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="yes"),  # bill all
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=None)

    assert exc_info.value.exit_code == 1
    assert "could not export invoice 105" in capsys.readouterr().out

    mock_write.assert_not_called()
    assert time_tracker_invoice_log.read_invoice_log(gvars["TT_INVOICES_LOG_FILE"]) == []
    # The entries stay unbilled so the run can simply be repeated.
    assert all(e["status"] == "unbilled" for e in time_tracker_time_log.read_time_entries(str(log))
               if e["client"] == "IO" and e["notes"] in {"A", "B"})


def test_invoice_logs_retainer_aware_total(tmp_path):
    _log, gvars = _setup(tmp_path)
    retainer_clients = {"IO": {"company": "IO Inc", "rate_hr": 100, "retainer_hrs": 2, "retainer_rate": 500}}
    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("time_tracker_invoices.read_json_args", side_effect=[retainer_clients, INV_DATA]),
        patch("time_tracker_invoices.write_json_args"),
        patch("time_tracker_invoices.make_invoice"),
    ):
        time_tracker_invoices.invoice(inv_num=105, client="IO", inv_hrs=10)

    logged = time_tracker_invoice_log.read_invoice_log(gvars["TT_INVOICES_LOG_FILE"])
    # Retainer covers the first 2 hrs @ 500 flat; the remaining 8 hrs @ 100/hr = 800.
    assert logged[0]["total"] == 1300.0
