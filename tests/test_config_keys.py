"""Contract tests: every config key the code reads must be one load_config() produces.

The TT_ prefix refactor renamed the keys the config loader returns without
renaming the call sites that read them, so every command raised ``KeyError`` at
runtime while the suite stayed green - each test patched ``global_vars`` with its
own hand-written fixture, so no test ever used a real loader result. These tests
compare the source's subscripts against ``load_config()``'s actual output instead
of trusting fixtures.
"""

import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import time_tracker_config
import time_tracker_init


# Every module that reads a resolved setting. The commands were split out of
# time_tracker.py by area, so scanning that file alone would now check almost nothing.
SOURCE_FILES = (
    "time_tracker_clients.py",
    "time_tracker_init.py",
    "time_tracker_invoices.py",
    "time_tracker_time.py",
    "timer_app.py",
)

# global_vars['KEY'] / config["KEY"] / self.config['KEY'] / global_vars.get("KEY")
# The .get() form matters since the command split: init reads its settings that way.
SUBSCRIPT_RE = re.compile(r"\b(?:self\.)?(?:global_vars|config)(?:\[|\.get\()(['\"])([A-Za-z_]+)\1")

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def config_keys(tmp_path_factory) -> set[str]:
    """The keys ``load_config()`` actually returns, with every layer empty.

    Pointing both file layers at paths that do not exist isolates this from the
    developer's own ``.env`` files; ``load_config`` is pure, so no patching of
    ``os.environ`` is needed either.
    """
    missing = tmp_path_factory.mktemp("no-config") / ".env"
    return set(time_tracker_config.load_config(environ={}, cwd_env_file=missing, user_env_file=missing).values)


def _referenced_keys(filename: str) -> set[str]:
    source = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
    return {match.group(2) for match in SUBSCRIPT_RE.finditer(source)}


@pytest.mark.parametrize("filename", SOURCE_FILES)
def test_every_referenced_config_key_is_produced_by_init(filename: str, config_keys: set[str]) -> None:
    referenced = _referenced_keys(filename)
    assert referenced, f"no config subscripts found in {filename} - has the access pattern changed?"

    missing = referenced - config_keys
    assert not missing, (
        f"{filename} reads config keys that load_config() does not return: {sorted(missing)}. "
        f"load_config() returns: {sorted(config_keys)}"
    )


def test_all_config_keys_are_tt_prefixed(config_keys: set[str]) -> None:
    unprefixed = {key for key in config_keys if not key.startswith("TT_")}
    assert not unprefixed, f"load_config() returned unprefixed keys: {sorted(unprefixed)}"


def _settable_keys(config_keys: set[str]) -> list[str]:
    """Config keys a user can actually set, i.e. excluding the derived ones."""
    return sorted(config_keys - set(time_tracker_config.DERIVED_SETTINGS))


def _plausible_custom_value(key: str, tmp_path: Path) -> str:
    """A customized value of the right shape for the given setting."""
    if key == "TT_MAX_MINUTES_CONFIRMATION":
        return "77"
    if key.endswith("_FILENAME"):
        return "customized.csv"
    if key.endswith("_DIR"):
        return str(tmp_path / "customized_dir")
    return str(tmp_path / "customized_dir" / "customized_file.xlsx")


def _init_inputs(tmp_path: Path) -> tuple:
    """The directories and files `init` would decide, for a plain fresh setup."""
    data = tmp_path / "data"
    paths = time_tracker_init.InitPaths(
        data_dir=data, log_dir=data / "logs", clients_dir=data, invoices_dir=data,
    )
    files = time_tracker_init.InitFiles(
        clients_file=data / "clients.json",
        invoices_file=data / "invoices.json",
        template_file=data / "Invoice - blank.xlsx",
    )
    return paths, files


@pytest.mark.skipif(
    sys.platform != "win32",
    reason=(
        "Separator tolerance is a Windows-only question. On POSIX a backslash is an "
        "ordinary filename character, so these name two different files and comparing "
        "them unequal is the correct answer rather than a bug to work around."
    ),
)
def test_same_setting_tolerates_path_spelling() -> None:
    """os.path.join yields a backslash where a hand-written .env has a slash."""
    assert time_tracker_init._same_setting("C:/data\\clients.json", "C:/data/clients.json")


def test_same_setting_rejects_a_genuinely_different_value() -> None:
    """The other half of the contract, and true on every platform."""
    assert not time_tracker_init._same_setting("180", "240")


def test_same_setting_survives_a_value_that_is_not_a_path() -> None:
    """Must compare unequal rather than raise, whatever a .env happens to contain."""
    assert not time_tracker_init._same_setting("\0not-a-path", "C:/data/clients.json")
    assert not time_tracker_init._same_setting("", "C:/data/clients.json")


def test_owned_settings_are_all_settable(config_keys: set[str]) -> None:
    """A typo in INIT_OWNED_SETTINGS would silently exempt nothing - or everything."""
    settable = set(_settable_keys(config_keys))
    unknown = set(time_tracker_init.INIT_OWNED_SETTINGS) - settable

    assert not unknown, f"INIT_OWNED_SETTINGS names settings that do not exist: {sorted(unknown)}"


def test_init_writes_every_setting_it_owns(config_keys: set[str], tmp_path) -> None:
    """The settings init decides must always be written, not left to defaults."""
    paths, files = _init_inputs(tmp_path)
    with patch.dict(time_tracker_config.global_vars, {}, clear=True):
        written = time_tracker_init._settings_to_write(paths, files)

    missing = set(time_tracker_init.INIT_OWNED_SETTINGS) - set(written)
    assert not missing, f"init claims to own these but does not write them: {sorted(missing)}"


def test_init_preserves_every_setting_it_does_not_own(config_keys: set[str], tmp_path) -> None:
    """A customized value must survive `init` for every setting it does not decide.

    init used to write a hand-maintained subset, so any setting nobody remembered
    silently reverted to a default pointing elsewhere - a renamed time log hid its
    entries, a relocated counter file reset the invoice number. This asserts the
    general mechanism covers every remaining settable key, including ones added
    later, so the failure cannot come back by omission.
    """
    paths, files = _init_inputs(tmp_path)
    not_owned = [key for key in _settable_keys(config_keys) if key not in time_tracker_init.INIT_OWNED_SETTINGS]
    assert not_owned, "no unowned settings found - has the ownership split changed?"

    dropped = []
    for key in not_owned:
        custom = _plausible_custom_value(key, tmp_path)
        with patch.dict(time_tracker_config.global_vars, {key: custom}, clear=True):
            written = time_tracker_init._settings_to_write(paths, files)

        if key not in written or not time_tracker_init._same_setting(written[key], custom):
            dropped.append(f"{key} (set to {custom!r}, wrote {written.get(key)!r})")

    assert not dropped, "init would silently revert these customized settings:\n  " + "\n  ".join(dropped)


def test_init_writes_no_backslashes_for_any_setting(config_keys: set[str], tmp_path) -> None:
    """dotenv reads a backslash in a quoted value as an escape sequence."""
    paths, files = _init_inputs(tmp_path)
    customized = {key: _plausible_custom_value(key, tmp_path) for key in _settable_keys(config_keys)}

    with patch.dict(time_tracker_config.global_vars, customized, clear=True):
        written = time_tracker_init._settings_to_write(paths, files)

    offenders = {key: value for key, value in written.items() if "\\" in value}
    assert not offenders, f"backslashes would corrupt on read: {offenders}"


def test_list_env_labels_cover_every_config_key(config_keys: set[str], capsys) -> None:
    """`list-env` must show every setting, or a value silently becomes invisible."""
    with patch.dict(time_tracker_config.global_vars, dict.fromkeys(config_keys, "x"), clear=True):
        time_tracker_config.list_env()

    output = capsys.readouterr().out
    unlisted = {key for key in config_keys if key not in output}
    assert not unlisted, f"list-env does not display: {sorted(unlisted)}"
