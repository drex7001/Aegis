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
