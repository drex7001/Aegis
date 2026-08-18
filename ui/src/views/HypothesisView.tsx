import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  ApiError,
  getHypothesis,
  linkHypothesisClaim,
  reviseHypothesis,
  unlinkHypothesisClaim,
  type Hypothesis,
  type HypothesisClaim,
} from "../api/client";
import { casePath } from "../routing";

/**
 * One hypothesis: what is believed, what would change it, and both sides of
 * the evidence (T47, GOAL.md §18, spec 09 §3).
 *
 * Three rules this screen exists to hold, each of which is easy to lose by
 * being helpful:
 *
 * 1. **Both sides always render.** `supporting` and `contradicting` are
 *    columns whether or not they hold anything, and an empty one says "no
 *    contradicting evidence recorded" rather than disappearing. A page that
 *    hides the empty column teaches the reader that the question was not
 *    asked, which is the opposite of Article VIII.
 * 2. **What is missing is a heading, not a footnote.** GOAL.md §18's whole
 *    point is that a hypothesis states what would change it; burying that under
 *    the evidence would make it decoration.
 * 3. **Nothing is scored.** No "3 for, 1 against" tally, no confidence bar. The
 *    counts a reader needs are the two lists, and a number over them is the
 *    thing that would get quoted without them.
 */

function Column({
  title,
  stance,
  links,
  empty,
  onDetach,
}: {
  title: string;
  stance: string;
  links: HypothesisClaim[];
  empty: string;
  onDetach: (link: HypothesisClaim) => void;
}) {
  return (
    <section className="hypothesis__column" data-testid={`hypothesis-${stance}`}>
      <h3>{title}</h3>
      {links.length === 0 ? (
        // Present and explicit. See rule 1.
        <p className="notice" data-testid={`hypothesis-${stance}-empty`}>
          {empty}
        </p>
      ) : (
        <ul>
          {links.map((link) => (
            <li key={link.claim_id}>
              <code>{link.claim_id}</code>
              {link.note && <span className="muted"> — {link.note}</span>}
              <span className="muted"> · linked by {link.linked_by}</span>
              <button
                type="button"
                className="reference__detach"
                data-testid={`unlink-${stance}-${link.claim_id}`}
                onClick={() => onDetach(link)}
              >
                Unlink
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function HypothesisView() {
  const { hypothesisId = "" } = useParams<{ hypothesisId: string }>();
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["hypothesis", hypothesisId],
    queryFn: () => getHypothesis(hypothesisId),
  });
  const refresh = () =>
    void client.invalidateQueries({ queryKey: ["hypothesis", hypothesisId] });
  const fail = (err: unknown, fallback: string) =>
    setError(err instanceof ApiError ? err.message : fallback);

  const revise = useMutation({
    mutationFn: (body: Parameters<typeof reviseHypothesis>[1]) =>
      reviseHypothesis(hypothesisId, body),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (err: unknown) => fail(err, "Could not revise the hypothesis."),
  });

  const link = useMutation({
    mutationFn: (body: Parameters<typeof linkHypothesisClaim>[1]) =>
      linkHypothesisClaim(hypothesisId, body),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (err: unknown) => fail(err, "Could not link the claim."),
  });

  const unlink = useMutation({
    mutationFn: (target: { claimId: string; stance: string; reason: string }) =>
      unlinkHypothesisClaim(hypothesisId, target.claimId, target.stance, target.reason),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (err: unknown) => fail(err, "Could not unlink the claim."),
  });

  if (query.isPending) {
    return (
      <section className="page" aria-busy="true">
        <p className="muted">Loading…</p>
      </section>
    );
  }
  if (query.error || !query.data) {
    return (
      <section className="page" data-testid="hypothesis-absent" role="alert">
        <h1>Not available</h1>
        {/* 404 is "absent or not yours" by design (spec 09 §5 rule 1). */}
        <p className="muted">
          Nothing here for <code>{hypothesisId}</code>.
        </p>
      </section>
    );
  }

  const hypothesis: Hypothesis = query.data;
  const current = hypothesis.current;

  const detach = (stance: string) => (linkRow: HypothesisClaim) => {
    const reason = window.prompt("Why does this claim no longer belong here?");
    if (reason) unlink.mutate({ claimId: linkRow.claim_id, stance, reason });
  };

  return (
    <section className="page" data-testid="hypothesis-view">
      <header className="page__head">
        <h1 data-testid="hypothesis-statement">{current.statement}</h1>
        <p className="muted">
          <span data-testid="hypothesis-status">{current.status}</span> · version{" "}
          {current.version} · opened by {hypothesis.opened_by} ·{" "}
          <Link to={casePath(hypothesis.case_id)}>back to the case</Link>
        </p>
      </header>

      {/* Rule 2: what would change this belief is a heading of its own. */}
      <section className="hypothesis__missing" data-testid="hypothesis-missing">
        <h2>What is missing</h2>
        <p>{current.missing_info}</p>
      </section>

      {error && (
        <p className="notice notice--error" role="alert" data-testid="hypothesis-error">
          {error}
        </p>
      )}

      <div className="hypothesis__columns">
        <Column
          title="Supporting"
          stance="supports"
          links={hypothesis.supporting}
          empty="No supporting evidence recorded."
          onDetach={detach("supports")}
        />
        <Column
          title="Contradicting"
          stance="contradicts"
          links={hypothesis.contradicting}
          empty="No contradicting evidence recorded."
          onDetach={detach("contradicts")}
        />
      </div>

      <form
        className="case-form"
        data-testid="hypothesis-link-form"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          link.mutate({
            claim_id: String(form.get("claim_id") ?? ""),
            stance: form.get("stance") === "contradicts" ? "contradicts" : "supports",
            note: String(form.get("note") ?? "") || null,
          });
          event.currentTarget.reset();
        }}
      >
        <label>
          <span>Claim</span>
          {/*
           * A claim id rather than a picker. There is no "claims in this case"
           * route to populate one from, and inventing a client-side search over
           * a route that does not exist would be a worse answer than asking for
           * the id an analyst already has in front of them on the object view.
           * A picker is a real improvement and is not a P4 gate criterion.
           */}
          <input name="claim_id" required data-testid="link-claim-id" />
        </label>
        <label>
          <span>Stance</span>
          <select name="stance" data-testid="link-stance">
            <option value="supports">supports</option>
            <option value="contradicts">contradicts</option>
          </select>
        </label>
        <label>
          <span>Note</span>
          <input name="note" data-testid="link-note" />
        </label>
        <button type="submit" data-testid="link-claim">
          Link claim
        </button>
      </form>

      <h2>Revisions</h2>
      <ol className="line" data-testid="hypothesis-revisions">
        {hypothesis.revisions.map((revision) => (
          <li key={revision.version}>
            <strong>v{revision.version}</strong>{" "}
            <span className="chip chip--kind">{revision.status}</span>{" "}
            <span className="muted">
              {revision.authored_by} · {revision.authored_at.slice(0, 10)}
            </span>
            {/* The statement of every version, not only the current one: this
                is why revisions are rows rather than an audit payload. */}
            <p className="line__note">{revision.statement}</p>
            {revision.note && <p className="line__note muted">{revision.note}</p>}
          </li>
        ))}
      </ol>

      <form
        className="case-form"
        data-testid="hypothesis-revise-form"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const statement = String(form.get("statement") ?? "");
          const missing = String(form.get("missing_info") ?? "");
          revise.mutate({
            note: String(form.get("note") ?? ""),
            // Unsupplied fields carry forward on the server: a revision is a
            // snapshot, and sending "" would blank what it should preserve.
            statement: statement || null,
            missing_info: missing || null,
            status: (form.get("status") as never) || null,
          });
          event.currentTarget.reset();
        }}
      >
        <label>
          <span>Why (required)</span>
          <input name="note" required data-testid="revise-note" />
        </label>
        <label>
          <span>Status</span>
          <select name="status" data-testid="revise-status" defaultValue="">
            <option value="">unchanged</option>
            {["open", "supported", "refuted", "withdrawn"].map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>New statement</span>
          <input name="statement" data-testid="revise-statement" />
        </label>
        <label>
          <span>What is still missing</span>
          <input name="missing_info" data-testid="revise-missing" />
        </label>
        <button type="submit" data-testid="revise-submit">
          Record revision
        </button>
      </form>
    </section>
  );
}
