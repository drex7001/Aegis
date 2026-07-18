"""Feature frame for the Splink run (T19; spec 05 §3.2, H-07).

One row per mention, carrying everything the model compares.  Two of these
columns are the ones that make the run *reproducible* rather than merely
repeatable:

* **`associates`** is computed from a projection snapshot whose id is recorded
  on every candidate the run emits.  A graph-context feature read from a live
  projection would score differently on every rebuild, and nobody could say
  which graph a stored score was computed against (H-07).
* **`date_of_birth`** is included so a *conflict* can act as negative evidence.
  Agreement between two dates is weak — many people share a birthday — but
  disagreement between two stated dates is strong, which is why it gets its own
  comparison level rather than being folded into a name score.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegis.er.normalize import detect_script, norm_key
from aegis.er.translit import latin_key, phonetic_key, script_key
from aegis.store import Claim, IdentityMembership, Mention

#: Predicate whose literal object is an alternate name for the subject.
ALIAS_PREDICATE = "known_as"
#: Predicate linking a person to an organization or a literal affiliation.
AFFILIATION_PREDICATE = "affiliated_with"
#: Predicate carrying a stated date of birth.
DOB_PREDICATE = "born_on"


@dataclass(frozen=True, slots=True)
class FeatureFrame:
    """The comparison rows plus the snapshot they were computed against."""

    rows: list[dict[str, Any]]
    graph_snapshot_id: str

    def __len__(self) -> int:
        return len(self.rows)


def graph_snapshot_id(session: Session) -> str:
    """A content digest of the association graph the features were read from.

    Recording *which* graph a score came from is what makes the score
    reproducible; a timestamp would only say when it ran (H-07).
    """
    edges = session.execute(
        select(Claim.subject_id, Claim.object_id, Claim.predicate)
        .where(Claim.object_id.isnot(None), Claim.retracted_at.is_(None))
        .order_by(Claim.subject_id, Claim.object_id, Claim.predicate)
    ).all()
    digest = sha256()
    for subject, obj, predicate in edges:
        digest.update(f"{subject}|{obj}|{predicate}\n".encode())
    return f"sha256:{digest.hexdigest()[:32]}"


def _associates(session: Session) -> dict[str, list[str]]:
    """Entity → the entities it is linked to by any non-retracted claim."""
    associates: dict[str, set[str]] = {}
    for subject, obj in session.execute(
        select(Claim.subject_id, Claim.object_id).where(
            Claim.object_id.isnot(None), Claim.retracted_at.is_(None)
        )
    ):
        associates.setdefault(subject, set()).add(obj)
        associates.setdefault(obj, set()).add(subject)
    return {entity: sorted(values) for entity, values in associates.items()}


def _literal_claims(session: Session, predicate: str) -> dict[str, list[str]]:
    """Entity → the literal object values it carries for one predicate."""
    values: dict[str, set[str]] = {}
    for subject, value in session.execute(
        select(Claim.subject_id, Claim.object_value).where(
            Claim.predicate == predicate,
            Claim.object_value.isnot(None),
            Claim.retracted_at.is_(None),
        )
    ):
        if isinstance(value, str):
            values.setdefault(subject, set()).add(value)
    return {entity: sorted(items) for entity, items in values.items()}


def _entity_affiliations(session: Session) -> dict[str, list[str]]:
    """Entity → affiliations, whether recorded as an org entity or a literal."""
    affiliations: dict[str, set[str]] = {}
    for subject, obj, value in session.execute(
        select(Claim.subject_id, Claim.object_id, Claim.object_value).where(
            Claim.predicate == AFFILIATION_PREDICATE, Claim.retracted_at.is_(None)
        )
    ):
        key = obj if obj is not None else (value if isinstance(value, str) else None)
        if key is not None:
            affiliations.setdefault(subject, set()).add(norm_key(key))
    return {entity: sorted(items) for entity, items in affiliations.items()}


def build_feature_frame(session: Session) -> FeatureFrame:
    """One row per mention that currently belongs to an entity.

    Unresolved mentions are excluded: every feature except the name itself is
    reached *through* the entity, so an unattached mention would be compared on
    its name alone and score misleadingly high against anything similar.
    """
    entity_by_mention = {
        mention_id: entity_id
        for mention_id, entity_id in session.execute(
            select(IdentityMembership.mention_id, IdentityMembership.entity_id).where(
                IdentityMembership.closed_revision_id.is_(None)
            )
        )
    }
    associates = _associates(session)
    aliases = _literal_claims(session, ALIAS_PREDICATE)
    dobs = _literal_claims(session, DOB_PREDICATE)
    affiliations = _entity_affiliations(session)

    rows: list[dict[str, Any]] = []
    for mention in session.scalars(select(Mention).order_by(Mention.mention_id)):
        entity_id = entity_by_mention.get(mention.mention_id)
        if entity_id is None:
            continue
        stated_dobs = dobs.get(entity_id, [])
        rows.append(
            {
                "unique_id": mention.mention_id,
                "entity_id": entity_id,
                "latin_key": latin_key(mention.raw_text),
                "script_key": script_key(mention.raw_text),
                "phonetic_key": phonetic_key(mention.raw_text),
                "norm_key": mention.norm_key,
                "script": mention.script or detect_script(mention.raw_text),
                "alias_keys": [latin_key(alias) for alias in aliases.get(entity_id, [])],
                "affiliations": affiliations.get(entity_id, []),
                "associates": associates.get(entity_id, []),
                # Only an unambiguous single stated date can conflict.  Where a
                # person carries two (the ontology says conflicts: preserve),
                # the entity already disagrees with itself and no comparison
                # against it would mean anything.
                "date_of_birth": stated_dobs[0] if len(stated_dobs) == 1 else None,
            }
        )
    return FeatureFrame(rows=rows, graph_snapshot_id=graph_snapshot_id(session))


__all__ = [
    "AFFILIATION_PREDICATE",
    "ALIAS_PREDICATE",
    "DOB_PREDICATE",
    "FeatureFrame",
    "build_feature_frame",
    "graph_snapshot_id",
]
