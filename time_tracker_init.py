"""The init command: create the directories, seed the data files, write the config.

Leonard Wanger, 2026
"""

import datetime
import shutil
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import cooked_input as ci
import typer
from prettytable import PrettyTable

import time_tracker_templates
from time_tracker_cli import CMDS, app
from time_tracker_config import (
    CLIENTS_FILENAME,
    DEFAULT_INV_SAVE_DIR,
    DEFAULT_LOG_SAVE_DIR,
    DERIVED_SETTINGS,
    INVOICES_FILENAME,
    NO_CONFIG_FILE,
    USER_CONFIG_FILE,
    global_vars,
    load_config,
)
from time_tracker_json import (
    read_json_args,
    write_json_args,
)
from time_tracker_template import VARIABLES_SHEET_NAME


# Settings `init` decides itself, from its flags and prompts. Their existing values
# are preserved as prompt defaults and by split/relocation detection, not by the
# customization check - which would otherwise pin them and make init unable to
# move anything. Every *other* settable setting is written whenever it differs
# from the default, so nothing can be silently dropped by omission.
INIT_OWNED_SETTINGS = (
    "TT_INV_SAVE_DIR",
    "TT_LOG_SAVE_DIR",
    "TT_CLIENTS_JSON_DIR",
    "TT_INVOICES_JSON_DIR",
    "TT_CLIENTS_FILE",
    "TT_INVOICES_FILE",
    "TT_TEMPLATE_FILE",
)

# Absolute fallbacks offered by `init`, which must not write relative paths: the
# whole point of the user-global config is that it works from any directory.
INIT_DEFAULT_DATA_DIR = Path.home() / "time-tracker"
INIT_DEFAULT_LOG_SUBDIR = "time_logs"

# Written to a fresh clients.json so the file documents its own schema. `add-client`
# is the easier route in; this is what a hand-editor copies.
SAMPLE_CLIENT_CODE = "SAMPLE"
SAMPLE_CLIENT: dict[str, Any] = {
    "company": "Sample Client Inc",
    "contact": "Sample Contact",
    "addr1": "123 Example Street",
    "addr2": "Sample City, ST 00000",
    "phone": "(555) 555-0100",
    "rate_hr": 100,
    "rate_day": 800,
}

# --------------------------------------------------------------------------- #
# init command
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class InitPaths:
    """The directories `init` configures."""

    data_dir: Path
    log_dir: Path
    clients_dir: Path
    invoices_dir: Path


@dataclass(frozen=True)
class InitFiles:
    """The data files `init` seeds and configures."""

    clients_file: Path
    invoices_file: Path
    template_file: Path


@dataclass(frozen=True)
class SeedResult:
    """What `init` did with one data file."""

    path: Path
    action: str
    detail: str = ""


def _absolute_default(current: str, fallback: Path) -> str:
    """Choose a directory prompt default, never a relative one.

    A configured absolute path is offered back so re-running ``init`` to change
    one directory is easy. Anything relative - including the built-in
    ``./invoices`` - is replaced by the fallback, because a relative path in the
    user-global config would resolve differently in every shell, which is the
    problem this command exists to fix.

    Args:
        current: The currently configured value, from any layer.
        fallback: Absolute path to offer when ``current`` is unusable.

    Returns:
        The default to show in the prompt.
    """
    path = Path(current).expanduser()
    return str(path if path.is_absolute() else fallback)


def _prompt_directory(label: str, default: str, yes: bool) -> Path:
    """Prompt for a directory, or take the default when ``--yes`` is set.

    Args:
        label: Prompt text.
        default: Value used on an empty response or with ``--yes``.
        yes: Skip the prompt entirely.

    Returns:
        The absolute, user-expanded directory path.

    Raises:
        typer.Exit: If the response is blank.
    """
    value = default if yes else ci.get_string(
        prompt=label, default=default, cleaners=[ci.StripCleaner()], commands=CMDS,
    )

    if not value.strip():
        print(f"Error: {label} cannot be empty.")
        raise typer.Exit(code=1)

    return Path(value).expanduser().resolve()


def _resolve_optional_dir(
    flag_value: str | None,
    label: str,
    data_dir: Path,
    setting: str,
    advanced: bool,
    yes: bool,
) -> Path:
    """Resolve a split-out directory, preserving one the config already splits.

    These directories normally follow the data directory. But a setup that
    deliberately keeps `clients.json` or `invoices.json` elsewhere must survive a
    plain re-run: collapsing it onto the data directory would orphan the real
    files and seed decoys in their place, and `--advanced` is opt-in so the user
    has no way to know they needed it.

    Args:
        flag_value: Explicit directory from the command line, if given.
        label: Prompt text when ``--advanced`` is set.
        data_dir: The directory this one follows by default.
        setting: Config key holding the current value, for split detection.
        advanced: Prompt for this directory instead of deriving it.
        yes: Accept defaults without prompting.

    Returns:
        The directory to configure.
    """
    if flag_value:
        return Path(flag_value).expanduser().resolve()

    # Split means the existing config already points somewhere other than its
    # data directory; a relative default has simply never been configured.
    configured = str(global_vars.get(setting, ""))
    current_data_dir = str(global_vars.get("TT_INV_SAVE_DIR", ""))
    already_split = bool(
        configured
        and Path(configured).is_absolute()
        and not _same_setting(configured, current_data_dir)
    )
    split_dir = Path(configured).expanduser().resolve() if already_split else data_dir

    if advanced:
        return _prompt_directory(label, str(split_dir), yes)

    return split_dir


def _resolve_init_paths(
    data_dir: str | None,
    log_dir: str | None,
    clients_dir: str | None,
    invoices_dir: str | None,
    advanced: bool,
    yes: bool,
) -> InitPaths:
    """Resolve all four directories from flags, prompts and the current config."""
    data_default = _absolute_default(
        global_vars.get("TT_INV_SAVE_DIR", DEFAULT_INV_SAVE_DIR), INIT_DEFAULT_DATA_DIR,
    )
    data_path = (
        Path(data_dir).expanduser().resolve() if data_dir
        else _prompt_directory("Data directory (invoices, clients.json, invoices.json)", data_default, yes)
    )

    log_default = _absolute_default(
        global_vars.get("TT_LOG_SAVE_DIR", DEFAULT_LOG_SAVE_DIR), data_path / INIT_DEFAULT_LOG_SUBDIR,
    )
    log_path = (
        Path(log_dir).expanduser().resolve() if log_dir
        else _prompt_directory("Time log directory (time_log.csv, invoices_log.csv)", log_default, yes)
    )

    return InitPaths(
        data_dir=data_path,
        log_dir=log_path,
        clients_dir=_resolve_optional_dir(
            clients_dir, "Clients JSON directory", data_path, "TT_CLIENTS_JSON_DIR", advanced, yes,
        ),
        invoices_dir=_resolve_optional_dir(
            invoices_dir, "Invoices JSON directory", data_path, "TT_INVOICES_JSON_DIR", advanced, yes,
        ),
    )


def _resolve_data_file(setting: str, directory: Path, filename: str) -> Path:
    """Keep an already-configured data file, else use the default name.

    A setup that renamed or relocated one of these has to survive a re-run.
    Seeding the default path instead leaves a decoy that the new config points at
    while the real file sits unused - which resets the Invoice Counter, hides a
    real client list behind a SAMPLE record, or swaps a customized template for a
    blank placeholder.

    Args:
        setting: Config key that may already name this file.
        directory: Where the file lives by default.
        filename: Default filename.

    Returns:
        The path to seed and configure.
    """
    configured = str(global_vars.get(setting, ""))
    if configured:
        path = Path(configured).expanduser()
        if path.is_absolute():
            return path

    return directory / filename


def _resolve_init_files(paths: InitPaths) -> InitFiles:
    """Resolve the three data files `init` seeds, preserving configured locations."""
    return InitFiles(
        clients_file=_resolve_data_file("TT_CLIENTS_FILE", paths.clients_dir, CLIENTS_FILENAME),
        invoices_file=_resolve_data_file("TT_INVOICES_FILE", paths.invoices_dir, INVOICES_FILENAME),
        template_file=_resolve_data_file(
            "TT_TEMPLATE_FILE", paths.invoices_dir, time_tracker_templates.TEMPLATE_FILENAME,
        ),
    )


def _config_value(value: Any) -> str:
    """Render a setting for the .env file, never emitting a backslash.

    dotenv reads a backslash inside a quoted value as an escape sequence, so a
    Windows path written verbatim would come back corrupted.
    """
    return str(value).replace("\\", "/")


def _same_setting(current: Any, other: Any) -> bool:
    """Compare two resolved values, tolerating path spelling differences.

    ``os.path.join`` produces ``dir\\clients.json`` where a hand-written .env has
    ``dir/clients.json``; these name the same file and must not be treated as a
    customization worth writing out.

    That tolerance is Windows-only, and deliberately so: on POSIX a backslash is an
    ordinary filename character, ``Path`` does not treat it as a separator, and the
    two spellings really are two different files. The case cannot arise there
    anyway, since ``os.path.join`` yields a forward slash on POSIX and the plain
    string comparison already matches.
    """
    # Path comparison normalizes separators. Both arguments are stringified first,
    # and Path() accepts any string, so this cannot raise on odd input - a value
    # that is not a path simply compares unequal.
    return str(current) == str(other) or Path(str(current)) == Path(str(other))


def _baseline_settings(owned: dict[str, str]) -> dict[str, Any]:
    """What `load_config` would resolve from init's own choices alone.

    Asking the resolver rather than restating the defaults keeps the two from
    drifting: a default only has to change in one place.

    Args:
        owned: The settings init decided, as an environment-shaped mapping.

    Returns:
        Every resolved setting, with no config file contributing.
    """
    return load_config(
        environ=owned, cwd_env_file=NO_CONFIG_FILE, user_env_file=NO_CONFIG_FILE,
    ).values


def _settings_to_write(paths: InitPaths, files: InitFiles) -> dict[str, str]:
    """Every setting `init` should write explicitly, and its value.

    `init` decides the directories and data files (see ``INIT_OWNED_SETTINGS``).
    For every *other* settable setting, the current value is written whenever it
    differs from what those choices alone would produce - so a renamed time log
    survives a re-run instead of silently reverting to a default that points
    somewhere else. Settings matching the derived default are left out, and shown
    commented in the file, so they keep tracking future changes to the defaults.

    Args:
        paths: The configured directories.
        files: The resolved data-file paths.

    Returns:
        Setting name to the value to write.
    """
    owned = {
        "TT_INV_SAVE_DIR": _config_value(paths.data_dir),
        "TT_LOG_SAVE_DIR": _config_value(paths.log_dir),
        "TT_CLIENTS_JSON_DIR": _config_value(paths.clients_dir),
        "TT_INVOICES_JSON_DIR": _config_value(paths.invoices_dir),
        "TT_CLIENTS_FILE": _config_value(files.clients_file),
        "TT_INVOICES_FILE": _config_value(files.invoices_file),
        "TT_TEMPLATE_FILE": _config_value(files.template_file),
    }

    written = dict(owned)
    for key, baseline_value in _baseline_settings(owned).items():
        if key in owned or key in DERIVED_SETTINGS:
            continue

        current = global_vars.get(key)
        if current is None or _same_setting(current, baseline_value):
            continue

        written[key] = _config_value(current)

    return written


def _resolve_starting_number(next_invoice: int | None, invoices_file: Path, force: bool, yes: bool) -> int | None:
    """Decide the starting invoice number, or ``None`` to keep an existing counter.

    Only a fresh setup is asked: rewriting a live ``invoices.json`` would reset
    the Invoice Counter, and duplicate invoice numbers are a hard error
    (see docs/adr/0002-*), so keeping it is the safe default.

    Args:
        next_invoice: Value from ``--next-invoice``, if given.
        invoices_file: Where the counter lives.
        force: Whether existing data files are being overwritten.
        yes: Accept the default of 1 without prompting.

    Returns:
        The starting number, or ``None`` when the existing counter is kept.

    Raises:
        typer.Exit: If ``--next-invoice`` is below 1.
    """
    if invoices_file.exists() and not force:
        return None

    if next_invoice is not None:
        if next_invoice < 1:
            print(f"Error: --next-invoice must be at least 1 (got {next_invoice}).")
            raise typer.Exit(code=1)
        return next_invoice

    if yes:
        return 1

    return ci.get_int(
        prompt="Starting invoice number", default=1, validators=ci.RangeValidator(1, None), commands=CMDS,
    )


def _seed_file(path: Path, force: bool, write: Callable[[Path], object], detail: str = "") -> SeedResult:
    """Create a data file, keeping any existing one unless ``force`` is set.

    Args:
        path: File to create.
        force: Overwrite an existing file instead of keeping it.
        write: Callable that creates the file; only invoked when writing. Its return
            value is ignored, hence ``object`` - shutil.copyfile hands back a path.
        detail: Extra context for the report line.

    Returns:
        What happened, for the summary `init` prints.
    """
    existed = path.exists()
    if existed and not force:
        return SeedResult(path=path, action="kept", detail=detail)

    write(path)
    return SeedResult(path=path, action="replaced" if existed else "created", detail=detail)


def _seed_data_files(files: InitFiles, starting_number: int | None, force: bool) -> list[SeedResult]:
    """Seed the three data files, reporting what was created and what was kept."""
    invoices_file, clients_file, template_file = (
        files.invoices_file, files.clients_file, files.template_file,
    )

    if starting_number is None:
        current = read_json_args(str(invoices_file)).get("next_invoice", "unknown")
        counter_detail = f"next invoice number {current}"
    else:
        counter_detail = f"next invoice number {starting_number}"

    clients = _seed_file(
        clients_file, force,
        lambda path: write_json_args(str(path), {SAMPLE_CLIENT_CODE: SAMPLE_CLIENT}),
    )
    # Only a file we just wrote holds the sample; reporting it for a kept file
    # would describe someone else's real client list.
    if clients.action != "kept":
        clients = replace(clients, detail=f"sample client {SAMPLE_CLIENT_CODE}")

    return [
        _seed_file(
            invoices_file, force,
            lambda path: write_json_args(str(path), {"next_invoice": starting_number}),
            detail=counter_detail,
        ),
        clients,
        _seed_file(
            template_file, force,
            lambda path: shutil.copyfile(time_tracker_templates.template_path(), path),
        ),
    ]


def _write_user_env(path: Path, paths: InitPaths, files: InitFiles) -> None:
    """Write the per-user .env, replacing any existing one.

    Args:
        path: The config file to write, normally ``~/.time-tracker/.env``.
        paths: The configured directories.
        files: Resolved paths of the seeded data files.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    settings = _settings_to_write(paths, files)
    # Anything not written is left as a comment showing the value it will resolve
    # to, so the file documents the whole vocabulary without freezing defaults.
    baseline = _baseline_settings(settings)
    commented = {
        key: value for key, value in baseline.items()
        if key not in settings and key not in DERIVED_SETTINGS
    }

    lines = [
        f"# Time Tracker configuration - written by `time-tracker init` on {datetime.date.today().isoformat()}.",
        "# Read by every time-tracker and timer-app run, from any working directory.",
        "#",
        "# Precedence, highest first: real TT_* environment variables, a .env in the",
        "# current directory, then this file. `time-tracker list-env` shows which one won.",
        "#",
        "# Paths use forward slashes because dotenv reads backslashes inside a quoted",
        "# value as escape sequences; Windows accepts forward slashes everywhere.",
        "",
        *(f'{key}="{value}"' for key, value in settings.items()),
        "",
        "# Remaining settings, shown with the value they resolve to. Uncomment to change:",
        *(f'# {key}="{_config_value(value)}"' for key, value in sorted(commented.items())),
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")


def _print_init_summary(paths: InitPaths, config_file: Path) -> None:
    """Show the directories and config file `init` is about to write."""
    table = PrettyTable(field_names=["Setting", "Path"])
    table.align = "l"
    table.add_row(["Data directory", paths.data_dir])
    table.add_row(["Time log directory", paths.log_dir])
    table.add_row(["Clients JSON directory", paths.clients_dir])
    table.add_row(["Invoices JSON directory", paths.invoices_dir])
    table.add_row(["Configuration file", config_file])
    print()
    print(table)


def _print_next_steps(template_file: Path, clients_file: Path) -> None:
    """Print what the user has to do by hand before invoicing."""
    print(
        f"""
Next steps:

  1. Customize the invoice template:
       {template_file}
     - Replace the issuer details (business name, address, phone) on the invoice
       sheet. They are static text, not variables.
     - The '{VARIABLES_SHEET_NAME}' sheet lists every value Time Tracker fills in. Reference one
       from the invoice sheet with a formula like =Variables!B3 rather than
       typing the value, and Excel keeps it correct when cells move.

  2. Add your clients:
       time-tracker add-client      (prompts for each field, then confirms)
     - Or edit {clients_file} by hand: copy the {SAMPLE_CLIENT_CODE} record, which is
       there to show the shape. Retainer clients also take 'retainer_hrs' and
       'retainer_rate'. Add '"non_billable": true' to track a client's time
       without ever invoicing it (rates are then optional).

  3. Check the setup:
       time-tracker list-env        (confirm the paths, and where each came from)
       time-tracker list-clients    (confirm your clients parse)

  4. Start tracking time:
       time-tracker add-time        or   timer-app
"""
    )


@app.command()
def init(
    data_dir: str = typer.Option(None, "--data-dir", help="Directory for invoices, clients.json and invoices.json (omit to be prompted)."),
    log_dir: str = typer.Option(None, "--log-dir", help="Directory for the time log and invoice log CSVs (omit to be prompted)."),
    clients_dir: str = typer.Option(None, "--clients-dir", help="Directory for clients.json (defaults to the data directory)."),
    invoices_dir: str = typer.Option(None, "--invoices-dir", help="Directory for invoices.json and the template (defaults to the data directory)."),
    next_invoice: int = typer.Option(None, "--next-invoice", help="Starting invoice number for a fresh setup (omit to be prompted; default 1)."),
    advanced: bool = typer.Option(False, "--advanced", help="Also prompt for the clients and invoices directories separately."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing data files instead of keeping them."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept all defaults without prompting."),
) -> None:
    """Set up Time Tracker: create directories, seed data files and write the config."""
    try:
        paths = _resolve_init_paths(data_dir, log_dir, clients_dir, invoices_dir, advanced, yes)
        files = _resolve_init_files(paths)
        starting_number = _resolve_starting_number(next_invoice, files.invoices_file, force, yes)

        _print_init_summary(paths, USER_CONFIG_FILE)
        confirmed = yes or ci.get_yes_no(
            prompt="Write this configuration (y/n)?", default="Yes", commands=CMDS,
        ) == "yes"
    except ci.GetInputInterrupt:
        print("\nOperation cancelled")
        raise typer.Exit(code=1)

    if not confirmed:
        print("Operation cancelled")
        raise typer.Exit(code=1)

    try:
        for directory in (paths.data_dir, paths.log_dir, paths.clients_dir, paths.invoices_dir):
            directory.mkdir(parents=True, exist_ok=True)

        results = _seed_data_files(files, starting_number, force)
        _write_user_env(USER_CONFIG_FILE, paths, files)
    except OSError as os_error:
        # Half-finished setup is recoverable - init never overwrites, so re-running
        # after fixing the permission or path problem completes the rest.
        print(f"Error: setup failed: {os_error}")
        raise typer.Exit(code=1)

    print(f"\nWrote {USER_CONFIG_FILE}")
    for result in results:
        suffix = f"  ({result.detail})" if result.detail else ""
        print(f"  {result.action:<8} {result.path}{suffix}")

    _print_next_steps(files.template_file, files.clients_file)

