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

### Where things are (P4 layout)

The workspace grew a **left rail** at T42 and the screens named below moved into
it; the API and every step of this loop are unchanged. Reading top to bottom the
rail holds:

- **Cases** — the case switcher, and *All cases*. Empty until you open one.
- **Workspace** — **Sources**, **Review**, **Graph**. Every instruction in this
  runbook that says "open **Review**" means this group.
- **Object types** and **Interfaces** — one screen per declared ontology type,
  generated from the ontology rather than written per type (ADR-043). Nothing in
  this runbook needs them; they are listed so their presence is not a surprise.

Two things above the active view are worth recognising when they appear. A
**caution-coloured banner** means either that this bundle was built against a
different ontology version than the server is running, or that you are in a
**historical (as-of) view** — in which case every value on the page is what was
recorded at that moment, and the banner names what is *not* historical. Neither
should appear during this runbook.

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

## 3a. One incident on three surfaces (P5, T64)

Added by Phase 5. The rest of this runbook proves the governed loop; this proves
the phase's headline criterion — **the same incident renders consistently on
map, timeline and graph from one claim set**.

The automated form is
`tests/integration/test_incident_consistency.py` plus `ui/e2e/incident.spec.ts`,
and they are what CI runs. This is the version a person walks, because the
criterion is about what a reader can find out, and only a reader can check that.

1. **Record the occurrence once.** In the workspace, record an arrest with three
   or more participants at a named place, on a stated day. (Through the API:
   `POST /v1/events` with `participants` and `places`.) Note the event id it
   returns.

2. **Object view.** Open the event. Every participant is listed under the role
   the source gave them — `Arrestee`, `Arresting officer` — and **every value
   opens its provenance**. Then open one *participant*. The arrest appears under
   **Referenced by**, because a participation claim is subjected to the event
   and the participant's page reads it from the other end.

3. **Map.** The incident is at its place. If the place is known only to a
   district, it is drawn as an **area** — not a pin, at any zoom. Check three
   zoom levels. A place whose geometry you are not cleared to read is listed
   under *Not shown on the map* with the reason, never placed at a guess.

4. **Timeline.** One row **per assertion** — three arrestees are three rows —
   and there is no separate row for "the event". A stated day renders as a
   **range**, visibly wider than a stated instant. Anything undated is counted
   below the axis rather than dropped.

5. **The window is one window.** Narrow to a range containing the incident.
   Walk Map → Timeline → Graph using the links in each header: the range comes
   with you, each surface shows the incident, and the URL carries `from`/`to`.
   Now narrow to a range *excluding* it. It disappears from all three. Nothing
   renders on one surface that the filter excludes on another.

6. **The graph is a cache.** A freshly recorded incident is on the map and the
   timeline immediately, and reaches the graph after a projection rebuild
   (Article XIII). An admin can rebuild from the graph view. This is the one
   asymmetry between the three surfaces and it is deliberate — but if the graph
   showed the incident *without* a rebuild, that would be a defect worth
   reporting.

7. **Precision, from two clearances.** Where a place carries both a coarse
   public geometry and a finer restricted one, sign in as a lower-clearance
   analyst: the map draws the **coarse** shape. Nothing on the page says a finer
   one exists. That is authorized generalization — a recorded claim the filter
   left, not a blur the server computed.

Record pass/fail per step. A defect here is a phase-gate defect, not a polish
item.

## 3b. One set, two analysts (P6, T76)

Added by Phase 6, and it proves that phase's headline criterion — **a set stores
a question, never an answer**, so sharing one hands over the question and not
the sharer's clearance.

The automated form is `tests/integration/test_phase06_exit.py`, and that is what
CI runs. This is the version a person walks, because the criterion is about what
a second reader can and cannot find out, and only a second reader can check it.

You need two accounts on one case with **different clearances**. Everything else
must be held equal — same case membership, same role — so that a narrower answer
cannot be explained by anything except the filter.

1. **Create the set, case-scoped.** As the cleared analyst, build a set in the
   Set Builder (`type: person` is enough) and scope it to the case. Note the set
   id.

2. **Share it.** Grant the narrower analyst **`evaluator`**, not `viewer`. That
   is the weaker grant on purpose: running somebody's saved query and reading it
   are different disclosures, so a colleague can be given the answer without
   being given the question (spec 12 §5.2).

3. **Drive an analytic from it.** Run a metric over the set. The finding panel
   shows each finding **with its caveat**, and the manifest names the set, its
   pinned version, and an `evaluation_digest`.

4. **Drive a watchlist from it.** Create a watchlist over the same set, then
   sweep it explicitly:

   ```bash
   aegis watchlists evaluate --watchlist <id>
   ```

   Nothing fires on the write path — that is ADR-056, and the watermark on the
   watchlist is how you can tell a sweep happened. Before the first sweep it is
   **null**, which reads as a gap rather than as "nothing found".

5. **Now sign in as the narrower analyst and evaluate the same set.** Not a
   copy — the same set id, the same version. Three things must be true at once,
   and checking only one of them is how this property is usually lost:

   - the narrower analyst still sees **something** (an empty answer would pass a
     careless "fewer results" check while proving nothing);
   - they see **strictly fewer** members than the cleared analyst; and
   - the members missing are exactly the ones whose only claims are above their
     clearance — an entity carries no handling code of its own, so "exists, for
     this caller" means "some claim they may read mentions it".

6. **Compare the two runs.** Run the same metric over the same set as the
   narrower analyst. The two `analytic_run` rows carry **different**
   `evaluation_digest` and `authorization_digest` values. That is the tell that
   the filters ran during evaluation: if the set had stored members, both runs
   would carry the same digest and the difference would have to show up
   somewhere downstream, where nobody looks.

7. **A watchlist points the other way, deliberately.** A set evaluates as the
   **caller**; a watchlist sweeps as its **owner** (spec 12 §11.3), because an
   alert nobody may read is not an alert. Create a watchlist as the narrower
   analyst over the same set and sweep it: it produces no alert from evidence
   they cannot read. Both behaviours are intended, and they point opposite ways,
   so confirm both rather than assuming one from the other.

Record pass/fail and counts only. Do not paste member lists, matched identifier
values, or alert contents into the test record — the whole point of the step is
that some of them are not for every reader.

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
