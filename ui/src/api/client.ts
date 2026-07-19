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
 * RFC 7807 problem detail — what every Aegis error is (spec 06).
 *
 * Deliberately treated as opaque prose rather than parsed for meaning: error
 * bodies are written not to disclose whether a resource exists (spec 06 §6), so
 * code that branched on them would be building the inference channel the
 * convention exists to close.
 */
export interface ProblemDetail {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
}

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
}): Promise<GraphView> {
  return unwrap(await api.POST("/v1/graph/expand", { body }));
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

export interface LandFileFields {
  file: File;
  source_id?: string;
  handling_code?: string;
  source_url?: string;
  collection_policy?: string;
  retention_class?: string;
  authority_ref?: string;
  authority_valid_from?: string;
  authority_valid_to?: string;
  notes?: string;
}

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

export async function getEntity(entityId: string): Promise<EntityDetail> {
  return unwrap(
    await api.GET("/v1/entities/{entity_id}", {
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
export interface StaleRevisionProblem extends ProblemDetail {
  parent_revision_id: number;
  intervening: {
    decision_id: string;
    kind: string;
    decided_by: string;
    note: string;
    result_revision_id: number;
  }[];
}

export function asStaleRevision(error: unknown): StaleRevisionProblem | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const problem = error.problem as StaleRevisionProblem;
  return Array.isArray(problem.intervening) ? problem : null;
}
