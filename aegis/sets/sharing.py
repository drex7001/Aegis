"""Grants, and the definition as protected data (T70, spec 12 §5).

B-17's observation about sets is easy to skim past and is the sharpest thing in
the finding: *"a shared set definition can reveal hidden identifiers even if
results are filtered."* A set filtering on `has_nic = '…'` discloses that
identifier to everyone it is shared with, **whatever the evaluation returns**.
The results are filtered; the question is not.

So this module treats a definition as data with a clearance, and it separates
two permissions that look like one:

| Grant | Lets you |
|---|---|
| `evaluator` | run the set — get the answer |
| `viewer` | read the definition — see the question |
| `editor` | write a new version |

`viewer` implies `evaluator`; the reverse is deliberately false. "Run the
analyst's saved query" and "read what the analyst was looking for" are
different disclosures, and a colleague can be given the first without the
second.

A `property` node above the reader's clearance comes back **shape-intact and
value-empty** — `{property, op, value: null, withheld: true}`. Removing the node
would misdescribe the set (its evaluation still uses it); showing the value
would be the leak. Saying "there is a condition here you may not read" is the
only honest third option.
"""

from __future__ import annotations

from typing import Any

from aegis.authz.filters import property_sensitivity
from aegis.ontology import Ontology
from aegis.sets.grammar import (
    FilterNode,
    GrammarError,
    NotNode,
    SetNode,
    walk,
)

#: FGA relations on the `object_set` type (infra/fga/model.fga).
VIEWER = "viewer"
EDITOR = "editor"
EVALUATOR = "evaluator"


def fga_object(set_id: str) -> str:
    return f"object_set:{set_id}"


def grant_tuple(user_sub: str, relation: str, set_id: str) -> dict[str, str]:
    return {"user": f"user:{user_sub}", "relation": relation, "object": fga_object(set_id)}


def redact_definition(
    node: FilterNode, *, ontology: Ontology, clearance: int
) -> dict[str, Any]:
    """A definition as this reader may see it (spec 12 §5.2 rule 1).

    Field sensitivity is resolved the same way a claim's is — through
    `property_sensitivity`, which reads the ontology's declaration first
    (ADR-047). A set and a claim disclosing the same property must disclose it
    under the same rule, or the set becomes the softer path to the same value.
    """
    payload = node.model_dump(mode="json", by_alias=True)
    return _redact(payload, ontology=ontology, clearance=clearance)


def _redact(payload: dict[str, Any], *, ontology: Ontology, clearance: int) -> dict[str, Any]:
    kind = payload.get("kind")
    if kind == "property":
        sensitivity = _property_sensitivity(ontology, payload["property"])
        if sensitivity is not None and ontology.handling_rank(sensitivity) > clearance:
            return {**payload, "value": None, "withheld": True}
        return payload
    if kind in {"and", "or"}:
        return {
            **payload,
            "children": [
                _redact(child, ontology=ontology, clearance=clearance)
                for child in payload["children"]
            ],
        }
    if kind == "not":
        return {
            **payload,
            "child": _redact(payload["child"], ontology=ontology, clearance=clearance),
        }
    return payload


def _property_sensitivity(ontology: Ontology, name: str) -> str | None:
    """The clearance a property demands, however it is declared.

    A `property` node names a *property*, while `property_sensitivity` answers
    for a *predicate*. Most property predicates use the property name directly,
    so asking it first is right; the declared-property sweep below catches the
    rest, including identifiers whose predicate is a verb (`has_nic`).
    """
    direct = property_sensitivity(ontology, name)
    if direct is not None:
        return direct
    declared = {
        spec.sensitivity
        for object_type in ontology.object_types.values()
        for property_name, spec in object_type.properties.items()
        if property_name == name and spec.sensitivity is not None
    }
    return max(declared, key=ontology.handling_rank) if declared else None


def refuse_undisclosable_difference(
    node: FilterNode, *, readable_set_ids: set[str]
) -> None:
    """A `not` over a set whose definition the caller cannot read is refused.

    Spec 12 §7. `difference` is the sharpest tool in the grammar: *"everything
    in Ayesha's set that is not in mine"* evaluates fine and discloses nothing
    by itself — but run once per candidate, it is a definition-disclosure
    oracle. The author learns the shape of a question they were never shown.

    Refused **at save**, so the oracle never exists, rather than rate-limited at
    evaluation, which would only make it slower.

    Composition itself stays allowed: negating a set you *can* read tells you
    nothing you did not already know.
    """
    for path, item in walk(node):
        if not isinstance(item, NotNode):
            continue
        for _, inner in walk(item.child):
            if isinstance(inner, SetNode) and inner.set_id not in readable_set_ids:
                raise GrammarError(
                    path,
                    f"cannot negate set {inner.set_id}: its definition is not "
                    "readable to you, and difference over an unreadable set is a "
                    "disclosure oracle (spec 12 §7)",
                )


def referenced_set_ids(node: FilterNode) -> set[str]:
    return {item.set_id for _, item in walk(node) if isinstance(item, SetNode)}


__all__ = [
    "EDITOR",
    "EVALUATOR",
    "VIEWER",
    "fga_object",
    "grant_tuple",
    "redact_definition",
    "referenced_set_ids",
    "refuse_undisclosable_difference",
]
