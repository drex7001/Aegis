"""Append-only hash-chained audit log writer + verifier (T6, spec 02 §5)."""

from aegis.audit.chain import (
    GENESIS_HASH,
    VerificationReport,
    append,
    calculate_hash,
    canonical_event,
    canonical_json,
    verify,
)

__all__ = [
    "GENESIS_HASH",
    "VerificationReport",
    "append",
    "calculate_hash",
    "canonical_event",
    "canonical_json",
    "verify",
]
