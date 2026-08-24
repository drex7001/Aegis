"""Every CLI command is reachable, and one of them was not (T78a).

`aegis migrate arrests-to-events` shipped in Phase 5 raising `NameError` on two
names its function never imported. It has tests — `test_arrest_migration.py`
calls `migrate_co_arrests` directly — and none of them goes through the CLI, so
the entry point had never been executed by anything.

`ruff` found it in under a second, which is the argument T78a is making. These
tests are the second half of that argument: a linter proves a name resolves, and
a test proves the command *runs*, and the two failures look identical from the
outside.
"""

from __future__ import annotations

import click
import pytest
from typer.testing import CliRunner

from aegis.cli import app as cli_app

pytestmark = pytest.mark.requirement("T78a", "T63")


class _ReachedTheDatabase(RuntimeError):
    """Sentinel: the command resolved everything it needed and got this far."""


def _command_paths() -> list[list[str]]:
    """Every leaf command, as the argv a user would type.

    Grouping is detected by the presence of `commands` rather than by
    `isinstance(..., click.Group)`: Typer's group class does not always satisfy
    that check across click versions, and a walk that silently finds one
    "command" is a test that passes by doing nothing.
    """
    from typer.main import get_command

    def walk(command: click.Command, prefix: list[str]) -> list[list[str]]:
        children = getattr(command, "commands", None)
        if not children:
            return [prefix]
        found: list[list[str]] = []
        for name, sub in children.items():
            found.extend(walk(sub, [*prefix, name]))
        return found

    paths = walk(get_command(cli_app), [])
    # The CLI has had at least this many commands since Phase 5; a walk that
    # collapses to a handful means the traversal broke, not the CLI shrank.
    assert len(paths) >= 25, f"command walk found only {len(paths)}: {paths}"
    return paths


@pytest.mark.parametrize("path", _command_paths(), ids=lambda path: " ".join(path))
def test_every_command_renders_its_help(path: list[str]) -> None:
    """A cheap net under the whole surface: help exercises the signature.

    It would not have caught the `NameError` below — help never enters the body —
    which is exactly why both tests are here.
    """
    result = CliRunner().invoke(cli_app, [*path, "--help"])
    assert result.exit_code == 0, result.output


def test_the_arrest_migration_reaches_the_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression. Before the fix this raised `NameError: get_settings`.

    The command loads settings and the ontology and builds its action context
    before it opens a session, so replacing the sessionmaker proves it got
    through all of that — without needing a database to prove it.
    """
    import aegis.store

    def _explode() -> None:
        raise _ReachedTheDatabase

    monkeypatch.setattr(aegis.store, "get_sessionmaker", _explode)

    result = CliRunner().invoke(
        cli_app, ["migrate", "arrests-to-events", "--actor", "lint-regression"]
    )

    assert isinstance(result.exception, _ReachedTheDatabase), (
        f"the command failed before reaching the database: {result.exception!r}"
    )


def test_the_arrest_migration_is_dry_by_default() -> None:
    """`--apply` exists and is off unless asked for (spec 10 §2.4).

    Asserted against the parsed command rather than against rendered help text,
    which rich wraps to the terminal width — an 80-column CI runner splits
    `--apply` across two lines and the substring check fails on the formatting
    rather than on the interface.
    """
    from typer.main import get_command

    command = get_command(cli_app).commands["migrate"].commands["arrests-to-events"]
    apply_option = next(p for p in command.params if p.name == "apply")

    assert "--apply" in apply_option.opts
    assert apply_option.default is False
