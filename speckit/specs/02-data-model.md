# Spec 02 — Data Model (Claim Store)

Status: draft for Phase 1 · Constitutional basis: Articles I, III, IV, V, VIII, X, XIII

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

## 2. Entities and identity

```sql
CREATE TABLE entity (
  entity_id    TEXT PRIMARY KEY,
  entity_type  TEXT NOT NULL,          -- ontology object type
  label        TEXT NOT NULL,          -- display only; rebuilt from name claims
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- a name-as-written inside one source record (Phase 2 fills these; Phase 1 creates
-- one mention per legacy node)
CREATE TABLE mention (
  mention_id   TEXT PRIMARY KEY,
  record_id    TEXT NOT NULL REFERENCES source_record,
  raw_text     TEXT NOT NULL,
  norm_key     TEXT NOT NULL,          -- slugify() lives on here — a *mention key*, not identity
  context      TEXT
);

-- versioned, reversible identity (Article V): current membership is the row with
-- valid_to IS NULL; history is never deleted
CREATE TABLE identity_membership (
  membership_id TEXT PRIMARY KEY,
  mention_id    TEXT NOT NULL REFERENCES mention,
  entity_id     TEXT NOT NULL REFERENCES entity,
  decided_by    TEXT NOT NULL,          -- user id or 'rule:<name>' for deterministic rules
  decision_note TEXT,                   -- evidence for the decision (required for manual)
  valid_from    TIMESTAMPTZ NOT NULL DEFAULT now(),
  valid_to      TIMESTAMPTZ             -- set when superseded by split/merge
);
```

Merge = close memberships pointing at entity B, open new ones at entity A (B is kept,
flagged `merged_into` via a claim). Split = the inverse. Both are adjudication actions.

## 3. Claims

```sql
CREATE TABLE claim (
  claim_id     TEXT PRIMARY KEY,
  subject_id   TEXT NOT NULL REFERENCES entity,
  predicate    TEXT NOT NULL,           -- ontology predicate — app-validated (ADR-013), never a DB CHECK
  object_id    TEXT REFERENCES entity,  -- exactly one of object_id / object_value
  object_value JSONB,
  CHECK ((object_id IS NULL) <> (object_value IS NULL)),

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
  location_text  TEXT,                  -- Phase 4 upgrades to location entity refs
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

**Vocabulary enforcement (ADR-013).** Ontology-owned vocabularies — `predicate`,
`entity_type`, `source_type`, grading values, `handling_code` — are plain TEXT.
The actions layer validates them at write time against the ontology version in force
and stamps that version into `ontology_version`; the DB never encodes them. CHECK
constraints above exist only for code-owned invariants (object XOR, no self-claims,
time sanity, fixed relation/status values), which don't change when the ontology does.

### Review queue (Article VII)

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
  status      TEXT NOT NULL DEFAULT 'open',   -- open | closed | sealed (Phase 6)
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
  legal_basis  TEXT,                 -- free text Phase 1; authority objects Phase 6
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

## 7. Traversal projection (ADR-002)

```sql
CREATE MATERIALIZED VIEW edge_projection AS
SELECT subject_id, object_id, predicate,
       min(valid_from)                          AS valid_from,
       CASE WHEN bool_or(valid_to IS NULL) THEN NULL ELSE max(valid_to) END AS valid_to,
       count(*)                                 AS claim_count,
       count(DISTINCT record_id)                AS independent_records,
       max(projection_weight(credibility_normalized)) AS weight,
       array_agg(claim_id)                      AS claim_ids,
       max(handling_code_rank(handling_code))   AS handling_rank
FROM claim
WHERE object_id IS NOT NULL
  AND retracted_at IS NULL
GROUP BY subject_id, object_id, predicate;
```

k-hop expansion = recursive CTE over this view with hop limit, handling-rank filter,
and time predicates pushed in. The graph-JSON emitter and Cypher export read this view.

## 8. Indexing (Phase 1 minimum)

- `claim(subject_id)`, `claim(object_id)`, `claim(predicate)`, `claim(record_id)`,
  partial index `WHERE retracted_at IS NULL`.
- `mention(norm_key)`, `entity(label gin_trgm_ops)` for lookup.
- `source_record(ingest_key)` unique (exists), `(content_hash)`.
- `audit_log(at)`, `audit_log(actor, at)`.
- `authz_outbox(processed_at) WHERE processed_at IS NULL` (dispatcher scan, ADR-014).
