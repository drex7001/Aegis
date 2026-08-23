"""Composition is set algebra, under one snapshot and the caller's filters (T70).

The T70 acceptance criterion is stated as an identity, and it is tested as one:

> For a given caller and snapshot, the evaluated membership of a composed set
> equals the corresponding set operation over the evaluated memberships of its
> operands **for that same caller**.

That identity is what makes composition safe rather than clever. A row the
caller cannot see is in *neither* operand, so it is in no result and changes no
cardinality — which is why `difference` cannot be used to probe. The tests
below check the identity **and** the reason: the same composition evaluated by
a narrower caller is a subset, and strictly so once a restricted row matches.

M-13's correction applies here as it does to search: two callers get the *same*
answer when everything matching is `open`, and a strict subset only when
something restricted matches. Asserting "strictly fewer" unconditionally would
assert something false about a correct system.

Fictional fixtures throughout.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.er.ledger import active_revision_id
from aegis.ids import new_id
from aegis.ontology import load
from aegis.sets.compile import compile_set
from aegis.sets.evaluation import Evaluation, evaluate, evaluate_version, evaluation_digest
from aegis.sets.grammar import GrammarError, parse
from aegis.sets.limits import STATEMENT_TIMEOUT_MS
from aegis.sets.service import add_version, create_set, share
from aegis.sets.sharing import EDITOR, VIEWER, redact_definition
from aegis.store import AuthzOutbox, Claim, Entity, Source, SourceRecord
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("B-17", "M-13", "M-16", "Article-VI", "T70")


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


def _user(sub: str, clearance: int) -> UserContext:
    return UserContext(
        sub=sub,
        username=sub,
        roles=frozenset({"analyst"}),
        clearance=clearance,
        claims={},
    )


@pytest.fixture()
def world(engine: sa.Engine):
    """Four people. One is reachable only through a `sensitive` claim."""
    truncate_domain_data(engine)
    session = Session(engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T70")
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="c" * 64,
                storage_uri="test://t70",
            )
        )
        session.flush()
        seeded = (
            ("open_a", "person", "Fictional HOTEL", "open", "courier"),
            ("open_b", "person", "Fictional INDIA", "open", "broker"),
            ("org", "organization", "Fictional Holdings", "open", "front"),
            ("restricted", "person", "Fictional JULIET", "sensitive", "courier"),
        )
        for key, entity_type, label, handling, role in seeded:
            ids[key] = new_id("ent")
            session.add(
                Entity(entity_id=ids[key], entity_type=entity_type, label=label)
            )
            session.flush()
            session.add(
                Claim(
                    claim_id=new_id("clm"),
                    subject_id=ids[key],
                    predicate="has_role",
                    object_value=role,
                    assertion_type="reported",
                    handling_code=handling,
                    record_id=ids["record"],
                    identity_revision_id=active_revision_id(session),
                    ontology_version="2.1.0",
                    credibility_normalized="possibly_true",
                    verification_status="unverified",
                )
            )
    try:
        yield {**ids, "session": session}
    finally:
        session.close()


def _members(session, ast, *, user, ontology) -> set[str]:
    result = evaluate(session, parse(ast), user=user, ontology=ontology)
    return {member.entity_id for member in result.members}


PEOPLE = {"kind": "type", "object_type": "person"}
COURIERS = {"kind": "property", "property": "has_role", "op": "eq", "value": "courier"}


# ── the composition identity ────────────────────────────────────────────────


def test_union_equals_the_union_of_its_operands(world, ontology) -> None:
    session, user = world["session"], _user("user:senior", 2)
    left = _members(session, PEOPLE, user=user, ontology=ontology)
    right = _members(
        session, {"kind": "type", "object_type": "organization"}, user=user, ontology=ontology
    )
    composed = _members(
        session,
        {"kind": "or", "children": [PEOPLE, {"kind": "type", "object_type": "organization"}]},
        user=user,
        ontology=ontology,
    )
    assert composed == left | right


def test_intersection_equals_the_intersection_of_its_operands(world, ontology) -> None:
    session, user = world["session"], _user("user:senior", 2)
    left = _members(session, PEOPLE, user=user, ontology=ontology)
    right = _members(session, COURIERS, user=user, ontology=ontology)
    composed = _members(
        session, {"kind": "and", "children": [PEOPLE, COURIERS]}, user=user, ontology=ontology
    )
    assert composed == left & right
    assert composed, "the control failed: the operands do not overlap"


def test_difference_equals_the_difference_of_its_operands(world, ontology) -> None:
    session, user = world["session"], _user("user:senior", 2)
    left = _members(session, PEOPLE, user=user, ontology=ontology)
    right = _members(session, COURIERS, user=user, ontology=ontology)
    composed = _members(
        session,
        {"kind": "and", "children": [PEOPLE, {"kind": "not", "child": COURIERS}]},
        user=user,
        ontology=ontology,
    )
    assert composed == left - right
    assert composed, "the control failed: the difference is empty"


# ── the caller's filters, never the owner's ─────────────────────────────────


def test_a_bare_type_node_still_requires_a_readable_claim(world, ontology) -> None:
    """The T69 hole, as a direct regression rather than a side effect.

    `{"kind": "type", "object_type": "person"}` compiled to
    `entity.entity_type = 'person'` and nothing else — no claim join, no
    filter — so a junior analyst evaluating it received every person in the
    database, including one reachable only through a `sensitive` claim.

    An entity carries no handling code of its own; claims do. The other tests
    in this section catch this as a subset failure, which is how it was found;
    this one names it, so a future reader sees the rule rather than inferring
    it from a comparison.
    """
    session = world["session"]
    junior = _members(session, PEOPLE, user=_user("user:junior", 0), ontology=ontology)
    assert world["restricted"] not in junior
    assert world["open_a"] in junior, "the control failed: the junior sees nothing"


def test_an_entity_with_no_readable_claim_at_all_is_absent(world, ontology) -> None:
    """Not merely filtered by handling code — reachable through nothing.

    An entity with no claims is not knowledge, and a set that listed it would
    be disclosing the bare fact of a record's existence.
    """
    session = world["session"]
    orphan = new_id("ent")
    session.add(Entity(entity_id=orphan, entity_type="person", label="Fictional KILO"))
    session.flush()

    members = _members(session, PEOPLE, user=_user("user:senior", 2), ontology=ontology)
    assert orphan not in members


def test_a_narrower_caller_sees_a_subset(world, ontology) -> None:
    session = world["session"]
    senior = _members(session, PEOPLE, user=_user("user:senior", 2), ontology=ontology)
    junior = _members(session, PEOPLE, user=_user("user:junior", 0), ontology=ontology)
    assert junior < senior
    assert world["restricted"] in senior - junior


def test_the_same_query_gives_the_same_answer_when_nothing_restricted_matches(
    world, ontology
) -> None:
    """M-13: "strictly fewer" is only true when a restricted row matches.

    Asserting it unconditionally would assert something false about a correct
    system, so the case where the two agree is a test rather than an omission.
    """
    session = world["session"]
    organizations = {"kind": "type", "object_type": "organization"}
    senior = _members(session, organizations, user=_user("user:senior", 2), ontology=ontology)
    junior = _members(session, organizations, user=_user("user:junior", 0), ontology=ontology)
    assert junior == senior
    assert senior, "the control failed: nothing matched for either caller"


def test_a_set_never_evaluates_with_its_owners_clearance(world, ontology) -> None:
    """The property that stops a set becoming a second authorization system.

    A senior analyst saves a set; a junior evaluates it. The junior must see
    their own view of it, not the owner's — otherwise sharing a set would be a
    way to lend clearance.
    """
    session = world["session"]
    row, version = create_set(
        session,
        name="Everyone",
        ast=PEOPLE,
        ontology=ontology,
        actor="user:senior",
    )
    session.flush()

    as_owner = evaluate_version(
        session, version, user=_user("user:senior", 2), ontology=ontology
    )
    as_viewer = evaluate_version(
        session, version, user=_user("user:junior", 0), ontology=ontology
    )
    owner_ids = {member.entity_id for member in as_owner.members}
    viewer_ids = {member.entity_id for member in as_viewer.members}
    assert viewer_ids < owner_ids
    assert world["restricted"] not in viewer_ids


def test_composition_of_someone_elses_set_uses_the_callers_filters(world, ontology) -> None:
    """Including subsets owned by other people — M-16's second clause."""
    session = world["session"]
    other, other_version = create_set(
        session,
        name="Senior's people",
        ast=PEOPLE,
        ontology=ontology,
        actor="user:senior",
    )
    session.flush()

    composed = {
        "kind": "and",
        "children": [
            {"kind": "set", "set_id": other.set_id, "version": other_version.version},
            COURIERS,
        ],
    }
    senior = _members(session, composed, user=_user("user:senior", 2), ontology=ontology)
    junior = _members(session, composed, user=_user("user:junior", 0), ontology=ontology)
    assert world["restricted"] in senior
    assert world["restricted"] not in junior


# ── one snapshot (M-16) ─────────────────────────────────────────────────────


def test_composition_is_a_single_statement(world, ontology) -> None:
    """M-16's snapshot, met by construction rather than by isolation level.

    The first version of this asserted `REPEATABLE READ`, and the code that
    would have set it could not: PostgreSQL accepts that only as a
    transaction's first statement, and an evaluation runs after the caller has
    done something. The workaround — rolling back the caller's transaction to
    get a clean one — would have been a library discarding uncommitted work.

    The guarantee is stronger without it. Every operand and every composed
    subset compiles into **one** `SELECT` as a subquery, so there is no moment
    *between* the operands for the corpus to change in. A single statement sees
    a single snapshot at any isolation level.

    If an evaluation ever needs a second statement this test fails, which is
    the point: at that moment the caller has to supply a REPEATABLE READ
    transaction, because construction no longer does it for them.
    """
    session = world["session"]
    composed = parse(
        {
            "kind": "or",
            "children": [
                PEOPLE,
                {"kind": "type", "object_type": "organization"},
                {"kind": "and", "children": [PEOPLE, COURIERS]},
            ],
        }
    )
    statement = compile_set(
        composed,
        session=session,
        user=_user("user:senior", 2),
        ontology=ontology,
    )
    sql = str(statement.compile(session.get_bind()))
    assert sql.count(";") == 0, "the evaluation is more than one statement"
    # Every operand really is in there, so "one statement" is not one statement
    # that quietly dropped a branch.
    assert sql.count("entity_type") >= 3


def test_evaluation_sets_a_statement_timeout(world, ontology) -> None:
    """B-17's resource bound: the complexity limits do not catch a slow corpus."""
    session = world["session"]
    evaluate(session, parse(PEOPLE), user=_user("user:senior", 2), ontology=ontology)
    timeout = session.execute(sa.text("SHOW statement_timeout")).scalar()
    assert timeout == f"{STATEMENT_TIMEOUT_MS // 1000}s"


# ── the evaluation digest ───────────────────────────────────────────────────


def test_the_digest_is_order_independent_and_membership_sensitive() -> None:
    """Membership is a set, not a ranking — but a different set is a different digest."""
    assert evaluation_digest(["a", "b"]) == evaluation_digest(["b", "a"])
    assert evaluation_digest(["a", "b"]) != evaluation_digest(["a", "c"])


def test_two_callers_get_different_digests_for_the_same_set(world, ontology) -> None:
    """Which is what makes it usable as an analytic input (ADR-055).

    A finding computed under a narrower clearance is a different finding, and
    the digest is what says so.
    """
    session = world["session"]
    senior = evaluate(session, parse(PEOPLE), user=_user("user:senior", 2), ontology=ontology)
    junior = evaluate(session, parse(PEOPLE), user=_user("user:junior", 0), ontology=ontology)
    assert senior.evaluation_digest != junior.evaluation_digest


def test_an_evaluation_carries_no_total(world, ontology) -> None:
    session = world["session"]
    result = evaluate(session, parse(PEOPLE), user=_user("user:senior", 2), ontology=ontology)
    assert not hasattr(result, "total")
    assert set(Evaluation.__dataclass_fields__) == {
        "members",
        "truncated",
        "evaluation_digest",
        "set_id",
        "version",
    }


# ── sharing, and the definition as protected data ───────────────────────────


def test_creating_a_set_makes_its_author_an_editor(world, ontology) -> None:
    """A set nobody can edit — including its author — should not be creatable."""
    session = world["session"]
    row, _ = create_set(
        session, name="Mine", ast=PEOPLE, ontology=ontology, actor="user:senior"
    )
    session.flush()
    queued = [
        entry.fga_tuple
        for entry in session.scalars(sa.select(AuthzOutbox))
        if entry.fga_tuple.get("object") == f"object_set:{row.set_id}"
    ]
    assert {"user": "user:user:senior", "relation": EDITOR, "object": f"object_set:{row.set_id}"} in queued


def test_sharing_queues_a_grant_and_names_it(world, ontology) -> None:
    session = world["session"]
    row, _ = create_set(
        session, name="Mine", ast=PEOPLE, ontology=ontology, actor="user:senior"
    )
    session.flush()
    tuple_ = share(session, set_id=row.set_id, user_sub="user:junior", relation=VIEWER)
    assert tuple_["relation"] == VIEWER
    assert tuple_["object"] == f"object_set:{row.set_id}"


def test_a_restricted_property_is_withheld_with_its_shape_intact(world, ontology) -> None:
    """Spec 12 §5.2 rule 1.

    Removing the node would misdescribe the set — its evaluation still uses the
    condition. Showing the value would be the leak B-17 names. Saying "there is
    a condition here you may not read" is the honest third option.
    """
    node = parse(
        {
            "kind": "and",
            "children": [
                PEOPLE,
                {"kind": "property", "property": "nic", "op": "eq", "value": "FIXTURE-ID-1"},
            ],
        }
    )
    cleared = redact_definition(node, ontology=ontology, clearance=2)
    withheld = redact_definition(node, ontology=ontology, clearance=0)

    assert cleared["children"][1]["value"] == "FIXTURE-ID-1"
    assert withheld["children"][1]["value"] is None
    assert withheld["children"][1]["withheld"] is True
    # The shape survives: same node kind, same property, same operator.
    assert withheld["children"][1]["property"] == "nic"
    assert withheld["children"][1]["op"] == "eq"


def test_an_unrestricted_property_is_not_withheld(world, ontology) -> None:
    """Non-vacuity: redaction that hid everything would pass the test above."""
    node = parse({"kind": "property", "property": "aliases", "op": "eq", "value": "Tharu"})
    assert redact_definition(node, ontology=ontology, clearance=0)["value"] == "Tharu"


# ── the difference oracle (spec 12 §7) ──────────────────────────────────────


def test_negating_an_unreadable_set_is_refused_at_save(world, ontology) -> None:
    """"Everything in Ayesha's set that is not in mine", run once per candidate.

    Refused at save so the oracle never exists, rather than rate-limited at
    evaluation, which would only make it slower.
    """
    session = world["session"]
    theirs, theirs_version = create_set(
        session, name="Theirs", ast=PEOPLE, ontology=ontology, actor="user:senior"
    )
    session.flush()

    with pytest.raises(GrammarError) as excinfo:
        create_set(
            session,
            name="Probe",
            ast={
                "kind": "not",
                "child": {
                    "kind": "set",
                    "set_id": theirs.set_id,
                    "version": theirs_version.version,
                },
            },
            ontology=ontology,
            actor="user:probe",
            readable_set_ids=set(),
        )
    assert "disclosure oracle" in excinfo.value.message


def test_negating_a_readable_set_is_allowed(world, ontology) -> None:
    """Non-vacuity: negation is not banned, only negation of what you cannot read."""
    session = world["session"]
    mine, mine_version = create_set(
        session, name="Mine", ast=PEOPLE, ontology=ontology, actor="user:senior"
    )
    session.flush()

    _, version = create_set(
        session,
        name="Not mine",
        ast={
            "kind": "not",
            "child": {
                "kind": "set",
                "set_id": mine.set_id,
                "version": mine_version.version,
            },
        },
        ontology=ontology,
        actor="user:senior",
        readable_set_ids={mine.set_id},
    )
    assert version.version == 1


def test_the_default_refuses_rather_than_permits(world, ontology) -> None:
    """A caller that does not say which sets it can read gets no negation.

    Defaulting the other way would make the rule opt-in, and a security rule
    nobody remembers to opt into is not a rule.
    """
    session = world["session"]
    theirs, theirs_version = create_set(
        session, name="Theirs", ast=PEOPLE, ontology=ontology, actor="user:senior"
    )
    session.flush()

    with pytest.raises(GrammarError):
        add_version(
            session,
            set_id=theirs.set_id,
            ast={
                "kind": "not",
                "child": {
                    "kind": "set",
                    "set_id": theirs.set_id,
                    "version": theirs_version.version,
                },
            },
            ontology=ontology,
            actor="user:senior",
        )
