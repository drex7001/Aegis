"""Executable role/purpose half of specs/06's route authorization matrix."""

from __future__ import annotations

import pytest

from aegis.api import create_app
from aegis.api.deps import GATE_MARKER, GATE_PURPOSE, GATE_ROLES, _dependency_calls

pytestmark = pytest.mark.requirement("Article-VI", "B-14", "T24b")


# Empty means any authenticated platform user. Object relations and row/field
# dimensions are exercised in integration/system tests; this table pins the
# RBAC and purpose declaration for every P2 operation in one place.
EXPECTED = {
    "queryAudit": ({"auditor"}, True),
    "verifyAudit": ({"auditor", "admin"}, False),
    "openCase": ({"analyst", "investigator"}, True),
    "getCase": (set(), False),
    "addCaseMember": ({"supervisor"}, False),
    "removeCaseMember": ({"supervisor"}, False),
    "createClaim": ({"analyst", "investigator"}, False),
    "getClaim": (set(), False),
    "claimProvenance": (set(), False),
    "linkClaim": ({"analyst"}, False),
    "retractClaim": ({"analyst", "supervisor"}, False),
    "getEntity": (set(), False),
    "identityHistory": (set(), False),
    "whyConnected": (set(), False),
    "registerEvidence": ({"investigator", "evidence_officer"}, False),
    "getEvidence": (set(), False),
    "addCustodyEvent": (set(), False),
    "expandGraph": (set(), False),
    "graphPaths": (set(), False),
    "listIdentityCandidates": ({"analyst"}, False),
    "batchConfirmCandidates": ({"analyst"}, False),
    "recordIdentityDecision": ({"analyst"}, False),
    "landFile": ({"analyst", "investigator"}, False),
    "landText": ({"analyst", "investigator"}, False),
    "getOntologyVocabulary": (set(), False),
    "rebuildProjections": ({"admin"}, False),
    "listSuggestions": ({"analyst"}, False),
    "acceptSuggestion": ({"analyst"}, False),
    "rejectSuggestion": ({"analyst"}, False),
    "searchEntities": (set(), False),
    "listSourceRecords": ({"analyst"}, False),
    "getSourceRecord": (set(), False),
    "listDerivatives": ({"analyst"}, False),
    "extractRecord": ({"analyst"}, False),
    "releaseSourceRecord": ({"supervisor"}, False),
    "listSources": ({"analyst"}, False),
    "createSource": ({"analyst"}, False),
}


def test_every_shipped_operation_matches_the_authoritative_matrix() -> None:
    actual = {}
    routes = []
    for entry in create_app().routes:
        original = getattr(entry, "original_router", None)
        routes.extend(original.routes if original is not None else [entry])
    for route in routes:
        operation_id = getattr(route, "operation_id", None)
        dependant = getattr(route, "dependant", None)
        if operation_id is None or dependant is None:
            continue
        gates = [
            call
            for call in _dependency_calls(dependant)
            if getattr(call, GATE_MARKER, False)
        ]
        assert len(gates) == 1, operation_id
        gate = gates[0]
        actual[operation_id] = (
            set(getattr(gate, GATE_ROLES)),
            bool(getattr(gate, GATE_PURPOSE)),
        )

    assert actual == EXPECTED
