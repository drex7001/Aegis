# Phase 7 Charter — Sharing & governance hardening

Status: charter (amended 2026-07-18, ADR-033) · tasks pre-authored:
`../tasks/phase-07.md` (T78–T89; re-validated by T78 at phase start, which
also dispositions the 2026-07 review findings tagged P7: B-08 enforcement,
H-25, H-26, H-27, H-28, M-14, M-20, M-21) · Constitutional basis: Articles IV,
VI, VIII, X · GOAL.md §21–24, §27 (exchange packages), Rule 4

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
   records excluded from all projections and reads except the auditor role;
   expungement as a governed, audited operation — suppression/sealing
   distinguished from legally-required destruction, which is a named policy
   decision, never a default (H-26).
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
   collection-policy objects with validity intervals and fail-closed expiry;
   purpose as a policy-evaluated vocabulary, not a free string; retention
   classes with review dates, legal-hold override, and a governed disposition
   workflow; a deployment policy profile stating which controls are relaxed
   for the solo-OSINT profile and why.

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

- `specs/03-security.md` — promote field-level filter section to implemented;
  add compartments, sealed states, break-glass.
- `specs/13-disclosure-packages.md` — author at phase start (manifest format,
  redaction log schema, signing).

## Explicit non-goals

Real multi-agency federation, originator-control enforcement across
organizations, cross-border policy packs, signed inter-agency exchange (all
P9 federation-trigger territory — the package *format* lands here, the
federation *protocol* does not).

## Task sketch (expanded into `../tasks/phase-07.md`, T78–T89)

- **A — Field filters:** read-path redaction from ontology sensitivity.
- **B — Compartments:** FGA live, informant pattern, synthetic tests.
- **C — Judicial states:** sealed/expunged lifecycle + projection exclusion.
- **D — Disclosure:** package builder, manifests, redaction log, export action.
- **E — Break-glass & oversight:** elevation flow, insider-threat queries,
  auditor review screen.
