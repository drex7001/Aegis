"""PostgreSQL acceptance tests for the legacy migration (speckit T8)."""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegis.audit import verify
from aegis.evidence import LocalFilesystemVault
from aegis.migration import migrate
from aegis.ontology import load
from aegis.store import (
    Claim,
    Entity,
    IdentityDecision,
    IdentityMembership,
    Mention,
    Source,
    SourceRecord,
)
from tests.support.paths import REPO_ROOT, SNAPSHOT_ROOT
from tests.support.database import (
    RESTORE_BASELINE_REVISION,
    TRUNCATE_DOMAIN_TABLES,
    migrated_test_engine,
)

BASELINE = SNAPSHOT_ROOT / "real_graph.baseline.json"
pytestmark = pytest.mark.requirement("Article-XIII", "T8")


@pytest.fixture(scope="module")
def ontology():
    return load(REPO_ROOT / "ontology" / "aegis.yaml")


@pytest.fixture(scope="module")
def baseline_graph() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def migration_engine(test_database_url: str, alembic_config: Config) -> sa.Engine:
    with migrated_test_engine(test_database_url, alembic_config) as engine:
        # Deterministic migration ids require empty domain tables. Keep the
        # append-only audit chain intact and verify it below.
        with engine.begin() as connection:
            connection.execute(sa.text(TRUNCATE_DOMAIN_TABLES))
            connection.execute(sa.text(RESTORE_BASELINE_REVISION))
        yield engine


@pytest.fixture(scope="module")
def migrated(migration_engine: sa.Engine, tmp_path_factory: pytest.TempPathFactory):
    vault = LocalFilesystemVault(tmp_path_factory.mktemp("vault"))
    with Session(migration_engine) as session:
        first = migrate(session, vault=vault)
    with Session(migration_engine) as session:
        second = migrate(session, vault=vault)
    return {"engine": migration_engine, "first": first, "second": second}


@pytest.mark.integration
def test_migration_counts_reconcile(migrated, baseline_graph) -> None:
    first = migrated["first"]
    assert first.entities_created == 41 == len(baseline_graph["nodes"])
    assert first.sources_created == len(baseline_graph["meta"]["sources"]) == 12
    assert first.records_created == 12
    assert first.mentions == 41
    assert first.edges_total == len(baseline_graph["edges"]) == 57
    # every edge produced ≥1 claim, splits included, all listed in the report
    assert len(first.remap_log) == 57
    assert all(len(entry["predicates"]) >= 1 for entry in first.remap_log)
    expected_split_claims = sum(len(e["predicates"]) for e in first.remap_log)
    assert first.edge_claims_created == expected_split_claims == 63
    report = first.to_dict()
    assert len(report["splits"]) == 6
    assert len(report["credibility_caps"]) == 2
    assert len(report["category_corrections"]) == 7


@pytest.mark.integration
def test_migration_is_idempotent(migrated) -> None:
    second = migrated["second"]
    assert second.entities_created == 0
    assert second.sources_created == 0
    assert second.records_created == 0
    assert second.node_claims_created == 0
    assert second.edge_claims_created == 0
    first = migrated["first"]
    assert second.entities_existing == first.entities_created
    assert second.edge_claims_existing == first.edge_claims_created
    assert second.node_claims_existing == first.node_claims_created


@pytest.mark.integration
def test_migrated_store_contents(migrated, baseline_graph) -> None:
    engine = migrated["engine"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Entity)) == 41
        assert session.scalar(select(func.count()).select_from(Source)) == 12
        assert session.scalar(select(func.count()).select_from(SourceRecord)) == 12
        assert session.scalar(select(func.count()).select_from(Mention)) == 41
        # Legacy one-mention clusters are *verified as* the ledger baseline,
        # not adjudicated: they open at revision 0 and never close, and no
        # decision is invented for them (spec 05 §7 step 3, ADR-005).  The old
        # `decided_by='rule:legacy-slug'` marker went with the column — a rule
        # is never a decider (ADR-027).
        assert (
            session.scalar(
                select(func.count())
                .select_from(IdentityMembership)
                .where(
                    IdentityMembership.opened_revision_id == 0,
                    IdentityMembership.closed_revision_id.is_(None),
                )
            )
            == 41
        )
        assert session.scalar(select(func.count()).select_from(IdentityDecision)) == 0
        # Every entity is reachable from at least one mention (spec 05 §1): an
        # entity nobody ever wrote down in a source record is not knowledge.
        orphans = session.scalars(
            select(Entity.entity_id)
            .outerjoin(
                IdentityMembership, IdentityMembership.entity_id == Entity.entity_id
            )
            .where(IdentityMembership.membership_id.is_(None))
        ).all()
        assert orphans == []
        # Claims drawn from the record their subject was named in carry that
        # mention as an anchor (ADR-029); a claim citing a different
        # publication has no mention there and stays unanchored by design,
        # following the re-adjudication path on a split rather than pointing
        # at text it was not drawn from (spec 02 §3.1 rule 4).
        anchored = session.scalar(
            select(func.count())
            .select_from(Claim)
            .where(Claim.subject_mention_id.isnot(None))
        )
        assert anchored > 0
        for claim in session.scalars(
            select(Claim).where(Claim.subject_mention_id.isnot(None)).limit(50)
        ):
            mention = session.get(Mention, claim.subject_mention_id)
            assert mention.record_id == claim.record_id

        # one content-addressed snapshot backs every record (same bytes → one hash)
        hashes = set(session.scalars(select(SourceRecord.content_hash)))
        assert len(hashes) == 1

        # affiliation fallback: NTJ resolves to the organization entity,
        # unmatched affiliation strings stay as literals
        ntj = session.scalar(
            select(Entity).where(Entity.label == "National Thowheeth Jamaath")
        )
        assert ntj is not None and ntj.entity_type == "organization"
        resolved = session.scalar(
            select(func.count())
            .select_from(Claim)
            .where(Claim.predicate == "affiliated_with", Claim.object_id == ntj.entity_id)
        )
        assert resolved >= 15  # the extremism network members
        literal_affiliations = set(
            session.scalars(
                select(Claim.object_value).where(
                    Claim.predicate == "affiliated_with", Claim.object_id.is_(None)
                )
            )
        )
        assert "Madush drug network" in literal_affiliations
        assert "LTTE (alleged)" in literal_affiliations

        # grading preserved: original tag + scheme on every edge claim
        schemes = set(
            session.scalars(
                select(Claim.credibility_scheme).where(
                    Claim.credibility_scheme.isnot(None)
                )
            )
        )
        assert schemes == {"legacy-confidence-tag"}

        # the former-ally regime change produced complementary windows
        allied = session.scalar(
            select(Claim).where(
                Claim.predicate == "allied_with", Claim.excerpt.like("%Moratu Saman%")
            )
        )
        rival = session.scalar(
            select(Claim).where(
                Claim.predicate == "rival_of", Claim.excerpt.like("%Moratu Saman%")
            )
        )
        assert allied is not None and rival is not None
        assert allied.record_id == rival.record_id

        # Article X: the audit chain over the whole run verifies
        report = verify(session)
        assert report.valid, report.reason
