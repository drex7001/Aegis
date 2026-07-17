"""Legacy dataset migration (speckit T8, spec 02 §6, ADR-016).

This module is **the only place legacy vocabulary lives**: the curated
prototype's ConfidenceTag→grading map and the verb-remap table both sit here,
are validated against the ontology registry at run time, and are consumed by
exactly two callers — ``aegis migrate-legacy`` and the T10 snapshot test.

Grading of migrated claims (ADR-011):

* edge claims carry ``credibility_scheme='legacy-confidence-tag'`` with the
  original tag preserved and the normalized values from
  :data:`CONFIDENCE_TAG_GRADING`;
* node-derived claims had no legacy tag — aliases are stated plainly by the
  cited reporting (EXTRACTED-equivalent grading), affiliations are descriptive
  network labels (INFERRED-equivalent grading);
* a ``suspected_`` verb prefix is grading information, not vocabulary: the
  remapped claim's credibility is capped at the weaker of the mapped value and
  ``possibly_true`` (Article III).

Identity: one mention + one identity membership per legacy node, decided by
``rule:legacy-slug`` — the deterministic slug equality the prototype used.

Idempotency: sources and source records use deterministic ``src_legacy_*`` /
``rec_legacy_*`` ids; entities are found back through their mention's
``norm_key``; claims through a (subject, predicate, object, record, window)
existence probe.  Re-running the migration therefore changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import and_, or_, select, type_coerce
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from aegis.actions import ActionContext, ActionService, new_id
from aegis.audit import append as append_audit
from aegis.evidence import EvidenceVault, ProvenanceEnvelope, get_vault
from aegis.ontology import Ontology
from aegis.store import Claim, Entity, IdentityMembership, Mention, Source, SourceRecord

_REPO_ROOT = Path(__file__).resolve().parents[2]

LEGACY_SOURCE_SYSTEM = "legacy-migration"
LEGACY_SCHEME = "legacy-confidence-tag"
SNAPSHOT_RELPATH = Path("pipeline") / "real_dataset.py"
DECIDED_BY_RULE = "rule:legacy-slug"

# ConfidenceTag → (credibility_normalized, verification_status)  (spec 02 §6)
CONFIDENCE_TAG_GRADING: dict[str, tuple[str, str]] = {
    "EXTRACTED": ("confirmed", "record_confirmed"),
    "INFERRED": ("probably_true", "partially_corroborated"),
    "AMBIGUOUS": ("doubtful", "unverified"),
}

# Node-derived claims have no legacy tag; see module docstring.
ALIAS_GRADING = CONFIDENCE_TAG_GRADING["EXTRACTED"]
AFFILIATION_GRADING = CONFIDENCE_TAG_GRADING["INFERRED"]

SUSPECTED_CREDIBILITY_CAP = "possibly_true"


class LegacyMigrationError(RuntimeError):
    """The legacy dataset no longer reconciles with the remap table/ontology."""


@dataclass(frozen=True, slots=True)
class RemapTarget:
    """One claim produced from a legacy edge.

    ``window`` slices the legacy validity interval when a verb encodes a
    regime change: ``until_start`` ends at the legacy start date,
    ``from_start`` begins there (used by ``former_ally_turned_rival_of``).
    """

    predicate: str
    credibility_cap: str | None = None
    location_text: str | None = None
    window: str = "full"  # full | until_start | from_start


# Verb-remap table (ADR-016).  Verbs absent from this table map to the
# same-named ontology predicate; a verb that matches neither fails migration —
# forcing this table to stay complete.
VERB_REMAP: dict[str, tuple[RemapTarget, ...]] = {
    "co_conspirator_in_plot_with": (RemapTarget("conspired_with"),),
    "co_masterminded_attacks_with": (RemapTarget("masterminded_attack_with"),),
    "suspected_successor_leader_of": (
        RemapTarget("successor_leader_of", credibility_cap=SUSPECTED_CREDIBILITY_CAP),
    ),
    "suspected_foreign_is_contact_of": (
        RemapTarget("foreign_contact_of", credibility_cap=SUSPECTED_CREDIBILITY_CAP),
    ),
    "sibling_co_attacker_of": (
        RemapTarget("sibling_of"),
        RemapTarget("co_attacker_with"),
    ),
    "spousal_co_attacker_of": (
        RemapTarget("spouse_of"),
        RemapTarget("co_attacker_with"),
    ),
    "former_ally_turned_rival_of": (
        RemapTarget("allied_with", window="until_start"),
        RemapTarget("rival_of", window="from_start"),
    ),
    "avenging_rival_of": (RemapTarget("rival_of"),),
    "helped_establish_in_dubai": (
        RemapTarget("helped_establish_operations_of", location_text="Dubai"),
    ),
    "ran_narcotics_from_tamil_nadu_with": (
        RemapTarget("trafficked_narcotics_with", location_text="Tamil Nadu route"),
    ),
}

# Where predicate.category deliberately corrects a legacy layer, the ontology
# wins (spec 02 §6) — but only for the corrections declared here; anything else
# is drift and fails the migration.  Keyed by predicate → legacy layers the
# correction is accepted from.
EXPECTED_CATEGORY_CORRECTIONS: dict[str, frozenset[str]] = {
    "sibling_of": frozenset({"FINANCIAL", "IDEOLOGICAL"}),
    "spouse_of": frozenset({"IDEOLOGICAL"}),
    "partnered_with": frozenset({"TRANSNATIONAL"}),
}

# Legacy ExtractionMethod → claim.collection_method (spec 02 §6).
COLLECTION_METHODS = {"CURATED": "curated", "STRUCTURAL": "structural", "SEMANTIC": "semantic_llm"}


def weaker_credibility(ontology: Ontology, a: str, b: str) -> str:
    """The weaker of two normalized credibility values (later in the declared
    strongest→weakest scale)."""
    scale = ontology.grading.values_for("credibility")
    for value in (a, b):
        if value not in scale:
            raise LegacyMigrationError(
                f"grading.credibility.{value}: not declared (expected one of {scale})"
            )
    return max(a, b, key=scale.index)


def validate_legacy_maps(ontology: Ontology) -> None:
    """Every remap/grading target must exist in the ontology (ADR-016)."""
    credibility = set(ontology.grading.values_for("credibility"))
    verification = set(ontology.grading.values_for("verification"))
    for tag, (cred, verif) in CONFIDENCE_TAG_GRADING.items():
        if cred not in credibility:
            raise LegacyMigrationError(
                f"grading.credibility.{cred}: ConfidenceTag {tag} maps to an undeclared value"
            )
        if verif not in verification:
            raise LegacyMigrationError(
                f"grading.verification.{verif}: ConfidenceTag {tag} maps to an undeclared value"
            )
    if SUSPECTED_CREDIBILITY_CAP not in credibility:
        raise LegacyMigrationError(
            f"grading.credibility.{SUSPECTED_CREDIBILITY_CAP}: credibility cap is undeclared"
        )
    for verb, targets in VERB_REMAP.items():
        for target in targets:
            if target.predicate not in ontology.predicates:
                raise LegacyMigrationError(
                    f"predicates.{target.predicate}: verb-remap target for {verb!r} "
                    "is not declared in the ontology"
                )


def remap_edge(edge: Mapping[str, Any], ontology: Ontology) -> list[dict[str, Any]]:
    """One legacy edge (``real_graph.json`` schema) → one claim draft per remap
    target.  Pure — shared by the migration and the T10 snapshot test.

    Dates stay ISO strings (or None); the caller parses them as needed.
    """
    relation = edge["relation"]
    targets = VERB_REMAP.get(relation)
    if targets is None:
        if relation not in ontology.predicates:
            raise LegacyMigrationError(
                f"predicates.{relation}: legacy verb has no remap entry and no "
                "same-named ontology predicate (extend VERB_REMAP in "
                "aegis/migration/legacy.py)"
            )
        targets = (RemapTarget(relation),)

    tag = edge["confidence"]
    if tag not in CONFIDENCE_TAG_GRADING:
        raise LegacyMigrationError(f"confidence.{tag}: unknown legacy ConfidenceTag")
    credibility, verification = CONFIDENCE_TAG_GRADING[tag]
    legacy_layer = edge["layer"]
    start, end = edge.get("start_date"), edge.get("end_date")

    drafts: list[dict[str, Any]] = []
    for target in targets:
        spec = ontology.predicate(target.predicate)
        category = spec.category
        corrected = category is not None and category != legacy_layer.lower()
        if corrected and legacy_layer not in EXPECTED_CATEGORY_CORRECTIONS.get(
            target.predicate, frozenset()
        ):
            raise LegacyMigrationError(
                f"predicates.{target.predicate}.category: {category!r} does not match "
                f"legacy layer {legacy_layer!r} and is not a declared correction"
            )
        capped = target.credibility_cap is not None
        cred = (
            weaker_credibility(ontology, credibility, target.credibility_cap)
            if capped
            else credibility
        )
        if target.window == "until_start":
            valid_from, valid_to = None, start
        elif target.window == "from_start":
            valid_from, valid_to = start, None
        else:
            valid_from, valid_to = start, end
        drafts.append(
            {
                "predicate": target.predicate,
                "symmetric": spec.symmetric,
                "category": category,
                "credibility_original": tag,
                "credibility_normalized": cred,
                "verification_status": verification,
                "valid_from": valid_from,
                "valid_to": valid_to,
                # The edge's own location is better data than the remap default.
                "location_text": edge.get("location") or target.location_text,
                "split": len(targets) > 1,
                # A declared cap is reported even when the mapped value was
                # already weaker — the "suspected_" rule applied either way.
                "credibility_capped": capped,
                "category_corrected": corrected,
                "legacy_relation": relation,
                "legacy_layer": legacy_layer,
            }
        )
    return drafts


@dataclass
class MigrationReport:
    ontology_version: str = ""
    snapshot_hash: str = ""
    sources_created: int = 0
    sources_existing: int = 0
    records_created: int = 0
    records_existing: int = 0
    entities_created: int = 0
    entities_existing: int = 0
    mentions: int = 0
    node_claims_created: int = 0
    node_claims_existing: int = 0
    edge_claims_created: int = 0
    edge_claims_existing: int = 0
    edges_total: int = 0
    # one entry per legacy edge: what it became and why
    remap_log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def claims_created(self) -> int:
        return self.node_claims_created + self.edge_claims_created

    def to_dict(self) -> dict[str, Any]:
        return {
            "ontology_version": self.ontology_version,
            "snapshot_hash": self.snapshot_hash,
            "sources": {"created": self.sources_created, "existing": self.sources_existing},
            "records": {"created": self.records_created, "existing": self.records_existing},
            "entities": {"created": self.entities_created, "existing": self.entities_existing},
            "mentions": self.mentions,
            "node_claims": {
                "created": self.node_claims_created,
                "existing": self.node_claims_existing,
            },
            "edge_claims": {
                "created": self.edge_claims_created,
                "existing": self.edge_claims_existing,
            },
            "edges_total": self.edges_total,
            "splits": [e for e in self.remap_log if e["split"]],
            "credibility_caps": [e for e in self.remap_log if e["credibility_capped"]],
            "category_corrections": [e for e in self.remap_log if e["category_corrected"]],
            "remap_log": self.remap_log,
        }


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _claim_exists(
    session: Session,
    *,
    subject_id: str,
    predicate: str,
    record_id: str,
    object_id: str | None = None,
    object_value: Any | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
    symmetric: bool = False,
) -> bool:
    query = select(Claim.claim_id).where(
        Claim.predicate == predicate,
        Claim.record_id == record_id,
        Claim.retracted_at.is_(None),
        Claim.valid_from.is_(None) if valid_from is None else Claim.valid_from == valid_from,
        Claim.valid_to.is_(None) if valid_to is None else Claim.valid_to == valid_to,
    )
    if object_id is None:
        # object_value is JSONB; bind the literal through the JSONB processor so
        # the comparison is jsonb = jsonb (json.dumps matches how it was stored).
        query = query.where(
            Claim.subject_id == subject_id,
            Claim.object_value == type_coerce(object_value, JSONB()),
        )
    elif symmetric:
        query = query.where(
            or_(
                and_(Claim.subject_id == subject_id, Claim.object_id == object_id),
                and_(Claim.subject_id == object_id, Claim.object_id == subject_id),
            )
        )
    else:
        query = query.where(
            Claim.subject_id == subject_id, Claim.object_id == object_id
        )
    return session.scalar(query.limit(1)) is not None


def _connector_version() -> str:
    try:
        from importlib.metadata import version

        return version("aegis")
    except Exception:  # pragma: no cover - metadata missing in odd installs
        return "unknown"


def migrate(
    session: Session,
    *,
    ontology: Ontology | None = None,
    vault: EvidenceVault | None = None,
    actor: str = "system:migrate-legacy",
    snapshot_path: Path | None = None,
) -> MigrationReport:
    """Migrate the curated legacy dataset into the canonical store.

    Runs in one transaction on ``session``; idempotent (see module docstring).
    """
    # Imported here: the legacy prototype lives beside the package in the repo,
    # not inside the installed distribution.
    from pipeline.models import slugify
    from pipeline.real_dataset import SOURCES, build_curated_network

    service = ActionService(session, ontology)
    ontology = service.ontology
    validate_legacy_maps(ontology)
    vault = vault or get_vault()
    context = ActionContext(actor=actor, purpose="phase-1 legacy migration")
    report = MigrationReport(ontology_version=ontology.version)

    snapshot_path = snapshot_path or _REPO_ROOT / SNAPSHOT_RELPATH
    snapshot = snapshot_path.read_bytes()
    stored = vault.put(
        snapshot,
        ProvenanceEnvelope(
            source_system=LEGACY_SOURCE_SYSTEM,
            original_filename=SNAPSHOT_RELPATH.as_posix(),
            connector="aegis.migration.legacy",
            connector_version=_connector_version(),
            operator=actor,
            collection_policy="public-osint-v1",
            notes="curated dataset snapshot backing the migrated source records",
        ),
        media_type="text/x-python",
    )
    report.snapshot_hash = stored.content_hash

    network = build_curated_network()
    dangling = network.dangling_edges()
    if dangling:
        raise LegacyMigrationError(
            f"legacy dataset has {len(dangling)} dangling edge(s); refusing to migrate"
        )
    report.edges_total = len(network.edges)

    with session.begin():
        # 1. Sources + source records (deterministic ids ⇒ idempotent).
        publication_to_record: dict[str, str] = {}
        for key, (publication, url) in SOURCES.items():
            source_id = f"src_legacy_{key}"
            record_id = f"rec_legacy_{key}"
            if session.get(Source, source_id) is None:
                session.add(
                    Source(
                        source_id=source_id,
                        source_type="open_source",
                        name=publication,
                        url=url,
                        notes=f"legacy migration citation key: {key}",
                    )
                )
                report.sources_created += 1
            else:
                report.sources_existing += 1
            if session.get(SourceRecord, record_id) is None:
                ingest_key = sha256(
                    f"{LEGACY_SOURCE_SYSTEM}|{key}|{stored.content_hash}".encode()
                ).hexdigest()
                session.add(
                    SourceRecord(
                        record_id=record_id,
                        source_id=source_id,
                        ingest_key=ingest_key,
                        content_hash=stored.content_hash,
                        storage_uri=stored.storage_uri,
                        media_type="text/x-python",
                        handling_code="open",
                        status="processed",
                        provenance={
                            "source_system": LEGACY_SOURCE_SYSTEM,
                            "original_filename": SNAPSHOT_RELPATH.as_posix(),
                            "connector": "aegis.migration.legacy",
                            "connector_version": _connector_version(),
                            "operator": actor,
                            "source_url": url,
                            "collection_policy": "public-osint-v1",
                            "legacy_source_key": key,
                        },
                    )
                )
                report.records_created += 1
            else:
                report.records_existing += 1
            publication_to_record[publication] = record_id
        session.flush()

        def record_for(publication: str, what: str) -> str:
            try:
                return publication_to_record[publication]
            except KeyError:
                raise LegacyMigrationError(
                    f"{what}: source citation {publication!r} is not in "
                    "pipeline.real_dataset.SOURCES"
                ) from None

        # 2. Entities — one mention + one membership per legacy node.
        entity_by_slug: dict[str, str] = {}
        for node in network.nodes:
            record_id = record_for(node.source_file, f"node {node.node_id}")
            existing = session.execute(
                select(Entity)
                .join(IdentityMembership, IdentityMembership.entity_id == Entity.entity_id)
                .join(Mention, Mention.mention_id == IdentityMembership.mention_id)
                .where(
                    Mention.norm_key == node.node_id,
                    Mention.record_id == record_id,
                    IdentityMembership.valid_to.is_(None),
                )
                .limit(1)
            ).scalar_one_or_none()
            if existing is not None:
                entity_by_slug[node.node_id] = existing.entity_id
                report.entities_existing += 1
                continue
            entity = Entity(
                entity_id=new_id("ent"),
                entity_type=node.node_type.value.lower(),
                label=node.name,
            )
            mention = Mention(
                mention_id=new_id("men"),
                record_id=record_id,
                raw_text=node.name,
                norm_key=node.node_id,
                context=node.source_excerpt,
            )
            # These tables carry FK columns but no ORM relationship(), so the
            # unit of work will not order the membership insert after its parents
            # on its own — flush entity + mention first (spec 02 §2 FKs).
            session.add_all([entity, mention])
            session.flush()
            session.add(
                IdentityMembership(
                    membership_id=new_id("mem"),
                    mention_id=mention.mention_id,
                    entity_id=entity.entity_id,
                    decided_by=DECIDED_BY_RULE,
                    decision_note="deterministic legacy node_id slug",
                )
            )
            entity_by_slug[node.node_id] = entity.entity_id
            report.entities_created += 1
        report.mentions = report.entities_created + report.entities_existing
        session.flush()

        # 3. Node-derived claims: aliases and affiliations.
        for node in network.nodes:
            record_id = record_for(node.source_file, f"node {node.node_id}")
            subject_id = entity_by_slug[node.node_id]
            # Aliases migrate verbatim, even when one equals the display name —
            # the source listed it as an alias, and the projection round-trips it.
            for alias in node.aliases:
                if _claim_exists(
                    session,
                    subject_id=subject_id,
                    predicate="known_as",
                    record_id=record_id,
                    object_value=alias,
                ):
                    report.node_claims_existing += 1
                    continue
                service.record_claim(
                    context,
                    subject_id=subject_id,
                    predicate="known_as",
                    object_value=alias,
                    record_id=record_id,
                    assertion_type="reported",
                    collection_method=COLLECTION_METHODS["CURATED"],
                    credibility_normalized=ALIAS_GRADING[0],
                    verification_status=ALIAS_GRADING[1],
                    excerpt=node.source_excerpt,
                )
                report.node_claims_created += 1
            for affiliation in node.affiliations:
                org_id = entity_by_slug.get(slugify(affiliation))
                object_kwargs: dict[str, Any] = (
                    {"object_id": org_id} if org_id else {"object_value": affiliation}
                )
                if _claim_exists(
                    session,
                    subject_id=subject_id,
                    predicate="affiliated_with",
                    record_id=record_id,
                    object_id=org_id,
                    object_value=None if org_id else affiliation,
                ):
                    report.node_claims_existing += 1
                    continue
                service.record_claim(
                    context,
                    subject_id=subject_id,
                    predicate="affiliated_with",
                    record_id=record_id,
                    assertion_type="reported",
                    collection_method=COLLECTION_METHODS["CURATED"],
                    credibility_normalized=AFFILIATION_GRADING[0],
                    verification_status=AFFILIATION_GRADING[1],
                    excerpt=node.source_excerpt,
                    **object_kwargs,
                )
                report.node_claims_created += 1

        # 4. Edge claims via the verb-remap table.
        for edge in network.edges:
            record_id = record_for(edge.source_file, f"edge {edge.source}->{edge.target}")
            subject_id = entity_by_slug[edge.source]
            object_id = entity_by_slug[edge.target]
            edge_json = edge.model_dump(mode="json")
            drafts = remap_edge(edge_json, ontology)
            produced: list[str] = []
            for draft in drafts:
                valid_from = _parse_date(draft["valid_from"])
                valid_to = _parse_date(draft["valid_to"])
                if _claim_exists(
                    session,
                    subject_id=subject_id,
                    predicate=draft["predicate"],
                    record_id=record_id,
                    object_id=object_id,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    symmetric=draft["symmetric"],
                ):
                    report.edge_claims_existing += 1
                    produced.append(draft["predicate"])
                    continue
                service.record_claim(
                    context,
                    subject_id=subject_id,
                    predicate=draft["predicate"],
                    object_id=object_id,
                    record_id=record_id,
                    assertion_type="reported",
                    collection_method=COLLECTION_METHODS[edge.extraction_method.value],
                    credibility_scheme=LEGACY_SCHEME,
                    credibility_original=draft["credibility_original"],
                    credibility_normalized=draft["credibility_normalized"],
                    verification_status=draft["verification_status"],
                    valid_from=valid_from,
                    valid_to=valid_to,
                    location_text=draft["location_text"],
                    excerpt=edge.source_excerpt,
                )
                report.edge_claims_created += 1
                produced.append(draft["predicate"])
            report.remap_log.append(
                {
                    "source": edge.source,
                    "target": edge.target,
                    "legacy_relation": edge.relation,
                    "legacy_layer": edge.layer.value,
                    "confidence": edge.confidence.value,
                    "predicates": produced,
                    "split": len(drafts) > 1,
                    "credibility_capped": any(d["credibility_capped"] for d in drafts),
                    "category_corrected": any(d["category_corrected"] for d in drafts),
                }
            )

        # One summary entry for the run itself; per-claim audits were written by
        # record_claim inside the same transaction.
        append_audit(
            session,
            actor=actor,
            session_id=None,
            purpose=context.purpose,
            case_id=None,
            action="migrate_legacy",
            resource_type="source_record",
            resource_id=f"sha256:{stored.content_hash}",
            decision="allow",
            detail={
                "entities_created": report.entities_created,
                "claims_created": report.claims_created,
                "edges_total": report.edges_total,
                "ontology_version": report.ontology_version,
            },
        )

    return report
