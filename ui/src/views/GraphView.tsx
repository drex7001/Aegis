import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useAuth } from "react-oidc-context";

import { ApiError, expandGraph, rebuildProjections } from "../api/client";
import { EntitySearch } from "./EntitySearch";
import { GraphCanvas } from "./GraphCanvas";
import { ProvenancePanel, type PanelSelection } from "./ProvenancePanel";

/**
 * The governed graph view (T22, completed by T23c). Reads `/v1/graph/expand` —
 * authenticated, authorization-filtered and bounded — which is what replaced
 * the anonymous `/api/graph` dump (ADR-026).
 *
 * T23c gave it the two halves T22 left stubbed: entity search, so spec 07 §5's
 * "search first, expand second" is literally that rather than "overview first";
 * and the real provenance panel behind every edge and node.
 *
 * Selecting a node **opens its claims** rather than immediately re-seeding the
 * canvas. Re-laying out the graph under someone who clicked to read is how a
 * reader loses the thing they were looking at; focusing is offered inside the
 * panel instead, so it stays a decision rather than a side effect.
 */
export function GraphView() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const [seedId, setSeedId] = useState<string | null>(null);
  const [maxHops, setMaxHops] = useState(1);
  const [selection, setSelection] = useState<PanelSelection | null>(null);

  const query = useQuery({
    queryKey: ["graph", seedId, maxHops],
    queryFn: () =>
      expandGraph({
        seed_ids: seedId ? [seedId] : [],
        max_hops: seedId ? maxHops : 0,
      }),
  });
  const roles = (
    auth.user?.profile["realm_access"] as { roles?: string[] } | undefined
  )?.roles ?? [];
  const rebuild = useMutation({
    mutationFn: rebuildProjections,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["graph"] }),
  });

  const onSelectEdge = useCallback(
    (edgeId: string) => {
      const edge = query.data?.edges.find((e) => e.edge_id === edgeId);
      setSelection(edge ? { kind: "edge", edge } : null);
    },
    [query.data],
  );

  const onSelectNode = useCallback(
    (entityId: string) => {
      const node = query.data?.nodes.find((n) => n.entity_id === entityId);
      setSelection({ kind: "node", entityId, label: node?.label ?? entityId });
    },
    [query.data],
  );

  const focus = useCallback((entityId: string) => {
    setSeedId(entityId);
    setSelection(null);
  }, []);

  return (
    <div className="graph">
      <div className="graph__toolbar">
        <EntitySearch onPick={focus} />
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
        {roles.includes("admin") && (
          <button
            type="button"
            className="button"
            data-testid="projection-rebuild"
            disabled={rebuild.isPending}
            onClick={() => rebuild.mutate()}
          >
            {rebuild.isPending ? "Rebuilding…" : "Rebuild projection"}
          </button>
        )}
        {rebuild.data && (
          <span className="muted" data-testid="projection-rebuild-result">
            Rebuilt {rebuild.data.edges} edges / {rebuild.data.segments} segments at
            revision {rebuild.data.built_at_revision_id}.
          </span>
        )}
        {rebuild.error && (
          <span className="notice notice--error" role="alert">
            {rebuild.error instanceof ApiError
              ? rebuild.error.message
              : "The projection could not be rebuilt."}
          </span>
        )}
      </div>

      {/* Body and panel side by side. `.graph` is a column, so a panel that is
          a direct sibling of the body competes with it for height and a tall
          one collapses the canvas it exists to annotate. */}
      <div className="graph__workspace">
        <div className="graph__body">
          {query.isPending && <p className="muted">Loading graph…</p>}
          {query.error && <GraphError error={query.error} />}
          {query.data && (
            <>
              {/* Article IX: every bound the answer hit is stated on the
                  answer, never left for the reader to infer from a thin
                  picture. */}
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
                onSelectNode={onSelectNode}
              />
            </>
          )}
        </div>

        {selection && (
          <ProvenancePanel
            selection={selection}
            onClose={() => setSelection(null)}
            onFocus={focus}
          />
        )}
      </div>
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
