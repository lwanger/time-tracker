"""Tests for the list-time command."""

import datetime
from unittest.mock import patch

import cooked_input as ci

import time_tracker_config
import time_tracker_time


SAMPLE_CSV = (
    "Start,End,Elapsed,Client,Status,Notes\n"
    "2026-05-01T09:00:00,2026-05-01T10:30:00,90,IO,billed,May work\n"
    "2026-06-02T13:00:00,2026-06-02T14:00:00,60,IO,unbilled,June work\n"
)

RICH_CSV = SAMPLE_CSV + "2026-06-03T09:00:00,2026-06-03T10:00:00,30,ACME,unbilled,Acme work\n"

MIXED_CSV = SAMPLE_CSV + "2026-06-04T09:00:00,2026-06-04T10:00:00,30,IO,non-billable,Internal admin\n"

CLIENTS = {"IO": {"company": "IO Inc"}, "ACME": {"company": "Acme"}}


def _write_log(tmp_path, contents=SAMPLE_CSV):
    log = tmp_path / "time_log.csv"
    log.write_text(contents, encoding="utf-8")
    return log


def _gvars(tmp_path, time_log):
    return {"TT_TIME_LOG_FILE": str(time_log), "TT_CLIENTS_FILE": str(tmp_path / "clients.json")}


def test_list_time_no_file_reports_missing(tmp_path, capsys):
    missing = tmp_path / "nope.csv"
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, missing), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="IO", status="all")

    assert "No time log file found" in capsys.readouterr().out


def test_list_time_lists_all_entries(tmp_path, capsys):
    """status=all with a blank client prompt shows billed and unbilled entries."""
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_string", autospec=True, return_value=""),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client=None, status="all")

    output = capsys.readouterr().out
    assert "All time log entries" in output
    assert "May work" in output
    assert "June work" in output
    # 90 + 60 = 150 minutes total
    assert "150 minutes" in output


def test_list_time_defaults_to_unbilled_only(tmp_path, capsys):
    """status=unbilled shows only unbilled entries."""
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_string", autospec=True, return_value=""),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client=None, status="unbilled")

    output = capsys.readouterr().out
    assert "unbilled" in output.lower()
    assert "June work" in output
    assert "May work" not in output  # billed, excluded


def test_list_time_billed_only(tmp_path, capsys):
    """status=billed shows only billed entries."""
    log = _write_log(tmp_path, RICH_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="", status="billed")

    output = capsys.readouterr().out
    assert "billed time log entries" in output.lower()
    assert "May work" in output       # billed
    assert "June work" not in output  # unbilled, excluded
    assert "Acme work" not in output  # unbilled, excluded


def test_list_time_interactive_status_prompt(tmp_path, capsys):
    """status resolved through the interactive prompt (here: billed)."""
    log = _write_log(tmp_path, RICH_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_string", autospec=True, return_value="billed"),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="", status=None)

    output = capsys.readouterr().out
    assert "May work" in output       # billed
    assert "June work" not in output  # unbilled, excluded


def test_list_time_filters_by_first_date(tmp_path, capsys):
    log = _write_log(tmp_path)
    first = datetime.datetime(2026, 6, 1, 0, 0)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[first, None]),
    ):
        time_tracker_time.list_time(client="", status="all")

    output = capsys.readouterr().out
    assert "after" in output
    assert "June work" in output
    assert "May work" not in output


def test_list_time_filters_by_last_date(tmp_path, capsys):
    log = _write_log(tmp_path)
    last = datetime.datetime(2026, 5, 31, 0, 0)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, last]),
    ):
        time_tracker_time.list_time(client="", status="all")

    output = capsys.readouterr().out
    assert "before" in output
    assert "May work" in output
    assert "June work" not in output


def test_list_time_filters_by_range(tmp_path, capsys):
    log = _write_log(tmp_path)
    first = datetime.datetime(2026, 4, 1, 0, 0)
    last = datetime.datetime(2026, 5, 31, 0, 0)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[first, last]),
    ):
        time_tracker_time.list_time(client="", status="all")

    output = capsys.readouterr().out
    assert "between" in output
    assert "May work" in output
    assert "June work" not in output


def test_list_time_filters_by_client_cli_option(tmp_path, capsys):
    log = _write_log(tmp_path, RICH_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="IO", status="all")

    output = capsys.readouterr().out
    assert "time log entries for IO" in output
    assert "May work" in output
    assert "Acme work" not in output


def test_list_time_unbilled_default_with_client(tmp_path, capsys):
    log = _write_log(tmp_path, RICH_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="", status="unbilled")

    output = capsys.readouterr().out
    assert "unbilled" in output.lower()
    assert "June work" in output
    assert "Acme work" in output
    assert "May work" not in output


def test_list_time_interactive_client_prompt(tmp_path, capsys):
    """Client resolved through the interactive (validated) prompt; unbilled status."""
    log = _write_log(tmp_path, RICH_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_string", autospec=True, return_value="IO"),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client=None, status="unbilled")

    output = capsys.readouterr().out
    assert "June work" in output
    assert "May work" not in output   # billed, excluded
    assert "Acme work" not in output  # different client


# --------------------------------------------------------------------------- #
# Non-billable filtering and totals
# --------------------------------------------------------------------------- #
def test_list_time_non_billable_only(tmp_path, capsys):
    log = _write_log(tmp_path, MIXED_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="", status="non-billable")

    output = capsys.readouterr().out
    assert "Internal admin" in output
    assert "June work" not in output  # unbilled, excluded
    assert "May work" not in output   # billed, excluded


def test_list_time_unbilled_excludes_non_billable(tmp_path, capsys):
    log = _write_log(tmp_path, MIXED_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="", status="unbilled")

    output = capsys.readouterr().out
    assert "June work" in output
    assert "Internal admin" not in output


def test_list_time_splits_totals_when_results_are_mixed(tmp_path, capsys):
    log = _write_log(tmp_path, MIXED_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="", status="all")

    output = capsys.readouterr().out
    # 90 billed + 60 unbilled + 30 non-billable
    assert "Total: 180 minutes (3.00 hours)" in output
    assert "Billable:     150 minutes (2.50 hours)" in output
    assert "Non-billable: 30 minutes (0.50 hours)" in output


def test_list_time_does_not_split_totals_when_unmixed(tmp_path, capsys):
    """A single-status listing keeps its one unambiguous total."""
    log = _write_log(tmp_path, MIXED_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="", status="non-billable")

    output = capsys.readouterr().out
    assert "Total: 30 minutes (0.50 hours)" in output
    assert "Billable:" not in output


# --------------------------------------------------------------------------- #
# _default_status_for_client
# --------------------------------------------------------------------------- #
CLIENTS_WITH_NON_BILLABLE = {
    "IO": {"company": "IO Inc"},
    "PRO": {"company": "Pro Bono Inc", "non_billable": True},
}


def test_default_status_for_a_non_billable_client():
    assert time_tracker_time._default_status_for_client(CLIENTS_WITH_NON_BILLABLE, "PRO") == "non-billable"


def test_default_status_for_an_ordinary_client():
    assert time_tracker_time._default_status_for_client(CLIENTS_WITH_NON_BILLABLE, "IO") == "unbilled"


def test_default_status_for_all_clients_is_unbilled():
    assert time_tracker_time._default_status_for_client(CLIENTS_WITH_NON_BILLABLE, None) == "unbilled"


def test_default_status_for_client_is_case_insensitive():
    """--client accepts any case; the record lookup must not miss because of it."""
    assert time_tracker_time._default_status_for_client(CLIENTS_WITH_NON_BILLABLE, "pro") == "non-billable"


def test_default_status_for_an_unknown_client_is_unbilled():
    assert time_tracker_time._default_status_for_client(CLIENTS_WITH_NON_BILLABLE, "NOPE") == "unbilled"


def test_list_time_offers_non_billable_as_the_default_for_such_a_client(tmp_path):
    log = _write_log(tmp_path, MIXED_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS_WITH_NON_BILLABLE),
        patch("time_tracker_time.ci.get_string", autospec=True, return_value="non-billable") as mock_get_string,
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="PRO", status=None)

    assert mock_get_string.call_args.kwargs["default"] == "non-billable"


def test_list_time_offers_unbilled_as_the_default_for_a_billable_client(tmp_path):
    log = _write_log(tmp_path, MIXED_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS_WITH_NON_BILLABLE),
        patch("time_tracker_time.ci.get_string", autospec=True, return_value="unbilled") as mock_get_string,
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="IO", status=None)

    assert mock_get_string.call_args.kwargs["default"] == "unbilled"


def test_list_time_explicit_status_beats_the_client_default(tmp_path, capsys):
    """--status always wins, so a non-billable client can still be asked for anything."""
    log = _write_log(tmp_path, MIXED_CSV)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS_WITH_NON_BILLABLE),
        patch("time_tracker_time.ci.get_string", autospec=True) as mock_get_string,
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[None, None]),
    ):
        time_tracker_time.list_time(client="PRO", status="billed")

    mock_get_string.assert_not_called()
    assert "No time entries found" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# _format_time_totals
# --------------------------------------------------------------------------- #
def _entries(*pairs):
    return [{"elapsed": minutes, "status": status} for minutes, status in pairs]


def test_format_time_totals_all_billable_has_no_split():
    result = time_tracker_time._format_time_totals(_entries((60, "unbilled"), (30, "billed")))

    assert result == "Total: 90 minutes (1.50 hours)"


def test_format_time_totals_all_non_billable_has_no_split():
    result = time_tracker_time._format_time_totals(_entries((60, "non-billable")))

    assert result == "Total: 60 minutes (1.00 hours)"


def test_format_time_totals_mixed_splits():
    result = time_tracker_time._format_time_totals(_entries((90, "billed"), (30, "non-billable")))

    assert result.splitlines() == [
        "Total: 120 minutes (2.00 hours)",
        "  Billable:     90 minutes (1.50 hours)",
        "  Non-billable: 30 minutes (0.50 hours)",
    ]


def test_format_time_totals_empty():
    assert time_tracker_time._format_time_totals([]) == "Total: 0 minutes (0.00 hours)"


def test_list_time_no_matching_rows(tmp_path, capsys):
    log = _write_log(tmp_path)
    first = datetime.datetime(2027, 1, 1, 0, 0)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=[first, None]),
    ):
        time_tracker_time.list_time(client="", status="all")

    assert "No time entries found" in capsys.readouterr().out


def test_list_time_cancelled_on_interrupt(tmp_path, capsys):
    log = _write_log(tmp_path)
    with (
        patch.dict(time_tracker_config.global_vars, _gvars(tmp_path, log), clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=ci.GetInputInterrupt),
    ):
        time_tracker_time.list_time(client="", status="all")

    assert "cancelled" in capsys.readouterr().out.lower()
