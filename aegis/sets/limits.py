"""Complexity limits for object-set definitions (spec 12 §2.2, B-17).

B-17's objection is that a filter grammar with no cost model is a denial of
service with a friendly UI: *"recursive composition can cause denial of
service"*. Every number here answers that, and every one is enforced **at save**
rather than at evaluation.

Saving is where the check belongs. A limit enforced at run time turns a bad
definition into a slow request that fails differently every time, and it leaves
the bad definition sitting in the database being shared. A limit enforced at
save turns it into a `422` naming the offending path, before anybody can act on
it.

The numbers are code-owned so spec 12 §2.2's table and the enforcement are the
same numbers, and `tests/contract/test_object_set_limits.py` fails if the two
disagree.
"""

from __future__ import annotations

#: How deeply boolean nodes may nest. Deeper than this is unreadable, and an
#: unreadable set cannot be reviewed before it is shared — which matters here
#: because sharing a set is disclosing its definition (spec 12 §5.2).
MAX_DEPTH = 8

#: Total nodes in one definition.
MAX_NODES = 64

#: Direct `set` references from one definition.
MAX_SET_REFERENCES = 8

#: How far composition may recurse. A set of sets of sets is a query language,
#: not a filter, and the difference matters because each level multiplies the
#: work an evaluation does under one snapshot (M-16).
MAX_COMPOSITION_DEPTH = 3

#: Objects one evaluation may return. Above this the evaluation reports
#: `truncated` and **refuses to feed an analytic run**: a metric computed over
#: a truncated set is a metric about the truncation, and a finding carrying it
#: would be wrong in a way its caveat does not cover (Article IX).
MAX_EVALUATED_OBJECTS = 50_000

#: One statement timeout per evaluation, in milliseconds.
STATEMENT_TIMEOUT_MS = 10_000


__all__ = [
    "MAX_COMPOSITION_DEPTH",
    "MAX_DEPTH",
    "MAX_EVALUATED_OBJECTS",
    "MAX_NODES",
    "MAX_SET_REFERENCES",
    "STATEMENT_TIMEOUT_MS",
]
