"""Tests for the --version callback and the main() entry point.

Configuration resolution itself is covered in test_load_config.py.
"""

from unittest.mock import patch

import cooked_input as ci
import pytest
import typer

import time_tracker
import time_tracker_cli
import time_tracker_config


def test_version_callback_prints_and_exits(capsys):
    with pytest.raises(typer.Exit):
        time_tracker_cli._version_callback(True)

    assert "time-tracker version" in capsys.readouterr().out


def test_version_callback_noop_when_false():
    # Should not raise and should produce no exit
    assert time_tracker_cli._version_callback(False) is None


def test_main_initializes_global_vars_and_runs_app():
    config = time_tracker.Config(values={"TT_FOO": "bar"}, sources={"TT_FOO": "environment"})
    with (
        patch("time_tracker.load_config", return_value=config),
        patch("time_tracker.app") as mock_app,
        patch.dict(time_tracker_config.global_vars, {}, clear=True),
        patch.dict(time_tracker_config.config_sources, {}, clear=True),
    ):
        time_tracker.main()
        mock_app.assert_called_once()
        assert time_tracker_config.global_vars == {"TT_FOO": "bar"}
        assert time_tracker_config.config_sources == {"TT_FOO": "environment"}


def test_main_reports_config_warnings(capsys):
    """An ignored derived setting has to reach the user, not just the Config object."""
    config = time_tracker.Config(
        values={"TT_FOO": "bar"},
        sources={"TT_FOO": "environment"},
        warnings=["TT_TIME_LOG_FILE is set in some.env but is computed"],
    )
    with (
        patch("time_tracker.load_config", return_value=config),
        patch("time_tracker.app"),
        patch.dict(time_tracker_config.global_vars, {}, clear=True),
        patch.dict(time_tracker_config.config_sources, {}, clear=True),
    ):
        time_tracker.main()

    output = capsys.readouterr().out
    assert "Warning:" in output
    assert "TT_TIME_LOG_FILE" in output


def test_main_handles_interrupt(capsys):
    with (
        patch("time_tracker.load_config", return_value=time_tracker.Config()),
        patch("time_tracker.app", side_effect=ci.GetInputInterrupt),
    ):
        time_tracker.main()

    assert "cancelled" in capsys.readouterr().out.lower()


# --------------------------------------------------------------------------- #
# main() - a broken config must not hide the command that repairs it
# --------------------------------------------------------------------------- #
def test_main_exits_on_config_error(capsys):
    with (
        patch("time_tracker.load_config", side_effect=time_tracker.ConfigError("bad value")),
        patch("time_tracker.app") as mock_app,
        patch.object(time_tracker.sys, "argv", ["time-tracker", "list-env"]),
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker.main()

    assert exc_info.value.exit_code == 1
    output = capsys.readouterr().out
    assert "bad value" in output
    assert "time-tracker init" in output  # points at the fix
    mock_app.assert_not_called()


def test_main_still_runs_init_when_config_is_broken(capsys):
    """A bad value must not lock the user out of the command that rewrites it."""
    with (
        patch("time_tracker.load_config", side_effect=time_tracker.ConfigError("bad value")),
        patch("time_tracker.app") as mock_app,
        patch.object(time_tracker.sys, "argv", ["time-tracker", "init"]),
        patch.dict(time_tracker_config.global_vars, {}, clear=True),
        patch.dict(time_tracker_config.config_sources, {}, clear=True),
    ):
        time_tracker.main()

    output = capsys.readouterr().out
    assert "Warning" in output
    assert "bad value" in output
    mock_app.assert_called_once()
