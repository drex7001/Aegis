"""Deterministic fictional corpus for the Phase 2 MVP gate (T25).

This is application-owned demo data, not a test factory.  The same loader is
used by the CLI, integration smoke, and (in T27) the documented analyst demo.
Machine extraction still stops at the review queue; the small canonical
baseline is explicitly marked ``curated`` and written through the ordinary
human action service.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService
from aegis.er.canonical import rebuild_canonical_map
from aegis.er.mentions import extract_mentions
from aegis.er.rules import run_rules
from aegis.er.splink_job import run_splink
from aegis.evidence import EvidenceVault
from aegis.ingestion.service import (
    IngestionError,
    land_bytes,
    run_semantic_pass,
    run_structural_pass,
)
from aegis.projections import build_full_graph, rebuild_edge_projection, write_outputs
from aegis.store import CaseFile, Claim, ClaimRelation, Mention, Source, SourceRecord

MVP_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "data" / "sample" / "mvp"
MVP_SOURCE_ID = "src_mvp_fixture"
MVP_SOURCE_SYSTEM = "aegis-mvp-fixture"
MVP_ACTOR = "user:mvp-demo-operator"


class MvpFixtureError(RuntimeError):
    """The committed fixture is invalid or cannot safely run here."""


class _Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    path: str
    original_filename: str
    handling_code: Literal["open", "restricted", "sensitive"] = "open"
    producer: Literal["structural", "semantic"] | None = None
    cached_output: str | None = None
    mentions: dict[str, str] = Field(default_factory=dict)


class _CuratedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    document: str
    mention: str
    entity_key: str
    entity_type: Literal[
        "person", "organization", "location", "vehicle", "phone_number"
    ]
    predicate: str
    object_value: str
    handling_code: Literal["open", "restricted", "sensitive"] = "open"
    excerpt: str | None = None

    @property
    def claim_id(self) -> str:
        return f"clm_mvp_{self.key}"


class _ClaimRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_claim: str
    to_claim: str
    relation: Literal["corroborates", "contradicts"]


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    documents: list[_Document]
    curated_claims: list[_CuratedClaim]
    claim_relations: list[_ClaimRelation] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MvpFixtureReport:
    records: int
    quarantined: int
    suggestions: int
    curated_claims: int
    rule_candidates: int
    splink_candidates: int
    projection_edges: int


@dataclass(frozen=True, slots=True)
class MvpResetReport:
    projection_edges: int


def _fixture_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise MvpFixtureError(f"fixture path escapes its root: {relative!r}") from exc
    if not candidate.is_file():
        raise MvpFixtureError(f"fixture file does not exist: {relative!r}")
    return candidate


def _load_manifest(root: Path) -> _Manifest:
    path = _fixture_path(root, "manifest.json")
    try:
        manifest = _Manifest.model_validate_json(path.read_bytes())
    except Exception as exc:
        raise MvpFixtureError(f"invalid MVP manifest: {exc}") from exc
    keys = [document.key for document in manifest.documents]
    if len(keys) != len(set(keys)):
        raise MvpFixtureError("document keys must be unique")
    claim_keys = [claim.key for claim in manifest.curated_claims]
    if len(claim_keys) != len(set(claim_keys)):
        raise MvpFixtureError("curated claim keys must be unique")
    return manifest


def _ensure_source(session: Session) -> Source:
    source = session.get(Source, MVP_SOURCE_ID)
    if source is None:
        source = Source(
            source_id=MVP_SOURCE_ID,
            source_type="open_source",
            name="Fictional MVP fixture",
            reliability_scheme="admiralty",
            reliability_original="A",
            reliability_normalized="reliable",
            notes="Deterministic fictional corpus; never use as real intelligence.",
        )
        session.add(source)
        session.flush()
    return source


def load_mvp_fixture(
    session: Session,
    vault: EvidenceVault,
    *,
    root: Path = MVP_FIXTURE_ROOT,
    actor: str = MVP_ACTOR,
    output_dir: Path | None = None,
) -> MvpFixtureReport:
    """Land, extract, seed the curated baseline, and emit ER candidates.

    Re-running is idempotent: landing, mention extraction, suggestions,
    stable curated claim ids, claim relations, and candidate producers all
    reuse or skip their existing rows.
    """

    if not actor.startswith("user:") or not actor.removeprefix("user:").strip():
        raise MvpFixtureError(
            "the curated fixture baseline requires a human actor in user:<id> form"
        )

    manifest = _load_manifest(root)
    _ensure_source(session)
    records: dict[str, SourceRecord] = {}
    mentions: dict[tuple[str, str], Mention] = {}
    suggestions_created = 0
    quarantined = 0

    for document in manifest.documents:
        data = _fixture_path(root, document.path).read_bytes()
        landing = land_bytes(
            session,
            vault,
            data=data,
            original_filename=document.original_filename,
            operator=actor,
            source_id=MVP_SOURCE_ID,
            source_system=MVP_SOURCE_SYSTEM,
            media_type="text/plain",
            collection_policy="fictional-demo-v1",
            retention_class="demo-ephemeral",
            authority_ref="fixture:T25",
            notes=f"T25 fixture document {document.key}",
            handling_code=document.handling_code,
        )
        record = landing.record
        records[document.key] = record
        if record.status == "quarantined":
            quarantined += 1
            continue

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MvpFixtureError(f"{document.path!r} is not UTF-8 text") from exc

        if document.producer == "structural":
            suggestions_created += len(
                run_structural_pass(session, record=record, text=text, actor=actor)
            )
        elif document.producer == "semantic":
            if document.cached_output is None:
                raise MvpFixtureError(
                    f"semantic document {document.key!r} has no cached_output"
                )
            try:
                suggestions_created += len(
                    run_semantic_pass(
                        session,
                        vault,
                        record=record,
                        text=text,
                        actor=actor,
                        cached_output=_fixture_path(
                            root, document.cached_output
                        ).read_bytes(),
                    )
                )
            except IngestionError as exc:
                raise MvpFixtureError(
                    f"cached semantic output for {document.key!r} is invalid: {exc}"
                ) from exc
        elif document.cached_output is not None:
            raise MvpFixtureError(
                f"document {document.key!r} has cached_output without semantic producer"
            )

        extraction = extract_mentions(
            session,
            record=record,
            text=text,
            names=document.mentions,
        )
        for reference, mention in extraction.by_ref.items():
            mentions[(document.key, reference)] = mention

    service = ActionService(session)
    context = ActionContext(actor=actor, purpose="load fictional MVP fixture")
    entity_by_key: dict[str, str] = {}
    claims_by_key: dict[str, Claim] = {}
    curated_created = 0

    for claim_spec in manifest.curated_claims:
        record = records.get(claim_spec.document)
        mention = mentions.get((claim_spec.document, claim_spec.mention))
        if record is None or mention is None:
            raise MvpFixtureError(
                f"claim {claim_spec.key!r} references an unknown document/mention"
            )
        existing = session.get(Claim, claim_spec.claim_id)
        if existing is not None:
            entity_by_key.setdefault(claim_spec.entity_key, existing.subject_id)
            claims_by_key[claim_spec.key] = existing
            continue
        claim = service.record_claim(
            context,
            claim_id=claim_spec.claim_id,
            subject_id=entity_by_key.get(claim_spec.entity_key),
            subject_mention_id=mention.mention_id,
            subject_entity_type=claim_spec.entity_type,
            predicate=claim_spec.predicate,
            object_value=claim_spec.object_value,
            assertion_type="reported",
            collection_method="curated",
            record_id=record.record_id,
            excerpt=claim_spec.excerpt,
            credibility_scheme="fixture-v1",
            credibility_original="curated",
            credibility_normalized="confirmed",
            verification_status="record_confirmed",
            handling_code=claim_spec.handling_code,
        )
        entity_by_key[claim_spec.entity_key] = claim.subject_id
        claims_by_key[claim_spec.key] = claim
        curated_created += 1

    for relation_spec in manifest.claim_relations:
        left = claims_by_key.get(relation_spec.from_claim)
        right = claims_by_key.get(relation_spec.to_claim)
        if left is None or right is None:
            raise MvpFixtureError("claim relation references an unknown curated claim")
        existing = session.get(
            ClaimRelation,
            (left.claim_id, right.claim_id, relation_spec.relation),
        )
        if existing is None:
            service.link_claims(
                context,
                from_claim=left.claim_id,
                to_claim=right.claim_id,
                relation=relation_spec.relation,
            )

    rules = run_rules(session, ontology=service.ontology)
    splink = run_splink(session)
    identity = rebuild_canonical_map(session)
    del identity
    projection = rebuild_edge_projection(session, ontology=service.ontology)
    graph = build_full_graph(session, service.ontology)
    session.commit()
    if output_dir is not None:
        write_outputs(graph, output_dir)

    return MvpFixtureReport(
        records=len(records),
        quarantined=quarantined,
        suggestions=suggestions_created,
        curated_claims=curated_created,
        rule_candidates=rules.emitted,
        splink_candidates=splink.emitted,
        projection_edges=projection.edges,
    )


_TRUNCATE_DOMAIN_TABLES = (
    "TRUNCATE claim_relation, review_queue, claim, entity_canonical_map, "
    "identity_negative_constraint, er_candidate, identity_decision, "
    "identity_revision, identity_membership, mention, evidence_item, "
    "custody_event, derivative, source_record, source, case_member, case_file, "
    "entity, authz_outbox CASCADE"
)


def reset_mvp_fixture(
    session: Session,
    *,
    output_dir: Path | None = None,
) -> MvpResetReport:
    """Restore a fixture-only local database to its migrated empty baseline.

    The operation refuses any non-fixture record, non-fixture source, or case.
    It is intentionally not a selective delete: canonical claims and audit
    rows are append-only in a real store.  A demo reset is a disposable-store
    restore, so it clears the complete domain and audit state in one guarded
    transaction, then recreates revision 0 and all empty projections.
    """

    foreign_records = session.scalar(
        select(sa.func.count())
        .select_from(SourceRecord)
        .where(
            SourceRecord.provenance["source_system"].astext.is_distinct_from(
                MVP_SOURCE_SYSTEM
            )
        )
    )
    foreign_sources = session.scalar(
        select(sa.func.count())
        .select_from(Source)
        .where(Source.source_id != MVP_SOURCE_ID)
    )
    cases = session.scalar(select(sa.func.count()).select_from(CaseFile))
    if foreign_records or foreign_sources or cases:
        raise MvpFixtureError(
            "reset refused: database contains non-fixture state; use the governed "
            "backup/restore procedure instead"
        )

    session.execute(sa.text("TRUNCATE audit_log CASCADE"))
    session.execute(sa.text(_TRUNCATE_DOMAIN_TABLES))
    session.execute(
        sa.text(
            "INSERT INTO identity_revision (revision_id, decision_id) VALUES (0, NULL) "
            "ON CONFLICT DO NOTHING"
        )
    )
    from aegis.config import get_settings
    from aegis.ontology import load

    ontology_path = Path(get_settings().ontology_path)
    if not ontology_path.is_absolute():
        ontology_path = Path(__file__).resolve().parents[2] / ontology_path
    ontology = load(ontology_path)
    rebuild_canonical_map(session)
    projection = rebuild_edge_projection(session, ontology=ontology)
    graph = build_full_graph(session, ontology)
    session.commit()
    if output_dir is not None:
        write_outputs(graph, output_dir)
    return MvpResetReport(projection_edges=projection.edges)


__all__ = [
    "MVP_ACTOR",
    "MVP_FIXTURE_ROOT",
    "MVP_SOURCE_ID",
    "MVP_SOURCE_SYSTEM",
    "MvpFixtureError",
    "MvpFixtureReport",
    "MvpResetReport",
    "load_mvp_fixture",
    "reset_mvp_fixture",
]
