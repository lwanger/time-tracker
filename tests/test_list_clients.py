"""Tests for the list-clients command."""

from unittest.mock import patch

import time_tracker_clients
import time_tracker_config


CLIENTS_WITH_RETAINER = {
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
        "phone": "(555) 000-0001",
        "addr1": "100 Retainer Blvd",
        "addr2": "Chicago, IL 60601",
        "rate_hr": 100,
        "rate_day": 800,
        "retainer_hrs": 20,
        "retainer_rate": 1500,
    },
}

FAKE_GLOBAL_VARS = {
    "TT_CLIENTS_JSON_DIR": "./data",
    "TT_CLIENTS_FILE": "./data/clients.json",
}


def test_list_clients_all_fields(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=CLIENTS_WITH_RETAINER),
    ):
        time_tracker_clients.list_clients()

    captured = capsys.readouterr()
    output = captured.out

    assert "TEST" in output
    assert "RET" in output
    assert "FakeCo" in output
    assert "Retainer Corp" in output
    assert "Retained Hrs" in output
    assert "Retained Rate" in output
    # Clients without retainer fields should show empty string for those columns
    assert "20" in output
    assert "1500" in output


def test_list_clients_shows_the_non_billable_column(capsys):
    clients = {
        **CLIENTS_WITH_RETAINER,
        "PRO": {"company": "Pro Bono Inc", "contact": "Pro Contact", "non_billable": True},
    }
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients),
    ):
        time_tracker_clients.list_clients()

    output = capsys.readouterr().out
    assert "Non-billable" in output   # labelled, not auto-title-cased to "Non Billable"
    assert "Non Billable" not in output
    assert "Yes" in output            # the flag reads as a mark, not as "True"
    assert "True" not in output


def test_list_clients_hides_the_non_billable_column_when_no_client_uses_it(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=CLIENTS_WITH_RETAINER),
    ):
        time_tracker_clients.list_clients()

    assert "Non-billable" not in capsys.readouterr().out


def test_list_clients_renders_a_false_flag_as_blank(capsys):
    clients = {"TEST": {"company": "FakeCo", "non_billable": False}}
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients),
    ):
        time_tracker_clients.list_clients()

    output = capsys.readouterr().out
    assert "Non-billable" in output   # declared, so the column shows
    assert "False" not in output      # but a billable client is not marked


def test_list_clients_no_retainer_columns_hidden(capsys):
    clients_no_retainer = {
        "TEST": {
            "company": "FakeCo",
            "contact": "Fake Client",
            "phone": "(123) 456-8900",
            "addr1": "Fake addr1",
            "addr2": "Fake City, FS 00000",
            "rate_hr": 100,
            "rate_day": 800,
        },
    }

    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_no_retainer),
    ):
        time_tracker_clients.list_clients()

    captured = capsys.readouterr()
    output = captured.out

    assert "TEST" in output
    assert "FakeCo" in output
    assert "Retained Hrs" not in output
    assert "Retained Rate" not in output


def test_list_clients_shows_unknown_extra_field(capsys):
    clients_with_extra = {
        "TEST": {
            "company": "FakeCo",
            "contact": "Fake Client",
            "rate_hr": 100,
            "email": "fake@example.com",  # field not in the known label map
        },
    }

    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value=clients_with_extra),
    ):
        time_tracker_clients.list_clients()

    output = capsys.readouterr().out
    # Unknown field is title-cased into a header and its value is shown
    assert "Email" in output
    assert "fake@example.com" in output


def test_list_clients_empty(capsys):
    with (
        patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True),
        patch("time_tracker_clients.read_json_args", return_value={}),
    ):
        time_tracker_clients.list_clients()

    captured = capsys.readouterr()
    assert "No clients found" in captured.out
    assert "./data" in captured.out