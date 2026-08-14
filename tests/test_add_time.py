"""Tests for the add-time command and the add_time_to_log helper."""

import datetime
from unittest.mock import patch

import cooked_input as ci
import pytest
import typer

import time_tracker_config
import time_tracker_time


# --------------------------------------------------------------------------- #
# add_time_to_log
# --------------------------------------------------------------------------- #
def test_add_time_to_log_creates_file_with_header(tmp_path, capsys):
    log = tmp_path / "time_log.csv"
    gvars = {"TT_TIME_LOG_FILE": str(log), "TT_TIME_LOG_FILENAME": "time_log.csv"}
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 30)

    with patch.dict(time_tracker_config.global_vars, gvars, clear=True):
        result = time_tracker_time.add_time_to_log(start, end, 90, "IO", "Did work")

    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Start,End,Elapsed,Client,Status,Notes"
    assert lines[1].startswith("2026-05-01T09:00:00,2026-05-01T10:30:00,90,IO,unbilled,Did work")
    assert "Successfully appended" in capsys.readouterr().out
    assert result is True


def test_add_time_to_log_appends_without_duplicate_header(tmp_path):
    log = tmp_path / "time_log.csv"
    log.write_text("Start,End,Elapsed,Client,Status,Notes\n", encoding="utf-8")
    gvars = {"TT_TIME_LOG_FILE": str(log), "TT_TIME_LOG_FILENAME": "time_log.csv"}
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 0)

    with patch.dict(time_tracker_config.global_vars, gvars, clear=True):
        time_tracker_time.add_time_to_log(start, end, 60, "IO", "More work")

    contents = log.read_text(encoding="utf-8")
    assert contents.count("Start,End,Elapsed,Client,Status,Notes") == 1
    assert "More work" in contents


def test_add_time_to_log_records_billed_status(tmp_path):
    log = tmp_path / "time_log.csv"
    gvars = {"TT_TIME_LOG_FILE": str(log), "TT_TIME_LOG_FILENAME": "time_log.csv"}
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 0)

    with patch.dict(time_tracker_config.global_vars, gvars, clear=True):
        time_tracker_time.add_time_to_log(start, end, 60, "IO", "Done", status="billed")

    assert ",IO,billed,Done" in log.read_text(encoding="utf-8")


def test_add_time_to_log_records_non_billable_status(tmp_path):
    log = tmp_path / "time_log.csv"
    gvars = {"TT_TIME_LOG_FILE": str(log), "TT_TIME_LOG_FILENAME": "time_log.csv"}
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 0)

    with patch.dict(time_tracker_config.global_vars, gvars, clear=True):
        time_tracker_time.add_time_to_log(start, end, 60, "PRO", "Board meeting", status="non-billable")

    assert ",PRO,non-billable,Board meeting" in log.read_text(encoding="utf-8")


def test_add_time_to_log_handles_permission_error(tmp_path, capsys):
    gvars = {"TT_TIME_LOG_FILE": str(tmp_path / "time_log.csv"), "TT_TIME_LOG_FILENAME": "time_log.csv"}
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 0)

    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("builtins.open", side_effect=PermissionError),
    ):
        result = time_tracker_time.add_time_to_log(start, end, 60, "IO", "x")

    assert "Could not write" in capsys.readouterr().out
    assert result is False


def test_add_time_to_log_reports_an_os_error(tmp_path, capsys):
    """Any I/O failure the user can act on is reported, not just PermissionError."""
    gvars = {"TT_TIME_LOG_FILE": str(tmp_path / "time_log.csv"), "TT_TIME_LOG_FILENAME": "time_log.csv"}
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 0)

    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("builtins.open", side_effect=OSError("no space left on device")),
    ):
        result = time_tracker_time.add_time_to_log(start, end, 60, "IO", "x")

    assert "no space left on device" in capsys.readouterr().out
    assert result is False


def test_add_time_to_log_lets_an_unexpected_error_propagate(tmp_path):
    """A bug in the write path must raise, not be flattened into a one-line message."""
    gvars = {"TT_TIME_LOG_FILE": str(tmp_path / "time_log.csv"), "TT_TIME_LOG_FILENAME": "time_log.csv"}
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 0)

    with (
        patch.dict(time_tracker_config.global_vars, gvars, clear=True),
        patch("builtins.open", side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError, match="boom"),
    ):
        time_tracker_time.add_time_to_log(start, end, 60, "IO", "x")


# --------------------------------------------------------------------------- #
# add_time command - fully interactive (no CLI flags)
# --------------------------------------------------------------------------- #
GVARS = {"TT_MAX_MINUTES_CONFIRMATION": 240, "TT_CLIENTS_FILE": "clients.json"}
CLIENTS = {"TEST": {"company": "FakeCo"}}


def test_add_time_confirmed_writes_entry():
    dates = [
        datetime.datetime(2026, 5, 1, 0, 0),   # date
        datetime.datetime(2026, 5, 1, 9, 0),   # start
        datetime.datetime(2026, 5, 1, 10, 30), # end
    ]
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=dates),
        patch("time_tracker_time.ci.get_string", autospec=True, side_effect=["TEST", "Did work"]),
        patch("time_tracker_time.ci.get_yes_no", autospec=True, return_value="yes"),
        patch("time_tracker_time.add_time_to_log", return_value=True) as mock_add,
    ):
        time_tracker_time.add_time(client=None, date=None, start=None, end=None, notes=None, yes=False, non_billable=None)

    mock_add.assert_called_once()
    # elapsed minutes == 90, client passed through as 4th positional arg
    assert mock_add.call_args.args[2] == 90
    assert mock_add.call_args.args[3] == "TEST"


# --------------------------------------------------------------------------- #
# add_time command - non-billable resolution
# --------------------------------------------------------------------------- #
CLIENTS_WITH_NON_BILLABLE = {
    "TEST": {"company": "FakeCo"},
    "PRO": {"company": "Pro Bono Inc", "non_billable": True},
}


def _run_add_time(client: str, non_billable: bool | None, capture=None):
    """Drive one confirmed add-time run, returning the patched add_time_to_log mock."""
    dates = [
        datetime.datetime(2026, 5, 1, 0, 0),
        datetime.datetime(2026, 5, 1, 9, 0),
        datetime.datetime(2026, 5, 1, 10, 30),
    ]
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS_WITH_NON_BILLABLE),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=dates),
        patch("time_tracker_time.ci.get_string", autospec=True, side_effect=[client, "Did work"]),
        patch("time_tracker_time.ci.get_yes_no", autospec=True, return_value="yes"),
        patch("time_tracker_time.add_time_to_log", return_value=True) as mock_add,
    ):
        time_tracker_time.add_time(client=None, date=None, start=None, end=None, notes=None, yes=False,
                          non_billable=non_billable)

    return mock_add


def test_add_time_defaults_to_the_clients_non_billable_flag():
    mock_add = _run_add_time("PRO", non_billable=None)

    assert mock_add.call_args.kwargs["status"] == "non-billable"


def test_add_time_defaults_to_unbilled_for_an_ordinary_client():
    mock_add = _run_add_time("TEST", non_billable=None)

    assert mock_add.call_args.kwargs["status"] == "unbilled"


def test_add_time_non_billable_flag_overrides_a_billable_client():
    mock_add = _run_add_time("TEST", non_billable=True)

    assert mock_add.call_args.kwargs["status"] == "non-billable"


def test_add_time_billable_flag_overrides_a_non_billable_client():
    mock_add = _run_add_time("PRO", non_billable=False)

    assert mock_add.call_args.kwargs["status"] == "unbilled"


def test_add_time_summary_shows_the_status(capsys):
    _run_add_time("PRO", non_billable=None)

    assert "Status:     non-billable" in capsys.readouterr().out


def test_add_time_no_clients_aborts(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value={}),
        patch("time_tracker_time.add_time_to_log") as mock_add,
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_time.add_time(client=None, date=None, start=None, end=None, notes=None, yes=False, non_billable=None)

    assert exc_info.value.exit_code == 1
    assert "No clients found" in capsys.readouterr().out
    mock_add.assert_not_called()


def test_add_time_reentry_then_confirm():
    dates = [
        datetime.datetime(2026, 5, 1, 0, 0),
        datetime.datetime(2026, 5, 1, 9, 0),
        datetime.datetime(2026, 5, 1, 10, 30),
        datetime.datetime(2026, 5, 1, 0, 0),
        datetime.datetime(2026, 5, 1, 9, 0),
        datetime.datetime(2026, 5, 1, 11, 0),
    ]
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=dates),
        patch("time_tracker_time.ci.get_string", autospec=True, side_effect=["TEST", "Did work", "TEST", "Did work"]),
        patch("time_tracker_time.ci.get_yes_no", autospec=True, side_effect=["no", "yes"]),
        patch("time_tracker_time.add_time_to_log", return_value=True) as mock_add,
    ):
        time_tracker_time.add_time(client=None, date=None, start=None, end=None, notes=None, yes=False, non_billable=None)

    mock_add.assert_called_once()
    # Second pass: 9:00 -> 11:00 == 120 minutes
    assert mock_add.call_args.args[2] == 120


def test_add_time_rollover_past_midnight():
    dates = [
        datetime.datetime(2026, 5, 1, 0, 0),
        datetime.datetime(2026, 5, 1, 10, 30),  # start later than end
        datetime.datetime(2026, 5, 1, 9, 0),    # end earlier
    ]
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=dates),
        patch("time_tracker_time.ci.get_string", autospec=True, side_effect=["TEST", "overnight"]),
        patch("time_tracker_time.ci.get_yes_no", autospec=True, return_value="yes"),
        patch("time_tracker_time.add_time_to_log", return_value=True) as mock_add,
    ):
        time_tracker_time.add_time(client=None, date=None, start=None, end=None, notes=None, yes=False, non_billable=None)

    # abs(10:30 - 9:00) == 90 minutes
    assert mock_add.call_args.args[2] == 90


def test_add_time_warns_when_exceeding_threshold(capsys):
    dates = [
        datetime.datetime(2026, 5, 1, 0, 0),
        datetime.datetime(2026, 5, 1, 9, 0),
        datetime.datetime(2026, 5, 1, 11, 0),  # 120 minutes
    ]
    with (
        patch.dict(time_tracker_config.global_vars, {"TT_MAX_MINUTES_CONFIRMATION": 60, "TT_CLIENTS_FILE": "clients.json"}, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=dates),
        patch("time_tracker_time.ci.get_string", autospec=True, side_effect=["TEST", "long task"]),
        patch("time_tracker_time.ci.get_yes_no", autospec=True, return_value="yes"),
        patch("time_tracker_time.add_time_to_log", return_value=True),
    ):
        time_tracker_time.add_time(client=None, date=None, start=None, end=None, notes=None, yes=False, non_billable=None)

    assert "WARNING" in capsys.readouterr().out


def test_add_time_cancelled_on_interrupt(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_string", autospec=True, side_effect=ci.GetInputInterrupt),
        patch("time_tracker_time.add_time_to_log") as mock_add,
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_time.add_time(client=None, date=None, start=None, end=None, notes=None, yes=False, non_billable=None)

    assert exc_info.value.exit_code == 1
    assert "cancelled" in capsys.readouterr().out.lower()
    mock_add.assert_not_called()


def test_add_time_write_failure_exits_nonzero():
    dates = [
        datetime.datetime(2026, 5, 1, 0, 0),
        datetime.datetime(2026, 5, 1, 9, 0),
        datetime.datetime(2026, 5, 1, 10, 30),
    ]
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=dates),
        patch("time_tracker_time.ci.get_string", autospec=True, side_effect=["TEST", "Did work"]),
        patch("time_tracker_time.ci.get_yes_no", autospec=True, return_value="yes"),
        patch("time_tracker_time.add_time_to_log", return_value=False),
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_time.add_time(client=None, date=None, start=None, end=None, notes=None, yes=False, non_billable=None)

    assert exc_info.value.exit_code == 1


# --------------------------------------------------------------------------- #
# add_time command - CLI flags
# --------------------------------------------------------------------------- #
def test_add_time_all_flags_fully_non_interactive():
    """All 5 flags + --yes: no prompts, no confirmation, entry added directly."""
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True) as mock_get_date,
        patch("time_tracker_time.ci.get_string", autospec=True) as mock_get_string,
        patch("time_tracker_time.ci.get_yes_no", autospec=True) as mock_get_yes_no,
        patch("time_tracker_time.add_time_to_log", return_value=True) as mock_add,
    ):
        time_tracker_time.add_time(
            client="test",
            date="2026-05-01",
            start="9:00 am",
            end="10:30 am",
            notes="Did work",
            yes=True,
            non_billable=None,
        )

    mock_get_date.assert_not_called()
    mock_get_string.assert_not_called()
    mock_get_yes_no.assert_not_called()
    mock_add.assert_called_once()
    assert mock_add.call_args.args[2] == 90
    assert mock_add.call_args.args[3] == "TEST"
    assert mock_add.call_args.args[4] == "Did work"


def test_add_time_partial_flags_prompts_for_rest():
    """--client/--notes given; date/start/end still prompted (mix-and-match)."""
    dates = [
        datetime.datetime(2026, 5, 1, 0, 0),   # date
        datetime.datetime(2026, 5, 1, 9, 0),   # start
        datetime.datetime(2026, 5, 1, 10, 30), # end
    ]
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=dates) as mock_get_date,
        patch("time_tracker_time.ci.get_string", autospec=True) as mock_get_string,
        patch("time_tracker_time.ci.get_yes_no", autospec=True, return_value="yes"),
        patch("time_tracker_time.add_time_to_log", return_value=True) as mock_add,
    ):
        time_tracker_time.add_time(client="TEST", date=None, start=None, end=None, notes="Did work", yes=False,
                          non_billable=None)

    # client/notes never prompted for; date/start/end were
    mock_get_string.assert_not_called()
    assert mock_get_date.call_count == 3
    assert mock_add.call_args.args[2] == 90
    assert mock_add.call_args.args[3] == "TEST"
    assert mock_add.call_args.args[4] == "Did work"


def test_add_time_unknown_client_flag_exits_nonzero(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.add_time_to_log") as mock_add,
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_time.add_time(client="NOPE", date=None, start=None, end=None, notes=None, yes=False,
                          non_billable=None)

    assert exc_info.value.exit_code == 1
    assert "unknown client" in capsys.readouterr().out.lower()
    mock_add.assert_not_called()


def test_add_time_unparseable_date_flag_exits_nonzero(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.add_time_to_log") as mock_add,
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_time.add_time(client="TEST", date="not-a-real-date-xyz", start=None, end=None, notes=None,
                          yes=False, non_billable=None)

    assert exc_info.value.exit_code == 1
    assert "could not parse" in capsys.readouterr().out.lower()
    mock_add.assert_not_called()


def test_add_time_reentry_after_all_flags_falls_back_to_interactive():
    """Rejecting the confirmation on a fully-flagged first pass drops into an
    interactive re-entry (flags only ever apply on the first pass)."""
    dates = [
        datetime.datetime(2026, 5, 1, 0, 0),
        datetime.datetime(2026, 5, 1, 9, 0),
        datetime.datetime(2026, 5, 1, 11, 0),
    ]
    with (
        patch.dict(time_tracker_config.global_vars, GVARS, clear=True),
        patch("time_tracker_time.read_json_args", return_value=CLIENTS),
        patch("time_tracker_time.ci.get_date", autospec=True, side_effect=dates),
        patch("time_tracker_time.ci.get_string", autospec=True, side_effect=["TEST", "Did work"]),
        patch("time_tracker_time.ci.get_yes_no", autospec=True, side_effect=["no", "yes"]),
        patch("time_tracker_time.add_time_to_log", return_value=True) as mock_add,
    ):
        time_tracker_time.add_time(client="TEST", date="2026-05-01", start="9:00 am", end="10:30 am", notes="Did work",
                          yes=False, non_billable=None)

    mock_add.assert_called_once()
    # Second (interactive re-entry) pass: 9:00 -> 11:00 == 120 minutes
    assert mock_add.call_args.args[2] == 120
