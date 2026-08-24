# Phase 7 Charter — Sharing & governance hardening

Status: **ACTIVE from 2026-08-24** (charter amended 2026-07-18 by ADR-033;
further amended by ADR-064 and ADR-065 at T78, before the exit review, as
ADR-025 requires) · tasks: `../tasks/phase-07.md` (T78–T89, plus T78a) ·
re-validated by T78, whose eleven divergences are recorded in
`../specs/13-disclosure-packages.md` §0, dispositioning the 2026-07 review
findings tagged P7: B-08 enforcement, H-25, H-26, H-27, H-28, M-14, M-20,
M-21 · Constitutional basis: Articles IV, VI, VIII, X · GOAL.md §21–24, §27
(exchange packages), Rule 4 · ADR-061…ADR-066

## Objective

Ready for a second user you don't fully trust, and for output that leaves the
system. Until now every governance control has assumed cooperative users; this
phase makes the controls hold against curious insiders and makes exports
defensible artifacts rather than screenshots.

## Architecture layers touched

- **Governance plane:** compartments, sealed/expunged states, break-glass,
  insider-threat queries, legal-authority objects.
- **Consumption:** disclosure/export packages; field-filtering **response
  modes** beyond P2's omit-default (marked redaction, counts — H-25). Base
  field-level filtering shipped in P2 (T24a); this phase adds the policy-
  differentiated modes.
- **Kinetic:** seal_record action (declared in the ontology since 0.3.0,
  scheduled for this phase); export/disclosure actions.

## Deliverables

1. **Compartments**: a **canonical Postgres assignment model** (membership,
   resource/field assignment, versioned grants, expiry) is the source of
   truth, projected into the existing FGA `compartment` type via the outbox
   (H-26 — FGA tuples alone are not a policy record); a **policy precedence
   matrix** (admin, auditor, handler, supervisor, break-glass, legal hold,
   seal) is written and tested; includes the informant-pattern separation
   (pseudonym objects, handler-only reads — GOAL.md §21) tested with synthetic
   data. *Honesty note (H-27):* this is a compartment **prototype** of the
   GOAL.md §21 protected-source boundary — separate security domain/keys,
   two-person disclosure, independent-supervisor alerts remain north-star
   until real informant data exists.
2. **Response-mode policy (H-25)**: the field-filtering modes are defined per
   resource/action and tested: **omit** (default — exploratory search/object
   views, the P2 behavior), **marked redaction** (caller authorized to know
   the schema but not the value), **counts** (disclosure officers only). This
   phase adds the marked-redaction and counts modes; P2 shipped omit.
3. **Sealed/expunged handling**: judicial-state model (GOAL.md §22); sealed
   records excluded from all projections and reads except the auditor role.
   **Amended by ADR-063/ADR-064:** a seal attaches to a source record *or* a
   claim and is excluded at source, never at render; and "reversible only by
   policy" is retired — reversible destruction is not destruction, it is
   suppression, which sealing already provides. Sealing suppresses reversibly;
   expungement destroys content, leaves an audited tombstone, is irreversible,
   and is always a named policy decision made by a person — never a default and
   never a scheduled job (H-26).
4. **Disclosure/export packages**: **BagIt-based container (RFC 8493) + Aegis
   metadata profile** (H-28 — adopt before build): payload/tag manifests,
   detached signature, recipient grant snapshot, expiry, redaction log,
   acknowledgement/receipt record; export is an audited action; packages are
   the sanctioned **disclosure workflow** — an egress inventory (search,
   tiles, API pagination, backups, logs) is maintained rather than claiming
   packages are the only possible bulk path (M-20).
5. **Break-glass**: emergency access flow — explicit declaration, time-boxed
   elevation with **expiry enforced at request time from canonical policy
   state** (M-21 — never only by scheduled tuple deletion), mandatory
   after-review; insider-threat audit queries (bulk reads, off-case access
   patterns, export anomalies) runnable by the auditor role.
6. **Governance enforcement (B-08 — the P2 seams go live)**: legal-authority /
   collection-policy records with validity intervals and fail-closed expiry —
   **amended by ADR-065: a governance table, not an ontology object type**,
   because an ontology object's attributes are claims and a control a source
   can contradict is not a control. What the ontology gains instead is the
   **purpose vocabulary** (platform module, minor bump), so purpose is
   policy-evaluated rather than a free string. Plus retention classes with
   review dates, legal-hold override, and a **proposal-only** disposition
   workflow; and a deployment policy profile (`docs/POLICY_PROFILE.md`) stating
   which controls the solo-OSINT profile relaxes and why.

## Dependencies

- P4: workspace (redaction preview, compartment UX).
- P6 gate closed (strict sequence, ADR-025). Export packages take an object
  set or a case as input; the package format work may start after P6 T70
  (set storage stable).

## Exit criteria

- [ ] An export never contains handling levels above the recipient's grant;
      the redaction log is attached and accurate; the package verifies
      (manifest + signature) on a clean machine.
- [ ] A sealed record disappears from every projection and every non-auditor
      read path, and reappears (auditor-only) with its full history intact.
- [ ] Each response mode (omit / marked redaction / counts) behaves per the
      policy table for its resource class, including nested fields and
      sort/filter behavior (H-25).
- [ ] A break-glass access requires a reason, is denied at request time after
      expiry even with a stale FGA tuple present (M-21), and produces an audit
      trail the auditor role can review as a single query.
- [ ] Compartment tests: a user outside compartment C never sees C's rows via
      search, sets, projections, exports, or object views; the precedence
      matrix tests pass (H-26).
- [ ] An expired legal authority fails closed on the reads it governs (B-08).

## Risks

| Risk | Mitigation |
|---|---|
| Projection/search side-channels leak sealed or compartmented rows | Exit tests enumerate *every* read surface; projection rebuild excludes at source, not at render |
| Redaction preview itself leaks | Preview shows categories/counts, never values; reviewed against GOAL.md §24 prohibited behaviors |
| Break-glass becomes routine | Time-boxed, reason required, auditor notification on every use, reviewed at phase close |
| Governance friction for the solo user | Compartments default off; the machinery must exist and be tested, not be mandatory for OSINT-only data |

## Specs to author or update

- `specs/03-security.md` — **done (T78):** §4 field filtering promoted to
  implemented with §4.1 explaining what it means when a property is a claim;
  §§6–13 added (response modes, compartments, judicial states, precedence
  matrix, break-glass, oversight, the frozen read-surface inventory, B-08
  enforcement).
- `specs/13-disclosure-packages.md` — **done (T78):** BagIt profile, manifest,
  redaction-log schema, signing and key custody, recipient grants, expiry /
  acknowledgement / revocation, and the phase's re-validation divergences (§0).
- `docs/POLICY_PROFILE.md` — authored across the phase, closed at T89.

## Explicit non-goals

Real multi-agency federation, originator-control enforcement across
organizations, cross-border policy packs, signed inter-agency exchange (all
P9 federation-trigger territory — the package *format* lands here, the
federation *protocol* does not).

## Task sketch (expanded into `../tasks/phase-07.md`, T78–T89)

- **A — Specs, tooling & response modes:** spec 13 + spec 03 + the frozen
  read-surface inventory (T78); `ruff` (T78a, the P6 carryover); the
  three-mode response policy (T79). Base field filtering is **not** in scope —
  it shipped at P2 T24a and specs/03 §4.1 records the Phase 1 debt closed.
- **B — Compartments:** the canonical Postgres model enforced in
  `claim_filters` with FGA projected for route checks only (ADR-062), the
  informant pattern, synthetic tests.
- **C — Judicial states:** sealed/expunged lifecycle + projection exclusion.
- **D — Disclosure:** package builder, BagIt manifests, redaction log, export
  action, and the B-08 governance records (legal authority, purposes,
  retention).
- **E — Break-glass & oversight:** elevation flow, insider-threat queries,
  auditor review screen.
