"""Tests for the shared CLI plumbing in time_tracker_cli.

The version callback is covered in test_init_version.py, alongside main().
"""

import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

import cooked_input as ci

import time_tracker_cli


PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


# --------------------------------------------------------------------------- #
# Version resolution
# --------------------------------------------------------------------------- #
def test_resolve_version_reads_the_installed_distribution():
    with patch("time_tracker_cli.version", return_value="9.9.9") as mock_version:
        assert time_tracker_cli.resolve_version() == "9.9.9"

    mock_version.assert_called_once_with("time-tracker")


def test_resolve_version_falls_back_without_an_installed_distribution():
    """A source checkout has no distribution metadata to query."""
    with patch("time_tracker_cli.version", side_effect=PackageNotFoundError("time-tracker")):
        assert time_tracker_cli.resolve_version() == time_tracker_cli.FALLBACK_VERSION


def test_fallback_version_matches_pyproject():
    """The hand-maintained fallback drifted once already; keep it pinned to the real version."""
    with PYPROJECT.open("rb") as pyproject_file:
        declared_version = tomllib.load(pyproject_file)["project"]["version"]

    assert time_tracker_cli.FALLBACK_VERSION == declared_version


# --------------------------------------------------------------------------- #
# parse_flexible_datetime
# --------------------------------------------------------------------------- #
def test_parse_flexible_datetime_parses_iso_date():
    result = time_tracker_cli.parse_flexible_datetime("2026-05-01")

    assert result.year == 2026
    assert result.month == 5
    assert result.day == 1


def test_parse_flexible_datetime_parses_time_of_day():
    result = time_tracker_cli.parse_flexible_datetime("9:00 am")

    assert result.hour == 9
    assert result.minute == 0


def test_parse_flexible_datetime_returns_none_for_garbage():
    result = time_tracker_cli.parse_flexible_datetime("not-a-real-date-xyz")

    assert result is None

# --------------------------------------------------------------------------- #
# cooked_input command callbacks
# --------------------------------------------------------------------------- #
def test_cancel_action_returns_cancel_response():
    response = time_tracker_cli.cancel_action("/cancel", "", {})

    assert response.action == ci.COMMAND_ACTION_CANCEL


def test_help_action_prints_help_and_returns_nop(capsys):
    response = time_tracker_cli.help_action("/help", "", {})

    output = capsys.readouterr().out
    assert "Commands:" in output
    assert "/help" in output
    assert response.action == ci.COMMAND_ACTION_NOP
