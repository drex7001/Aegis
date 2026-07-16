"""Evidence schema and content-addressed vault tests (speckit T5)."""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
import pytest
import sqlalchemy as sa

from aegis.evidence import (
    IntegrityError,
    LocalFilesystemVault,
    MinioVault,
    ProvenanceEnvelope,
    get_vault,
    object_key,
)
from aegis.store import Base

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_TABLES = {"evidence_item", "derivative", "custody_event"}
T4_TABLES = {
    "source",
    "source_record",
    "entity",
    "claim",
    "claim_relation",
    "review_queue",
    "case_file",
    "case_member",
    "authz_outbox",
}


@pytest.fixture
def provenance() -> ProvenanceEnvelope:
    return ProvenanceEnvelope(
        source_system="manual-upload",
        original_filename="report.pdf",
        connector="pipeline.ingest",
        connector_version="20aec97",
        operator="user:analyst",
        collection_policy="public-osint-v1",
    )


def test_provenance_requires_landing_identity() -> None:
    with pytest.raises(ValidationError):
        ProvenanceEnvelope(  # type: ignore[call-arg]
            source_system="manual-upload",
            original_filename="report.pdf",
            connector="pipeline.ingest",
            connector_version="1",
        )


def test_local_vault_deduplicates_and_preserves_first_envelope(
    tmp_path: Path, provenance: ProvenanceEnvelope
) -> None:
    vault = LocalFilesystemVault(tmp_path)
    payload = b"immutable evidence bytes"

    first = vault.put(payload, provenance, media_type="application/pdf")
    second_envelope = provenance.model_copy(update={"operator": "user:other"})
    second = vault.put(payload, second_envelope)

    assert first.created is True
    assert second.created is False
    assert second.content_hash == first.content_hash
    assert object_key(first.content_hash) == (
        f"sha256/{first.content_hash[:2]}/{first.content_hash}"
    )
    assert vault.exists(first.content_hash)
    assert vault.get(first.content_hash) == payload

    record = vault.get_provenance(first.content_hash)
    assert record.content_hash == first.content_hash
    assert record.size_bytes == len(payload)
    assert record.envelope == provenance

    content_files = [
        path
        for path in tmp_path.rglob("*")
        if path.is_file() and not path.name.endswith(".provenance.json")
    ]
    assert len(content_files) == 1


def test_local_vault_detects_tampering(
    tmp_path: Path, provenance: ProvenanceEnvelope
) -> None:
    vault = LocalFilesystemVault(tmp_path)
    stored = vault.put(b"original", provenance)
    content_path = tmp_path.joinpath(*object_key(stored.content_hash).split("/"))
    content_path.write_bytes(b"tampered")

    with pytest.raises(IntegrityError, match="content hash mismatch"):
        vault.get(stored.content_hash)


def test_vault_factory_selects_filesystem_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AEGIS_VAULT_BACKEND", "filesystem")
    monkeypatch.setenv("AEGIS_VAULT_PATH", str(tmp_path))
    from aegis.config import get_settings

    get_settings.cache_clear()
    try:
        vault = get_vault()
        assert isinstance(vault, LocalFilesystemVault)
        assert vault.root == tmp_path
    finally:
        get_settings.cache_clear()


class _MissingObject(Exception):
    code = "NoSuchKey"


class _Response(BytesIO):
    def release_conn(self) -> None:
        pass


class _FakeMinioClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls = 0

    def stat_object(self, bucket: str, key: str) -> object:
        if (bucket, key) not in self.objects:
            raise _MissingObject
        return object()

    def put_object(
        self,
        bucket: str,
        key: str,
        stream: BytesIO,
        length: int,
        **kwargs: object,
    ) -> None:
        del kwargs
        self.put_calls += 1
        self.objects[(bucket, key)] = stream.read(length)

    def get_object(self, bucket: str, key: str) -> _Response:
        if (bucket, key) not in self.objects:
            raise _MissingObject
        return _Response(self.objects[(bucket, key)])


def test_minio_vault_uses_same_keys_and_deduplicates(provenance: ProvenanceEnvelope) -> None:
    client = _FakeMinioClient()
    vault = MinioVault("unused:9000", "evidence", client=client)
    payload = b"minio evidence"

    first = vault.put(payload, provenance)
    second = vault.put(
        payload,
        provenance.model_copy(update={"operator": "user:duplicate-uploader"}),
    )

    assert first.created is True
    assert second.created is False
    assert first.storage_uri == f"s3://evidence/{object_key(first.content_hash)}"
    assert client.put_calls == 2  # one content object + one immutable JSON sidecar
    assert vault.get(first.content_hash) == payload
    assert vault.get_provenance(first.content_hash).envelope == provenance


def test_evidence_metadata_matches_spec() -> None:
    assert set(Base.metadata.tables) == T4_TABLES | EVIDENCE_TABLES
    derivative_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in Base.metadata.tables["derivative"].constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    assert derivative_checks == {
        "ck_derivative_has_parent": "parent_evidence IS NOT NULL OR parent_record IS NOT NULL"
    }
    assert type(Base.metadata.tables["evidence_item"].c.handling_code.type) is sa.Text


@pytest.mark.integration
def test_evidence_migration_up_inspect_down_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.getenv("AEGIS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set AEGIS_TEST_DATABASE_URL to run PostgreSQL migration test")

    monkeypatch.setenv("AEGIS_DATABASE_URL", database_url)
    from aegis.config import get_settings

    get_settings.cache_clear()
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    engine = sa.create_engine(database_url)

    command.upgrade(config, "head")
    try:
        inspector = sa.inspect(engine)
        table_names = set(inspector.get_table_names())
        assert EVIDENCE_TABLES <= table_names
        assert T4_TABLES <= table_names
        assert {check["name"] for check in inspector.get_check_constraints("derivative")} == {
            "ck_derivative_has_parent"
        }

        for table_name in EVIDENCE_TABLES:
            actual = {column["name"] for column in inspector.get_columns(table_name)}
            mapped = set(Base.metadata.tables[table_name].c.keys())
            assert actual == mapped

        command.downgrade(config, "0002")
        downgraded_tables = set(sa.inspect(engine).get_table_names())
        assert EVIDENCE_TABLES.isdisjoint(downgraded_tables)
        assert T4_TABLES <= downgraded_tables
    finally:
        command.upgrade(config, "head")
        engine.dispose()
        get_settings.cache_clear()
