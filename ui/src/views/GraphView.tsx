import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { ApiError, expandGraph, type GraphEdge } from "../api/client";
import { GraphCanvas } from "./GraphCanvas";

/**
 * The governed graph view (T22). Reads `/v1/graph/expand` — authenticated,
 * authorization-filtered and bounded — which is what replaced the anonymous
 * `/api/graph` dump (ADR-026).
 *
 * It opens on the **bounded overview** because entity search lands in T23c.
 * "Search first, expand second" (spec 07 §5) degrades to "overview first,
 * expand second" until then; the bound is the same either way, so the mode
 * without a seed is not a bulk export by another name.
 */
export function GraphView() {
  const [seedId, setSeedId] = useState<string | null>(null);
  const [maxHops, setMaxHops] = useState(1);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  const query = useQuery({
    queryKey: ["graph", seedId, maxHops],
    queryFn: () =>
      expandGraph({
        seed_ids: seedId ? [seedId] : [],
        max_hops: seedId ? maxHops : 0,
      }),
  });

  const onSelectEdge = useCallback(
    (edgeId: string) =>
      setSelectedEdge(query.data?.edges.find((e) => e.edge_id === edgeId) ?? null),
    [query.data],
  );

  return (
    <div className="graph">
      <div className="graph__toolbar">
        <span className="muted" data-testid="graph-mode">
          {seedId ? `Expanding from ${seedId}` : "Bounded overview"}
        </span>
        {seedId && (
          <>
            <label>
              Hops
              <select
                value={maxHops}
                onChange={(event) => setMaxHops(Number(event.target.value))}
              >
                {[1, 2, 3].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" onClick={() => setSeedId(null)}>
              Back to overview
            </button>
          </>
        )}
        <Stamps view={query.data} />
      </div>

      <div className="graph__body">
        {query.isPending && <p className="muted">Loading graph…</p>}
        {query.error && <GraphError error={query.error} />}
        {query.data && (
          <>
            {/* Article IX: every bound the answer hit is stated on the answer,
                never left for the reader to infer from a thin picture. */}
            {query.data.truncated && (
              <p className="notice" data-testid="truncated">
                Bounded result — the graph continues past what is drawn here.
              </p>
            )}
            {query.data.edges.length === 0 && (
              <p className="notice" data-testid="no-edges">
                No connections you are cleared to see.
              </p>
            )}
            <GraphCanvas
              view={query.data}
              onSelectEdge={onSelectEdge}
              onSelectNode={setSeedId}
            />
          </>
        )}
      </div>

      {selectedEdge && (
        <EdgeSupport edge={selectedEdge} onClose={() => setSelectedEdge(null)} />
      )}
    </div>
  );
}

function GraphError({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError ? error.message : "The graph could not be loaded.";
  return (
    <p className="notice notice--error" role="alert" data-testid="graph-error">
      {message}
    </p>
  );
}

function Stamps({ view }: { view: { stamps?: unknown } | undefined }) {
  const stamps = view?.stamps as
    | { stale?: boolean; built_at_revision_id?: number | null }
    | null
    | undefined;
  if (!stamps) return null;
  // A null revision means the projection has never been built. Rendering
  // "revision null" would read as a stamp; saying so plainly tells the reader
  // the canvas is empty because nothing was built, not because nothing exists.
  const label =
    stamps.built_at_revision_id == null
      ? "Projection has not been built — run `aegis projections rebuild`"
      : stamps.stale
        ? "Projection is behind the current identity revision"
        : `Built at identity revision ${stamps.built_at_revision_id}`;
  return (
    <span className="muted" data-testid="stamps">
      {label}
    </span>
  );
}

/**
 * The T22 stub of the provenance panel. It shows the support summary the edge
 * already carries — each claim's three grading dimensions kept apart
 * (Article III) — and nothing it does not: the full "why connected?" panel,
 * with sources and the identity-decision line, is T23c against the route T21
 * already shipped.
 */
function EdgeSupport({ edge, onClose }: { edge: GraphEdge; onClose: () => void }) {
  const support = edge.support as {
    claims?: Array<Record<string, unknown>>;
    record_count?: number;
    contradiction_count?: number;
    corroboration_count?: number;
  };
  return (
    <aside className="panel" data-testid="edge-panel">
      <div className="panel__head">
        <h2>{edge.predicate}</h2>
        <button type="button" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      <p className="muted">
        {edge.segment_from ?? "unbounded"} → {edge.segment_to ?? "unbounded"}
      </p>
      <p>
        {support.record_count ?? 0} source record(s) ·{" "}
        {support.corroboration_count ?? 0} corroborating ·{" "}
        {support.contradiction_count ?? 0} contradicting
      </p>
      <ul className="claims">
        {(support.claims ?? []).map((claim) => (
          <li key={String(claim["claim_id"])}>
            <code>{String(claim["claim_id"])}</code>
            <span className="muted">
              reliability {String(claim["reliability"] ?? "—")} · credibility{" "}
              {String(claim["credibility"])} · verification{" "}
              {String(claim["verification"])}
            </span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
