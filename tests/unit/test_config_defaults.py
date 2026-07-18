"""Local service defaults must not resolve through `localhost`.

On Windows `localhost` resolves to `::1` before `127.0.0.1`, and the compose
ports publish on IPv4 only — so every connection waits for the IPv6 attempt to
fail before falling back.  Measured on the dev stack: **2.05 s per connection
via `localhost` against 0.01 s via `127.0.0.1`**.  Nothing errors, so it is
invisible until something connection-heavy runs: the integration suite took
**1:59:59** on `localhost` and **37 s** on `127.0.0.1`, the same 244 tests.

That is a footgun with no local symptom, which is exactly what a test is for.
"""

from __future__ import annotations

import pytest

from aegis.config import Settings

pytestmark = pytest.mark.requirement("T21")

#: Keycloak is the one deliberate exception. Its URL is an *identity*, not just
#: an address: it is the OIDC issuer and must match the `iss` claim Keycloak
#: mints, byte for byte. Pointing it at a literal IP 401s every request — which
#: is how this exception was discovered.
ISSUER_SETTINGS = {"keycloak_url"}

LOCAL_ADDRESS_SETTINGS = {
    "database_url",
    "fga_api_url",
    "minio_endpoint",
}


def test_local_service_defaults_use_the_literal_loopback_address() -> None:
    defaults = Settings.model_fields
    for name in LOCAL_ADDRESS_SETTINGS:
        value = str(defaults[name].default)
        assert "localhost" not in value, (
            f"{name} defaults to {value!r}; use 127.0.0.1 so connections do not "
            "stall on a failed IPv6 attempt (see this module's docstring)"
        )
        assert "127.0.0.1" in value, f"{name} should target loopback, got {value!r}"


def test_the_issuer_setting_is_exempt_and_stays_exempt() -> None:
    """Named explicitly so the exemption is a decision, not an oversight."""
    value = str(Settings.model_fields["keycloak_url"].default)
    assert "localhost" in value, (
        "keycloak_url must match Keycloak's configured issuer hostname; "
        "changing it to an IP invalidates every token"
    )


def test_every_local_default_is_classified() -> None:
    """A new local-service setting must land in one bucket or the other."""
    suspects = {
        name
        for name, field in Settings.model_fields.items()
        if isinstance(field.default, str)
        and ("localhost" in field.default or "127.0.0.1" in field.default)
    }
    unclassified = suspects - LOCAL_ADDRESS_SETTINGS - ISSUER_SETTINGS
    assert not unclassified, (
        f"unclassified local-service settings: {sorted(unclassified)}. Add each "
        "to LOCAL_ADDRESS_SETTINGS (plain address — use 127.0.0.1) or "
        "ISSUER_SETTINGS (identity — must match the issuer's own hostname)."
    )
