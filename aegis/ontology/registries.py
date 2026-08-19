"""Code-owned names the ontology is allowed to reference (spec 08 §6.3, §6.5).

A `submission_criteria` entry names a predicate the actions layer evaluates; a
`side_effects` entry names a hook; a `json` parameter names a payload schema.
All three are **code**, so the ontology may only *select* from what exists —
the same allowlist discipline ADR-021 requires of function implementations
(H-13). A criterion that could be declared before it could be enforced would be
a governance rule that silently does nothing.

The names live here rather than in `aegis/actions/` because the ontology loader
validates against them and `aegis.actions` imports the loader — a module-level
import the other way would be a cycle. `aegis/actions/criteria.py` holds the
implementations, and `tests/contract/test_actions_v2.py` asserts the two sets
agree in both directions, so neither can drift.
"""

from __future__ import annotations

#: Predicates the actions layer evaluates before a write (spec 08 §6.3).
#: Phase 3 registered three, each making an *existing* policy declarative rather
#: than inventing a new one. Phase 4 adds the fourth for a rule that had no
#: mechanism at all (spec 09 §3.3). P7's `target_not_sealed` and
#: `within_legal_authority` are added by the phase that implements them.
SUBMISSION_CRITERIA = frozenset(
    {
        "actor_holds_action_role",
        "actor_is_case_member",
        "second_approver_present",
        "required_text_is_substantive",
    }
)

#: Post-commit hooks an action may declare. **Nothing executes these in P3**
#: (spec 08 §6.5): the declarations parse and are stored, and the existing
#: hard-coded refresh paths keep running. The generalized outbox lands with the
#: first action that genuinely needs one.
SIDE_EFFECTS = frozenset({"refresh_projection", "notify"})

#: Schemas a `json` parameter may name. Every one is code-owned: requiring a
#: registered schema id is what stops `json` becoming an escape hatch around a
#: closed list. `suggestion_payload` is per-kind (ADR-031 §1); the two event
#: schemas are `record_event`'s participant and place lists (spec 10 §12), whose
#: elements each become an ordinary claim through the ordinary validator.
PAYLOAD_SCHEMAS = frozenset(
    {"suggestion_payload", "event_participants", "event_places"}
)

# ── geospatial vocabularies (spec 10 §4.2, ADR-048) ─────────────────────────
#
# Code-owned for the same reason `SUBMISSION_CRITERIA` is: the validator and the
# renderer must implement each value, so a value that could be *declared* before
# it could be *honoured* would be a promise nothing keeps (H-13). They are
# platform vocabulary, not domain vocabulary — a second domain gets the same
# ladder, which is why they are not in a module file.
#
# Both are exported to the workspace by `aegis ontology generate`, so no
# geospatial vocabulary is typed into React either.

#: Administrative granularity of a claimed geometry, ordered **coarse → fine**.
#: Generic on purpose: `subdivision` covers a province, state or district
#: without the platform learning any country's hierarchy.
GEO_ADMIN_LEVELS = ("country", "subdivision", "locality", "site")

#: Geometry that is not an administrative unit at all — an instrument fix, a
#: coverage polygon, a route. Not a rung on the ladder, which is why it is not
#: in it: asking whether it is coarser than `locality` has no answer.
GEO_NOT_ADMINISTRATIVE = "not_administrative"

#: Every value `admin_level` may take.
GEO_ADMIN_VALUES = frozenset(GEO_ADMIN_LEVELS) | {GEO_NOT_ADMINISTRATIVE}

#: How a geometry was obtained. The renderer selects its mark from this together
#: with the admin level, the geometry type and the accuracy — never from one
#: overloaded "precision" value, which is the H-21 finding this replaces.
GEO_DERIVATIONS = frozenset(
    {
        "instrument_fix",             # GPS/technical fix with a stated accuracy
        "source_stated_coordinates",  # the source printed coordinates
        "address_match",              # matched to a street address
        "admin_unit_boundary",        # the boundary polygon of a named unit
        "admin_unit_centroid",        # the centre of a named unit — NOT a location
        "coverage_area",              # the area something covers (a cell, a zone)
        "analyst_estimate",           # a reasoned estimate; the reasoning is the excerpt
    }
)

#: Derivations that describe an area rather than a position, so a radius is
#: mandatory: a centroid without one is a pin pretending to be a city
#: (spec 10 §4.3 rule 5).
GEO_DERIVATIONS_REQUIRING_ACCURACY = frozenset(
    {"admin_unit_centroid", "coverage_area"}
)
