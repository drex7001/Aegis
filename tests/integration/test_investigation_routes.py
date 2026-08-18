"""The investigation routes, and the two properties they must never lose (T43).

`test_investigation_model.py` covers the actions layer. This is the HTTP half,
and it exists for one thing above all: **a non-member gets 404 from every one of
these routes, writes included.** A 403 on a write would disclose that the case
exists just as surely as a 403 on a read (spec 09 §5 rule 1), and a write path
is the easy place to forget it — the handler already knows the caller lacks
permission, so returning "forbidden" feels like the honest answer.

The second is Article VIII as a *shape*: `supporting` and `contradicting` are
present on every hypothesis response whether or not they hold anything. A client
cannot render "no contradicting evidence recorded" from a field that was
omitted.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from aegis.actions import new_id
from aegis.store import Claim, Entity, Source, SourceRecord
from sqlalchemy.orm import Session
from tests.integration.test_api import _FakeFGA, auth, client, api_db, clean_api_database, fake_fga  # noqa: F401

pytestmark = pytest.mark.requirement(
    "Article-VI", "Article-VIII", "ADR-044", "H-17", "H-18", "T43"
)

OWNER = "owner-t43"
OUTSIDER = "outsider-t43"


@pytest.fixture()
def case(client: TestClient, fake_fga: _FakeFGA) -> dict:
    """An open case the owner is a supervisor of, with one claim inside it."""
    created = client.post(
        "/v1/cases",
        params={"purpose": "open the fictional T43 case"},
        json={"title": "Fictional investigation", "purpose": "T43"},
        headers=auth(OWNER, "analyst", "supervisor"),
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]
    fake_fga.add(f"user:{OWNER}", "supervisor", f"case:{case_id}")

    engine = sa.create_engine(client.app.state.settings.database_url)
    ids = {"case": case_id}
    with Session(engine) as session, session.begin():
        session.add(Source(source_id=(sid := new_id("src")), source_type="open_source", name="T43"))
        session.add(
            SourceRecord(
                record_id=(rid := new_id("rec")),
                source_id=sid,
                ingest_key=new_id("key"),
                content_hash="e" * 64,
                storage_uri="test://t43-routes",
            )
        )
        session.add(Entity(entity_id=(eid := new_id("ent")), entity_type="person", label="Fictional A"))
        session.add(Entity(entity_id=(oid := new_id("ent")), entity_type="organization", label="Fictional Co"))
        session.flush()
        session.add(
            Claim(
                claim_id=(cid := new_id("clm")),
                subject_id=eid,
                predicate="member_of",
                object_id=oid,
                assertion_type="reported",
                record_id=rid,
                identity_revision_id=0,
                ontology_version=client.app.state.ontology.version,
            )
        )
        ids.update({"record": rid, "person": eid, "org": oid, "claim": cid})
    engine.dispose()
    return ids


def _open_hypothesis(client: TestClient, case_id: str, **overrides) -> dict:
    body = {
        "case_id": case_id,
        "statement": "The two fictional parties act as one enterprise.",
        "missing_info": "The registry filing has not been checked.",
    }
    body.update(overrides)
    return client.post("/v1/hypotheses", json=body, headers=auth(OWNER, "analyst"))


# ── the round trip ──────────────────────────────────────────────────────────


def test_a_hypothesis_round_trips_with_both_sides_and_its_history(
    client: TestClient, case: dict
) -> None:
    opened = _open_hypothesis(client, case["case"])
    assert opened.status_code == 201, opened.text
    hypothesis_id = opened.json()["hypothesis_id"]
    assert opened.json()["version"] == 1

    for stance in ("supports", "contradicts"):
        linked = client.post(
            f"/v1/hypotheses/{hypothesis_id}/claims",
            json={"claim_id": case["claim"], "stance": stance},
            headers=auth(OWNER, "analyst"),
        )
        assert linked.status_code == 201, linked.text

    revised = client.post(
        f"/v1/hypotheses/{hypothesis_id}/revisions",
        json={"note": "a filing was found", "status": "supported"},
        headers=auth(OWNER, "analyst"),
    )
    assert revised.status_code == 201, revised.text

    read = client.get(f"/v1/hypotheses/{hypothesis_id}", headers=auth(OWNER, "analyst"))
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["current"]["version"] == 2
    assert body["current"]["status"] == "supported"
    # A revision is a snapshot: the statement survived a status-only revision.
    assert body["current"]["statement"] == body["revisions"][0]["statement"]
    assert [r["version"] for r in body["revisions"]] == [1, 2]
    assert len(body["supporting"]) == 1
    assert len(body["contradicting"]) == 1


def test_both_sides_are_present_even_when_empty(client: TestClient, case: dict) -> None:
    """Article VIII is a rendering obligation, so the shape must carry it."""
    hypothesis_id = _open_hypothesis(client, case["case"]).json()["hypothesis_id"]
    body = client.get(
        f"/v1/hypotheses/{hypothesis_id}", headers=auth(OWNER, "analyst")
    ).json()
    assert body["supporting"] == []
    assert body["contradicting"] == []
    assert "contradicting" in body  # present, not omitted


def test_a_blank_missing_info_note_is_refused_over_http(
    client: TestClient, case: dict
) -> None:
    refused = _open_hypothesis(client, case["case"], missing_info="   ")
    assert refused.status_code == 422, refused.text
    assert refused.headers["content-type"].startswith("application/problem+json")
    # The criterion is named in the stable `path`, the reason in `detail`
    # (ADR-013): a client shows the second and a maintainer greps the first.
    body = refused.json()
    assert body["path"] == (
        "actions.open_hypothesis.submission_criteria.required_text_is_substantive"
    )
    assert "missing_info" in body["detail"]


def test_a_task_lifecycle_round_trips(client: TestClient, case: dict) -> None:
    created = client.post(
        "/v1/tasks",
        json={"case_id": case["case"], "title": "Check the filing", "kind": "lead"},
        headers=auth(OWNER, "analyst"),
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["task_id"]
    assert created.json()["status"] == "open"
    assert created.json()["owner"] is None

    moved = client.post(
        f"/v1/tasks/{task_id}",
        json={"status": "done", "owner": OWNER, "note": "filing checked"},
        headers=auth(OWNER, "analyst"),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "done"
    assert moved.json()["closed_at"] is not None

    listed = client.get(
        "/v1/tasks", params={"case": case["case"]}, headers=auth(OWNER, "analyst")
    )
    assert listed.status_code == 200
    assert [item["task_id"] for item in listed.json()["items"]] == [task_id]


def test_a_reference_round_trips_without_rescoping_the_claim(
    client: TestClient, case: dict
) -> None:
    linked = client.post(
        f"/v1/cases/{case['case']}/references",
        json={"target_type": "claim", "target_id": case["claim"], "note": "cited"},
        headers=auth(OWNER, "analyst"),
    )
    assert linked.status_code == 201, linked.text

    listed = client.get(
        f"/v1/cases/{case['case']}/references", headers=auth(OWNER, "analyst")
    )
    assert [r["target_id"] for r in listed.json()] == [case["claim"]]

    # The claim's recording scope is untouched: a reference grants nothing
    # (ADR-044), and `claim_filters` reads `case_id`, not this table.
    engine = sa.create_engine(client.app.state.settings.database_url)
    with Session(engine) as session:
        assert session.get(Claim, case["claim"]).case_id is None
    engine.dispose()

    unlinked = client.delete(
        f"/v1/cases/{case['case']}/references/claim/{case['claim']}",
        params={"reason": "cited the wrong filing"},
        headers=auth(OWNER, "analyst"),
    )
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["target_id"] == case["claim"]
    after = client.get(f"/v1/cases/{case['case']}/references", headers=auth(OWNER, "analyst"))
    assert after.json() == []


# ── the exit criterion: a non-member learns nothing ─────────────────────────


def test_a_non_member_gets_404_from_every_investigation_route(
    client: TestClient, case: dict
) -> None:
    """Reads **and** writes. A 403 on a write discloses the case just as well.

    The list routes are 404 rather than empty because they name a case in the
    query string: answering "here are zero hypotheses" would confirm it exists.
    """
    case_id = case["case"]
    hypothesis_id = _open_hypothesis(client, case_id).json()["hypothesis_id"]
    task_id = client.post(
        "/v1/tasks",
        json={"case_id": case_id, "title": "Private"},
        headers=auth(OWNER, "analyst"),
    ).json()["task_id"]

    outsider = auth(OUTSIDER, "analyst", "investigator", "supervisor")
    attempts = [
        client.get(f"/v1/cases/{case_id}", headers=outsider),
        client.get(f"/v1/cases/{case_id}/members", headers=outsider),
        client.get(f"/v1/cases/{case_id}/references", headers=outsider),
        client.post(f"/v1/cases/{case_id}/close", json={"reason": "no"}, headers=outsider),
        client.post(
            f"/v1/cases/{case_id}/references",
            json={"target_type": "claim", "target_id": case["claim"]},
            headers=outsider,
        ),
        client.delete(
            f"/v1/cases/{case_id}/references/claim/{case['claim']}",
            params={"reason": "no"},
            headers=outsider,
        ),
        client.get("/v1/hypotheses", params={"case": case_id}, headers=outsider),
        client.get(f"/v1/hypotheses/{hypothesis_id}", headers=outsider),
        client.post(
            "/v1/hypotheses",
            json={"case_id": case_id, "statement": "s", "missing_info": "m"},
            headers=outsider,
        ),
        client.post(
            f"/v1/hypotheses/{hypothesis_id}/revisions",
            json={"note": "mine now"},
            headers=outsider,
        ),
        client.post(
            f"/v1/hypotheses/{hypothesis_id}/claims",
            json={"claim_id": case["claim"], "stance": "supports"},
            headers=outsider,
        ),
        client.delete(
            f"/v1/hypotheses/{hypothesis_id}/claims/{case['claim']}/supports",
            params={"reason": "no"},
            headers=outsider,
        ),
        client.get("/v1/tasks", params={"case": case_id}, headers=outsider),
        client.post(
            "/v1/tasks", json={"case_id": case_id, "title": "mine"}, headers=outsider
        ),
        client.post(f"/v1/tasks/{task_id}", json={"status": "dropped"}, headers=outsider),
    ]
    assert [r.status_code for r in attempts] == [404] * len(attempts), [
        (r.request.method, r.request.url.path, r.status_code) for r in attempts
    ]
    # And the body says nothing either: 404 is "absent", never "forbidden".
    for response in attempts:
        assert "forbidden" not in response.text.lower()
        assert case_id not in response.text


def test_an_unknown_hypothesis_and_a_hidden_one_answer_identically(
    client: TestClient, case: dict
) -> None:
    """The 404 must not be distinguishable from "no such id"."""
    hypothesis_id = _open_hypothesis(client, case["case"]).json()["hypothesis_id"]
    outsider = auth(OUTSIDER, "analyst")
    hidden = client.get(f"/v1/hypotheses/{hypothesis_id}", headers=outsider)
    absent = client.get("/v1/hypotheses/hyp_does_not_exist", headers=outsider)
    assert hidden.status_code == absent.status_code == 404
    assert hidden.json() == absent.json()


def test_the_case_list_holds_only_the_callers_own_cases(
    client: TestClient, case: dict, fake_fga: _FakeFGA
) -> None:
    """Derived from membership, not filtered afterwards (spec 09 §2.4)."""
    mine = client.get("/v1/cases", headers=auth(OWNER, "analyst"))
    assert mine.status_code == 200
    assert [c["case_id"] for c in mine.json()["items"]] == [case["case"]]
    # No total: a count over an authorization-filtered collection is an
    # existence leak (spec 06 §4 default 4).
    assert set(mine.json()) == {"items", "next_cursor"}

    theirs = client.get("/v1/cases", headers=auth(OUTSIDER, "analyst"))
    assert theirs.status_code == 200
    assert theirs.json()["items"] == []


def test_every_investigation_route_requires_a_token(client: TestClient, case: dict) -> None:
    for method, path in (
        ("get", "/v1/cases"),
        ("get", f"/v1/cases/{case['case']}/members"),
        ("get", "/v1/hypotheses?case=x"),
        ("post", "/v1/hypotheses"),
        ("get", "/v1/tasks?case=x"),
        ("post", "/v1/tasks"),
    ):
        # `client.request`, not `client.get(json=...)`: httpx's get takes no body.
        response = client.request(method.upper(), path, json={} if method == "post" else None)
        assert response.status_code == 401, (method, path, response.status_code)
