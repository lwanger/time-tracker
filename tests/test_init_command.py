"""Tests for the init command.

``init`` writes to ``~/.time-tracker/.env`` and creates directories, so the
``isolate_user_config`` fixture is autouse: a test that forgot to redirect it
would overwrite the developer's own configuration.
"""

from pathlib import Path
from unittest.mock import patch

import cooked_input as ci
import openpyxl
import pytest
import typer

import time_tracker_config
import time_tracker_init
import time_tracker_json
import time_tracker_template
import time_tracker_templates


@pytest.fixture(autouse=True)
def isolate_user_config(tmp_path):
    """Redirect the per-user config file and start from an unconfigured state."""
    user_config = tmp_path / "home" / ".time-tracker" / ".env"
    with (
        patch.object(time_tracker_init, "USER_CONFIG_FILE", user_config),
        patch.dict(time_tracker_config.global_vars, {}, clear=True),
        patch.dict(time_tracker_config.config_sources, {}, clear=True),
    ):
        yield user_config


@pytest.fixture
def data_dir(tmp_path) -> Path:
    return tmp_path / "time_tracker_data"


def _run_init(data_dir: Path, **kwargs):
    """Run init non-interactively with the given data directory."""
    options = {
        "data_dir": str(data_dir),
        "log_dir": str(data_dir / "time_logs"),
        "clients_dir": None,
        "invoices_dir": None,
        "next_invoice": None,
        "advanced": False,
        "force": False,
        "yes": True,
    }
    options.update(kwargs)
    time_tracker_init.init(**options)


# --------------------------------------------------------------------------- #
# fresh setup
# --------------------------------------------------------------------------- #
def test_init_creates_directories_and_data_files(data_dir, isolate_user_config):
    _run_init(data_dir, next_invoice=500)

    assert data_dir.is_dir()
    assert (data_dir / "time_logs").is_dir()
    assert (data_dir / "invoices.json").is_file()
    assert (data_dir / "clients.json").is_file()
    assert (data_dir / time_tracker_templates.TEMPLATE_FILENAME).is_file()
    assert isolate_user_config.is_file()


def test_init_seeds_the_requested_invoice_number(data_dir):
    _run_init(data_dir, next_invoice=500)

    assert time_tracker_json.read_json_args(str(data_dir / "invoices.json")) == {"next_invoice": 500}


def test_init_defaults_the_invoice_number_to_one(data_dir):
    _run_init(data_dir)

    assert time_tracker_json.read_json_args(str(data_dir / "invoices.json"))["next_invoice"] == 1


def test_init_seeds_a_sample_client_to_copy(data_dir):
    _run_init(data_dir)

    clients = time_tracker_json.read_json_args(str(data_dir / "clients.json"))
    assert time_tracker_init.SAMPLE_CLIENT_CODE in clients
    # The sample has to carry the fields make_invoice reads, or it is a bad model.
    sample = clients[time_tracker_init.SAMPLE_CLIENT_CODE]
    for required in ("company", "contact", "addr1", "addr2", "phone", "rate_hr"):
        assert required in sample


def test_init_copies_a_usable_template(data_dir):
    """The copied template must satisfy the phase-1 contract, not just exist."""
    _run_init(data_dir)

    template = data_dir / "Invoice - blank.xlsx"
    workbook = openpyxl.load_workbook(template)
    rows = time_tracker_template.read_template_variable_rows(workbook)
    time_tracker_template.validate_template_variables(workbook, rows, str(template))

    assert time_tracker_template.VARIABLES_SHEET_NAME in workbook.sheetnames


def test_init_splits_the_log_directory_from_the_data_directory(tmp_path, data_dir):
    log_dir = tmp_path / "logs_elsewhere"
    _run_init(data_dir, log_dir=str(log_dir))

    assert log_dir.is_dir()
    assert (data_dir / "invoices.json").is_file()


# --------------------------------------------------------------------------- #
# the written config
# --------------------------------------------------------------------------- #
def test_init_writes_every_path_setting(data_dir, isolate_user_config):
    _run_init(data_dir)

    written = isolate_user_config.read_text(encoding="utf-8")
    for key in (
        "TT_INV_SAVE_DIR",
        "TT_LOG_SAVE_DIR",
        "TT_CLIENTS_JSON_DIR",
        "TT_INVOICES_JSON_DIR",
        "TT_TEMPLATE_FILE",
    ):
        assert f"{key}=" in written


def test_written_config_round_trips_through_load_config(data_dir, isolate_user_config, tmp_path):
    """The file init writes must be one load_config reads back identically."""
    _run_init(data_dir)

    config = time_tracker_config.load_config(
        environ={}, cwd_env_file=tmp_path / "absent.env", user_env_file=isolate_user_config,
    )

    assert Path(config.values["TT_INV_SAVE_DIR"]) == data_dir
    assert Path(config.values["TT_LOG_SAVE_DIR"]) == data_dir / "time_logs"
    assert Path(config.values["TT_TEMPLATE_FILE"]) == data_dir / "Invoice - blank.xlsx"
    assert config.sources["TT_INV_SAVE_DIR"] == str(isolate_user_config)


def test_written_paths_are_absolute(data_dir, isolate_user_config):
    """A relative path in the user-global config resolves differently per shell."""
    _run_init(data_dir)

    for line in isolate_user_config.read_text(encoding="utf-8").splitlines():
        if line.startswith("TT_"):
            value = line.split("=", 1)[1].strip('"')
            assert Path(value).is_absolute(), line


def test_written_paths_avoid_backslashes(data_dir, isolate_user_config):
    """dotenv reads a backslash in a quoted value as an escape sequence."""
    _run_init(data_dir)

    for line in isolate_user_config.read_text(encoding="utf-8").splitlines():
        if line.startswith("TT_"):
            assert "\\" not in line, line


def test_init_keeps_a_renamed_template_out_of_the_default_path(data_dir, isolate_user_config):
    """A renamed template must survive a re-run, not be replaced by a placeholder."""
    data_dir.mkdir(parents=True)
    custom = data_dir / "My Company Invoice.xlsx"
    custom.write_bytes(b"the user's customized template")

    with patch.dict(time_tracker_config.global_vars, {"TT_TEMPLATE_FILE": str(custom)}):
        _run_init(data_dir)

    written = isolate_user_config.read_text(encoding="utf-8")
    assert f'TT_TEMPLATE_FILE="{custom.as_posix()}"' in written
    assert custom.read_bytes() == b"the user's customized template"
    # No placeholder copied in under the default name to compete with it.
    assert not (data_dir / time_tracker_templates.TEMPLATE_FILENAME).exists()


def test_init_preserves_non_default_optional_settings(data_dir, isolate_user_config):
    """Reverting a renamed time log would hide every existing entry."""
    customized = {
        "TT_TIME_LOG_FILENAME": "my_time_log.csv",
        "TT_MAX_MINUTES_CONFIRMATION": 180,
    }
    with patch.dict(time_tracker_config.global_vars, customized):
        _run_init(data_dir)

    written = isolate_user_config.read_text(encoding="utf-8")
    assert 'TT_TIME_LOG_FILENAME="my_time_log.csv"' in written
    assert 'TT_MAX_MINUTES_CONFIRMATION="180"' in written
    # Carried over as real settings, not as commented-out defaults.
    assert '# TT_TIME_LOG_FILENAME' not in written
    assert '# TT_MAX_MINUTES_CONFIRMATION' not in written


def test_init_leaves_default_optional_settings_commented(data_dir, isolate_user_config):
    """Untouched settings stay commented so they keep tracking the defaults."""
    _run_init(data_dir)

    written = isolate_user_config.read_text(encoding="utf-8")
    assert f'# TT_TIME_LOG_FILENAME="{time_tracker_config.DEFAULT_TIME_LOG_FILENAME}"' in written
    assert f'# TT_MAX_MINUTES_CONFIRMATION="{time_tracker_config.DEFAULT_MAX_MINUTES_CONFIRMATION}"' in written


def test_preserved_settings_round_trip(data_dir, isolate_user_config, tmp_path):
    """What init preserves must come back out of load_config with the same value."""
    with patch.dict(time_tracker_config.global_vars, {"TT_TIME_LOG_FILENAME": "my_time_log.csv"}):
        _run_init(data_dir)

    config = time_tracker_config.load_config(
        environ={}, cwd_env_file=tmp_path / "absent.env", user_env_file=isolate_user_config,
    )

    assert config.values["TT_TIME_LOG_FILENAME"] == "my_time_log.csv"
    assert Path(config.values["TT_TIME_LOG_FILE"]).name == "my_time_log.csv"


def _resolved(user_config: Path, tmp_path: Path) -> dict:
    """Read back the config init wrote, with no other layer contributing."""
    return time_tracker_config.load_config(
        environ={}, cwd_env_file=tmp_path / "absent.env", user_env_file=user_config,
    ).values


def test_init_preserves_a_relocated_counter_file(tmp_path, data_dir, isolate_user_config):
    """Reverting this orphans the real counter and restarts invoice numbers at 1."""
    data_dir.mkdir(parents=True)
    counter = data_dir / "counter.json"
    time_tracker_json.write_json_args(str(counter), {"next_invoice": 900})

    with patch.dict(time_tracker_config.global_vars, {"TT_INVOICES_FILE": str(counter)}):
        _run_init(data_dir)

    resolved = _resolved(isolate_user_config, tmp_path)
    assert Path(resolved["TT_INVOICES_FILE"]) == counter
    assert time_tracker_json.read_json_args(resolved["TT_INVOICES_FILE"])["next_invoice"] == 900
    # No decoy counter left at the default path to compete with the real one.
    assert not (data_dir / "invoices.json").exists()


def test_init_preserves_a_relocated_clients_file(tmp_path, data_dir, isolate_user_config):
    """A shared clients.json outside the data directory must stay configured."""
    shared = tmp_path / "shared" / "clients.json"
    shared.parent.mkdir(parents=True)
    time_tracker_json.write_json_args(str(shared), {"REAL": {"company": "Real Co"}})

    with patch.dict(time_tracker_config.global_vars, {"TT_CLIENTS_FILE": str(shared)}):
        _run_init(data_dir)

    resolved = _resolved(isolate_user_config, tmp_path)
    assert Path(resolved["TT_CLIENTS_FILE"]) == shared
    assert "REAL" in time_tracker_json.read_json_args(resolved["TT_CLIENTS_FILE"])
    assert not (data_dir / "clients.json").exists()  # no SAMPLE decoy


def test_init_preserves_a_split_directory_layout(tmp_path, data_dir, isolate_user_config):
    """A plain re-run must not collapse a split layout onto the data directory."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir(parents=True)
    time_tracker_json.write_json_args(str(elsewhere / "clients.json"), {"REAL": {"company": "Real Co"}})
    time_tracker_json.write_json_args(str(elsewhere / "invoices.json"), {"next_invoice": 900})

    existing = {
        "TT_INV_SAVE_DIR": str(data_dir),
        "TT_CLIENTS_JSON_DIR": str(elsewhere),
        "TT_INVOICES_JSON_DIR": str(elsewhere),
    }
    with patch.dict(time_tracker_config.global_vars, existing):
        _run_init(data_dir)  # note: no --advanced, no --clients-dir/--invoices-dir

    resolved = _resolved(isolate_user_config, tmp_path)
    assert Path(resolved["TT_CLIENTS_JSON_DIR"]) == elsewhere
    assert Path(resolved["TT_INVOICES_JSON_DIR"]) == elsewhere
    assert time_tracker_json.read_json_args(resolved["TT_INVOICES_FILE"])["next_invoice"] == 900
    assert not (data_dir / "clients.json").exists()
    assert not (data_dir / "invoices.json").exists()


def test_unsplit_directories_still_follow_a_moved_data_directory(tmp_path, isolate_user_config):
    """Preserving a split must not freeze a layout that was never split."""
    old_data = tmp_path / "old"
    new_data = tmp_path / "new"
    existing = {
        "TT_INV_SAVE_DIR": str(old_data),
        "TT_CLIENTS_JSON_DIR": str(old_data),  # same as the data dir: not split
        "TT_INVOICES_JSON_DIR": str(old_data),
    }
    with patch.dict(time_tracker_config.global_vars, existing):
        _run_init(new_data)

    resolved = _resolved(isolate_user_config, tmp_path)
    assert Path(resolved["TT_CLIENTS_JSON_DIR"]) == new_data
    assert Path(resolved["TT_INVOICES_JSON_DIR"]) == new_data


def test_init_rewrites_an_existing_config(data_dir, isolate_user_config, tmp_path):
    isolate_user_config.parent.mkdir(parents=True, exist_ok=True)
    isolate_user_config.write_text('TT_INV_SAVE_DIR="/stale/path"\n', encoding="utf-8")

    _run_init(data_dir)

    assert "/stale/path" not in isolate_user_config.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# never overwrite data files
# --------------------------------------------------------------------------- #
def test_init_keeps_an_existing_invoice_counter(data_dir, capsys):
    data_dir.mkdir(parents=True)
    time_tracker_json.write_json_args(str(data_dir / "invoices.json"), {"next_invoice": 900})

    _run_init(data_dir, next_invoice=1)

    # Clobbering this would reset the counter, and duplicates are a hard error.
    assert time_tracker_json.read_json_args(str(data_dir / "invoices.json"))["next_invoice"] == 900
    output = capsys.readouterr().out
    assert "kept" in output
    assert "900" in output  # the current counter is reported, not silently skipped


def test_init_keeps_existing_clients(data_dir, capsys):
    data_dir.mkdir(parents=True)
    time_tracker_json.write_json_args(str(data_dir / "clients.json"), {"REAL": {"company": "Real Co"}})

    _run_init(data_dir)

    clients = time_tracker_json.read_json_args(str(data_dir / "clients.json"))
    assert clients == {"REAL": {"company": "Real Co"}}
    assert time_tracker_init.SAMPLE_CLIENT_CODE not in clients
    # The report must not claim a kept file holds the sample record. (The
    # next-steps text mentions SAMPLE too, so match the report's detail exactly.)
    assert f"(sample client {time_tracker_init.SAMPLE_CLIENT_CODE})" not in capsys.readouterr().out


def test_init_keeps_an_existing_customized_template(data_dir):
    data_dir.mkdir(parents=True)
    template = data_dir / "Invoice - blank.xlsx"
    template.write_bytes(b"not really a workbook, but it is the user's")

    _run_init(data_dir)

    assert template.read_bytes() == b"not really a workbook, but it is the user's"


def test_force_overwrites_data_files(data_dir, capsys):
    data_dir.mkdir(parents=True)
    time_tracker_json.write_json_args(str(data_dir / "invoices.json"), {"next_invoice": 900})

    _run_init(data_dir, next_invoice=1, force=True)

    assert time_tracker_json.read_json_args(str(data_dir / "invoices.json"))["next_invoice"] == 1
    assert "replaced" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# prompts
# --------------------------------------------------------------------------- #
def test_init_prompts_for_directories_when_flags_are_omitted(tmp_path, isolate_user_config):
    prompted = tmp_path / "prompted"
    with (
        patch("time_tracker_init.ci.get_string", autospec=True, side_effect=[str(prompted), str(prompted / "logs")]) as mock_string,
        patch("time_tracker_init.ci.get_int", autospec=True, return_value=42) as mock_int,
        patch("time_tracker_init.ci.get_yes_no", autospec=True, return_value="yes"),
    ):
        time_tracker_init.init(
            data_dir=None, log_dir=None, clients_dir=None, invoices_dir=None,
            next_invoice=None, advanced=False, force=False, yes=False,
        )

    assert mock_string.call_count == 2  # data and log directories only
    mock_int.assert_called_once()
    assert (prompted / "invoices.json").is_file()
    assert time_tracker_json.read_json_args(str(prompted / "invoices.json"))["next_invoice"] == 42


def test_advanced_prompts_for_the_split_directories(tmp_path, isolate_user_config):
    base = tmp_path / "base"
    with (
        patch("time_tracker_init.ci.get_string", autospec=True, side_effect=[
            str(base), str(base / "logs"), str(base / "clients"), str(base / "invoices"),
        ]) as mock_string,
        patch("time_tracker_init.ci.get_int", autospec=True, return_value=1),
        patch("time_tracker_init.ci.get_yes_no", autospec=True, return_value="yes"),
    ):
        time_tracker_init.init(
            data_dir=None, log_dir=None, clients_dir=None, invoices_dir=None,
            next_invoice=None, advanced=True, force=False, yes=False,
        )

    assert mock_string.call_count == 4
    assert (base / "clients" / "clients.json").is_file()
    assert (base / "invoices" / "invoices.json").is_file()


def test_split_directory_flags_skip_their_prompts(tmp_path, data_dir, isolate_user_config):
    """--clients-dir/--invoices-dir are usable without --advanced."""
    clients_elsewhere = tmp_path / "clients_here"
    invoices_elsewhere = tmp_path / "invoices_here"

    with patch("time_tracker_init.ci.get_string", autospec=True) as mock_string:
        _run_init(
            data_dir,
            clients_dir=str(clients_elsewhere),
            invoices_dir=str(invoices_elsewhere),
            advanced=True,  # would prompt, but the flags supply both
        )

    mock_string.assert_not_called()
    assert (clients_elsewhere / "clients.json").is_file()
    assert (invoices_elsewhere / "invoices.json").is_file()
    assert (invoices_elsewhere / time_tracker_templates.TEMPLATE_FILENAME).is_file()


def test_declining_the_confirmation_writes_nothing(data_dir, isolate_user_config):
    with (
        patch("time_tracker_init.ci.get_yes_no", autospec=True, return_value="no"),
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_init.init(
            data_dir=str(data_dir), log_dir=str(data_dir / "logs"), clients_dir=None,
            invoices_dir=None, next_invoice=1, advanced=False, force=False, yes=False,
        )

    assert exc_info.value.exit_code == 1
    assert not isolate_user_config.exists()
    assert not data_dir.exists()  # nothing created before confirmation


def test_interrupt_cancels_without_writing(data_dir, isolate_user_config, capsys):
    with (
        patch("time_tracker_init.ci.get_int", autospec=True, side_effect=ci.GetInputInterrupt),
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_init.init(
            data_dir=str(data_dir), log_dir=str(data_dir / "logs"), clients_dir=None,
            invoices_dir=None, next_invoice=None, advanced=False, force=False, yes=False,
        )

    assert exc_info.value.exit_code == 1
    assert "cancelled" in capsys.readouterr().out.lower()
    assert not isolate_user_config.exists()


# --------------------------------------------------------------------------- #
# validation and failure paths
# --------------------------------------------------------------------------- #
def test_invalid_next_invoice_exits_nonzero(data_dir, capsys, isolate_user_config):
    with pytest.raises(typer.Exit) as exc_info:
        _run_init(data_dir, next_invoice=0)

    assert exc_info.value.exit_code == 1
    assert "at least 1" in capsys.readouterr().out
    assert not isolate_user_config.exists()


def test_blank_directory_response_exits_nonzero(capsys, isolate_user_config):
    with (
        patch("time_tracker_init.ci.get_string", autospec=True, return_value="   "),
        pytest.raises(typer.Exit) as exc_info,
    ):
        time_tracker_init.init(
            data_dir=None, log_dir=None, clients_dir=None, invoices_dir=None,
            next_invoice=None, advanced=False, force=False, yes=False,
        )

    assert exc_info.value.exit_code == 1
    assert "cannot be empty" in capsys.readouterr().out


def test_unwritable_directory_exits_nonzero(data_dir, capsys):
    with (
        patch("time_tracker_init.Path.mkdir", side_effect=OSError("access denied")),
        pytest.raises(typer.Exit) as exc_info,
    ):
        _run_init(data_dir)

    assert exc_info.value.exit_code == 1
    assert "access denied" in capsys.readouterr().out


def test_init_prints_next_steps(data_dir, capsys):
    _run_init(data_dir)

    output = capsys.readouterr().out
    assert "Next steps" in output
    assert time_tracker_template.VARIABLES_SHEET_NAME in output  # how to wire up the template
    assert "list-env" in output
    assert "clients.json" in output


# --------------------------------------------------------------------------- #
# prompt defaults
# --------------------------------------------------------------------------- #
def test_relative_configured_path_is_not_offered_as_a_default():
    """./invoices in the current config must not be written to the user config."""
    assert time_tracker_init._absolute_default("./invoices", Path("/fallback")) == str(Path("/fallback"))


def test_absolute_configured_path_is_offered_back(tmp_path):
    """Re-running init to change one directory should keep the others."""
    assert time_tracker_init._absolute_default(str(tmp_path), Path("/fallback")) == str(tmp_path)
