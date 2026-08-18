import { useQuery } from "@tanstack/react-query";

import { claimProvenance, whyConnected } from "../../api/client";
import { ClaimCard, ClaimGroups, predicateLabel } from "./ClaimGroup";

/**
 * "Why?" — for a value and for a link (T45).
 *
 * Two questions, two P2 routes, **consumed as-is**:
 *
 * * a **value** asks "where did this come from", answered by
 *   `GET /v1/claims/{id}/provenance` — the excerpt, the source record, the
 *   grading, and both relation directions;
 * * a **link** asks "why are these two connected", answered by
 *   `GET /v1/entities/{a}/why-connected/{b}` — the relation claims *and* the
 *   identity decisions that made the endpoints these endpoints, which is the
 *   step most worth auditing and the one a claim-level view cannot show.
 *
 * T45 adds no endpoint. If the object view needs provenance these routes do not
 * return, that is a P2 regression to fix in those routes rather than a reason
 * for a seventh one (spec 09 §6.6).
 *
 * Rendered through the same `ClaimCard`/`ClaimGroups` as everywhere else, so a
 * drilled-into claim looks like the claim it was drilled into.
 */

export type Drill =
  | { kind: "claim"; claimId: string; label: string }
  | { kind: "link"; from: string; to: string; label: string };

export function ProvenanceDrawer({ drill, onClose }: { drill: Drill; onClose: () => void }) {
  return (
    <aside className="drawer" data-testid="provenance-drawer" aria-label="Provenance">
      <div className="panel__head">
        <h2>{drill.label}</h2>
        <button type="button" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      {drill.kind === "claim" ? (
        <ClaimDrill claimId={drill.claimId} />
      ) : (
        <LinkDrill from={drill.from} to={drill.to} />
      )}
    </aside>
  );
}

function ClaimDrill({ claimId }: { claimId: string }) {
  const query = useQuery({
    queryKey: ["claim-provenance", claimId],
    queryFn: () => claimProvenance(claimId),
  });

  if (query.isPending) return <p className="muted">Loading evidence…</p>;
  if (query.error || !query.data) return <DrillError />;
  return <ClaimCard entry={query.data} compare={false} />;
}

function LinkDrill({ from, to }: { from: string; to: string }) {
  const query = useQuery({
    queryKey: ["why-connected", from, to],
    queryFn: () => whyConnected(from, to),
  });

  if (query.isPending) return <p className="muted">Loading evidence…</p>;
  if (query.error || !query.data) return <DrillError />;
  const data = query.data;

  return (
    <>
      <p className="tally" data-testid="drawer-tally">
        {/* "Source records", never "independent sources" (ADR-030 §3): two
            records can repeat one another, and calling that independence would
            manufacture corroboration out of a copy-paste. */}
        <span>
          <strong>{data.record_count}</strong> source record
          {data.record_count === 1 ? "" : "s"}
        </span>
        <span>{data.corroboration_count} corroborating</span>
        <span className={data.contradiction_count > 0 ? "tally__contested" : undefined}>
          {data.contradiction_count} contradicting
        </span>
      </p>
      {data.truncated && (
        <p className="notice">
          Showing the first {data.claims.length} claims — this link has more
          support than is shown here.
        </p>
      )}
      <ClaimGroups claims={data.claims} />
      {data.identity_line.length > 0 && (
        <section className="provenance__section">
          {/* Why these are *these* entities. A link can exist only because a
              human merged two mentions, and showing the evidence without the
              decision would hide the step most worth auditing. */}
          <h3>Identity decisions behind these endpoints</h3>
          <ol className="line" data-testid="drawer-identity-line">
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
    </>
  );
}

function DrillError() {
  return (
    <p className="notice" data-testid="drawer-error" role="alert">
      {/* 404 here is "absent or not for you", by design. Phrased as absence so
          asking cannot confirm what the status code exists to hide. */}
      No evidence you are cleared to see.
    </p>
  );
}

export { predicateLabel };
