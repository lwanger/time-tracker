"""Configuration: the four-layer settings waterfall and the resolved values.

See docs/adr/0004-config-resolution-waterfall.md. ``global_vars`` and
``config_sources`` live here because every command reads them; ``main()`` fills them
in once from :func:`load_config`, and the command modules share the same two dicts.

Leonard Wanger, 2026
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from prettytable import PrettyTable

import time_tracker_templates
from time_tracker_cli import app


# --------------------------------------------------------------------------- #
# Configuration (see docs/adr/0004-config-resolution-waterfall.md)
# --------------------------------------------------------------------------- #
# The per-user config lives in its own directory rather than a bare ~/.env, which
# any dotenv-using project below the home directory would otherwise pick up.
USER_CONFIG_DIR = Path.home() / ".time-tracker"
USER_CONFIG_FILE = USER_CONFIG_DIR / ".env"
CWD_CONFIG_FILENAME = ".env"

# Source labels for the list-env "Source" column. Real paths are shown verbatim,
# so these are bracketed/lower-cased to stay distinguishable from a filename.
SOURCE_ENVIRONMENT = "environment"
SOURCE_DEFAULT = "(default)"
SOURCE_DERIVED = "(derived)"

CLIENTS_FILENAME = "clients.json"
INVOICES_FILENAME = "invoices.json"

DEFAULT_INV_SAVE_DIR = "./invoices"
DEFAULT_LOG_SAVE_DIR = "./time_logs"
DEFAULT_TIME_LOG_FILENAME = "time_log.csv"
DEFAULT_INVOICES_LOG_FILENAME = "invoices_log.csv"
DEFAULT_MAX_MINUTES_CONFIRMATION = "240"

# Settings composed from other settings rather than read from a layer. Setting one
# directly has no effect, so `load_config` warns and names what to set instead.
DERIVED_SETTINGS: dict[str, str] = {
    "TT_TIME_LOG_FILE": "TT_LOG_SAVE_DIR and TT_TIME_LOG_FILENAME",
    "TT_INVOICES_LOG_FILE": "TT_LOG_SAVE_DIR and TT_INVOICES_LOG_FILENAME",
}

# Passed as a layer path to mean "this layer contributes nothing", as distinct from
# None, which means "use the default location". Lets `init` ask what the defaults
# alone would produce without reading any file.
NO_CONFIG_FILE = ""

class ConfigError(Exception):
    """Configuration holds a value that cannot be used."""


@dataclass(frozen=True)
class Config:
    """Resolved configuration and the provenance of each value.

    Attributes:
        values: Setting name to resolved value, as the commands consume it.
        sources: Setting name to the layer that supplied it - a file path,
            ``environment``, ``(default)`` or ``(derived)``.
        warnings: Problems worth reporting that do not prevent resolution, such
            as a layer setting a derived setting that will be ignored.
    """

    values: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


global_vars: dict[str, Any] = {}  # dictionary containing global variables (mainly environment variables from .env)
config_sources: dict[str, str] = {}  # where each global_vars value came from, for list-env



def _config_layers(
    environ: Mapping[str, str] | None,
    cwd_env_file: Path | str | None,
    user_env_file: Path | str | None,
) -> list[tuple[Mapping[str, str | None], str]]:
    """Build the ordered configuration layers, highest precedence first.

    Args:
        environ: Environment mapping to read; ``None`` uses ``os.environ``.
        cwd_env_file: Current-directory ``.env``; ``None`` uses ``./.env``,
            ``NO_CONFIG_FILE`` omits the layer entirely.
        user_env_file: Per-user ``.env``; ``None`` uses ``~/.time-tracker/.env``,
            ``NO_CONFIG_FILE`` omits the layer entirely.

    Returns:
        ``(mapping, source-label)`` pairs to be searched in order.
    """
    environ = os.environ if environ is None else environ
    layers: list[tuple[Mapping[str, str | None], str]] = [(environ, SOURCE_ENVIRONMENT)]

    file_layers = (
        (cwd_env_file, Path.cwd() / CWD_CONFIG_FILENAME),
        (user_env_file, USER_CONFIG_FILE),
    )
    for supplied, default_location in file_layers:
        if supplied == NO_CONFIG_FILE:
            continue
        # dotenv_values() on a missing path returns an empty mapping, so a layer
        # whose file does not exist simply contributes nothing.
        path = default_location if supplied is None else Path(supplied)
        layers.append((dotenv_values(path), str(path)))

    return layers


def _derived_setting_warnings(layers: list[tuple[Mapping[str, str | None], str]]) -> list[str]:
    """Report layers that set a derived setting, which has no effect.

    Silently ignoring `TT_TIME_LOG_FILE=...` looks like the tool is reading the
    wrong file for no reason, so say so rather than leaving `(derived)` in
    list-env as the only clue.

    Args:
        layers: The resolution layers, highest precedence first.

    Returns:
        One message per derived setting found, naming the layer and the fix.
    """
    return [
        f"{key} is set in {source} but is computed from other settings, so it is "
        f"ignored - set {instead} instead."
        for key, instead in DERIVED_SETTINGS.items()
        for mapping, source in layers
        if mapping.get(key)
    ]


def load_config(
    environ: Mapping[str, str] | None = None,
    cwd_env_file: Path | str | None = None,
    user_env_file: Path | str | None = None,
) -> Config:
    """Resolve configuration through the four-layer waterfall.

    Layers, highest precedence first: real ``TT_*`` environment variables, a
    ``.env`` in the current directory, the per-user ``~/.time-tracker/.env`` that
    ``time-tracker init`` writes, then built-in defaults. Merging is per key, so the
    user-global file still supplies everything a CWD ``.env`` leaves out. An
    empty value counts as unset, so a stray ``TT_FOO=`` line falls through
    rather than blanking a path.

    Unlike the ``load_dotenv`` it replaces, this does not mutate ``os.environ``
    and it records where every value came from, which is what makes the
    waterfall debuggable via ``list-env``.

    Args:
        environ: Environment mapping to read; defaults to ``os.environ``.
        cwd_env_file: Current-directory layer; defaults to ``./.env``, or
            ``NO_CONFIG_FILE`` to omit the layer.
        user_env_file: Per-user layer; defaults to ``~/.time-tracker/.env``, or
            ``NO_CONFIG_FILE`` to omit the layer.

    Returns:
        The resolved values, the source of each, and any warnings.

    Raises:
        ConfigError: If a setting holds a value of the wrong type.
    """
    layers = _config_layers(environ, cwd_env_file, user_env_file)
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}

    def setting(key: str, default: str) -> str:
        """Resolve one key through the layers, recording the source that won."""
        for mapping, source in layers:
            value = mapping.get(key)
            if value:
                values[key] = value
                sources[key] = source
                return value
        values[key] = default
        sources[key] = SOURCE_DEFAULT
        return default

    def derived(key: str, value: Any) -> None:
        """Record a value composed from other settings rather than set directly."""
        values[key] = value
        sources[key] = SOURCE_DERIVED

    inv_save_dir = setting("TT_INV_SAVE_DIR", DEFAULT_INV_SAVE_DIR)
    log_save_dir = setting("TT_LOG_SAVE_DIR", DEFAULT_LOG_SAVE_DIR)
    time_log_filename = setting("TT_TIME_LOG_FILENAME", DEFAULT_TIME_LOG_FILENAME)
    invoices_log_filename = setting("TT_INVOICES_LOG_FILENAME", DEFAULT_INVOICES_LOG_FILENAME)
    clients_json_dir = setting("TT_CLIENTS_JSON_DIR", inv_save_dir)
    setting("TT_CLIENTS_FILE", os.path.join(clients_json_dir, CLIENTS_FILENAME))
    invoices_json_dir = setting("TT_INVOICES_JSON_DIR", inv_save_dir)
    setting("TT_INVOICES_FILE", os.path.join(invoices_json_dir, INVOICES_FILENAME))
    # The template used to be named inside invoices.json; it is configuration, not
    # state, so it lives here instead (see docs/adr/0003-*). Defaults to the previous
    # location so an existing setup keeps working without editing .env.
    setting("TT_TEMPLATE_FILE", os.path.join(invoices_json_dir, time_tracker_templates.TEMPLATE_FILENAME))
    max_minutes = setting("TT_MAX_MINUTES_CONFIRMATION", DEFAULT_MAX_MINUTES_CONFIRMATION)

    derived("TT_TIME_LOG_FILE", os.path.join(log_save_dir, time_log_filename))
    derived("TT_INVOICES_LOG_FILE", os.path.join(log_save_dir, invoices_log_filename))

    try:
        values["TT_MAX_MINUTES_CONFIRMATION"] = int(max_minutes)
    except ValueError as exc:
        # Fail loudly at the boundary: a non-numeric limit would otherwise blow up
        # mid-command inside add-time, far from the .env line that caused it.
        raise ConfigError(
            f"TT_MAX_MINUTES_CONFIRMATION must be a whole number of minutes, got "
            f"{max_minutes!r} (from {sources['TT_MAX_MINUTES_CONFIRMATION']})"
        ) from exc

    return Config(values=values, sources=sources, warnings=_derived_setting_warnings(layers))


@app.command()
def list_env() -> None:
    """Show the resolved configuration and which layer supplied each value."""
    label_map: dict[str, str] = {
        "TT_INV_SAVE_DIR": "Invoice Save Directory",
        "TT_LOG_SAVE_DIR": "Time Log Save Directory",
        "TT_CLIENTS_JSON_DIR": "Clients JSON Directory",
        "TT_INVOICES_JSON_DIR": "Invoices JSON Directory",
        "TT_TIME_LOG_FILENAME": "Time Log Filename",
        "TT_TIME_LOG_FILE": "Time Log File Path",
        "TT_INVOICES_LOG_FILENAME": "Invoice Log Filename",
        "TT_INVOICES_LOG_FILE": "Invoice Log File Path",
        "TT_CLIENTS_FILE": "Clients File Path",
        "TT_INVOICES_FILE": "Invoices File Path",
        "TT_TEMPLATE_FILE": "Invoice Template Path",
        "TT_MAX_MINUTES_CONFIRMATION": "Warn if added time exceeds",
    }

    # Source is always shown: a four-layer waterfall you cannot trace is
    # undebuggable (see docs/adr/0004-*).
    table = PrettyTable(field_names=["Variable", "Value", "Setting", "Source"])
    table.align = "l"

    for key, label in label_map.items():
        table.add_row([key, global_vars.get(key, ""), label, config_sources.get(key, "")])

    print(table)

