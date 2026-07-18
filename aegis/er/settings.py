"""Versioned entity-resolution settings (spec 05 §6).

Every candidate records the settings version that produced it, so a score can
be traced to the configuration that computed it and an evaluation diff can say
*which* change moved the numbers.  A settings change without a rerun of the
T26 evaluation in the same PR is a defect (spec 05 §6).

Bump the version whenever a change alters which candidates are emitted or how
they are ranked.  Never edit a version in place: candidates already carry it.
"""

from __future__ import annotations

#: Deterministic rule engine (:mod:`aegis.er.rules`).
RULES_VERSION = "rules-v1"

#: Same ``norm_key`` inside one document.  Deliberately **not** pre-verified:
#: one document reusing a name is weak evidence on its own — documents list
#: different people with the same common name — so it ranks above cross-document
#: noise and below identifier matches (spec 05 §3.1).
SAME_KEY_IN_DOCUMENT_RULE = "rule:same-norm-key-in-doc"

#: Prefix for the per-identifier rules; the suffix is the ontology predicate,
#: so ``has_nic`` produces ``rule:has_nic``.  The engine never names an
#: identifier itself (Article XIV).
IDENTIFIER_RULE_PREFIX = "rule:"

#: Splink model (:mod:`aegis.er.splink_job`).  Covers the comparison levels,
#: their declared m/u probabilities, and the blocking rules — anything that
#: changes which pairs are scored or how.
SPLINK_VERSION = "splink-v1"
SPLINK_PRODUCER = "splink"

#: Emission threshold, spec 05 §6.  A pair below this is not surfaced at all:
#: review capacity is the scarcest resource in the system, and a queue nobody
#: can finish is a queue nobody reads carefully.  Ratified against the T26
#: golden set at its first passing run; change it only with an eval diff in the
#: same PR.
SPLINK_MATCH_THRESHOLD = 0.80


__all__ = [
    "IDENTIFIER_RULE_PREFIX",
    "RULES_VERSION",
    "SAME_KEY_IN_DOCUMENT_RULE",
    "SPLINK_MATCH_THRESHOLD",
    "SPLINK_PRODUCER",
    "SPLINK_VERSION",
]
