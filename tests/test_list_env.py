"""Tests for the list-env command."""

from unittest.mock import patch

import time_tracker_config


FAKE_GLOBAL_VARS = {
    "TT_INV_SAVE_DIR": "/fake/invoices",
    "TT_LOG_SAVE_DIR": "/fake/time_logs",
    "TT_CLIENTS_JSON_DIR": "/fake/invoices",
    "TT_TIME_LOG_FILENAME": "fake_time_log.csv",
    "TT_TIME_LOG_FILE": "/fake/time_logs/fake_time_log.csv",
    "TT_INVOICES_LOG_FILENAME": "fake_invoices_log.csv",
    "TT_INVOICES_LOG_FILE": "/fake/time_logs/fake_invoices_log.csv",
    "TT_CLIENTS_FILE": "/fake/invoices/clients.json",
    "TT_INVOICES_FILE": "/fake/invoices/invoices.json",
    "TT_MAX_MINUTES_CONFIRMATION": 180,
}


def test_list_env_shows_all_settings(capsys):
    with patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True):
        time_tracker_config.list_env()

    output = capsys.readouterr().out

    # Variable column (env var names)
    assert "TT_INV_SAVE_DIR" in output
    assert "TT_LOG_SAVE_DIR" in output
    assert "TT_CLIENTS_JSON_DIR" in output
    assert "TT_TIME_LOG_FILENAME" in output
    assert "TT_TIME_LOG_FILE" in output
    assert "TT_INVOICES_LOG_FILENAME" in output
    assert "TT_INVOICES_LOG_FILE" in output
    assert "TT_CLIENTS_FILE" in output
    assert "TT_INVOICES_FILE" in output
    assert "TT_MAX_MINUTES_CONFIRMATION" in output

    # Setting column (friendly labels)
    assert "Invoice Save Directory" in output
    assert "Time Log Save Directory" in output
    assert "Clients JSON Directory" in output
    assert "Time Log Filename" in output
    assert "Time Log File Path" in output
    assert "Invoice Log Filename" in output
    assert "Invoice Log File Path" in output
    assert "Clients File Path" in output
    assert "Invoices File Path" in output
    assert "Warn if added time exceeds" in output


def test_list_env_shows_values(capsys):
    with patch.dict(time_tracker_config.global_vars, FAKE_GLOBAL_VARS, clear=True):
        time_tracker_config.list_env()

    output = capsys.readouterr().out

    assert "/fake/invoices" in output
    assert "/fake/time_logs" in output
    assert "fake_time_log.csv" in output
    assert "fake_invoices_log.csv" in output
    assert "clients.json" in output
    assert "invoices.json" in output
    assert "180" in output


def test_list_env_missing_key_shows_empty(capsys):
    sparse_vars: dict = {}
    with patch.dict(time_tracker_config.global_vars, sparse_vars, clear=True):
        time_tracker_config.list_env()

    output = capsys.readouterr().out
    # Table headers should still appear
    assert "Variable" in output
    assert "Setting" in output
    assert "Value" in output