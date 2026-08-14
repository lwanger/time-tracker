"""Tests for the set-next-invoice command."""

from unittest.mock import patch

import cooked_input as ci
import pytest
import typer

import time_tracker_config
import time_tracker_invoices


FAKE_GLOBAL_VARS = {
    "TT_INVOICES_FILE": "./data/invoices.json",
}

FAKE_INV_DATA = {
    "next_invoice": 102,
}


def test_set_next_invoice_updates_number(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=dict(FAKE_INV_DATA)),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.ci.get_int", autospec=True, return_value=105),
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="yes"),
    ):
        time_tracker_invoices.set_next_inv(number=None, yes=False)

    output = capsys.readouterr().out
    assert "102" in output
    assert "105" in output

    saved = mock_write.call_args[0][1]
    assert saved["next_invoice"] == 105


def test_set_next_invoice_confirm_no_does_not_save(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=dict(FAKE_INV_DATA)),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.ci.get_int", autospec=True, return_value=110),
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="no"),
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_invoices.set_next_inv(number=None, yes=False)

    assert exc_info.value.exit_code == 1
    output = capsys.readouterr().out
    assert "cancelled" in output.lower()
    mock_write.assert_not_called()


def test_set_next_invoice_interrupt_does_not_save(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=dict(FAKE_INV_DATA)),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.ci.get_int", autospec=True, side_effect=ci.GetInputInterrupt),
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_invoices.set_next_inv(number=None, yes=False)

    assert exc_info.value.exit_code == 1
    output = capsys.readouterr().out
    assert "cancelled" in output.lower()
    mock_write.assert_not_called()


def test_set_next_invoice_missing_data(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_invoices.read_json_args", return_value={}),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_invoices.set_next_inv(number=None, yes=False)

    assert exc_info.value.exit_code == 1
    output = capsys.readouterr().out
    assert "No invoices data" in output
    mock_write.assert_not_called()


# --------------------------------------------------------------------------- #
# set_next_inv command - CLI flags
# --------------------------------------------------------------------------- #
def test_set_next_invoice_number_and_yes_skips_prompts():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=dict(FAKE_INV_DATA)),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.ci.get_int", autospec=True) as mock_get_int,
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True) as mock_get_yes_no,
    ):
        time_tracker_invoices.set_next_inv(number=200, yes=True)

    mock_get_int.assert_not_called()
    mock_get_yes_no.assert_not_called()
    saved = mock_write.call_args[0][1]
    assert saved["next_invoice"] == 200


def test_set_next_invoice_number_without_yes_still_confirms():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=dict(FAKE_INV_DATA)),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        patch("time_tracker_invoices.ci.get_int", autospec=True) as mock_get_int,
        patch("time_tracker_invoices.ci.get_yes_no", autospec=True, return_value="yes") as mock_get_yes_no,
    ):
        time_tracker_invoices.set_next_inv(number=200, yes=False)

    mock_get_int.assert_not_called()
    mock_get_yes_no.assert_called_once()
    saved = mock_write.call_args[0][1]
    assert saved["next_invoice"] == 200


def test_set_next_invoice_invalid_number_exits_nonzero(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_invoices.read_json_args", return_value=dict(FAKE_INV_DATA)),
        patch("time_tracker_invoices.write_json_args") as mock_write,
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_invoices.set_next_inv(number=0, yes=False)

    assert exc_info.value.exit_code == 1
    assert "must be at least 1" in capsys.readouterr().out
    mock_write.assert_not_called()
