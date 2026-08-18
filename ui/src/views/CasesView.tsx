import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError, listCases, openCase } from "../api/client";
import { casePath } from "../routing";

/**
 * The caller's own cases (T46, over the route T43 landed).
 *
 * Two things this screen must never do, both of them the same rule from
 * different sides: **it may not report what it cannot show.** The route returns
 * no total, so there is nothing here to render as "N cases" — a count over an
 * authorization-filtered collection is an existence leak (spec 06 §4). And an
 * empty list is phrased as "none you are a member of", never as "none exist",
 * because the second answers a question the caller was not permitted to ask.
 *
 * Opening a case requires a **purpose**, captured by the route's authorization
 * gate and audited with the allow (GOAL.md §12.4). It is a query parameter
 * rather than a body field for exactly that reason: the gate reads it before
 * the handler sees the body.
 */

export function CasesView() {
  const client = useQueryClient();
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [error, setError] = useState<string | null>(null);

  const cases = useQuery({ queryKey: ["cases"], queryFn: () => listCases() });

  const create = useMutation({
    mutationFn: () => openCase({ title, purpose }, purpose),
    onSuccess: () => {
      setTitle("");
      setPurpose("");
      setError(null);
      void client.invalidateQueries({ queryKey: ["cases"] });
    },
    onError: (err: unknown) =>
      setError(err instanceof ApiError ? err.message : "Could not open the case."),
  });

  return (
    <section className="page" data-testid="cases-view">
      <header className="page__head">
        <h1>Cases</h1>
      </header>

      <form
        className="case-form"
        data-testid="case-form"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <label>
          <span>Title</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            required
            data-testid="case-title"
          />
        </label>
        <label>
          <span>Purpose</span>
          {/*
           * Not a description. This is the recorded reason the case exists, it
           * is audited with the opening, and it is what a later reader has to
           * judge the work against — so it is required by the route, not just
           * by this form.
           */}
          <input
            value={purpose}
            onChange={(event) => setPurpose(event.target.value)}
            required
            data-testid="case-purpose"
          />
        </label>
        <button type="submit" disabled={create.isPending} data-testid="case-open">
          {create.isPending ? "Opening…" : "Open case"}
        </button>
      </form>
      {error && (
        <p className="notice notice--error" role="alert" data-testid="case-error">
          {error}
        </p>
      )}

      {cases.isPending && <p className="muted">Loading…</p>}
      {cases.data && cases.data.items.length === 0 && (
        <p className="notice" data-testid="cases-empty">
          {/* "None you are a member of", never "none exist". */}
          You are not a member of any case.
        </p>
      )}
      {cases.data && cases.data.items.length > 0 && (
        <table className="table" data-testid="cases-table">
          <thead>
            <tr>
              <th scope="col">Case</th>
              <th scope="col">Status</th>
              <th scope="col">Purpose</th>
              <th scope="col">Opened</th>
            </tr>
          </thead>
          <tbody>
            {cases.data.items.map((entry) => (
              <tr key={entry.case_id}>
                <th scope="row">
                  <Link to={casePath(entry.case_id)}>{entry.title}</Link>
                </th>
                <td>{entry.status}</td>
                <td>{entry.purpose}</td>
                <td>{entry.opened_at.slice(0, 10)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
