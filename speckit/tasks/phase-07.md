# Phase 7 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 6 (T77).

> **Status: ACTIVE from 2026-08-24.** Pre-authored 2026-07-17, amended
> 2026-07-18 by ADR-033, and **re-validated by T78 against the as-built
> system** — the eleven divergences and their dispositions are recorded in
> `../specs/13-disclosure-packages.md` §0, and the decisions they produced are
> ADR-061…ADR-066. Task text below is the corrected version; where a
> pre-authored sentence was wrong, the divergence id (G1…G11) says where to read
> why. Charter: `../phases/phase-07-sharing-governance.md` · specs:
> `../specs/03-security.md` (§§6–13 new or promoted),
> `../specs/13-disclosure-packages.md` (authored by T78).

## Milestone A — Specs, tooling & response modes

**T78. ⛓ Spec 13 + spec 03 + the read-surface inventory** (charter §Specs) —
**DONE 2026-08-24.** Re-validated this plan against the as-built system; authored
`specs/13-disclosure-packages.md` (BagIt profile, manifest, redaction-log schema,
signing, recipient grants, expiry/acknowledgement/revocation); promoted specs/03
§4 and added §§6–13 (response modes, compartments, judicial states, precedence
matrix, break-glass, oversight, the read-surface inventory, B-08 enforcement);
appended ADR-061…ADR-066.

The **read-surface inventory** is frozen in specs/03 §12 and covers both API
reads (§12.1, with each surface's filter path and response mode) and non-API
egress (§12.2 — CLI, database, object store, backups, logs, projections). It
drives every exclusion test in this phase; **a read surface not on it is a
defect**.
AC (met): spec 13 exists; specs/03 updated; the inventory is frozen and each
entry names its filter path and mode; divergences are ADR'd or dispositioned in
spec 13 §0.

**T78a. Python linter in the toolchain** (P6 carryover, G11) — `ruff` added with
a configuration that matches the code as written, a `make lint` target, and a CI
step. The Phase 6 exit review recorded the cost of not having one: a `NameError`
that broke thirty integration tests and would have been caught in under a second.
It lands **before** the first feature task so the diff is a tooling diff and not a
tooling diff wearing a feature's clothes.
AC: `make lint` passes on a clean tree; CI fails on a lint error; the initial
ruleset is recorded with a reason for each rule that was disabled rather than
fixed; no behavioural change (the test suite result is identical before and
after).

**T79. ⛓ Response-mode policy** (specs/03 §6, ADR-061; G1, G2, G3) — **not**
"field-level sensitivity on reads": that shipped at P2 T24a in its `omit` mode
and the Phase 1 debt is recorded closed in specs/03 §4.1. What this task builds
is the **policy that chooses between the three modes** (H-25) and the two modes
P2 did not ship.

One policy table, read from one place, applied per resource class: `omit`
(default), `marked` (predicate named, value withheld — the shape
`aegis/sets/sharing.py` already uses), `counts` (disclosure only). Object views,
geo features, object-set definitions and audit records become `marked`; search,
graph, timeline, findings and alerts stay `omit`; previews and packages are
`counts`.
AC: every surface in the T78 inventory resolves to a row in the policy table, and
a contract test fails if one does not; on a `marked` surface a restricted
predicate returns `{predicate, withheld: true}` and **nothing else** — no value,
count, grading or id (ADR-061); on an `omit` surface the same claim is absent; a
sort or filter on a predicate above the caller's clearance is **422**, not an
empty list; the P5 withheld-geometry carryover is closed by the geo row.

## Milestone B — Compartments

**T80. ⛓ Compartments live** (specs/03 §7, ADR-062; needs T79; G4) — the
canonical Postgres model (`compartment`, `compartment_member`,
`compartment_assignment`) is the source of truth; row visibility is decided
inside `claim_filters`; the FGA `compartment` type is projected through the
existing `authz_outbox` for **route-level** checks only and never decides a row.
**Default off** — zero behavioural change for uncompartmented data.

Includes the FGA object-type stub codegen carried from ADR-038 **if it earns its
place here** — this is its first real consumer, and if one call site does not
justify generated code, that is recorded rather than built.
AC: with no compartments defined the entire existing test suite passes unchanged
(the `NOT EXISTS` is true for every row — structural, not a promise); a
compartmented claim is invisible to non-members on every inventory surface;
compartment grants compose with, never replace, handling-code and case filters;
an expired `compartment_member` row stops authorizing at request time with no job
having run; `aegis authz rebuild` re-derives the compartment tuples.

**T81. Informant pattern (synthetic)** (specs/03 §7.4; GOAL.md §21; needs T80) —
pseudonym entity plus handler-compartment identity entity, with the linkage as a
claim **inside the compartment** so it is filtered by T80's mechanism rather than
by a special case. Tested with synthetic data regardless of whether real
informant data ever exists.
AC: the synthetic informant's identity resolves only for a handler; every other
role — **including `admin`** — sees the pseudonym; no projection, search index or
export contains the linkage; the audit trail records that the linkage was read,
by whom and why, without restating the identity in `audit_log.detail`; the
docstring and spec both state that this is a compartment prototype and **not**
GOAL.md §21's protected-source boundary (H-27).

## Milestone C — Judicial states

**T82. ⛓ Sealed/expunged lifecycle** (specs/03 §8, ADR-063, ADR-064; needs T79;
G5, G6) — the `judicial_state` model; `seal_record` implemented for both
`source_record` (reaching its derivatives and claims) and `claim` (reaching only
itself); sealed rows excluded **in `claim_filters`**, so every projection rebuild
excludes them at source.

Expungement is **destruction with a tombstone and is irreversible** (ADR-064) —
the charter's "reversible only by policy" is retired. It requires a supervisor, a
reason, and an `authority_ref` resolving to a valid legal authority.
AC: a sealed record disappears from every inventory surface for non-auditors and
reappears, history intact, for the auditor (charter exit №2); a projection
rebuilt after sealing contains no row, no id and no count for it, proved by
rebuild-and-diff rather than by reading the render path; unsealing restores
visibility exactly; expungement without its precondition is rejected and the
attempt audited; **`aegis audit verify` still passes after an expungement**;
sealed **and** compartmented is denied to an auditor who is not a member (specs/03
§9).

## Milestone D — Disclosure & export

**T83. ⛓ Package builder + manifests** (specs/13; needs T79; G9) — BagIt
container (RFC 8493) with payload and tag manifests, canonical serialization, the
Aegis manifest, detached Ed25519 signature over the tag manifest, and a
`disclosure_package` record. Input is an object set (P6) or a case; building and
exporting are separate audited actions.
AC: the payload and tag manifests verify; **verification succeeds using only
`sha256sum` and an Ed25519 verifier, with no Aegis code in the path**; a package
built twice from the same inputs is byte-identical apart from `package_id` and
`built_at`; the export action records recipient, purpose and legal basis in
audit; the route lint fails on a **new record-returning route absent from the
T78 inventory** — which is what a lint can prove, rather than the pre-authored
claim that no other bulk path exists (M-20).

**T84. Redaction + handling ceiling** (specs/13 §5, §6, §10; needs T83) — the
recipient grant caps the build: the grant's ceiling and compartment set are
composed into `claim_filters` **before assembly**, never filtered out of an
assembled payload. The redaction log records reason, resource and count — never a
value, an id or an excerpt — and never names a compartment.
AC: an export never contains handling levels above the recipient's grant and its
redaction log is attached and accurate (charter exit №1); a zero-redaction export
still ships a log with `entries: []`; a preview-leakage test proves no seeded
withheld value appears anywhere in the serialized preview payload; building
against an expired or not-yet-valid grant fails closed and is audited.

**T85. Legal authority, purpose vocabulary & retention** (specs/03 §13, ADR-065;
B-08; G7) — the P2 governance seams go live. `legal_authority` as a **governance
table, not an ontology object**; `source_record.authority_ref` /
`collection_policy_ref` and `watchlist_alert.authority_ref` resolve into it;
**purposes become an ontology vocabulary** in the platform module via the P3
proposal workflow (minor bump), and `authorize` rejects a term outside it;
retention classes with review dates, a **proposal-only** disposition queue, and a
legal hold that blocks disposition entirely.
AC: the platform module gains `purposes` through a proposal with both version
bumps and `aegis ontology check-release` green; a purpose outside the vocabulary
is rejected and the denial audited; an **expired legal authority fails closed on
the reads it governs** (charter exit №6), naming the expired authority in the
denial; what was recorded while the authority was valid stays readable; the
disposition queue destroys nothing and a legal hold blocks it; T83's manifest
includes the legal basis of every included source, including one marked
`authority_expired_at_collection`.

## Milestone E — Break-glass & oversight

**T86. Break-glass flow** (specs/03 §10, ADR-066; needs T80; G10) — emergency
access as an explicit, reasoned, time-boxed elevation held in `break_glass_grant`
and read from canonical state on **every** request. **No FGA tuple is written at
all.** Scope is a clearance ceiling and optionally a case — never a compartment,
never a seal exception.
AC: a break-glass request without a substantive reason is rejected
(`required_text_is_substantive`); the elevation is **denied at request time after
expiry even with a stale FGA tuple seeded by hand** (charter exit №4); it never
grants a compartment and never unseals, asserted against specs/03 §9's matrix;
every use notifies the auditor, creates a mandatory review record, and is
reviewable as a **single** query; the grant id appears on every request that used
it.

**T87. Insider-threat queries + auditor console** (specs/03 §11; ADR-045; needs
T86) — the auditor's oversight kit and the workspace screen ADR-045 moved out of
Phase 4 and named this phase: bulk reads, off-case access, repeated subject
lookups, export anomalies, break-glass uses (unreviewed first), unacknowledged
disclosures.
AC: seeded anomalous patterns each surface in their query; the screen is reachable
only by the `auditor` role; the queries expose audit **metadata**, never protected
content — asserted by a leakage test over the response payloads; querying audit
from the console is itself audited.

**T88. Full-surface exclusion proof** (charter exits №2 + №5; needs T80–T85) —
the owning task for the phase's headline guarantee, as an automated matrix: for
every surface in the T78 inventory × {compartmented row, sealed record,
restricted field, expired authority}, the wrong reader sees nothing — or the
marked form, where and only where specs/03 §6.2 says so.
AC: the matrix passes for every inventory surface — search, sets, projections,
exports, object views, geo, timeline, analytics, alerts, audit; **a newly added
read surface fails CI until it registers in the inventory and the matrix**; the
precedence matrix (specs/03 §9) is a test, row by row, including the two negative
rules (no role is a superuser; elevations do not compose).

**T89. Phase exit review** — walk the charter's exit criteria; update speckit docs
where reality diverged; append ADRs; write
`../reviews/phase-07-exit-review.md`; tag `phase-7-governance` per the git
workflow. Also disposition the two carryovers this phase deliberately deferred:
**watchlist sharing** and the `owner_clearance` behaviour that goes with it,
which needed T80's grant vocabulary before they could be stated honestly.
AC: every gate criterion checked (non-deferrable, ADR-025); non-blocking
deliverables carried over with owner + target phase recorded; `docs/POLICY_PROFILE.md`
(specs/03 §13.4) lists every control the solo-OSINT profile relaxes and why.

## Explicit non-goals for Phase 7

Real multi-agency federation, originator-control enforcement across
organizations, cross-border policy packs, signed inter-agency exchange protocols
(all P9 federation-trigger territory — the package *format* lands here, the
federation *protocol* does not), mandatory compartment UX for the solo OSINT
deployment (machinery exists and is tested; it is not imposed), recipient key
management (a pilot-gate operational concern), and automatic retention
destruction (ADR-064: a human decides, always).
