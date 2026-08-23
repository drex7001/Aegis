"""Watchlists: a standing question, swept explicitly (T75, spec 12 §11)."""

from aegis.watchlists.rules import EXACT, EXACT_IDENTIFIER, RULES, RULE_VERSION
from aegis.watchlists.service import (
    WatchlistError,
    create_watchlist,
    evaluate_watchlist,
    sweep,
    triage_alert,
)

__all__ = [
    "EXACT",
    "EXACT_IDENTIFIER",
    "RULES",
    "RULE_VERSION",
    "WatchlistError",
    "create_watchlist",
    "evaluate_watchlist",
    "sweep",
    "triage_alert",
]
