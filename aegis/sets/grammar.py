"""The object-set filter grammar: a validated AST, never SQL (spec 12 §2, B-17).

B-17 asks for a **validated AST, never raw SQL**, with depth, node, cycle and
cardinality limits. This module is the AST and the validation; `compile.py`
turns one into a query and is the only place SQL is constructed.

Three properties hold by construction rather than by discipline:

**No node can carry SQL.** There is no free-text field anywhere in the grammar.
A `property` node names a property the ontology declares and an operator from a
closed list; a `search` node carries a query string that goes to the spec 11
pipeline, which treats it as text and never as syntax. There is nothing for an
injection to inject into, because nothing here is ever concatenated.

**Every leaf names ontology vocabulary**, checked against the composed registry
at save time (Article XI). A predicate the ontology does not declare is a `422`
naming the failing path, exactly as a claim write is — the same error shape, for
the same reason.

**Interfaces are expanded at save, not at read.** ADR-054: a pinned set records
what its interfaces meant when it was written, so a domain module landing later
cannot silently widen a saved analytic or a watchlist rule. `track_interface_members`
opts out, explicitly, per version.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aegis.ontology import Ontology
from aegis.sets.limits import (
    MAX_DEPTH,
    MAX_NODES,
    MAX_SET_REFERENCES,
)


class GrammarError(ValueError):
    """A definition the grammar refuses, with the path that refused it.

    Carries `path` for the same reason `ActionValidationError` does: an error
    that says "invalid" without saying *where* makes a caller guess, and a
    guessing caller edits the wrong node.
    """

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


#: Comparisons a `property` node may make. Closed, and small on purpose: every
#: operator here has to compile to a parameterized comparison, and an operator
#: nobody can compile would be a promise the grammar cannot keep (H-13).
PROPERTY_OPERATORS = ("eq", "neq", "contains", "exists", "absent")

#: Which end of a claim the object sits at.
DIRECTIONS = ("subject", "object", "either")

#: Time fields a `time` node may filter on. `event` is when something happened,
#: `validity` is when an assertion was true, and they are different questions —
#: which is why the graph filters one and the map the other (spec 10 §11.2).
TIME_FIELDS = ("event", "validity", "recorded")


class _Node(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TypeNode(_Node):
    """Membership in an object type or an interface."""

    kind: Literal["type"] = "type"
    object_type: str | None = None
    interface: str | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> "TypeNode":
        if bool(self.object_type) == bool(self.interface):
            raise ValueError("a type node names exactly one of object_type, interface")
        return self


class PredicateNode(_Node):
    """The object has a claim with this predicate."""

    kind: Literal["predicate"] = "predicate"
    predicate: str
    direction: Literal["subject", "object", "either"] = "either"
    #: An entity id at the far end, when the filter is "connected to *that*".
    target: str | None = None


class PropertyNode(_Node):
    """A claim-derived property comparison.

    `value` is `Any` because a property may be text, a number or a date — and
    is **never** interpolated: `compile.py` binds it as a parameter, so its type
    is a matter of comparison semantics, not of safety.
    """

    kind: Literal["property"] = "property"
    property: str
    op: Literal["eq", "neq", "contains", "exists", "absent"] = "eq"
    value: Any = None

    @model_validator(mode="after")
    def value_matches_operator(self) -> "PropertyNode":
        if self.op in {"exists", "absent"}:
            if self.value is not None:
                raise ValueError(f"{self.op} takes no value")
        elif self.value is None:
            raise ValueError(f"{self.op} requires a value")
        return self


class TimeNode(_Node):
    kind: Literal["time"] = "time"
    field: Literal["event", "validity", "recorded"] = "event"
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def bounded_and_ordered(self) -> "TimeNode":
        if self.from_ is None and self.to is None:
            raise ValueError("a time node needs at least one bound")
        if self.from_ and self.to and self.to < self.from_:
            raise ValueError("to is before from")
        return self


class CaseNode(_Node):
    """Recorded in this case's scope.

    Filtering by case is **not** authorization: `claim_filters` decides what the
    caller may read, and this narrows within that. A set naming a case the
    caller cannot see evaluates to nothing rather than to an error, because an
    error would disclose that the case exists (spec 06 §2.5).
    """

    kind: Literal["case"] = "case"
    case_id: str


class SearchNode(_Node):
    """Free text, through the spec 11 pipeline.

    The one node carrying a string a user typed. It reaches `search_keys` and
    then a bound parameter; it never reaches a query as syntax.
    """

    kind: Literal["search"] = "search"
    q: str = Field(min_length=1, max_length=200)


class SetNode(_Node):
    """Composition: the members of another set, at a pinned version."""

    kind: Literal["set"] = "set"
    set_id: str
    #: Pinned. A composition that followed "whatever that set is now" would let
    #: someone else's edit change the meaning of this definition (ADR-054).
    version: int = Field(ge=1)


class AndNode(_Node):
    kind: Literal["and"] = "and"
    children: list["FilterNode"] = Field(min_length=1)


class OrNode(_Node):
    kind: Literal["or"] = "or"
    children: list["FilterNode"] = Field(min_length=1)


class NotNode(_Node):
    kind: Literal["not"] = "not"
    child: "FilterNode"


FilterNode = Annotated[
    Union[
        TypeNode,
        PredicateNode,
        PropertyNode,
        TimeNode,
        CaseNode,
        SearchNode,
        SetNode,
        AndNode,
        OrNode,
        NotNode,
    ],
    Field(discriminator="kind"),
]

AndNode.model_rebuild()
OrNode.model_rebuild()
NotNode.model_rebuild()


class _Root(BaseModel):
    """Parsing wrapper, so a bare dict can be validated against the union."""

    model_config = ConfigDict(extra="forbid")
    node: FilterNode


def parse(payload: dict[str, Any]) -> FilterNode:
    """A dict to an AST, or `GrammarError` naming where it went wrong."""
    try:
        return _Root.model_validate({"node": payload}).node
    except Exception as exc:  # pydantic raises its own type
        raise GrammarError("ast", str(exc)) from exc


def walk(node: FilterNode, path: str = "ast") -> list[tuple[str, FilterNode]]:
    """Every node with the path that reaches it, depth first."""
    found = [(path, node)]
    if isinstance(node, (AndNode, OrNode)):
        for index, child in enumerate(node.children):
            found += walk(child, f"{path}.children[{index}]")
    elif isinstance(node, NotNode):
        found += walk(node.child, f"{path}.child")
    return found


def depth(node: FilterNode) -> int:
    if isinstance(node, (AndNode, OrNode)):
        return 1 + max(depth(child) for child in node.children)
    if isinstance(node, NotNode):
        return 1 + depth(node.child)
    return 1


def validate(node: FilterNode, *, ontology: Ontology) -> None:
    """Every leaf names declared vocabulary, and the shape is within limits.

    Raises the first `GrammarError` it finds rather than collecting: a
    definition with one bad node is one edit away from valid, and a list of
    twelve consequential errors from a single typo is noise.
    """
    _check_limits(node)
    for path, item in walk(node):
        _check_leaf(path, item, ontology)


def _check_limits(node: FilterNode) -> None:
    nodes = walk(node)
    if len(nodes) > MAX_NODES:
        raise GrammarError("ast", f"{len(nodes)} nodes exceeds the limit of {MAX_NODES}")
    measured = depth(node)
    if measured > MAX_DEPTH:
        raise GrammarError("ast", f"depth {measured} exceeds the limit of {MAX_DEPTH}")
    references = [item for _, item in nodes if isinstance(item, SetNode)]
    if len(references) > MAX_SET_REFERENCES:
        raise GrammarError(
            "ast",
            f"{len(references)} set references exceeds the limit of "
            f"{MAX_SET_REFERENCES}",
        )


def _check_leaf(path: str, node: FilterNode, ontology: Ontology) -> None:
    if isinstance(node, TypeNode):
        if node.object_type and node.object_type not in ontology.object_types:
            raise GrammarError(
                f"{path}.object_type", f"{node.object_type!r} is not a declared type"
            )
        if node.interface and node.interface not in ontology.interfaces:
            raise GrammarError(
                f"{path}.interface", f"{node.interface!r} is not a declared interface"
            )
    elif isinstance(node, PredicateNode):
        if node.predicate not in ontology.predicates:
            raise GrammarError(
                f"{path}.predicate", f"{node.predicate!r} is not a declared predicate"
            )
    elif isinstance(node, PropertyNode):
        declared = {
            name
            for object_type in ontology.object_types.values()
            for name in object_type.properties
        }
        if node.property not in declared:
            raise GrammarError(
                f"{path}.property", f"{node.property!r} is not a declared property"
            )


def expand_interfaces(node: FilterNode, *, ontology: Ontology) -> FilterNode:
    """Freeze every `interface` into the types it names right now (ADR-054).

    This is what "pinned" means mechanically. The saved AST holds an `or` over
    the members, so the definition keeps meaning what it meant even after a
    domain module adds an implementor — and a reader of the stored definition
    can see exactly which types it covers rather than having to resolve an
    interface against a version they may not have.
    """
    if isinstance(node, TypeNode) and node.interface:
        members = sorted(ontology.implementors(node.interface))
        if not members:
            raise GrammarError(
                "ast.interface",
                f"{node.interface!r} has no implementors to pin; a set over an "
                "empty interface would evaluate to nothing forever",
            )
        return OrNode(
            children=[TypeNode(object_type=member) for member in members]
        )
    if isinstance(node, AndNode):
        return AndNode(
            children=[expand_interfaces(c, ontology=ontology) for c in node.children]
        )
    if isinstance(node, OrNode):
        return OrNode(
            children=[expand_interfaces(c, ontology=ontology) for c in node.children]
        )
    if isinstance(node, NotNode):
        return NotNode(child=expand_interfaces(node.child, ontology=ontology))
    return node


def interfaces_used(node: FilterNode) -> set[str]:
    """Which interfaces a definition names, before expansion.

    Kept even for a pinned set, because §4.3 sends the owner a notice when a
    composition bump adds a member to an interface their set uses — pinned or
    tracking. Finding out your set *could* have widened is as useful as finding
    out that it did.
    """
    return {
        item.interface
        for _, item in walk(node)
        if isinstance(item, TypeNode) and item.interface
    }


def referenced_sets(node: FilterNode) -> set[tuple[str, int]]:
    return {
        (item.set_id, item.version)
        for _, item in walk(node)
        if isinstance(item, SetNode)
    }


__all__ = [
    "AndNode",
    "CaseNode",
    "DIRECTIONS",
    "FilterNode",
    "GrammarError",
    "NotNode",
    "OrNode",
    "PROPERTY_OPERATORS",
    "PredicateNode",
    "PropertyNode",
    "SearchNode",
    "SetNode",
    "TIME_FIELDS",
    "TimeNode",
    "TypeNode",
    "depth",
    "expand_interfaces",
    "interfaces_used",
    "parse",
    "referenced_sets",
    "validate",
    "walk",
]
