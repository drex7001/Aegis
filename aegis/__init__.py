"""Aegis platform core (speckit/plan.md §3).

Layering (GOAL.md §37): domain is pure; actions/queries orchestrate; adapters
(store, evidence, authz) touch infrastructure. No domain module may import an
infrastructure library.
"""

__version__ = "0.1.0"
