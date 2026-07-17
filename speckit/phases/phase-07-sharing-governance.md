# Phase 7 Charter — Sharing & governance hardening

Status: charter · tasks pre-authored: `../tasks/phase-07.md` (T78–T89;
re-validated by T78 at phase start) · Constitutional basis: Articles IV, VI,
VIII, X · GOAL.md §21–24, §27 (exchange packages), Rule 4

## Objective

Ready for a second user you don't fully trust, and for output that leaves the
system. Until now every governance control has assumed cooperative users; this
phase makes the controls hold against curious insiders and makes exports
defensible artifacts rather than screenshots.

## Architecture layers touched

- **Governance plane:** compartments, sealed/expunged states, break-glass,
  insider-threat queries, legal-authority objects.
- **Consumption:** disclosure/export packages; field-level sensitivity filters
  finally applied on *reads* (specced in Phase 1 — specs/03 §4 — carried as
  known debt since the Phase 1 exit review).
- **Kinetic:** seal_record action (declared in the ontology since 0.3.0,
  scheduled for this phase); export/disclosure actions.

## Deliverables

1. **Compartments**: the existing (unused) FGA `compartment` type goes live;
   compartment membership gates rows/fields orthogonally to handling codes;
   includes the informant-pattern separation (pseudonym objects, handler-only
   reads — GOAL.md §21) implemented if/when such data exists, tested with
   synthetic data regardless.
2. **Field-level sensitivity on reads**: property-level `sensitivity` from the
   ontology enforced in query responses (redact-not-drop where the row is
   visible but a field is not).
3. **Sealed/expunged handling**: judicial-state model (GOAL.md §22); sealed
   records excluded from all projections and reads except the auditor role;
   expungement as a governed, audited, reversible-only-by-policy operation.
4. **Disclosure/export packages**: manifest of included records, redaction
   preview (what's withheld and why, without revealing it), hash manifest,
   recipient + legal-basis record; export is an audited action; packages are
   the only sanctioned bulk output path.
5. **Break-glass**: emergency access flow — explicit declaration, time-boxed
   elevation, mandatory after-review; insider-threat audit queries (bulk
   reads, off-case access patterns, export anomalies) runnable by the auditor
   role.
6. **Legal-authority objects**: collection-policy references attachable to
   sources/collections (Rule 4 scaled to OSINT: the authority is the collection
   policy, not a warrant — but the mechanism is the real one).

## Dependencies

- P4: workspace (redaction preview, compartment UX).
- P6: object sets (export packages take a set as input) — soft; a case can be
  the export unit if P6 slips.

## Exit criteria

- [ ] An export never contains handling levels above the recipient's grant;
      the redaction log is attached and accurate.
- [ ] A sealed record disappears from every projection and every non-auditor
      read path, and reappears (auditor-only) with its full history intact.
- [ ] A field with `sensitivity: restricted` is redacted for a low-clearance
      reader even when the row itself is visible.
- [ ] A break-glass access requires a reason, expires, and produces an audit
      trail the auditor role can review as a single query.
- [ ] Compartment tests: a user outside compartment C never sees C's rows via
      search, sets, projections, exports, or object views.

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
