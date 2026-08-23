/**
 * The route table. History belongs to `react-router` from T42 onward.
 *
 * P2 routed on the History API directly, and said why: two views did not need a
 * router, but they did need real URLs. The reason to wait was that the OIDC
 * callback finished by rewriting the URL with `history.replaceState`, so
 * adopting a router meant re-testing the whole sign-in round trip — worth doing
 * once, when the view count justified it.
 *
 * P4 is that point: `/types/:name` takes a parameter, and the phase adds cases
 * and object views behind more of them. The callback no longer touches
 * `history` at all — `auth/SigninCallback.tsx` navigates through the router
 * instead, which is what removes the hazard rather than working around it.
 *
 * What stays here is the **table**: every path in one place, with builders, so
 * a link is never a hand-written string and a renamed route is a type error.
 */

export const ROUTES = {
  graph: "/graph",
  /** The map (spec 10 §9). Time window and selection live in its query. */
  map: "/map",
  /** The timeline (spec 10 §11). Shares `from`/`to` with the map. */
  timeline: "/timeline",
  /** Findings: metrics that recorded an answer, each with its caveat. */
  findings: "/findings",
  /** Object sets: build, compose, share, evaluate (spec 12). */
  sets: "/sets",
  sources: "/sources",
  review: "/review",
  /** The caller's own cases, and one case (spec 09 §2.4). */
  cases: "/cases",
  case: "/cases/:caseId",
  /** One hypothesis, with both sides and its history (spec 09 §3.5). */
  hypothesis: "/hypotheses/:hypothesisId",
  /** The entity-360: one generic screen for any entity (spec 09 §6.4). */
  entity: "/entities/:entityId",
  /** One generic screen per declared object type (spec 09 §6). */
  objectType: "/types/:name",
  /** …and per interface, which is a shape over those types (spec 08 §4). */
  interface: "/interfaces/:name",
  signinCallback: "/auth/callback",
} as const;

export type RouteName = keyof typeof ROUTES;

/** `/types/person`. The only place a parameterized path is assembled. */
export function objectTypePath(name: string): string {
  return `/types/${encodeURIComponent(name)}`;
}

export function interfacePath(name: string): string {
  return `/interfaces/${encodeURIComponent(name)}`;
}

export function entityPath(entityId: string): string {
  return `/entities/${encodeURIComponent(entityId)}`;
}

export function casePath(caseId: string): string {
  return `/cases/${encodeURIComponent(caseId)}`;
}

export function hypothesisPath(hypothesisId: string): string {
  return `/hypotheses/${encodeURIComponent(hypothesisId)}`;
}

/**
 * Where an interrupted visit resumes.
 *
 * `/auth/callback` is never a destination: returning to it would re-enter the
 * callback with no code in the URL, which signs in again and returns to
 * `/auth/callback`. That loop is the reason this function exists rather than a
 * bare `?? "/"`.
 */
export function safeReturnTo(path: string | undefined | null): string {
  if (!path || path.startsWith(ROUTES.signinCallback)) return ROUTES.graph;
  return path;
}
