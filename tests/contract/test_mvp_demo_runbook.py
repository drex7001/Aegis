"""Keep the blocking Phase 2 operator journey aligned with the product."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.requirement(
    "Article-VI", "Article-VII", "H-09", "T27"
)

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "MVP_DEMO.md"
REALM = ROOT / "infra" / "keycloak" / "aegis-realm.json"
BOOTSTRAP = ROOT / "infra" / "bootstrap.sh"

LOCAL_ORIGINS = {
    f"http://{host}:{port}"
    for host in ("127.0.0.1", "localhost")
    for port in (8000, 5173, 4173)
}


@pytest.fixture(scope="module")
def runbook() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_runbook_pins_the_ui_only_governed_loop(runbook: str) -> None:
    flat = " ".join(runbook.split())
    required_product_contract = {
        "data/sample/mvp/remand-register.txt",
        "Land file",
        "Structural — deterministic rules",
        "1 suggestion waiting for review",
        "co located in prison with",
        "Accept",
        "Sign out",
        "Rebuild projection",
        "Rebuilt 1 edges / 1 segments at revision 0.",
        "Source reliability",
        "Information credibility",
        "Analytic confidence",
    }

    missing = sorted(item for item in required_product_contract if item not in flat)
    assert not missing, f"runbook lost product labels/expectations: {missing}"
    loop = flat.split("## 2. Complete the UI-only governed loop", maxsplit=1)[1]
    loop = loop.split("## 3. Exercise the complete T25 fixture", maxsplit=1)[0]
    assert loop.index("Extract") < loop.index("Accept")
    assert loop.index("Accept") < loop.index("Rebuild projection")


def test_runbook_pins_the_fixture_identity_and_governance_gate(runbook: str) -> None:
    flat = " ".join(runbook.split())
    required_fixture_contract = {
        "uv run aegis ingest mvp --output output/mvp-demo/fixture",
        "Nimal Perera / නිමල් පෙරේරා",
        "0.80",
        "Same person",
        "Record decision",
        "Rebuilt 1 edges / 1 segments at revision 1.",
        "Ruwan Silva",
        "Maya Fernando",
        "contradicts",
        "has_nic",
        "dev-analyst",
        "dev-admin",
    }

    missing = sorted(item for item in required_fixture_contract if item not in flat)
    assert not missing, f"runbook lost fixture/governance checks: {missing}"
    assert "exactly two results" in flat
    assert "must be absent" in flat
    assert "no **Rebuild projection** action" in flat


def test_runbook_uses_a_disposable_database_and_explicit_cleanup(runbook: str) -> None:
    assert "aegis_mvp_demo" in runbook
    assert "127.0.0.1:5433/aegis_mvp_demo" in runbook
    assert "dropdb --if-exists -U aegis aegis_mvp_demo" in runbook
    assert "Remove-Item -LiteralPath output/mvp-demo -Recurse -Force" in runbook
    assert "Do not use `down -v`, `make nuke`" in runbook


def test_real_osint_appendix_stays_manual_non_blocking_and_no_egress(
    runbook: str,
) -> None:
    appendix = " ".join(runbook.split("## Appendix A", maxsplit=1)[1].split())

    assert "manual, operator-run, and non-blocking" in appendix
    assert "written authority" in appendix
    assert "data/real/README.md" in appendix
    assert "Do not send real text" in appendix
    assert "hosted model" in appendix
    assert "Do not capture sensitive output" in appendix
    assert "Never use a national identity number for a real person" in appendix
    assert "drop the disposable database" in appendix


def test_keycloak_accepts_sign_in_and_logout_for_every_documented_origin() -> None:
    realm = json.loads(REALM.read_text(encoding="utf-8"))
    clients = [
        client for client in realm["clients"] if client["clientId"] == "aegis-ui"
    ]
    assert len(clients) == 1

    client = clients[0]
    assert LOCAL_ORIGINS <= set(client["redirectUris"])
    assert {f"{origin}/auth/callback" for origin in LOCAL_ORIGINS} <= set(
        client["redirectUris"]
    )
    assert LOCAL_ORIGINS <= set(client["webOrigins"])
    assert client["attributes"]["post.logout.redirect.uris"] == "+"


def test_bootstrap_synchronizes_existing_keycloak_volumes() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")

    assert "/opt/keycloak/bin/kcadm.sh" in bootstrap
    assert 'update "clients/$kc_ui_client_id"' in bootstrap
    assert "redirectUris=$kc_ui_redirects" in bootstrap
    for origin in LOCAL_ORIGINS:
        assert origin in bootstrap
