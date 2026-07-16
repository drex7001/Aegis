"""Baseline — empty schema marker so `aegis db upgrade` is wired end-to-end (T2).
The claim-store schema lands in the next revision (T4, speckit spec 02).

Revision ID: 0001
Revises: None
"""
from __future__ import annotations

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
