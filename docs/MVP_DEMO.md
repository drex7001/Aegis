# Phase 2 MVP demo

This is the blocking Phase 2 operator journey. It proves the governed loop on
the fictional T25 corpus: land a source, extract a proposal, review it as a
human, accept it, rebuild the derived projection, inspect provenance, and
adjudicate an identity candidate. Nothing in `data/sample/mvp/` represents a
real person or event.

Allow 30–45 minutes for a first run. The application steps are entirely in the
workspace UI. Terminal commands only prepare the disposable environment and
load the remainder of the deterministic fixture.

## Pass record

Record this run as `MAN-P2-001` with the operator, date, commit, operating
system, result, and any deviation. A pass requires all of these observations:

- extraction creates a suggestion and no canonical claim;
- a named analyst accepts the suggestion with an evidence note;
- an admin rebuild reports one edge and the graph refreshes;
- the edge opens a provenance panel with its source and three separate
  gradings;
- the Sinhala/English Nimal Perera pair scores above `0.80`, is adjudicated in
  the UI, and becomes one search result after a rebuild;
- the two fictional Ruwan Silva namesakes remain two search results;
- both contradictory Maya Fernando dates are visible together, while the
  ontology-restricted `has_nic` value is absent for the analyst; and
- an analyst never sees the admin-only **Rebuild projection** action.

Do not paste claim text, identifiers, tokens, screenshots, database dumps, or
browser storage into the pass record. The fictional run needs only the result
and the observations above.

## 1. Prepare an isolated local environment

Prerequisites are Docker with Compose, `uv`, Node.js 22 with npm, and Bash for
the idempotent infrastructure bootstrap. Run from the repository root.

Start and synchronize the local services:

```bash
docker compose -f infra/docker-compose.yml up -d --wait
bash infra/bootstrap.sh
uv sync --locked --extra dev
```

The bootstrap updates an existing development Keycloak volume as well as a
fresh one, so sign-out can return to the served app on ports 8000, 5173, or
4173.

Create a dedicated database. Never point this walkthrough at the normal
`aegis` database:

```bash
docker compose -f infra/docker-compose.yml exec -T postgres dropdb --if-exists -U aegis aegis_mvp_demo
docker compose -f infra/docker-compose.yml exec -T postgres createdb -U aegis aegis_mvp_demo
```

Set the demo environment in every terminal used below. PowerShell:

```powershell
$env:AEGIS_DATABASE_URL = "postgresql+psycopg://aegis:aegis-dev@127.0.0.1:5433/aegis_mvp_demo"
$env:AEGIS_VAULT_BACKEND = "filesystem"
$env:AEGIS_VAULT_PATH = "output/mvp-demo/vault"
```

POSIX shell:

```bash
export AEGIS_DATABASE_URL='postgresql+psycopg://aegis:aegis-dev@127.0.0.1:5433/aegis_mvp_demo'
export AEGIS_VAULT_BACKEND=filesystem
export AEGIS_VAULT_PATH=output/mvp-demo/vault
```

Migrate the disposable database and build the workspace:

```bash
uv run aegis db upgrade
cd ui
npm ci
npm run build
cd ..
```

Start the served production bundle and leave it running:

```bash
uv run aegis serve --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/sources>. Use only these local development
accounts:

| Responsibility | Username | Password |
|---|---|---|
| Land, extract, review and inspect | `dev-analyst` | `analyst` |
| Rebuild the derived projection | `dev-admin` | `admin` |

These credentials belong only to the imported local development realm.

## 2. Complete the UI-only governed loop

Sign in as `dev-analyst`.

1. On **Sources**, leave **File** selected and choose
   `data/sample/mvp/remand-register.txt`.
2. Leave **Source** as `Manual upload` and **Handling** as `open`.
3. Enter `https://example.test/fictional-remand-register` in
   **Collected from**. Under **Collection details**, enter
   `fictional-demo-v1` as the collection policy.
4. Select **Land file**. The outcome must say **Landed** and show a digest.
   Expand the new `remand-register.txt` row and confirm the origin and policy.
5. Leave **Producer** as **Structural — deterministic rules** and select
   **Extract**. The row must report **1 suggestion waiting for review**.
6. Open **Review**. The proposed `co located in prison with` item must be in
   **Waiting** status and identify `structural_pass v1` plus its record.
7. Open the proposal. Leave assertion type as `reported`, enter
   `Fictional remand register supports this reported co-location claim.` in
   **Note**, and select **Accept**. The waiting list must become empty.

The extraction step is allowed to write only to the review queue. The claim
exists because the named analyst accepted it, not because a producer emitted
it (Article VII).

Select **Sign out**, then sign in as `dev-admin` and open **Graph**.

8. The page must say the projection has not been built and show
   **Rebuild projection**. Select it once.
9. Confirm the exact outcome starts with `Rebuilt 1 edges / 1 segments at
   revision 0.` and that the stale/not-built warning is replaced by
   `Built at identity revision 0`.
10. Sign out, return as `dev-analyst`, and open **Graph**. Confirm there is no
    **Rebuild projection** action.
11. In the bounded overview, select the rendered edge. Its provenance panel
    must show the remand-register source record, the claim, and separate
    **Source reliability**, **Information credibility**, and
    **Analytic confidence** rows. It must not show a combined confidence score.

That is the charter's ingest → suggest → review → accept → projection loop.
The account switch is deliberate separation of duties; every action still
happens through the UI.

## 3. Exercise the complete T25 fixture

In a second terminal with the same three environment variables, load the
remaining deterministic fixture:

```bash
uv run aegis ingest mvp --output output/mvp-demo/fixture
```

The command must finish with ten records, one quarantined record, two new
suggestions, fourteen curated claims, one Splink candidate, and one projection
edge. It makes no hosted-model call: the semantic path consumes the checked-in,
prompt-digest-pinned cache.

Refresh the workspace and sign in as `dev-analyst`.

1. Open **Review**, then **Identity**. Open the Nimal Perera / නිමල් පෙරේරා
   candidate. Its producer must be `splink`, score `0.99` (and therefore above
   the `0.80` live threshold), and the evidence waterfall must show supporting
   and opposing features separately.
2. Leave **Same person** selected. Enter
   `Aliases, date of birth and affiliation align across the Sinhala and English records.`
   as the evidence note, then select **Record decision**. The candidate leaves
   the waiting list.
3. Open **Graph**. It must warn that the projection is behind identity revision
   1. Sign out, sign in as `dev-admin`, open **Graph**, and select
   **Rebuild projection**. Confirm
   `Rebuilt 1 edges / 1 segments at revision 1.`
4. Return as `dev-analyst`. Search for `Nimal`; exactly one **Nimal Perera**
   result must appear. Search for `Ruwan Silva`; exactly two results must
   remain. Do not merge them: their fixture dates and aliases deliberately
   describe different people.
5. Search for `Maya Fernando`, select the result to focus the graph, then
   select the Maya node. The entity panel must place `1988-02-10` and
   `1989-02-10` together with a visible **contradicts** indication. The
   restricted fictional identifier predicate `has_nic` and its value must be
   absent for this analyst.

Optionally inspect the semantic proposal in **Review → Suggestions**. Its
producer must be labelled `cached:*`; it remains a proposal until a human
reviews it.

## 4. Cleanup

Stop `aegis serve` with Ctrl+C. Then remove only the disposable demo database
and local output:

```bash
docker compose -f infra/docker-compose.yml exec -T postgres dropdb --if-exists -U aegis aegis_mvp_demo
```

PowerShell:

```powershell
Remove-Item -LiteralPath output/mvp-demo -Recurse -Force
```

POSIX shell:

```bash
rm -rf -- output/mvp-demo
```

Use `docker compose -f infra/docker-compose.yml down` only if this walkthrough
started the shared local stack. Do not use `down -v`, `make nuke`, or the MVP
reset command against a non-fixture database.

## Troubleshooting and drift check

- **Invalid redirect URI after sign-out:** rerun `bash infra/bootstrap.sh`; it
  synchronizes older Keycloak volumes. Reloading the realm JSON alone does not
  update an existing realm.
- **The graph says it is stale:** sign in as the admin and rebuild. An analyst
  cannot and should not receive this control.
- **No suggestion after extraction:** confirm the selected file is exactly
  `data/sample/mvp/remand-register.txt` and the structural producer is selected.
- **A CLI import fails against `localhost`:** use the documented `127.0.0.1`
  database address; the Compose PostgreSQL port is IPv4-bound.

Before a phase review, run the runbook contract and workspace journey:

```bash
uv run pytest -q tests/contract/test_mvp_demo_runbook.py
cd ui
npm run typecheck
npx playwright test e2e/provenance.spec.ts
```

The contract pins commands, labels, fixture paths, local roles, cleanup, and
the manual real-data boundary. If the product changes, update this document in
the same pull request; deleting an assertion is not a substitute for repairing
the operator path.

## Appendix A — authorized real-OSINT smoke (`MAN-P2-002`)

This appendix is manual, operator-run, and non-blocking. It is not part of CI
and never replaces the fictional gate above. Run it only with written authority
for the specific open-source material and after reading `data/real/README.md`.

Before starting, record only these metadata fields in the manual test system:

- authorization or case reference, responsible owner, and expiry if any;
- public source URL, collection policy, retention class, and handling code;
- environment and commit; and
- provider/egress decision and the cleanup owner.

Use a new disposable database and filesystem-vault directory, following the
same setup and cleanup pattern as `aegis_mvp_demo`. In the workspace, land one
small authorized public document with its real source URL and collection
policy, run the deterministic structural producer, and confirm that any output
stops in **Review** until a named human acts. Inspect only enough of an accepted
fictional or authorized claim to confirm provenance and authorization behavior.

Provider and egress rules:

- The structural producer is local and is the default for this smoke.
- The workspace's semantic option is an offline mock; it does not prove a
  hosted provider path.
- Do not send real text, prompts, embeddings, logs, or identifiers to a hosted
  model or third-party service. Phase 8 owns provider approval and egress
  controls. If a separately approved provider exercise is required, its
  written authorization and data-processing conditions supersede this smoke.

Never use a national identity number for a real person, even if a public page
prints one. Do not interpret an association as guilt. Do not capture sensitive
output in screenshots, terminal logs, CI artifacts, tickets, PRs, or the manual
test record. Record only pass/fail, timestamps, counts that reveal nothing
about the subjects, and defects stated without copied content.

At the end, close the browser, stop the server, drop the disposable database,
delete its vault/output directory, and verify that no downloaded or copied
source remains outside the authorized evidence location. A failure to clean up
is a failed manual smoke, even when the UI behavior passed.
