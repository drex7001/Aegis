"""Finding → claim promotion (T74, spec 12 §10).

The line this crosses is the one Article IX draws. A **finding** is a machine's
reading of what has been written down; a **claim** is somebody's assertion about
the world. Promotion turns the first into the second, so it happens the way
every other machine output reaches canon — as a typed suggestion a human
decides on. Article VII is not relaxed because the producer is deterministic.

Three rules, and the third is the one that is easy to get backwards.

**A rationale is required.** The finding already says what was computed; what
the reviewer adds is *why it is worth asserting*, and a promotion with no
reasoning is a number being laundered into an assertion.

**The claim's `record_id` is the finding's own source chain**, never an invented
one (H-23 says so explicitly). A finding computed over claims from several
records promotes against the record the promoter names as the basis — and if
they name none, the promotion is refused rather than attributed to a record
that did not say it.

**The finding is not consumed.** It stays, immutable, and gains a pointer to
the claim it became the basis of. Promoting twice is refused: two assessed
claims from one computation would read as two independent assessments, which is
the double-counting Article IX exists to prevent.

## On `analytic_basis`

Spec 12 §10 originally said the link was "a `claim_relation` of kind
`analytic_basis`". T74 found that unbuildable and, on inspection, wrong:
`claim_relation` has `from_claim` and `to_claim`, both foreign keys to `claim`,
and its `relation` is constrained to `corroborates`/`contradicts` — the
claim-to-claim epistemic relations Article VIII is about. A finding is not a
claim, so it cannot go in either column, and widening the constraint would have
made "this claim relates to that claim" mean two different things.

The link already existed and is one-directional on purpose:
`analytic_finding.promoted_claim_id`. The spec is corrected rather than the
schema.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, ActionValidationError
from aegis.actions.service import suggestion_idempotency_key
from aegis.store import AnalyticFinding, AnalyticRun, Claim, ReviewQueue

#: What the review queue records as the producer of a promotion. Named for the
#: act rather than for a model, because the "producer" here is a person deciding
#: that a computation is worth asserting.
PRODUCER = "finding-promotion"


class PromotionError(ValueError):
    """A promotion that cannot be proposed, with a reason a caller can act on."""


def promote_finding(
    session: Session,
    *,
    finding_id: str,
    subject_id: str,
    predicate: str,
    record_id: str,
    rationale: str,
    actor: str,
    roles: frozenset[str],
    ontology,
    object_id: str | None = None,
    object_value=None,
    analytic_confidence: str | None = None,
    purpose: str | None = None,
) -> ReviewQueue:
    """Propose a finding as an assessed claim. Writes a suggestion, never a claim.

    Returns the queue row. Nothing canonical exists until a reviewer accepts it,
    and the reviewer is the actor on the claim that results (ADR-031 §2) — so
    the person who proposed and the person who decided are both in the record,
    and they may be different people.
    """
    finding = session.get(AnalyticFinding, finding_id)
    if finding is None:
        raise PromotionError(f"finding {finding_id!r} does not exist")
    if finding.promoted_claim_id is not None:
        raise PromotionError(
            f"finding {finding_id} has already been promoted to claim "
            f"{finding.promoted_claim_id}; one finding, one assessed claim"
        )
    if not rationale or not rationale.strip():
        raise PromotionError(
            "a promotion needs a rationale: the finding says what was computed, "
            "and the reviewer has to say why it is worth asserting"
        )
    if session.get(Claim, record_id) is not None:
        raise PromotionError("record_id names a claim, not a source record")

    pending = session.query(ReviewQueue).filter(
        ReviewQueue.suggestion_kind == "finding_promotion",
        ReviewQueue.status == "suggested",
    )
    for row in pending:
        if (row.producer_meta or {}).get("finding_id") == finding_id:
            raise PromotionError(
                f"finding {finding_id} is already awaiting review as "
                f"{row.suggestion_id}"
            )

    run = session.get(AnalyticRun, finding.run_id)
    service = ActionService(session, ontology)
    try:
        return service.submit_suggestion(
            ActionContext(actor=actor, roles=roles, purpose=purpose),
            suggestion_kind="finding_promotion",
            payload={
                "subject_id": subject_id,
                "predicate": predicate,
                "object_id": object_id,
                "object_value": object_value,
                "record_id": record_id,
                # An assessment, and the ontology's own vocabulary for one
                # (`assessed`, not "assessment" — spec 12 §0 O7).
                "assertion_type": "assessed",
                "analytic_confidence": analytic_confidence,
                "collection_method": "analytic",
                # The finding's handling code travels with it: an assertion
                # derived from restricted evidence is restricted.
                "handling_code": finding.handling_code,
            },
            producer=PRODUCER,
            producer_version=run.method_version if run else "unknown",
            producer_meta={
                # The basis link. Read at acceptance to set
                # `promoted_claim_id`, which is what makes the finding the
                # claim's recorded analytic basis rather than a footnote.
                "finding_id": finding_id,
                "run_id": finding.run_id,
                "finding_type": finding.finding_type,
                "finding_digest": finding.finding_digest,
                "rationale": rationale.strip(),
                # Copied, not referenced: the reviewer must see the caveat the
                # finding was issued with, at the moment they decide whether to
                # turn it into an assertion.
                "caveat_text": finding.caveat_text,
                "caveat_version": finding.caveat_version,
            },
            record_id=record_id,
            # The rationale is part of the key, which is a governance choice
            # rather than a detail. The default key digests the *payload*, so
            # two promotions of one finding with the same subject and
            # predicate collide however differently they were argued — and a
            # promotion rejected once could never be re-proposed on better
            # reasoning.
            #
            # Including the rationale makes the rule the one worth having:
            # **the same argument, already rejected, cannot be resubmitted; a
            # new argument can.** A reviewer who said no to "central to the
            # harbour movements" is not thereby saying no to every future case
            # anybody might make from the same finding.
            idempotency_key=suggestion_idempotency_key(
                kind="finding_promotion",
                producer=PRODUCER,
                producer_version=run.method_version if run else "unknown",
                payload={
                    "finding_id": finding_id,
                    "subject_id": subject_id,
                    "predicate": predicate,
                    "object_id": object_id,
                    "object_value": object_value,
                    "rationale": rationale.strip(),
                },
            ),
        )
    except ActionValidationError as exc:
        raise PromotionError(f"{exc.path}: {exc.message}") from exc


__all__ = ["PRODUCER", "PromotionError", "promote_finding"]
