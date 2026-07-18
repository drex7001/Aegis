"""Prefixed ULID generation — a platform primitive.

Lives at the top level, not under ``aegis.actions``, because the actions
service and the modules it imports (:mod:`aegis.er.ledger`,
:mod:`aegis.projections`) all need to mint ids.  T17 split it out of
``actions.service`` for that reason but left it *inside* the actions package,
which does not break the cycle: importing ``aegis.actions.ids`` still executes
``aegis/actions/__init__.py`` and therefore the service.  The cycle stayed
latent only because ``actions`` happened to be imported first; T21 tripped it
by importing ``aegis.projections`` first.

This module imports nothing from ``aegis``, and nothing about id generation is
specific to actions.
"""

from __future__ import annotations

import secrets
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str) -> str:
    """Generate a prefixed ULID without adding a runtime dependency."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(secrets.token_bytes(10), "big")
    encoded = ""
    for _ in range(26):
        encoded = _CROCKFORD[value & 31] + encoded
        value >>= 5
    return f"{prefix}_{encoded}"


__all__ = ["new_id"]
