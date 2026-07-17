# Git Workflow

The rules for how code reaches `master` in this repository. Adopted 2026-07-17
(everything before then was committed directly to master; that stopped with the
roadmap-v2 commit). Model: **GitHub Flow** — trunk-based development with
short-lived branches. AI agents follow these rules too (see `/AGENTS.md`).

## The six rules

1. **`master` is protected and always green.** No direct commits or pushes —
   ever. It must always pass CI and be releasable. GitHub branch protection
   enforces this (PR + green CI check required; admin bypass exists for
   genuine emergencies only, and a bypass should be explained in the commit).
2. **Every unit of work gets a short-lived branch.** One branch ≈ one task ≈
   one PR, merged within days, then deleted. Branch from up-to-date master:

   ```bash
   git switch master && git pull
   git switch -c <type>/<slug>
   ```

3. **Every change lands via a Pull Request** — even solo. The PR is (a) where
   CI runs *before* code reaches master, (b) a forced self-review of the diff,
   (c) an atomic, revertable history unit.
4. **CI must be green before merge, then squash-merge.** The whole branch
   becomes one clean commit on master (1 PR = 1 commit). Merge commits and
   rebase merges are disabled in the repo settings.
5. **Tag phase gates.** At each phase exit review, create an annotated tag:

   ```bash
   git tag -a phase-2-mvp -m "Phase 2 exit: MVP gate passed"
   git push origin phase-2-mvp
   ```

6. **Never rewrite pushed history.** Undo on master is `git revert`, never
   `reset`/force-push. Locally, `git config pull.ff only` prevents surprise
   merge commits.

## Branch naming

`<type>/<slug>` — type matches the commit convention, slug is short kebab-case.
Reference the task ID when one exists.

| Type | Use | Example |
|---|---|---|
| `feat/` | new capability | `feat/t17-mention-extraction` |
| `fix/` | bug fix | `fix/projection-weight-rounding` |
| `docs/` | documentation only | `docs/git-workflow` |
| `test/` | tests only | `test/authz-matrix-gaps` |
| `chore/` | infra, CI, deps, scripts | `chore/backup-cron` |

## Commit messages

Conventional style, as the history already uses:

```
<type>(<optional scope>): <imperative summary ≤ 72 chars>

<body: what and why, wrapped at 72; reference task IDs (T17) and ADRs>
```

AI-assisted commits keep the `Co-Authored-By:` trailer. Since PRs are
squash-merged, the **PR title becomes the master commit subject** — write PR
titles in the same conventional format.

## The day-to-day loop

```bash
git switch master && git pull
git switch -c feat/t17-mention-extraction
# ... work, commit as often as you like ...
pytest -q -m "not integration" && aegis ontology validate   # before pushing
git push -u origin feat/t17-mention-extraction
gh pr create --fill                # PR opens, CI starts automatically
gh pr checks --watch               # wait for green
gh pr merge --squash --delete-branch
git switch master && git pull
```

## PR checklist (self-review, every time)

- [ ] Tests pass locally (`pytest -q -m "not integration"`); integration tests
      if the change touches the store/authz.
- [ ] `aegis ontology validate` if `ontology/aegis.yaml` changed (+ version
      bump per spec 01 §4 / spec 08 §7).
- [ ] Read the full diff on the PR page — you are the reviewer.
- [ ] Constitution check: which Article governs this change? (speckit
      `constitution.md`)
- [ ] Speckit updated if reality diverged (new ADR, charter/task status).
- [ ] No secrets, no real-person identifiers beyond the documented OSINT
      ethics rules (`data/real/README.md`).

## CI policy (GitHub Actions)

- CI (`.github/workflows/ci.yml`) triggers **automatically** on every push and
  PR — nobody runs it manually. It is the merge gate.
- Let it run, even for docs-only changes: a green check on every master commit
  is what makes "master is always green" trustworthy, and this CI costs
  minutes.
- `[skip ci]` in a commit message is allowed only for trivial typo-level doc
  fixes, and should stay rare.
- A red master is the top priority: fix forward or `git revert` the squash
  commit immediately.

## Secrets & data hygiene

- `.env` is gitignored and must stay untracked; only `.env.example` is
  committed. Never paste tokens/keys into code, docs, or commit messages.
- Large binaries (e.g. `Files/*.mp4`) stay out of git. If versioning large
  data ever becomes necessary, use Git LFS — decide via ADR first.
- If a secret ever lands in history: rotate the secret immediately, then
  rewrite history (this is the one exception to rule 6) and force-push with
  coordination.

## Releases & phases

- Phases (speckit roadmap) are the release cadence; the exit-review PR for a
  phase is its release PR, tagged per rule 5.
- `aegis` package version bumps in `pyproject.toml` accompany phase tags.
