# Ontology change proposals (Phase 3 — spec 08 §7)

One file per proposed ontology change: `NNN-short-title.md`, containing the
motivation, the YAML diff, the **competency questions** the change answers
(GOAL.md §7.9), and a migration plan when the bump is major. Review happens on
the PR; approval merges the proposal and the version bump together, and CI
verifies the bump commit references a proposal file.

CI verifies that `ontology/release.json` references an existing proposal file
for the version it records — the check is a filesystem lookup, not commit
archaeology (spec 08 §7.3). Proposal `001` backfills the modularization bump
itself and lands with **T35**; the directory stays empty until then.
