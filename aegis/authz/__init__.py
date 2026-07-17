"""Authorization adapter: OpenFGA client + SQL row-filter builders (T12, spec 03)."""

from aegis.authz.fga import FGAClient, FGAError, Tuple3
from aegis.authz.filters import allowed_handling_codes, claim_filters, member_case_ids
from aegis.authz.outbox import (
    RebuildReport,
    SyncReport,
    desired_tuples,
    rebuild,
    sync,
)

__all__ = [
    "FGAClient",
    "FGAError",
    "RebuildReport",
    "SyncReport",
    "Tuple3",
    "allowed_handling_codes",
    "claim_filters",
    "desired_tuples",
    "member_case_ids",
    "rebuild",
    "sync",
]
