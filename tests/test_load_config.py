"""Tests for the four-layer configuration waterfall.

``load_config()`` is a pure function taking each layer explicitly, so these tests
pass isolated tmp_path files and an explicit environ mapping - no ``os.environ``
patching, and no risk of picking up the developer's own ``.env``.
See docs/adr/0004-config-resolution-waterfall.md.
"""

import os
from pathlib import Path

import pytest

import time_tracker_config


def _write_env(path: Path, **settings: str) -> Path:
    path.write_text("\n".join(f'{key}="{value}"' for key, value in settings.items()), encoding="utf-8")
    return path


@pytest.fixture
def missing_env(tmp_path) -> Path:
    """A path with no file, standing in for an absent layer."""
    return tmp_path / "absent" / ".env"


# --------------------------------------------------------------------------- #
# defaults
# --------------------------------------------------------------------------- #
def test_defaults_when_every_layer_is_empty(missing_env):
    config = time_tracker_config.load_config(environ={}, cwd_env_file=missing_env, user_env_file=missing_env)

    assert config.values["TT_INV_SAVE_DIR"] == "./invoices"
    assert config.values["TT_LOG_SAVE_DIR"] == "./time_logs"
    assert config.values["TT_TIME_LOG_FILENAME"] == "time_log.csv"
    assert config.values["TT_INVOICES_LOG_FILENAME"] == "invoices_log.csv"
    assert config.values["TT_MAX_MINUTES_CONFIRMATION"] == 240
    # Dependent defaults: these follow TT_INV_SAVE_DIR.
    assert config.values["TT_CLIENTS_JSON_DIR"] == "./invoices"
    assert config.values["TT_INVOICES_JSON_DIR"] == "./invoices"
    assert config.values["TT_CLIENTS_FILE"] == os.path.join("./invoices", "clients.json")
    assert config.values["TT_INVOICES_FILE"] == os.path.join("./invoices", "invoices.json")
    # Derived: composed from a directory plus a filename.
    assert config.values["TT_TIME_LOG_FILE"] == os.path.join("./time_logs", "time_log.csv")
    assert config.values["TT_INVOICES_LOG_FILE"] == os.path.join("./time_logs", "invoices_log.csv")


def test_defaults_are_reported_as_such(missing_env):
    config = time_tracker_config.load_config(environ={}, cwd_env_file=missing_env, user_env_file=missing_env)

    assert config.sources["TT_INV_SAVE_DIR"] == time_tracker_config.SOURCE_DEFAULT
    assert config.sources["TT_TIME_LOG_FILE"] == time_tracker_config.SOURCE_DERIVED


def test_load_config_does_not_mutate_the_environment(missing_env):
    """The old load_dotenv flattened every layer into os.environ; this must not."""
    before = dict(os.environ)
    time_tracker_config.load_config(
        environ={"TT_INV_SAVE_DIR": "/from/env"}, cwd_env_file=missing_env, user_env_file=missing_env,
    )

    assert dict(os.environ) == before


# --------------------------------------------------------------------------- #
# precedence
# --------------------------------------------------------------------------- #
def test_environment_beats_both_files(tmp_path):
    cwd_env = _write_env(tmp_path / "cwd.env", TT_INV_SAVE_DIR="/from/cwd")
    user_env = _write_env(tmp_path / "user.env", TT_INV_SAVE_DIR="/from/user")

    config = time_tracker_config.load_config(
        environ={"TT_INV_SAVE_DIR": "/from/env"}, cwd_env_file=cwd_env, user_env_file=user_env,
    )

    assert config.values["TT_INV_SAVE_DIR"] == "/from/env"
    assert config.sources["TT_INV_SAVE_DIR"] == time_tracker_config.SOURCE_ENVIRONMENT


def test_cwd_file_beats_user_file(tmp_path):
    cwd_env = _write_env(tmp_path / "cwd.env", TT_INV_SAVE_DIR="/from/cwd")
    user_env = _write_env(tmp_path / "user.env", TT_INV_SAVE_DIR="/from/user")

    config = time_tracker_config.load_config(environ={}, cwd_env_file=cwd_env, user_env_file=user_env)

    assert config.values["TT_INV_SAVE_DIR"] == "/from/cwd"
    assert config.sources["TT_INV_SAVE_DIR"] == str(cwd_env)


def test_user_file_used_when_no_cwd_file(tmp_path, missing_env):
    user_env = _write_env(tmp_path / "user.env", TT_INV_SAVE_DIR="/from/user")

    config = time_tracker_config.load_config(environ={}, cwd_env_file=missing_env, user_env_file=user_env)

    assert config.values["TT_INV_SAVE_DIR"] == "/from/user"
    assert config.sources["TT_INV_SAVE_DIR"] == str(user_env)


def test_layers_merge_per_key_not_per_file(tmp_path):
    """The point of the waterfall: a CWD file overriding one key keeps the rest."""
    cwd_env = _write_env(tmp_path / "cwd.env", TT_INV_SAVE_DIR="/from/cwd")
    user_env = _write_env(
        tmp_path / "user.env", TT_INV_SAVE_DIR="/from/user", TT_LOG_SAVE_DIR="/user/logs",
    )

    config = time_tracker_config.load_config(environ={}, cwd_env_file=cwd_env, user_env_file=user_env)

    assert config.values["TT_INV_SAVE_DIR"] == "/from/cwd"
    assert config.values["TT_LOG_SAVE_DIR"] == "/user/logs"  # not blanked by the CWD file
    assert config.sources["TT_LOG_SAVE_DIR"] == str(user_env)


def test_empty_value_falls_through_to_the_next_layer(tmp_path):
    """A stray `TT_FOO=` line should not blank a configured path."""
    cwd_env = _write_env(tmp_path / "cwd.env", TT_INV_SAVE_DIR="")
    user_env = _write_env(tmp_path / "user.env", TT_INV_SAVE_DIR="/from/user")

    config = time_tracker_config.load_config(environ={}, cwd_env_file=cwd_env, user_env_file=user_env)

    assert config.values["TT_INV_SAVE_DIR"] == "/from/user"


def test_dependent_defaults_follow_an_overridden_directory(tmp_path, missing_env):
    user_env = _write_env(tmp_path / "user.env", TT_INV_SAVE_DIR="/data")

    config = time_tracker_config.load_config(environ={}, cwd_env_file=missing_env, user_env_file=user_env)

    assert config.values["TT_CLIENTS_JSON_DIR"] == "/data"
    assert config.values["TT_CLIENTS_FILE"] == os.path.join("/data", "clients.json")
    assert config.values["TT_TEMPLATE_FILE"] == os.path.join("/data", "Invoice - blank.xlsx")


def test_paths_with_spaces_survive_a_quoted_value(tmp_path, missing_env):
    """Template filenames contain spaces; dotenv must hand them back intact."""
    user_env = _write_env(tmp_path / "user.env", TT_TEMPLATE_FILE="/data/My Invoice - blank.xlsx")

    config = time_tracker_config.load_config(environ={}, cwd_env_file=missing_env, user_env_file=user_env)

    assert config.values["TT_TEMPLATE_FILE"] == "/data/My Invoice - blank.xlsx"


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def test_non_numeric_max_minutes_raises_config_error(tmp_path, missing_env):
    user_env = _write_env(tmp_path / "user.env", TT_MAX_MINUTES_CONFIRMATION="soon")

    with pytest.raises(time_tracker_config.ConfigError) as exc_info:
        time_tracker_config.load_config(environ={}, cwd_env_file=missing_env, user_env_file=user_env)

    message = str(exc_info.value)
    assert "TT_MAX_MINUTES_CONFIRMATION" in message
    assert "soon" in message
    assert str(user_env) in message  # names the file to fix


def test_max_minutes_from_a_file_is_an_int(tmp_path, missing_env):
    user_env = _write_env(tmp_path / "user.env", TT_MAX_MINUTES_CONFIRMATION="300")

    config = time_tracker_config.load_config(environ={}, cwd_env_file=missing_env, user_env_file=user_env)

    assert config.values["TT_MAX_MINUTES_CONFIRMATION"] == 300


# --------------------------------------------------------------------------- #
# derived settings
# --------------------------------------------------------------------------- #
def test_setting_a_derived_key_warns_instead_of_being_silently_ignored(tmp_path, missing_env):
    """Ignoring TT_TIME_LOG_FILE looks like the tool reading the wrong file."""
    user_env = _write_env(tmp_path / "user.env", TT_TIME_LOG_FILE="D:/my/custom/log.csv")

    config = time_tracker_config.load_config(environ={}, cwd_env_file=missing_env, user_env_file=user_env)

    assert config.values["TT_TIME_LOG_FILE"] != "D:/my/custom/log.csv"  # still derived
    assert len(config.warnings) == 1
    warning = config.warnings[0]
    assert "TT_TIME_LOG_FILE" in warning
    assert str(user_env) in warning  # names the offending layer
    assert "TT_TIME_LOG_FILENAME" in warning  # names what to set instead


def test_no_warnings_when_no_derived_key_is_set(tmp_path, missing_env):
    user_env = _write_env(tmp_path / "user.env", TT_LOG_SAVE_DIR="/logs")

    assert time_tracker_config.load_config(environ={}, cwd_env_file=missing_env, user_env_file=user_env).warnings == []


def test_derived_key_in_the_environment_also_warns(missing_env):
    config = time_tracker_config.load_config(
        environ={"TT_INVOICES_LOG_FILE": "/somewhere/log.csv"},
        cwd_env_file=missing_env,
        user_env_file=missing_env,
    )

    assert len(config.warnings) == 1
    assert time_tracker_config.SOURCE_ENVIRONMENT in config.warnings[0]


# --------------------------------------------------------------------------- #
# default layer locations
# --------------------------------------------------------------------------- #
def test_no_config_file_sentinel_omits_a_layer(tmp_path, monkeypatch):
    """Lets init ask what the defaults alone produce, ignoring real files."""
    _write_env(tmp_path / ".env", TT_INV_SAVE_DIR="/from/cwd")
    monkeypatch.chdir(tmp_path)

    config = time_tracker_config.load_config(
        environ={}, cwd_env_file=time_tracker_config.NO_CONFIG_FILE, user_env_file=time_tracker_config.NO_CONFIG_FILE,
    )

    assert config.values["TT_INV_SAVE_DIR"] == "./invoices"
    assert config.sources["TT_INV_SAVE_DIR"] == time_tracker_config.SOURCE_DEFAULT



def test_cwd_layer_defaults_to_the_current_directory(tmp_path, monkeypatch, missing_env):
    _write_env(tmp_path / ".env", TT_INV_SAVE_DIR="/from/cwd")
    monkeypatch.chdir(tmp_path)

    config = time_tracker_config.load_config(environ={}, user_env_file=missing_env)

    assert config.values["TT_INV_SAVE_DIR"] == "/from/cwd"


def test_user_config_file_lives_under_the_home_directory():
    """It must not be a bare ~/.env, which every dotenv-using project would read."""
    assert time_tracker_config.USER_CONFIG_FILE == Path.home() / ".time-tracker" / ".env"
