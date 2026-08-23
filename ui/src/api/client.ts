import createClient, { type Middleware } from "openapi-fetch";

import { userManager } from "../auth/config";
import type { components, paths } from "./schema";

/**
 * The typed API client, generated from the committed OpenAPI document
 * (ADR-032 §2). Every path, body and response shape below is checked against
 * `openapi.json`; a route that changes shape without the document being
 * re-exported fails `npm run typecheck`, and the contract test fails if the
 * document and the routes disagree.
 *
 * Same origin by default — FastAPI serves this bundle — so no base URL is
 * configured and no CORS policy needs to exist.
 */

export type GraphView = components["schemas"]["GraphViewOut"];
export type GraphEdge = components["schemas"]["GraphEdgeOut"];
export type GraphNode = components["schemas"]["GraphNodeOut"];
export type ProjectionStamps = components["schemas"]["ProjectionStampsOut"];

export type LandingResult = components["schemas"]["LandingOut"];
export type SourceRecord = components["schemas"]["SourceRecordOut"];
export type SourceRecordPage = components["schemas"]["SourceRecordPageOut"];
export type SourceSummary = components["schemas"]["SourceOut"];
export type SourcePage = components["schemas"]["SourcePageOut"];
export type Derivative = components["schemas"]["DerivativeOut"];
export type ExtractionResult = components["schemas"]["ExtractionOut"];
export type LandingOutcome = LandingResult["outcome"];
export type Suggestion = components["schemas"]["SuggestionOut"];
export type SuggestionPage = components["schemas"]["SuggestionPageOut"];
export type IdentityCandidate = components["schemas"]["CandidateOut"];
export type CandidatePage = components["schemas"]["CandidateListOut"];
export type CandidateSide = components["schemas"]["CandidateMentionOut"];
export type IdentityDecisionResult = components["schemas"]["DecisionOut"];
export type BatchConfirmResult = components["schemas"]["BatchConfirmOut"];
/**
 * Typed per mode by the server's discriminated union, so a reject that forgets
 * its evidence basis is a compile error here rather than a 422 at the desk.
 */
export type DecisionRequest =
  | components["schemas"]["ConfirmMatchIn"]
  | components["schemas"]["RejectMatchIn"]
  | components["schemas"]["SplitEntityIn"]
  | components["schemas"]["MarkUnresolvedIn"];
export type OntologyVocabulary = components["schemas"]["OntologyVocabularyOut"];

export type WhyConnected = components["schemas"]["WhyConnectedOut"];
export type EntityDetail = components["schemas"]["EntityDetail"];
export type EntityCase = components["schemas"]["EntityCaseOut"];
/**
 * One claim with its evidence — the unit both provenance panels render. The
 * three grading dimensions arrive apart (Article III) and both relation
 * directions survive, so the UI cannot accidentally net them into a score.
 */
export type ClaimProvenance = components["schemas"]["ClaimProvenanceOut"];
export type SearchResults = components["schemas"]["SearchResultsOut"];
export type EntityHit = components["schemas"]["EntityHitOut"];
export type ProjectionRebuild = components["schemas"]["ProjectionRebuildOut"];

/**
 * RFC 7807 problem detail — what every Aegis error is (spec 06 §7.2).
 *
 * Generated since T36. It was hand-written here for as long as the envelope was
 * real at runtime but absent from the OpenAPI document; now every operation
 * declares it, so the shape comes from the server rather than from a copy kept
 * in step by hand.
 *
 * Deliberately treated as opaque prose rather than parsed for meaning: error
 * bodies are written not to disclose whether a resource exists (spec 06 §6), so
 * code that branched on them would be building the inference channel the
 * convention exists to close.
 */
export type ProblemDetail = components["schemas"]["ProblemDetail"];

export class ApiError extends Error {
  readonly status: number;
  readonly problem: ProblemDetail;

  constructor(status: number, problem: ProblemDetail) {
    super(problem.detail ?? problem.title ?? `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }

  /**
   * 404 is both "absent" and "you may not see this" — by design, so that
   * asking cannot confirm existence (spec 06 default 4). The UI must therefore
   * phrase it as absence and never as a permission prompt, or it would leak
   * exactly what the status code was chosen to hide.
   */
  get isAbsent(): boolean {
    return this.status === 404;
  }
}

/**
 * The token is fetched from the `UserManager` at request time, not held here.
 *
 * Asking per request is what makes the timing correct — the first query fires
 * from a child effect, before any parent effect could have handed a token down
 * — and it also means a silently renewed token is used immediately rather than
 * after the next React render. The user store is in memory (auth/config.ts), so
 * this resolves without touching web storage or the network.
 */
const bearer: Middleware = {
  async onRequest({ request }) {
    const user = await userManager.getUser();
    if (user?.access_token) {
      request.headers.set("Authorization", `Bearer ${user.access_token}`);
    }
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: "/" });
api.use(bearer);

/** Unwrap an openapi-fetch result, turning a problem body into an ApiError. */
export function unwrap<T>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): T {
  if (result.error !== undefined || !result.response.ok) {
    const problem = (result.error ?? {}) as ProblemDetail;
    throw new ApiError(result.response.status, problem);
  }
  return result.data as T;
}

export async function expandGraph(body: {
  seed_ids?: string[];
  max_hops?: number;
  max_elements?: number;
  categories?: string[];
  /** Narrow to one case's own evidence (T46) — a claim filter, not a display one. */
  case_id?: string;
  /**
   * The **event-time** window the map and timeline share (T62). Distinct from
   * `valid_from`/`valid_to`, which is when a relationship was true: one control
   * answering both would mean different things on different surfaces.
   */
  event_from?: string;
  event_to?: string;
  as_of?: string;
  as_of_revision?: number;
}): Promise<GraphView> {
  return unwrap(await api.POST("/v1/graph/expand", { body }));
}

/* ── geo (T59) ─────────────────────────────────────────────────────────── */

/**
 * A GeoJSON `FeatureCollection` with two foreign members (`next_cursor`,
 * `stamp`), which RFC 7946 §6.1 permits.
 *
 * The feature shapes are **generated**, not declared here. The first cut of
 * this file wrote them by hand — a GeoJSON Feature's `properties` is
 * open-ended by the standard, so the server had left them untyped — and the
 * repository sweep refused it, correctly: an undescribed shape is a gap in the
 * OpenAPI document, not a licence to keep a second copy (ADR-039).
 */
export type FeatureCollection = components["schemas"]["FeatureCollectionOut"];

export type GeoFeature = components["schemas"]["GeoFeatureOut"];
export type PlaceProperties = components["schemas"]["PlaceFeaturePropertiesOut"];
export type EventProperties = components["schemas"]["EventFeaturePropertiesOut"];

export async function geoLocations(params: {
  bbox?: string;
  limit?: number;
  cursor?: string;
  asOf?: string;
  asOfRevision?: number;
} = {}): Promise<FeatureCollection> {
  return unwrap(await api.GET("/v1/geo/locations", { params: { query: params } }));
}

export async function geoEvents(params: {
  bbox?: string;
  from?: string;
  to?: string;
  eventType?: string;
  limit?: number;
  cursor?: string;
  asOf?: string;
  asOfRevision?: number;
} = {}): Promise<FeatureCollection> {
  return unwrap(await api.GET("/v1/geo/events", { params: { query: params } }));
}

export type TimelineItem = components["schemas"]["TimelineItemOut"];
export type TimelinePage = components["schemas"]["TimelinePageOut"];

export async function getTimeline(params: {
  entityId?: string;
  caseId?: string;
  from?: string;
  to?: string;
  limit?: number;
  cursor?: string;
  asOf?: string;
  asOfRevision?: number;
} = {}): Promise<TimelinePage> {
  return unwrap(await api.GET("/v1/timeline", { params: { query: params } }));
}

/* ── ingestion (T23a) ──────────────────────────────────────────────────── */

/**
 * Multipart serializer for the file-landing route.
 *
 * Empty strings are dropped rather than sent: an untouched optional input
 * would otherwise land as `source_url: ""`, recording "collected from nowhere"
 * as if the operator had asserted it. Absent and empty are different claims
 * about provenance, and only one of them is true here.
 */
function multipart(body: Record<string, unknown>): FormData {
  const form = new FormData();
  for (const [key, value] of Object.entries(body)) {
    if (value === undefined || value === null || value === "") continue;
    form.append(key, value as string | Blob);
  }
  return form;
}

/**
 * The multipart landing form, generated from the route's own body model.
 *
 * `file` is narrowed to `File` because the document says `string` (binary), the
 * only shape OpenAPI has for an upload — the browser needs the real thing.
 */
export type LandFileFields = Omit<components["schemas"]["Body_landFile"], "file"> & {
  file: File;
};

export async function landFile(fields: LandFileFields): Promise<LandingResult> {
  return unwrap(
    await api.POST("/v1/ingest/file", {
      // `openapi-typescript` types a `format: binary` field as `string`; the
      // request is multipart, so the value has to be the File itself. The cast
      // is confined to this line rather than loosening the operation's type.
      body: fields as unknown as components["schemas"]["Body_landFile"],
      bodySerializer: multipart,
    }),
  );
}

export async function landText(
  body: components["schemas"]["LandTextIn"],
): Promise<LandingResult> {
  return unwrap(await api.POST("/v1/ingest/text", { body }));
}

export async function listSourceRecords(params?: {
  status?: string;
  source_id?: string;
  cursor?: string;
  limit?: number;
}): Promise<SourceRecordPage> {
  return unwrap(await api.GET("/v1/source-records", { params: { query: params } }));
}

export async function listSources(params?: {
  cursor?: string;
  limit?: number;
}): Promise<SourcePage> {
  return unwrap(await api.GET("/v1/sources", { params: { query: params } }));
}

export async function createSource(
  body: components["schemas"]["SourceIn"],
): Promise<SourceSummary> {
  return unwrap(await api.POST("/v1/sources", { body }));
}

export async function listDerivatives(recordId: string): Promise<Derivative[]> {
  return unwrap(
    await api.GET("/v1/source-records/{record_id}/derivatives", {
      params: { path: { record_id: recordId } },
    }),
  );
}

export async function extractRecord(
  recordId: string,
  body: components["schemas"]["ExtractIn"],
): Promise<ExtractionResult> {
  return unwrap(
    await api.POST("/v1/source-records/{record_id}/extract", {
      params: { path: { record_id: recordId } },
      body,
    }),
  );
}

export async function listSuggestions(params: {
  record?: string;
  status?: string;
  kind?: string;
  producer?: string;
  cursor?: string;
  limit?: number;
}): Promise<SuggestionPage> {
  return unwrap(await api.GET("/v1/review-queue", { params: { query: params } }));
}

/**
 * Handling codes and source types come from the server, never from a constant
 * in this bundle: the ontology is the single domain artifact (Article XI), and
 * a hard-coded picker is a second one that stays wrong silently.
 */
export async function getVocabulary(): Promise<OntologyVocabulary> {
  return unwrap(await api.GET("/v1/ontology/vocabulary", {}));
}

export async function releaseRecord(recordId: string): Promise<SourceRecord> {
  return unwrap(
    await api.POST("/v1/source-records/{record_id}/release", {
      params: { path: { record_id: recordId } },
    }),
  );
}

export async function acceptSuggestion(
  suggestionId: string,
  body: { edits?: Record<string, unknown>; note?: string },
): Promise<Suggestion> {
  return unwrap(
    await api.POST("/v1/review-queue/{suggestion_id}/accept", {
      params: { path: { suggestion_id: suggestionId } },
      body,
    }),
  );
}

export async function rejectSuggestion(
  suggestionId: string,
  reason: string,
): Promise<Suggestion> {
  return unwrap(
    await api.POST("/v1/review-queue/{suggestion_id}/reject", {
      params: { path: { suggestion_id: suggestionId } },
      body: { reason },
    }),
  );
}

export async function listIdentityCandidates(params: {
  disposition?: string;
  producer?: string;
  cursor?: string;
  limit?: number;
}): Promise<CandidatePage> {
  return unwrap(await api.GET("/v1/identity/candidates", { params: { query: params } }));
}

export async function recordIdentityDecision(
  body: DecisionRequest,
): Promise<IdentityDecisionResult> {
  return unwrap(await api.POST("/v1/identity/decisions", { body }));
}

export async function batchConfirmCandidates(body: {
  candidate_ids: string[];
  parent_revision_id: number;
  note: string;
}): Promise<BatchConfirmResult> {
  return unwrap(await api.POST("/v1/identity/candidates/batch-confirm", { body }));
}

/* ── provenance & search (T23c) ────────────────────────────────────────── */

export async function whyConnected(
  entityId: string,
  otherId: string,
): Promise<WhyConnected> {
  return unwrap(
    await api.GET("/v1/entities/{entity_id}/why-connected/{other_id}", {
      params: { path: { entity_id: entityId, other_id: otherId } },
    }),
  );
}

/**
 * One claim's evidence (spec 06 §2.1) — the generic drill-down.
 *
 * Any value a screen renders from a claim can reach its evidence through this,
 * which is what makes provenance a property of the platform rather than a
 * feature of the graph. Consumed as-is from P2: T45 adds no endpoint.
 */
export async function claimProvenance(claimId: string): Promise<ClaimProvenance> {
  return unwrap(
    await api.GET("/v1/claims/{claim_id}/provenance", {
      params: { path: { claim_id: claimId } },
    }),
  );
}

/**
 * One entity's claims.
 *
 * `asOf` is a **claim-recording** snapshot: what had been recorded and not
 * retracted then. `asOfRevision` pins the identity revision entity arguments
 * resolve through — without it, a historical question is answered with today's
 * identity, which is why the response always echoes the revision it used
 * (spec 06 §3, B-11).
 */
export async function getEntity(
  entityId: string,
  options?: { asOf?: string; asOfRevision?: number },
): Promise<EntityDetail> {
  return unwrap(
    await api.GET("/v1/entities/{entity_id}", {
      params: {
        path: { entity_id: entityId },
        query: {
          asOf: options?.asOf,
          asOfRevision: options?.asOfRevision,
        },
      },
    }),
  );
}

/**
 * Cases this entity appears in — only the ones the caller may know about.
 *
 * An empty array means "none you can see", and deliberately cannot be told
 * apart from "none at all": the route returns the same 200 and the same body
 * for both (H-18, spec 09 §6.5). Any UI that rendered "no cases" differently
 * from "no visible cases" would put the leak back.
 */
export async function listEntityCases(entityId: string): Promise<EntityCase[]> {
  return unwrap(
    await api.GET("/v1/entities/{entity_id}/cases", {
      params: { path: { entity_id: entityId } },
    }),
  );
}

export async function searchEntities(
  q: string,
  limit = 10,
  cursor?: string,
): Promise<SearchResults> {
  return unwrap(
    await api.GET("/v1/search/entities", { params: { query: { q, limit, cursor } } }),
  );
}

/* ── cases (T46, over the routes T43 landed) ───────────────────────────── */

export type Case = components["schemas"]["CaseOut"];
export type CasePage = components["schemas"]["CasePageOut"];
export type CaseMember = components["schemas"]["CaseMemberOut"];
export type CaseReference = components["schemas"]["CaseReferenceOut"];

/**
 * The caller's own cases.
 *
 * An empty list means "none you are a member of". It carries no total, by
 * design — a count over an authorization-filtered collection is an existence
 * leak (spec 06 §4 default 4) — so nothing here may render one.
 */
export async function listCases(params?: {
  cursor?: string;
  limit?: number;
}): Promise<CasePage> {
  return unwrap(await api.GET("/v1/cases", { params: { query: params } }));
}

export async function openCase(
  body: components["schemas"]["CaseIn"],
  purpose: string,
): Promise<Case> {
  // `purpose` is a required query parameter on this route, not a body field:
  // it is captured by the authorization gate and audited with the allow
  // (GOAL.md §12.4), which happens before the handler sees a body.
  return unwrap(await api.POST("/v1/cases", { params: { query: { purpose } }, body }));
}

export async function getCase(caseId: string): Promise<Case> {
  return unwrap(
    await api.GET("/v1/cases/{case_id}", { params: { path: { case_id: caseId } } }),
  );
}

export async function closeCase(caseId: string, reason: string): Promise<Case> {
  return unwrap(
    await api.POST("/v1/cases/{case_id}/close", {
      params: { path: { case_id: caseId } },
      body: { reason },
    }),
  );
}

export async function listCaseMembers(caseId: string): Promise<CaseMember[]> {
  return unwrap(
    await api.GET("/v1/cases/{case_id}/members", {
      params: { path: { case_id: caseId } },
    }),
  );
}

export async function addCaseMember(
  caseId: string,
  body: components["schemas"]["CaseMemberIn"],
): Promise<unknown> {
  return unwrap(
    await api.POST("/v1/cases/{case_id}/members", {
      params: { path: { case_id: caseId } },
      body,
    }),
  );
}

export async function listCaseReferences(caseId: string): Promise<CaseReference[]> {
  return unwrap(
    await api.GET("/v1/cases/{case_id}/references", {
      params: { path: { case_id: caseId } },
    }),
  );
}

export async function linkCaseReference(
  caseId: string,
  body: components["schemas"]["CaseReferenceIn"],
): Promise<CaseReference> {
  return unwrap(
    await api.POST("/v1/cases/{case_id}/references", {
      params: { path: { case_id: caseId } },
      body,
    }),
  );
}

export async function unlinkCaseReference(
  caseId: string,
  targetType: string,
  targetId: string,
  reason: string,
): Promise<CaseReference> {
  return unwrap(
    await api.DELETE("/v1/cases/{case_id}/references/{target_type}/{target_id}", {
      params: {
        path: { case_id: caseId, target_type: targetType, target_id: targetId },
        query: { reason },
      },
    }),
  );
}

/* ── hypotheses and tasks (T47/T48, over the routes T43 landed) ─────────── */

export type Hypothesis = components["schemas"]["HypothesisOut"];
export type HypothesisSummary = components["schemas"]["HypothesisSummaryOut"];
export type HypothesisRevision = components["schemas"]["HypothesisRevisionOut"];
export type HypothesisClaim = components["schemas"]["HypothesisClaimOut"];
export type Task = components["schemas"]["TaskOut"];

export async function openHypothesis(
  body: components["schemas"]["HypothesisIn"],
): Promise<HypothesisRevision> {
  return unwrap(await api.POST("/v1/hypotheses", { body }));
}

/** Always case-scoped: there is no global hypothesis list (spec 09 §3.5). */
export async function listHypotheses(caseId: string): Promise<HypothesisSummary[]> {
  const page = unwrap(
    await api.GET("/v1/hypotheses", { params: { query: { case: caseId } } }),
  );
  return page.items;
}

export async function getHypothesis(hypothesisId: string): Promise<Hypothesis> {
  return unwrap(
    await api.GET("/v1/hypotheses/{hypothesis_id}", {
      params: { path: { hypothesis_id: hypothesisId } },
    }),
  );
}

export async function reviseHypothesis(
  hypothesisId: string,
  body: components["schemas"]["HypothesisRevisionIn"],
): Promise<HypothesisRevision> {
  return unwrap(
    await api.POST("/v1/hypotheses/{hypothesis_id}/revisions", {
      params: { path: { hypothesis_id: hypothesisId } },
      body,
    }),
  );
}

export async function linkHypothesisClaim(
  hypothesisId: string,
  body: components["schemas"]["HypothesisClaimIn"],
): Promise<HypothesisClaim> {
  return unwrap(
    await api.POST("/v1/hypotheses/{hypothesis_id}/claims", {
      params: { path: { hypothesis_id: hypothesisId } },
      body,
    }),
  );
}

export async function unlinkHypothesisClaim(
  hypothesisId: string,
  claimId: string,
  stance: string,
  reason: string,
): Promise<HypothesisClaim> {
  return unwrap(
    await api.DELETE("/v1/hypotheses/{hypothesis_id}/claims/{claim_id}/{stance}", {
      params: {
        path: { hypothesis_id: hypothesisId, claim_id: claimId, stance },
        query: { reason },
      },
    }),
  );
}

export async function openTask(
  body: components["schemas"]["TaskIn"],
): Promise<Task> {
  return unwrap(await api.POST("/v1/tasks", { body }));
}

export async function listTasks(caseId: string): Promise<Task[]> {
  const page = unwrap(await api.GET("/v1/tasks", { params: { query: { case: caseId } } }));
  return page.items;
}

export async function updateTask(
  taskId: string,
  body: components["schemas"]["TaskUpdateIn"],
): Promise<Task> {
  return unwrap(
    await api.POST("/v1/tasks/{task_id}", {
      params: { path: { task_id: taskId } },
      body,
    }),
  );
}

export async function rebuildProjections(): Promise<ProjectionRebuild> {
  return unwrap(await api.POST("/v1/projections/rebuild", {}));
}

/**
 * The one error body this client reads for meaning.
 *
 * `ProblemDetail` is otherwise treated as opaque prose, because error bodies are
 * written so that asking cannot confirm a resource exists. A stale-revision 409
 * is not that channel: it reports decisions from the identity ledger the caller
 * has already been authorized to read, and spec 05 §2 requires the analyst be
 * re-presented with them. Showing a bare "conflict" instead is what teaches
 * people to retry until it sticks.
 */
export type StaleRevisionProblem = components["schemas"]["StaleRevisionProblem"];
export type InterveningDecision = components["schemas"]["InterveningDecision"];

export function asStaleRevision(error: unknown): StaleRevisionProblem | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const problem = error.problem as StaleRevisionProblem;
  return Array.isArray(problem.intervening) ? problem : null;
}
