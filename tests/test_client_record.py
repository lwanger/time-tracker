"""Tests for the client-record helpers in time_tracker_client_record."""

import logging

import pytest

import time_tracker_client_record
from conftest import CLIENT_HOURLY


# --------------------------------------------------------------------------- #
# Client-record helpers
# --------------------------------------------------------------------------- #
def test_has_retainer_needs_both_fields():
    assert time_tracker_client_record.has_retainer({"retainer_hrs": 20, "retainer_rate": 1500}) is True
    # Half an agreement is not one - it would otherwise be billed as if it were whole.
    assert time_tracker_client_record.has_retainer({"retainer_hrs": 20}) is False
    assert time_tracker_client_record.has_retainer({"retainer_rate": 1500}) is False
    assert time_tracker_client_record.has_retainer({}) is False


@pytest.mark.parametrize("code", ["ACME", "A", "RET-2", "CLIENT_1", "X9"])
def test_validate_client_code_accepts_usable_codes(code):
    assert time_tracker_client_record.validate_client_code(code, {}, must_be_new=True) is None


@pytest.mark.parametrize("code", ["", "-LEAD", "_LEAD", "A B", "ACME!", "acme"])
def test_validate_client_code_rejects_unusable_codes(code):
    assert time_tracker_client_record.validate_client_code(code, {}, must_be_new=True) is not None


def test_validate_client_code_rejects_a_duplicate_when_adding():
    error = time_tracker_client_record.validate_client_code("TEST", {"TEST": {}}, must_be_new=True)

    assert "already exists" in error


def test_validate_client_code_rejects_an_unknown_code_when_editing():
    error = time_tracker_client_record.validate_client_code("NOPE", {"TEST": {}}, must_be_new=False)

    assert "unknown client NOPE" in error
    assert "TEST" in error  # the known codes are named, so the fix is obvious


def test_validate_client_code_accepts_a_known_code_when_editing():
    assert time_tracker_client_record.validate_client_code("TEST", {"TEST": {}}, must_be_new=False) is None


def test_merge_client_record_orders_known_fields_and_keeps_extras_last():
    record = time_tracker_client_record.merge_client_record(
        {}, {"rate_hr": 150, "email": "a@b.test", "company": "Acme Inc", "contact": "Jane"},
    )

    assert list(record) == ["company", "contact", "rate_hr", "email"]


def test_merge_client_record_ignores_none_updates():
    """None means "not supplied", so it must not blank an existing value."""
    record = time_tracker_client_record.merge_client_record(
        {"company": "Acme Inc", "phone": "555"}, {"phone": None, "rate_hr": 150},
    )

    assert record == {"company": "Acme Inc", "phone": "555", "rate_hr": 150}


def test_merge_client_record_removes_named_fields():
    record = time_tracker_client_record.merge_client_record(
        {"company": "Acme Inc", "retainer_hrs": 20, "retainer_rate": 1500},
        {},
        removed=time_tracker_client_record.RETAINER_FIELDS,
    )

    assert record == {"company": "Acme Inc"}


def test_merge_client_record_preserves_an_unknown_field():
    """clients.json is hand-edited: a field Time Tracker does not know is still data."""
    record = time_tracker_client_record.merge_client_record(
        {"company": "Acme Inc", "email": "a@b.test"}, {"rate_hr": 150},
    )

    assert record["email"] == "a@b.test"


def test_merge_client_record_does_not_mutate_the_existing_record():
    existing = {"company": "Acme Inc"}

    time_tracker_client_record.merge_client_record(existing, {"rate_hr": 150}, removed=("company",))

    assert existing == {"company": "Acme Inc"}


# --------------------------------------------------------------------------- #
# Non-billable clients
# --------------------------------------------------------------------------- #
def test_is_non_billable_client_true_only_for_boolean_true():
    assert time_tracker_client_record.is_non_billable_client({"non_billable": True}) is True


def test_is_non_billable_client_false_flag_is_billable():
    assert time_tracker_client_record.is_non_billable_client({"non_billable": False}) is False


def test_is_non_billable_client_absent_key_is_billable():
    """Billable is the default: the key is opt-in, so existing records are unaffected."""
    assert time_tracker_client_record.is_non_billable_client({}) is False
    assert time_tracker_client_record.is_non_billable_client(CLIENT_HOURLY) is False


def test_is_non_billable_client_rejects_non_boolean_and_warns(caplog):
    """A quoted "false" is truthy in Python; clients.json is hand-edited and unchecked."""
    with caplog.at_level(logging.WARNING, logger="time_tracker_client_record"):
        result = time_tracker_client_record.is_non_billable_client(
            {"company": "FakeCo", "non_billable": "false"}
        )

    assert result is False
    assert "non_billable" in caplog.text
    assert "FakeCo" in caplog.text
