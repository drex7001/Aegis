"""Seed the golden corpus and measure real search against it (T68).

`quality.py` holds the scoring and is deliberately database-free, so the metric
arithmetic is unit-testable. This is the half that needs Postgres: it writes the
golden corpus through the same tables the product uses, runs the **real**
`search()` — same filters, same ranking, same pipeline — and maps the hits back
to golden ids so they can be scored.

Two choices worth stating.

**Each query is scoped to the resource group it is a target for.** The targets
in `targets.py` are stated *per resource type*, so "entity precision@5" is a
statement about the entity group. Letting a name query also return every claim
that mentions the name would measure something the target does not describe —
and would make the number improvable by narrowing the corpus rather than by
improving retrieval.

**The corpus is seeded with background names.** Twenty-odd fictional people who
should not match anything, so precision has something to lose. A golden set
containing only the answers measures nothing: every query would score 1.0 by
having nowhere else to go.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from aegis.api.auth import UserContext
from aegis.er.ledger import active_revision_id, open_membership
from aegis.ids import new_id
from aegis.ontology import Ontology
from aegis.projections.documents import BUILDER_VERSION
from aegis.search.pipeline import NORMALIZATION_VERSION, search_keys
from aegis.search.quality import (
    DEFAULT_GOLDEN_SET,
    GoldenSet,
    QualityReport,
    load_golden_set,
    measure,
)
from aegis.search.results import CLAIM_GROUP, DOCUMENT_GROUP
from aegis.search.service import search
from aegis.store import (
    Claim,
    DocumentTextProjection,
    Entity,
    Mention,
    Source,
    SourceRecord,
)

#: Ontology version stamped on golden claims. The corpus is never interpreted
#: against a released ontology — it exists to be searched — but the column is
#: NOT NULL and a fixture that lies about it would be a fixture teaching a
#: habit.
GOLDEN_ONTOLOGY_VERSION = "golden-set"


def seed(session: Session, golden: GoldenSet, *, ontology: Ontology) -> dict[str, str]:
    """Write the corpus and return `golden id -> database id`.

    Entities carry their names as `mention` rows because that is what makes a
    romanized query reach a name written in another script (ADR-035): the
    stored `latin_key`/`phonetic_key` are the only bridge, and an entity with a
    label and no mention would silently measure a narrower system.
    """
    ids: dict[str, str] = {}

    source_id, record_id = new_id("src"), new_id("rec")
    session.add(
        Source(source_id=source_id, source_type="open_source", name="T68 golden set")
    )
    session.add(
        SourceRecord(
            record_id=record_id,
            source_id=source_id,
            ingest_key=new_id("key"),
            content_hash="g" * 64,
            storage_uri="test://t68/golden",
            media_type="text/plain",
        )
    )
    session.flush()

    # The ledger's own accessor, not a hand-rolled query: `active_revision_id`
    # is what every write path uses, and a fixture that computed identity
    # revision differently would be measuring a different system.
    revision_id = active_revision_id(session)

    for entity in golden.entities:
        entity_id = new_id("ent")
        ids[entity.id] = entity_id
        session.add(
            Entity(entity_id=entity_id, entity_type=entity.type, label=entity.label)
        )
        session.flush()
        for name in entity.mentions:
            keys = search_keys(name)
            mention_id = new_id("men")
            session.add(
                Mention(
                    mention_id=mention_id,
                    record_id=record_id,
                    raw_text=name,
                    norm_key=keys.norm,
                    latin_key=keys.latin,
                    phonetic_key=keys.phonetic,
                    script=keys.script,
                    normalization_version=keys.version,
                )
            )
            session.flush()
            # The production write path, not a hand-built row: `open_membership`
            # owns the membership id and the revision, and a fixture that built
            # one itself would drift from the ledger the moment either changed.
            open_membership(session, mention_id=mention_id, entity_id=entity_id)
        # Every entity needs one readable claim, because an entity is reachable
        # only through a claim the caller may read (spec 11 §4.1). Without it
        # the corpus would be invisible to the very filter being measured.
        session.add(
            _claim(
                claim_id=new_id("clm"),
                subject_id=entity_id,
                predicate="has_role",
                value="fixture subject",
                record_id=record_id,
                revision_id=revision_id,
            )
        )

    for claim in golden.claims:
        claim_id = new_id("clm")
        ids[claim.id] = claim_id
        session.add(
            _claim(
                claim_id=claim_id,
                subject_id=ids[claim.subject],
                predicate=claim.predicate,
                value=claim.value,
                excerpt=claim.excerpt,
                handling=claim.handling,
                record_id=record_id,
                revision_id=revision_id,
            )
        )

    for document in golden.documents:
        projection_id = new_id("dtp")
        ids[document.id] = projection_id
        session.add(
            DocumentTextProjection(
                projection_id=projection_id,
                record_id=record_id,
                derivative_id=None,
                content_hash=new_id("hash"),
                text_body=document.text,
                handling_code=document.handling,
                handling_rank=ontology.handling_rank(document.handling),
                normalization_version=NORMALIZATION_VERSION,
                builder_version=BUILDER_VERSION,
            )
        )

    session.flush()
    return ids


def _claim(
    *,
    claim_id: str,
    subject_id: str,
    predicate: str,
    value: str | None,
    record_id: str,
    revision_id: int,
    excerpt: str | None = None,
    handling: str = "open",
) -> Claim:
    return Claim(
        claim_id=claim_id,
        subject_id=subject_id,
        predicate=predicate,
        object_value=value,
        excerpt=excerpt,
        assertion_type="reported",
        handling_code=handling,
        record_id=record_id,
        identity_revision_id=revision_id,
        ontology_version=GOLDEN_ONTOLOGY_VERSION,
        credibility_normalized="possibly_true",
        verification_status="unverified",
        recorded_at=datetime.now(timezone.utc),
    )


def _groups_for(resource: str, ontology: Ontology) -> list[str]:
    if resource == "claim":
        return [CLAIM_GROUP]
    if resource == "document":
        return [DOCUMENT_GROUP]
    return sorted(ontology.object_types)


def evaluate(
    session: Session,
    *,
    user: UserContext,
    ontology: Ontology,
    path: Path = DEFAULT_GOLDEN_SET,
    ids: dict[str, str] | None = None,
) -> QualityReport:
    """Seed, search, score. The report is the phase gate's input.

    `ids` re-scores an already-seeded corpus — which is how a regression test
    degrades the corpus between two runs and compares them. It is a mapping
    rather than a boolean for a reason discovered the hard way: an earlier
    version took `seed_corpus=False` and left the id map **empty**, so every
    query scored zero and a "regression" test passed without regressing
    anything.
    """
    golden, digest = load_golden_set(path)
    if ids is None:
        ids = seed(session, golden, ontology=ontology)
    session.flush()
    reverse = {database_id: golden_id for golden_id, database_id in ids.items()}

    def run_query(text: str) -> list[str]:
        query = next(item for item in golden.queries if item.q == text)
        hits, _ = search(
            session,
            query=text,
            user=user,
            ontology=ontology,
            types=_groups_for(query.resource, ontology),
            limit=50,
        )
        # Unmapped ids cannot occur with a truncated corpus, but dropping them
        # rather than raising keeps the harness usable against a database that
        # holds more than the golden set.
        return [reverse[hit.id] for hit in hits if hit.id in reverse]

    return measure(
        golden,
        digest,
        run_query=run_query,
        normalization_version=NORMALIZATION_VERSION,
    )


__all__ = ["GOLDEN_ONTOLOGY_VERSION", "evaluate", "seed"]
