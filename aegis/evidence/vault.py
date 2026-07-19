"""Immutable, content-addressed storage for originals and derivatives.

Both adapters use the ADR-007 key layout ``sha256/<first2>/<hash>``.  A JSON
sidecar at ``<key>.provenance.json`` records the content hash and the provenance
envelope without mixing metadata into the original bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROVENANCE_SUFFIX = ".provenance.json"


class VaultError(RuntimeError):
    """Base error for evidence-vault operations."""


class IntegrityError(VaultError):
    """Stored bytes no longer match their content-addressed key."""


class ProvenanceEnvelope(BaseModel):
    """Provenance supplied at raw landing (spec 04 §2).

    The required fields identify who collected an artifact and which connector
    produced it.  Additional connector-specific fields are preserved.
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    source_system: str = Field(min_length=1)
    original_filename: str = Field(min_length=1)
    connector: str = Field(min_length=1)
    connector_version: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    source_url: str | None = None
    collection_policy: str | None = None
    retention_class: str | None = None
    authority_ref: str | None = None
    authority_valid_from: datetime | None = None
    authority_valid_to: datetime | None = None
    schema_version: str | None = None
    notes: str | None = None


class ProvenanceRecord(BaseModel):
    """Canonical JSON sidecar stored beside a content object."""

    model_config = ConfigDict(frozen=True)

    format_version: str = "aegis.provenance/v1"
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    stored_at: datetime
    envelope: ProvenanceEnvelope


@dataclass(frozen=True, slots=True)
class StoredObject:
    content_hash: str
    storage_uri: str
    provenance_uri: str
    size_bytes: int
    created: bool


@runtime_checkable
class EvidenceVault(Protocol):
    def put(
        self,
        data: bytes | bytearray | memoryview,
        provenance: ProvenanceEnvelope,
        *,
        media_type: str | None = None,
    ) -> StoredObject: ...

    def get(self, content_hash: str) -> bytes: ...

    def get_provenance(self, content_hash: str) -> ProvenanceRecord: ...

    def exists(self, content_hash: str) -> bool: ...


def _normalize_hash(content_hash: str) -> str:
    digest = content_hash.removeprefix("sha256:").lower()
    if not _SHA256_RE.fullmatch(digest):
        raise ValueError("content hash must be 64 hexadecimal SHA-256 characters")
    return digest


def object_key(content_hash: str) -> str:
    digest = _normalize_hash(content_hash)
    return f"sha256/{digest[:2]}/{digest}"


def _provenance_key(content_hash: str) -> str:
    return f"{object_key(content_hash)}{_PROVENANCE_SUFFIX}"


def _record_bytes(record: ProvenanceRecord) -> bytes:
    payload = record.model_dump(mode="json", exclude_none=True)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _parse_record(data: bytes, expected_hash: str) -> ProvenanceRecord:
    try:
        record = ProvenanceRecord.model_validate_json(data)
    except Exception as exc:
        raise IntegrityError("stored provenance envelope is invalid") from exc
    if record.content_hash != expected_hash:
        raise IntegrityError(
            f"provenance hash mismatch: expected {expected_hash}, got {record.content_hash}"
        )
    return record


class LocalFilesystemVault:
    """Local development vault with atomic, no-overwrite writes."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def _path(self, key: str) -> Path:
        return self.root.joinpath(*key.split("/"))

    @staticmethod
    def _write_once(path: Path, data: bytes) -> bool:
        """Atomically link a complete temp file into place without replacement."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temp_path, path)
                return True
            except FileExistsError:
                return False
        finally:
            temp_path.unlink(missing_ok=True)

    def put(
        self,
        data: bytes | bytearray | memoryview,
        provenance: ProvenanceEnvelope,
        *,
        media_type: str | None = None,
    ) -> StoredObject:
        del media_type  # The canonical envelope carries source media metadata when needed.
        payload = bytes(data)
        digest = sha256(payload).hexdigest()
        content_path = self._path(object_key(digest))
        provenance_path = self._path(_provenance_key(digest))

        created = self._write_once(content_path, payload)
        if not created:
            self.get(digest)
        record = ProvenanceRecord(
            content_hash=digest,
            size_bytes=len(payload),
            stored_at=datetime.now(UTC),
            envelope=provenance,
        )
        provenance_created = self._write_once(provenance_path, _record_bytes(record))
        if not provenance_created:
            self.get_provenance(digest)

        return StoredObject(
            content_hash=digest,
            storage_uri=content_path.as_uri(),
            provenance_uri=provenance_path.as_uri(),
            size_bytes=len(payload),
            created=created,
        )

    def get(self, content_hash: str) -> bytes:
        digest = _normalize_hash(content_hash)
        payload = self._path(object_key(digest)).read_bytes()
        actual = sha256(payload).hexdigest()
        if actual != digest:
            raise IntegrityError(f"content hash mismatch: expected {digest}, got {actual}")
        return payload

    def get_provenance(self, content_hash: str) -> ProvenanceRecord:
        digest = _normalize_hash(content_hash)
        return _parse_record(self._path(_provenance_key(digest)).read_bytes(), digest)

    def exists(self, content_hash: str) -> bool:
        digest = _normalize_hash(content_hash)
        return self._path(object_key(digest)).is_file()


class MinioVault:
    """MinIO/S3 adapter using the same content keys as the filesystem vault."""

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        secure: bool = False,
        client: Any | None = None,
        create_bucket: bool = False,
    ) -> None:
        if client is None:
            try:
                from minio import Minio
            except ImportError as exc:  # pragma: no cover - dependency is in pyproject
                raise VaultError("MinIO backend requires the 'minio' package") from exc
            client = Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
            )
        self.client = client
        self.bucket = bucket
        if create_bucket and not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def _exists_key(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, key)
            return True
        except Exception as exc:
            if getattr(exc, "code", None) in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return False
            if getattr(exc, "status", None) == 404:
                return False
            raise

    def _put_once(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> bool:
        if self._exists_key(key):
            return False
        self.client.put_object(
            self.bucket,
            key,
            BytesIO(data),
            len(data),
            content_type=content_type,
            metadata=metadata,
        )
        return True

    def _get_key(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def put(
        self,
        data: bytes | bytearray | memoryview,
        provenance: ProvenanceEnvelope,
        *,
        media_type: str | None = None,
    ) -> StoredObject:
        payload = bytes(data)
        digest = sha256(payload).hexdigest()
        key = object_key(digest)
        provenance_key = _provenance_key(digest)
        created = self._put_once(
            key,
            payload,
            content_type=media_type or "application/octet-stream",
            metadata={"sha256": digest},
        )
        if not created:
            self.get(digest)
        record = ProvenanceRecord(
            content_hash=digest,
            size_bytes=len(payload),
            stored_at=datetime.now(UTC),
            envelope=provenance,
        )
        provenance_created = self._put_once(
            provenance_key,
            _record_bytes(record),
            content_type="application/json",
        )
        if not provenance_created:
            self.get_provenance(digest)
        return StoredObject(
            content_hash=digest,
            storage_uri=f"s3://{self.bucket}/{key}",
            provenance_uri=f"s3://{self.bucket}/{provenance_key}",
            size_bytes=len(payload),
            created=created,
        )

    def get(self, content_hash: str) -> bytes:
        digest = _normalize_hash(content_hash)
        payload = self._get_key(object_key(digest))
        actual = sha256(payload).hexdigest()
        if actual != digest:
            raise IntegrityError(f"content hash mismatch: expected {digest}, got {actual}")
        return payload

    def get_provenance(self, content_hash: str) -> ProvenanceRecord:
        digest = _normalize_hash(content_hash)
        return _parse_record(self._get_key(_provenance_key(digest)), digest)

    def exists(self, content_hash: str) -> bool:
        return self._exists_key(object_key(_normalize_hash(content_hash)))


def get_vault() -> EvidenceVault:
    """Build the configured vault backend from :class:`aegis.config.Settings`."""
    from aegis.config import get_settings

    settings = get_settings()
    if settings.vault_backend == "filesystem":
        return LocalFilesystemVault(settings.vault_local_path)
    if settings.vault_backend == "minio":
        return MinioVault(
            settings.minio_endpoint,
            settings.minio_bucket,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    raise VaultError(f"unsupported vault backend: {settings.vault_backend!r}")
