# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "cooked-input==0.7.0",
#     "openpyxl==3.1.5",
#     "prettytable",
#     "pywin32==311; sys_platform == 'win32'",
#     "python-dotenv",
#     "typer",
# ]
# ///

"""
Standalone timer GUI for Time Tracker.

A small tkinter window to track work as it happens and append the result to the
same time-log CSV (and using the same ``.env`` configuration) as ``time_tracker.py``.

Run it with::

    uv run timer_app.py
    uv run timer_app.py --client IO --notes "Bug fixes"

The optional ``--client`` / ``--notes`` flags pre-fill the UI; the timer is not
started automatically.

Copyright (c) 2015-2026 Leonard Wanger
"""

import logging
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

import typer

# From the config and CLI-plumbing modules rather than from `time_tracker` itself, which
# pulls in every command module the GUI has no use for.
from time_tracker_cli import __version__
from time_tracker_config import ConfigError, load_config
from time_tracker_json import read_json_args
from time_tracker_time_log import (
    STATUS_NON_BILLABLE,
    STATUS_UNBILLED,
    append_time_entry,
    default_entry_status,
)


logger = logging.getLogger(__name__)

APP_NAME = "Time Tracker Timer"
AUTHOR = "Leonard Wanger"
COPYRIGHT = "Copyright (c) 2015-2026 Leonard Wanger"
PROJECT_URL = "https://github.com/lwanger/time-tracker"

# How often the elapsed-time label is refreshed (ms). The display is HH:MM, so a
# once-a-minute refresh is sufficient.
TICK_INTERVAL_MS = 60_000

# Colour of the elapsed-time display while the timer is running (a calm green).
RUNNING_COLOR = "#1b8a3a"

# The tracked multi-resolution Windows icon, shipped next to this script.
ICON_FILE = Path(__file__).resolve().parent / "timer.ico"

# PNG fallback used on platforms without ``.ico`` support, i.e. everywhere but
# Windows - which is why these files are tracked. The load is still best-effort:
# the app falls back to Tk's default icon when both the .ico and the PNGs are absent.
ICON_DIR = Path(__file__).resolve().parent / "assets" / "timer_app_icon_pngs" / "icons"
ICON_SIZES = (16, 32, 48, 64, 128, 256)

# A distinct AppUserModelID lets Windows group the timer under its own taskbar
# icon instead of the generic Python launcher icon.
APP_USER_MODEL_ID = "TimeTracker.Timer"

# Bounds for the client pulldown's width, in characters. The minimum keeps the
# control from collapsing for short names; the maximum stops one long company
# name from stretching the window off-screen.
CLIENT_COMBO_MIN_WIDTH = 20
CLIENT_COMBO_MAX_WIDTH = 45


# --------------------------------------------------------------------------- #
# Pure helpers (no tkinter / I/O) - unit tested in tests/test_timer_app.py
# --------------------------------------------------------------------------- #
def format_elapsed(total_seconds: float) -> str:
    """Format an elapsed duration in seconds as ``HH:MM``.

    Args:
        total_seconds: Elapsed time in seconds (negative values clamp to zero).

    Returns:
        A zero-padded ``"HH:MM"`` string, e.g. ``3660 -> "01:01"``.
    """
    safe_seconds = max(int(total_seconds), 0)
    hours, remainder = divmod(safe_seconds, 3600)
    minutes = remainder // 60
    return f"{hours:02d}:{minutes:02d}"


def compute_elapsed_minutes(start_dt: datetime, end_dt: datetime) -> int:
    """Return whole minutes between two timestamps (matching the CSV schema).

    Args:
        start_dt: Entry start timestamp.
        end_dt: Entry end timestamp.

    Returns:
        The elapsed minutes, rounded to the nearest whole minute (never negative).
    """
    elapsed_seconds = (end_dt - start_dt).total_seconds()
    return max(round(elapsed_seconds / 60), 0)


def running_title(running: bool) -> str:
    """Return the window title for the given running state.

    Args:
        running: Whether the timer is currently running.

    Returns:
        ``"Time Tracker Timer — running"`` while running, otherwise
        ``"Time Tracker Timer"``.
    """
    return f"{APP_NAME} — running" if running else APP_NAME


def build_save_confirmation(minutes: int, notes: str, elapsed_display: str,
                            status: str = STATUS_UNBILLED) -> tuple[str, bool]:
    """Build the prompt and default answer for the "save this entry?" dialog.

    Adds a warning line for entries under a minute and for entries with no
    notes, so the user is asked to confirm before either is recorded.

    Args:
        minutes: Whole minutes that would be written to the time log.
        notes: Current contents of the notes field.
        elapsed_display: Pre-formatted ``HH:MM`` elapsed string for display.
        status: Status the entry will be logged with. Named in the dialog when it is
            not ``unbilled``, since this is the last point the user can decline it.

    Returns:
        A ``(message, default_yes)`` tuple. ``default_yes`` is ``False`` when
        the entry has no notes, so the dialog defaults to *not* adding it and
        the user can cancel to add notes first.
    """
    lines = [f"Total time: {elapsed_display} ({minutes} min)."]

    if status == STATUS_NON_BILLABLE:
        lines.append("This entry will be logged as non-billable.")

    warnings: list[str] = []
    if minutes < 1:
        warnings.append("• This entry is under a minute.")
    has_notes = bool(notes.strip())
    if not has_notes:
        warnings.append("• This entry has no notes.")

    if warnings:
        lines.append("")
        lines.extend(warnings)

    lines.append("")
    lines.append("Add this entry to the time log?")
    return "\n".join(lines), has_notes


def resolve_prefill_client(clients: dict[str, Any], client: str | None) -> str | None:
    """Resolve a CLI ``--client`` value against the known client codes.

    Args:
        clients: Mapping of client code to record (from ``clients.json``).
        client: The raw CLI value (any case) or ``None``.

    Returns:
        The matching upper-cased client code, or ``None`` when no value was given
        or it does not match a known client.
    """
    if not client:
        return None

    candidate = client.strip().upper()
    return candidate if candidate in clients else None


def format_client_choice(code: str, client_record: dict[str, Any]) -> str:
    """Format one client for the pulldown as ``"Company Name (CODE)"``.

    The code stays visible because it is what is written to the time log and what
    ``--client`` accepts, so the UI must not be the one place it is hidden.

    Args:
        code: The client code (the key in ``clients.json``).
        client_record: That client's record.

    Returns:
        ``"FakeCo (TEST)"``, or the bare code when the record has no usable
        ``company``. ``clients.json`` is not schema-validated anywhere, so a
        record missing a company name must still be selectable.
    """
    company = str(client_record.get("company", "")).strip()
    return f"{company} ({code})" if company else code


def build_client_choices(clients: dict[str, Any]) -> dict[str, str]:
    """Build the pulldown's label-to-code mapping, ordered by company name.

    The mapping is the pulldown's single source of truth: it is insertion-ordered,
    so ``list(choices)`` are the values to display and ``choices[label]`` is the
    code to record. Labels are never parsed back apart - a company name containing
    parentheses would defeat that.

    Args:
        clients: Mapping of client code to record (from ``clients.json``).

    Returns:
        ``{label: code}`` sorted case-insensitively by company name, with the code
        breaking ties. A client with no company name sorts by its code.
    """
    ordered_codes = sorted(
        clients,
        key=lambda code: (str(clients[code].get("company", "")).strip().casefold(), code),
    )
    return {format_client_choice(code, clients[code]): code for code in ordered_codes}


def choice_for_code(choices: dict[str, str], code: str | None) -> str:
    """Find the pulldown label for a client code (used to apply ``--client``).

    Args:
        choices: The mapping from :func:`build_client_choices`.
        code: A client code, or ``None``.

    Returns:
        The matching label, or ``""`` when there is no match - which the pulldown
        reads as "nothing selected".
    """
    if code is None:
        return ""

    return next((label for label, client_code in choices.items() if client_code == code), "")


def client_combo_width(choices: dict[str, str]) -> int:
    """Width in characters for the client pulldown, sized to its longest label.

    Without this the combobox keeps Tk's 20-character default and clips the very
    names this pulldown exists to show.

    Args:
        choices: The mapping from :func:`build_client_choices`.

    Returns:
        The longest label's length, clamped to
        ``[CLIENT_COMBO_MIN_WIDTH, CLIENT_COMBO_MAX_WIDTH]``.
    """
    longest_label = max((len(label) for label in choices), default=0)
    return min(max(longest_label, CLIENT_COMBO_MIN_WIDTH), CLIENT_COMBO_MAX_WIDTH)


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
class TimerApp:  # pragma: no cover - tkinter view wiring is verified manually
    """The tkinter timer window.

    The class is a thin view over the tested pure helpers above; its event
    handlers delegate formatting/computation to them and persistence to
    :func:`time_tracker_time_log.append_time_entry`.
    """

    def __init__(self, root: tk.Tk, config: dict[str, Any], clients: dict[str, Any],
                 prefill_client: str | None = None, prefill_notes: str | None = None) -> None:
        self.root = root
        self.config = config
        self.clients = clients

        self._start_dt: datetime | None = None
        self._tick_job: str | None = None
        self._icon_images: list[tk.PhotoImage] = []
        self._default_elapsed_fg: str = ""

        # The pulldown shows labels; ``selected_client_code`` maps back to the code.
        self._client_choices = build_client_choices(clients)

        self.client_var = tk.StringVar(value=choice_for_code(self._client_choices, prefill_client))
        self.elapsed_var = tk.StringVar(value=format_elapsed(0))
        self.notes_var = tk.StringVar(value=prefill_notes or "")

        root.title(running_title(False))
        root.minsize(360, 0)
        self._set_window_icon()

        self._build_menu()
        self._build_body()
        self._update_button_states()
        root.protocol("WM_DELETE_WINDOW", self.on_exit)

    # -- layout ------------------------------------------------------------- #
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Settings…", command=self.show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        timer_menu = tk.Menu(menubar, tearoff=0)
        timer_menu.add_command(label="Start", accelerator="Ctrl+S", command=self.start)
        timer_menu.add_command(label="Stop", accelerator="Ctrl+T", command=self.stop)
        timer_menu.add_separator()
        timer_menu.add_command(label="Clear Notes", command=self.clear_notes)
        menubar.add_cascade(label="Timer", menu=timer_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)
        self.root.bind_all("<Control-s>", lambda _event: self.start())
        self.root.bind_all("<Control-t>", lambda _event: self.stop())

    def _build_body(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        # Row 0: client selector
        ttk.Label(frame, text="Client:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.client_combo = ttk.Combobox(
            frame, textvariable=self.client_var, state="readonly",
            values=list(self._client_choices),
            width=client_combo_width(self._client_choices),
        )
        self.client_combo.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)

        # Row 1: elapsed time
        self.elapsed_label = ttk.Label(frame, textvariable=self.elapsed_var, font=("Segoe UI", 32))
        self.elapsed_label.grid(row=1, column=0, columnspan=3, pady=8)
        # Remember the theme default so the running-state green can be reverted.
        self._default_elapsed_fg = str(self.elapsed_label.cget("foreground"))

        # Row 2: start / stop
        button_row = ttk.Frame(frame)
        button_row.grid(row=2, column=0, columnspan=3, pady=4)
        self.start_button = ttk.Button(button_row, text="Start", command=self.start)
        self.start_button.grid(row=0, column=0, padx=4)
        self.stop_button = ttk.Button(button_row, text="Stop", command=self.stop)
        self.stop_button.grid(row=0, column=1, padx=4)

        # Row 3: notes + clear
        ttk.Label(frame, text="Notes:").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        self.notes_entry = ttk.Entry(frame, textvariable=self.notes_var)
        self.notes_entry.grid(row=3, column=1, sticky="ew", pady=4)
        self.clear_button = ttk.Button(frame, text="✕", width=3, command=self.clear_notes)
        self.clear_button.grid(row=3, column=2, sticky="w", padx=(4, 0), pady=4)

        if not self.clients:
            messagebox.showerror(
                APP_NAME,
                f"No clients found at {self.config['TT_CLIENTS_FILE']}.\n"
                "Add a clients.json before tracking time.",
            )

    def _set_window_icon(self) -> None:
        """Apply the app icon to the title bar and taskbar (best effort).

        Prefers the tracked ``.ico`` (crisp on the Windows taskbar) and falls
        back to the PNGs on platforms without ``.ico`` support. Missing or
        unreadable icons are logged and ignored so the app still runs with Tk's
        default icon.
        """
        if ICON_FILE.is_file():
            try:
                self.root.iconbitmap(default=str(ICON_FILE))
                return
            except tk.TclError as exc:
                logger.debug("Could not apply .ico icon %s: %s", ICON_FILE, exc)

        images: list[tk.PhotoImage] = []
        for size in ICON_SIZES:
            icon_path = ICON_DIR / f"timer-{size}.png"
            if not icon_path.is_file():
                continue
            try:
                images.append(tk.PhotoImage(file=str(icon_path)))
            except tk.TclError as exc:
                logger.debug("Could not load icon %s: %s", icon_path, exc)

        if not images:
            logger.info("No application icon found in %s; using the default.", ICON_DIR)
            return

        # Keep references on the instance so the images survive garbage collection.
        self._icon_images = images
        self.root.iconphoto(True, *images)

    def _apply_running_indicator(self, running: bool) -> None:
        """Reflect the running state in the title bar and elapsed-time colour."""
        self.root.title(running_title(running))
        self.elapsed_label.config(
            foreground=RUNNING_COLOR if running else self._default_elapsed_fg
        )

    # -- state -------------------------------------------------------------- #
    @property
    def is_running(self) -> bool:
        return self._start_dt is not None

    @property
    def selected_client_code(self) -> str:
        """The selected client's code, or ``""`` when nothing is selected.

        The pulldown holds a display label; this is the only place it becomes the
        code that gets recorded.
        """
        return self._client_choices.get(self.client_var.get(), "")

    def _update_button_states(self) -> None:
        can_start = bool(self.clients) and not self.is_running
        self.start_button.config(state="normal" if can_start else "disabled")
        self.stop_button.config(state="normal" if self.is_running else "disabled")
        self.client_combo.config(state="disabled" if self.is_running else "readonly")

    # -- timer actions ------------------------------------------------------ #
    def start(self) -> None:
        if self.is_running:
            return

        if not self.client_var.get():
            messagebox.showwarning(APP_NAME, "Please select a client before starting the timer.")
            return

        self._start_dt = datetime.now()
        self.elapsed_var.set(format_elapsed(0))
        self._apply_running_indicator(True)
        self._update_button_states()
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        self._tick_job = self.root.after(TICK_INTERVAL_MS, self._tick)

    def _tick(self) -> None:
        # Bound once and tested directly rather than via is_running, which is that same
        # test behind a property and so narrows the Optional for no reader or checker.
        start_dt = self._start_dt
        if start_dt is None:
            return
        elapsed = (datetime.now() - start_dt).total_seconds()
        self.elapsed_var.set(format_elapsed(elapsed))
        self._schedule_tick()

    def _cancel_tick(self) -> None:
        if self._tick_job is not None:
            self.root.after_cancel(self._tick_job)
            self._tick_job = None

    def stop(self) -> None:
        start_dt = self._start_dt
        if start_dt is None:
            return

        self._cancel_tick()
        end_dt = datetime.now()
        minutes = compute_elapsed_minutes(start_dt, end_dt)
        elapsed_display = format_elapsed((end_dt - start_dt).total_seconds())

        message, default_yes = build_save_confirmation(minutes, self.notes_var.get(), elapsed_display,
                                                       self._entry_status())
        save = messagebox.askyesno(
            APP_NAME, message,
            default=messagebox.YES if default_yes else messagebox.NO,
        )
        if save:
            self._save_entry(start_dt, end_dt, minutes)

        self._reset()

    def _entry_status(self) -> str:
        """Status for an entry saved now, from the selected client's setting."""
        return default_entry_status(self.clients.get(self.selected_client_code, {}))

    def _save_entry(self, start_dt: datetime, end_dt: datetime, minutes: int) -> None:
        try:
            append_time_entry(
                self.config["TT_TIME_LOG_FILE"], start_dt, end_dt, minutes,
                self.selected_client_code, self.notes_var.get(), self._entry_status(),
            )
        except OSError as exc:
            logger.error("Could not write time log: %s", exc)
            messagebox.showerror(
                APP_NAME,
                f"Could not write to {self.config['TT_TIME_LOG_FILE']}.\n"
                "Please ensure the file is not open in another program.",
            )
            return

        messagebox.showinfo(APP_NAME, f"Added {minutes} minute(s) to the time log.")

    def _reset(self) -> None:
        """Stop and zero the timer, keeping the client and notes for re-use."""
        self._cancel_tick()
        self._start_dt = None
        self.elapsed_var.set(format_elapsed(0))
        self._apply_running_indicator(False)
        self._update_button_states()

    def clear_notes(self) -> None:
        self.notes_var.set("")

    # -- menu commands ------------------------------------------------------ #
    def show_about(self) -> None:
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME}\nVersion {__version__}\n\n{AUTHOR}\n{COPYRIGHT}\n\n{PROJECT_URL}",
        )

    def show_settings(self) -> None:
        rows = (
            ("Time Log Filename", self.config["TT_TIME_LOG_FILENAME"]),
            ("Log Save Directory", self.config["TT_LOG_SAVE_DIR"]),
            ("Clients File", self.config["TT_CLIENTS_FILE"]),
        )

        window = tk.Toplevel(self.root)
        window.title(f"{APP_NAME} Settings")
        window.transient(self.root)
        frame = ttk.Frame(window, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        for index, (label, value) in enumerate(rows):
            ttk.Label(frame, text=f"{label}:").grid(row=index, column=0, sticky="w", padx=(0, 8), pady=2)
            # Read-only entry so long paths can be selected and copied.
            entry = ttk.Entry(frame, width=60)
            entry.insert(0, str(value))
            entry.config(state="readonly")
            entry.grid(row=index, column=1, sticky="ew", pady=2)

        ttk.Button(frame, text="Close", command=window.destroy).grid(
            row=len(rows), column=0, columnspan=2, pady=(10, 0)
        )

    def on_exit(self) -> None:
        start_dt = self._start_dt
        if start_dt is not None:
            self._cancel_tick()
            end_dt = datetime.now()
            minutes = compute_elapsed_minutes(start_dt, end_dt)
            answer = messagebox.askyesnocancel(
                APP_NAME,
                f"A timer is running ({minutes} min).\nSave it to the time log before exiting?",
            )
            if answer is None:  # cancel - keep running
                self._schedule_tick()
                return
            if answer:
                self._save_entry(start_dt, end_dt, minutes)
            self._start_dt = None

        self.root.destroy()


def _set_app_user_model_id() -> None:  # pragma: no cover - Windows-only side effect
    """Tell Windows to group the timer under its own taskbar icon.

    Must run before the Tk window is created. A no-op on non-Windows platforms
    and best-effort if the shell call is unavailable.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (OSError, AttributeError) as exc:
        logger.debug("Could not set AppUserModelID: %s", exc)


def launch(config: dict[str, Any], prefill_client: str | None, prefill_notes: str | None) -> None:  # pragma: no cover
    """Create the Tk root and run the timer window."""
    _set_app_user_model_id()
    clients = read_json_args(config["TT_CLIENTS_FILE"])
    root = tk.Tk()
    TimerApp(root, config, clients, prefill_client=prefill_client, prefill_notes=prefill_notes)
    root.mainloop()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
app = typer.Typer(add_completion=False, help="Time Tracker's standalone time-tracking timer.")


@app.command()
def main(
    client: str = typer.Option(None, "--client", "-c", help="Pre-select this client code in the UI."),
    notes: str = typer.Option(None, "--notes", "-n", help="Pre-fill the notes field in the UI."),
) -> None:
    """Launch the timer GUI, optionally pre-filling the client and notes."""
    try:
        resolved = load_config()
    except ConfigError as config_error:
        typer.echo(f"Error: {config_error}")
        raise typer.Exit(code=1)

    for warning in resolved.warnings:
        typer.echo(f"Warning: {warning}")

    config = resolved.values
    clients = read_json_args(config["TT_CLIENTS_FILE"])

    prefill_client = resolve_prefill_client(clients, client)
    if client and prefill_client is None:
        typer.echo(f"Warning: client '{client}' not found in clients.json; leaving it unselected.")

    launch(config, prefill_client, notes)


if __name__ == "__main__":
    app()
