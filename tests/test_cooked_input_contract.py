"""Contract tests: every ``cooked_input`` call site must bind against the installed release.

The same failure mode as ``test_config_keys.py``, one layer out. Every test that drives
an interactive command patches ``ci.get_string`` and friends, so the suite can pass in
full while no call site has ever reached real ``cooked_input`` code. That was harmless
until 0.7.0 replaced the old ``**options`` bag with named parameters: an unrecognised
keyword used to be logged and ignored, and now raises ``TypeError`` naming it. A bump
could therefore break every prompt in the application and leave 374 tests green.

These tests read the call sites out of the source and bind each one against
``inspect.signature`` of the object the *installed* ``cooked_input`` actually exposes.
Nothing is mocked and nothing is called - binding is what catches a renamed keyword, a
dropped parameter or a name removed from the package's namespace, which is the whole
class of breakage a version bump can cause.
"""

import ast
import inspect
from pathlib import Path
from typing import NamedTuple

import cooked_input
import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Everything that talks to cooked_input. Discovered rather than listed: the commands were
# split out of time_tracker.py by area once already, and a module added later must not be
# able to skip this check just because nobody remembered to add it here.
SOURCE_GLOBS = ("time_tracker*.py", "timer_app.py")

# Stands in for a real argument. bind_partial only checks arity and names, never values.
ARGUMENT = object()


class CallSite(NamedTuple):
    """One ``ci.<attribute>(...)`` call found in the source."""

    module: str
    line: int
    attribute: str
    positional_count: int
    keywords: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.module}:{self.line} ci.{self.attribute}"


def _import_aliases(tree: ast.Module) -> set[str]:
    """The local names bound to the ``cooked_input`` module in ``tree``.

    Handles ``import cooked_input as ci`` and a plain ``import cooked_input``, so the
    check does not quietly stop working if a module spells the import differently.
    """
    aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "cooked_input":
                    aliases.add(alias.asname or alias.name)

    return aliases


def _call_sites(path: Path) -> list[CallSite]:
    """Every ``<alias>.<attribute>(...)`` call in ``path``.

    Calls that splat (``*args`` / ``**kwargs``) are skipped: their arity is not knowable
    from the source, so binding them would report a failure that is not one. No call site
    currently splats, so nothing is being skipped today.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = _import_aliases(tree)
    if not aliases:
        return []

    sites: list[CallSite] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
            continue
        if func.value.id not in aliases:
            continue
        if any(isinstance(arg, ast.Starred) for arg in node.args):
            continue
        if any(keyword.arg is None for keyword in node.keywords):
            continue

        sites.append(
            CallSite(
                module=path.name,
                line=node.lineno,
                attribute=func.attr,
                positional_count=len(node.args),
                keywords=tuple(keyword.arg for keyword in node.keywords),
            )
        )

    return sites


def _collect() -> list[CallSite]:
    """Every cooked_input call site in the project, ordered for stable test ids."""
    paths = {path for glob in SOURCE_GLOBS for path in PROJECT_ROOT.glob(glob)}
    sites = [site for path in sorted(paths) for site in _call_sites(path)]
    return sorted(sites, key=lambda site: (site.module, site.line))


CALL_SITES = _collect()


def test_call_sites_were_found() -> None:
    """Guard the scanner itself: a parser that silently matches nothing proves nothing.

    66 call sites across seven modules at the time of writing; the floor is loose enough
    to survive ordinary edits and tight enough to catch a scanner that stops matching.
    """
    assert len(CALL_SITES) > 50, "cooked_input call sites are no longer being found"
    assert len({site.module for site in CALL_SITES}) >= 5


@pytest.mark.parametrize("site", CALL_SITES, ids=str)
def test_call_site_binds_against_installed_cooked_input(site: CallSite) -> None:
    """The call's arity and keyword names are accepted by the installed signature."""
    target = getattr(cooked_input, site.attribute, None)
    assert target is not None, (
        f"{site}: cooked_input {cooked_input.__version__} no longer exports "
        f"{site.attribute!r}"
    )

    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError) as exc:  # pragma: no cover - no such call site today
        pytest.skip(f"{site}: signature unavailable ({exc})")

    try:
        signature.bind_partial(
            *[ARGUMENT] * site.positional_count,
            **{keyword: ARGUMENT for keyword in site.keywords},
        )
    except TypeError as exc:
        pytest.fail(
            f"{site} does not bind against cooked_input {cooked_input.__version__}: "
            f"{exc}\n  signature: {site.attribute}{signature}"
        )
