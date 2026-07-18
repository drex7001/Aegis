# Phase 7 — Task Breakdown

Ordered; each task lists acceptance criteria (AC). Tasks marked ⛓ block everything
after them; narrower dependencies are noted in the task text. Reference specs in
parentheses. Numbering continues from Phase 6 (T77).

> **Status: PRE-AUTHORED, NOT ACTIVE.** Phases 2–6 must close first (strict
> sequence, ADR-025; package-format work may start after P6 T70 per the
> charter). Authored 2026-07-17 ahead of phase start; **the charter was
> amended 2026-07-18 (ADR-033): canonical Postgres compartment model projected
> to FGA + precedence matrix (H-26), BagIt-based package profile (H-28),
> response-mode policy — base field filtering shipped in P2 T24a, this phase
> adds marked-redaction/counts modes (H-25), request-time break-glass expiry
> (M-21), and enforcement of the P2 governance seams: legal authority,
> purpose vocabulary, retention/disposition (B-08)**. T78 re-validates this
> plan against the amended charter and dispositions the findings tagged P7
> before any other task starts. Charter:
> `../phases/phase-07-sharing-governance.md` · specs: `../specs/03-security.md`
> (promoted), `../specs/13-disclosure-packages.md` (authored by T78).

## Milestone A — Specs & field-level filters

**T78. ⛓ Spec 13 + the read-surface inventory** (charter §Specs) — re-validate
this plan against the as-built system; author `specs/13-disclosure-packages.md`
(manifest format, redaction-log schema, hash manifest, signing); promote
specs/03 §4 (field-level filters) from specced to active and add compartments,
sealed states, break-glass; and write the **read-surface inventory** — the
frozen list of every path data can leave the store (API reads, search, object
sets, projections, geo/tiles, timeline, object views, exports, audit queries).
The inventory drives every exclusion test in this phase; a read surface not on
it is a defect.
AC: spec 13 exists; specs/03 updated; the inventory is frozen in the spec and
each entry names its planned exclusion test; divergences from this plan are
ADR'd.

**T79. ⛓ Field-level sensitivity on reads** (specs/03 §4 — the debt carried
since the Phase 1 exit review) — property-level `sensitivity` from the
ontology enforced in query responses across the inventory's surfaces:
**redact-not-drop** where the row is visible but a field is not; redaction is
marked, never silent.
AC: a `sensitivity: restricted` field is redacted for a low-clearance reader
while the row stays visible (charter exit №3); the response marks the
redaction explicitly; every inventory surface that returns properties passes
the same test; the Phase 1 debt is recorded closed.

## Milestone B — Compartments

**T80. ⛓ Compartments live** (specs/03; needs T79) — the existing unused FGA
`compartment` type goes live: membership gates rows (and fields) orthogonally
to handling codes; **default off** — zero behavioral change for
uncompartmented data (the solo-user friction risk).
AC: with no compartments defined, the entire existing test suite passes
unchanged; a compartmented row is invisible to non-members on API reads and
projections; compartment grants compose with (never replace) handling-code
filters.

**T81. Informant pattern (synthetic)** (GOAL.md §21; needs T80) — pseudonym
objects with handler-only reads, implemented and tested with **synthetic data
regardless** of whether real informant data ever exists; the
pseudonym-to-identity link lives only inside the compartment.
AC: the synthetic informant's identity resolves only for the handler; every
other role — including admin — sees the pseudonym; no projection, search
index, or export ever contains the linkage; the audit trail records access
without revealing the identity.

## Milestone C — Judicial states

**T82. ⛓ Sealed/expunged lifecycle** (GOAL.md §22; needs T79) — the judicial-
state model; the `seal_record` action (declared in the ontology since 0.3.0,
scheduled for this phase) implemented; sealed records **excluded at source**
in projection rebuilds — never filtered at render; expungement as a governed,
audited operation reversible only by policy.
AC: a sealed record disappears from every inventory surface for non-auditors
and reappears, history intact, for the auditor role (charter exit №2); a
projection rebuilt after sealing contains no trace of the record; expungement
without the policy precondition is rejected and the attempt audited.

## Milestone D — Disclosure & export

**T83. ⛓ Package builder + manifests** (specs/13; needs T79) — disclosure/
export packages as the **only sanctioned bulk output path**: record manifest,
hash manifest, recipient + legal-basis record; input is an object set (P6) or
a case; building and exporting are audited actions.
AC: a package's hash manifest verifies against its contents; the export
action records recipient and legal basis in audit; a route lint proves no
other bulk-output endpoint exists.

**T84. Redaction + handling ceiling** (specs/13; needs T83) — the recipient's
grant caps handling levels in the package; the redaction preview shows
**categories and counts, never values** (GOAL.md §24 reviewed); the redaction
log records what was withheld and why.
AC: an export never contains handling levels above the recipient's grant and
its redaction log is attached and accurate (charter exit №1); a
preview-leakage test proves no withheld value appears in any preview payload.

**T85. Legal-authority objects** (Rule 4; ontology proposal) — collection-
policy references attachable to sources/collections (the OSINT scaling of
Rule 4: the authority is the collection policy, not a warrant — the mechanism
is the real one); surfaced in export manifests.
AC: the ontology gains the object via the P3 proposal workflow (minor bump);
a source carries its collection-policy reference; the T83 manifest includes
the legal basis of every included source.

## Milestone E — Break-glass & oversight

**T86. Break-glass flow** (specs/03; needs T80) — emergency access as an
explicit, reasoned, **time-boxed** elevation with mandatory after-review and
auditor notification on every use.
AC: break-glass requires a stated reason, expires on schedule, and produces
an audit trail the auditor reviews as a single query (charter exit №4); an
unreviewed use is flagged at phase close; elevation never survives its
time-box.

**T87. Insider-threat queries + auditor screen** (needs T86) — the auditor
role's oversight kit: bulk-read detection, off-case access patterns, export
anomalies; a workspace screen for the auditor role.
AC: seeded anomalous patterns (a bulk read, an off-case browse, an oversized
export) each surface in their query; the screen is reachable only by the
auditor role; the queries expose audit metadata, never protected content.

**T88. Full-surface exclusion proof** (charter exits №2 + №5; needs T80–T84)
— the owning task for the phase's headline guarantee, as an automated matrix:
for every surface in the T78 inventory × {compartmented row, sealed record,
restricted field}, the wrong reader sees nothing (or a marked redaction,
per T79's rule).
AC: the matrix passes for every inventory surface — search, sets,
projections, exports, object views, geo, timeline; a newly added read surface
fails CI until it registers in the inventory and the matrix.

**T89. Phase exit review** — walk the charter's exit criteria; update speckit
docs where reality diverged; append ADRs; write
`../reviews/phase-07-exit-review.md`; tag `phase-7-governance` per the git
workflow.
AC: every gate criterion checked (non-deferrable, ADR-025); non-blocking
deliverables carried over with owner + target phase recorded.

## Explicit non-goals for Phase 7

Real multi-agency federation, originator-control enforcement across
organizations, cross-border policy packs, signed inter-agency exchange
protocols (all P9 federation-trigger territory — the package *format* lands
here, the federation *protocol* does not), mandatory compartment UX for the
solo OSINT deployment (machinery exists and is tested; it is not imposed).
