# Aegis Intelligence Platform

## An ontology-driven intelligence platform — one governed core, many analytical domains

Aegis is a production-grade, sovereign intelligence platform in which a single
**ontology** — the declared model of objects, properties, links, events,
actions, and governance rules — powers every analytical domain built on top of
it. **Criminal-network analysis is the first application domain, not the
platform.** The same core will carry financial-crime, border, and other
domains as ontology modules, the way Palantir's platforms carry many
workflows on one ontology — but open-stack, auditable, and designed for our
country's legal, linguistic (Sinhala / Tamil / English), and institutional
needs.

The correct design is **not** a giant graph database containing “criminals and their connections.”

That would create an authoritative-looking rumor engine.

The platform must instead model:

```text
What was observed
Who reported it
How it was acquired
What legal authority allowed its collection
When it was believed to be valid
How reliable the source is
What contradicts it
What an analyst inferred
What was later verified
What may legally be shared
```

Its core principle should be:

> **Entities are not facts. Relationships are not facts. Intelligence consists of claims supported, contradicted, or contextualized by evidence and sources.**

The platform is named **Aegis**.

---

# 1. What real intelligence systems teach us

Publicly documented police and intelligence practices reveal several recurring patterns.

## 1.1 Intelligence is a process, not a database

UNODC describes criminal intelligence through a cycle involving direction or tasking, collection, evaluation, collation, analysis, dissemination, and subsequent review. Information only becomes intelligence after evaluation and analysis. ([UNODC][1])

Aegis should therefore support this lifecycle:

```text
Strategic priorities
        ↓
Collection requirements
        ↓
Information acquisition
        ↓
Source and information evaluation
        ↓
Collation and entity resolution
        ↓
Analysis and hypothesis testing
        ↓
Intelligence products
        ↓
Operational or judicial use
        ↓
Outcome review and new requirements
```

A dashboard showing connected nodes covers only a small part of this process.

## 1.2 Source reliability and information credibility are separate

Law-enforcement grading systems distinguish the reliability of the source from the credibility of the information. The historical UK 5×5×5 system did this, while current College of Policing guidance uses a configurable 3×5×2 reporting model. The lesson is not to hard-code one national scheme: preserve the original grading system and map it to an internal normalized representation. ([College of Policing Library][2])

For example:

```text
Source:
Previously reliable confidential informant

Information:
Claims a shipment will arrive tomorrow

Possible evaluation:
Source reliability: high
Information credibility: uncorroborated
Verification status: pending
Analytic confidence: moderate
```

Aegis must never collapse this into a simplistic `confidence = 82%` without showing the components.

## 1.3 Multi-agency systems exchange information; they do not necessarily centralize everything

INTERPOL’s I-24/7 connects authorized law-enforcement users across member countries to exchange information and access databases. Europol’s SIENA similarly provides controlled information exchange between Europol and its partners. These are secure cooperation mechanisms, not evidence that every agency places all of its data into one unrestricted global database. ([Interpol][3])

The production architecture should therefore use:

* Sovereign or agency-controlled data cells.
* Federated search.
* Explicit disclosure packages.
* Originator-controlled sharing.
* Local data-residency policies.
* Shared data only where legally authorized.

## 1.4 Interoperability requires common meaning

NIEM provides agreed terms, definitions, formats, and relationships for exchanging justice and public-safety information independently of how participating systems store their data. Its core includes concepts such as persons, activities, documents, locations, and items. ([reference.niem.gov][4])

Aegis should adopt the same philosophy:

> Maintain an internal canonical ontology, but exchange versioned packages through open, documented schemas.

## 1.5 Evidence and intelligence are different

Evidence must preserve integrity, handlers, collection and transfer events, purpose, and chain of custody. NIST defines chain of custody as tracking evidence through collection, safeguarding, analysis, and transfer, including who handled it, when, and why. NIST also recommends cryptographic hashes, strong access controls, logging, backups, and documented transfers for digital evidence. ([NIST Computer Security Resource Center][5])

Intelligence may include:

* Unverified reports.
* Anonymous tips.
* Analyst assessments.
* Conflicting claims.
* Leads that are not admissible evidence.

The system must not silently transform intelligence into evidence.

## 1.6 Criminal networks are incomplete and deceptive

Social-network analysis is useful for understanding organized crime, but research warns that criminal-justice records are incomplete, biased toward detected activity, and shaped by investigative practices. Network centrality also does not necessarily identify leadership: studies of mafia structures show that important leaders may deliberately avoid central positions. ([ScienceDirect][6])

Therefore:

> “Most connected person” must never be presented as “leader” without separate evidence.

---

# 2. Mission and vision

## 2.1 Mission

Build a governed, ontology-driven intelligence platform: one core that turns
raw sources into graded, sourced, time-bounded **claims** about a shared model
of the world, and lets accountable humans — never algorithms — decide what
becomes accepted knowledge. Every capability (ingestion, identity resolution,
analysis, visualization, sharing) is generated from or governed by the
ontology, so the platform serves any lawful analytical domain without being
rebuilt for each one.

## 2.2 Long-term vision

A national-scale, sovereign platform — comparable in concept to Palantir's
ontology-centred systems, but open-stack and independently auditable — where:

* the **ontology** is the single source of domain truth (semantic + kinetic +
  governance layers, §7.8);
* **domains are modules**: each analytical domain is an ontology module plus
  generated screens, not a bespoke system;
* **governance is structural**: grading, handling, authorization, audit, and
  review-queue discipline are properties of the core, inherited by every
  domain for free;
* multiple institutions cooperate through **federated, originator-controlled
  exchange** (§33), never one unrestricted database.

## 2.3 One platform, many domains

The domain-neutral core (claims, identity, evidence, cases, actions,
projections, search, analytics, governance) carries application domains
declared in the ontology:

* **Criminal-network analysis** — the first domain, in active development on a
  Sri Lankan OSINT corpus: organized crime, gangs, drug and human-trafficking
  networks.
* Financial crime and money laundering.
* Border and customs intelligence.
* Counterterrorism investigations subject to applicable law.
* Multi-agency task forces, strategic threat assessments, judicial and
  disclosure workflows — cross-domain capabilities of the same core.

Adding a domain means adding object types, predicates, event types, actions,
and functions to the ontology (Article XIV) — plus migrations — and letting
codegen and the generic surfaces (object views, search, analytics) do the
rest.

The pre-Aegis prototype (static pipeline + Cytoscape explorer) is treated as
scaffolding: it seeded the corpus and proved the projection layer, and it is
**replaced, never extended** (ADR-023). No new capability is designed around
legacy shapes.

Aegis is **not**:

* An autonomous accusation system.
* An automated probable-cause generator.
* A universal “criminal risk” scoring platform.
* A system that treats association as guilt.
* A tool that automatically promotes AI predictions into graph facts.
* A replacement for investigators, prosecutors, courts, or independent oversight.

---

# 3. Foundational design rules

## Rule 1: Never model a person as inherently criminal

Do not create a `Criminal` entity type.

Use:

```text
Person
 ├─ case-scoped role: suspect
 ├─ case-scoped role: witness
 ├─ case-scoped role: victim
 ├─ case-scoped role: informant
 ├─ legal status: charged
 ├─ judicial outcome: convicted
 ├─ judicial outcome: acquitted
 └─ intelligence designation: person of interest
```

Every role must include:

* The related case or authority.
* Effective dates.
* Source.
* Jurisdiction.
* Current legal status.
* Whether the status is alleged, assessed, charged, adjudicated, dismissed, sealed, or expunged.

## Rule 2: Properties must be claims

Do not directly say:

```text
Person X owns Vehicle Y
```

Store:

```text
Claim:
  subject: Person X
  predicate: OWNS
  object: Vehicle Y
  source: Vehicle Registry Record 8271
  valid_from: 2024-01-12
  valid_to: 2025-04-08
  acquired_at: 2025-04-09
  verification: registry-confirmed
  legal_basis: authorized registry access
```

A second source may contradict it without overwriting the first.

## Rule 3: Separate observation, assertion, and assessment

```text
Observation:
Camera recorded a vehicle entering a location.

Assertion:
An informant says Person X was driving the vehicle.

Assessment:
Analyst assesses Person X was probably present.

Evidence:
Authenticated video accepted into the case evidence collection.
```

These are different objects.

## Rule 4: Legal authority is first-class data

Every sensitive collection or query should be traceable to an authority such as:

* Statutory mandate.
* Search warrant.
* Production order.
* Court order.
* Consent.
* Border/customs authority.
* Emergency authority.
* Intelligence authorization.
* Public-source collection policy.

The authority carries:

```text
scope
purpose
jurisdiction
permitted data categories
subjects or selectors
start and expiry times
minimization rules
sharing restrictions
retention rules
approving authority
```

## Rule 5: Preserve uncertainty and disagreement

Aegis must allow:

* Two possible dates of birth.
* Multiple spelling variants.
* Conflicting ownership records.
* Disputed identities.
* Retracted reports.
* Alternative hypotheses.
* Unknown or partially known relationships.

Conflict resolution should produce an **assessment**, not delete inconvenient source records.

## Rule 6: No unrestricted global graph

The platform should present users with an **authorized knowledge projection** based on:

* Agency.
* Case assignment.
* Clearance.
* Compartment.
* Purpose.
* Legal authority.
* Jurisdiction.
* Originator restrictions.
* Data residency.
* Current device and session risk.

---

# 4. High-level architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                       User Experiences                       │
│ Search │ Case Workspace │ Graph │ Map │ Timeline │ Evidence │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│             API Gateway and Experience Services             │
│ REST │ Query API │ Graph API │ OGC API │ Export │ WebSocket │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
┌──────────────▼─────────────┐  ┌────────────▼───────────────┐
│ Operational Domain Plane   │  │ Intelligence Analysis Plane │
│ Cases                       │  │ Entity resolution           │
│ Evidence                    │  │ Graph analytics             │
│ Legal authority             │  │ Geospatial analysis         │
│ Tasks and approvals         │  │ Pattern detection           │
│ Reports and dissemination   │  │ ML and AI services          │
└──────────────┬─────────────┘  └────────────┬───────────────┘
               │                              │
┌──────────────▼──────────────────────────────▼───────────────┐
│                    Knowledge and Query Plane                 │
│ Claim store │ Entity registry │ Graph │ Search │ Geo │ Cache │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                       Data Platform                          │
│ Kafka │ Flink │ Lakehouse │ Object Store │ Data Quality     │
│ Connectors │ Schema Registry │ Lineage │ Quarantine         │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ Sources: police, courts, telecom, finance, border, customs, │
│ vehicle registries, surveillance, OSINT, files and humans  │
└─────────────────────────────────────────────────────────────┘

Cross-cutting:
Identity │ ABAC/ReBAC │ Encryption │ Audit │ Policy │ Retention
```

---

# 5. Architectural planes

## 5.1 Evidence plane

Stores legally significant original material:

* Documents.
* Device images.
* Photographs.
* Video.
* Audio.
* Body-camera footage.
* CCTV exports.
* Forensic reports.
* Seized digital material.
* Exported system records.
* Signed statements.
* Physical evidence metadata.

Original evidence is immutable.

Derived products are separate:

```text
Original audio
 ├─ working copy
 ├─ enhanced audio
 ├─ transcript
 ├─ translation
 ├─ speaker annotations
 └─ analytic extracts
```

Every derivative records its parent, tool, operator, algorithm version, parameters, timestamp, and hash.

NIST notes that cryptographic hashes and digital signatures should be stored securely and that blockchain generally introduces more operational overhead than most evidence units can justify. A tamper-evident append-only ledger with independently protected hashes is usually the better default. ([NIST Publications][7])

## 5.2 Knowledge plane

Contains:

* Canonical entities.
* Identity candidates.
* Claims.
* Relationship assertions.
* Events.
* Locations.
* Source metadata.
* Confidence and reliability assessments.
* Contradictions.
* Analytic findings.

This is the intelligence graph.

## 5.3 Operational plane

Handles:

* Cases.
* Investigations.
* Operations.
* Collection plans.
* Tasks.
* Warrants and legal authorities.
* Approvals.
* Evidence transfers.
* Watchlists.
* Alerts.
* Court deadlines.
* Disclosure packages.
* Review and closure.

## 5.4 Analytics plane

Runs:

* Graph algorithms.
* Temporal correlation.
* Geospatial analytics.
* Financial-flow analysis.
* Communication analysis.
* Entity-resolution models.
* Anomaly detection.
* Machine-learning models.
* Controlled AI assistants.

## 5.5 Governance plane

Enforces:

* Purpose limitation.
* Access policy.
* Compartments.
* Retention.
* Sealing and expungement.
* Disclosure restrictions.
* Audit.
* Model governance.
* Data sovereignty.
* Oversight.

---

# 6. Domain-driven design

Aegis should be divided into bounded contexts.

## 6.1 Intelligence Information

Owns:

* Intelligence reports.
* Source evaluations.
* Claims.
* Information handling codes.
* Dissemination restrictions.
* Corroboration and contradiction.

## 6.2 Entity and Identity

Owns:

* Canonical entities.
* Aliases.
* External identifiers.
* Identity clusters.
* Candidate matches.
* Merge and split history.

## 6.3 Investigations

Owns:

* Investigations.
* Cases.
* Case participants.
* Hypotheses.
* Leads.
* Tasks.
* Investigation workspaces.

## 6.4 Evidence and Forensics

Owns:

* Evidence items.
* Evidence containers.
* Hashes.
* Custody events.
* Laboratory requests.
* Derived artifacts.
* Exhibits.

## 6.5 Legal and Judicial

Owns:

* Legal authorities.
* Charges.
* Hearings.
* Court orders.
* Judicial outcomes.
* Disclosure.
* Privilege.
* Sealed and expunged records.

## 6.6 Communications Intelligence

Owns legally acquired:

* Phone identifiers.
* Subscriber records.
* Call-detail metadata.
* Communication events.
* Device associations.
* Communication summaries.

Content must remain separate from metadata and require an appropriate authorization.

## 6.7 Financial Intelligence

Owns:

* Accounts.
* Transactions.
* Institutions.
* Businesses.
* Shareholding.
* Control relationships.
* Beneficial ownership.
* Financial alerts.

FATF recommends combining multiple sources to identify true beneficial owners rather than relying on a single registry or declaration. ([FATF][8])

## 6.8 Movement and Geospatial Intelligence

Owns:

* Locations.
* Routes.
* Border crossings.
* Travel events.
* Vehicle observations.
* Geofences.
* Movement tracks.
* Spatial alerts.

## 6.9 Collaboration and Dissemination

Owns:

* Agency sharing agreements.
* Disclosure packages.
* Requests for information.
* Originator controls.
* Redactions.
* Receipts and acknowledgements.

## 6.10 Analytics and Models

Owns:

* Algorithm definitions.
* Model versions.
* Analytic jobs.
* Findings.
* Explanations.
* Evaluations.
* Approval status.
* Drift and incident records.

---

# 7. Core domain model

## 7.1 Parties

```text
Party
 ├─ Person
 ├─ Organization
 │   ├─ Business
 │   ├─ Criminal organization assessment
 │   ├─ Government agency
 │   ├─ Police department
 │   ├─ Intelligence agency
 │   ├─ Military branch
 │   ├─ Court
 │   ├─ Bank
 │   └─ Legal practice
 └─ Organizational unit
```

A “criminal organization” label must itself be an assessment tied to a source, jurisdiction, designation authority, and time period.

## 7.2 Assets and identifiers

```text
Asset
 ├─ Vehicle
 ├─ Vessel
 ├─ Aircraft
 ├─ Property
 ├─ Device
 ├─ Weapon record
 ├─ Bank account
 ├─ Digital wallet
 └─ Communications account

Identifier
 ├─ Phone number
 ├─ Email address
 ├─ Username
 ├─ Passport
 ├─ National identifier
 ├─ Vehicle registration
 ├─ IMEI
 ├─ IMSI
 ├─ IP address
 └─ Account number
```

Identifiers should usually be entities because they have:

* Ownership history.
* Assignment history.
* Multiple users.
* Multiple sources.
* Validity intervals.
* Reuse and reassignment.

## 7.3 Events

Most complex relationships should be represented through events.

```text
Event
 ├─ Communication
 ├─ Financial transaction
 ├─ Meeting
 ├─ Travel
 ├─ Border crossing
 ├─ Vehicle observation
 ├─ Surveillance observation
 ├─ Ownership transfer
 ├─ Arrest
 ├─ Search
 ├─ Seizure
 ├─ Court hearing
 ├─ Intelligence collection event
 └─ Evidence custody event
```

Instead of:

```text
Person A MET Person B
```

Prefer:

```text
Meeting Event M
  participant → Person A
  participant → Person B
  location → Hotel X
  occurred_at → 2026-01-14 19:30 ± 20 minutes
  source → CCTV Record
  source → Informant Report
```

This supports more than two participants, uncertainty, time, place, and multiple sources.

## 7.4 Claims

A claim is the atomic knowledge unit:

```yaml
claim_id: clm_01J...
subject: person_184
predicate: controls
object: company_972

assertion_type: reported
source_record: intelligence_report_889
source_actor: confidential_source_41
collection_method: human_source_reporting

source_reliability:
  scheme: 3x5x2
  original_grade: B
  normalized: generally_reliable

information_credibility:
  original_grade: 3
  normalized: possibly_true

verification_status: partially_corroborated
analytic_confidence: moderate

observed_time:
  earliest: 2025-08-01
  latest: 2025-11-30

valid_time:
  from: 2024-06-01
  to: null

recorded_at: 2025-12-03T08:51:00Z
jurisdiction: LK
handling_code: restricted
legal_authority: auth_827

corroborates: [clm_872]
contradicts: [clm_334]
supersedes: null
```

## 7.5 Relationship assertions

A single relationship-strength number is misleading.

Store separate dimensions:

```text
semantic type       associate / owner / caller / participant / controller
directness          direct / inferred / hearsay
frequency           number of interactions
duration            length of association
recency             time since last supported interaction
corroboration       number and quality of independent sources
confidence          analyst or model confidence
legal relevance     scoped to investigative purpose
```

The UI may calculate a display score, but must expose the dimensions behind it.

## 7.6 Source model

```text
Source
 ├─ Human source
 ├─ Anonymous source
 ├─ Government system
 ├─ Foreign agency
 ├─ Financial institution
 ├─ Telecom provider
 ├─ Sensor or camera
 ├─ Open source
 ├─ Court record
 ├─ Investigator observation
 └─ Algorithmic result
```

An AI model is a source of an **analytic suggestion**, never a source of observed fact.

## 7.7 Time model

Every relevant record should support:

* **Event time:** when something occurred.
* **Valid time:** when the claim was true or believed to be true.
* **Knowledge time:** when the agency learned it.
* **System time:** when Aegis stored or changed it.
* **Authorization time:** when collection or use was legally permitted.

This enables questions such as:

> What did investigators know on 1 March, based only on information legally available at that time?

## 7.8 Ontology architecture

Aegis's domain model is organized as a layered ontology in the sense proven by
Palantir Foundry: the ontology is the operational layer that connects integrated
data to the applications where decisions happen. Aegis adopts Foundry's layer
structure while keeping its own stricter provenance rules (see §7.10 for the
explicit mapping and divergences).

**Semantic layer — what exists.**

* **Object types** define entities (person, organization, location, vehicle,
  phone number) and events. They are schemas; individual entities are instances.
* **Properties** define an object type's characteristics. In Aegis a property
  *value* is always a claim (Rule 2) — the ontology entry defines validation,
  sensitivity, and display, never a mutable column.
* **Link predicates** define relationships between object types. Every link
  instance is a claim with source, grading, and time.
* **Interfaces** describe shared shapes across object types (e.g. `Party` over
  person and organization; `Identifiable` for anything carrying registry
  identifiers). Workflows and analytics target interfaces so new object types
  inherit behavior without new code. Prefer composition of focused interfaces
  over wide, sparse object types.
* **Shared property types** define a property once (e.g. `alias`,
  `registered_identifier`) and reuse it across object types with consistent
  semantics, formatting, and sensitivity.

**Kinetic layer — what can happen.**

* **Action types** are the only write path. Each declares its parameters, its
  submission criteria (who may run it, against what state), its validation
  rules, and its side effects (notifications, webhooks, projection refresh).
  Every execution is audited.
* **Functions** are declared, versioned derivations over the ontology: computed
  predicates (e.g. prison co-location from overlapping remand windows), derived
  display values, and rule-based inference. A function's output is attributed to
  an algorithmic source and enters the store as a suggestion or as a rebuildable
  derived record (a projection/finding, never a canonical claim) — never as
  anonymous fact and never machine-written canon (Rule 2, §7.6, ADR-027).

**Consumption layer — how it is used.**

* **Projections** index recorded claims into query-serving shapes (graph views,
  search indexes, materialized edges). They are rebuildable caches, never canon.
* **Object sets** are saved, composable, access-controlled queries over objects
  — the unit that feeds analytics, watchlists, and bulk operations.
* **Object views** are the entity-360 surface: everything known about one
  entity — claim-derived properties, links, timeline, sources, cases — with
  every displayed value traceable to its claims.
* **Typed SDKs** are generated from the ontology (Python and TypeScript), so
  applications are written against domain types, not raw HTTP. SDK tokens are
  scoped to the intersection of the application's grant and the user's own
  permissions.

**Governance layer — how it changes.**

The ontology artifact is versioned (semver), changes flow through a proposal →
review → migration workflow, historical versions remain interpretable, and every
consumer (validators, authorization types, UI descriptors, SDKs) is regenerated
from it. Drift between ontology and code is a build failure.

## 7.9 Ontology design principles

These principles govern every ontology change; reviewers reject changes that
violate them.

* **Model reality, not systems.** Object types represent real-world entities —
  a person, a vessel, a meeting — never a source system's table, API response,
  or spreadsheet tab.
* **Competency questions are requirements.** Each ontology increment states the
  analyst questions it must answer ("Which persons shared a prison block with X
  during 2019?", "What sources support this edge?") and keeps them as executable
  tests against seeded data.
* **Curate properties intentionally.** Every property has clear investigative
  or technical value. Reject the kitchen sink: mapping source columns 1:1 into
  object types.
* **Separate identity from observation.** Entities are stable identities;
  measurements and sightings about them are events/claims. A source row that
  bundles several real-world things is decomposed into linked objects, never
  modeled as one wide type (no embedded entities).
* **Name in the domain's language.** `person.aliases`, not `tbl_aka_names`;
  predicates read as statements a human analyst would make. No place names, no
  compound relations, no credibility words inside predicate names.
* **Minimal ontological commitment, additive evolution.** Assert only what is
  needed; extend by adding types, interfaces, and links rather than renaming or
  overloading. Protect core types — builders extend via new linked types and
  interface implementations, not breaking changes.
* **Rule of three.** The third time a shape is duplicated, refactor it into a
  shared property type or interface.

## 7.10 Aegis ↔ Palantir Foundry concept map

| Foundry concept | Aegis counterpart | Divergence (deliberate) and why |
| --- | --- | --- |
| Ontology (semantic + kinetic layers) | `ontology/aegis.yaml`, the single domain artifact | Same role; Aegis's is a versioned file in git, not a managed service |
| Object type / object | `object_types` entry / `entity` row | Aegis entities carry no asserted properties of their own — labels are rebuilt from claims (Rule 2) |
| Property value | claim with an auto-derived `has_<property>` predicate | Values are claims with source, grading, and time; contradictory values coexist (Rule 5) |
| Link type / link | predicate / claim between two entities | Links are claims — provenance and time are mandatory, and symmetric links store one canonical row |
| Interface, shared property type | `interfaces:` / `shared_properties:` (ontology v2) | Adopted as-is |
| Action type (parameters, submission criteria, side effects) | `actions:` declarations enforced by the actions layer | Adopted; `audit: true` is mandatory, not optional (Article X) |
| Function / function-backed action | `functions:` registry of versioned derivations | Function output is attributed to an algorithmic source and is suggest-only or a rebuildable derived record — never a machine-written canonical claim (§7.6, ADR-027) |
| Datasource backing + writeback datasets | `source` / `source_record` + review queue | No silent writeback: machine output must pass human adjudication before it becomes a recorded claim |
| Object Storage v2 (funnel, object databases, Object Set Service) | projection builders + object sets | Projections are disposable caches; losing every projection loses nothing |
| Object Views / Object Explorer | entity-360 object views | Every displayed value links back to the claims and sources behind it |
| OSDK (generated typed clients) | generated Python/TypeScript SDKs from aegis.yaml | Same dual scoping: app grant ∩ user permission |
| Ontology proposals / branching | proposal → review → semver bump + migration, history retained | Scaled to a single-repo workflow |
| Security markings, mandatory controls | handling codes + OpenFGA relations + row/field filters | ReBAC-first (case membership, handler-of), evaluated at query time (Rule 6) |

The one divergence that defines Aegis: **Foundry's object properties hold current
values; Aegis's hold competing claims.** Foundry layers user edits over source
data to present one truth. Aegis presents graded, sourced, possibly conflicting
assertions and lets analysts assess them — because in intelligence work the
disagreement *is* the data. Everything else about the layer architecture
transfers.

---

# 8. Graph representation

Use a hybrid model.

## 8.1 Canonical graph

Contains relatively stable entities and associations:

```text
Person
Organization
Vehicle
Account
Device
Phone
Location
Case
Event
```

## 8.2 Assertion graph

Contains reified claims:

```text
Claim ──SUBJECT──> Person
Claim ──PREDICATE──> "owns"
Claim ──OBJECT──> Vehicle
Claim ──SUPPORTED_BY──> Evidence
Claim ──REPORTED_IN──> IntelligenceReport
Claim ──CONTRADICTS──> Claim
```

Reification is necessary because claims have rich provenance and may conflict.

## 8.3 Materialized operational edges

For fast traversal, confirmed or authorized claims can generate projection edges:

```text
(Person)-[:ASSOCIATED_WITH {
  projection_version,
  confidence_band,
  valid_from,
  valid_to
}]->(Organization)
```

The projection edge is a cache. The underlying claims remain the source of truth.

## 8.4 Three-tier graph strategy

Do not load every phone call or financial transaction permanently as a top-level graph edge.

### Tier 1: Knowledge graph

Stable entities, assessed relationships, cases, organizations, assets.

### Tier 2: Investigation graph projection

Detailed calls, transactions, movements, and events for a selected:

* Case.
* Time window.
* Geography.
* Set of selectors.
* Authorized user.

### Tier 3: Raw event lake

Billions of low-level records stored in columnar form.

This prevents supernodes and uncontrolled graph growth.

---

# 9. Data ingestion architecture

Aegis must support:

* Scheduled batch imports.
* API polling.
* Webhooks.
* Database CDC.
* Event streams.
* SFTP.
* Signed exchange packages.
* Manual investigator entry.
* Bulk document upload.
* Mobile and field collection.
* Federated query without copying.

## 9.1 Pipeline

```text
Source connector
      ↓
Connection and authority validation
      ↓
Raw immutable landing
      ↓
Malware and file-format inspection
      ↓
Schema validation
      ↓
Normalization and data classification
      ↓
Data-quality checks
      ↓
Source-specific transformation
      ↓
Claim and event extraction
      ↓
Entity-resolution candidates
      ↓
Human or automated adjudication
      ↓
Canonical storage
      ↓
Graph, search and geospatial projections
      ↓
Rules, alerts and downstream analytics
```

## 9.2 Raw landing zone

Every received item gets:

```text
source system
source record ID
connector version
ingestion timestamp
source timestamp
legal authority
purpose
payload hash
digital signature when available
schema version
processing status
classification
retention policy
```

Never modify the original payload.

## 9.3 Idempotency

Every input should receive a deterministic ingestion key:

```text
hash(source_system + source_record_id + source_version)
```

Retries must not create duplicate evidence, events, or claims.

Kafka provides durable event topics and transactional processing capabilities, while Flink supports stateful recovery through checkpoints and exactly-once state consistency. End-to-end correctness still requires idempotent external sinks and transactional-outbox patterns; “Kafka exactly once” alone does not make every external system exactly once. ([Apache Kafka][9])

## 9.4 Schema registry and data contracts

Each source gets:

* Versioned schema.
* Field definitions.
* Sensitivity classifications.
* Legal-use restrictions.
* Expected update frequency.
* Data-quality rules.
* Owner.
* Contact.
* Decommissioning policy.

Breaking changes enter quarantine until reviewed.

## 9.5 Quarantine

Records should be quarantined when:

* Schema validation fails.
* The authority has expired.
* Malware is detected.
* The source signature is invalid.
* Required provenance is absent.
* The record violates jurisdiction rules.
* Data appears corrupted or unexpectedly voluminous.
* Identity resolution creates an unsafe ambiguity.

---

# 10. Entity resolution

Entity resolution is one of the most dangerous parts of the platform. A wrong merge can contaminate every downstream analysis.

## 10.1 Resolution stages

### Deterministic matching

Examples:

* Exact passport number plus issuing country.
* Exact account identifier plus bank.
* VIN plus jurisdiction.
* Provider-assigned telecom identifier.

### Probabilistic matching

Uses:

* Names.
* Dates of birth.
* Addresses.
* Phone numbers.
* Family members.
* Photographs where legally allowed.
* Travel patterns.
* Shared identifiers.

### Contextual graph matching

Uses surrounding relationships:

```text
Same alias
Same phone
Same employer
Same address during matching time
Same frequent associates
```

### Human adjudication

Required for:

* High-impact merges.
* Conflicting official identities.
* Cross-border identities.
* Protected persons.
* Informants.
* Candidates above uncertainty thresholds.

## 10.2 Never perform irreversible merges

Use an identity-cluster model:

```text
IdentityCluster
  ├─ SourceRecord A
  ├─ SourceRecord B
  └─ SourceRecord C
```

Cluster membership is versioned.

Analysts can:

* Confirm.
* Reject.
* Split.
* Merge.
* Mark unresolved.
* Add explanatory notes.

Every decision must record the evidence used.

## 10.3 Multilingual identity handling

Support:

* Sinhala.
* Tamil.
* English.
* Arabic.
* Hindi.
* Urdu.
* Chinese scripts.
* Multiple transliteration standards.
* Initial-based names.
* Patronymics.
* Compound family names.
* Honorifics and aliases.

Do not rely on English phonetic matching alone.

## 10.4 Entity-resolution explanation

Each candidate pair should show:

```text
Why suggested:
  Passport number exact match             +0.80
  Name transliteration similarity         +0.12
  Date of birth conflict                   -0.25
  Shared historical address               +0.08

Model output:
  Candidate match, not confirmed identity
```

---

# 11. Storage strategy

A production implementation needs polyglot persistence.

## 11.1 PostgreSQL

Use for strongly consistent operational records:

* Cases.
* Tasks.
* Legal authorities.
* Evidence metadata.
* Custody events.
* Approvals.
* Disclosure.
* Policies.
* Entity-resolution decisions.
* Audit references.

## 11.2 PostGIS

Use for authoritative operational geospatial data:

* Locations.
* Administrative boundaries.
* Routes.
* Geofences.
* Spatial intersections.
* Distance and containment queries.

PostGIS adds storage, indexing, and querying of geographic data to PostgreSQL. ([PostGIS][10])

## 11.3 Object storage

Use S3-compatible storage with:

* Object versioning.
* Retention lock.
* Legal hold.
* Server-side encryption.
* Separate evidence and analytics buckets.
* Independent hash ledger.
* Cross-region replication according to data-residency policy.

Stores:

* Original documents.
* Images.
* Video.
* Audio.
* Forensic images.
* Export packages.
* Raw source payloads.

## 11.4 Iceberg lakehouse

Use Apache Iceberg over object storage for:

* Raw normalized records.
* Historical claims.
* Telecom metadata.
* Financial events.
* Travel events.
* Analytical features.
* Model-training snapshots.

Iceberg supports hidden partitioning and schema/partition evolution, which are useful when source schemas and query patterns change over long investigations. ([Apache Iceberg][11])

## 11.5 Graph database

### Recommended first production choice

**Neo4j Enterprise**, behind an internal graph abstraction.

Reasons:

* Mature property-graph model.
* Cypher.
* Strong investigative query ergonomics.
* Graph Data Science ecosystem.
* Clustering and enterprise security.
* Rapid development of path and neighborhood queries.

However, do not assume a product name guarantees performance at billions of relationships. Benchmark with realistic:

* Degree distributions.
* Supernodes.
* Temporal filters.
* Security predicates.
* Concurrent users.
* Projection rebuilds.
* Algorithm workloads.

### Sovereign/open-stack alternative

For deployments requiring a horizontally partitioned open architecture:

* JanusGraph with ScyllaDB/Cassandra.
* Or another benchmarked distributed graph engine.

The domain must not depend directly on vendor-specific graph objects.

## 11.6 OpenSearch

Use for:

* Full-text search.
* Faceted search.
* Multilingual analysis.
* Fuzzy and phonetic matching.
* Document search.
* Vector similarity.
* Search highlighting.
* Fast entity lookup.

Search results return identifiers; access policy must be re-evaluated before returning details.

## 11.7 Redis

Use only for:

* Short-lived caches.
* Rate limiting.
* Session state.
* Job coordination.
* Authorized query-result caching.

Never use it as an evidence or intelligence system of record.

## 11.8 Analytical query engines

Use:

* Trino for federated SQL.
* Spark for large batch jobs.
* Flink for real-time correlation.
* Optional ClickHouse for very high-volume interactive event aggregations.

---

# 12. Search architecture

## 12.1 Global search

One search field should recognize:

* Person names.
* Aliases.
* Phone numbers.
* Passport numbers.
* Vehicle plates.
* VINs.
* Addresses.
* Businesses.
* Accounts.
* Cases.
* Reports.
* Document text.
* Locations.

Results are grouped by category and include source and access context.

## 12.2 Search modes

```text
Exact search
Fuzzy search
Phonetic/transliteration search
Boolean search
Temporal search
Geospatial search
Document-content search
Graph-pattern search
Similarity search
Historical/as-of search
```

## 12.3 Graph-pattern search

Example:

```text
Find people who:
  communicated with two or more members of Organization X
  AND travelled through Dubai within 72 hours
  AND are linked to a business receiving funds from Account Y
```

The query planner should:

1. Validate authorization.
2. Restrict the time and source scope.
3. Use search/lakehouse indexes to generate candidates.
4. Use the graph for bounded traversal.
5. Return evidence paths and caveats.

## 12.4 Purpose-aware search

Before sensitive searches, require:

* Case.
* Investigation purpose.
* Legal authority where required.
* Query justification.

This is not cosmetic metadata. It becomes part of the authorization decision and audit record.

---

# 13. Graph analytics

## 13.1 Deterministic analytics first

Support:

* One-hop and multi-hop neighborhood expansion.
* Shortest paths.
* All paths under bounded constraints.
* Common-neighbor analysis.
* Shared identifier discovery.
* Community detection.
* Connected components.
* Degree and weighted-degree centrality.
* Betweenness.
* PageRank-like influence.
* Brokerage and bridge analysis.
* K-core.
* Temporal motifs.
* Bipartite projections.
* Flow networks.

## 13.2 Analyst warnings

Every metric should display an interpretation warning.

Example:

```text
High betweenness:
This entity lies on many known paths in the observed graph.

It does not prove:
- leadership
- criminal involvement
- control
- awareness of every connected participant
```

## 13.3 Hidden relationship discovery

A candidate hidden relationship can be suggested from:

* Repeated co-location.
* Shared devices.
* Common accounts.
* Synchronized travel.
* Repeated financial intermediaries.
* Communication immediately before or after events.
* Shared ownership chains.
* Overlapping associates.
* Matching document metadata.

It must be created as:

```text
AnalyticFinding:
  possible_association(Person A, Person B)
```

Not:

```text
Person A ASSOCIATED_WITH Person B
```

until reviewed or supported by claims.

## 13.4 GNNs and link prediction

Graph neural networks may be used experimentally for candidate discovery, but link-prediction explanations remain difficult to evaluate, and criminal-network datasets have structural and sampling limitations. ([arXiv][12])

Production sequence:

1. Deterministic rules.
2. Transparent statistical models.
3. Supervised ML with strong evaluation.
4. GNN research mode.
5. Limited operational use only after independent validation.

---

# 14. Communication analysis

Support metadata such as:

```text
caller
receiver
start time
duration
cell site or coarse location where lawful
communication type
device identifiers
provider
source record
legal authority
```

Capabilities:

* Ego networks.
* Frequency and duration matrices.
* Communication bursts.
* First and last contact.
* Changes before and after an event.
* Common contacts.
* Device and SIM changes.
* Cell-site sequence analysis.
* Communication-community detection.
* Time-zone-aware timeline correlation.

Content and metadata must remain separately authorized.

A thousand calls should normally be represented as an aggregated relationship:

```text
A → B
1,024 calls
first: 2025-01-03
last: 2026-02-11
total duration: ...
```

The individual calls stay in the event store and appear on drill-down.

---

# 15. Financial intelligence

## 15.1 Model

```text
Person
Business
Financial institution
Account
Transaction
Ownership interest
Control relationship
Beneficial owner assessment
Invoice
Asset
Digital wallet
```

## 15.2 Analytics

* Fan-in and fan-out.
* Circular flows.
* Rapid pass-through.
* Structuring patterns.
* Shared beneficiaries.
* Layering.
* Dormant-account activation.
* Cross-border flows.
* Asset purchases after transfers.
* Shell-company chains.
* Common directors, addresses, or agents.
* Transaction sequences around known events.

## 15.3 Beneficial ownership

Do not treat corporate registry shareholders as automatically equivalent to actual controllers.

Support:

```text
legal owner
declared beneficial owner
assessed beneficial owner
nominee relationship
control through voting
control through agreements
control through intermediaries
```

Each is a claim with independent provenance.

---

# 16. Geospatial and movement intelligence

## 16.1 Map engine

Recommended frontend:

* MapLibre GL JS for the base map.
* deck.gl for large event layers, routes, arcs, heatmaps, and animated movement.
* Server-generated vector tiles.
* PostGIS for spatial operations.
* OGC API Features for interoperable feature access.

OGC API Features provides standardized web interfaces for querying geospatial features, while MapLibre uses GPU-accelerated browser rendering and PostGIS provides spatial storage and indexing. ([GitHub][13])

## 16.2 Supported layers

* People and asset observations.
* Routes.
* Border crossings.
* Ports and airports.
* Addresses.
* Properties.
* Telecom cells.
* Meetings.
* Surveillance events.
* Financial transaction locations.
* Vehicle observations.
* Agency-defined areas.
* Administrative boundaries.
* Operational zones.

## 16.3 Time-aware map

The map and timeline should be synchronized.

Dragging the time window changes:

* Visible entities.
* Known ownership.
* Active phone assignments.
* Locations.
* Relationships.
* Organizational membership.
* Legal status.

## 16.4 Geographic uncertainty

Locations may be:

```text
Exact coordinate
Address centroid
Cell-tower coverage area
City-level claim
Country-level travel record
Estimated route
Uncertain polygon
```

The UI must visually distinguish precision.

## 16.5 Privacy-aware map rendering

Low-authority users may see:

* Country instead of exact address.
* General area instead of informant meeting location.
* Redacted route.
* Aggregated heatmap instead of individual observations.

---

# 17. Timeline analysis

A unified timeline should combine:

* Calls.
* Transactions.
* Travel.
* Vehicle observations.
* Meetings.
* Surveillance.
* Intelligence reports.
* Evidence acquisition.
* Arrests.
* Court events.
* Ownership changes.
* Entity-resolution decisions.

Features:

* Multiple time zones.
* Uncertain intervals.
* Relative-time search.
* Before/after comparison.
* Event clustering.
* Gap analysis.
* Contradiction detection.
* “What was known at the time?” mode.
* Comparison of two or more subjects.

---

# 18. Investigation workspace

Each investigation gets a controlled workspace.

## Main views

```text
Overview
Entities
Graph
Map
Timeline
Evidence
Intelligence reports
Hypotheses
Leads
Tasks
Analytics
Legal authorities
Disclosures
Audit
```

## Hypothesis management

Analysts should be able to create competing hypotheses:

```text
H1: Company X controls the trafficking route.
H2: Company X is an unwitting logistics provider.
H3: Company X is controlled by a separate intermediary.
```

For each hypothesis:

* Supporting claims.
* Contradicting claims.
* Missing information.
* Collection requirements.
* Analyst confidence.
* Review history.

This reduces confirmation bias better than a graph that only displays selected connections.

## “Why connected?” panel

Selecting a relationship should show:

```text
Connection explanation

Person A → Company X

1. Company registry lists A as director
2. Bank record shows signing authority
3. Intelligence report alleges beneficial control
4. Analyst assessment identifies probable nominee director

Contradictory information:
5. Tax record shows no declared income from Company X

Assessment:
Probable control, not judicially established
```

---

# 19. Intelligence report workflow

```text
Draft
  ↓
Source grading
  ↓
Information grading
  ↓
Handling restrictions
  ↓
Supervisor review
  ↓
Claims extracted
  ↓
Entity resolution
  ↓
Dissemination approval
  ↓
Published intelligence report
  ↓
Corroboration or re-evaluation
```

The report must preserve original language. Structured extraction creates linked claims but does not rewrite the original.

Anonymous tips should default to:

```text
source identity: unknown
source reliability: cannot be assessed
information credibility: unverified
action: triage only
```

---

# 20. Evidence and chain-of-custody workflow

```text
Acquisition
  ↓
Initial hash and registration
  ↓
Packaging or secure upload
  ↓
Storage
  ↓
Transfer
  ↓
Examination
  ↓
Derived artifacts
  ↓
Review
  ↓
Disclosure or court exhibit
  ↓
Return, destruction or long-term retention
```

Each custody event includes:

```text
evidence ID
from custodian
to custodian
date and time
location
purpose
condition
container/seal
digital hash
authorization
signatures
```

Critical evidence operations should use dual control where appropriate.

---

# 21. Informant protection

Informants require a separate security domain.

## Design

* Real identity stored separately.
* Operational pseudonym used in normal reports.
* Handler-only access by default.
* Two-person approval for identity disclosure.
* No identity exposed through graph expansion.
* No search snippets revealing protected identity.
* Separate encryption key.
* Access alerts to an independent supervisor.
* Export disabled except through a formal workflow.

The graph may display:

```text
Confidential Source CS-041
```

without enabling an analyst to traverse to the source’s real identity.

---

# 22. Courts, lawyers, and privileged material

## Judicial states

Use explicit states:

```text
allegation
investigation
arrest
charge
trial
conviction
acquittal
dismissal
appeal
overturned
sealed
expunged
```

A conviction later overturned must not remain displayed as a current conviction.

## Legal representatives

Relationships such as:

```text
REPRESENTS
PRIVILEGED_COMMUNICATION_WITH
COURT_APPOINTED_FOR
```

must be time-bounded and case-scoped.

Privileged communications must be segregated and inaccessible to ordinary investigative searches unless an applicable legal process authorizes access.

## Disclosure

Support:

* Relevant evidence review.
* Exculpatory or contradictory material identification.
* Redaction.
* Privilege review.
* Court-ordered disclosure.
* Export manifests.
* Hash verification.
* Recipient acknowledgement.

---

# 23. Security architecture

CJIS policy treats protection as a full information lifecycle problem—from creation and viewing through transmission, storage, dissemination, and destruction. Aegis should adopt the same lifecycle mindset even outside the United States. ([Law Enforcement][14])

## 23.1 Zero trust

No access is trusted because a user is “inside the police network.”

NIST zero trust focuses authorization on users, devices, assets, and resources rather than granting implicit trust based on network location. ([NIST Computer Security Resource Center][15])

Evaluate every request using:

```text
User identity
Agency
Role
Clearance
Case assignment
Compartments
Purpose
Legal authority
Device posture
Session risk
Resource classification
Originating agency
Requested action
Location and time
```

## 23.2 RBAC + ABAC + ReBAC

### RBAC

General job responsibilities:

* Investigator.
* Analyst.
* Evidence officer.
* Prosecutor.
* Court liaison.
* Supervisor.
* Auditor.

### ABAC

Attributes of user, data, action, and environment.

NIST defines ABAC as evaluating subject, object, operation, and sometimes environmental attributes against policy. ([NIST Computer Security Resource Center][16])

### ReBAC

Relationships:

```text
User assigned to Case
Agency participates in Task Force
User is handler for Informant
Prosecutor assigned to Matter
```

## 23.3 Policy example

```rego
allow_view_claim if
  user.clearance >= claim.classification
  and user.agency in claim.authorized_agencies
  and user.purpose in claim.allowed_purposes
  and user.case_assignment contains claim.case_id
  and current_time < claim.authority_expiry
  and not claim.sealed
```

Enforcement must occur in backend services and data projections, not only in the UI.

## 23.4 Compartments

Examples:

* Operation-specific.
* Informant identity.
* Counterintelligence.
* Military branch.
* Foreign-partner caveat.
* Financial intelligence.
* Juvenile records.
* Sealed judicial material.

## 23.5 Originator control

The source agency controls:

* Who may view.
* Whether it may be quoted.
* Whether it may be exported.
* Whether it may be used as evidence.
* Whether it may be shared onward.
* Expiration.

## 23.6 Break-glass access

Emergency access requires:

* Reason.
* Incident or case.
* Scope.
* Expiry.
* Strong authentication.
* Immediate audit notification.
* Mandatory subsequent review.

## 23.7 Insider-threat controls

* Bulk-query detection.
* Unusual entity lookups.
* Repeated searches of acquaintances.
* Excessive export.
* Access outside assigned cases.
* Informant-record access.
* Honey records.
* Export watermarking.
* Independent audit review.

Analytics should identify suspicious access behavior without hiding the rules from authorized oversight personnel.

---

# 24. Privacy and legal compliance

There is no single “globally compliant” configuration.

Aegis needs jurisdiction-specific **legal policy packs**.

Each pack defines:

* Collection authority.
* Permitted purposes.
* Sensitive categories.
* Retention.
* Data localization.
* Cross-border transfer.
* Notice requirements.
* Disclosure.
* Correction and challenge procedures.
* Sealing and expungement.
* Biometric restrictions.
* Automated-decision restrictions.
* Oversight authority.

UNODC emphasizes accountability, transparency, human-rights protection, independent oversight, and data-protection mechanisms in democratic policing. ([UNODC][17])

## Prohibited platform behavior

Aegis should technically prevent:

* Searching without a purpose or case where required.
* Indefinite retention by default.
* Automatic criminal labeling based on associations.
* Autonomous arrest, detention, or charging recommendations.
* Person-level predictive policing based only on profiling.
* Use of protected characteristics as proxies for criminality.
* Secret model changes.
* Silent deletion of conflicting or exculpatory information.

The EU AI framework specifically places strong restrictions on law-enforcement AI and prohibits certain individual predictive-policing uses based on profiling or personality characteristics. ([EUR-Lex][18])

---

# 25. Risk scoring

The phrase “risk score” is too broad.

Do not build:

```text
Person X criminal risk = 87
```

Build purpose-specific indicators:

```text
Transaction money-laundering alert score
Identity-match confidence
Evidence-integrity risk
Case deadline risk
Network structural centrality
Travel-pattern anomaly
Watchlist match confidence
Data-quality risk
```

Every score must include:

* Intended use.
* Prohibited use.
* Model version.
* Input features.
* Supporting records.
* Known limitations.
* Calibration.
* False-positive performance.
* Review requirements.
* Expiry or recalculation policy.

A model output is an investigative lead, not evidence of guilt.

---

# 26. AI assistant architecture

AI can help with:

* Document summarization.
* Named-entity suggestions.
* Translation.
* Transcript review.
* Timeline extraction.
* Contradiction detection.
* Query construction.
* Case briefing.
* Evidence-package indexing.
* Alternative-hypothesis generation.

## AI execution flow

```text
User request
    ↓
Purpose and authorization check
    ↓
Case-scoped retrieval
    ↓
Redaction and minimization
    ↓
Approved model
    ↓
Response with source citations
    ↓
Human review
    ↓
Optional saved analytic note
```

## AI restrictions

The model must not:

* Add canonical graph relationships directly.
* Change identity clusters.
* Mark someone guilty.
* Issue operational commands.
* Export intelligence.
* reveal informant identities.
* access privileged material.
* create evidence.
* conceal uncertainty.

Any proposed claim enters:

```text
AI-suggested extraction
        ↓
Human verification
        ↓
Structured claim
```

NIST’s AI RMF is intended to incorporate trustworthiness and risk management into the design, use, and evaluation of AI systems. ([NIST][19])

---

# 27. APIs

## External APIs

Use versioned REST APIs and asynchronous exchange.

```http
POST /v1/intelligence-reports
POST /v1/claims
POST /v1/evidence-items
POST /v1/evidence-items/{id}/custody-transfers
POST /v1/entity-resolution/candidates/{id}/decision

GET /v1/entities/{id}
GET /v1/entities/{id}?asOf=2025-01-01T00:00:00Z

POST /v1/search
POST /v1/graph/expand
POST /v1/graph/path-search
POST /v1/analytics/jobs
POST /v1/disclosure-packages
```

## Geospatial API

Expose authorized features using OGC API Features-compatible endpoints.

```http
GET /ogc/collections/vehicle-observations/items
GET /ogc/collections/travel-events/items?bbox=...
```

## Internal APIs

* gRPC or well-defined REST between services.
* Protobuf/JSON Schema contracts.
* AsyncAPI for Kafka topics.
* CloudEvents-compatible envelopes.
* OpenTelemetry trace context.

## Exchange packages

A disclosure package should contain:

```text
manifest
schema version
records
handling restrictions
legal basis
redaction log
source agency
recipient
hash manifest
digital signature
expiry
acknowledgement requirement
```

NIEM-compatible mappings should be supported for justice and public-safety integrations.

---

# 28. Event architecture

Example domain events:

```text
IntelligenceReportPublished
ClaimRecorded
ClaimRetracted
EntityMatchProposed
EntityMatchConfirmed
IdentityClusterSplit
EvidenceRegistered
EvidenceTransferred
LegalAuthorityExpired
CaseOpened
CaseClosed
WatchlistMatchDetected
DisclosurePackageReleased
RetentionPeriodExpired
RecordSealed
```

Use the transactional outbox pattern:

```text
Domain database transaction
   ├─ update case/evidence/claim
   └─ insert outbox event

Publisher
   ↓
Kafka
   ↓
Graph projection
Search projection
Analytics
Notifications
Audit enrichment
```

The graph and search indexes are rebuildable projections, not the sole source of truth.

---

# 29. Visualization architecture

## Graph client

Use a WebGL-based renderer such as:

* Sigma.js for high-performance custom exploration.
* Cytoscape.js when its analysis and layout ecosystem is more valuable.

Never send millions of nodes to a browser.

## Server-side subgraph extraction

The user begins with:

* A known entity.
* Search results.
* A saved analytic query.
* A watchlist event.

Then expands a bounded neighborhood.

Controls:

```text
Maximum hops
Relationship types
Time range
Confidence threshold
Source types
Cases
Jurisdictions
Maximum result count
```

## Semantic zoom

### Far zoom

Show:

* Communities.
* Organizations.
* Geographic clusters.
* Aggregate flows.

### Mid zoom

Show:

* Key entities.
* Aggregated relationships.
* Major events.

### Near zoom

Show:

* Individual calls.
* Transactions.
* Evidence.
* Claims and sources.

## Visual lenses

Investigators can switch among:

* Relationship-type lens.
* Confidence lens.
* Time lens.
* Source lens.
* Agency lens.
* Evidence-status lens.
* Contradiction lens.
* Legal-access lens.

Avoid using red as a universal “criminal” indicator.

---

# 30. UI/UX design

## Main shell

```text
┌─────────────────────────────────────────────────────────┐
│ Global Search │ Investigation │ Alerts │ Tasks │ Profile │
├───────────────┬─────────────────────────────────────────┤
│ Workspace     │                                         │
│ navigation    │             Active View                 │
│               │        Graph / Map / Timeline           │
│ Entities      │                                         │
│ Evidence      │                                         │
│ Reports       │                                         │
│ Hypotheses    │                                         │
├───────────────┴───────────────────────┬─────────────────┤
│ Selected item details                │ Provenance       │
│ properties and history               │ Why connected?  │
└───────────────────────────────────────┴─────────────────┘
```

## Interaction principles

* Search first, expand second.
* Every claim opens its source.
* Every analytic result shows why.
* Contradictory information is visible.
* Current state and historical state are clearly separated.
* Unsaved analytic notes are visually different from published intelligence.
* Restricted information is not hinted at through counts or hidden labels.
* Map, graph, and timeline selections remain synchronized.
* Analysts can undo workspace changes without modifying source data.
* Exports preview all included and redacted fields.

---

# 31. Collaboration

Support:

* Case-level teams.
* Tasks and assignments.
* Notes.
* Review requests.
* Analyst comments.
* Hypothesis discussions.
* Evidence requests.
* Requests for information to other agencies.
* Versioned intelligence products.
* Supervisor approval.
* Conflict-free workspace annotations.

Comments must distinguish:

```text
Private working note
Team note
Published analytic assessment
Formal intelligence report
Evidence annotation
```

Chat messages are not automatically intelligence records.

---

# 32. Alerts and watchlists

## Watchlist types

* Exact identity.
* Candidate identity.
* Vehicle.
* Passport.
* Phone.
* Account.
* Organization.
* Geofence.
* Travel pattern.
* Transaction rule.
* Communication pattern.

## Alert lifecycle

```text
Detected
  ↓
Deduplicated
  ↓
Policy and authority checked
  ↓
Triage
  ↓
Assigned
  ↓
Investigated
  ↓
Confirmed / dismissed / escalated
  ↓
Outcome recorded
```

Every alert includes:

* Rule or model.
* Input records.
* Match explanation.
* Confidence.
* False-positive considerations.
* Legal-use restrictions.

Watchlist matches must distinguish exact identifiers from probabilistic identity matches.

---

# 33. Deployment architecture

## 33.1 Sovereign-cell model

```text
National or agency data cell
 ├─ local storage
 ├─ local graph
 ├─ local search
 ├─ local policy engine
 ├─ local encryption keys
 └─ federated exchange gateway
```

A regional or international layer stores only explicitly shared information.

This is more realistic than a single database containing Sri Lankan, Indian, American, Chinese, Pakistani, Emirati, and Maldivian operational data.

## 33.2 Kubernetes

Deploy on Kubernetes across:

* Government cloud.
* Private cloud.
* On-premises data centers.
* Classified networks.
* Disconnected environments.

Use separate clusters or security domains for different classifications, not merely Kubernetes namespaces.

## 33.3 Recommended platform services

```text
Ingress/API gateway        Envoy, Kong or equivalent
Identity                   Keycloak, Entra ID or agency IdP
Policy                     Open Policy Agent
Relationship authorization SpiceDB/OpenFGA-style service
Secrets                    Vault plus HSM/KMS
Service mesh               Istio or Linkerd
GitOps                     Argo CD
Observability              OpenTelemetry
Metrics                    Prometheus
Dashboards                 Grafana
Logs                       Loki or OpenSearch
Traces                     Tempo or Jaeger
Workflow orchestration     Temporal
```

Temporal is suitable for durable processes such as evidence transfers, disclosure approvals, long-running imports, and cross-agency requests because its workflows persist progress and resume after failures. ([GitHub][20])

## 33.4 Network zones

```text
Public integration zone
Connector/DMZ zone
Application zone
Data zone
Evidence vault
Analytics zone
Management zone
Audit zone
Cross-agency exchange zone
```

No source connector should write directly to the canonical graph.

---

# 34. Availability and disaster recovery

Initial production targets should include:

* Multi-availability-zone operation.
* Synchronous replication for critical case and custody metadata.
* Versioned, locked object storage.
* Independently protected audit records.
* Point-in-time database recovery.
* Regular restore tests.
* Region-level disaster-recovery exercises.
* Offline evidence manifests.
* Cryptographic verification after restore.

Possible initial SLO targets:

```text
Core case/evidence APIs       99.95% monthly
Audit acceptance              99.99%
Indexed entity search p95     under 2 seconds
Bounded graph expansion p95   under 2 seconds
Streaming ingestion lag       under 60 seconds normally
```

These are engineering targets and must be validated against real workloads.

---

# 35. Scalability strategy

Design target:

```text
Tens of millions of canonical entities
Billions of relationship assertions and events
Petabyte-scale documents and media
Continuous streaming ingestion
Hundreds or thousands of concurrent investigators
```

## Techniques

* Partition lakehouse data by time, jurisdiction, source, and event type.
* Store low-level events outside the primary graph.
* Build investigation-specific graph projections.
* Aggregate repetitive communications.
* Detect and specially handle supernodes.
* Apply path-query limits.
* Precompute selected network metrics.
* Use asynchronous analytics for expensive algorithms.
* Generate vector and graph tiles.
* Cache only authorization-safe projections.
* Rebuild graph/search indexes from canonical event history.
* Place computation close to sovereign data.

---

# 36. Technology recommendation

Aegis is built and taken to production as **one modular Python application plus
proven platform services**. Python 3.12 + FastAPI is the *reference
implementation* of the core domain — not a stepping stone to a JVM rewrite
(ADR-020; the earlier Kotlin/Spring end-state recommendation is withdrawn).
Scale pressure is answered by the trigger-gated upgrades below (details and
triggers in `speckit/plan.md` §2 and `speckit/roadmap.md` Phase 9), never by
speculative adoption.

| Layer | Reference implementation | Trigger-gated upgrade |
| ----- | ------------------------ | --------------------- |
| Web application | React + TypeScript (Phase 4) | — |
| Graph visualization | Cytoscape.js | Sigma.js when WebGL-scale rendering is needed |
| Map | MapLibre GL JS + PostGIS tiles | + deck.gl for large event layers |
| Core domain + APIs | Python 3.12 + FastAPI | — (permanent) |
| Ontology + SDKs | `ontology/aegis.yaml` + generated Pydantic/TypeScript clients | — |
| Analytics | Python (networkx/igraph, Splink) | Spark for batch scale |
| Workflow | DB status columns | Temporal for multi-day approval chains |
| Event streaming | none (batch) | Kafka when a real continuous feed exists |
| OLTP / system of record | PostgreSQL 16 | — (permanent) |
| Spatial | PostGIS | — |
| Graph traversal | recursive CTEs over `edge_projection` | Neo4j when traversal-dominant and CTE p95 > 2 s |
| Search | Postgres FTS + `pg_trgm` (+ ICU) | OpenSearch on multilingual golden-set failure or corpus scale |
| Lakehouse | Parquet + DuckDB | Iceberg + Trino past single-node comfort |
| Cache | in-process | Redis when measured need appears |
| Policy | OpenFGA (ReBAC) + handling-code row filters | + OPA if policy-as-code outgrows relationships |
| Identity | Keycloak (OIDC) | agency IdP via OIDC/SAML on agency deployment |
| Secrets | env + compose secrets | Vault + KMS/HSM on multi-user deployment |
| Containers | Docker Compose | Kubernetes + Argo CD at multi-host / agency cell |
| Observability | structlog JSON + healthchecks | OpenTelemetry + Prometheus/Grafana (Phase 9 baseline) |
| Model registry | git-versioned model configs | MLflow when models multiply |

---

# 37. Clean architecture approach

Do **not** begin with 60 microservices.

Start with:

```text
1 modular domain application
  - cases
  - intelligence reports
  - claims
  - evidence
  - legal authority
  - collaboration

Separate platform services
  - ingestion
  - entity resolution
  - graph projection
  - search indexing
  - analytics
  - policy decision point
  - file/evidence processing
```

Extract bounded contexts only when there is a demonstrated reason:

* Independent scaling.
* Independent security boundary.
* Different availability requirements.
* Separate team ownership.
* Different release cadence.
* Classification separation.

This gives clean architecture without creating distributed-system complexity before the domain is understood.

## Internal layering

```text
Domain
  Entities, value objects, invariants

Application
  Commands, queries, use cases, authorization context

Ports
  Repositories, event publishers, policy interfaces

Adapters
  PostgreSQL, graph, Kafka, OpenSearch, object store, APIs
```

No domain object should depend on Neo4j, Kafka, or OpenSearch classes.

---

# 38. Model and analytic governance

Every production model needs:

* Named owner.
* Approved purpose.
* Training-data record.
* Evaluation dataset.
* Accuracy and calibration.
* Subgroup testing where legally appropriate.
* Known limitations.
* Model card.
* Approval date.
* Expiry/review date.
* Runtime monitoring.
* Drift detection.
* Rollback.
* Incident process.
* Independent audit access.

Models should run in three environments:

```text
Research
Shadow
Production
```

A shadow model produces results for evaluation but cannot affect investigations.

---

# 39. Audit design

Audit events must include:

```text
who
agency
device
session
purpose
case
legal authority
resource
action
timestamp
policy decision
data returned
export destination
reason
result
```

Audit storage should be:

* Append-only.
* Tamper-evident.
* Replicated.
* Accessible to independent auditors.
* Separate from ordinary administrators.
* Retained according to policy.
* Searchable without revealing unrelated protected data.

Administrators should not automatically have access to investigation content.

---

# 40. Implementation roadmap

The authoritative, buildable roadmap lives in **`speckit/roadmap.md`** (phases
P0–P9, gated by exit criteria, not dates), with a full charter per phase in
**`speckit/phases/`**. The P-numbering there supersedes the phase numbers this
section previously used. Summary:

## Milestone I — Governed foundation *(complete)*

* **P0 Governance before code** — spec kit, constitution, roles, grading and
  handling schemes, starter ontology.
* **P1 Claim store, evidence vault, RBAC, audit** — governed Postgres claim
  store, content-addressed evidence, Keycloak/OpenFGA, hash-chained audit,
  ingestion → review queue, projections feeding the existing UI.

## Milestone II — MVP ★

* **P2 Identity, provenance & analyst console** — entity resolution with
  reversible, versioned identity; review-queue and adjudication UI; "Why
  connected?" provenance on every edge; basic entity search; scripted
  end-to-end demo. **At this gate Aegis is a usable product:** land a source →
  extraction suggests → human reviews → governed graph explains itself.

## Milestone III — Ontology platform

* **P3 Ontology v2: semantic & kinetic completion** — interfaces, shared
  property types, functions (declared derivations), action types with
  parameters/submission criteria/side effects, ontology change management,
  generated Python/TypeScript SDKs (§7.8).
* **P4 Investigation workspace & object views** — case-scoped React workspace
  on the generated SDK, entity-360 object views, hypotheses, tasks, timeline
  and as-of reads. Replaces and deletes the legacy explorer; its scope comes
  from analyst needs, never from matching legacy features (ADR-023).

## Milestone IV — Full intelligence domain

* **P5 Events, geospatial & time** — event object types with participants,
  PostGIS geometries with honest precision, map/timeline/graph synchronization,
  movement ingestion.
* **P6 Search, object sets & governed analytics** — multilingual global
  search, object sets as governed reusable queries, explainable network
  analytics as findings, finding→claim promotion, watchlists.

## Milestone V — Trust boundaries & AI

* **P7 Sharing & governance hardening** — compartments and informant
  protection, sealed/expunged states, disclosure packages, break-glass,
  legal-authority objects.
* **P8 Controlled AI & assisted reasoning** — schema-aware extraction,
  translation, summarization, hypothesis assistance — all suggest-only through
  the review queue (§26).

## Milestone VI — Production

* **P9 Production readiness & scale-out** — observability, SLOs, hardening,
  DR drills, performance baselines; plus the trigger-gated upgrades (Neo4j,
  OpenSearch, Kubernetes, Kafka, …). Multi-agency federation and sovereign
  cells (§33) remain here, triggered by a real second agency — not built on
  speculation.

---

# 41. Most important product decisions

The success of Aegis depends less on the graph renderer than on these decisions:

1. **Claims, not mutable “facts,” are the core knowledge primitive.**
2. **Evidence is stored separately from intelligence and inference.**
3. **Every relationship has provenance and time.**
4. **Entity merges are reversible.**
5. **Legal authority and purpose are evaluated at query time.**
6. **The global view is federated, not one unrestricted database.**
7. **Raw event volume stays in the lakehouse; only useful projections enter the graph.**
8. **AI creates suggestions, not facts or operational decisions.**
9. **Every analytic result explains its input path and limitations.**
10. **Conflicting and exculpatory information remains visible.**
11. **Association never equals guilt.**
12. **Independent oversight is a system feature, not merely an organizational promise.**

The resulting platform is best understood as:

```text
Evidence vault
+ intelligence claim system
+ temporal knowledge graph
+ investigation workspace
+ geospatial platform
+ federated multi-agency exchange
+ governed analytics environment
```

That is a realistic foundation for an enterprise intelligence-analysis platform. A plain graph database with people, vehicles, and phone numbers would represent perhaps ten percent of the actual system.

[1]: https://www.unodc.org/documents/organized-crime/Law-Enforcement/Criminal_Intelligence_for_Analysts.pdf?utm_source=chatgpt.com "Criminal Intelligence - Manual for Analysts"
[2]: https://library.college.police.uk/docs/APPref/how-to-complete-5x5x5-form.pdf?utm_source=chatgpt.com "How to Complete a 5x5x5 Form and Relevant Supplements"
[3]: https://www.interpol.int/en/How-we-work/Databases?utm_source=chatgpt.com "Databases"
[4]: https://reference.niem.gov/niem/guidance/dmg/content/model-content/index.html?utm_source=chatgpt.com "Model Content - NIEM.gov"
[5]: https://csrc.nist.gov/glossary/term/chain_of_custody?utm_source=chatgpt.com "chain of custody - Glossary | CSRC"
[6]: https://www.sciencedirect.com/science/article/pii/S0378873321000149?utm_source=chatgpt.com "Using social network analysis to study crime"
[7]: https://nvlpubs.nist.gov/nistpubs/ir/2022/NIST.IR.8387.pdf "Digital Evidence Preservation: Considerations for Evidence Handlers"
[8]: https://www.fatf-gafi.org/en/publications/Fatfrecommendations/Guidance-Beneficial-Ownership-Legal-Persons.html?utm_source=chatgpt.com "Guidance on Beneficial Ownership of Legal Persons"
[9]: https://kafka.apache.org/documentation/?utm_source=chatgpt.com "Introduction | Apache Kafka"
[10]: https://postgis.net/?utm_source=chatgpt.com "PostGIS"
[11]: https://iceberg.apache.org/?utm_source=chatgpt.com "Apache Iceberg - Apache Iceberg™"
[12]: https://arxiv.org/abs/2308.01682?utm_source=chatgpt.com "Evaluating Link Prediction Explanations for Graph Neural Networks"
[13]: https://github.com/maplibre/maplibre-gl-js?utm_source=chatgpt.com "MapLibre GL JS - Interactive vector tile maps in the browser"
[14]: https://le.fbi.gov/file-repository/cjis_security_policy_v6-0_20241227.pdf "Criminal Justice Information Services (CJIS) Security Policy"
[15]: https://csrc.nist.gov/pubs/sp/800/207/final "SP 800-207, Zero Trust Architecture | CSRC"
[16]: https://csrc.nist.gov/pubs/sp/800/162/upd2/final "SP 800-162, Guide to Attribute Based Access Control (ABAC) Definition and Considerations | CSRC"
[17]: https://www.unodc.org/documents/justice-and-prison-reform/cjat_eng/4_Police_Information_Intelligence_Systems.pdf?utm_source=chatgpt.com "Police Information and Intelligence Systems"
[18]: https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX%3A52024DC0419&utm_source=chatgpt.com "EUROPEAN COMMISSION Brussels, 25.9.2024 ... - EUR-Lex"
[19]: https://www.nist.gov/itl/ai-risk-management-framework "AI Risk Management Framework | NIST"
[20]: https://github.com/temporalio/temporal?utm_source=chatgpt.com "temporalio/temporal: Temporal service"
