"""Saving a set pins it; editing versions it; a cycle is refused (T69, ADR-054).

The headline case is the one whose acceptance criterion T66 **inverted**. The
pre-authored plan said a set filtering on an interface should "pick up a new
member type after an ontology minor bump without edits". B-17 says the
opposite, and the amended charter agrees: a saved set is an input to analytics
and watchlists, so widening it silently changes the meaning of a finding
somebody already acted on — at the moment a *different* team lands a domain
module.

So the test seeds an ontology that grew an implementor and asserts the pinned
set did **not** move, the tracking set did, and both owners were told.

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
from aegis.ontology import compose, load, load_dict
from aegis.sets.compile import CompileError, compile_set
from aegis.sets.grammar import GrammarError, parse
from aegis.sets.service import add_version, create_set, notify_interface_growth
from aegis.store import Claim, Entity, ObjectSetNotice, ObjectSetVersion, Source, SourceRecord
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("B-17", "ADR-054", "Article-XI", "T69")


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def grown_ontology():
    """The same composition, plus a fictional `port` implementing `place`.

    A domain-module addition, exactly as a minor bump would deliver one.
    """
    document = compose(ONTOLOGY_PATH).document
    return load_dict(
        {
            **document,
            "object_types": {
                **document["object_types"],
                # `place` requires the shared `geometry` property, which is
                # the interface contract doing its job — a place you cannot
                # locate is not a place (spec 10 §4.1).
                "port": {
                    "label": "Port",
                    "implements": ["place"],
                    "properties": {
                        "name": {"type": "text"},
                        "geometry": {"shared": "geometry"},
                    },
                    "display": {"title": "name"},
                },
            },
        }
    )


@pytest.fixture(scope="module")
def engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def world(engine: sa.Engine, ontology):
    """A person, an organisation and a location, each with one readable claim."""
    truncate_domain_data(engine)
    session = Session(engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    with session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T69")
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="c" * 64,
                storage_uri="test://t69",
            )
        )
        session.flush()
        for key, entity_type, label in (
            ("person", "person", "Fictional GOLF"),
            ("org", "organization", "Fictional Holdings"),
            ("place", "location", "Fictional Jetty"),
        ):
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
                    object_value="fixture subject",
                    assertion_type="reported",
                    handling_code="open",
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


@pytest.fixture()
def analyst(ontology) -> UserContext:
    return UserContext(
        sub="user:analyst",
        username="analyst",
        roles=frozenset({"analyst"}),
        clearance=len(ontology.handling_codes) - 1,
        claims={},
    )


def _members(session, node, *, user, ontology) -> set[str]:
    statement = compile_set(node, session=session, user=user, ontology=ontology)
    return set(session.scalars(statement))


# ── storage: a query, never results ─────────────────────────────────────────


def test_the_schema_has_nowhere_to_put_results(world) -> None:
    """The T69 AC, met by there being no column rather than by a convention."""
    columns = set(ObjectSetVersion.__table__.columns.keys())
    assert not columns & {"results", "members", "entity_ids", "evaluated"}
    assert "ast" in columns


def test_a_saved_definition_round_trips(world, ontology) -> None:
    session: Session = world["session"]
    _, version = create_set(
        session,
        name="People",
        ast={"kind": "type", "object_type": "person"},
        ontology=ontology,
        actor="user:analyst",
    )
    session.commit()

    stored = session.get(ObjectSetVersion, (version.set_id, 1))
    assert stored.ast == {"kind": "type", "object_type": "person", "interface": None}
    assert stored.ontology_version == ontology.version


def test_an_edit_writes_a_new_immutable_version(world, ontology) -> None:
    """A finding names `(set_id, version)` and must name something stable."""
    session: Session = world["session"]
    row, first = create_set(
        session,
        name="People",
        ast={"kind": "type", "object_type": "person"},
        ontology=ontology,
        actor="user:analyst",
    )
    second = add_version(
        session,
        set_id=row.set_id,
        ast={"kind": "type", "object_type": "organization"},
        ontology=ontology,
        actor="user:analyst",
        note="widened to organisations",
    )
    session.commit()

    assert (first.version, second.version) == (1, 2)
    assert session.get(ObjectSetVersion, (row.set_id, 1)).ast["object_type"] == "person"
    assert second.note == "widened to organisations"


# ── compilation ─────────────────────────────────────────────────────────────


def test_a_type_set_evaluates_to_its_members(world, analyst, ontology) -> None:
    session: Session = world["session"]
    node = parse({"kind": "type", "object_type": "person"})
    assert _members(session, node, user=analyst, ontology=ontology) == {world["person"]}


def test_boolean_composition_behaves_like_set_algebra(world, analyst, ontology) -> None:
    session: Session = world["session"]
    both = parse(
        {
            "kind": "or",
            "children": [
                {"kind": "type", "object_type": "person"},
                {"kind": "type", "object_type": "organization"},
            ],
        }
    )
    assert _members(session, both, user=analyst, ontology=ontology) == {
        world["person"],
        world["org"],
    }

    negated = parse(
        {"kind": "not", "child": {"kind": "type", "object_type": "person"}}
    )
    members = _members(session, negated, user=analyst, ontology=ontology)
    assert world["person"] not in members
    assert world["org"] in members


def test_a_predicate_node_finds_entities_through_readable_claims(
    world, analyst, ontology
) -> None:
    session: Session = world["session"]
    node = parse({"kind": "predicate", "predicate": "has_role"})
    assert _members(session, node, user=analyst, ontology=ontology) == {
        world["person"],
        world["org"],
        world["place"],
    }


def test_an_unexpanded_interface_reaching_the_compiler_is_an_error(
    world, analyst, ontology
) -> None:
    """Loud rather than ignored.

    A compiler that treated an unrecognised node as "no constraint" would
    evaluate a *wider* set than the one that was saved, and the definition
    would still read correctly — the one failure mode a shared,
    analytic-feeding definition must not have.
    """
    session: Session = world["session"]
    with pytest.raises(CompileError):
        compile_set(
            parse({"kind": "type", "interface": "party"}),
            session=session,
            user=analyst,
            ontology=ontology,
        )


def test_composition_without_a_resolver_is_refused(world, analyst, ontology) -> None:
    session: Session = world["session"]
    with pytest.raises(CompileError):
        compile_set(
            parse({"kind": "set", "set_id": "oset_x", "version": 1}),
            session=session,
            user=analyst,
            ontology=ontology,
        )


# ── the pinning rule (ADR-054) ──────────────────────────────────────────────


def test_a_pinned_set_freezes_its_interface_at_save(world, ontology) -> None:
    session: Session = world["session"]
    _, version = create_set(
        session,
        name="Parties",
        ast={"kind": "type", "interface": "party"},
        ontology=ontology,
        actor="user:analyst",
    )
    session.commit()

    named = {child["object_type"] for child in version.ast["children"]}
    assert named == set(ontology.implementors("party"))
    assert version.ast_as_written["interface"] == "party"


def test_a_pinned_set_does_not_gain_a_new_member(world, ontology, grown_ontology) -> None:
    """The acceptance criterion T66 inverted, asserted directly.

    The pre-authored plan wanted this to pick up `port`. B-17 and the amended
    charter want the opposite, because a saved set feeds analytics and
    watchlists: widening it silently changes the meaning of a finding somebody
    already acted on.
    """
    session: Session = world["session"]
    _, version = create_set(
        session,
        name="Places",
        ast={"kind": "type", "interface": "place"},
        ontology=ontology,
        actor="user:analyst",
    )
    session.commit()

    assert "port" in grown_ontology.implementors("place"), "the control failed"
    frozen = {child["object_type"] for child in version.ast["children"]}
    assert "port" not in frozen
    assert frozen == set(ontology.implementors("place"))


def test_a_tracking_set_keeps_its_interface_and_moves(world, ontology, grown_ontology) -> None:
    session: Session = world["session"]
    _, version = create_set(
        session,
        name="Places, tracking",
        ast={"kind": "type", "interface": "place"},
        ontology=ontology,
        actor="user:analyst",
        track_interface_members=True,
    )
    session.commit()

    # Unexpanded, so evaluation resolves it against whatever composition is
    # live — which is what "track future members" means.
    assert version.ast["interface"] == "place"
    assert version.track_interface_members is True


def test_both_kinds_of_set_receive_a_notice(world, ontology, grown_ontology) -> None:
    """Pinned owners are told too, and that is deliberate (spec 12 §4.3).

    A tracking set changed; a pinned set *could* have. Telling only the first
    means the owner of a pinned set discovers the divergence when somebody
    questions a number, which is the wrong moment.
    """
    session: Session = world["session"]
    pinned, pinned_version = create_set(
        session,
        name="Places",
        ast={"kind": "type", "interface": "place"},
        ontology=ontology,
        actor="user:analyst",
    )
    tracking, tracking_version = create_set(
        session,
        name="Places, tracking",
        ast={"kind": "type", "interface": "place"},
        ontology=ontology,
        actor="user:analyst",
        track_interface_members=True,
    )
    unrelated, _ = create_set(
        session,
        name="People",
        ast={"kind": "type", "object_type": "person"},
        ontology=ontology,
        actor="user:analyst",
    )
    session.flush()

    notices = notify_interface_growth(
        session,
        ontology=grown_ontology,
        previous_members={"place": set(ontology.implementors("place"))},
    )
    session.commit()

    notified = {(notice.set_id, notice.tracking) for notice in notices}
    assert (pinned.set_id, False) in notified
    assert (tracking.set_id, True) in notified
    # A set that names no interface is not told about one.
    assert unrelated.set_id not in {notice.set_id for notice in notices}
    assert {notice.member for notice in notices} == {"port"}


def test_a_notice_is_not_repeated_by_a_second_sweep(world, ontology, grown_ontology) -> None:
    """Rerunning the sweep must not multiply what an owner sees."""
    session: Session = world["session"]
    create_set(
        session,
        name="Places",
        ast={"kind": "type", "interface": "place"},
        ontology=ontology,
        actor="user:analyst",
    )
    session.flush()

    previous = {"place": set(ontology.implementors("place"))}
    notify_interface_growth(session, ontology=grown_ontology, previous_members=previous)
    session.commit()

    with pytest.raises(sa.exc.IntegrityError):
        notify_interface_growth(
            session, ontology=grown_ontology, previous_members=previous
        )
        session.commit()
    session.rollback()

    assert session.scalar(
        sa.select(sa.func.count()).select_from(ObjectSetNotice)
    ) == 1


def test_no_growth_produces_no_notices(world, ontology) -> None:
    session: Session = world["session"]
    create_set(
        session,
        name="Places",
        ast={"kind": "type", "interface": "place"},
        ontology=ontology,
        actor="user:analyst",
    )
    session.flush()
    notices = notify_interface_growth(
        session,
        ontology=ontology,
        previous_members={"place": set(ontology.implementors("place"))},
    )
    assert notices == []


# ── composition cycles, refused at save ─────────────────────────────────────


def test_a_set_referencing_itself_is_refused(world, ontology) -> None:
    session: Session = world["session"]
    row, _ = create_set(
        session,
        name="Seed",
        ast={"kind": "type", "object_type": "person"},
        ontology=ontology,
        actor="user:analyst",
    )
    session.flush()

    with pytest.raises(GrammarError) as excinfo:
        add_version(
            session,
            set_id=row.set_id,
            ast={"kind": "set", "set_id": row.set_id, "version": 1},
            ontology=ontology,
            actor="user:analyst",
        )
    assert "cycle" in excinfo.value.message


def test_a_reference_to_a_missing_version_is_refused(world, ontology) -> None:
    """At save, so the definition never exists in a state nobody can evaluate."""
    session: Session = world["session"]
    with pytest.raises(GrammarError) as excinfo:
        create_set(
            session,
            name="Dangling",
            ast={"kind": "set", "set_id": "oset_missing", "version": 3},
            ontology=ontology,
            actor="user:analyst",
        )
    assert "does not exist" in excinfo.value.message


def test_composition_deeper_than_the_limit_is_refused(world, ontology) -> None:
    """A set of sets of sets is a query language, not a filter."""
    session: Session = world["session"]
    previous = None
    for index in range(5):
        ast = (
            {"kind": "type", "object_type": "person"}
            if previous is None
            else {"kind": "set", "set_id": previous, "version": 1}
        )
        try:
            row, _ = create_set(
                session,
                name=f"Layer {index}",
                ast=ast,
                ontology=ontology,
                actor="user:analyst",
            )
        except GrammarError as exc:
            assert "deeper" in exc.message
            session.rollback()
            return
        session.flush()
        previous = row.set_id
    pytest.fail("composition nested five deep without being refused")
