"""Tests for the edit-client command."""

from unittest.mock import patch

import cooked_input as ci
import pytest
import typer

import time_tracker_clients
import time_tracker_config


FAKE_GLOBAL_VARS = {
    "TT_CLIENTS_JSON_DIR": "./data",
    "TT_CLIENTS_FILE": "./data/clients.json",
}

CLIENTS = {
    "TEST": {
        "company": "FakeCo",
        "contact": "Fake Client",
        "phone": "(123) 456-8900",
        "addr1": "Fake addr1",
        "addr2": "Fake City, FS 00000",
        "rate_hr": 100,
        "rate_day": 800,
    },
    "RET": {
        "company": "Retainer Corp",
        "contact": "Retainer Contact",
        "rate_hr": 100,
        "retainer_hrs": 20,
        "retainer_rate": 1500,
    },
    "PRO": {
        "company": "Pro Bono Inc",
        "contact": "Pro Contact",
        "rate_hr": 100,
        "non_billable": True,
    },
}


def clients_copy():
    """A deep-enough copy: the commands replace records rather than mutate them."""
    return {code: dict(record) for code, record in CLIENTS.items()}


def edit_client(**overrides):
    """Call edit_client with every parameter supplied.

    Typer leaves an ``OptionInfo`` object in place of the default when a command is
    called directly as a function, so an omitted argument would read as truthy rather
    than as "flag not given".
    """
    params = {
        "client": None, "company": None, "contact": None, "phone": None, "addr1": None,
        "addr2": None, "rate_hr": None, "rate_day": None, "retainer_hrs": None,
        "retainer_rate": None, "non_billable": None, "yes": False,
    }
    params.update(overrides)
    return time_tracker_clients.edit_client(**params)


# --------------------------------------------------------------------------- #
# Flag-driven (non-interactive) use
# --------------------------------------------------------------------------- #
def test_edit_client_changes_one_field_and_leaves_the_rest():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True) as mock_get_string,
        patch("time_tracker_clients.ci.get_float", autospec=True) as mock_get_float,
        patch("time_tracker_clients.ci.get_yes_no", autospec=True) as mock_get_yes_no,
    ):
        edit_client(client="TEST", rate_hr=175.0, yes=True)

    mock_get_string.assert_not_called()
    mock_get_float.assert_not_called()
    mock_get_yes_no.assert_not_called()

    saved = mock_write.call_args[0][1]
    assert saved["TEST"] == {**CLIENTS["TEST"], "rate_hr": 175.0}
    assert saved["RET"] == CLIENTS["RET"]  # other clients are untouched


def test_edit_client_keeps_a_fractional_rate():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
    ):
        edit_client(client="TEST", rate_hr=17.50, yes=True)

    assert mock_write.call_args[0][1]["TEST"]["rate_hr"] == 17.5


def test_edit_client_accepts_a_lower_case_client_code():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
    ):
        edit_client(client="test", company="Renamed Co", yes=True)

    assert mock_write.call_args[0][1]["TEST"]["company"] == "Renamed Co"


def test_edit_client_preserves_a_field_time_tracker_does_not_know():
    """clients.json is hand-edited: an unrecognised field is data, not junk."""
    clients = clients_copy()
    clients["TEST"]["email"] = "fake@example.com"

    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients),
        patch("time_tracker_clients.write_json_args") as mock_write,
    ):
        edit_client(client="TEST", rate_hr=175.0, yes=True)

    assert mock_write.call_args[0][1]["TEST"]["email"] == "fake@example.com"


def test_edit_client_billable_removes_the_non_billable_flag():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
    ):
        edit_client(client="PRO", non_billable=False, yes=True)

    record = mock_write.call_args[0][1]["PRO"]
    # A billable client is the default, so the key goes rather than being set to false.
    assert "non_billable" not in record
    assert record["rate_hr"] == 100


def test_edit_client_non_billable_keeps_an_existing_rate():
    """Flipping a client to non-billable must not throw away the rate it had."""
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_float", autospec=True) as mock_get_float,
    ):
        edit_client(client="TEST", non_billable=True, yes=True)

    mock_get_float.assert_not_called()
    record = mock_write.call_args[0][1]["TEST"]
    assert record["non_billable"] is True
    assert record["rate_hr"] == 100
    assert record["rate_day"] == 800


def test_edit_client_yes_keeps_an_existing_retainer():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
    ):
        edit_client(client="RET", rate_hr=125.0, yes=True)

    record = mock_write.call_args[0][1]["RET"]
    assert record["retainer_hrs"] == 20
    assert record["retainer_rate"] == 1500


def test_edit_client_no_changes_does_not_write(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_yes_no", autospec=True) as mock_get_yes_no,
    ):
        edit_client(client="TEST", yes=True)

    assert "No changes" in capsys.readouterr().out
    mock_get_yes_no.assert_not_called()  # nothing to confirm
    mock_write.assert_not_called()


# --------------------------------------------------------------------------- #
# Interactive use
# --------------------------------------------------------------------------- #
def test_edit_client_answering_no_to_the_retainer_clears_both_fields():
    """The only way to end a retainer - and it must not leave half of one behind."""
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True, side_effect=["Retainer Corp", "Retainer Contact", None, None, None]),
        patch("time_tracker_clients.ci.get_float", autospec=True, side_effect=[100, None]),
        # billable? -> yes, retainer? -> no, save? -> yes
        patch("time_tracker_clients.ci.get_yes_no", autospec=True, side_effect=["yes", "no", "yes"]),
    ):
        edit_client(client="RET")

    record = mock_write.call_args[0][1]["RET"]
    assert "retainer_hrs" not in record
    assert "retainer_rate" not in record
    assert record["rate_hr"] == 100


def test_edit_client_without_a_client_flag_lists_the_clients(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.prompt_for_client", return_value="TEST") as mock_prompt,
        patch("time_tracker_clients.ci.get_string", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_float", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_yes_no", autospec=True, side_effect=["yes", "no", "yes"]),
    ):
        edit_client(rate_hr=175.0)

    output = capsys.readouterr().out
    mock_prompt.assert_called_once()
    # The code is what gets typed, but nobody thinks about a client by its code.
    assert "FakeCo" in output
    assert "TEST" in output
    mock_write.assert_called_once()


def test_edit_client_shows_current_and_new_values(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args"),
        patch("time_tracker_clients.ci.get_string", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_float", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_yes_no", autospec=True, return_value="yes"),
    ):
        edit_client(client="TEST", rate_hr=175.0, yes=False)

    output = capsys.readouterr().out
    assert "Changes to client TEST" in output
    assert "Current" in output and "New" in output
    assert "175.0" in output
    assert "* = changed" in output


# --------------------------------------------------------------------------- #
# Failure paths - none of them may write
# --------------------------------------------------------------------------- #
def test_edit_client_rejects_an_unknown_client(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
        pytest.raises(typer.Exit) as exc_info,
    ):
        edit_client(client="NOPE", rate_hr=175.0, yes=True)

    assert exc_info.value.exit_code == 1
    assert "unknown client NOPE" in capsys.readouterr().out
    mock_write.assert_not_called()


def test_edit_client_with_no_clients_at_all(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
        pytest.raises(typer.Exit) as exc_info,
    ):
        edit_client(client="TEST", yes=True)

    assert exc_info.value.exit_code == 1
    assert "add-client" in capsys.readouterr().out
    mock_write.assert_not_called()


def test_edit_client_rejects_a_negative_rate(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
        pytest.raises(typer.Exit) as exc_info,
    ):
        edit_client(client="TEST", rate_hr=-1.0, yes=True)

    assert exc_info.value.exit_code == 1
    assert "must not be negative" in capsys.readouterr().out
    mock_write.assert_not_called()


def test_edit_client_confirmation_no_does_not_save(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_float", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_yes_no", autospec=True, return_value="no"),
        pytest.raises(typer.Exit) as exc_info,
    ):
        edit_client(client="TEST", rate_hr=175.0)

    assert exc_info.value.exit_code == 1
    assert "cancelled" in capsys.readouterr().out.lower()
    mock_write.assert_not_called()


def test_edit_client_rejecting_the_save_offers_another_pass():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True, return_value=None) as mock_get_string,
        # pass 1 prompts only for rate_day (rate_hr came from the flag); pass 2 for both
        patch("time_tracker_clients.ci.get_float", autospec=True, side_effect=[None, 200.0, None]),
        # billable, retainer, save? -> no, change? -> yes, billable, retainer, save? -> yes
        patch("time_tracker_clients.ci.get_yes_no", autospec=True,
              side_effect=["yes", "no", "no", "yes", "yes", "no", "yes"]),
    ):
        edit_client(client="TEST", rate_hr=175.0)

    assert mock_write.call_args[0][1]["TEST"]["rate_hr"] == 200.0
    # The second pass starts from the first pass's answers, not from the stored record.
    company_calls = [c for c in mock_get_string.call_args_list if "Company" in c.kwargs["prompt"]]
    assert company_calls[-1].kwargs["default"] == "FakeCo"


def test_edit_client_re_entry_still_compares_against_the_stored_record(capsys):
    """The Current column must track what is on disk, not the previous attempt."""
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args"),
        patch("time_tracker_clients.ci.get_string", autospec=True, return_value=None),
        # pass 1 prompts only for rate_day (rate_hr came from the flag); pass 2 for both
        patch("time_tracker_clients.ci.get_float", autospec=True, side_effect=[None, 200.0, None]),
        patch("time_tracker_clients.ci.get_yes_no", autospec=True,
              side_effect=["yes", "no", "no", "yes", "yes", "no", "yes"]),
    ):
        edit_client(client="TEST", rate_hr=175.0)

    # Both confirmations compare against the stored 100, not against each other.
    assert capsys.readouterr().out.count("| 100 ") == 2


def test_edit_client_declining_to_change_answers_cancels(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_float", autospec=True, return_value=None),
        # billable, retainer, save? -> no, change? -> no
        patch("time_tracker_clients.ci.get_yes_no", autospec=True, side_effect=["yes", "no", "no", "no"]),
        pytest.raises(typer.Exit) as exc_info,
    ):
        edit_client(client="TEST", rate_hr=175.0)

    assert exc_info.value.exit_code == 1
    assert "cancelled" in capsys.readouterr().out.lower()
    mock_write.assert_not_called()


def test_edit_client_interrupt_does_not_save(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True, side_effect=ci.GetInputInterrupt),
        pytest.raises(typer.Exit) as exc_info,
    ):
        edit_client(client="TEST")

    assert exc_info.value.exit_code == 1
    assert "cancelled" in capsys.readouterr().out.lower()
    mock_write.assert_not_called()


def test_edit_client_reports_a_failed_write(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_copy()),
        patch("time_tracker_clients.write_json_args", side_effect=OSError("read-only")),
        pytest.raises(typer.Exit) as exc_info,
    ):
        edit_client(client="TEST", rate_hr=175.0, yes=True)

    assert exc_info.value.exit_code == 1
    assert "could not write" in capsys.readouterr().out
