"""Shared plumbing for the Time Tracker command modules.

Holds the Typer application each command module registers itself on, the version
``--version`` reports, the ``/help`` and ``/cancel`` commands every prompt accepts,
and the date parsing more than one command needs. It imports nothing else from the
project, so every command module can depend on it without a cycle.

Leonard Wanger, 2026
"""

import datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import cooked_input as ci
import dateparser
import typer


# Reported when no installed distribution can be queried - running from a source
# checkout, or straight from time_tracker.py. Kept in step with pyproject.toml's
# version by test_fallback_version_matches_pyproject.
FALLBACK_VERSION = "1.0.0"


def resolve_version() -> str:
    """Report the installed distribution's version, or the fallback without one."""
    try:
        return version("time-tracker")
    except PackageNotFoundError:
        return FALLBACK_VERSION


__version__ = resolve_version()


app = typer.Typer()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"time-tracker version {__version__}")
        raise typer.Exit()


@app.callback()
def app_callback(
    version: bool | None = typer.Option(None, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit."),
) -> None:
    """Time Tracker - track time and create invoices."""


# cmd_dict is Optional because cooked_input passes None when a command carries no
# dictionary; neither callback reads it, but the signature has to match what calls it.
def cancel_action(cmd_str: str, cmd_vars: str, cmd_dict: dict[str, Any] | None) -> ci.CommandResponse:
    # cooked_input callback function for canceling an operation
    return ci.CommandResponse(ci.COMMAND_ACTION_CANCEL, None)


def help_action(cmd_str: str, cmd_vars: str, cmd_dict: dict[str, Any] | None) -> ci.CommandResponse:
    # cooked_input callback function for printing help content for commands
    print("Commands:")
    print("\t/? or /help - print this help message")
    print("\t/cancel, /quit - cancel the current operation")
    return ci.CommandResponse(ci.COMMAND_ACTION_NOP, None)


# Accepted at every prompt, so they are passed to every cooked_input call.
CMDS = {'/?': ci.GetInputCommand(help_action), '/help': ci.GetInputCommand(help_action),
        '/cancel': ci.GetInputCommand(cancel_action), '/quit': ci.GetInputCommand(cancel_action)}


def parse_flexible_datetime(value: str) -> datetime.datetime | None:
    """Parse a flexible date/time string, e.g. '2026-07-23', '9:00 am', or 'today'.

    Uses the same underlying parser as the interactive ``ci.get_date`` prompts
    (cooked_input's ``DateConvertor`` wraps ``dateparser.parse``), so CLI flags
    and interactive input accept identical formats.

    Args:
        value: The date/time string to parse.

    Returns:
        The parsed datetime, or ``None`` if ``value`` could not be parsed.
    """
    return dateparser.parse(value)


def parse_cli_datetime(value: str, flag_name: str) -> datetime.datetime:
    """Parse a CLI date/time flag's value, exiting with an error if it can't be parsed."""
    parsed = parse_flexible_datetime(value)
    if parsed is None:
        print(f"Error: could not parse {flag_name} value '{value}' as a date/time.")
        raise typer.Exit(code=1)
    return parsed