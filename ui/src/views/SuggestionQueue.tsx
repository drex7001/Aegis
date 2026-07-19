import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  acceptSuggestion,
  ApiError,
  getVocabulary,
  listSuggestions,
  rejectSuggestion,
  type Suggestion,
} from "../api/client";

/**
 * The typed review queue: what a producer proposed, waiting on a person.
 *
 * Nothing here writes a claim. Accepting dispatches through the suggestion's own
 * declared `target_action` with the reviewer as the actor (ADR-031 §2), so the
 * thing that lands is a claim someone made, not a claim a model made and a
 * button rubber-stamped.
 */
export function SuggestionQueue() {
  const [status, setStatus] = useState("suggested");
  const [kind, setKind] = useState("");
  const queryClient = useQueryClient();

  const suggestions = useInfiniteQuery({
    queryKey: ["review-queue", status, kind],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      listSuggestions({
        ...(status ? { status } : {}),
        ...(kind ? { kind } : {}),
        ...(pageParam ? { cursor: pageParam } : {}),
      }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const rows = suggestions.data?.pages.flatMap((page) => page.items) ?? [];
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["review-queue"] });
  };

  return (
    <section className="queue" aria-labelledby="suggestions-heading">
      <header className="queue__head">
        <h2 id="suggestions-heading">Suggestions</h2>
        <div className="queue__filters">
          <label className="queue__filter">
            <span className="muted">Status</span>
            <select
              value={status}
              data-testid="suggestion-status-filter"
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="suggested">Waiting</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
              <option value="">Everything</option>
            </select>
          </label>
          <label className="queue__filter">
            <span className="muted">Kind</span>
            <select
              value={kind}
              data-testid="suggestion-kind-filter"
              onChange={(event) => setKind(event.target.value)}
            >
              <option value="">Every kind</option>
              <option value="claim_draft">Claim draft</option>
              <option value="mention_link">Mention link</option>
            </select>
          </label>
        </div>
      </header>

      {suggestions.isPending && <p className="muted">Loading the queue…</p>}
      {suggestions.error && (
        <p className="outcome outcome--error" role="alert">
          {suggestions.error instanceof ApiError
            ? suggestions.error.message
            : "The queue could not be loaded."}
        </p>
      )}
      {suggestions.data && rows.length === 0 && (
        <p className="empty" data-testid="queue-empty">
          Nothing waiting. Extract a landed record to propose some.
        </p>
      )}

      <ul className="queue__list" data-testid="suggestion-list">
        {rows.map((suggestion) => (
          <SuggestionRow
            key={suggestion.suggestion_id}
            suggestion={suggestion}
            onDecided={invalidate}
          />
        ))}
      </ul>
      {suggestions.hasNextPage && (
        <button
          type="button"
          className="button"
          disabled={suggestions.isFetchingNextPage}
          onClick={() => void suggestions.fetchNextPage()}
        >
          {suggestions.isFetchingNextPage ? "Loading…" : "Load more"}
        </button>
      )}
    </section>
  );
}

function SuggestionRow({
  suggestion,
  onDecided,
}: {
  suggestion: Suggestion;
  onDecided: () => void;
}) {
  const [open, setOpen] = useState(false);
  const payload = suggestion.payload as Record<string, unknown>;
  const settled = suggestion.status !== "suggested";

  return (
    <li className="suggestion" data-testid="suggestion">
      <button
        type="button"
        className="suggestion__summary"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="suggestion__claim">
          {summarise(suggestion.suggestion_kind, payload)}
        </span>
        <span className="suggestion__meta">
          <span className="chip chip--kind" data-testid="suggestion-kind">
            {suggestion.suggestion_kind.replace(/_/g, " ")}
          </span>
          {settled && (
            <span className="chip" data-testid="suggestion-status">
              {suggestion.status}
            </span>
          )}
          <span className="muted mono">{suggestion.producer}</span>
        </span>
      </button>

      {open && (
        <div className="suggestion__body">
          <Producer suggestion={suggestion} />
          {settled ? (
            <p className="muted" data-testid="suggestion-settled">
              {suggestion.status} by {suggestion.decided_by ?? "unknown"}
              {suggestion.decision_note ? ` — ${suggestion.decision_note}` : ""}
            </p>
          ) : (
            <Decide suggestion={suggestion} onDecided={onDecided} />
          )}
        </div>
      )}
    </li>
  );
}

function summarise(kind: string, payload: Record<string, unknown>): string {
  if (kind === "claim_draft") {
    const predicate = String(payload["predicate"] ?? "—").replace(/_/g, " ");
    const object = payload["object_id"] ?? payload["object_value"] ?? "—";
    return `${payload["subject_id"] ?? "—"} · ${predicate} · ${object}`;
  }
  return Object.entries(payload)
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(" · ");
}

/**
 * Producer metadata, rendered per kind.
 *
 * A model pass and a rule pass are not comparable and should not be flattened
 * into one "confidence" line: what makes a model's output checkable is the model
 * name and the prompt that produced it, and what makes a rule's output checkable
 * is which rule fired. Showing whichever exists is the honest option.
 */
function Producer({ suggestion }: { suggestion: Suggestion }) {
  const meta = (suggestion.producer_meta ?? {}) as Record<string, unknown>;
  const entries = Object.entries(meta);

  return (
    <dl className="suggestion__producer">
      <dt>Producer</dt>
      <dd className="mono">
        {suggestion.producer} {suggestion.producer_version}
      </dd>
      {entries.map(([key, value]) => (
        <ProducerFact key={key} label={key.replace(/_/g, " ")} value={value} />
      ))}
      {suggestion.record_id && (
        <>
          <dt>From record</dt>
          <dd className="mono">{suggestion.record_id}</dd>
        </>
      )}
    </dl>
  );
}

function ProducerFact({ label, value }: { label: string; value: unknown }) {
  const text = typeof value === "object" ? JSON.stringify(value) : String(value);
  return (
    <>
      <dt>{label}</dt>
      <dd className="mono">{text.length > 80 ? `${text.slice(0, 80)}…` : text}</dd>
    </>
  );
}

/**
 * Accept, edit-then-accept, or reject with a reason.
 *
 * The edit is not a convenience: a reviewer who can only take or leave a
 * suggestion will take the near-misses, and the record will say a model was
 * right when a person quietly corrected it. Edits ride with the acceptance so
 * the queue row keeps both what was proposed and what was recorded.
 */
function Decide({
  suggestion,
  onDecided,
}: {
  suggestion: Suggestion;
  onDecided: () => void;
}) {
  const payload = suggestion.payload as Record<string, unknown>;
  const [assertion, setAssertion] = useState(String(payload["assertion_type"] ?? ""));
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");

  const vocabulary = useQuery({ queryKey: ["vocabulary"], queryFn: getVocabulary });

  const accept = useMutation({
    mutationFn: () =>
      acceptSuggestion(suggestion.suggestion_id, {
        // Only send an edit when it differs from what was proposed, so the
        // audit trail distinguishes "accepted" from "corrected, then accepted".
        ...(assertion && assertion !== payload["assertion_type"]
          ? { edits: { assertion_type: assertion } }
          : {}),
        ...(note.trim() ? { note } : {}),
      }),
    onSuccess: onDecided,
  });

  const reject = useMutation({
    mutationFn: () => rejectSuggestion(suggestion.suggestion_id, reason),
    onSuccess: onDecided,
  });

  const busy = accept.isPending || reject.isPending;
  const error = accept.error ?? reject.error;

  return (
    <div className="decide">
      {suggestion.suggestion_kind === "claim_draft" && (
        <label className="field__label">
          <span className="field__name">Assertion type</span>
          <select
            value={assertion}
            data-testid="accept-assertion"
            onChange={(event) => setAssertion(event.target.value)}
          >
            {/* Served by the API, never a constant in this bundle: a second
                copy of a closed vocabulary keeps working while being wrong. */}
            {(vocabulary.data?.assertion_types ?? []).map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          {assertion !== payload["assertion_type"] && (
            <span className="field__hint" data-testid="accept-edited">
              Changed from {String(payload["assertion_type"] ?? "unset")} — this is
              recorded as an edit, not a plain acceptance.
            </span>
          )}
        </label>
      )}

      <label className="field__label">
        <span className="field__name">Note (optional)</span>
        <input
          value={note}
          data-testid="accept-note"
          placeholder="Anything a later reader should know"
          onChange={(event) => setNote(event.target.value)}
        />
      </label>

      <div className="decide__actions">
        <button
          type="button"
          className="button button--primary"
          data-testid="suggestion-accept"
          disabled={busy}
          onClick={() => accept.mutate()}
        >
          {accept.isPending ? "Recording…" : "Accept"}
        </button>
      </div>

      <label className="field__label">
        <span className="field__name">Reject because</span>
        <input
          value={reason}
          data-testid="reject-reason"
          placeholder="Why this should not be recorded"
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      <button
        type="button"
        className="button"
        data-testid="suggestion-reject"
        disabled={busy || !reason.trim()}
        onClick={() => reject.mutate()}
      >
        {reject.isPending ? "Rejecting…" : "Reject"}
      </button>

      {error && (
        <p className="outcome outcome--error" role="alert" data-testid="decide-error">
          {error instanceof ApiError ? error.message : "The decision could not be recorded."}
        </p>
      )}
    </div>
  );
}
