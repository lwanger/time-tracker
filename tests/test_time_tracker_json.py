"""Tests for the JSON data-file helpers in time_tracker_json."""

import json

import time_tracker_json


# --------------------------------------------------------------------------- #
# JSON helpers
# --------------------------------------------------------------------------- #
def test_read_json_args_reads_existing_file(tmp_path):
    target = tmp_path / "invoices.json"
    payload = {"next_invoice": 105, "template": {"indent": "    "}}
    target.write_text(json.dumps(payload), encoding="utf-8")

    result = time_tracker_json.read_json_args(str(target))

    assert result == payload


def test_read_json_args_missing_file_returns_empty(tmp_path):
    missing = tmp_path / "does_not_exist.json"

    assert time_tracker_json.read_json_args(str(missing)) == {}


def test_write_json_args_round_trips(tmp_path):
    target = tmp_path / "invoices.json"
    payload = {"next_invoice": 200, "name": "ACME"}

    time_tracker_json.write_json_args(str(target), payload)

    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_write_json_args_is_indented_and_newline_terminated(tmp_path):
    """clients.json is hand-edited and diff-reviewed, so it is not written as one line."""
    target = tmp_path / "clients.json"

    time_tracker_json.write_json_args(str(target), {"TEST": {"company": "FakeCo"}})

    text = target.read_text(encoding="utf-8")
    assert text.startswith('{\n  "TEST"')
    assert text.endswith("\n")
