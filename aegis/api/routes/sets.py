"""Object-set routes (spec 06 §2.9, spec 12 §§3–7).

Three properties hold on every route here, and each is a rule from spec 12
rather than a convention of this file.

**An unshared set is absent, not forbidden.** Every check is
`fga_check_or_404`, and the list route returns only what the caller may reach.
A 403 would disclose that a set exists, which is the same leak a non-member 403
would be on a case (spec 06 §2.5).

**Reading a definition and running it are different permissions.** `viewer`
reads the AST — the *question* — and `evaluator` runs it and gets the *answer*.
A set filtering on a restricted identifier discloses that identifier to anyone
who can read it, whatever the evaluation returns (B-17), so the weaker grant
has to be reachable on its own.

**A definition is read at the caller's clearance.** A `property` node above it
comes back shape-intact and value-empty, because deleting the node would
misdescribe the set and showing the value would be the leak.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.api.deps import (
    AuthContext,
    DbSession,
    FGADep,
    OntologyDep,
    authorize,
    fga_check_or_404,
)
from aegis.api.pagination import encode_cursor, page_limit, split_page
from aegis.api.schemas import (
    ObjectSetEvaluationOut,
    ObjectSetIn,
    ObjectSetMemberOut,
    ObjectSetNoticeOut,
    ObjectSetOut,
    ObjectSetPageOut,
    ObjectSetShareIn,
    ObjectSetVersionIn,
    ObjectSetVersionOut,
)
from aegis.audit import append as append_audit
from aegis.sets.evaluation import evaluate_version
from aegis.sets.grammar import GrammarError, parse
from aegis.sets.service import add_version, create_set, share
from aegis.sets.sharing import (
    EDITOR,
    EVALUATOR,
    VIEWER,
    fga_object,
    redact_definition,
)
from aegis.store import ObjectSet, ObjectSetNotice, ObjectSetVersion

router = APIRouter(tags=["object-sets"])


def _set_or_404(session: Session, set_id: str) -> ObjectSet:
    row = session.get(ObjectSet, set_id)
    if row is None:
        raise HTTPException(404, "not found")
    return row


def _latest(session: Session, set_id: str) -> ObjectSetVersion:
    row = session.scalars(
        select(ObjectSetVersion)
        .where(ObjectSetVersion.set_id == set_id)
        .order_by(ObjectSetVersion.version.desc())
        .limit(1)
    ).first()
    if row is None:
        raise HTTPException(404, "not found")
    return row


def _version_out(
    version: ObjectSetVersion, *, ontology, clearance: int
) -> ObjectSetVersionOut:
    """A version as this reader may see it (spec 12 §5.2)."""
    return ObjectSetVersionOut(
        set_id=version.set_id,
        version=version.version,
        ast=redact_definition(parse(version.ast), ontology=ontology, clearance=clearance),
        ontology_version=version.ontology_version,
        track_interface_members=version.track_interface_members,
        as_of=version.as_of,
        as_of_revision=version.as_of_revision,
        note=version.note,
        created_by=version.created_by,
        created_at=version.created_at,
    )


def _readable_set_ids(session: Session, fga, auth: AuthContext) -> set[str]:
    """Which set definitions this caller may read — for the §7 difference rule.

    Computed here rather than trusted from the request, because the rule exists
    to stop a caller learning the shape of a question they were never shown.
    """
    readable: set[str] = set()
    for row in session.scalars(select(ObjectSet)):
        try:
            fga_check_or_404(fga, auth.user, VIEWER, fga_object(row.set_id))
        except HTTPException:
            continue
        readable.add(row.set_id)
    return readable


@router.post("/object-sets", response_model=ObjectSetOut, operation_id="createObjectSet")
def create(
    body: ObjectSetIn,
    session: DbSession,
    ontology: OntologyDep,
    fga: FGADep,
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> ObjectSetOut:
    """Save a definition. Interfaces are pinned here unless tracking is asked for."""
    try:
        row, version = create_set(
            session,
            name=body.name,
            description=body.description,
            ast=body.ast,
            ontology=ontology,
            actor=auth.user.sub,
            case_id=body.case_id,
            track_interface_members=body.track_interface_members,
            note=body.note,
            readable_set_ids=_readable_set_ids(session, fga, auth),
        )
    except GrammarError as exc:
        raise HTTPException(422, f"{exc.path}: {exc.message}") from exc

    append_audit(
        session,
        actor=auth.user.sub,
        action="object_set.create",
        decision="allow",
        purpose=auth.purpose,
        case_id=body.case_id,
        resource_type="object_set",
        resource_id=row.set_id,
        detail={"name": body.name, "version": version.version},
    )
    session.commit()
    return _out(row, version, ontology=ontology, clearance=auth.user.clearance)


def _out(row: ObjectSet, version: ObjectSetVersion, *, ontology, clearance: int) -> ObjectSetOut:
    return ObjectSetOut(
        set_id=row.set_id,
        name=row.name,
        description=row.description,
        case_id=row.case_id,
        owner=row.owner,
        created_at=row.created_at,
        latest=_version_out(version, ontology=ontology, clearance=clearance),
    )


@router.get("/object-sets", response_model=ObjectSetPageOut, operation_id="listObjectSets")
def list_sets(
    session: DbSession,
    ontology: OntologyDep,
    fga: FGADep,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 20,
    auth: AuthContext = Depends(authorize()),
) -> ObjectSetPageOut:
    """Only sets the caller may see. No total — a count is an existence leak.

    Sets the caller cannot reach are **absent**, which is why this filters
    rather than 403s per row: a list with holes in it is a list that answers
    the question it was refusing to answer.
    """
    limit = min(page_limit(limit), 50)
    rows = list(
        session.scalars(select(ObjectSet).order_by(ObjectSet.set_id))
    )
    visible = []
    for row in rows:
        try:
            fga_check_or_404(fga, auth.user, VIEWER, fga_object(row.set_id))
        except HTTPException:
            continue
        if cursor and row.set_id <= cursor:
            continue
        visible.append(row)

    items, next_cursor = split_page(visible, limit, lambda row: row.set_id)
    return ObjectSetPageOut(
        items=[
            _out(row, _latest(session, row.set_id), ontology=ontology, clearance=auth.user.clearance)
            for row in items
        ],
        next_cursor=next_cursor,
    )


@router.get(
    "/object-sets/{set_id}", response_model=ObjectSetOut, operation_id="getObjectSet"
)
def get_set(
    set_id: str,
    session: DbSession,
    ontology: OntologyDep,
    fga: FGADep,
    auth: AuthContext = Depends(authorize()),
) -> ObjectSetOut:
    row = _set_or_404(session, set_id)
    fga_check_or_404(fga, auth.user, VIEWER, fga_object(set_id))
    return _out(
        row, _latest(session, set_id), ontology=ontology, clearance=auth.user.clearance
    )


@router.post(
    "/object-sets/{set_id}/versions",
    response_model=ObjectSetVersionOut,
    operation_id="addObjectSetVersion",
)
def add_set_version(
    set_id: str,
    body: ObjectSetVersionIn,
    session: DbSession,
    ontology: OntologyDep,
    fga: FGADep,
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> ObjectSetVersionOut:
    """An edit is a new version; nothing updates one."""
    _set_or_404(session, set_id)
    fga_check_or_404(fga, auth.user, EDITOR, fga_object(set_id))
    try:
        version = add_version(
            session,
            set_id=set_id,
            ast=body.ast,
            ontology=ontology,
            actor=auth.user.sub,
            track_interface_members=body.track_interface_members,
            note=body.note,
            readable_set_ids=_readable_set_ids(session, fga, auth),
        )
    except GrammarError as exc:
        raise HTTPException(422, f"{exc.path}: {exc.message}") from exc

    append_audit(
        session,
        actor=auth.user.sub,
        action="object_set.version",
        decision="allow",
        purpose=auth.purpose,
        resource_type="object_set",
        resource_id=set_id,
        detail={"version": version.version, "note": body.note},
    )
    session.commit()
    return _version_out(version, ontology=ontology, clearance=auth.user.clearance)


@router.post(
    "/object-sets/{set_id}/evaluate",
    response_model=ObjectSetEvaluationOut,
    operation_id="evaluateObjectSet",
)
def evaluate_set(
    set_id: str,
    session: DbSession,
    ontology: OntologyDep,
    fga: FGADep,
    version: Annotated[int | None, Query(ge=1)] = None,
    auth: AuthContext = Depends(authorize()),
) -> ObjectSetEvaluationOut:
    """Run the set under the **caller's** filters, never the owner's.

    `evaluator` and not `viewer`: running somebody's saved query is the weaker
    disclosure, and a colleague can be given the answer without being given the
    question (spec 12 §5.2).
    """
    _set_or_404(session, set_id)
    fga_check_or_404(fga, auth.user, EVALUATOR, fga_object(set_id))

    row = (
        session.get(ObjectSetVersion, (set_id, version))
        if version is not None
        else _latest(session, set_id)
    )
    if row is None:
        raise HTTPException(404, "not found")

    result = evaluate_version(session, row, user=auth.user, ontology=ontology)
    session.commit()
    return ObjectSetEvaluationOut(
        set_id=set_id,
        version=row.version,
        members=[
            ObjectSetMemberOut(
                entity_id=member.entity_id,
                label=member.label,
                entity_type=member.entity_type,
            )
            for member in result.members
        ],
        truncated=result.truncated,
        evaluation_digest=result.evaluation_digest,
    )


@router.post(
    "/object-sets/{set_id}/share",
    response_model=ObjectSetOut,
    operation_id="shareObjectSet",
)
def share_set(
    set_id: str,
    body: ObjectSetShareIn,
    session: DbSession,
    ontology: OntologyDep,
    fga: FGADep,
    auth: AuthContext = Depends(authorize("analyst", "investigator")),
) -> ObjectSetOut:
    """Grant or revoke, audited with what was shared and with whom.

    An audit row saying "shared" without naming the grant answers no question
    anybody will later ask (spec 12 §5.2 rule 3).
    """
    row = _set_or_404(session, set_id)
    fga_check_or_404(fga, auth.user, EDITOR, fga_object(set_id))
    if body.relation not in {VIEWER, EDITOR, EVALUATOR}:
        raise HTTPException(422, f"unknown relation {body.relation!r}")

    tuple_ = share(
        session,
        set_id=set_id,
        user_sub=body.user_sub,
        relation=body.relation,
        op="delete" if body.revoke else "write",
    )
    append_audit(
        session,
        actor=auth.user.sub,
        action="object_set.revoke" if body.revoke else "object_set.share",
        decision="allow",
        purpose=auth.purpose,
        resource_type="object_set",
        resource_id=set_id,
        detail={"grant": tuple_},
    )
    session.commit()
    return _out(
        row, _latest(session, set_id), ontology=ontology, clearance=auth.user.clearance
    )


@router.get(
    "/object-sets/{set_id}/notices",
    response_model=list[ObjectSetNoticeOut],
    operation_id="listObjectSetNotices",
)
def list_notices(
    set_id: str,
    session: DbSession,
    fga: FGADep,
    auth: AuthContext = Depends(authorize()),
) -> list[ObjectSetNoticeOut]:
    """Interface growth this set's owner should know about (spec 12 §4.3).

    Delivered to pinned and tracking sets alike: a tracking set changed, a
    pinned set could have, and finding that out is as useful as finding out it
    did.
    """
    _set_or_404(session, set_id)
    fga_check_or_404(fga, auth.user, VIEWER, fga_object(set_id))
    rows = session.scalars(
        select(ObjectSetNotice)
        .where(ObjectSetNotice.set_id == set_id)
        .order_by(ObjectSetNotice.created_at.desc(), ObjectSetNotice.notice_id)
    )
    return [
        ObjectSetNoticeOut(
            notice_id=row.notice_id,
            set_id=row.set_id,
            version=row.version,
            interface=row.interface,
            member=row.member,
            ontology_version=row.ontology_version,
            tracking=row.tracking,
            created_at=row.created_at,
        )
        for row in rows
    ]
