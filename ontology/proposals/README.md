# Ontology change proposals (spec 08 §7)

One file per ontology change: `NNN-short-title.md`, containing the motivation,
the YAML diff, the **competency questions** the change answers (GOAL.md §7.9),
why the declared compatibility class is right, and a migration plan when the
bump is major. Copy `000-template.md` to start.

Review happens on the PR; approval merges the proposal and the version bump
together.

## What CI enforces (`aegis ontology check-release`)

1. `ontology/release.json` names a proposal, and that file exists here.
2. It declares a compatibility class — `major`, `minor` or `patch`.
3. The **diff against the previous released artifact** is no stronger than the
   declared class. Removing a predicate, retyping a property, changing a
   handling floor, or reordering `handling_codes` is `major`; the check refuses
   a bump that calls any of them `minor`.
4. Versions advance — the composition's and every module's.
5. The archived artifact still hashes to what `release.json` recorded, so
   comparing against a committed file is trustworthy.
6. A major bump archives the prior module sources under
   `ontology/history/<version>/`.

Comparison reads `ontology/history/composed-<previous>.json`, never git
history (H-16), so the check answers the same way on a bare checkout with no
remote.

## Why the class matters more than it looks

Claims are immutable and stamp the ontology version current when they were
recorded (ADR-013). A bump that removes vocabulary while calling itself minor
does not fail loudly — it leaves rows nobody can interpret, and the failure
surfaces years later with no way back.

## The existing proposals

`001`–`003` are **backfilled**: they describe changes that landed at T30, T32
and T34, written when T35 built the workflow. Every bump from `1.5.0` onward is
proposed before it merges.
