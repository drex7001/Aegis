"""The new predicate reaches API validation, with no code that knows about it (T39).

The contract half — proposal, ownership, interface expansion, generated client —
is `tests/contract/test_ontology_change_flow.py`. This is the half that needs a
database: proposal 004's `controls` predicate validates, records, projects, and
is *constrained* exactly as a hand-coded predicate would be, having reached the
system as one line of YAML.

The interface is the point. `subject: [party]` means a **person or an
organization** may control something, and a `location` may not — enforced by
the expansion, not by a branch anyone wrote.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
import yaml
from alembic.config import Config
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, ActionValidationError, new_id
from aegis.er.canonical import rebuild_canonical_map
from aegis.er.ledger import open_membership
from aegis.er.normalize import norm_key
from aegis.ontology import load
from aegis.projections import rebuild_edge_projection
from aegis.store import Claim, EdgeProjection, Entity, Mention, Source, SourceRecord
from tests.support.database import migrated_test_engine, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("Article-XI", "Article-XIV", "T39")

ANALYST = frozenset({"analyst"})


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


@pytest.fixture(scope="module")
def change_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        yield engine


@pytest.fixture()
def world(change_engine: sa.Engine):
    """A person, an organization, a second organization, and a location.

    All fictional. The location exists to be *refused*: it is not a `party`,
    and nothing in the code says so.
    """
    truncate_domain_data(change_engine)
    ids = {"source": new_id("src"), "record": new_id("rec")}
    session = Session(change_engine)
    with session.begin():
        session.add(
            Source(source_id=ids["source"], source_type="open_source", name="T39 source")
        )
        session.add(
            SourceRecord(
                record_id=ids["record"],
                source_id=ids["source"],
                ingest_key=new_id("key"),
                content_hash="c" * 64,
                storage_uri="test://t39",
            )
        )
        session.flush()
        for key, entity_type, label in (
            ("person", "person", "Fictional Director"),
            ("org", "organization", "Fictional Holdings"),
            ("subsidiary", "organization", "Fictional Haulage"),
            ("place", "location", "Fictional Port"),
        ):
            entity_id, mention_id = new_id("ent"), new_id("men")
            ids[key] = entity_id
            session.add(Entity(entity_id=entity_id, entity_type=entity_type, label=label))
            session.add(
                Mention(
                    mention_id=mention_id,
                    record_id=ids["record"],
                    raw_text=label,
                    norm_key=f"{norm_key(label)}-{mention_id[-6:].lower()}",
                )
            )
            session.flush()
            open_membership(session, mention_id=mention_id, entity_id=entity_id)
    try:
        yield {**ids, "session": session, "service": ActionService(session)}
    finally:
        session.close()


def _control(world, subject: str, obj: str) -> Claim:
    return world["service"].record_claim(
        ActionContext(actor="user:analyst", roles=ANALYST),
        subject_id=world[subject],
        predicate="controls",
        object_id=world[obj],
        record_id=world["record"],
        collection_method="curated",
    )


def test_a_person_may_control_an_organization(world, ontology) -> None:
    session: Session = world["session"]
    claim = _control(world, "person", "org")
    session.commit()

    stored = session.get(Claim, claim.claim_id)
    assert stored.predicate == "controls"
    # The stamp is the **composition** version (ADR-037), which is the durable
    # claim here. This used to pin the literal `1.6.0` and went red at T42 for a
    # label change: what matters is that a claim records the version of the
    # whole composition, not the version of whichever module owns its predicate.
    assert stored.ontology_version == ontology.version
    # Where that version comes from, asserted against the manifest itself rather
    # than against a module's version being different. The inequality this
    # replaces held only by coincidence, and the coincidence ended at T55 when
    # `criminal_network` also reached 2.0.0 — at which point a test meant to
    # prove the two are *independent* was failing because they had agreed.
    manifest = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    assert stored.ontology_version == manifest["version"]
    assert "composition" in manifest, "the stamp must come from the manifest, not a module"


def test_an_organization_may_control_an_organization(world) -> None:
    """The reason the subject is an interface: front companies are companies."""
    session: Session = world["session"]
    claim = _control(world, "org", "subsidiary")
    session.commit()
    assert session.get(Claim, claim.claim_id).subject_id == world["org"]


def test_a_non_party_subject_is_refused(world) -> None:
    """Enforced by the expansion, not by a branch anyone wrote.

    `location` does not implement `party`, so it is not in the expanded subject
    set — and the error names the predicate's own YAML path.
    """
    with pytest.raises(ActionValidationError) as excinfo:
        _control(world, "place", "org")
    assert excinfo.value.path == "predicates.controls.subject"
    assert "'location' is not allowed" in excinfo.value.message


def test_a_non_organization_object_is_refused(world) -> None:
    with pytest.raises(ActionValidationError) as excinfo:
        _control(world, "person", "place")
    assert excinfo.value.path == "predicates.controls.object"


def test_the_claim_projects_into_the_graph_under_its_declared_category(
    world, ontology
) -> None:
    """The projection groups by a category it was never told about."""
    session: Session = world["session"]
    _control(world, "person", "org")
    session.commit()

    with Session(session.get_bind()) as fresh:
        rebuild_canonical_map(fresh)
        rebuild_edge_projection(fresh, ontology=ontology)
        fresh.commit()
        segments = list(
            fresh.scalars(
                sa.select(EdgeProjection).where(EdgeProjection.predicate == "controls")
            )
        )
    assert len(segments) == 1
    assert ontology.predicate("controls").category == "financial"


def test_the_suggestion_path_accepts_it_too(world) -> None:
    """A producer can propose it without the review queue knowing the name."""
    session: Session = world["session"]
    service: ActionService = world["service"]
    suggestion = service.submit_suggestion(
        ActionContext(actor="user:analyst", roles=ANALYST),
        payload={
            "subject_id": world["person"],
            "predicate": "controls",
            "object_id": world["org"],
            "record_id": world["record"],
            "collection_method": "curated",
        },
        producer="t39-fixture",
        producer_meta={"reason": "ontology-change proof"},
    )
    session.commit()

    decided = service.review_suggestion(
        ActionContext(actor="user:analyst", roles=ANALYST),
        suggestion_id=suggestion.suggestion_id,
        decision="accepted",
    )
    session.commit()
    assert decided.status == "accepted"
    assert session.get(Claim, decided.result_claim_id).predicate == "controls"
