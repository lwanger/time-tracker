"""Tests for the time-log helpers in time_tracker_time_log."""

import datetime

import time_tracker_time_log
from conftest import CLIENT_HOURLY


# --------------------------------------------------------------------------- #
# Row parsing / printing
# --------------------------------------------------------------------------- #
def test_parse_time_entry_builds_expected_dict():
    row = ["2026-05-01T09:00:00", "2026-05-01T10:30:00", "90", "IO", "unbilled", "Did work"]

    result = time_tracker_time_log.parse_time_entry(row)

    assert result["start"] == datetime.datetime(2026, 5, 1, 9, 0, 0)
    assert result["end"] == datetime.datetime(2026, 5, 1, 10, 30, 0)
    assert result["elapsed"] == 90
    assert result["client"] == "IO"
    assert result["status"] == "unbilled"
    assert result["notes"] == "Did work"


def test_print_row_outputs_tab_separated(capsys):
    row = {
        "start": datetime.datetime(2026, 5, 1, 9, 0, 0),
        "end": datetime.datetime(2026, 5, 1, 10, 30, 0),
        "elapsed": 90,
        "client": "IO",
        "status": "unbilled",
        "notes": "Did work",
    }

    time_tracker_time_log.print_row(row)

    output = capsys.readouterr().out
    assert "2026-05-01 09:00:00" in output
    assert "2026-05-01 10:30:00" in output
    assert "90" in output
    assert "IO" in output
    assert "unbilled" in output
    assert "Did work" in output


# --------------------------------------------------------------------------- #
# Time-log read / filter / write / billing helpers
# --------------------------------------------------------------------------- #
SAMPLE_LOG = (
    "Start,End,Elapsed,Client,Status,Notes\n"
    "2026-05-01T09:00:00,2026-05-01T10:30:00,90,IO,billed,May IO work\n"
    "2026-06-02T13:00:00,2026-06-02T14:00:00,60,IO,unbilled,June IO work\n"
    "2026-06-03T09:00:00,2026-06-03T10:00:00,60,ACME,unbilled,June ACME work\n"
)


def _write_log(tmp_path):
    log = tmp_path / "time_log.csv"
    log.write_text(SAMPLE_LOG, encoding="utf-8")
    return log


def test_read_time_entries_missing_file_returns_empty(tmp_path):
    assert time_tracker_time_log.read_time_entries(str(tmp_path / "nope.csv")) == []


def test_read_time_entries_parses_all_rows(tmp_path):
    entries = time_tracker_time_log.read_time_entries(str(_write_log(tmp_path)))

    assert len(entries) == 3
    assert entries[0]["client"] == "IO"
    assert entries[0]["status"] == "billed"
    assert entries[2]["client"] == "ACME"


def test_filter_time_entries_by_client_is_case_insensitive(tmp_path):
    entries = time_tracker_time_log.read_time_entries(str(_write_log(tmp_path)))

    io_entries = time_tracker_time_log.filter_time_entries(entries, client="io")

    assert len(io_entries) == 2
    assert all(e["client"] == "IO" for e in io_entries)


def test_filter_time_entries_unbilled_only(tmp_path):
    entries = time_tracker_time_log.read_time_entries(str(_write_log(tmp_path)))

    unbilled = time_tracker_time_log.filter_time_entries(entries, status="unbilled")

    assert len(unbilled) == 2
    assert all(e["status"] == "unbilled" for e in unbilled)


def test_filter_time_entries_billed_only(tmp_path):
    entries = time_tracker_time_log.read_time_entries(str(_write_log(tmp_path)))

    billed = time_tracker_time_log.filter_time_entries(entries, status="billed")

    assert len(billed) == 1
    assert all(e["status"] == "billed" for e in billed)


def test_filter_time_entries_status_none_keeps_all(tmp_path):
    entries = time_tracker_time_log.read_time_entries(str(_write_log(tmp_path)))

    assert len(time_tracker_time_log.filter_time_entries(entries, status=None)) == 3
    assert len(time_tracker_time_log.filter_time_entries(entries, status="all")) == 3


# A non-billable row shares its (start, end, client) key with the billed IO row, so this
# log also exercises the identity collision mark_entries_billed has to survive.
LOG_WITH_NON_BILLABLE = (
    "Start,End,Elapsed,Client,Status,Notes\n"
    "2026-06-02T13:00:00,2026-06-02T14:00:00,60,IO,unbilled,June IO work\n"
    "2026-06-04T09:00:00,2026-06-04T10:00:00,60,IO,non-billable,Internal admin\n"
    "2026-06-05T09:00:00,2026-06-05T10:30:00,90,PRO,non-billable,Pro bono work\n"
)


def _write_non_billable_log(tmp_path):
    log = tmp_path / "time_log.csv"
    log.write_text(LOG_WITH_NON_BILLABLE, encoding="utf-8")
    return log


def test_filter_time_entries_non_billable_only(tmp_path):
    entries = time_tracker_time_log.read_time_entries(str(_write_non_billable_log(tmp_path)))

    non_billable = time_tracker_time_log.filter_time_entries(entries, status="non-billable")

    assert len(non_billable) == 2
    assert all(e["status"] == "non-billable" for e in non_billable)


def test_filter_time_entries_unbilled_excludes_non_billable(tmp_path):
    entries = time_tracker_time_log.read_time_entries(str(_write_non_billable_log(tmp_path)))

    unbilled = time_tracker_time_log.filter_time_entries(entries, status="unbilled")

    assert [e["notes"] for e in unbilled] == ["June IO work"]


def test_filter_time_entries_unknown_status_still_keeps_all(tmp_path):
    """Widening the whitelist must not change what an unrecognised status does."""
    entries = time_tracker_time_log.read_time_entries(str(_write_non_billable_log(tmp_path)))

    assert len(time_tracker_time_log.filter_time_entries(entries, status="nonbillable")) == 3
    assert len(time_tracker_time_log.filter_time_entries(entries, status="unbiled")) == 3


def test_filter_time_entries_by_date_range(tmp_path):
    entries = time_tracker_time_log.read_time_entries(str(_write_log(tmp_path)))

    in_may = time_tracker_time_log.filter_time_entries(
        entries, last=datetime.datetime(2026, 5, 31)
    )

    assert len(in_may) == 1
    assert in_may[0]["notes"] == "May IO work"


def test_write_time_entries_round_trips(tmp_path):
    log = _write_log(tmp_path)
    entries = time_tracker_time_log.read_time_entries(str(log))

    time_tracker_time_log.write_time_entries(str(log), entries)
    reread = time_tracker_time_log.read_time_entries(str(log))

    assert reread == entries


def test_mark_entries_billed_flips_only_matching_rows(tmp_path):
    log = _write_log(tmp_path)
    entries = time_tracker_time_log.read_time_entries(str(log))
    to_bill = time_tracker_time_log.filter_time_entries(entries, client="IO", status="unbilled")

    changed = time_tracker_time_log.mark_entries_billed(str(log), to_bill)

    assert changed == 1
    after = time_tracker_time_log.read_time_entries(str(log))
    assert all(e["status"] == "billed" for e in after if e["client"] == "IO")
    # The ACME entry is untouched.
    acme = next(e for e in after if e["client"] == "ACME")
    assert acme["status"] == "unbilled"


def test_mark_entries_billed_never_flips_non_billable(tmp_path):
    """A non-billable row must never be swept onto an invoice.

    It can share a (start, end, client) key with a billable row, and the caller may pass
    it in by mistake; only an unbilled row may become billed.
    """
    log = _write_non_billable_log(tmp_path)
    entries = time_tracker_time_log.read_time_entries(str(log))
    non_billable = time_tracker_time_log.filter_time_entries(entries, status="non-billable")

    changed = time_tracker_time_log.mark_entries_billed(str(log), non_billable)

    assert changed == 0
    after = time_tracker_time_log.read_time_entries(str(log))
    assert [e["status"] for e in after] == ["unbilled", "non-billable", "non-billable"]


def test_mark_entries_billed_bills_unbilled_alongside_non_billable(tmp_path):
    log = _write_non_billable_log(tmp_path)
    entries = time_tracker_time_log.read_time_entries(str(log))

    changed = time_tracker_time_log.mark_entries_billed(str(log), entries)

    assert changed == 1
    after = time_tracker_time_log.read_time_entries(str(log))
    assert [e["status"] for e in after] == ["billed", "non-billable", "non-billable"]


def test_build_time_table_includes_client_and_status(tmp_path):
    entries = time_tracker_time_log.read_time_entries(str(_write_log(tmp_path)))

    table = time_tracker_time_log.build_time_table(entries)
    rendered = table.get_string()

    assert "Client" in rendered
    assert "Status" in rendered
    assert "ACME" in rendered


# --------------------------------------------------------------------------- #
# append_time_entry
# --------------------------------------------------------------------------- #
def test_append_time_entry_creates_file_with_header(tmp_path):
    log = tmp_path / "time_log.csv"
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 30)

    time_tracker_time_log.append_time_entry(str(log), start, end, 90, "IO", "Did work")

    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Start,End,Elapsed,Client,Status,Notes"
    assert lines[1] == "2026-05-01T09:00:00,2026-05-01T10:30:00,90,IO,unbilled,Did work"


def test_append_time_entry_appends_without_duplicate_header(tmp_path):
    log = tmp_path / "time_log.csv"
    log.write_text("Start,End,Elapsed,Client,Status,Notes\n", encoding="utf-8")
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 0)

    time_tracker_time_log.append_time_entry(str(log), start, end, 60, "IO", "More work")

    contents = log.read_text(encoding="utf-8")
    assert contents.count("Start,End,Elapsed,Client,Status,Notes") == 1
    assert "More work" in contents


def test_append_time_entry_records_billed_status_and_blank_notes(tmp_path):
    log = tmp_path / "time_log.csv"
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 0)

    time_tracker_time_log.append_time_entry(
        str(log), start, end, 60, "IO", notes=None, status=time_tracker_time_log.STATUS_BILLED
    )

    last_line = log.read_text(encoding="utf-8").splitlines()[-1]
    assert last_line == "2026-05-01T09:00:00,2026-05-01T10:00:00,60,IO,billed,"


def test_append_time_entry_records_non_billable_status(tmp_path):
    log = tmp_path / "time_log.csv"
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 0)

    time_tracker_time_log.append_time_entry(
        str(log), start, end, 60, "PRO", "Board meeting",
        status=time_tracker_time_log.STATUS_NON_BILLABLE,
    )

    last_line = log.read_text(encoding="utf-8").splitlines()[-1]
    assert last_line == "2026-05-01T09:00:00,2026-05-01T10:00:00,60,PRO,non-billable,Board meeting"


def test_default_entry_status_non_billable_client():
    assert time_tracker_time_log.default_entry_status({"non_billable": True}) == "non-billable"


def test_default_entry_status_defaults_to_unbilled():
    assert time_tracker_time_log.default_entry_status(CLIENT_HOURLY) == "unbilled"
    assert time_tracker_time_log.default_entry_status({}) == "unbilled"
