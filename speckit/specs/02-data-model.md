# Spec 02 — Data Model (Claim Store)

Status: implemented in Phase 1 (v1 reference) — **§2 (identity) rewritten
2026-07-18 by T17a under ADR-028 (identity decision ledger); §3 (claim
arguments) and §7 (traversal projection) rewritten 2026-07-18 by T17b under
ADR-029 (mention anchors + identity-revision resolution) and ADR-030 (honest
aggregation). The review-queue section is still being rewritten by T17c under
ADR-031 (typed suggestion envelope). Where this text conflicts with those ADRs,
the ADRs win.** · Constitutional basis: Articles I, III, IV, V, VIII, X, XIII

DDL below is illustrative Postgres 16; Alembic migrations are authoritative. IDs are
ULIDs with type prefixes (`ent_`, `clm_`, `src_`, `rec_`, `evd_`, `cas_`) — sortable,
non-guessable enough, grep-friendly.

## 1. Sources and source records

```sql
CREATE TABLE source (
  source_id        TEXT PRIMARY KEY,
  source_type      TEXT NOT NULL,      -- ontology: open_source | court_record | human |
                                       -- government_system | sensor | algorithmic | ...
  name             TEXT NOT NULL,
  url              TEXT,
  reliability_scheme     TEXT,         -- e.g. 'admiralty', 'internal-v1'
  reliability_original   TEXT,         -- as graded, e.g. 'B'
  reliability_normalized TEXT,         -- ontology grading.reliability.normalized
  notes            TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- one immutable received artifact: a PDF, a transcript, an arrest list, a pasted text,
-- one LLM extraction run's input snapshot
CREATE TABLE source_record (
  record_id      TEXT PRIMARY KEY,
  source_id      TEXT NOT NULL REFERENCES source,
  ingest_key     TEXT NOT NULL UNIQUE, -- sha256(source_system|source_record_id|version) — idempotency (GOAL.md §9.3)
  content_hash   TEXT NOT NULL,        -- sha256 of raw payload in the vault
  storage_uri    TEXT NOT NULL,        -- evidence-vault object (ADR-007)
  media_type     TEXT,
  source_time    TIMESTAMPTZ,          -- when the source produced it, if known
  received_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  handling_code  TEXT NOT NULL DEFAULT 'open',
  status         TEXT NOT NULL DEFAULT 'landed',  -- landed | quarantined | processed
  quarantine_reason TEXT,
  provenance     JSONB NOT NULL DEFAULT '{}'      -- connector, versions, operator, envelope
);
```

The current provenance headers written by `pipeline/ingest.py` move into `provenance`;
raw bytes move into the vault.

## 2. Entities and identity — the decision ledger (ADR-028)

Rewritten by P2 T17a. Semantics, stages, thresholds, migration and the reversal
test plan live in specs/05; this section owns the schema. The Phase-1 shape
(`mention` + timestamp-versioned `identity_membership`, migration `0005`) is the
migration substrate — §2.6 of specs/05 describes the upgrade.

```sql
CREATE TABLE entity (
  entity_id    TEXT PRIMARY KEY,
  entity_type  TEXT NOT NULL,          -- ontology object type
  label        TEXT NOT NULL,          -- display only; rebuilt from name claims
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  tombstoned_at TIMESTAMPTZ            -- no active memberships, no lineage target;
                                       -- retained forever, ids never reused (specs/05 §5)
);

-- a name-as-written inside one source record. Offsets and script are the H-06
-- minimum: without them a mention cannot be re-anchored to its text.
CREATE TABLE mention (
  mention_id   TEXT PRIMARY KEY,
  record_id    TEXT NOT NULL REFERENCES source_record,
  raw_text     TEXT NOT NULL,
  norm_key     TEXT NOT NULL,          -- slugify() lives on here — a *mention key*, not identity
  char_start   INTEGER,                -- offsets into the derivative text, when known
  char_end     INTEGER,
  script       TEXT,                   -- ISO 15924 when detected: Sinh | Taml | Latn
  language     TEXT,                   -- BCP-47 when detected
  context      TEXT,
  CHECK (char_end IS NULL OR char_start IS NULL OR char_end >= char_start)
);

-- the revision chain. Append-only; revision 0 is the migration baseline.
CREATE TABLE identity_revision (
  revision_id  BIGSERIAL PRIMARY KEY,  -- monotonic; ordering is the chain
  decision_id  TEXT REFERENCES identity_decision,  -- NULL only for revision 0
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- one row per human adjudication (Article VII: decided_by is always a person)
CREATE TABLE identity_decision (
  decision_id   TEXT PRIMARY KEY,
  kind          TEXT NOT NULL CHECK (kind IN ('confirm','reject','merge','split','unresolved')),
  decided_by    TEXT NOT NULL,          -- human actor; never 'rule:<name>' (ADR-027)
  decision_note TEXT NOT NULL,          -- evidence for the decision — required, always
  candidate_id  TEXT REFERENCES er_candidate,     -- the machine input, when there was one
  input_mentions TEXT[] NOT NULL DEFAULT '{}',    -- explicit mention set (splits, manual merges)
  parent_revision_id BIGINT NOT NULL REFERENCES identity_revision,  -- optimistic concurrency
  result_revision_id BIGINT NOT NULL REFERENCES identity_revision,  -- exactly one per decision
  decided_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (result_revision_id)
);

-- revision-keyed, reversible identity (Article V). A membership names the revision
-- that opened it and the revision that closed it; history is never deleted.
CREATE TABLE identity_membership (
  membership_id     TEXT PRIMARY KEY,
  mention_id        TEXT NOT NULL REFERENCES mention,
  entity_id         TEXT NOT NULL REFERENCES entity,
  opened_revision_id BIGINT NOT NULL REFERENCES identity_revision,
  closed_revision_id BIGINT REFERENCES identity_revision   -- NULL = active
);

-- THE invariant (ADR-028 §2): at most one active membership per mention.
-- Enforced by the database, not by application code.
CREATE UNIQUE INDEX ux_membership_one_active
  ON identity_membership (mention_id) WHERE closed_revision_id IS NULL;

-- every candidate pair the machine ever produced, with its explanation
CREATE TABLE er_candidate (
  candidate_id     TEXT PRIMARY KEY,
  mention_a        TEXT NOT NULL REFERENCES mention,
  mention_b        TEXT NOT NULL REFERENCES mention,
  producer         TEXT NOT NULL,       -- 'rule:nic' | 'rule:same-norm-key-in-doc' | 'splink'
  producer_version TEXT NOT NULL,       -- settings version (aegis/er/settings.py), git-tracked
  graph_snapshot_id TEXT,               -- projection snapshot used for context features (H-07)
  score            NUMERIC,             -- match probability; NULL for rule producers
  features         JSONB NOT NULL,      -- per-feature waterfall, verbatim (GOAL.md §10.4)
  pre_verified     BOOLEAN NOT NULL DEFAULT false,  -- rule band: batch-confirmable in one action
  disposition      TEXT NOT NULL DEFAULT 'open'
                   CHECK (disposition IN ('open','confirmed','rejected','unresolved','superseded')),
  decision_id      TEXT REFERENCES identity_decision,  -- set when adjudicated
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (mention_a < mention_b)         -- canonical pair ordering — one row per pair
);

-- a reject is durable: the pair is not re-suggested while the constraint holds
CREATE TABLE identity_negative_constraint (
  constraint_id  TEXT PRIMARY KEY,
  mention_a      TEXT NOT NULL REFERENCES mention,
  mention_b      TEXT NOT NULL REFERENCES mention,
  version        INTEGER NOT NULL DEFAULT 1,   -- superseded by new evidence *type*, never erased
  decision_id    TEXT NOT NULL REFERENCES identity_decision,
  evidence_basis TEXT NOT NULL,         -- what was known when it was written (specs/05 §3.3)
  superseded_by  TEXT REFERENCES identity_negative_constraint,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (mention_a < mention_b)
);

-- rebuildable projection of merge lineage (Article XIII) — losing it loses nothing
CREATE TABLE entity_canonical_map (
  entity_id           TEXT PRIMARY KEY REFERENCES entity,
  canonical_entity_id TEXT NOT NULL REFERENCES entity,
  at_revision_id      BIGINT NOT NULL REFERENCES identity_revision
);
```

`identity_revision` and `identity_decision` reference each other, so the
migration creates both tables first and adds `identity_revision.decision_id` as
a deferred constraint afterwards. Revision 0 carries `decision_id IS NULL` — it
is a baseline, not a decision anyone made.

Merge lineage is **ledger metadata** — reconstructed from `identity_decision` and
the membership rows it closed and opened. There is no `merged_into` claim: a
claim requires a source record (Article I), and administrative metadata has
none. The `merged_into` predicate is retired from the ontology by the T17
migration.

## 3. Claims

```sql
CREATE TABLE claim (
  claim_id     TEXT PRIMARY KEY,
  subject_id   TEXT NOT NULL REFERENCES entity,
  predicate    TEXT NOT NULL,           -- ontology predicate — app-validated (ADR-013), never a DB CHECK
  object_id    TEXT REFERENCES entity,  -- exactly one of object_id / object_value
  object_value JSONB,
  CHECK ((object_id IS NULL) <> (object_value IS NULL)),

  -- mention anchors (ADR-029): the textual evidence each entity argument came from.
  -- Nullable in the schema because analyst and assessment claims legitimately have
  -- no mention; REQUIRED for extracted/reported claims by the rule below — an
  -- application invariant, not a CHECK, because it depends on assertion_type
  -- semantics the DB does not own.
  subject_mention_id TEXT REFERENCES mention,
  object_mention_id  TEXT REFERENCES mention,
  CHECK (object_mention_id IS NULL OR object_id IS NOT NULL),  -- no anchor without an entity arg

  -- the identity revision current at recorded_at (ADR-029 §2). Projections resolve
  -- arguments through the ACTIVE revision; as-of queries may pin this one instead.
  identity_revision_id BIGINT NOT NULL REFERENCES identity_revision,

  assertion_type TEXT NOT NULL,         -- observed | reported | inferred | assessed  (GOAL.md Rule 3)
  record_id      TEXT NOT NULL REFERENCES source_record,   -- Article I: no orphan claims
  excerpt        TEXT,                  -- verbatim supporting text
  collection_method TEXT,               -- structural | semantic_llm | curated | manual | ...

  -- grading (Article III / ADR-011): original + normalized, source & info separate
  credibility_scheme      TEXT,
  credibility_original    TEXT,
  credibility_normalized  TEXT NOT NULL DEFAULT 'cannot_judge',
  verification_status     TEXT NOT NULL DEFAULT 'unverified',
  analytic_confidence     TEXT,         -- only on assertion_type='assessed'

  -- time (ADR-008)
  event_time_earliest TIMESTAMPTZ,
  event_time_latest   TIMESTAMPTZ,
  valid_from     DATE,
  valid_to       DATE,                  -- NULL = ongoing (matches current semantics)
  recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  retracted_at   TIMESTAMPTZ,
  retraction_reason TEXT,

  handling_code  TEXT NOT NULL DEFAULT 'open',
  case_id        TEXT REFERENCES case_file,
  jurisdiction   TEXT,
  location_text  TEXT,                  -- Phase 5 upgrades to location entity refs
  supersedes     TEXT REFERENCES claim,
  ontology_version TEXT NOT NULL,
  CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
  CHECK (subject_id <> object_id)       -- no self-claims (ports the prototype rule)
);

CREATE TABLE claim_relation (
  from_claim TEXT NOT NULL REFERENCES claim,
  to_claim   TEXT NOT NULL REFERENCES claim,
  relation   TEXT NOT NULL CHECK (relation IN ('corroborates','contradicts')),
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (from_claim, to_claim, relation)
);
```

### 3.1 Argument attribution rules (ADR-029)

The hybrid argument model: a claim keeps its **entity** arguments *and* carries
the **mention** evidence behind them. Mention-only references were rejected —
analyst-authored and assessment claims legitimately have no textual mention.

1. **Anchors required by assertion type.** `assertion_type IN ('observed',
   'reported')` — and every claim produced by an extraction producer — must
   carry an anchor for each entity-valued argument. `inferred` and `assessed`
   claims may be unanchored. Enforced in the actions layer at write time, where
   `assertion_type` is already validated (ADR-013), not by a CHECK.
2. **Revision stamp.** Every claim stamps `identity_revision_id` = the active
   revision at `recorded_at`. This records *what identity meant when the claim
   was made*; it is not a resolution instruction.
3. **Resolution.** Projections and queries resolve `subject_id`/`object_id`
   through the **active** revision via `entity_canonical_map` (specs/05 §5).
   An as-of query may pin an explicit revision instead — that pinning is what
   makes the P4 as-of answer defensible (B-11).
4. **Split behavior.** When a split affects a claim's entity:
   - **Anchored** claims follow their mention. The mention moved to a specific
     entity, so the claim's attribution is decided — no human is asked, and no
     claim row is rewritten.
   - **Unanchored** claims route to **re-adjudication**: a
     `claim_relation`-kind entry in the review inbox naming both candidate
     entities. They are never silently reassigned to either side, and never
     dropped (Article VIII).
5. **No claim row is ever rewritten by an identity decision.** Merges and
   splits change memberships and the canonical map; `claim.subject_id` and
   `claim.object_id` are immutable after write. This is the property the
   reversal tests assert (specs/05 §8).

The backfill for Phase-1 claims is **heuristic and lossy**: existing rows record
only `record_id`, never the mention that produced them, so T17 matches
`mention.norm_key` within the claim's own record. Where the heuristic is
ambiguous — several mentions of the same `norm_key` in one record, or none —
the claim is left **unanchored** rather than guessed, and is therefore governed
by rule 4's re-adjudication path. The migration reports the counts it anchored,
left unanchored, and found ambiguous.

**Vocabulary enforcement (ADR-013).** Ontology-owned vocabularies — `predicate`,
`entity_type`, `source_type`, grading values, `handling_code` — are plain TEXT.
The actions layer validates them at write time against the ontology version in force
and stamps that version into `ontology_version`; the DB never encodes them. CHECK
constraints above exist only for code-owned invariants (object XOR, no self-claims,
time sanity, fixed relation/status values), which don't change when the ontology does.

### Review queue (Article VII)

> **Superseded by ADR-031 (P2 T17c rewrites this section).** The opaque
> `payload` + single `result_claim` FK cannot represent identity decisions,
> claim relations, or later P8 outputs. The typed envelope adds
> `suggestion_kind`, `schema_version`, per-kind payload schemas generated from
> target-action parameters, producer identity/version, idempotency key,
> supersession/expiry, and a typed result reference; acceptance dispatches
> through the declared action. High-volume ER candidates live in
> `er_candidate` (ADR-028); the review inbox is a UI composition.

```sql
CREATE TABLE review_queue (
  suggestion_id  TEXT PRIMARY KEY,
  payload        JSONB NOT NULL,        -- claim draft (validated against ontology on accept)
  producer       TEXT NOT NULL,         -- 'semantic_pass', 'splink', 'structural_pass', ...
  producer_meta  JSONB NOT NULL,        -- model id/version, prompt hash, score breakdown
  status         TEXT NOT NULL DEFAULT 'suggested',  -- suggested | accepted | rejected
  decided_by     TEXT,
  decided_at     TIMESTAMPTZ,
  decision_note  TEXT,
  result_claim   TEXT REFERENCES claim, -- set on acceptance
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 4. Cases, evidence, custody

```sql
CREATE TABLE case_file (
  case_id     TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'open',   -- open | closed | sealed (Phase 7)
  purpose     TEXT NOT NULL,                  -- purpose limitation anchor (GOAL.md §12.4)
  handling_code TEXT NOT NULL DEFAULT 'open',
  opened_by   TEXT NOT NULL,
  opened_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at   TIMESTAMPTZ
);
CREATE TABLE case_member (          -- projected into OpenFGA tuples (specs/03, ADR-014)
  case_id  TEXT REFERENCES case_file,
  user_id  TEXT NOT NULL,
  role     TEXT NOT NULL,           -- investigator | analyst | supervisor | auditor
  PRIMARY KEY (case_id, user_id)
);

-- transactional outbox (ADR-014): FGA tuple changes commit atomically with the rows
-- they mirror; a dispatcher drains rows into FGA with idempotent retries
CREATE TABLE authz_outbox (
  outbox_id    BIGSERIAL PRIMARY KEY,
  op           TEXT NOT NULL CHECK (op IN ('write','delete')),
  fga_tuple    JSONB NOT NULL,      -- {user, relation, object}
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ,         -- set by the dispatcher after FGA acknowledges
  attempts     INT NOT NULL DEFAULT 0,
  last_error   TEXT
);

CREATE TABLE evidence_item (
  evidence_id  TEXT PRIMARY KEY,
  case_id      TEXT REFERENCES case_file,
  record_id    TEXT REFERENCES source_record,  -- when evidence entered via ingestion
  description  TEXT NOT NULL,
  content_hash TEXT,                 -- NULL only for physical items
  storage_uri  TEXT,
  acquired_at  TIMESTAMPTZ,
  acquired_by  TEXT,
  legal_basis  TEXT,                 -- free text Phase 1; authority objects Phase 7
  handling_code TEXT NOT NULL DEFAULT 'restricted',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE derivative (            -- transcript-of, translation-of, extract-of (Article IV)
  derivative_id TEXT PRIMARY KEY,
  parent_evidence TEXT REFERENCES evidence_item,
  parent_record   TEXT REFERENCES source_record,
  CHECK (parent_evidence IS NOT NULL OR parent_record IS NOT NULL),
  kind          TEXT NOT NULL,       -- transcript | translation | ocr_text | extract | enhanced
  tool          TEXT NOT NULL,       -- 'whisper-small-sinhala', 'opendataloader-pdf', ...
  tool_version  TEXT NOT NULL,
  params        JSONB NOT NULL DEFAULT '{}',
  operator      TEXT NOT NULL,
  content_hash  TEXT NOT NULL,
  storage_uri   TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE custody_event (
  evidence_id  TEXT NOT NULL REFERENCES evidence_item,
  seq          INT  NOT NULL,
  from_actor   TEXT,
  to_actor     TEXT NOT NULL,
  occurred_at  TIMESTAMPTZ NOT NULL,
  purpose      TEXT NOT NULL,
  hash_checked BOOLEAN NOT NULL DEFAULT false,
  note         TEXT,
  PRIMARY KEY (evidence_id, seq)
);
```

## 5. Audit (Article X)

```sql
CREATE TABLE audit_log (
  id          BIGSERIAL PRIMARY KEY,
  at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor       TEXT NOT NULL,          -- user id or 'system:<job>'
  session_id  TEXT,
  purpose     TEXT,
  case_id     TEXT,
  action      TEXT NOT NULL,          -- 'record_claim', 'read:claims', 'export', 'authz.deny', ...
  resource_type TEXT,
  resource_id TEXT,
  decision    TEXT NOT NULL,          -- allow | deny
  detail      JSONB NOT NULL DEFAULT '{}',
  prev_hash   TEXT NOT NULL,
  entry_hash  TEXT NOT NULL           -- sha256(prev_hash || canonical_json(all fields above))
);
-- App DB role: INSERT + SELECT only. No UPDATE/DELETE grant exists for anyone but a
-- dedicated maintenance role that ordinary admins do not hold.
```

Chaining is **synchronous**: the audit insert happens inside the action's transaction,
so concurrent audited actions serialize on the chain head. That is deliberate — an
asynchronously-hashed row is an unhashed tamper window. Rationale, capacity math, and
the escape hatch (batching, then per-shard chains + Merkle anchors) are in ADR-015.

## 6. Legacy migration mapping

| Legacy (`pipeline/models.py`) | Target |
|---|---|
| `CriminalNode` | `entity(entity_type=person\|organization)`; `name` → label + `has_name` claim; each alias → `known_as` claim; each affiliation → `affiliated_with` claim (object resolved to org entity when it exists, else literal) |
| `node_id` slug | `mention.norm_key`; one mention + one identity_membership per legacy node (`decided_by='rule:legacy-slug'`) |
| `TemporalEdge.relation` | `claim.predicate` via the verb-remap table in `aegis/migration/legacy.py` (below, ADR-016); migration fails on verbs missing from the table — forcing the table to be complete |
| `layer` | derived — `predicate.category` normally equals the legacy layer (migration asserts); where the ontology deliberately corrects a legacy miscategorization (e.g. `sibling_of`: FIN → `kinship`), the ontology wins and the remap is logged in the migration report |
| `confidence` tag | ConfidenceTag map in `aegis/migration/legacy.py`: `EXTRACTED → confirmed/record_confirmed`, `INFERRED → probably_true/partially_corroborated`, `AMBIGUOUS → doubtful/unverified` — targets validated against the ontology registry at run time (ADR-011, ADR-016) |
| `weight` | not stored — recomputed in projections from normalized grading |
| `start_date`/`end_date` | `valid_from` / `valid_to` |
| `source_file`/`source_excerpt` | `source` + `source_record` (one per SOURCES entry) + `claim.excerpt` |
| `extraction_method` | `collection_method` (`CURATED→curated`, `STRUCTURAL→structural`, `SEMANTIC→semantic_llm`) |
| `SEMANTIC`-produced edges | **not** migrated as recorded claims — re-run passes into `review_queue` (Article VII); only curated + structural edges migrate directly |

Verb-remap table (ADR-016 — legacy narrative verbs normalize into reusable
vocabulary; specifics move onto the claim):

| Legacy verb | Target claim(s) |
|---|---|
| `co_conspirator_in_plot_with` | `conspired_with` |
| `co_masterminded_attacks_with` | `masterminded_attack_with` |
| `suspected_successor_leader_of` | `successor_leader_of`, credibility capped at `possibly_true` |
| `suspected_foreign_is_contact_of` | `foreign_contact_of`, credibility capped at `possibly_true` |
| `sibling_co_attacker_of` | two claims: `sibling_of` + `co_attacker_with` |
| `spousal_co_attacker_of` | two claims: `spouse_of` + `co_attacker_with` |
| `former_ally_turned_rival_of` | two claims: `allied_with` (`valid_to` = edge start) + `rival_of` (`valid_from` = edge start) |
| `avenging_rival_of` | `rival_of` (revenge motive stays in the excerpt) |
| `helped_establish_in_dubai` | `helped_establish_operations_of`, `location_text = 'Dubai'` |
| `ran_narcotics_from_tamil_nadu_with` | `trafficked_narcotics_with`, `location_text = 'Tamil Nadu route'` |
| all other verbs | the same-named ontology predicate |

"Capped at" = the mapped credibility or `possibly_true`, whichever is weaker — a
"suspected" prefix in a verb is grading information, not vocabulary (Article III).

Projection weight function (keeps UI/clustering behavior):
`confirmed→1.0, probably_true→0.7, possibly_true→0.55, doubtful→0.4, improbable→0.2,
cannot_judge→0.4`. Committed as code with tests; tune only with an ADR.
**Legacy-only from P2 (ADR-030):** the v2 projection stores no aggregate weight,
so this function survives solely inside the legacy graph emitter until T22
deletes it. It is a migration-compatibility artifact, not a claim about
confidence.

## 7. Traversal projection v2 (ADR-002, ADR-029, ADR-030)

Rewritten by P2 T17b; implemented by T21. The Phase-1 view (migration `0006`,
still live until T21) fabricates time by collapsing disjoint intervals with
`min`/`max`, erases contradictions with `max(projection_weight(...))`, and
labels distinct records `independent_records`. Together those three produce
precisely the "authoritative rumor engine" GOAL.md forbids. The v2 semantics:

**Identity resolution.** Subject and object resolve through the **active**
identity revision via `entity_canonical_map` before grouping, so a merge
collapses two nodes into one and a split restores them — with zero claim-row
rewrites (ADR-029 §3, specs/05 §5).

**Time — interval sets, never collapsed.** An edge is emitted as
**time-segmented rows**: one row per maximal interval over which the same
supporting claim set holds. Two claims covering 2019 and 2023 produce two
segments, not one 2019–2023 edge. An open interval (`valid_to IS NULL`) stays
open in its own segment.

**Confidence — no authoritative scalar.** No aggregate weight column exists.
The edge carries a **support summary**: the grading references of every
supporting claim (reliability, credibility, verification kept separate —
Article III), a contradiction count and a corroboration count from
`claim_relation`, and the aggregation method + version that produced it. Any
display score is computed in the UI from the summary and is inspectable
(Article III's "display scores are *derived*"). The Phase-1
`projection_weight()` function survives only inside the legacy emitter until
T22 deletes it.

**Counting — `record_count`, never "independent".** Distinct supporting records
are counted and named `record_count`. Independence is a claim about source
derivation that Aegis cannot yet substantiate; until a source-derivation model
exists, **no independence is rendered anywhere** (ADR-030 §3).

**Stamps.** Every build records the identity revision, ontology version, and
builder version it ran at, so any rendered edge is fully attributable and a
stale projection is detectable rather than silently wrong.

```sql
-- illustrative shape; T21 owns the implementation. A TABLE, not a matview:
-- segmentation is not expressible as a single GROUP BY.
CREATE TABLE edge_projection (
  edge_id        TEXT PRIMARY KEY,
  subject_id     TEXT NOT NULL REFERENCES entity,   -- canonical at build revision
  object_id      TEXT NOT NULL REFERENCES entity,
  predicate      TEXT NOT NULL,
  segment_from   DATE,                              -- one row per maximal interval
  segment_to     DATE,                              -- NULL = open
  claim_ids      TEXT[] NOT NULL,                   -- the claims holding over this segment
  record_count   INTEGER NOT NULL,                  -- DISTINCT records — never "independent"
  support        JSONB NOT NULL,                    -- per-claim grading refs, contradiction +
                                                    -- corroboration counts, method + version
  handling_rank  INTEGER NOT NULL,                  -- max over supporting claims (row filter)
  built_at_revision_id BIGINT NOT NULL REFERENCES identity_revision,
  ontology_version TEXT NOT NULL,
  builder_version  TEXT NOT NULL
);
```

k-hop expansion = recursive CTE over this table with hop limit, handling-rank filter,
and time predicates pushed into the segment bounds. The graph-JSON emitter and Cypher
export read it. Losing the whole table loses nothing (Article XIII).

### 7.1 Blocking tests (ADR-029 §5, ADR-030)

| Case | Assertion |
|---|---|
| Merge collapse | Merging B into A collapses their nodes and edges; **no claim row is modified** |
| Split restore | Splitting B back out restores the pre-merge edge set exactly, again with zero claim rewrites |
| Disjoint intervals | Claims covering 2019 and 2023 yield **two segments**, not one continuous edge |
| Contradiction survives | An edge supported by contradicting claims exposes both in its support summary; no aggregate hides either |
| Attribution | Every rendered edge resolves to ≥ 1 source record (Article I) |
| Stamp freshness | An edge built at an older revision is detectable as stale via `built_at_revision_id` |
| Unanchored on split | An ambiguous unanchored claim appears in the review inbox rather than being reassigned (§3.1 rule 4) |

## 8. Indexing (Phase 1 minimum)

- `claim(subject_id)`, `claim(object_id)`, `claim(predicate)`, `claim(record_id)`,
  partial index `WHERE retracted_at IS NULL`.
- `mention(norm_key)`, `entity(label gin_trgm_ops)` for lookup.
- P2 additions: `claim(subject_mention_id)`, `claim(object_mention_id)` (split
  re-adjudication looks claims up by mention); `identity_membership(entity_id)
  WHERE closed_revision_id IS NULL` (canonical-map rebuild and scoped
  concurrency checks); `er_candidate(disposition) WHERE disposition = 'open'`
  (inbox scan); `edge_projection(subject_id, predicate)` and
  `(object_id, predicate)` for k-hop expansion.
- `source_record(ingest_key)` unique (exists), `(content_hash)`.
- `audit_log(at)`, `audit_log(actor, at)`.
- `authz_outbox(processed_at) WHERE processed_at IS NULL` (dispatcher scan, ADR-014).
