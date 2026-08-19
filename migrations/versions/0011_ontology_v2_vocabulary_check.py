"""Composition 2.0.0's migration: prove the recorded vocabulary still resolves (T55).

Spec 01 §4 requires a major bump to ship a data migration. This one moves no
data, and the reason is worth stating rather than leaving a reader to infer from
an empty function.

The breaking change is the removal of `location.precision` (ADR-048). It was a
**property**, and properties in this system are claim-derived (spec 09 §6.4):
no column stores one, and no predicate ever carried this one. There is no row
anywhere that references it, so a migration that "migrated precision" would have
nothing to read and nothing to write.

What runs instead is the check that makes that claim true on **every** database
this upgrade touches, rather than only on the one it was written against. It
reads the vocabulary actually recorded — the distinct `claim.predicate` and
`entity.entity_type` values — and fails the upgrade, naming what it found, if
any of it is absent from the composed 2.0.0 registry.

Failing loudly is the point. Claims are immutable and stamp the ontology version
current at `recorded_at` (ADR-013), so a recorded predicate whose declaration
disappeared cannot be reinterpreted afterwards; it is simply unreadable, and
nothing would have told anyone. A major bump is exactly when that risk is real,
which is exactly when the check should run.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _recorded_vocabulary() -> tuple[set[str], set[str]]:
    """Predicates and entity types that exist in this database, non-retracted or not.

    Retracted claims are included deliberately: an auditor can still read them
    (`claim_filters`), so their vocabulary must still resolve.
    """
    bind = op.get_bind()
    predicates = {
        row[0] for row in bind.exec_driver_sql("SELECT DISTINCT predicate FROM claim") if row[0]
    }
    entity_types = {
        row[0]
        for row in bind.exec_driver_sql("SELECT DISTINCT entity_type FROM entity")
        if row[0]
    }
    return predicates, entity_types


def upgrade() -> None:
    # Imported here rather than at module scope: a migration must not make the
    # alembic environment depend on the ontology loader being importable, and
    # `alembic history` should not read YAML.
    from pathlib import Path

    from aegis.config import get_settings
    from aegis.ontology import load

    repo_root = Path(__file__).resolve().parents[2]
    declared = Path(get_settings().ontology_path)
    ontology = load(declared if declared.is_absolute() else repo_root / declared)
    predicates, entity_types = _recorded_vocabulary()

    missing_predicates = sorted(predicates - set(ontology.predicates))
    missing_types = sorted(entity_types - set(ontology.object_types))
    if missing_predicates or missing_types:
        raise RuntimeError(
            "ontology 2.0.0 does not declare vocabulary this database has already "
            "recorded, and claims are immutable (ADR-013) — the upgrade stops here "
            "rather than leave rows that cannot be read.\n"
            f"  predicates: {missing_predicates or 'none'}\n"
            f"  entity types: {missing_types or 'none'}\n"
            "Restore the declarations, or migrate the rows to vocabulary that "
            "exists, before upgrading."
        )


def downgrade() -> None:
    """Nothing to undo: the upgrade wrote nothing.

    Not an oversight — a check that passed leaves no trace, and re-declaring
    `location.precision` is an ontology change, not a schema one.
    """
