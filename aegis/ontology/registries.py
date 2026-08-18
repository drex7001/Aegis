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

#: Schemas a `json` parameter may name. Exactly one exists, deliberately:
#: `submit_suggestion.payload` is per-kind and code-owned (ADR-031 §1), and
#: requiring a registered schema id is what stops `json` becoming an escape
#: hatch around the closed suggestion-kind list.
PAYLOAD_SCHEMAS = frozenset({"suggestion_payload"})
