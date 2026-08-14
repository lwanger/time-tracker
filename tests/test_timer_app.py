"""Tests for the pure helpers in the standalone timer app.

The tkinter view (``TimerApp``) is verified manually; these tests cover the
formatting / computation / CLI-resolution logic the view delegates to.
"""

import datetime

import pytest


# tkinter is stdlib but not always installed: Debian and Ubuntu split it into
# python3-tk, Homebrew into python-tk@X.Y, and a Python built without Tk has no
# _tkinter at all. Importing timer_app therefore fails outright on some perfectly
# good Linux and macOS installs, which is a fact about the platform rather than a
# breakage - so skip the module instead of erroring during collection. Only the
# GUI is affected; the time-tracker CLI never imports timer_app.
pytest.importorskip("tkinter", reason="tkinter is not installed for this interpreter")

import timer_app


# --------------------------------------------------------------------------- #
# format_elapsed
# --------------------------------------------------------------------------- #
def test_format_elapsed_zero():
    assert timer_app.format_elapsed(0) == "00:00"


def test_format_elapsed_under_a_minute_shows_zero_minutes():
    assert timer_app.format_elapsed(59) == "00:00"


def test_format_elapsed_one_minute():
    assert timer_app.format_elapsed(60) == "00:01"


def test_format_elapsed_hours_and_minutes():
    assert timer_app.format_elapsed(3660) == "01:01"


def test_format_elapsed_negative_clamps_to_zero():
    assert timer_app.format_elapsed(-30) == "00:00"


# --------------------------------------------------------------------------- #
# compute_elapsed_minutes
# --------------------------------------------------------------------------- #
def test_compute_elapsed_minutes_whole():
    start = datetime.datetime(2026, 5, 1, 9, 0)
    end = datetime.datetime(2026, 5, 1, 10, 30)

    assert timer_app.compute_elapsed_minutes(start, end) == 90


def test_compute_elapsed_minutes_rounds_to_nearest():
    start = datetime.datetime(2026, 5, 1, 9, 0, 0)
    end = datetime.datetime(2026, 5, 1, 9, 1, 40)  # 100 seconds -> 1.67 min

    assert timer_app.compute_elapsed_minutes(start, end) == 2


def test_compute_elapsed_minutes_negative_clamps_to_zero():
    start = datetime.datetime(2026, 5, 1, 10, 0)
    end = datetime.datetime(2026, 5, 1, 9, 0)

    assert timer_app.compute_elapsed_minutes(start, end) == 0


# --------------------------------------------------------------------------- #
# running_title
# --------------------------------------------------------------------------- #
def test_running_title_when_running():
    assert timer_app.running_title(True) == "Time Tracker Timer — running"


def test_running_title_when_stopped():
    assert timer_app.running_title(False) == "Time Tracker Timer"


# --------------------------------------------------------------------------- #
# build_save_confirmation
# --------------------------------------------------------------------------- #
def test_build_save_confirmation_normal_defaults_to_yes():
    message, default_yes = timer_app.build_save_confirmation(30, "Bug fixes", "00:30")

    assert default_yes is True
    assert "Total time: 00:30 (30 min)." in message
    assert "Add this entry to the time log?" in message
    assert "under a minute" not in message
    assert "no notes" not in message


def test_build_save_confirmation_short_entry_warns_but_defaults_to_yes():
    message, default_yes = timer_app.build_save_confirmation(0, "Quick call", "00:00")

    assert default_yes is True  # has notes, so adding stays the default
    assert "under a minute" in message


def test_build_save_confirmation_no_notes_defaults_to_no():
    message, default_yes = timer_app.build_save_confirmation(45, "", "00:45")

    assert default_yes is False
    assert "no notes" in message


def test_build_save_confirmation_whitespace_notes_treated_as_empty():
    _message, default_yes = timer_app.build_save_confirmation(45, "   ", "00:45")

    assert default_yes is False


def test_build_save_confirmation_short_and_no_notes_lists_both():
    message, default_yes = timer_app.build_save_confirmation(0, "", "00:00")

    assert default_yes is False
    assert "under a minute" in message
    assert "no notes" in message


def test_build_save_confirmation_defaults_to_unbilled_without_a_status():
    """The status argument is optional, so the three-argument callers stay valid."""
    message, _default_yes = timer_app.build_save_confirmation(30, "Bug fixes", "00:30")

    assert "non-billable" not in message


def test_build_save_confirmation_names_a_non_billable_entry():
    message, _default_yes = timer_app.build_save_confirmation(
        30, "Board meeting", "00:30", timer_app.STATUS_NON_BILLABLE
    )

    assert "This entry will be logged as non-billable." in message


# --------------------------------------------------------------------------- #
# resolve_prefill_client
# --------------------------------------------------------------------------- #
CLIENTS = {"IO": {"company": "IO Co"}, "ACME": {"company": "Acme"}}


def test_resolve_prefill_client_none():
    assert timer_app.resolve_prefill_client(CLIENTS, None) is None


def test_resolve_prefill_client_blank():
    assert timer_app.resolve_prefill_client(CLIENTS, "") is None


def test_resolve_prefill_client_case_insensitive_match():
    assert timer_app.resolve_prefill_client(CLIENTS, "io") == "IO"


def test_resolve_prefill_client_unknown_returns_none():
    assert timer_app.resolve_prefill_client(CLIENTS, "NOPE") is None


# --------------------------------------------------------------------------- #
# format_client_choice / build_client_choices / choice_for_code
# --------------------------------------------------------------------------- #
# Company names and codes sort in opposite orders, so a test that passes here
# cannot be passing by accident on a code sort.
CROSSED_CLIENTS = {
    "ZULU": {"company": "Acme"},
    "ACME": {"company": "Zulu"},
    "MID": {"company": "middling"},  # lower case: the sort must be case-insensitive
}


def test_format_client_choice_puts_the_code_after_the_company():
    assert timer_app.format_client_choice("TEST", {"company": "FakeCo"}) == "FakeCo (TEST)"


def test_format_client_choice_without_a_company_falls_back_to_the_code():
    """clients.json is not schema-validated, so a record with no company must still show."""
    assert timer_app.format_client_choice("TEST", {"rate_hr": 100}) == "TEST"


def test_format_client_choice_with_a_blank_company_falls_back_to_the_code():
    assert timer_app.format_client_choice("TEST", {"company": "   "}) == "TEST"


def test_build_client_choices_maps_each_label_to_its_code():
    choices = timer_app.build_client_choices(CLIENTS)

    assert choices == {"Acme (ACME)": "ACME", "IO Co (IO)": "IO"}


def test_build_client_choices_sorts_by_company_not_by_code():
    labels = list(timer_app.build_client_choices(CROSSED_CLIENTS))

    assert labels == ["Acme (ZULU)", "middling (MID)", "Zulu (ACME)"]


def test_build_client_choices_sorts_a_company_less_record_by_its_code():
    clients = {"AAA": {"company": "Zebra"}, "BBB": {"rate_hr": 100}}

    assert list(timer_app.build_client_choices(clients)) == ["BBB", "Zebra (AAA)"]


def test_build_client_choices_with_no_clients_is_empty():
    assert timer_app.build_client_choices({}) == {}


def test_choice_for_code_returns_the_label():
    choices = timer_app.build_client_choices(CLIENTS)

    assert timer_app.choice_for_code(choices, "IO") == "IO Co (IO)"


def test_choice_for_code_none_selects_nothing():
    choices = timer_app.build_client_choices(CLIENTS)

    assert timer_app.choice_for_code(choices, None) == ""


def test_choice_for_code_unknown_selects_nothing():
    choices = timer_app.build_client_choices(CLIENTS)

    assert timer_app.choice_for_code(choices, "NOPE") == ""


# --------------------------------------------------------------------------- #
# client_combo_width
# --------------------------------------------------------------------------- #
def test_client_combo_width_short_labels_use_the_minimum():
    choices = timer_app.build_client_choices({"IO": {"company": "IO Co"}})

    assert timer_app.client_combo_width(choices) == timer_app.CLIENT_COMBO_MIN_WIDTH


def test_client_combo_width_no_clients_uses_the_minimum():
    assert timer_app.client_combo_width({}) == timer_app.CLIENT_COMBO_MIN_WIDTH


def test_client_combo_width_grows_to_fit_the_longest_label():
    label = "A" * (timer_app.CLIENT_COMBO_MIN_WIDTH + 5)
    choices = timer_app.build_client_choices({"IO": {"company": "IO Co"}, "X": {"company": label}})

    assert timer_app.client_combo_width(choices) == len(f"{label} (X)")


def test_client_combo_width_clamps_a_very_long_label():
    choices = timer_app.build_client_choices({"X": {"company": "A" * 200}})

    assert timer_app.client_combo_width(choices) == timer_app.CLIENT_COMBO_MAX_WIDTH
