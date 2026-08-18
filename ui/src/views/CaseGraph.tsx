import { useQuery } from "@tanstack/react-query";

import { expandGraph } from "../api/client";
import { GraphCanvas } from "./GraphCanvas";

/**
 * A case's own graph — the same projection API with one extra filter (T46).
 *
 * `case_id` is threaded into `claim_filters` on the server, not applied to the
 * result, which is what makes "never renders out-of-case data" a property of
 * the query rather than a promise about this component. Two consequences worth
 * knowing while reading it:
 *
 * * an edge appears only if at least one claim **scoped to this case** supports
 *   it; and
 * * its tally counts only those claims, so an edge with one case claim and
 *   three open ones reads "1 source record" here and "4" on the open graph.
 *   Both are true; they answer different questions.
 *
 * Seedless: the bounded overview, capped by the same element budget as any
 * expansion (spec 06 §2.6). A case is small enough that "everything in it" is a
 * reasonable opening view, and the cap is what keeps that from being a
 * promise the data can break.
 */
export function CaseGraph({ caseId }: { caseId: string }) {
  const view = useQuery({
    queryKey: ["case-graph", caseId],
    queryFn: () => expandGraph({ case_id: caseId, max_hops: 1 }),
  });

  if (view.isPending) return <p className="muted">Loading the case graph…</p>;
  if (view.error || !view.data) {
    return (
      <p className="notice" data-testid="case-graph-error" role="alert">
        The case graph could not be loaded.
      </p>
    );
  }
  if (view.data.edges.length === 0 && view.data.nodes.length === 0) {
    return (
      <p className="notice" data-testid="case-graph-empty">
        {/* Absence, stated as absence: this case has recorded no claims you can
            read, which is not the same as the graph being broken. */}
        No claim recorded into this case that you are cleared to see.
      </p>
    );
  }

  return (
    <div className="case-graph" data-testid="case-graph">
      <GraphCanvas view={view.data} />
      {view.data.truncated && (
        <p className="notice" data-testid="case-graph-truncated">
          The element budget was reached — this case has more than is drawn here.
        </p>
      )}
    </div>
  );
}
