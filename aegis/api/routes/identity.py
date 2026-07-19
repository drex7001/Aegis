"""Identity routes: ER candidates, and the decisions humans make about them.

Nothing here changes identity on its own. Every write goes through
``ActionService.adjudicate_identity`` with the caller as ``decided_by`` — a
producer proposes, a person decides (ADR-027, Article VII). The candidate
table is read-only from this module's point of view; a candidate's disposition
moves only as a consequence of a decision, never because a route set it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Float, Integer, and_, case, cast, not_, or_, select
from sqlalchemy.orm import aliased

from aegis.actions import ActionContext, ActionService, ActionValidationError
from aegis.api.deps import AuthContext, DbSession, OntologyDep, authorize
from aegis.api.pagination import decode_cursor, encode_cursor, page_limit, split_page
from aegis.api.schemas import (
    BatchConfirmIn,
    BatchConfirmOut,
    BatchSkipOut,
    CandidateListOut,
    CandidateMentionOut,
    CandidateOut,
    DecisionIn,
    DecisionOut,
    IdentityDecisionOut,
)
from aegis.er.adjudication import AdjudicationResult, StaleRevisionError
from aegis.er.ledger import active_revision_id
from aegis.authz.filters import (
    allowed_handling_codes,
    forbidden_field_predicates,
    hidden_entity_types,
)
from aegis.store import Entity, ErCandidate, IdentityMembership, Mention, SourceRecord

router = APIRouter(tags=["identity"])


def _side(mention: Mention, entity: Entity | None) -> CandidateMentionOut:
    return CandidateMentionOut(
        mention_id=mention.mention_id,
        record_id=mention.record_id,
        raw_text=mention.raw_text,
        norm_key=mention.norm_key,
        script=mention.script,
        language=mention.language,
        entity_id=entity.entity_id if entity is not None else None,
        entity_label=entity.label if entity is not None else None,
    )


def _decision_out(result: AdjudicationResult) -> DecisionOut:
    return DecisionOut(
        decision=IdentityDecisionOut.model_validate(result.decision),
        moved_mentions=list(result.moved_mentions),
        surviving_entity_id=result.surviving_entity_id,
        new_entity_id=result.new_entity_id,
        unattributable_claims=list(result.unattributable_claims),
    )


@router.get(
    "/identity/candidates",
    response_model=CandidateListOut,
    operation_id="listIdentityCandidates",
)
def list_candidates(
    session: DbSession,
    ontology: OntologyDep,
    disposition: Annotated[str | None, Query()] = None,
    producer: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 50,
    auth: AuthContext = Depends(authorize("analyst")),
) -> CandidateListOut:
    """Machine-proposed pairs with their full explanation (spec 06 §2.2)."""
    mention_a, mention_b = aliased(Mention), aliased(Mention)
    member_a, member_b = aliased(IdentityMembership), aliased(IdentityMembership)
    entity_a, entity_b = aliased(Entity), aliased(Entity)
    record_a, record_b = aliased(SourceRecord), aliased(SourceRecord)
    limit = page_limit(limit)
    key = decode_cursor(cursor, "identity-candidates", 3)
    # Numeric key for NULLS LAST that can also be used in the keyset predicate.
    score_key = case(
        (ErCandidate.score.is_(None), -1.0),
        else_=cast(ErCandidate.score, Float),
    )
    pre_key = cast(ErCandidate.pre_verified, Integer)

    query = (
        select(ErCandidate, mention_a, mention_b, entity_a, entity_b)
        .join(mention_a, mention_a.mention_id == ErCandidate.mention_a)
        .join(mention_b, mention_b.mention_id == ErCandidate.mention_b)
        .join(record_a, record_a.record_id == mention_a.record_id)
        .join(record_b, record_b.record_id == mention_b.record_id)
        # Joined rather than resolved per row: an inbox page is 50-200
        # candidates, and a helper call per side is 400 round trips to render
        # one screen. The partial unique index on an open membership is what
        # makes the join safe — at most one row can match each side.
        .outerjoin(
            member_a,
            and_(
                member_a.mention_id == ErCandidate.mention_a,
                member_a.closed_revision_id.is_(None),
            ),
        )
        .outerjoin(
            member_b,
            and_(
                member_b.mention_id == ErCandidate.mention_b,
                member_b.closed_revision_id.is_(None),
            ),
        )
        .outerjoin(entity_a, entity_a.entity_id == member_a.entity_id)
        .outerjoin(entity_b, entity_b.entity_id == member_b.entity_id)
        .where(
            record_a.handling_code.in_(
                allowed_handling_codes(ontology, auth.user.clearance)
            ),
            record_b.handling_code.in_(
                allowed_handling_codes(ontology, auth.user.clearance)
            ),
        )
        .order_by(
            # The pre-verified band first, because it is the one an analyst can
            # act on in bulk. Then strongest first — `nulls_last` is load
            # bearing: Postgres sorts NULLs first under DESC, which would file
            # every rule candidate (which computes no score at all) above the
            # highest-scoring probabilistic one.
            pre_key.desc(),
            score_key.desc(),
            # ties broken by key so paging stays stable when T24c adds a cursor
            ErCandidate.candidate_id,
        )
        .limit(limit + 1)
    )
    hidden_types = hidden_entity_types(ontology, auth.user.clearance)
    if hidden_types:
        query = query.where(
            or_(entity_a.entity_id.is_(None), not_(entity_a.entity_type.in_(hidden_types))),
            or_(entity_b.entity_id.is_(None), not_(entity_b.entity_type.in_(hidden_types))),
        )
    forbidden = forbidden_field_predicates(ontology, auth.user.clearance)
    if forbidden:
        feature_predicate = ErCandidate.features["predicate"].astext
        query = query.where(
            not_(ErCandidate.producer.in_([f"rule:{name}" for name in forbidden])),
            or_(feature_predicate.is_(None), not_(feature_predicate.in_(forbidden))),
        )
    if key is not None:
        try:
            pre_verified = bool(int(key[0]))
            score = float(key[1])
            candidate_id = str(key[2])
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "invalid cursor") from exc
        query = query.where(
            or_(
                pre_key < int(pre_verified),
                and_(pre_key == int(pre_verified), score_key < score),
                and_(
                    pre_key == int(pre_verified),
                    score_key == score,
                    ErCandidate.candidate_id > candidate_id,
                ),
            )
        )
    if disposition is not None:
        query = query.where(ErCandidate.disposition == disposition)
    if producer is not None:
        query = query.where(ErCandidate.producer == producer)

    rows = list(session.execute(query))
    candidates = [
        CandidateOut(
            candidate_id=candidate.candidate_id,
            mention_a=_side(row_mention_a, row_entity_a),
            mention_b=_side(row_mention_b, row_entity_b),
            producer=candidate.producer,
            producer_version=candidate.producer_version,
            graph_snapshot_id=candidate.graph_snapshot_id,
            score=float(candidate.score) if candidate.score is not None else None,
            features=candidate.features,
            pre_verified=candidate.pre_verified,
            disposition=candidate.disposition,
            created_at=candidate.created_at,
        )
        for candidate, row_mention_a, row_mention_b, row_entity_a, row_entity_b in rows
    ]
    items, next_cursor = split_page(
        candidates,
        limit,
        lambda candidate: encode_cursor(
            "identity-candidates",
            [
                int(candidate.pre_verified),
                candidate.score if candidate.score is not None else -1.0,
                candidate.candidate_id,
            ],
        ),
    )
    return CandidateListOut(
        revision_id=active_revision_id(session),
        candidates=items,
        next_cursor=next_cursor,
    )


@router.post(
    "/identity/decisions",
    response_model=DecisionOut,
    status_code=201,
    operation_id="recordIdentityDecision",
)
def record_decision(
    body: DecisionIn,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("analyst")),
) -> DecisionOut:
    """Confirm, reject, split or mark unresolved — one action, one ledger row.

    A stale ``parent_revision_id`` in the same entity scope raises
    ``StaleRevisionError``, which the app's error handler renders as a 409
    carrying the intervening decisions.
    """
    service = ActionService(session, ontology)
    # The union has already validated that this mode carries the arguments its
    # handler needs, so what is left after the shared fields *is* the handler's
    # parameter set.
    params = body.model_dump(
        exclude={"mode", "parent_revision_id", "note", "protected_person"}
    )
    result = service.adjudicate_identity(
        ActionContext(
        actor=auth.user.sub, purpose=auth.purpose, roles=frozenset(auth.user.roles)
    ),
        mode=body.mode,
        parent_revision_id=body.parent_revision_id,
        note=body.note,
        protected_person=body.protected_person,
        **params,
    )
    session.commit()
    return _decision_out(result)


@router.post(
    "/identity/candidates/batch-confirm",
    response_model=BatchConfirmOut,
    operation_id="batchConfirmCandidates",
)
def batch_confirm(
    body: BatchConfirmIn,
    session: DbSession,
    ontology: OntologyDep,
    auth: AuthContext = Depends(authorize("analyst")),
) -> BatchConfirmOut:
    """Confirm a pre-verified band — one ledger decision per pair (ADR-027).

    Not one decision covering many pairs: each pair gets its own decision, its
    own revision and its own audit row, so a later reviewer can reverse one
    merge without unpicking the batch it arrived in.
    """
    service = ActionService(session, ontology)
    context = ActionContext(
        actor=auth.user.sub, purpose=auth.purpose, roles=frozenset(auth.user.roles)
    )
    confirmed: list[DecisionOut] = []
    skipped: list[BatchSkipOut] = []

    rows = {
        candidate.candidate_id: candidate
        for candidate in session.scalars(
            select(ErCandidate).where(ErCandidate.candidate_id.in_(body.candidate_ids))
        )
    }
    for candidate_id in body.candidate_ids:
        candidate = rows.get(candidate_id)
        if candidate is None:
            skipped.append(BatchSkipOut(candidate_id=candidate_id, reason="not found"))
            continue
        if not candidate.pre_verified:
            skipped.append(
                BatchSkipOut(
                    candidate_id=candidate_id,
                    reason="not in the pre-verified band — decide this pair on its own",
                )
            )
            continue
        if candidate.disposition != "open":
            skipped.append(
                BatchSkipOut(
                    candidate_id=candidate_id,
                    reason=f"already {candidate.disposition}",
                )
            )
            continue
        try:
            result = service.adjudicate_identity(
                context,
                mode="confirm_match",
                parent_revision_id=body.parent_revision_id,
                note=body.note,
                mention_a=candidate.mention_a,
                mention_b=candidate.mention_b,
                candidate_id=candidate.candidate_id,
            )
        except (ActionValidationError, StaleRevisionError) as exc:
            # Each confirm runs in its own SAVEPOINT, so a refusal rolls back
            # that pair alone and the rest of the batch is unaffected. Two
            # pairs sharing an entity is the ordinary case: the first advances
            # the revision the second was computed against, and saying so is
            # more useful than failing the batch or quietly merging anyway.
            skipped.append(BatchSkipOut(candidate_id=candidate_id, reason=str(exc)))
            continue
        confirmed.append(_decision_out(result))

    session.commit()
    return BatchConfirmOut(confirmed=confirmed, skipped=skipped)
