import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  ApiError,
  getEntity,
  whyConnected,
  type GraphEdge,
} from "../api/client";
import { entityPath } from "../routing";
import { ClaimGroups, PredicateGroup } from "./claims/ClaimGroup";

/**
 * The provenance panel (T23c) — the answer to GOAL.md §18, replacing T22's
 * summary stub.
 *
 * Two selections reach the same question from different sides. An **edge**
 * asks "why are these two connected?" and is answered by `whyConnected`: the
 * relation claims, their sources, and the identity decisions that made the
 * endpoints these endpoints. A **node** asks "what is claimed about this
 * one?" and is answered by `getEntity`: its property claims, grouped by
 * predicate.
 *
 * Grouping is what puts two disagreeing claims about one property next to each
 * other; the `contradicts` badge is what names the disagreement rather than
 * leaving the reader to notice unaided. Corroboration is shown alongside and
 * never subtracted from it — a claim that is both corroborated and contradicted
 * is *contested*, not "net supported" (Article VIII).
 *
 * Nothing here computes a score. The three grading dimensions are rendered
 * apart because they answer different questions (Article III), and a panel that
 * averaged them would destroy the only information it exists to carry.
 */

export type PanelSelection =
  | { kind: "edge"; edge: GraphEdge }
  | { kind: "node"; entityId: string; label: string };

export interface ProvenancePanelProps {
  selection: PanelSelection;
  onClose: () => void;
  /** Re-seed the canvas on this entity — offered, never done on selection. */
  onFocus: (entityId: string) => void;
}

export function ProvenancePanel({ selection, onClose, onFocus }: ProvenancePanelProps) {
  return (
    <aside className="panel provenance" data-testid="provenance-panel">
      <div className="panel__head">
        <h2>
          {selection.kind === "edge" ? selection.edge.predicate : selection.label}
        </h2>
        <button type="button" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      {selection.kind === "edge" ? (
        <EdgeProvenance edge={selection.edge} onFocus={onFocus} />
      ) : (
        <NodeProvenance entityId={selection.entityId} onFocus={onFocus} />
      )}
    </aside>
  );
}

/* ── edge: why are these two connected? ─────────────────────────────────── */

function EdgeProvenance({
  edge,
  onFocus,
}: {
  edge: GraphEdge;
  onFocus: (entityId: string) => void;
}) {
  const query = useQuery({
    queryKey: ["why-connected", edge.subject_id, edge.object_id],
    queryFn: () => whyConnected(edge.subject_id, edge.object_id),
  });

  if (query.isPending) return <p className="muted">Loading evidence…</p>;
  if (query.error) return <PanelError error={query.error} />;
  const data = query.data;
  if (!data) return null;

  return (
    <>
      <p className="muted provenance__span">
        {edge.segment_from ?? "unbounded"} → {edge.segment_to ?? "unbounded"}
      </p>
      <Tally
        records={data.record_count}
        contradictions={data.contradiction_count}
        corroborations={data.corroboration_count}
      />
      <Resolved requested={edge.subject_id} actual={data.resolved_subject_id} />
      <Resolved requested={edge.object_id} actual={data.resolved_object_id} />
      {data.truncated && (
        <p className="notice" data-testid="provenance-truncated">
          Showing the first {data.claims.length} claims — this edge has more
          support than is drawn here.
        </p>
      )}

      <ClaimGroups claims={data.claims} />

      {data.identity_line.length > 0 && (
        <section className="provenance__section">
          {/* Why these are *these* entities. An edge can exist only because a
              human merged two mentions, and a panel that showed the evidence
              without the decision would hide the step most worth auditing. */}
          <h3>Identity decisions behind these endpoints</h3>
          <ol className="line" data-testid="identity-line">
            {data.identity_line.map((decision) => (
              <li key={decision.decision_id}>
                <span className="chip chip--kind">{decision.kind}</span>{" "}
                <strong>{decision.decided_by}</strong>
                <span className="muted"> · revision {decision.result_revision_id}</span>
                {decision.decision_note && (
                  <p className="line__note">{decision.decision_note}</p>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="provenance__actions">
        <button type="button" onClick={() => onFocus(edge.subject_id)}>
          Focus {edge.subject_id}
        </button>
        <button type="button" onClick={() => onFocus(edge.object_id)}>
          Focus {edge.object_id}
        </button>
      </div>
    </>
  );
}

/* ── node: what is claimed about this one? ──────────────────────────────── */

function NodeProvenance({
  entityId,
  onFocus,
}: {
  entityId: string;
  onFocus: (entityId: string) => void;
}) {
  const query = useQuery({
    queryKey: ["entity", entityId],
    queryFn: () => getEntity(entityId),
  });

  if (query.isPending) return <p className="muted">Loading claims…</p>;
  if (query.error) return <PanelError error={query.error} />;
  const data = query.data;
  if (!data) return null;

  const groups = Object.entries(data.claims_by_predicate);
  return (
    <>
      <p className="muted">
        {data.entity.entity_type} · <code>{data.entity.entity_id}</code>
      </p>
      <Resolved requested={entityId} actual={data.resolved_entity_id} />
      {data.truncated && (
        <p className="notice" data-testid="provenance-truncated">
          Showing the first claims only — more is recorded than is shown here.
        </p>
      )}
      {groups.length === 0 && (
        <p className="notice" data-testid="no-claims">
          No claims you are cleared to see.
        </p>
      )}
      {groups.map(([predicate, claims]) => (
        <PredicateGroup key={predicate} predicate={predicate} claims={claims} />
      ))}
      <div className="provenance__actions">
        <button type="button" onClick={() => onFocus(entityId)}>
          Focus the graph here
        </button>
        {/*
         * The panel answers "what is claimed about this one" inside the canvas;
         * the object view answers the same question with its links, sources and
         * cases beside it. A link rather than a replacement — leaving the graph
         * should be the reader's decision, not a side effect of clicking a node.
         */}
        <Link to={entityPath(data.resolved_entity_id)} data-testid="open-object-view">
          Open the full record
        </Link>
      </div>
    </>
  );
}

function Tally({
  records,
  contradictions,
  corroborations,
}: {
  records: number;
  contradictions: number;
  corroborations: number;
}) {
  return (
    <p className="tally" data-testid="tally">
      {/* "Source records", never "independent sources" (ADR-030 §3): two
          records can repeat one another, and calling that independence would
          manufacture corroboration out of a copy-paste. */}
      <span>
        <strong>{records}</strong> source record{records === 1 ? "" : "s"}
      </span>
      <span>
        <strong>{corroborations}</strong> corroborating
      </span>
      <span className={contradictions > 0 ? "tally__contested" : undefined}>
        <strong>{contradictions}</strong> contradicting
      </span>
    </p>
  );
}

/**
 * Say so when a followed id has been merged away.
 *
 * Answering about the surviving entity without mentioning it would be quietly
 * answering a different question than the one asked (Article V: identity moves
 * are reversible and visible, never silent).
 */
function Resolved({ requested, actual }: { requested: string; actual: string }) {
  if (requested === actual) return null;
  return (
    <p className="notice" data-testid="resolved-elsewhere">
      <code>{requested}</code> has been merged into <code>{actual}</code> — showing
      the surviving entity.
    </p>
  );
}

function PanelError({ error }: { error: unknown }) {
  // 404 is both "absent" and "not yours to see" by design, so it is phrased as
  // absence: a permission-shaped message would confirm the thing exists.
  const message =
    error instanceof ApiError && error.isAbsent
      ? "Nothing to show here."
      : error instanceof ApiError
        ? error.message
        : "The evidence could not be loaded.";
  return (
    <p className="notice notice--error" role="alert" data-testid="provenance-error">
      {message}
    </p>
  );
}

