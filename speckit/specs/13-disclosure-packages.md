# Spec 13 — Disclosure & export packages

Status: **final** (authored 2026-08-24 by T78, the blocking re-validation that
opens Phase 7) · Charter: `../phases/phase-07-sharing-governance.md` ·
Constitutional basis: Articles IV, VI, X · GOAL.md §23–24, §27, Rule 4 ·
Findings closed here: H-28, M-20 · ADR-061, ADR-065

Its governing sentence:

> **A package is a statement about what left, made at the moment it left, and
> verifiable by someone who does not trust us.**

Everything below follows from that. The container is a standard one so a
recipient can check it with tools we did not write. The manifest records the
grant the export was cut against, not the grant the recipient holds today. The
redaction log says what was withheld, because a package that silently omits is
indistinguishable from a package that never had it. And the claim that packages
are the *only* way data leaves is not made, because it is not true (§9).

---

## 0. What re-validation changed

`tasks/phase-07.md` was pre-authored 2026-07-17, before Phases 3–6 existed, and
amended 2026-07-18 by ADR-033 without the task text being rewritten. T78 walked
both against the as-built system. The divergences below cover the whole phase —
the ones about governance mechanics are implemented in `03-security.md`, the ones
about packages here — because splitting one re-validation across two tables is
how the second table goes stale.

| # | The plan said | As built / as required | Disposition |
|---|---|---|---|
| G1 | T79: "field-level sensitivity on reads — the debt carried since the Phase 1 exit review"; AC: a restricted field is redacted **while the row stays visible** | It shipped in **P2 T24a**. `aegis/authz/filters.py` resolves `property_sensitivity` → `forbidden_field_predicates` and composes them into `claim_filters`, and the mode it implements is **omit**: the claim is absent as a row. The debt is closed, and the AC describes a mode the amended charter assigns to *specific resource classes only* | Task re-scoped to the **response-mode policy** (H-25). The Phase 1 debt is recorded closed rather than re-opened. No ADR — ADR-033 already decided this; a stale sentence is being fixed |
| G2 | H-25: "marked redaction … including nested fields" | Aegis has no property column to null out: **a property is a claim**. "Redact the field, keep the row" has to be defined against a grouped object view, where the unit is a *predicate group*, not a column | **ADR-061** — a redaction marker names the predicate and carries no count, no grading, and no id. spec 03 §6 |
| G3 | The three modes do not exist yet | One of them does. `aegis/sets/sharing.py:redact_definition` already returns `{property, op, value: null, withheld: true}` for an object-set filter above the reader's clearance (T70) — marked redaction, shipped for one resource class with no policy behind it | The policy **adopts that shape** rather than inventing a second one, and object-set definitions enter the table as `marked` because that is what they already do. No ADR |
| G4 | T80: "the existing unused FGA `compartment` type goes live" | FGA is an **asynchronous projection** of Postgres (ADR-014), and M-15 showed a lagging projection can still authorize after canonical state says no. Rows must not be gated on it | **ADR-062** — compartment membership is canonical Postgres and is enforced inside `claim_filters`; the FGA type is projected for route-level checks and never decides a row. spec 03 §7 |
| G5 | T82: implement `seal_record`, declared in the ontology since 0.3.0 with `resource_id: {type: identifier}` | The declaration does not say what kind of resource, and the two candidates behave differently: sealing a **source record** must reach every claim recorded from it, while sealing a **claim** must not reach its siblings | **ADR-063** — a seal attaches to a source record *or* a claim, is a state and never a deletion, and projections exclude it at source. spec 03 §8 |
| G6 | Charter: "expungement as a governed, audited operation **reversible only by policy**" | H-26 warns against promising reversible expungement. Reversible destruction is not destruction — if the bytes are still there it is suppression under another name, and we already have suppression | **ADR-064** — sealing is reversible suppression; expungement destroys content, leaves an audited tombstone, and is irreversible. spec 03 §8.3 |
| G7 | T85: "the ontology gains the object via the P3 proposal workflow (minor bump)" | An ontology object type would make a legal authority an **entity**, whose attributes are claims — gradeable, retractable, contradictable, and subject to the very filters it governs. The seams that exist are Postgres columns on `source_record` (`collection_policy_ref`, `authority_ref`, `authority_valid_from/to`, `retention_class`), placed there by P2 T24a with a check constraint on the window | **ADR-065** — legal authority is a **governance record**, not an ontology object. The ontology gains the **purpose vocabulary** instead, which is a real minor bump and is what policy actually evaluates. spec 03 §13, §7 here |
| G8 | M-14: "define a general collection/workspace scope distinct from case" | Half is already answered: ADR-044 settled that a case reference grants nothing and `claim.case_id` is the immutable recording scope. The other half — a scope narrower than "every role sees case-less rows at their clearance" — is what a **compartment is** | Declined as a separate concept; compartments answer it. Recorded rather than silently dropped. No ADR |
| G9 | T83 AC: "a route lint proves no other bulk-output endpoint exists" | It cannot (M-20). A lint sees FastAPI routes; the CLI, the database, the object store, the logs and the backups are not routes | AC corrected: the **inventory** is the artifact and the lint keeps a narrower job (§9, spec 03 §12). No ADR — the charter already absorbed M-20 |
| G10 | T86: break-glass "expires on schedule"; M-21: "tuple cleanup is maintenance only" | Even maintenance-only cleanup leaves a window in which a stale tuple authorizes. The window closes completely only if no tuple is ever written | **ADR-066** — break-glass writes **no FGA tuple at all**; elevation is read from canonical state on every request. The exit test seeds a tuple by hand, to prove FGA is not the decider. spec 03 §10 |
| G11 | The task sketch has five milestones and no tooling | The Phase 6 exit review carried `ruff` into P7 with the target "before the next feature phase". T79 is the next feature task | **T78a** inserted before T79. A task addition, not a scope change |

Three things the plan assumed and reality confirms, recorded so nobody
re-checks them:

- The **governance seams are already there**. `source_record` carries
  `collection_policy_ref`, `retention_class`, `authority_ref`,
  `authority_valid_from` and `authority_valid_to`, with
  `ck_source_record_authority_window` already refusing an inverted window.
  B-08 enforcement is turning inert columns on, not a migration of a populated
  corpus — which is exactly why P2 put them there.
- The **audit console is this phase's work**, not an extra. ADR-045 moved it out
  of P4 and named P7; T87 owns it.
- `watchlist_alert.authority_ref` exists and is nullable, for the same reason and
  with the same owner (T85).

**Carryovers this phase inherits and where they land.** The P6 exit review
assigned four items to "the P7 owner". `ruff` is **T78a**. `authority_ref`
enforcement is **T85**. **Watchlist sharing** and the `owner_clearance` behaviour
that goes with it are deferred to the T89 exit review rather than scheduled now:
a watchlist runs at its owner's clearance, so a sharing grant is a
clearance-lending decision, and the compartment and grant vocabulary that would
let it be stated honestly does not exist until T80. Deciding it before then would
be guessing.

---

## 1. Why BagIt, and what BagIt does not give us (H-28)

The pre-amendment plan invented a manifest format. H-28 rejected that, and the
charter adopted **BagIt (RFC 8493)** before build rather than after. The reason
is narrow and worth stating so nobody re-opens it: a custom archive puts the
burden of writing a verifier on the recipient, and a recipient who cannot verify
cheaply does not verify.

BagIt gives us exactly three things:

| BagIt provides | What it means here |
|---|---|
| `data/` payload + `manifest-sha256.txt` | Every payload file's digest, checkable with one command |
| `tagmanifest-sha256.txt` | The metadata files are fixity-checked too, so the manifest cannot be edited without detection |
| `bag-info.txt` + `bagit.txt` | A place for declared metadata that standard tooling already reads |

**BagIt provides integrity, not authenticity.** A manifest proves the payload
was not corrupted; it proves nothing about who made it, because an attacker who
edits the payload can recompute every digest. RFC 8493 says this itself. So the
package carries a **detached signature over `tagmanifest-sha256.txt`** (§4), and
the signature — not the manifest — is what a recipient trusts.

## 2. Layout

```
aegis-pkg-<package_id>/
  bagit.txt                       # BagIt 1.0, UTF-8
  bag-info.txt                    # standard tags + Aegis profile tags (§3)
  manifest-sha256.txt             # digests of everything under data/
  tagmanifest-sha256.txt          # digests of bag-info.txt, manifest, aegis/*
  aegis/
    package.json                  # the Aegis manifest (§3)
    redaction-log.json            # what was withheld and why (§5)
    grant.json                    # the recipient grant, snapshotted (§6)
    sources.json                  # legal basis per contributing source (§7)
  data/
    claims.jsonl                  # one claim per line, in the export projection
    entities.jsonl
    evidence/<sha256>             # payload bytes, named by content hash
```

Two layout rules, both consequences of the governing sentence:

- **Everything Aegis asserts about the package lives under `aegis/` and is
  covered by the tag manifest**, never under `data/`. A recipient checking
  fixity of the payload and a recipient checking what we claimed about it are
  doing different jobs, and the second must not be satisfiable by editing a
  payload file.
- **Evidence files are named by content hash**, so a package's bytes are
  addressable the same way the vault addresses them (spec 04). A filename
  carrying a case number or a person's name would leak through a directory
  listing, which is a read surface (§9).

### 2.1 Serialization is canonical, or the signature is theatre

Every `aegis/*.json` file is written with **sorted keys, `\n` line endings, UTF-8
without BOM, no trailing whitespace, and RFC 3339 UTC timestamps with a `Z`
suffix**. `.jsonl` payload files are sorted by primary key.

This is not tidiness. A signature over a serialization that varies by platform or
dict ordering cannot be re-derived by anyone checking our work, and "re-export
and compare" is the only cheap way to audit an export after the fact. A contract
test pins the serializer: a package built twice from the same inputs is
**byte-identical** apart from `package_id` and `built_at`, and those two are
supplied rather than generated when the test builds it.

## 3. The Aegis manifest (`aegis/package.json`)

| Field | Meaning |
|---|---|
| `package_id` | ULID; also the bag directory name |
| `built_at` | When the package was cut (UTC) |
| `built_by` | Actor sub + display name |
| `purpose` | From the ontology purpose vocabulary (ADR-065), never free text |
| `legal_basis` | The disclosure's own authority record id (§7) |
| `input_kind` | `object_set` or `case` |
| `input_ref` | Set id + version, or case id |
| `evaluation_digest` | For a set input, the P6 evaluation digest (ADR-055) |
| `authorization_digest` | The filter state the export was cut under (ADR-055) |
| `identity_revision_id` | Which identity revision resolved the entities |
| `ontology_version` | Composition version (ADR-037) |
| `recipient` | Recipient record id + name |
| `grant_id` | The grant this was cut against (§6) |
| `handling_ceiling` | The highest handling code actually present in the payload |
| `expires_at` | When the recipient's authority to hold this lapses (§8) |
| `counts` | `{claims, entities, evidence_files}` |
| `redaction_log_sha256` | Digest of `aegis/redaction-log.json` |
| `signing_key_id` | Which key signed the tag manifest (§4) |

`handling_ceiling` is the **observed maximum in the payload**, not the grant's
ceiling. A package cut for a `restricted` recipient that happens to contain only
`open` rows says `open`, and a reader who over-classifies it is protecting
something that needs no protection. The grant's ceiling lives in `grant.json`,
where it belongs, and §6's rule is what makes the two agree.

## 4. Signing (H-28)

- Algorithm: **Ed25519**, detached, over the bytes of `tagmanifest-sha256.txt`.
- The signature is delivered as `aegis-pkg-<id>.sig` **beside** the bag, never
  inside it — a signature inside its own tag manifest is a circular reference.
- The public key is published with its key id and validity window; the manifest
  records `signing_key_id`.
- **Key custody**: the signing key never lives in the database, in `.env`, or in
  any bucket the API can write. In the dev profile it is a file the operator
  supplies; the pilot profile requires it off the application host. Rotation
  publishes the new key with an overlap window and **never re-signs old
  packages** — a package is a statement made at a moment, and re-signing it later
  would be a different statement.
- **Verification is possible without Aegis**: `sha256sum -c manifest-sha256.txt`
  plus any Ed25519 verifier are sufficient. `aegis disclosure verify` is a
  convenience, not the trust root. This is the property that makes the format
  worth its cost, so it is tested on an extracted tree using only the digests and
  the public key, with no Aegis code in the verification path.

## 5. The redaction log (`aegis/redaction-log.json`)

Records **what was withheld and why**, at the granularity the recipient is
entitled to know about, and no finer.

```json
{
  "package_id": "01J...",
  "modes": {"claim": "counts", "evidence": "counts"},
  "entries": [
    {"reason": "handling_above_grant", "resource": "claim", "count": 14,
     "detail": {"handling_code": "sensitive"}},
    {"reason": "compartment", "resource": "claim", "count": 3, "detail": {}},
    {"reason": "sealed", "resource": "claim", "count": 1, "detail": {}},
    {"reason": "field_sensitivity", "resource": "claim", "count": 7,
     "detail": {"predicate": "has_nic"}}
  ]
}
```

Four rules, each of which is a way this goes wrong:

1. **A reason, a resource, and a count — never a value, an id, or an excerpt.** A
   redaction log that named the withheld claims would be the leak it exists to
   document.
2. **`compartment` entries never name the compartment.** Knowing "three rows were
   withheld under a compartment" is the disclosure a recipient needs to assess
   completeness; knowing *which* compartment is the compartment's existence,
   which is exactly what spec 03 §9's outsider rule forbids.
3. **`field_sensitivity` entries name the predicate**, because the recipient is
   authorized to know the schema of what they received — this is the marked mode
   of ADR-061 applied to a package, and it is used only when the grant's response
   mode permits it (§10).
4. **A zero-redaction export still ships a log**, with `entries: []`. An absent
   log and a nothing-withheld log must not look the same, or "we forgot" reads as
   "nothing was withheld".

## 6. Recipient grants (`aegis/grant.json`)

A **recipient** is a canonical record (organization or named person, contact,
jurisdiction). A **grant** is a versioned authorization to receive:

| Field | Meaning |
|---|---|
| `grant_id`, `recipient_id`, `version` | Identity |
| `handling_ceiling` | The highest handling code this recipient may receive |
| `compartments` | Compartments explicitly included (default: none) |
| `purposes` | Permitted purposes from the ontology vocabulary |
| `valid_from`, `valid_to` | The grant's own window |
| `response_mode` | `omit`, `marked`, or `counts` for this recipient (§10) |
| `granted_by`, `granted_at`, `reason` | Who decided, when, why |

**The build is capped by the grant, not filtered after it.** The exporter
composes the grant's ceiling and compartment set into the same `claim_filters`
the API uses (spec 03 §4), so a row above the ceiling is absent from the scan
that assembles the package — B-17's rule, applied to export. A post-hoc "remove
rows above X" pass over an assembled payload is forbidden, because it puts
protected rows in memory, in logs, and in whatever temporary file the assembly
used.

**A grant is snapshotted into the package, never referenced.** A recipient
reading a package a year later must be able to see what they were authorized to
hold at the time, and a live reference would show them today's answer to
yesterday's question.

**Building against an expired or not-yet-valid grant fails closed**, and the
attempt is audited (§8).

## 7. Legal basis (`aegis/sources.json`)

For every source contributing a claim to the payload: `source_id`, `name`,
`source_type`, `collection_policy_ref`, `authority_ref`, and the authority
window. This is Rule 4 scaled to OSINT — the authority is usually a collection
policy rather than a warrant, and the mechanism is the real one (ADR-065).

The disclosure itself also carries a `legal_basis` in `package.json`, which is a
**different** record: the authority to *release*, not the authority to *hold*. A
package that cannot name both fails to build.

**A source whose authority window had already expired at recording time still
appears here**, marked `authority_expired_at_collection: true`. Hiding it would
make the package look cleaner than the collection was; ADR-065 fails such reads
closed going forward, but what was already recorded is recorded, and Article I
says we report what happened.

## 8. Expiry, acknowledgement, revocation

- **Expiry** (`expires_at`) is the recipient's authority to hold the package. It
  is metadata and a policy statement, not enforcement: once bytes leave, they are
  gone. The spec says this plainly rather than implying DRM.
- **Acknowledgement**: a `disclosure_receipt` row records that the recipient
  confirmed delivery — receipt id, actor, timestamp, package digest. An
  unacknowledged package after a configured interval surfaces in the auditor's
  oversight queries (spec 03 §11).
- **Revocation** marks the package revoked with a reason, notifies the recorded
  contact, and appears in audit. It **does not** recall data, and the API says so
  in the response. A revocation flow that implied recall would be a lie told to
  an analyst who then discloses more freely.

## 9. The egress inventory is the artifact, not the route lint (M-20)

T83's pre-authored acceptance criterion said a route lint proves no other bulk
output path exists. It cannot. A lint sees FastAPI routes; it does not see the
CLI, the database, the object store, the logs, or the backups.

So the claim this phase makes is the one that is true: **packages are the
sanctioned disclosure workflow**, and every other path data can take is
enumerated, owned, and constrained. The enumeration is the **read-surface
inventory** in spec 03 §12 — one list covering API reads and non-API egress
together, because two lists drift and the second one is always the stale one.

The lint keeps a narrower and still useful job: a new API route that returns
records and is not registered in the inventory **fails CI** (spec 03 §12.1).

## 10. Response modes in a package (H-25)

A package's default mode is **counts** — the redaction log's whole shape. This is
the one place counts are correct rather than dangerous: the recipient is a
disclosure counterparty entitled to assess completeness, which is exactly H-25's
"counts only for disclosure officers with an explicit privilege". The privilege
here is the grant.

`marked` (predicate named, value withheld) is available per grant and is the
right mode for a counterparty who already holds the schema — a prosecutor who
knows the record format and must be able to tell a withheld field from an empty
one. `omit` is available for a grant that should not learn the shape of what it
did not get.

The mode is a property of the **grant**, decided by a person, recorded in
`grant.json`, and tested per mode. It is never inferred from the recipient's
clearance, because a recipient outside the organization has no clearance.

## 11. Actions and routes

| Action | Route | Role | Audited |
|---|---|---|---|
| `create_recipient` | `POST /v1/recipients` | supervisor | yes |
| `grant_recipient` | `POST /v1/recipients/{id}/grants` | supervisor | yes |
| `preview_package` | `POST /v1/disclosure/preview` | analyst + purpose | yes |
| `build_package` | `POST /v1/disclosure/packages` | supervisor + purpose | yes |
| `export_package` | `POST /v1/disclosure/packages/{id}/export` | supervisor + purpose | yes |
| `acknowledge_package` | `POST /v1/disclosure/packages/{id}/receipt` | supervisor | yes |
| `revoke_package` | `POST /v1/disclosure/packages/{id}/revoke` | supervisor | yes |

Actions are declared in the platform ontology module and enforced at the write by
the ADR-040 gate, like every other action. Build and export are separate because
they are separate decisions: building assembles and shows a preview; exporting
hands over bytes.

**The preview shows categories and counts, never values** (GOAL.md §24). This is
tested as a leakage assertion over the whole preview payload rather than as a
review habit: no withheld value appears anywhere in the serialized preview,
checked by searching the payload for the seeded restricted values.

## 12. What this spec does not cover

Federation, originator control across organizations, cross-border policy packs,
and inter-agency exchange protocols are P9 federation-trigger territory. The
package **format** lands here; the **protocol** does not.

Encryption for a specific recipient (age or PGP to a recipient key) is specified
as a grant field and a build option and is exercised in tests, but recipient key
management is a pilot-gate operational concern, not a P7 feature.
