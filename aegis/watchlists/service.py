"""Creating, sweeping and triaging watchlists (T75, spec 12 §11, ADR-056).

**Evaluation is explicit.** `aegis watchlists evaluate` runs the rules; nothing
on the write path fires a watchlist. ADR-056 gives the reason: the side-effect
outbox spec 08 §6.5 declares is not executed by anything, and giving one feature
a private hook would make the second one harder rather than easier. A watchlist
is a standing query, and running a standing query on a schedule is the ordinary
shape of the thing.

The cost of that choice is stated rather than hidden: **detection latency is the
sweep interval.** What it buys is that a window nobody evaluated is a visible
gap in `analytic_run` rather than silence — you can ask "when was this last
swept, and through what?" and get an answer, which is not a question a
write-path hook can answer at all.

## Idempotence is in the schema, not in the sweep

`uq_watchlist_alert_dedupe` over `(watchlist_id, rule_version, matched_value,
entity_id)`. A re-run over an overlapping window cannot produce a second alert
even if the watermark is wrong, because the database refuses it — rather than
because the sweep remembered correctly.

## Whose eyes the sweep uses

The **owner's** (spec 12 §11.3), which is the one place a saved artifact runs
with its owner's clearance rather than the caller's. An alert nobody may read is
not an alert. The clearance is snapshotted on the watchlist at creation, because
there is no user table to look one up from offline — see `Watchlist`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegis.analytics.manifest import (
    Manifest,
    authorization_digest,
    code_version,
    edge_digest,
    settings_digest,
)
from aegis.analytics.service import METHOD_VERSION, _handling_for
from aegis.api.auth import UserContext
from aegis.audit import append as append_audit
from aegis.authz.filters import claim_filters, member_case_ids
from aegis.er.ledger import active_revision_id
from aegis.ids import new_id
from aegis.ontology import Ontology
from aegis.sets.evaluation import evaluate_version, evaluation_digest
from aegis.store import (
    AnalyticRun,
    Claim,
    ObjectSet,
    ObjectSetVersion,
    Watchlist,
    WatchlistAlert,
)
from aegis.watchlists.rules import (
    EXACT,
    EXACT_IDENTIFIER,
    RULES,
    RULE_VERSION,
    dedupe_key,
)

#: What the sweep records itself as in `analytic_run.method`. Not one of
#: `METRICS`: a sweep is not a metric, records no `analytic_finding`, and is not
#: reachable from `POST /v1/analytics/{metric}`. It shares the manifest because
#: reproducibility is the same problem (ADR-055), not because it shares a route.
METHOD = "watchlist_sweep"

TRIAGE_STATUSES = ("new", "reviewing", "closed")


class WatchlistError(ValueError):
    """A watchlist that cannot be created or swept, with an actionable reason."""


def create_watchlist(
    session: Session,
    *,
    name: str,
    set_id: str,
    rule: str,
    user: UserContext,
    set_version: int | None = None,
) -> Watchlist:
    """Pin a set version and record who the sweep will run as.

    The version is **pinned**, like a saved analytic's (ADR-054): a membership
    rule that widens later must not silently widen a watchlist. `owner` and
    `owner_clearance` come from the creator's own token, so a watchlist can
    never be created to run at a clearance its creator did not have.
    """
    if rule not in RULES:
        raise WatchlistError(f"{rule!r} is not a rule (have: {list(RULES)})")
    if not name or not name.strip():
        raise WatchlistError("a watchlist needs a name")

    obj = session.get(ObjectSet, set_id)
    if obj is None:
        raise WatchlistError(f"object set {set_id!r} does not exist")

    if set_version is None:
        set_version = session.scalar(
            select(ObjectSetVersion.version)
            .where(ObjectSetVersion.set_id == set_id)
            .order_by(ObjectSetVersion.version.desc())
            .limit(1)
        )
    if set_version is None:
        raise WatchlistError(f"object set {set_id} has no versions to pin")

    watchlist = Watchlist(
        watchlist_id=new_id("wl"),
        name=name.strip(),
        set_id=set_id,
        set_version=set_version,
        rule=rule,
        rule_version=RULE_VERSION,
        owner=user.sub,
        owner_clearance=user.clearance,
    )
    session.add(watchlist)
    session.flush()
    return watchlist


def _owner_context(watchlist: Watchlist) -> UserContext:
    """The eyes the sweep uses.

    Roles do not enter `claim_filters` except for the auditor exemption, which a
    sweep must not take; the clearance and case membership are what it reads.
    """
    return UserContext(
        sub=watchlist.owner,
        username=watchlist.owner,
        roles=frozenset({"analyst"}),
        clearance=watchlist.owner_clearance,
        claims={},
    )


def last_evaluated_through(session: Session, watchlist_id: str) -> datetime | None:
    """The watermark to resume from, read from the **runs**.

    Deliberately not a column on the watchlist. "A window that was never
    evaluated is a visible gap in the runs" is only literally true if the runs
    are where the answer lives; a denormalized field would be a second source
    that can disagree with them.
    """
    return session.scalar(
        select(AnalyticRun.evaluated_through)
        .where(
            AnalyticRun.method == METHOD,
            AnalyticRun.parameters["watchlist_id"].astext == watchlist_id,
            AnalyticRun.evaluated_through.is_not(None),
        )
        .order_by(AnalyticRun.evaluated_through.desc())
        .limit(1)
    )


def _watched_values(
    session: Session,
    watchlist: Watchlist,
    *,
    user: UserContext,
    ontology: Ontology,
) -> tuple[dict[str, set[str]], str]:
    """The identifier values held by the set's members, under the owner's eyes.

    Composed from `claim_filters` rather than reading `claim` bare — the mistake
    `shared_identifier` shipped with, and the third instance Phase 6 found of
    one module selecting entities without the shared filter. B-17's rule
    applies here too: what the owner may not read is absent from the scan, so a
    value they cannot see never becomes a value the watchlist watches.
    """
    version = session.scalar(
        select(ObjectSetVersion).where(
            ObjectSetVersion.set_id == watchlist.set_id,
            ObjectSetVersion.version == watchlist.set_version,
        )
    )
    if version is None:
        raise WatchlistError(
            f"watchlist {watchlist.watchlist_id} pins {watchlist.set_id} "
            f"v{watchlist.set_version}, which does not exist"
        )
    evaluation = evaluate_version(session, version, user=user, ontology=ontology)
    members = [member.entity_id for member in evaluation.members]
    # The digest of what the *owner's* evaluation returned, which is what the
    # manifest has to record: two sweeps of one watchlist under different
    # memberships are different sweeps, and without this on the run they would
    # read as the system contradicting itself. Taken from the evaluation rather
    # than recomputed, so it is the same number the set route would report.
    digest = evaluation.evaluation_digest or evaluation_digest(members)
    if not members:
        return {}, digest

    identifiers = [
        name for name, spec in ontology.predicates.items() if spec.identifier
    ]
    if not identifiers:
        return {}, digest

    rows = session.execute(
        select(Claim.predicate, Claim.object_value).where(
            Claim.subject_id.in_(members),
            Claim.predicate.in_(identifiers),
            Claim.object_value.is_not(None),
            *claim_filters(session, user, ontology),
        )
    )
    watched: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        watched[row.predicate].add(str(row.object_value))
    return dict(watched), digest


def evaluate_watchlist(
    session: Session,
    watchlist: Watchlist,
    *,
    ontology: Ontology,
    now: datetime | None = None,
) -> tuple[AnalyticRun, list[WatchlistAlert]]:
    """Sweep one watchlist and record the run, whether or not anything fired.

    The run is written **first** and always, for the reason `run_metric` gives:
    a sweep that found nothing and a sweep that never happened must not look the
    same, or "when was this last evaluated" has no answer.
    """
    if watchlist.rule != EXACT_IDENTIFIER:
        raise WatchlistError(f"{watchlist.rule!r} has no implementation")

    # The **database's** clock, not the process's. `claim.recorded_at` is a
    # server default, so a window boundary taken from Python is compared against
    # timestamps generated somewhere else — and on any skew a claim recorded
    # moments ago falls outside a window that should contain it. That is a
    # flaky sweep, which is worse than a slow one: it looks like the rule not
    # matching.
    now = now or session.scalar(select(func.now()))
    since = last_evaluated_through(session, watchlist.watchlist_id)
    user = _owner_context(watchlist)

    # The set is evaluated **before** the manifest, because its digest is an
    # input to the manifest — the same order `run_metric` uses for a set-driven
    # metric. The run is still written before any detection happens, which is
    # the part that matters: a sweep that crashed halfway is visible as a sweep.
    watched, digest = _watched_values(
        session, watchlist, user=user, ontology=ontology
    )

    manifest = Manifest(
        method=METHOD,
        method_version=METHOD_VERSION,
        implementation="builtin",
        parameters={
            "watchlist_id": watchlist.watchlist_id,
            "rule": watchlist.rule,
            "rule_version": watchlist.rule_version,
            "set_id": watchlist.set_id,
            "set_version": watchlist.set_version,
            "window_from": since.isoformat() if since else None,
            "window_to": now.isoformat(),
        },
        seed=None,
        input_kind="object_set",
        object_set_id=watchlist.set_id,
        object_set_version=watchlist.set_version,
        evaluation_digest=digest,
        # A sweep reads `claim`, never the edge projection: an identifier lives
        # in `object_value` and never becomes an edge.
        edge_digest=edge_digest([]),
        projection_built_at_revision_id=None,
        projection_builder_version=None,
        projection_aggregation_method_version=None,
        ontology_version=ontology.version,
        identity_revision_id=active_revision_id(session),
        code_version=code_version(),
        settings_digest=settings_digest(),
        actor=watchlist.owner,
        purpose=f"watchlist sweep: {watchlist.name}",
        authorization_digest=authorization_digest(
            user, member_case_ids(session, user)
        ),
        caveat_version=watchlist.rule_version,
    )
    run = AnalyticRun(run_id=new_id("run"), **manifest.__dict__)
    session.add(run)
    session.flush()

    alerts: list[WatchlistAlert] = []
    if watched:
        alerts = _detect(
            session,
            watchlist,
            run,
            watched=watched,
            user=user,
            ontology=ontology,
            since=since,
            now=now,
        )

    run.evaluated_through = now
    run.finished_at = datetime.now(timezone.utc)
    session.flush()
    return run, alerts


def _detect(
    session: Session,
    watchlist: Watchlist,
    run: AnalyticRun,
    *,
    watched: dict[str, set[str]],
    user: UserContext,
    ontology: Ontology,
    since: datetime | None,
    now: datetime,
) -> list[WatchlistAlert]:
    """Claims recorded in the window that carry a watched value, **exactly**."""
    conditions = [
        Claim.predicate.in_(list(watched)),
        Claim.object_value.is_not(None),
        Claim.recorded_at <= now,
        *claim_filters(session, user, ontology),
    ]
    if since is not None:
        # Half-open on the low side, so a claim recorded exactly at the last
        # watermark is not swept twice. The dedupe key would refuse the second
        # alert anyway; this keeps the *window* honest as well as the result.
        conditions.append(Claim.recorded_at > since)

    rows = session.execute(
        select(Claim.claim_id, Claim.subject_id, Claim.predicate, Claim.object_value)
        .where(*conditions)
        .order_by(Claim.claim_id)
    )

    # `(entity_id, matched_value) -> [claim_id]`. Grouped before any alert is
    # built, so two claims recording one value on one entity are one detection
    # with two inputs rather than one alert and one refusal.
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        value = str(row.object_value)
        # Exact, and this is the line that says so: `in` over a set of strings.
        # No normalization, no folding, no distance. ADR-053's reason — a
        # near-match on an identifier is a different person with a name
        # attached — and a watchlist that fires on one teaches its readers to
        # believe the next one.
        if value in watched.get(row.predicate, ()):
            grouped[(row.subject_id, value)].append(row.claim_id)

    existing = set(
        session.scalars(
            select(WatchlistAlert.dedupe_key).where(
                WatchlistAlert.watchlist_id == watchlist.watchlist_id
            )
        )
    )

    alerts = []
    for (entity_id, value), claim_ids in sorted(grouped.items()):
        key = dedupe_key(
            watchlist_id=watchlist.watchlist_id,
            rule_version=watchlist.rule_version,
            matched_value=value,
            entity_id=entity_id,
        )
        if key in existing:
            continue
        existing.add(key)
        code, rank = _handling_for(session, ontology, claim_ids)
        alerts.append(
            WatchlistAlert(
                alert_id=new_id("alrt"),
                watchlist_id=watchlist.watchlist_id,
                run_id=run.run_id,
                rule=watchlist.rule,
                rule_version=watchlist.rule_version,
                matched_value=value,
                entity_id=entity_id,
                claim_ids=sorted(claim_ids),
                dedupe_key=key,
                exactness=EXACT,
                handling_code=code,
                handling_rank=rank,
            )
        )
    session.add_all(alerts)
    session.flush()
    return alerts


def sweep(
    session: Session,
    *,
    ontology: Ontology,
    watchlist_id: str | None = None,
    now: datetime | None = None,
) -> list[tuple[AnalyticRun, list[WatchlistAlert]]]:
    """Every active watchlist, or one named. Each gets its own run."""
    statement = select(Watchlist).where(Watchlist.active.is_(True))
    if watchlist_id is not None:
        statement = statement.where(Watchlist.watchlist_id == watchlist_id)
    watchlists = list(session.scalars(statement.order_by(Watchlist.watchlist_id)))
    if watchlist_id is not None and not watchlists:
        raise WatchlistError(
            f"watchlist {watchlist_id!r} is not active or does not exist"
        )
    return [
        evaluate_watchlist(session, watchlist, ontology=ontology, now=now)
        for watchlist in watchlists
    ]


def triage_alert(
    session: Session,
    *,
    alert_id: str,
    status: str,
    actor: str,
    purpose: str | None = None,
    reason: str | None = None,
) -> WatchlistAlert:
    """Move an alert between `new`, `reviewing` and `closed`. Every move audited.

    There is **no transition graph** beyond "closed requires a reason" — the
    same decision spec 09 made for investigation tasks, for the same reason: a
    workflow nobody agreed to is a workflow people route around. Reopening a
    closed alert is allowed and audited, because deciding you were wrong is a
    thing that happens.
    """
    if status not in TRIAGE_STATUSES:
        raise WatchlistError(
            f"{status!r} is not a triage status (have: {list(TRIAGE_STATUSES)})"
        )
    alert = session.get(WatchlistAlert, alert_id)
    if alert is None:
        raise WatchlistError(f"alert {alert_id!r} does not exist")
    if status == "closed" and not (reason or "").strip():
        raise WatchlistError(
            "closing an alert needs a reason: an alert closed with no reason is "
            "indistinguishable from one nobody looked at"
        )

    previous = alert.status
    alert.status = status
    # Cleared on reopen, so a reopened alert does not carry the reason it was
    # closed with as though it were still closed.
    alert.closed_reason = reason.strip() if status == "closed" and reason else None

    append_audit(
        session,
        actor=actor,
        action="alert.triage",
        decision="allow",
        purpose=purpose,
        resource_type="watchlist_alert",
        resource_id=alert_id,
        detail={"from": previous, "to": status, "reason": alert.closed_reason},
    )
    session.flush()
    return alert


__all__ = [
    "METHOD",
    "TRIAGE_STATUSES",
    "WatchlistError",
    "create_watchlist",
    "evaluate_watchlist",
    "last_evaluated_through",
    "sweep",
    "triage_alert",
]
