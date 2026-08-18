import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError, listHypotheses, openHypothesis } from "../api/client";
import { hypothesisPath } from "../routing";

/**
 * A case's hypotheses, and the form that opens one (T47).
 *
 * The missing-information note is a **required field with its own label**, not
 * an optional "notes" box. GOAL.md §18 asks a hypothesis to state what would
 * change it, and the server refuses both an absent note and a blank one — the
 * second by the `required_text_is_substantive` criterion, which exists because
 * `required: true` accepts a string of spaces.
 *
 * That refusal is surfaced verbatim rather than translated. A generic "please
 * fill in all fields" would hide which rule fired, and this rule is worth the
 * analyst reading.
 */
export function CaseHypotheses({ caseId }: { caseId: string }) {
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const hypotheses = useQuery({
    queryKey: ["hypotheses", caseId],
    queryFn: () => listHypotheses(caseId),
  });

  const open = useMutation({
    mutationFn: (body: { statement: string; missing_info: string }) =>
      openHypothesis({ case_id: caseId, ...body }),
    onSuccess: () => {
      setError(null);
      void client.invalidateQueries({ queryKey: ["hypotheses", caseId] });
    },
    onError: (err: unknown) =>
      setError(
        err instanceof ApiError ? err.message : "Could not open the hypothesis.",
      ),
  });

  return (
    <>
      <h2>Hypotheses</h2>
      {(hypotheses.data ?? []).length === 0 ? (
        <p className="notice" data-testid="case-hypotheses-empty">
          No hypothesis recorded in this case.
        </p>
      ) : (
        <ul data-testid="case-hypotheses">
          {(hypotheses.data ?? []).map((entry) => (
            <li key={entry.hypothesis_id}>
              <Link to={hypothesisPath(entry.hypothesis_id)}>{entry.statement}</Link>{" "}
              <span className="chip chip--kind">{entry.status}</span>
              <span className="muted"> · v{entry.version}</span>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p className="notice notice--error" role="alert" data-testid="hypothesis-open-error">
          {error}
        </p>
      )}

      <form
        className="case-form"
        data-testid="hypothesis-form"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          open.mutate({
            statement: String(form.get("statement") ?? ""),
            missing_info: String(form.get("missing_info") ?? ""),
          });
        }}
      >
        <label>
          <span>Statement</span>
          <input name="statement" required data-testid="hypothesis-statement-input" />
        </label>
        <label>
          {/* Named for what it is. "Notes" would invite a blank. */}
          <span>What would change your mind (required)</span>
          <input name="missing_info" required data-testid="hypothesis-missing-input" />
        </label>
        <button type="submit" data-testid="hypothesis-open">
          Open hypothesis
        </button>
      </form>
    </>
  );
}
