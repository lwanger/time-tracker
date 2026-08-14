"""Tests for the add-client command."""

import json
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

EXISTING_CLIENTS = {
    "TEST": {
        "company": "FakeCo",
        "contact": "Fake Client",
        "phone": "(123) 456-8900",
        "rate_hr": 100,
    },
}


def add_client(**overrides):
    """Call add_client with every parameter supplied.

    Typer leaves an ``OptionInfo`` object in place of the default when a command is
    called directly as a function, so an omitted argument would read as truthy rather
    than as "flag not given".
    """
    params = {
        "code": None, "company": None, "contact": None, "phone": None, "addr1": None,
        "addr2": None, "rate_hr": None, "rate_day": None, "retainer_hrs": None,
        "retainer_rate": None, "non_billable": None, "yes": False,
    }
    params.update(overrides)
    return time_tracker_clients.add_client(**params)


# --------------------------------------------------------------------------- #
# Flag-driven (non-interactive) use
# --------------------------------------------------------------------------- #
def test_add_client_flags_and_yes_skip_every_prompt():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=dict(EXISTING_CLIENTS)),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True) as mock_get_string,
        patch("time_tracker_clients.ci.get_float", autospec=True) as mock_get_float,
        patch("time_tracker_clients.ci.get_yes_no", autospec=True) as mock_get_yes_no,
    ):
        add_client(code="ACME", company="Acme Inc", contact="Jane Roe", rate_hr=150.0, yes=True)

    mock_get_string.assert_not_called()
    mock_get_float.assert_not_called()
    mock_get_yes_no.assert_not_called()

    saved = mock_write.call_args[0][1]
    assert saved["ACME"] == {"company": "Acme Inc", "contact": "Jane Roe", "rate_hr": 150.0}
    assert saved["TEST"] == EXISTING_CLIENTS["TEST"]  # existing clients are untouched


def test_add_client_writes_only_the_fields_that_are_set():
    """An optional field left out must not appear as an empty value."""
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
    ):
        add_client(code="ACME", company="Acme Inc", contact="Jane Roe", rate_hr=150.0, yes=True)

    record = mock_write.call_args[0][1]["ACME"]
    assert set(record) == {"company", "contact", "rate_hr"}
    # Billable is the default, so the flag is absent rather than written as false.
    assert "non_billable" not in record


def test_add_client_keeps_a_fractional_rate():
    """A rate is money: $17.50/hr has to survive the round trip."""
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
    ):
        add_client(code="ACME", company="Acme Inc", contact="Jane Roe", rate_hr=17.50, yes=True)

    assert mock_write.call_args[0][1]["ACME"]["rate_hr"] == 17.5


def test_add_client_writes_the_fields_in_schema_order():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
    ):
        add_client(code="ACME", rate_day=800.0, company="Acme Inc", addr1="1 Way",
                   contact="Jane Roe", rate_hr=150.0, phone="555", yes=True)

    record = mock_write.call_args[0][1]["ACME"]
    assert list(record) == ["company", "contact", "phone", "addr1", "rate_hr", "rate_day"]


def test_add_client_non_billable_writes_the_flag_and_asks_for_no_rate():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_float", autospec=True) as mock_get_float,
    ):
        add_client(code="PRO", company="Pro Bono Inc", contact="Pat", non_billable=True, yes=True)

    mock_get_float.assert_not_called()  # a client that is never invoiced has no rate to set
    assert mock_write.call_args[0][1]["PRO"]["non_billable"] is True


def test_add_client_lower_case_code_is_stored_upper_cased():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
    ):
        add_client(code=" acme ", company="Acme Inc", contact="Jane Roe", rate_hr=150.0, yes=True)

    assert "ACME" in mock_write.call_args[0][1]


def test_add_client_retainer_flags_answer_the_retainer_question():
    """Asking for a retainer is answer enough - the gate must not be asked as well."""
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_yes_no", autospec=True) as mock_get_yes_no,
    ):
        add_client(code="RET", company="Retainer Corp", contact="Rex", rate_hr=100.0,
                   retainer_hrs=20.0, retainer_rate=1500.0, yes=True)

    mock_get_yes_no.assert_not_called()
    record = mock_write.call_args[0][1]["RET"]
    assert record["retainer_hrs"] == 20.0
    assert record["retainer_rate"] == 1500.0


# --------------------------------------------------------------------------- #
# Interactive use
# --------------------------------------------------------------------------- #
def test_add_client_prompts_for_every_field():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True,
              side_effect=["ACME", "Acme Inc", "Jane Roe", "(555) 111-2222", "1 Way", "Town, ST 00000"]),
        patch("time_tracker_clients.ci.get_float", autospec=True, side_effect=[150.0, 1200.0]),
        # billable? -> yes, retainer? -> no, save? -> yes
        patch("time_tracker_clients.ci.get_yes_no", autospec=True, side_effect=["yes", "no", "yes"]),
    ):
        add_client()

    assert mock_write.call_args[0][1]["ACME"] == {
        "company": "Acme Inc",
        "contact": "Jane Roe",
        "phone": "(555) 111-2222",
        "addr1": "1 Way",
        "addr2": "Town, ST 00000",
        "rate_hr": 150.0,
        "rate_day": 1200.0,
    }


def test_add_client_code_prompt_rejects_an_existing_code_and_asks_again(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=dict(EXISTING_CLIENTS)),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True, side_effect=["TEST", "ACME", "Acme Inc", "Jane Roe", None, None, None]),
        patch("time_tracker_clients.ci.get_float", autospec=True, side_effect=[150.0, None]),
        patch("time_tracker_clients.ci.get_yes_no", autospec=True, side_effect=["yes", "no", "yes"]),
    ):
        add_client()

    assert "already exists" in capsys.readouterr().out
    assert "ACME" in mock_write.call_args[0][1]


def test_add_client_blank_optional_answers_are_not_written():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
        # cooked_input returns None for a blank answer to an optional prompt
        patch("time_tracker_clients.ci.get_string", autospec=True, side_effect=["ACME", "Acme Inc", "Jane Roe", None, None, None]),
        patch("time_tracker_clients.ci.get_float", autospec=True, side_effect=[150.0, None]),
        patch("time_tracker_clients.ci.get_yes_no", autospec=True, side_effect=["yes", "no", "yes"]),
    ):
        add_client()

    assert set(mock_write.call_args[0][1]["ACME"]) == {"company", "contact", "rate_hr"}


def test_add_client_shows_the_record_before_saving(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args"),
        patch("time_tracker_clients.ci.get_string", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_float", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_yes_no", autospec=True, return_value="yes"),
    ):
        add_client(code="ACME", company="Acme Inc", contact="Jane Roe", rate_hr=150.0)

    output = capsys.readouterr().out
    assert "New client ACME" in output
    assert "Acme Inc" in output
    assert "Rate/Hr" in output


# --------------------------------------------------------------------------- #
# Failure paths - none of them may write
# --------------------------------------------------------------------------- #
def test_add_client_rejects_an_existing_code(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=dict(EXISTING_CLIENTS)),
        patch("time_tracker_clients.write_json_args") as mock_write,
        pytest.raises(typer.Exit) as exc_info,
    ):
        add_client(code="TEST", company="X", contact="Y", rate_hr=1.0, yes=True)

    assert exc_info.value.exit_code == 1
    assert "already exists" in capsys.readouterr().out
    mock_write.assert_not_called()


def test_add_client_rejects_a_malformed_code(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
        pytest.raises(typer.Exit) as exc_info,
    ):
        add_client(code="A B!", company="X", contact="Y", rate_hr=1.0, yes=True)

    assert exc_info.value.exit_code == 1
    assert "invalid client code" in capsys.readouterr().out
    mock_write.assert_not_called()


def test_add_client_rejects_a_negative_rate(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
        pytest.raises(typer.Exit) as exc_info,
    ):
        add_client(code="ACME", company="X", contact="Y", rate_hr=-5.0, yes=True)

    assert exc_info.value.exit_code == 1
    assert "must not be negative" in capsys.readouterr().out
    mock_write.assert_not_called()


def test_add_client_refuses_a_clients_file_that_does_not_parse(capsys):
    """A file we cannot read is a file we must not rewrite."""
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", side_effect=json.JSONDecodeError("bad", "{", 0)),
        patch("time_tracker_clients.write_json_args") as mock_write,
        pytest.raises(typer.Exit) as exc_info,
    ):
        add_client(code="ACME", company="X", contact="Y", rate_hr=1.0, yes=True)

    assert exc_info.value.exit_code == 1
    assert "not valid JSON" in capsys.readouterr().out
    mock_write.assert_not_called()


def test_add_client_reports_an_unreadable_clients_file(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", side_effect=OSError("denied")),
        patch("time_tracker_clients.write_json_args") as mock_write,
        pytest.raises(typer.Exit) as exc_info,
    ):
        add_client(code="ACME", company="X", contact="Y", rate_hr=1.0, yes=True)

    assert exc_info.value.exit_code == 1
    assert "could not read" in capsys.readouterr().out
    mock_write.assert_not_called()


def test_add_client_confirmation_no_does_not_save(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_float", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_yes_no", autospec=True, return_value="no"),
        pytest.raises(typer.Exit) as exc_info,
    ):
        add_client(code="ACME", company="Acme Inc", contact="Jane Roe", rate_hr=150.0)

    assert exc_info.value.exit_code == 1
    assert "cancelled" in capsys.readouterr().out.lower()
    mock_write.assert_not_called()


def test_add_client_rejecting_the_save_offers_another_pass():
    """One wrong answer must not throw away the other nine."""
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
        # first pass, then the re-entry pass
        patch("time_tracker_clients.ci.get_string", autospec=True,
              side_effect=["ACME", "Acme Inc", "Jane Roe", None, None, None,
                           "Acme Incorporated", "Jane Roe", None, None, None]),
        patch("time_tracker_clients.ci.get_float", autospec=True, side_effect=[150.0, None, 175.0, None]),
        # billable, retainer, save? -> no, change? -> yes, billable, retainer, save? -> yes
        patch("time_tracker_clients.ci.get_yes_no", autospec=True,
              side_effect=["yes", "no", "no", "yes", "yes", "no", "yes"]),
    ):
        add_client()

    saved = mock_write.call_args[0][1]["ACME"]
    assert saved["company"] == "Acme Incorporated"
    assert saved["rate_hr"] == 175.0


def test_add_client_re_entry_offers_the_previous_answers_as_defaults():
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args"),
        # first pass prompts only for the optional fields the flags left out
        patch("time_tracker_clients.ci.get_string", autospec=True,
              side_effect=[None, None, None, "Acme Inc", "Jane Roe", None, None, None]) as mock_get_string,
        patch("time_tracker_clients.ci.get_float", autospec=True, side_effect=[None, 175.0, None]) as mock_get_float,
        # billable, retainer, save? -> no, change? -> yes, billable, retainer, save? -> yes
        patch("time_tracker_clients.ci.get_yes_no", autospec=True,
              side_effect=["yes", "no", "no", "yes", "yes", "no", "yes"]),
    ):
        add_client(code="ACME", company="Acme Inc", contact="Jane Roe", rate_hr=150.0)

    def last_default(mock, prompt_text):
        """The default offered the last time a prompt was shown."""
        calls = [c for c in mock.call_args_list if prompt_text in c.kwargs["prompt"]]
        return calls[-1].kwargs["default"]

    # The re-entry pass offers back what the first pass produced - including the values
    # that came from flags, which do not apply a second time.
    assert last_default(mock_get_string, "Company name") == "Acme Inc"
    assert last_default(mock_get_float, "Hourly rate") == 150.0


def test_add_client_declining_to_change_answers_cancels(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True, return_value=None),
        patch("time_tracker_clients.ci.get_float", autospec=True, return_value=None),
        # billable, retainer, save? -> no, change? -> no
        patch("time_tracker_clients.ci.get_yes_no", autospec=True, side_effect=["yes", "no", "no", "no"]),
        pytest.raises(typer.Exit) as exc_info,
    ):
        add_client(code="ACME", company="Acme Inc", contact="Jane Roe", rate_hr=150.0)

    assert exc_info.value.exit_code == 1
    assert "cancelled" in capsys.readouterr().out.lower()
    mock_write.assert_not_called()


def test_add_client_interrupt_does_not_save(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args") as mock_write,
        patch("time_tracker_clients.ci.get_string", autospec=True, side_effect=ci.GetInputInterrupt),
        pytest.raises(typer.Exit) as exc_info,
    ):
        add_client()

    assert exc_info.value.exit_code == 1
    assert "cancelled" in capsys.readouterr().out.lower()
    mock_write.assert_not_called()


def test_add_client_reports_a_failed_write(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
        patch("time_tracker_clients.write_json_args", side_effect=OSError("disk full")),
        pytest.raises(typer.Exit) as exc_info,
    ):
        add_client(code="ACME", company="Acme Inc", contact="Jane Roe", rate_hr=150.0, yes=True)

    assert exc_info.value.exit_code == 1
    assert "could not write" in capsys.readouterr().out
