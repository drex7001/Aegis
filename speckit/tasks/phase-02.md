# Phase 2 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them. Reference specs in parentheses. Numbering continues from Phase 1 (T16).

> **Status: PENDING.** Authored with roadmap v2 (ADR-022). Phase 2 closes with the
> **★ MVP gate** — see `../phases/phase-02-mvp-identity-provenance.md`. Anything not
> needed for the demo loop moves to P3+.

## Milestone A — Identity core

**T17. ⛓ Mention extraction & backfill** (specs/05 §1–2) — populate `mention`
rows (raw_text, norm_key) from existing and newly landed source records; verify
the legacy one-mention clusters seeded by T8; **demote cross-document same-slug
from auto-merge to candidate** (the key behavior change vs the prototype —
spec 05 §2.1).
AC: every entity has ≥ 1 mention; a cross-document same-slug pair produces a
candidate in `review_queue`, not a merge; idempotent re-run.

**T18. Deterministic ER rules** (specs/05 §2.1) — rule engine auto-deciding
exact-identifier matches (NIC when lawfully present, vehicle registration +
jurisdiction, passport + country; same norm_key *within one document*), audited
as `rule:<name>`.
AC: fixture with a fictional NIC auto-merges with `decided_by='rule:nic-exact'`
in membership history and audit; cross-document slug alone never auto-merges.

**T19. Splink pipeline** (specs/05 §2.2) — DuckDB backend; transliteration-aware
features (ICU Latin key + raw-script key, Jaro-Winkler + token-set, alias
cross-match, affiliation overlap, graph-context feature, DOB conflict as
negative evidence); blocking rules; candidates above threshold land in
`review_queue` with `producer='splink'` and per-feature waterfall weights in
`producer_meta`; model settings versioned in `aegis/er/settings.py`.
AC: the seeded Sinhala/English transliteration pair scores above threshold and
its queue row carries per-feature weights; a seeded distinct same-name pair does
not auto-suggest above threshold.

**T20. ⛓ Adjudication actions + versioned history** (specs/05 §3) —
`confirm_match`, `reject_match`, `split_entity`, `mark_unresolved` implemented
under the ontology's `adjudicate_identity` action (evidence note required;
dual-control hook honored); membership history versioned; `merged_into` claim on
merge; negative constraints stored on reject; single transaction with audit.
AC: merge-then-split restores the exact prior membership state (history test);
a rejected pair is never re-suggested by T19; every decision carries actor +
note in audit.

## Milestone B — Provenance & review UX

**T21. ⛓ "Why connected?" API** (specs/06) — for any projected edge
(subject, predicate, object): the recorded claims behind it with all three
gradings (Article III), their source records, `claim_relation`
contradictions/corroborations, and the identity-decision line ("decided by /
when / why", spec 05 §4).
AC: every edge in a rebuilt projection resolves to ≥ 1 source record; a seeded
contradiction appears in the response.

**T22. Provenance panel** (specs/07 stage 2) — edge click in the explorer opens
a panel rendering T21: claims with reliability/credibility/verification shown
independently, sources, contradiction badges.
AC: browser smoke test — every rendered edge opens the panel; all three grading
fields visible per claim.

**T23. Review-queue UI** (specs/04, specs/07 stage 2) — queue list with
producer/status filters; accept / edit-then-accept / reject; on acceptance the
human picks the assertion type (plan §4.2); LLM producer metadata (model,
prompt) and Splink score breakdowns rendered; identity candidates adjudicated
from the same surface via T20.
AC: a Gemini-pass suggestion accepted in the UI appears in the rebuilt
projection and a rejected one never does (UI-level re-run of the Phase 1 exit
test); a Splink candidate can be confirmed end-to-end from the browser.

**T24. Contradiction/corroboration surfacing** — `link_claims` exposed in the
panel flow; conflicting property claims (e.g. two DOBs, `conflicts: preserve`)
render side by side with relation badges (Article VIII).
AC: seeded contradictory claims both render, linked by a visible
`contradicts` badge; nothing is hidden or collapsed to one value.

## Milestone C — MVP close-out

**T25. Basic entity search** (ADR-012, minimal) — `GET /v1/search/entities?q=`
using `pg_trgm` over names, aliases, and mention norm_keys,
authorization-filtered before return; search box in the explorer that focuses
the graph on hits.
AC: a transliterated query variant finds the seeded entity; results respect
handling-code and case filters (authz matrix extension); full FTS explicitly
deferred to P6.

**T26. ER evaluation harness** (specs/05 §5) — seeded golden set (known
transliteration pairs incl. Sinhala script, known distinct same-name people);
precision/recall computed in CI on every run; Splink settings changes are
visible in the same diff as their eval results.
AC: CI job publishes precision/recall for the current model; the seeded
distinct-pair stays unmerged in the full pipeline run.

**T27. MVP demo runbook** — `docs/MVP_DEMO.md`: scripted, repeatable
walkthrough on the real OSINT corpus — land a document (PDF or narrative txt)
→ extraction suggests → review/adjudicate in the UI → identity merge → graph
with provenance; includes a reset path (restore baseline, rebuild projections).
AC: a person who didn't build the system completes the loop in one sitting
following only the document (the ★ MVP gate); drift between doc and product
fails the phase review.

**T28. Phase exit review** — walk roadmap Phase 2 exit criteria including the
MVP gate; update speckit docs where reality diverged; append ADRs for changed
decisions; write `../reviews/phase-02-exit-review.md`.
AC: all exit boxes checked or explicitly deferred with reason.

## Explicit non-goals for Phase 2

React workspace and object views (P4), ontology interfaces/functions/SDK
codegen (P3), PostGIS geometry and events (P5), full multilingual FTS and
object sets and watchlists (P6), compartments and disclosure packages (P7),
new LLM capabilities beyond the existing extraction producers (P8).
