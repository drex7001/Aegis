import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  ApiError,
  addCaseMember,
  closeCase,
  getCase,
  listCaseMembers,
  listCaseReferences,
  unlinkCaseReference,
} from "../api/client";
import { entityPath } from "../routing";
import { CaseGraph } from "./CaseGraph";
import { CaseHypotheses } from "./CaseHypotheses";
import { CaseTasks } from "./CaseTasks";

/**
 * One case: what it is, who is in it, what it refers to, and its own graph.
 *
 * The distinction this screen has to keep visible is ADR-044's. A **reference**
 * says "this investigation refers to that"; it grants nothing, and it does not
 * move a claim into the case. The case's *own* evidence — the claims recorded
 * with its `case_id` — is what the graph below draws. Wording matters here:
 * calling references "the case's claims" would teach the reader the opposite of
 * how the authorization works.
 */

function useCaseData(caseId: string) {
  const detail = useQuery({ queryKey: ["case", caseId], queryFn: () => getCase(caseId) });
  const members = useQuery({
    queryKey: ["case-members", caseId],
    queryFn: () => listCaseMembers(caseId),
  });
  const references = useQuery({
    queryKey: ["case-references", caseId],
    queryFn: () => listCaseReferences(caseId),
  });
  return { detail, members, references };
}

export function CaseView() {
  const { caseId = "" } = useParams<{ caseId: string }>();
  const client = useQueryClient();
  const { detail, members, references } = useCaseData(caseId);
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState("analyst");
  const [error, setError] = useState<string | null>(null);

  const invalidate = (key: string) =>
    void client.invalidateQueries({ queryKey: [key, caseId] });

  const assign = useMutation({
    mutationFn: () => addCaseMember(caseId, { user_id: userId, role }),
    onSuccess: () => {
      setUserId("");
      setError(null);
      invalidate("case-members");
    },
    onError: (err: unknown) =>
      setError(err instanceof ApiError ? err.message : "Could not add the member."),
  });

  const close = useMutation({
    mutationFn: (reason: string) => closeCase(caseId, reason),
    onSuccess: () => {
      setError(null);
      invalidate("case");
    },
    onError: (err: unknown) =>
      setError(err instanceof ApiError ? err.message : "Could not close the case."),
  });

  const detach = useMutation({
    mutationFn: (target: { type: string; id: string; reason: string }) =>
      unlinkCaseReference(caseId, target.type, target.id, target.reason),
    onSuccess: () => invalidate("case-references"),
    onError: (err: unknown) =>
      setError(err instanceof ApiError ? err.message : "Could not detach the reference."),
  });

  if (detail.isPending) {
    return (
      <section className="page" aria-busy="true">
        <p className="muted">Loading…</p>
      </section>
    );
  }
  if (detail.error || !detail.data) {
    return (
      <section className="page" data-testid="case-absent" role="alert">
        <h1>Not available</h1>
        {/* 404 is "absent or not yours", by design. Phrased as absence so that
            asking cannot confirm the case exists (spec 09 §5 rule 1). */}
        <p className="muted">
          Nothing here for <code>{caseId}</code>.
        </p>
      </section>
    );
  }

  const record = detail.data;
  return (
    <section className="page" data-testid="case-view">
      <header className="page__head">
        <h1 data-testid="case-title">{record.title}</h1>
        <p className="muted">
          <span data-testid="case-status">{record.status}</span> ·{" "}
          <code>{record.case_id}</code> · opened by {record.opened_by}
        </p>
      </header>
      <p>
        <strong>Purpose:</strong> {record.purpose}
      </p>

      {error && (
        <p className="notice notice--error" role="alert" data-testid="case-error">
          {error}
        </p>
      )}

      {record.status === "open" && (
        <form
          className="case-form"
          data-testid="case-close-form"
          onSubmit={(event) => {
            event.preventDefault();
            const reason = new FormData(event.currentTarget).get("reason");
            close.mutate(String(reason ?? ""));
          }}
        >
          <label>
            <span>Reason for closing</span>
            <input name="reason" required data-testid="case-close-reason" />
          </label>
          <button type="submit" data-testid="case-close">
            Close case
          </button>
        </form>
      )}

      <h2>Members</h2>
      <ul data-testid="case-members">
        {(members.data ?? []).map((member) => (
          <li key={member.user_id}>
            {member.user_id} <span className="muted">· {member.role}</span>
          </li>
        ))}
      </ul>
      <form
        className="case-form"
        data-testid="case-member-form"
        onSubmit={(event) => {
          event.preventDefault();
          assign.mutate();
        }}
      >
        <label>
          <span>User</span>
          <input
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
            required
            data-testid="member-user"
          />
        </label>
        <label>
          <span>Role</span>
          <select
            value={role}
            onChange={(event) => setRole(event.target.value)}
            data-testid="member-role"
          >
            {/* Case roles, not realm roles: `auditor` here means an audited
                grant on this case (spec 03 §3), which is why it is offered
                beside the working roles rather than hidden. */}
            {["analyst", "investigator", "supervisor", "auditor"].map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" data-testid="member-add">
          Add member
        </button>
      </form>

      <h2>References</h2>
      <p className="muted">
        {/* ADR-044, said out loud where an analyst will read it. */}
        What this investigation refers to. A reference grants no access to its
        target and does not move a claim into this case.
      </p>
      {(references.data ?? []).length === 0 ? (
        <p className="notice" data-testid="case-references-empty">
          This case refers to nothing yet.
        </p>
      ) : (
        <ul data-testid="case-references">
          {(references.data ?? []).map((reference) => (
            <li key={`${reference.target_type}:${reference.target_id}`}>
              <span className="chip chip--kind">{reference.target_type}</span>{" "}
              {reference.target_type === "entity" ? (
                <Link to={entityPath(reference.target_id)}>{reference.target_id}</Link>
              ) : (
                <code>{reference.target_id}</code>
              )}
              {reference.note && <span className="muted"> — {reference.note}</span>}
              <button
                type="button"
                className="reference__detach"
                data-testid={`detach-${reference.target_id}`}
                onClick={() => {
                  const reason = window.prompt("Why is this reference wrong?");
                  if (reason) {
                    detach.mutate({
                      type: reference.target_type,
                      id: reference.target_id,
                      reason,
                    });
                  }
                }}
              >
                Detach
              </button>
            </li>
          ))}
        </ul>
      )}

      <CaseHypotheses caseId={caseId} />

      <CaseTasks caseId={caseId} />

      <h2>Case graph</h2>
      <p className="muted">
        Only the evidence this case recorded. An edge here is supported by at
        least one claim scoped to this case, and its tally counts only those —
        so it never overstates what the investigation has.
      </p>
      <CaseGraph caseId={caseId} />
    </section>
  );
}
