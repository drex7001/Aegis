"""Source landing, derivatives and extraction over HTTP (T23a; spec 04, B-04).

These routes are the front door for evidence, so the cases that matter are the
ones where a careless implementation loses material or invents it: a re-upload
that silently forks a second record, a quarantine an operator can extract from
anyway, an extraction pass that writes a claim instead of a suggestion.

Every fixture is fictional and generated (``tests.support.pdf``); the vault is
the local filesystem adapter, so this layer needs PostgreSQL and nothing else.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
import sqlalchemy as sa
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegis.actions import new_id
from aegis.api import create_app
from aegis.api.auth import OIDCAuthenticator
from aegis.api.routes import ingest as ingest_routes
from aegis.config import get_settings
from aegis.evidence import LocalFilesystemVault
from aegis.ontology import load
from aegis.store import AuditLog, Claim, Derivative, ReviewQueue, SourceRecord
from tests.support.database import configured_test_database, truncate_domain_data
from tests.support.paths import ONTOLOGY_PATH
from tests.support.pdf import REMAND_ANNEX_TEXT, minimal_pdf, remand_annex_pdf

ISSUER = "http://localhost:8180/realms/aegis"
AUDIENCE = "aegis-api"
PDF = "application/pdf"

pytestmark = pytest.mark.requirement(
    "Article-VI", "Article-VII", "Article-VIII", "spec-04-1", "spec-04-3", "spec-04-5", "T23a"
)

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StubKey:
    key = _KEY.public_key()


class _StubJWKS:
    def get_signing_key_from_jwt(self, token: str) -> _StubKey:
        return _StubKey()


def auth(sub: str, *roles: str, clearance: int = 2) -> dict:
    now = datetime.now(timezone.utc)
    encoded = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": sub,
            "preferred_username": sub,
            "iat": now,
            "exp": now + timedelta(minutes=10),
            "realm_access": {"roles": list(roles)},
            "clearance": clearance,
        },
        _KEY,
        algorithm="RS256",
    )
    return {"Authorization": f"Bearer {encoded}"}


ANALYST = auth("user:analyst", "analyst")
SUPERVISOR = auth("user:supervisor", "analyst", "supervisor")
INVESTIGATOR = auth("user:investigator", "investigator")
NO_ROLES = auth("user:outsider")
LOW_CLEARANCE = auth("user:junior", "analyst", clearance=0)


@pytest.fixture(scope="module")
def ingest_db(test_database_url: str, alembic_config: Config):
    with configured_test_database(test_database_url, alembic_config):
        yield test_database_url


@pytest.fixture(scope="module")
def client(ingest_db: str, tmp_path_factory) -> TestClient:
    app = create_app()
    app.state.authenticator = OIDCAuthenticator(app.state.settings, jwks_client=_StubJWKS())
    # The app's own seam: this layer promises PostgreSQL, not MinIO. Proving the
    # object-store adapter is tests/system's job.
    app.state.vault = LocalFilesystemVault(tmp_path_factory.mktemp("vault"))
    return TestClient(app)


@pytest.fixture()
def db(ingest_db: str):
    engine = sa.create_engine(ingest_db)
    truncate_domain_data(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def upload(client: TestClient, data: bytes, name: str, *, headers=ANALYST, **form):
    return client.post(
        "/v1/ingest/file",
        files={"file": (name, data, PDF)},
        data=form,
        headers=headers,
    )


def paste(client: TestClient, text: str, name: str, *, headers=ANALYST, **body):
    return client.post(
        "/v1/ingest/text",
        json={"text": text, "filename": name, **body},
        headers=headers,
    )


# ── landing ──────────────────────────────────────────────────────────────────


def test_landing_a_file_creates_a_landed_record(client: TestClient, db: Session) -> None:
    response = upload(client, remand_annex_pdf(), "annex-b.pdf")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["outcome"] == "landed"
    assert body["record"]["status"] == "landed"
    assert body["record"]["media_type"] == PDF
    assert body["record"]["quarantine_reason"] is None
    assert body["record"]["provenance"]["original_filename"] == "annex-b.pdf"
    assert db.scalar(sa.select(sa.func.count()).select_from(SourceRecord)) == 1


def test_re_landing_identical_bytes_is_a_no_op(client: TestClient, db: Session) -> None:
    """Spec 04 §5: the second send reports the first record, and adds nothing."""
    first = upload(client, remand_annex_pdf(), "annex-b.pdf").json()
    second = upload(client, remand_annex_pdf(), "annex-b.pdf").json()

    assert first["outcome"] == "landed"
    assert second["outcome"] == "already_landed"
    assert second["record"]["record_id"] == first["record"]["record_id"]
    assert db.scalar(sa.select(sa.func.count()).select_from(SourceRecord)) == 1


def test_same_filename_with_different_bytes_quarantines(client: TestClient, db: Session) -> None:
    """A version conflict is a human's call, not the pipeline's (spec 04 §3)."""
    upload(client, remand_annex_pdf(), "annex-b.pdf")
    response = upload(client, minimal_pdf(["A different annex entirely."]), "annex-b.pdf")

    body = response.json()
    assert body["outcome"] == "quarantined"
    assert body["record"]["status"] == "quarantined"
    assert "version conflict" in body["record"]["quarantine_reason"]
    assert db.scalar(sa.select(sa.func.count()).select_from(SourceRecord)) == 2


def test_oversized_artifact_lands_but_is_quarantined(
    client: TestClient, db: Session, monkeypatch
) -> None:
    """The bytes are kept and withheld — deciding an artifact is too big to
    exist is not this layer's call (spec 04 §3)."""
    bounded = get_settings().model_copy(update={"ingest_oversize_bytes": 32})
    monkeypatch.setattr(ingest_routes, "get_settings", lambda: bounded)

    body = upload(client, remand_annex_pdf(), "annex-b.pdf").json()
    assert body["outcome"] == "quarantined"
    assert "oversized" in body["record"]["quarantine_reason"]
    assert db.scalar(sa.select(sa.func.count()).select_from(SourceRecord)) == 1


def test_both_quarantine_reasons_are_reported_together(
    client: TestClient, db: Session, monkeypatch
) -> None:
    """Fixing one reason and re-landing should not reveal the next one."""
    upload(client, remand_annex_pdf(), "annex-b.pdf")
    bounded = get_settings().model_copy(update={"ingest_oversize_bytes": 32})
    monkeypatch.setattr(ingest_routes, "get_settings", lambda: bounded)

    reason = upload(client, minimal_pdf(["Another annex."]), "annex-b.pdf").json()["record"][
        "quarantine_reason"
    ]
    assert "version conflict" in reason
    assert "oversized" in reason


def test_upload_beyond_the_transport_bound_lands_nothing(
    client: TestClient, db: Session, monkeypatch
) -> None:
    bounded = get_settings().model_copy(update={"ingest_max_bytes": 64})
    monkeypatch.setattr(ingest_routes, "get_settings", lambda: bounded)

    response = upload(client, remand_annex_pdf(), "annex-b.pdf")
    assert response.status_code == 413
    assert db.scalar(sa.select(sa.func.count()).select_from(SourceRecord)) == 0


def test_landing_is_audited(client: TestClient, db: Session) -> None:
    record_id = upload(client, remand_annex_pdf(), "annex-b.pdf").json()["record"]["record_id"]
    entry = db.scalar(
        sa.select(AuditLog).where(
            AuditLog.action == "ingest.land", AuditLog.resource_id == record_id
        )
    )
    assert entry is not None
    assert entry.actor == "user:analyst"
    assert entry.detail["quarantined"] is False
    assert entry.detail["size_bytes"] > 0


def test_pasted_text_lands_as_a_record(client: TestClient, db: Session) -> None:
    response = paste(client, REMAND_ANNEX_TEXT, "field-note.txt", notes="typed by the operator")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["outcome"] == "landed"
    assert body["record"]["media_type"] == "text/plain"
    assert body["record"]["provenance"]["notes"] == "typed by the operator"


@pytest.mark.requirement("B-08", "T24a")
def test_landing_stores_and_returns_nullable_governance_seams(
    client: TestClient, db: Session
) -> None:
    body = paste(
        client,
        "fictional governed note",
        "governed.txt",
        collection_policy="public-osint-v1",
        retention_class="review-after-30d",
        authority_ref="FICTIONAL-AUTHORITY-1",
        authority_valid_from="2026-07-01T00:00:00Z",
        authority_valid_to="2026-07-31T00:00:00Z",
    ).json()["record"]

    assert body["collection_policy_ref"] == "public-osint-v1"
    assert body["retention_class"] == "review-after-30d"
    assert body["authority_ref"] == "FICTIONAL-AUTHORITY-1"
    row = db.get(SourceRecord, body["record_id"])
    assert row is not None
    assert row.collection_policy_ref == "public-osint-v1"
    assert row.authority_valid_from is not None
    assert row.authority_valid_to is not None


def test_re_pasting_the_same_note_is_a_no_op(client: TestClient, db: Session) -> None:
    first = paste(client, "A short fictional note.", "note.txt").json()
    second = paste(client, "A short fictional note.", "note.txt").json()

    assert second["outcome"] == "already_landed"
    assert second["record"]["record_id"] == first["record"]["record_id"]
    assert db.scalar(sa.select(sa.func.count()).select_from(SourceRecord)) == 1


def test_the_same_note_under_a_new_name_is_a_new_record(
    client: TestClient, db: Session
) -> None:
    """The ingest key includes the filename, so renaming is a real re-landing."""
    first = paste(client, "A short fictional note.", "note.txt").json()
    second = paste(client, "A short fictional note.", "note-copy.txt").json()

    assert second["outcome"] == "landed"
    assert second["record"]["record_id"] != first["record"]["record_id"]
    assert first["record"]["content_hash"] == second["record"]["content_hash"]


# ── authorization ────────────────────────────────────────────────────────────


def test_landing_requires_a_collecting_role(client: TestClient, db: Session) -> None:
    assert upload(client, remand_annex_pdf(), "a.pdf", headers=NO_ROLES).status_code == 403
    assert paste(client, "note", "n.txt", headers=NO_ROLES).status_code == 403
    assert db.scalar(sa.select(sa.func.count()).select_from(SourceRecord)) == 0


def test_investigators_may_land(client: TestClient) -> None:
    """specs/06 §2.3 grants landing to investigators as well as analysts."""
    assert paste(client, "a fictional note", "n.txt", headers=INVESTIGATOR).status_code == 201


def test_landing_above_your_clearance_is_refused(client: TestClient, db: Session) -> None:
    """Otherwise an analyst creates evidence they can never afterwards read."""
    response = paste(client, "note", "n.txt", headers=LOW_CLEARANCE, handling_code="sensitive")
    assert response.status_code == 403
    assert db.scalar(sa.select(sa.func.count()).select_from(SourceRecord)) == 0


def test_unknown_handling_code_is_rejected(client: TestClient, db: Session) -> None:
    response = paste(client, "note", "n.txt", handling_code="ultra-secret")
    assert response.status_code == 422
    assert db.scalar(sa.select(sa.func.count()).select_from(SourceRecord)) == 0


def test_records_above_clearance_are_absent_from_the_list(client: TestClient) -> None:
    """Absent, not counted (specs/03 §4) — no "1 hidden" tease."""
    paste(client, "an open note", "open.txt", handling_code="open")
    paste(client, "a restricted note", "restricted.txt", handling_code="restricted")

    visible = client.get("/v1/source-records", headers=LOW_CLEARANCE).json()
    names = {row["provenance"]["original_filename"] for row in visible["items"]}
    assert names == {"open.txt"}
    assert "total" not in visible

    everything = client.get("/v1/source-records", headers=ANALYST).json()
    assert len(everything["items"]) == 2


def test_listing_filters_by_status(client: TestClient) -> None:
    upload(client, remand_annex_pdf(), "annex-b.pdf")
    upload(client, minimal_pdf(["Conflicting content."]), "annex-b.pdf")

    quarantined = client.get(
        "/v1/source-records", params={"status": "quarantined"}, headers=ANALYST
    ).json()
    assert [row["status"] for row in quarantined["items"]] == ["quarantined"]


def test_source_record_cursor_is_stable_under_a_concurrent_insert(
    client: TestClient, db: Session,
) -> None:
    original = {
        paste(client, f"note {index}", f"page-{index}.txt").json()["record"]["record_id"]
        for index in range(3)
    }
    first = client.get(
        "/v1/source-records", params={"limit": 2}, headers=ANALYST
    ).json()
    first_ids = {row["record_id"] for row in first["items"]}
    assert first["next_cursor"] is not None

    inserted = paste(client, "arrived between pages", "concurrent.txt").json()["record"]
    second = client.get(
        "/v1/source-records",
        params={"limit": 2, "cursor": first["next_cursor"]},
        headers=ANALYST,
    ).json()
    second_ids = {row["record_id"] for row in second["items"]}

    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids == original
    assert inserted["record_id"] not in second_ids
    assert "total" not in second


@pytest.mark.requirement("Article-VI", "T24a", "T24b")
def test_review_queue_omits_a_restricted_property_without_a_count(
    client: TestClient, db: Session
) -> None:
    record_id = paste(client, "fictional identifiers", "fields.txt").json()["record"][
        "record_id"
    ]
    for predicate in ("known_as", "has_nic"):
        db.add(
            ReviewQueue(
                suggestion_id=new_id("sug"),
                suggestion_kind="claim_draft",
                schema_version=1,
                payload={"predicate": predicate},
                target_action="record_claim",
                producer="test:t24",
                producer_version="1",
                producer_meta={},
                record_id=record_id,
                idempotency_key=new_id("idem"),
            )
        )
    db.commit()

    high = client.get("/v1/review-queue", headers=ANALYST).json()
    low = client.get("/v1/review-queue", headers=LOW_CLEARANCE).json()
    assert {row["payload"]["predicate"] for row in high["items"]} == {
        "known_as",
        "has_nic",
    }
    assert [row["payload"]["predicate"] for row in low["items"]] == ["known_as"]
    assert "total" not in low


# ── derivatives and extraction ───────────────────────────────────────────────


def _land_and_extract(client: TestClient, producer: str = "structural", **kwargs):
    record_id = upload(client, remand_annex_pdf(), "annex-b.pdf").json()["record"]["record_id"]
    response = client.post(
        f"/v1/source-records/{record_id}/extract",
        json={"producer": producer, **kwargs},
        headers=ANALYST,
    )
    return record_id, response


def test_extracting_a_pdf_records_a_derivative_and_queues_suggestions(
    client: TestClient, db: Session
) -> None:
    """The whole stage-3 gap T23a closed: a PDF is now extractable."""
    record_id, response = _land_and_extract(client)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["derivative_created"] is True
    assert body["derivative"]["tool"] == "pdfplumber"
    assert body["derivative"]["kind"] == "text"
    # ALPHA and BRAVO overlap at one facility; CHARLIE is held elsewhere.
    assert body["suggestions_created"] == 1

    stored = db.scalar(sa.select(Derivative).where(Derivative.parent_record == record_id))
    assert stored is not None
    assert stored.operator == "user:analyst"


def test_extraction_writes_no_claims(client: TestClient, db: Session) -> None:
    """Article VII: machine output reaches the queue, never the canonical table."""
    _, response = _land_and_extract(client)
    assert response.json()["suggestions_created"] == 1
    assert db.scalar(sa.select(sa.func.count()).select_from(Claim)) == 0
    assert db.scalar(sa.select(sa.func.count()).select_from(ReviewQueue)) == 1
    assert db.scalar(sa.select(ReviewQueue.status)) == "suggested"


def test_re_extracting_reuses_the_derivative(client: TestClient, db: Session) -> None:
    record_id, first = _land_and_extract(client)
    again = client.post(
        f"/v1/source-records/{record_id}/extract",
        json={"producer": "structural"},
        headers=ANALYST,
    ).json()

    assert first.json()["derivative_created"] is True
    assert again["derivative_created"] is False
    assert again["derivative"]["derivative_id"] == first.json()["derivative"]["derivative_id"]
    assert db.scalar(sa.select(sa.func.count()).select_from(Derivative)) == 1


def test_re_extracting_queues_no_duplicate_suggestions(
    client: TestClient, db: Session
) -> None:
    """Replay updates nothing already suggested (spec 04 §5)."""
    record_id, _ = _land_and_extract(client)
    again = client.post(
        f"/v1/source-records/{record_id}/extract",
        json={"producer": "structural"},
        headers=ANALYST,
    ).json()

    assert again["suggestions_created"] == 0
    assert db.scalar(sa.select(sa.func.count()).select_from(ReviewQueue)) == 1


def test_semantic_mock_labels_itself_as_a_mock(client: TestClient, db: Session) -> None:
    """The workspace offers this producer, so the path it triggers is covered.

    The browser has no model credentials, so the UI's "semantic" option runs
    the offline extractor. What keeps that honest is that `producer_meta` says
    `model: mock` — a reviewer can always see what produced a suggestion, so
    the affordance is not a way to slip fabricated output in as model output.
    """
    _, response = _land_and_extract(client, producer="semantic", mock=True)
    assert response.status_code == 200, response.text
    assert response.json()["producer"] == "semantic"

    suggestion = db.scalar(sa.select(ReviewQueue))
    assert suggestion is not None
    assert suggestion.producer == "semantic_pass"
    assert suggestion.producer_meta["model"] == "mock"
    assert suggestion.producer_meta["raw_response_ref"].startswith("sha256:")
    # Still a suggestion, never a claim — the producer does not change that.
    assert suggestion.status == "suggested"
    assert db.scalar(sa.select(sa.func.count()).select_from(Claim)) == 0


def test_extraction_of_a_quarantined_record_is_refused(client: TestClient) -> None:
    upload(client, remand_annex_pdf(), "annex-b.pdf")
    conflicting = upload(client, minimal_pdf(["Conflicting content."]), "annex-b.pdf").json()
    record_id = conflicting["record"]["record_id"]

    response = client.post(
        f"/v1/source-records/{record_id}/extract",
        json={"producer": "structural"},
        headers=ANALYST,
    )
    assert response.status_code == 409
    assert "quarantined" in response.json()["detail"]


def test_releasing_quarantine_unblocks_extraction(client: TestClient) -> None:
    upload(client, remand_annex_pdf(), "annex-b.pdf")
    record_id = upload(client, minimal_pdf(["Conflicting content."]), "annex-b.pdf").json()[
        "record"
    ]["record_id"]

    denied = client.post(f"/v1/source-records/{record_id}/release", headers=ANALYST)
    assert denied.status_code == 403

    released = client.post(f"/v1/source-records/{record_id}/release", headers=SUPERVISOR)
    assert released.status_code == 200
    assert released.json()["status"] == "landed"

    extracted = client.post(
        f"/v1/source-records/{record_id}/extract",
        json={"producer": "structural"},
        headers=ANALYST,
    )
    assert extracted.status_code == 200


def test_extraction_of_an_unsupported_media_type_is_refused(client: TestClient) -> None:
    response = client.post(
        "/v1/ingest/file",
        files={"file": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")},
        headers=ANALYST,
    )
    record_id = response.json()["record"]["record_id"]

    extracted = client.post(
        f"/v1/source-records/{record_id}/extract",
        json={"producer": "structural"},
        headers=ANALYST,
    )
    assert extracted.status_code == 422
    assert "video/mp4" in extracted.json()["detail"]


def test_extraction_is_audited(client: TestClient, db: Session) -> None:
    record_id, _ = _land_and_extract(client)
    entry = db.scalar(
        sa.select(AuditLog).where(
            AuditLog.action == "ingest.extract", AuditLog.resource_id == record_id
        )
    )
    assert entry is not None
    assert entry.actor == "user:analyst"
    assert entry.detail["producer"] == "structural"
    assert entry.detail["suggestions_created"] == 1


def test_derivatives_are_listed_for_a_visible_record(client: TestClient) -> None:
    record_id, _ = _land_and_extract(client)
    listed = client.get(f"/v1/source-records/{record_id}/derivatives", headers=ANALYST).json()
    assert [row["tool"] for row in listed] == ["pdfplumber"]


def test_a_record_above_clearance_is_absent_rather_than_forbidden(
    client: TestClient,
) -> None:
    """404, not 403: the reply must not confirm the record exists."""
    record_id = paste(client, "a restricted note", "r.txt", handling_code="restricted").json()[
        "record"
    ]["record_id"]

    for path, method in (
        (f"/v1/source-records/{record_id}/derivatives", "get"),
        (f"/v1/source-records/{record_id}/extract", "post"),
    ):
        call = getattr(client, method)
        kwargs = {"json": {"producer": "structural"}} if method == "post" else {}
        assert call(path, headers=LOW_CLEARANCE, **kwargs).status_code == 404


def test_vocabulary_is_served_so_no_client_hard_codes_it(client: TestClient) -> None:
    """Article XI: the forms that need these vocabularies must not own a copy.

    Compared against the loaded ontology rather than a literal, because the
    point is that the route *reports* the ontology — a literal here would be
    the second hard-coded copy this route exists to prevent, and it would keep
    passing after the ontology moved.
    """
    ontology = load(ONTOLOGY_PATH)
    body = client.get("/v1/ontology/vocabulary", headers=ANALYST).json()

    assert body["version"] == ontology.version
    assert body["source_types"] == list(ontology.source_types)
    # Order, not just membership: clearance is an *index* into this list
    # (authz.filters.allowed_handling_codes), so a re-ordered copy would
    # mislabel who can see what.
    assert body["handling_codes"] == list(ontology.handling_codes)


def test_vocabulary_needs_no_role_but_does_need_a_token(client: TestClient) -> None:
    assert client.get("/v1/ontology/vocabulary", headers=NO_ROLES).status_code == 200
    assert client.get("/v1/ontology/vocabulary").status_code == 401


def test_extraction_requires_the_analyst_role(client: TestClient) -> None:
    record_id = upload(client, remand_annex_pdf(), "annex-b.pdf").json()["record"]["record_id"]
    response = client.post(
        f"/v1/source-records/{record_id}/extract",
        json={"producer": "structural"},
        headers=NO_ROLES,
    )
    assert response.status_code == 403
