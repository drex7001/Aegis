"""Provenance routes — "why connected?" (T21; GOAL.md §18, specs/06 §2.1).

These are read routes over the claim store, not over the projection: the
projection is a cache that answers *what* is connected, and this answers *why*,
which must come from canonical claims (Article XIII — the cache is never the
authority for evidence).

Authorization conditions are passed into the query so filtered claims never
enter the result set. Counts and the identity line are therefore computed over
exactly what this caller may see — a panel reporting evidence it then refuses
to show would leak the existence of the claims behind it (specs/03 §4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.schemas import (
    ClaimOut,
    ClaimProvenanceOut,
    GradingOut,
    IdentityDecisionOut,
    MentionOut,
    SourceOut,
    SourceRecordOut,
    WhyConnectedOut,
)
from aegis.authz.filters import claim_filters
from aegis.queries.provenance import (
    ClaimProvenance,
    IdentityLine,
    claim_provenance,
    identity_history,
    why_connected,
)

router = APIRouter(tags=["provenance"])


def _claim_out(entry: ClaimProvenance) -> ClaimProvenanceOut:
    claim = entry.claim
    return ClaimProvenanceOut(
        claim=ClaimOut.model_validate(claim),
        grading=GradingOut(
            # Reliability is graded on the source, not the claim: repeating a
            # claim does not make its source more reliable.
            reliability=entry.source.reliability_normalized if entry.source else None,
            credibility=claim.credibility_normalized,
            verification=claim.verification_status,
            analytic_confidence=claim.analytic_confidence,
        ),
        source=SourceOut.model_validate(entry.source) if entry.source else None,
        record=SourceRecordOut.model_validate(entry.record) if entry.record else None,
        corroborated_by=entry.corroborated_by,
        contradicted_by=entry.contradicted_by,
        subject_mention=(
            MentionOut.model_validate(entry.subject_mention)
            if entry.subject_mention
            else None
        ),
        object_mention=(
            MentionOut.model_validate(entry.object_mention)
            if entry.object_mention
            else None
        ),
    )


def _decision_out(line: IdentityLine) -> IdentityDecisionOut:
    out = IdentityDecisionOut.model_validate(line.decision)
    out.entity_id = line.entity_id or None
    return out


@router.get(
    "/entities/{entity_id}/why-connected/{other_id}",
    response_model=WhyConnectedOut,
    operation_id="whyConnected",
)
def get_why_connected(
    entity_id: str,
    other_id: str,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize()),
) -> WhyConnectedOut:
    """Every claim this caller may see connecting two entities, with evidence."""
    result = why_connected(
        session,
        subject_id=entity_id,
        object_id=other_id,
        filters=claim_filters(session, auth.user, ontology),
    )
    if result is None:
        raise HTTPException(404, "not found")

    claims = [_claim_out(entry) for entry in result.claims]
    # Distinct relations, not a sum over claims: two claims on one edge that
    # contradict each other are one disagreement, and inflating that number
    # would misinform exactly the reader who came here to judge the edge.
    contradictions = {
        frozenset({entry.claim.claim_id, other})
        for entry in result.claims
        for other in entry.contradicted_by
    }
    corroborations = {
        frozenset({entry.claim.claim_id, other})
        for entry in result.claims
        for other in entry.corroborated_by
    }
    return WhyConnectedOut(
        subject_id=result.subject_id,
        object_id=result.object_id,
        resolved_subject_id=result.resolved_subject_id,
        resolved_object_id=result.resolved_object_id,
        claims=claims,
        record_count=result.record_count,
        contradiction_count=len(contradictions),
        corroboration_count=len(corroborations),
        identity_line=[_decision_out(line) for line in result.identity_line],
        truncated=result.truncated,
    )


@router.get(
    "/claims/{claim_id}/provenance",
    response_model=ClaimProvenanceOut,
    operation_id="claimProvenance",
)
def get_claim_provenance(
    claim_id: str,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize()),
) -> ClaimProvenanceOut:
    """Generic provenance for any claim-derived value (B-14).

    Property values, aliases and edge labels all resolve to a claim, so one
    route serves every "where did this come from?" in the UI.
    """
    entry = claim_provenance(
        session,
        claim_id=claim_id,
        filters=claim_filters(session, auth.user, ontology),
    )
    if entry is None:
        raise HTTPException(404, "not found")  # absent and unauthorized look alike
    return _claim_out(entry)


@router.get(
    "/entities/{entity_id}/identity-history",
    response_model=list[IdentityDecisionOut],
    operation_id="identityHistory",
)
def get_identity_history(
    entity_id: str,
    session: DbSession,
    auth: AuthContext = Depends(authorize()),
) -> list[IdentityDecisionOut]:
    """The decision line behind an entity: who merged or split it, when, why.

    Not gated on claim visibility: a decision records an adjudication, not the
    content of any source. Its note is written by the reviewer for exactly this
    audience (Article V, specs/06 §2.2).
    """
    lines = identity_history(session, entity_id=entity_id)
    if lines is None:
        raise HTTPException(404, "not found")
    return [_decision_out(line) for line in lines]
