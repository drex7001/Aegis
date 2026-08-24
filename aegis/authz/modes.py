"""Response modes — the policy that decides what a caller is told about what
they were not shown (T79, spec 03 §6, ADR-061, ADR-067).

H-25 found a contradiction that was real. Spec 03 §4 rule 4 says a row the
caller may not read is **absent**; the pre-amendment Phase 7 plan said a field
the caller may not read is **marked**. Both are right somewhere and neither is
right everywhere, and until this module there was no artifact that chose.

There are exactly three modes and there is no fourth:

===========  ===============================================================
``omit``     absence. The caller learns nothing
``marked``   the caller is told a predicate is withheld — never its value,
             its count, its grading or its id (ADR-061)
``counts``   how many were withheld, by reason. Disclosure only, and only
             against an explicit grant (spec 13 §10)
===========  ===============================================================

**A marker is derived from the ontology, not from the rows** (ADR-067). On a
marked surface the marker set is a function of ``(object type, clearance)``
alone: the predicates that type declares whose *property sensitivity* exceeds
the caller's clearance. That is exactly what ``GET /v1/ontology/vocabulary``
already tells them, so a marker discloses nothing new — which is why it needs no
per-surface risk analysis before being shown.

**Handling-code withholding is never marked.** A claim somebody recorded as
``sensitive`` is absent, for everyone below it, everywhere. That rule has held
since Phase 1 and this module does not soften it. The distinction matters
because the two look identical from the renderer and are not remotely the same
disclosure: one repeats the schema, the other reveals that a particular row
exists.

There is **one** row-derived marker in the system, it is named here rather than
left as a local behaviour, and it is geometry existence — see ``GEOMETRY_EXISTENCE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aegis.authz.filters import forbidden_field_predicates
from aegis.ontology import Ontology

ResponseMode = Literal["omit", "marked", "counts"]

#: Marker kinds a surface may emit. A surface's `marks` set is empty unless its
#: mode is `marked` or `counts`, and a contract test asserts that.
PROPERTY_SENSITIVITY = "property_sensitivity"
"""Schema-derived: "this type declares a predicate you may not read."

Safe on any surface, because the ontology is already readable.
"""

GEOMETRY_EXISTENCE = "geometry_existence"
"""Row-derived, and the only one: "a geometry is recorded here that you may not
read" — `geometry_state = 'none_permitted'`, shipped at P5 T59.

It is an exception to ADR-067's rule and is kept rather than removed, for the
reason spec 10 §7.3 gave: on a map, *listed without a pin* and *not known to
exist* are conclusions an analyst draws visually, and collapsing them tells a
low-clearance viewer that nobody has recorded where something is. `geometry`
declares no `sensitivity` (the claim's handling code is what varies), so there
is no schema fact to derive a marker from — the choice is this marker or none.

It discloses existence, which is why it is written down here, tested, and not
generalised to other predicates.
"""

SET_FILTER_VALUE = "set_filter_value"
"""A saved set's filter value, withheld while the node stays shape-intact —
`{property, op, value: null, withheld: true}` (T70, `aegis.sets.sharing`).

Shipped before this policy existed. The policy adopts the shape rather than
inventing a second vocabulary for the same idea.
"""

REDACTION_REASONS = "redaction_reasons"
"""A disclosure package's redaction log: reason, resource and count, never a
value, an id, or a compartment name (spec 13 §5)."""


@dataclass(frozen=True)
class SurfacePolicy:
    """One row of spec 03 §6.2, as data rather than as prose in a review."""

    #: The read surface's id in the spec 03 §12.1 inventory.
    surface: str
    mode: ResponseMode
    #: Marker kinds this surface may emit. Empty for `omit`.
    marks: frozenset[str]
    #: Why this surface has this mode. Read at the next argument about it.
    why: str
    #: Set when the mode is declared ahead of the route that will honour it, so
    #: "declared but unrouted" is a stated fact rather than a silent gap.
    pending_task: str | None = None


def _policy(
    surface: str,
    mode: ResponseMode,
    why: str,
    *marks: str,
    pending_task: str | None = None,
) -> SurfacePolicy:
    return SurfacePolicy(
        surface=surface,
        mode=mode,
        marks=frozenset(marks),
        why=why,
        pending_task=pending_task,
    )


#: The policy table. One row per read surface in spec 03 §12.1, keyed by the
#: same id. `tests/contract/test_response_modes.py` fails when the two disagree
#: in either direction — a surface with no policy, or a policy for a surface
#: that does not exist.
POLICY: dict[str, SurfacePolicy] = {
    surface.surface: surface
    for surface in (
        _policy(
            "entity_object_view",
            "marked",
            "The caller is authorized to know the schema of the object they are "
            "looking at. An unmarked gap reads as 'nothing recorded', which is a "
            "different and false statement",
            PROPERTY_SENSITIVITY,
        ),
        _policy(
            "entity_related",
            "omit",
            "Identity history, case lists and why-connected answer questions about "
            "relationships, not about an object's schema",
        ),
        _policy(
            "claim_detail",
            "omit",
            "The row either is readable or is not; there is no schema to disclose "
            "separately from the value",
        ),
        _policy(
            "provenance",
            "omit",
            "Provenance is the claim's evidence. A marker here would name a source "
            "for a claim the caller cannot read",
        ),
        _policy(
            "search",
            "omit",
            "Exploratory. A marker on a search page is an index of what exists but "
            "is hidden (GOAL.md §30)",
        ),
        _policy(
            "graph",
            "omit",
            "An edge held up by one open and one restricted claim must look exactly "
            "like an edge held up by the open claim alone",
        ),
        _policy(
            "analytics",
            "omit",
            "A finding is computed from the claims the caller may read; there is no "
            "partial finding to mark",
        ),
        _policy(
            "object_set_definition",
            "marked",
            "Removing the node would misdescribe the set, whose evaluation still "
            "uses it; showing the value would be the leak (T70)",
            SET_FILTER_VALUE,
        ),
        _policy(
            "object_set_evaluation",
            "omit",
            "An evaluation is a list of objects. A filter the evaluator may not read "
            "is refused outright rather than evaluated to a wrong answer (§6.3)",
        ),
        _policy(
            "geo",
            "marked",
            "A place listed without a pin and a place nobody has located are "
            "different facts, and on a map the reader draws the conclusion visually",
            PROPERTY_SENSITIVITY,
            GEOMETRY_EXISTENCE,
        ),
        _policy(
            "timeline",
            "omit",
            "Same argument as search: a marked gap on a time axis points at when "
            "something happened",
        ),
        _policy(
            "alerts",
            "omit",
            "An alert whose firing claims are unreadable is absent, not redacted "
            "(T75)",
        ),
        _policy(
            "watchlists",
            "omit",
            "Owner-scoped; a watchlist runs at its owner's clearance and is not "
            "shared (spec 12 §11.3)",
        ),
        _policy(
            "investigation",
            "omit",
            "Cases, hypotheses and tasks answer 404 for a non-member on writes as "
            "well as reads — a marker would be the existence leak that closes "
            "(spec 09 §5)",
        ),
        _policy(
            "source_records",
            "omit",
            "A record is governed by its own handling code and judicial state; a "
            "marker would advertise a sealed record",
        ),
        _policy(
            "sources",
            "omit",
            "A source row carries no handling code — its records do — so there is "
            "nothing here to withhold and nothing to mark",
        ),
        _policy(
            "evidence",
            "omit",
            "Custody and case membership decide; an unauthorized item is a 404",
        ),
        _policy(
            "review_queue",
            "omit",
            "Queue visibility keys on the source record's handling code; a marker "
            "would name work the caller cannot see",
        ),
        _policy(
            "identity_candidates",
            "omit",
            "A candidate names two mentions. Marking one would name a mention "
            "reached through a claim the caller may not read",
        ),
        _policy(
            "audit",
            "marked",
            "The auditor is authorized to know that an event occurred even where "
            "its detail is compartmented",
            PROPERTY_SENSITIVITY,
            pending_task="T80 — nothing is compartmented until compartments exist",
        ),
        _policy(
            "disclosure_preview",
            "counts",
            "A preview shows categories and counts, never values (GOAL.md §24) — "
            "the disclosure officer needs to assess completeness before deciding",
            REDACTION_REASONS,
            pending_task="T83",
        ),
        _policy(
            "disclosure_package",
            "counts",
            "The recipient is a disclosure counterparty assessing completeness, "
            "which is the privilege the grant confers (spec 13 §10)",
            REDACTION_REASONS,
            pending_task="T83",
        ),
    )
}


class ModeError(KeyError):
    """A surface with no policy row.

    Raised rather than defaulted. Defaulting to `omit` would be the safe answer
    and the wrong mechanism: a new read surface must be *registered*, and a
    default is how it stops being.
    """


def policy_for(surface: str) -> SurfacePolicy:
    try:
        return POLICY[surface]
    except KeyError:
        raise ModeError(
            f"no response-mode policy for read surface {surface!r} — register it "
            "in spec 03 §6.2 and in aegis.authz.modes.POLICY"
        ) from None


def mode_for(surface: str) -> ResponseMode:
    return policy_for(surface).mode


def withheld_predicates(
    ontology: Ontology, object_type: str, clearance: int
) -> list[str]:
    """The schema-derived marker set for one object type at one clearance.

    A function of the ontology and the number, and of nothing in the database —
    which is the whole of ADR-067. Two entities of the same type produce the
    same list for the same reader whether either has a restricted claim or not,
    so a marker can never be read as evidence that one does.
    """
    forbidden = set(forbidden_field_predicates(ontology, clearance))
    if not forbidden:
        return []
    return sorted(
        name
        for name, predicate in ontology.predicates.items()
        if name in forbidden and object_type in ontology.expand_types(predicate.subject)
    )


__all__ = [
    "GEOMETRY_EXISTENCE",
    "POLICY",
    "PROPERTY_SENSITIVITY",
    "REDACTION_REASONS",
    "SET_FILTER_VALUE",
    "ModeError",
    "ResponseMode",
    "SurfacePolicy",
    "mode_for",
    "policy_for",
    "withheld_predicates",
]
