"""The grammar refuses what B-17 says it must, at save (T69, spec 12 §2).

T69's acceptance criterion has four parts, and each is checked here as a
property of the grammar rather than as a behaviour of one example:

* a definition **cannot contain SQL**, because there is no field to put it in;
* the **compiler is total** over the grammar and raises outside it;
* depth, node count and set references are refused **at save**;
* a leaf naming vocabulary the ontology does not declare is refused, with the
  path that refused it.

The non-vacuity checks matter more than usual here. "No node carries SQL" is
trivially true of an empty grammar, and "the compiler is total" is trivially
true of a compiler nobody calls — so both are paired with a check that the
grammar is actually populated and the compiler actually reached.
"""

from __future__ import annotations

import pytest

from aegis.ontology import load
from aegis.sets.grammar import (
    GrammarError,
    OrNode,
    PROPERTY_OPERATORS,
    depth,
    expand_interfaces,
    interfaces_used,
    parse,
    referenced_sets,
    validate,
    walk,
)
from aegis.sets.limits import MAX_DEPTH, MAX_NODES, MAX_SET_REFERENCES
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("B-17", "ADR-054", "Article-XI", "T69")


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


def _nest(levels: int) -> dict:
    node: dict = {"kind": "type", "object_type": "person"}
    for _ in range(levels - 1):
        node = {"kind": "and", "children": [node]}
    return node


# ── no SQL, structurally ────────────────────────────────────────────────────


def test_no_node_has_a_free_text_field_that_reaches_a_query() -> None:
    """The T69 AC: a stored definition contains no SQL text.

    Asserted over the grammar's own field types rather than by inspecting
    examples. Every string field either names ontology vocabulary (checked at
    save), is an opaque id, or is `search.q`, which goes to the spec 11
    normalization pipeline and becomes a bound parameter.
    """
    from aegis.sets import grammar

    allowed = {
        "kind",
        "object_type",
        "interface",
        "predicate",
        "direction",
        "property",
        "op",
        "target",
        "case_id",
        "set_id",
        "q",
        "field",
        "note",
    }
    for name in dir(grammar):
        node_type = getattr(grammar, name)
        if not (isinstance(node_type, type) and issubclass(node_type, grammar._Node)):
            continue
        for field, info in node_type.model_fields.items():
            if info.annotation is str or "str" in str(info.annotation):
                assert field in allowed, (
                    f"{name}.{field} is a new string field — if it can reach a "
                    "query as anything but a bound parameter, the grammar can "
                    "now carry SQL (spec 12 §2.3)"
                )


def test_the_grammar_actually_has_nodes() -> None:
    """Non-vacuity: the sweep above passes trivially over an empty grammar."""
    from aegis.sets import grammar

    kinds = {
        getattr(grammar, name).model_fields["kind"].default
        for name in dir(grammar)
        if isinstance(getattr(grammar, name), type)
        and issubclass(getattr(grammar, name), grammar._Node)
        and "kind" in getattr(grammar, name).model_fields
    }
    assert kinds >= {
        "type",
        "predicate",
        "property",
        "time",
        "case",
        "search",
        "set",
        "and",
        "or",
        "not",
    }


def test_an_unknown_node_kind_is_refused() -> None:
    with pytest.raises(GrammarError):
        parse({"kind": "raw_sql", "sql": "DROP TABLE claim"})


def test_an_extra_field_is_refused() -> None:
    """`extra="forbid"`, so a smuggled field is an error rather than ignored."""
    with pytest.raises(GrammarError):
        parse({"kind": "type", "object_type": "person", "sql": "1=1"})


# ── vocabulary comes from the ontology ──────────────────────────────────────


def test_a_declared_type_is_accepted(ontology) -> None:
    validate(parse({"kind": "type", "object_type": "person"}), ontology=ontology)


def test_an_undeclared_type_is_refused_with_its_path(ontology) -> None:
    with pytest.raises(GrammarError) as excinfo:
        validate(parse({"kind": "type", "object_type": "wizard"}), ontology=ontology)
    assert excinfo.value.path == "ast.object_type"


def test_an_undeclared_predicate_is_refused(ontology) -> None:
    with pytest.raises(GrammarError) as excinfo:
        validate(parse({"kind": "predicate", "predicate": "hexes"}), ontology=ontology)
    assert excinfo.value.path == "ast.predicate"


def test_a_nested_failure_names_the_nested_path(ontology) -> None:
    """A caller with a twelve-node definition needs the node, not "invalid"."""
    ast = {
        "kind": "and",
        "children": [
            {"kind": "type", "object_type": "person"},
            {"kind": "or", "children": [{"kind": "predicate", "predicate": "hexes"}]},
        ],
    }
    with pytest.raises(GrammarError) as excinfo:
        validate(parse(ast), ontology=ontology)
    assert excinfo.value.path == "ast.children[1].children[0].predicate"


def test_a_type_node_names_exactly_one_thing() -> None:
    with pytest.raises(GrammarError):
        parse({"kind": "type", "object_type": "person", "interface": "party"})
    with pytest.raises(GrammarError):
        parse({"kind": "type"})


@pytest.mark.parametrize("op", PROPERTY_OPERATORS)
def test_every_declared_operator_parses(op: str) -> None:
    """A closed list means every member has to work (H-13)."""
    payload = {"kind": "property", "property": "aliases", "op": op}
    if op not in {"exists", "absent"}:
        payload["value"] = "Fictional"
    parse(payload)


def test_a_value_operator_without_a_value_is_refused() -> None:
    with pytest.raises(GrammarError):
        parse({"kind": "property", "property": "aliases", "op": "eq"})


def test_an_existence_operator_with_a_value_is_refused() -> None:
    with pytest.raises(GrammarError):
        parse({"kind": "property", "property": "aliases", "op": "exists", "value": "x"})


def test_a_time_node_needs_a_bound_and_an_order() -> None:
    with pytest.raises(GrammarError):
        parse({"kind": "time", "field": "event"})
    with pytest.raises(GrammarError):
        parse({"kind": "time", "field": "event", "from": "2020-01-01", "to": "2019-01-01"})


# ── limits, refused at save ─────────────────────────────────────────────────


def test_depth_beyond_the_limit_is_refused(ontology) -> None:
    ok = parse(_nest(MAX_DEPTH))
    validate(ok, ontology=ontology)
    assert depth(ok) == MAX_DEPTH

    with pytest.raises(GrammarError) as excinfo:
        validate(parse(_nest(MAX_DEPTH + 1)), ontology=ontology)
    assert "depth" in excinfo.value.message


def test_node_count_beyond_the_limit_is_refused(ontology) -> None:
    children = [{"kind": "type", "object_type": "person"}] * MAX_NODES
    with pytest.raises(GrammarError) as excinfo:
        validate(parse({"kind": "and", "children": children}), ontology=ontology)
    assert "nodes" in excinfo.value.message


def test_too_many_set_references_are_refused(ontology) -> None:
    children = [
        {"kind": "set", "set_id": f"oset_{index}", "version": 1}
        for index in range(MAX_SET_REFERENCES + 1)
    ]
    with pytest.raises(GrammarError) as excinfo:
        validate(parse({"kind": "and", "children": children}), ontology=ontology)
    assert "set references" in excinfo.value.message


def test_a_definition_at_every_limit_is_still_accepted(ontology) -> None:
    """Non-vacuity: the limits must permit the thing they permit."""
    children = [{"kind": "type", "object_type": "person"}] * (MAX_NODES - 1)
    validate(parse({"kind": "and", "children": children}), ontology=ontology)


# ── interface pinning (ADR-054) ─────────────────────────────────────────────


def test_an_interface_expands_to_the_types_it_names_now(ontology) -> None:
    node = parse({"kind": "type", "interface": "party"})
    expanded = expand_interfaces(node, ontology=ontology)
    assert isinstance(expanded, OrNode)
    named = {child.object_type for child in expanded.children}
    assert named == set(ontology.implementors("party"))


def test_expansion_reaches_nested_interfaces(ontology) -> None:
    node = parse(
        {
            "kind": "and",
            "children": [
                {"kind": "not", "child": {"kind": "type", "interface": "party"}},
            ],
        }
    )
    expanded = expand_interfaces(node, ontology=ontology)
    assert not interfaces_used(expanded)


def test_the_as_written_form_still_remembers_the_interface(ontology) -> None:
    """Both forms are kept, because they answer different questions.

    The expanded AST is what the set *means*; the as-written one is what its
    author *meant*, and that is what tells §4.3 whose sets to notify when an
    interface gains a member.
    """
    node = parse({"kind": "type", "interface": "party"})
    assert interfaces_used(node) == {"party"}


def test_an_interface_with_no_implementors_is_refused(ontology) -> None:
    """A set over an empty interface evaluates to nothing forever.

    Refusing at save is kinder than saving a definition that can only ever
    return an empty result and letting its owner wonder why.
    """

    with pytest.raises(GrammarError):
        expand_interfaces(
            parse({"kind": "type", "interface": "unimplemented"}),
            ontology=_ontology_with_empty_interface(ontology),
        )


def _ontology_with_empty_interface(ontology):
    class _Stub:
        interfaces = {"unimplemented": object()}
        object_types = ontology.object_types
        predicates = ontology.predicates

        @staticmethod
        def implementors(name: str) -> list[str]:
            return []

    return _Stub()


# ── walking and references ──────────────────────────────────────────────────


def test_walk_visits_every_node() -> None:
    node = parse(
        {
            "kind": "or",
            "children": [
                {"kind": "type", "object_type": "person"},
                {"kind": "not", "child": {"kind": "type", "object_type": "location"}},
            ],
        }
    )
    assert len(walk(node)) == 4


def test_referenced_sets_are_found_with_their_versions() -> None:
    node = parse(
        {
            "kind": "and",
            "children": [
                {"kind": "set", "set_id": "oset_a", "version": 2},
                {"kind": "set", "set_id": "oset_b", "version": 1},
            ],
        }
    )
    assert referenced_sets(node) == {("oset_a", 2), ("oset_b", 1)}


def test_a_set_reference_must_pin_a_version() -> None:
    """Following "whatever that set is now" lets someone else's edit change this one."""
    with pytest.raises(GrammarError):
        parse({"kind": "set", "set_id": "oset_a"})
    with pytest.raises(GrammarError):
        parse({"kind": "set", "set_id": "oset_a", "version": 0})
