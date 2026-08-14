# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "cooked-input==0.7.0",
#     "dateparser",
#     "openpyxl==3.1.5",
#     "prettytable",
#     "pywin32==311; sys_platform == 'win32'",
#     "python-dotenv",
#     "typer",
# ]
# ///
"""
Track time and create invoices.

The command line entry point. Each command lives in the module for its area -
clients, time entries, invoices, init - and registers itself on the Typer app in
time_tracker_cli; importing them here is what makes them reachable.

TODO: see TODO.md

Copyright (c) 2015-2026 Leonard Wanger
"""

import sys

import cooked_input as ci
import typer

# __version__ is re-exported here as the package version.
from time_tracker_cli import __version__, app  # noqa: F401
from time_tracker_config import (
    USER_CONFIG_FILE,
    Config,
    ConfigError,
    config_sources,
    global_vars,
    load_config,
)


# isort: split
# Imported for their side effect: each module registers its commands on `app`.
import time_tracker_clients  # noqa: F401
import time_tracker_init  # noqa: F401
import time_tracker_invoices  # noqa: F401
import time_tracker_time  # noqa: F401


def main() -> None:
    """Entry point for the `time-tracker` / `tt` console scripts (and `python time_tracker.py`)."""
    try:
        config = load_config()
    except ConfigError as config_error:
        # `init` rewrites the config, so it has to stay reachable when the config is
        # what is broken - otherwise a bad value locks the user out of the fix.
        if "init" not in sys.argv[1:]:
            print(f"Error: {config_error}")
            print(f"Fix the value by hand, or run `time-tracker init` to rewrite {USER_CONFIG_FILE}.")
            raise typer.Exit(code=1)
        print(f"Warning: {config_error}")
        print("Continuing with defaults so init can rewrite the configuration.")
        config = Config()

    for warning in config.warnings:
        print(f"Warning: {warning}")

    global_vars.update(config.values)
    config_sources.update(config.sources)

    try:
        app()
    except ci.GetInputInterrupt:
        print("\nOperation cancelled")


if __name__ == '__main__':
    main()
