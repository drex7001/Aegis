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
    "listCases": (set(), False),
    "getCase": (set(), False),
    "closeCase": ({"supervisor"}, False),
    "addCaseMember": ({"supervisor"}, False),
    "removeCaseMember": ({"supervisor"}, False),
    "listCaseMembers": (set(), False),
    # References grant nothing (ADR-044), so linking is an ordinary case-scoped
    # write: the authorization is cheap precisely because the operation is
    # powerless. The FGA relation (`can_edit`) is what scopes it, and that is
    # exercised in the integration suite.
    "listCaseReferences": (set(), False),
    "linkCaseReference": ({"analyst", "investigator"}, False),
    "unlinkCaseReference": ({"analyst", "investigator"}, False),
    # Hypotheses and tasks have no authorization of their own: every one of
    # these resolves through its case (spec 09 §5), and a non-member gets 404
    # from writes as well as reads.
    "openHypothesis": ({"analyst", "investigator"}, False),
    "listHypotheses": (set(), False),
    "getHypothesis": (set(), False),
    "reviseHypothesis": ({"analyst", "investigator"}, False),
    "linkHypothesisClaim": ({"analyst", "investigator"}, False),
    "unlinkHypothesisClaim": ({"analyst", "investigator"}, False),
    "openTask": ({"analyst", "investigator"}, False),
    "listTasks": (set(), False),
    "updateTask": ({"analyst", "investigator"}, False),
    "createClaim": ({"analyst", "investigator"}, False),
    # An event *is* claims (ADR-046), so it is gated exactly as recording one:
    # the same roles, the same case check, and no privilege of its own. A
    # narrower or wider gate here would mean an occurrence could be asserted by
    # someone who may not assert its parts.
    "recordEvent": ({"analyst", "investigator"}, False),
    "getClaim": (set(), False),
    "claimProvenance": (set(), False),
    "linkClaim": ({"analyst"}, False),
    "retractClaim": ({"analyst", "supervisor"}, False),
    "getEntity": (set(), False),
    # The map is not a side door (spec 10 §7.1). Both geo routes are ordinary
    # authenticated reads — no role of their own, because a viewer who may
    # read a claim may see where it says something happened, and one who may
    # not sees neither.
    "geoLocations": (set(), False),
    "geoEvents": (set(), False),
    # Same gate for the same reason: the timeline answers "what happened and
    # when" through the same filter as the map answers "and where".
    "getTimeline": (set(), False),
    "listEntityCases": (set(), False),
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
    "search": (set(), False),
    # Object sets (T71). Reads carry no role because the FGA relation is the
    # authorization: `viewer` reads the definition, `evaluator` only runs it,
    # and every check is 404-on-failure so an unshared set is absent rather
    # than forbidden (spec 12 §5.1).
    # Analytics (T72). Running a metric is the one read here that *records*,
    # so it takes a purpose: a recorded answer outlives the question and gets
    # forwarded to people who never saw the query (ADR-057, Article X).
    "runAnalytic": ({"analyst"}, True),
    "listFindings": (set(), False),
    # Promotion is a human act crossing from a machine reading to an
    # assertion, so it takes a purpose too (spec 12 §10).
    "promoteFinding": ({"analyst"}, True),
    "getFinding": (set(), False),
    "createObjectSet": ({"analyst", "investigator"}, False),
    "listObjectSets": (set(), False),
    "getObjectSet": (set(), False),
    "addObjectSetVersion": ({"analyst", "investigator"}, False),
    "evaluateObjectSet": (set(), False),
    "shareObjectSet": ({"analyst", "investigator"}, False),
    "listObjectSetNotices": (set(), False),
    "listSourceRecords": ({"analyst"}, False),
    # `False` is the truth about the **gate**, and is not the whole story:
    # T67 makes purpose mandatory *conditionally*, when the record's handling
    # code ranks above the first one the ontology declares (spec 11 §7). The
    # gate cannot express "sometimes", so the route enforces it and
    # `tests/integration/test_purpose_capture.py` is where it is proved.
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
