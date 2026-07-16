"""Content-addressed evidence vault adapters (T5, ADR-007)."""

from aegis.evidence.vault import (
    EvidenceVault,
    IntegrityError,
    LocalFilesystemVault,
    MinioVault,
    ProvenanceEnvelope,
    ProvenanceRecord,
    StoredObject,
    VaultError,
    get_vault,
    object_key,
)

__all__ = [
    "EvidenceVault",
    "IntegrityError",
    "LocalFilesystemVault",
    "MinioVault",
    "ProvenanceEnvelope",
    "ProvenanceRecord",
    "StoredObject",
    "VaultError",
    "get_vault",
    "object_key",
]
