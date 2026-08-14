"""Tests for the invoice-log helpers in time_tracker_invoice_log."""

import time_tracker_invoice_log


# --------------------------------------------------------------------------- #
# Invoice-log read / filter / write / mark-paid helpers
# --------------------------------------------------------------------------- #
SAMPLE_INVOICE_LOG = (
    "InvoiceNum,Date,Client,Hours,Rate,Total,PaymentStatus,PaidDate\n"
    "101,2026-05-01,IO,10.00,100.00,1000.00,paid,2026-05-15\n"
    "102,2026-06-01,IO,5.00,100.00,500.00,unpaid,\n"
    "103,2026-06-02,ACME,20.00,150.00,3000.00,unpaid,\n"
)


def _write_invoice_log(tmp_path):
    log = tmp_path / "invoices_log.csv"
    log.write_text(SAMPLE_INVOICE_LOG, encoding="utf-8")
    return log


def test_read_invoice_log_missing_file_returns_empty(tmp_path):
    assert time_tracker_invoice_log.read_invoice_log(str(tmp_path / "nope.csv")) == []


def test_read_invoice_log_parses_all_rows(tmp_path):
    entries = time_tracker_invoice_log.read_invoice_log(str(_write_invoice_log(tmp_path)))

    assert len(entries) == 3
    assert entries[0]["inv_num"] == 101
    assert entries[0]["payment_status"] == "paid"
    assert entries[0]["paid_date"] == "2026-05-15"
    assert entries[1]["paid_date"] is None


def test_filter_invoice_log_by_client_is_case_insensitive(tmp_path):
    entries = time_tracker_invoice_log.read_invoice_log(str(_write_invoice_log(tmp_path)))

    io_entries = time_tracker_invoice_log.filter_invoice_log(entries, client="io")

    assert len(io_entries) == 2
    assert all(e["client"] == "IO" for e in io_entries)


def test_filter_invoice_log_unpaid_only(tmp_path):
    entries = time_tracker_invoice_log.read_invoice_log(str(_write_invoice_log(tmp_path)))

    unpaid = time_tracker_invoice_log.filter_invoice_log(entries, status="unpaid")

    assert len(unpaid) == 2
    assert all(e["payment_status"] == "unpaid" for e in unpaid)


def test_filter_invoice_log_status_none_keeps_all(tmp_path):
    entries = time_tracker_invoice_log.read_invoice_log(str(_write_invoice_log(tmp_path)))

    assert len(time_tracker_invoice_log.filter_invoice_log(entries, status=None)) == 3
    assert len(time_tracker_invoice_log.filter_invoice_log(entries, status="all")) == 3


def test_write_invoice_log_round_trips(tmp_path):
    log = _write_invoice_log(tmp_path)
    entries = time_tracker_invoice_log.read_invoice_log(str(log))

    time_tracker_invoice_log.write_invoice_log(str(log), entries)
    reread = time_tracker_invoice_log.read_invoice_log(str(log))

    assert reread == entries


def test_append_invoice_log_entry_creates_file_with_header(tmp_path):
    log = tmp_path / "invoices_log.csv"

    time_tracker_invoice_log.append_invoice_log_entry(str(log), inv_num=201, date="2026-07-01", client="IO", hours=4, rate=100, total=400)

    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "InvoiceNum,Date,Client,Hours,Rate,Total,PaymentStatus,PaidDate"
    assert lines[1] == "201,2026-07-01,IO,4.00,100.00,400.00,unpaid,"


def test_append_invoice_log_entry_appends_without_duplicate_header(tmp_path):
    log = _write_invoice_log(tmp_path)

    time_tracker_invoice_log.append_invoice_log_entry(str(log), inv_num=201, date="2026-07-01", client="IO", hours=4, rate=100, total=400)

    contents = log.read_text(encoding="utf-8")
    assert contents.count("InvoiceNum,Date,Client,Hours,Rate,Total,PaymentStatus,PaidDate") == 1
    assert len(time_tracker_invoice_log.read_invoice_log(str(log))) == 4


def test_mark_invoice_paid_updates_matching_row(tmp_path):
    log = _write_invoice_log(tmp_path)

    time_tracker_invoice_log.mark_invoice_paid(str(log), 102, "2026-07-10")

    entries = time_tracker_invoice_log.read_invoice_log(str(log))
    updated = next(e for e in entries if e["inv_num"] == 102)
    assert updated["payment_status"] == "paid"
    assert updated["paid_date"] == "2026-07-10"
    # Other rows are untouched.
    untouched = next(e for e in entries if e["inv_num"] == 103)
    assert untouched["payment_status"] == "unpaid"


def test_build_invoice_table_includes_client_and_status(tmp_path):
    entries = time_tracker_invoice_log.read_invoice_log(str(_write_invoice_log(tmp_path)))

    table = time_tracker_invoice_log.build_invoice_table(entries)
    rendered = table.get_string()

    assert "Payment Status" in rendered
    assert "ACME" in rendered
