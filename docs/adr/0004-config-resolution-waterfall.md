# Config resolves through a four-layer waterfall rooted in the user's home directory

`init()` (now `load_config()`) loaded config with `load_dotenv(find_dotenv(usecwd=True))`,
which walks *upward* from the current directory looking for a `.env`. Now that `time-tracker`
is installed on `PATH` as a console script rather than run with `uv run` from the project
directory, that meant the same command read different config — or none, silently falling
back to `./invoices` and `./time_logs` — depending on where the shell happened to be
sitting. Config now lives in one per-user location, `~/.time-tracker/.env`, which the `init`
command writes and `load_config()` reads regardless of the working directory.

A CWD `.env` is still honoured, and at *higher* precedence than the user-global file. The
full order is real `TT_*` environment variables, then `.\.env`, then `~/.time-tracker/.env`,
then built-in defaults, merged per key rather than per file. The CWD layer looks backwards
until you know what depends on it: `tests/.env` and `docs/.env` are picked up by exactly
that mechanism, and keeping it means the test suite and the documented examples work
unchanged while also giving a way to override config for a single run.

## Considered options

**A bare `~/.env`** as the user-global file. Rejected because `find_dotenv` matches any
file named `.env` in any ancestor directory, and the home directory is an ancestor of
essentially everything you work in. A `.env` there would be silently loaded by every other
dotenv-using project below it, and any unrelated tool's stray `~/.env` would be loaded
into Time Tracker. The `TT_` prefix stops the *variables* colliding but not the *file* being
read by the wrong tool. `~/.time-tracker/.env` is invisible to `find_dotenv` (it only matches
files literally named `.env`, and `.time-tracker` is a sibling directory rather than an
ancestor), which keeps the two layers cleanly separated.

**A `.env` shipped alongside the installed package** as the bottom layer. Rejected: the
install directory (`AppData\Roaming\uv\tools\time-tracker\`) is replaced wholesale by
`uv tool upgrade`, so anything written there is lost on the next upgrade, and it
duplicates the defaults already expressed as `os.getenv(key, default)` in code.

**Keeping CWD-relative discovery only.** Rejected — it is the behaviour that motivated
the change.

## Consequences

Provenance cannot be recovered from `load_dotenv`, which flattens every layer into
`os.environ`. Resolution therefore uses `dotenv_values()` to read each file into a plain
dict and walks the chain per key, recording which source supplied each value. This is a
pure function that does not mutate `os.environ` (removing the `patch("time_tracker.load_dotenv")`
scaffolding the tests previously needed), and it is what lets `list-env` show a `Source`
column — without which a four-layer waterfall is undebuggable. Config does not sync
between machines, since `~` is outside OneDrive; this is deliberate, as the values are
absolute machine-specific paths.
