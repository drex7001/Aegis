"""Search's two structural invariants, checked rather than reviewed (T67).

Both of these are rules about **how the code is shaped**, not about what one
query returns, and both fail silently when broken. A behavioural test cannot
catch either: a search path that generates candidates and filters afterwards
returns the right rows for every fixture anybody writes, and a second copy of
the normalization pipeline agrees with the first until the day someone edits
one of them.

So they are asserted over the source and over the contract:

1. **Authorization in candidate generation** (B-17, ADR-012). Every module that
   builds a candidate query composes a filter builder.
2. **One normalization pipeline** (H-22, ADR-052). Only `pipeline.py` calls the
   key functions; everyone else calls `search_keys`.

And one over the published document: **no totals**, anywhere in a search
response, because a count over an authorization-filtered collection is an
existence leak (spec 06 §4 default 4).
"""

from __future__ import annotations

import ast
import json

import pytest

from tests.support.paths import REPO_ROOT

pytestmark = pytest.mark.requirement("B-17", "H-22", "ADR-012", "ADR-052", "T67")

SEARCH_PACKAGE = REPO_ROOT / "aegis" / "search"

#: Modules that generate search candidates. Each must compose a filter builder.
CANDIDATE_MODULES = {
    "entities.py": "claim_filters",
    "claims.py": "claim_filters",
    "documents.py": "document_filters",
}

#: The three key functions. Calling them directly is how write and query drift
#: apart, so only the pipeline may.
KEY_FUNCTIONS = {"norm_key", "latin_key", "phonetic_key"}


def _called_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


# ── 1. authorization in candidate generation ────────────────────────────────


@pytest.mark.parametrize("module,builder", sorted(CANDIDATE_MODULES.items()))
def test_every_candidate_module_composes_a_filter_builder(
    module: str, builder: str
) -> None:
    """The B-17 invariant, as a property of the code.

    A behavioural test proves one query is filtered. This proves there is no
    unfiltered one to find, which is the claim spec 11 §4.1 actually makes.
    """
    source = (SEARCH_PACKAGE / module).read_text(encoding="utf-8")
    assert builder in _called_names(source), (
        f"aegis/search/{module} builds candidates without calling {builder}() — "
        "generate-then-filter answers 'no results' and 'results you may not "
        "see' with different response sizes (B-17)"
    )


def test_the_module_list_matches_what_is_actually_there() -> None:
    """Guards the parametrization: a new backend must not be missed silently."""
    present = {
        path.name
        for path in SEARCH_PACKAGE.glob("*.py")
        if path.name not in {"__init__.py", "pipeline.py", "results.py", "service.py", "targets.py"}
    }
    assert present == set(CANDIDATE_MODULES), (
        "a search backend was added or removed; add it to CANDIDATE_MODULES "
        f"with the filter builder it must compose (found {sorted(present)})"
    )


def test_the_orchestrator_generates_no_candidates_of_its_own() -> None:
    """`service.py` merges and pages; it must not query.

    If it grew its own query it would be a candidate module without the review
    that comes with being one, and the test above would not know to check it.
    """
    source = (SEARCH_PACKAGE / "service.py").read_text(encoding="utf-8")
    assert "select(" not in source, (
        "aegis/search/service.py issues its own query — every candidate query "
        "belongs in a backend, where the filter rule is enforced"
    )


# ── 2. one normalization pipeline ───────────────────────────────────────────


def test_only_the_pipeline_calls_the_key_functions() -> None:
    offenders: dict[str, set[str]] = {}
    for path in (*SEARCH_PACKAGE.glob("*.py"), REPO_ROOT / "aegis" / "er" / "mentions.py"):
        if path.name == "pipeline.py":
            continue
        direct = _called_names(path.read_text(encoding="utf-8")) & KEY_FUNCTIONS
        if direct:
            offenders[str(path.relative_to(REPO_ROOT))] = direct
    assert not offenders, (
        f"these call the key functions directly instead of search_keys(): {offenders}. "
        "Two ends computing keys independently is how a write and a query stop "
        "agreeing, and the failure mode is missing results (ADR-052)"
    )


def test_the_pipeline_really_is_the_thing_that_calls_them() -> None:
    """Non-vacuity: a rule nobody satisfies would pass the test above."""
    source = (SEARCH_PACKAGE / "pipeline.py").read_text(encoding="utf-8")
    assert KEY_FUNCTIONS <= _called_names(source)


def test_the_write_path_stamps_the_version() -> None:
    """A key with no version cannot be checked, and an unchecked key rots."""
    source = (REPO_ROOT / "aegis" / "er" / "mentions.py").read_text(encoding="utf-8")
    assert "normalization_version=" in source


# ── 3. no totals ────────────────────────────────────────────────────────────


def _schema(document: dict, name: str) -> dict:
    return document["components"]["schemas"][name]


def test_no_search_schema_carries_a_count() -> None:
    """A count over an authorization-filtered collection is an existence leak.

    Asserted against the published document rather than the Python class, so a
    field added anywhere in the response shape is caught — including one added
    to a nested model that nobody thought of as "the search response".
    """
    document = json.loads(
        (REPO_ROOT / "ui" / "openapi.json").read_text(encoding="utf-8")
    )
    forbidden = {"total", "count", "approximate_total", "hidden_count", "total_count"}
    for name in ("SearchResultsOut", "SearchGroupOut", "SearchHitOut"):
        fields = set(_schema(document, name).get("properties", {}))
        assert not fields & forbidden, (
            f"{name} exposes {sorted(fields & forbidden)} — a count over an "
            "authorization-filtered collection tells a caller that rows they "
            "cannot see exist (spec 06 §4 default 4)"
        )


def test_the_search_operation_is_the_only_one(  ) -> None:
    """ADR-050: one route. The removed one must stay removed."""
    document = json.loads(
        (REPO_ROOT / "ui" / "openapi.json").read_text(encoding="utf-8")
    )
    paths = {path for path in document["paths"] if path.startswith("/v1/search")}
    assert paths == {"/v1/search"}, (
        f"expected exactly one search route, found {sorted(paths)} — two routes "
        "means two rankings, two paginations and two copies of B-17's leak "
        "surface (M-11, ADR-050)"
    )
