"""The breaking-change escape hatch ADR-042 describes now exists (T67).

ADR-042: *"Explicitly declaring a break is the escape hatch. It is a phrase in
the change itself rather than a CLI flag, so the reason lands in the history
that the break will later be explained from."*

Until T67 that was half built. The flag existed; **nothing read the phrase**.
CI runs `aegis api check-contract --baseline origin/master` and passes no
flags, so there was no way to land an intended breaking change at all — the
documented mechanism was unreachable from the only place it mattered. Found
while trying to use it for ADR-050's route removal.

The scoping is the part worth testing rather than assuming: a marker may only
accept a break made on the **same branch that declared it**. A stale marker
from an old commit silently licensing a later, different break would be worse
than no hatch, because it would look like governance.

Real throwaway repositories, because the function reads real git.
"""

from __future__ import annotations

import subprocess

import pytest

from aegis.api.contract import BREAKING_MARKER, declaring_commit

pytestmark = pytest.mark.requirement("ADR-042", "T67")


def _git(cwd, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def _repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    return tmp_path


def _commit(cwd, name: str, message: str) -> None:
    (cwd / name).write_text(name, encoding="utf-8")
    _git(cwd, "add", name)
    _git(cwd, "commit", "-q", "-m", message)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _commit(root, "base.txt", "chore: baseline")
    _git(root, "branch", "baseline")
    monkeypatch.chdir(root)
    return root


def test_a_declared_break_is_found_and_named(repo) -> None:
    """Named, not merely detected: the operator should see *which* change accepted it."""
    _commit(
        repo,
        "change.txt",
        f"feat(api): one search route\n\n{BREAKING_MARKER}: /v1/search/entities is removed.",
    )
    assert declaring_commit("baseline") == "feat(api): one search route"


def test_an_undeclared_break_is_not_accepted(repo) -> None:
    _commit(repo, "change.txt", "feat(api): one search route")
    assert declaring_commit("baseline") is None


def test_the_marker_is_read_from_the_body_not_only_the_subject(repo) -> None:
    """A subject line is 72 characters; the reason needs more room than that."""
    _commit(repo, "change.txt", f"feat(api): rename\n\nWhy: because.\n{BREAKING_MARKER}")
    assert declaring_commit("baseline") == "feat(api): rename"


def test_a_marker_outside_the_range_does_not_license_a_later_break(repo) -> None:
    """The scoping rule, and the reason the range is not just "recent history".

    An old accepted break must not accept a new one. Otherwise a repository
    that once declared a break would accept every break afterwards, and the
    gate would read as governance while enforcing nothing.
    """
    _commit(repo, "old.txt", f"feat(api): an older break\n\n{BREAKING_MARKER}")
    _git(repo, "branch", "-f", "baseline", "HEAD")
    _commit(repo, "new.txt", "feat(api): a different change, undeclared")
    assert declaring_commit("baseline") is None


def test_any_commit_on_the_branch_may_declare_it(repo) -> None:
    """The declaration and the change need not be the same commit.

    A branch that fixes up its own work should not lose its declaration to a
    follow-up commit.
    """
    _commit(repo, "change.txt", f"feat(api): the break\n\n{BREAKING_MARKER}")
    _commit(repo, "fixup.txt", "test: cover the new route")
    assert declaring_commit("baseline") == "feat(api): the break"


def test_an_unreachable_baseline_falls_back_to_the_tip_commit(repo) -> None:
    """CI clones shallow, so the range may not be computable.

    `actions/checkout` fetches depth 1 and the workflow fetches master at depth
    1, leaving no common ancestor. The fallback reads the tip commit — enough
    for the marker to work in CI, and narrow enough that it cannot reach back
    into history it was never given.
    """
    _commit(repo, "change.txt", f"feat(api): the break\n\n{BREAKING_MARKER}")
    assert declaring_commit("no-such-ref") == "feat(api): the break"


def test_the_fallback_still_says_no_when_nothing_declares(repo) -> None:
    """Non-vacuity: the fallback must not accept everything."""
    _commit(repo, "change.txt", "feat(api): undeclared")
    assert declaring_commit("no-such-ref") is None


def test_outside_a_repository_it_declines_rather_than_raising(tmp_path, monkeypatch) -> None:
    """A gate that crashes is a gate that gets removed."""
    monkeypatch.chdir(tmp_path)
    assert declaring_commit("origin/master") is None
