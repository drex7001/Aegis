import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  ApiError,
  asStaleRevision,
  batchConfirmCandidates,
  listIdentityCandidates,
  recordIdentityDecision,
  type BatchConfirmResult,
  type CandidateSide,
  type IdentityCandidate,
  type StaleRevisionProblem,
} from "../api/client";
import { Waterfall } from "./Waterfall";

/**
 * Identity candidates: are these two mentions the same person?
 *
 * A candidate is a question, never an answer — nothing here moves identity
 * until someone decides, and every decision carries a note (ADR-027,
 * Article VII). The screen is built around that: the evidence is open by
 * default on the band that cannot be batched, and no action is reachable
 * without the reason for it.
 */
export function CandidateQueue() {
  const [producer, setProducer] = useState("");
  // Held here, not inside the batch panel. Confirming the last pre-verified
  // pair empties that band, so a result owned by the panel would be unmounted
  // by its own success — the reviewer would click Confirm and see nothing.
  const [batchResult, setBatchResult] = useState<BatchConfirmResult | null>(null);
  const queryClient = useQueryClient();

  const page = useInfiniteQuery({
    queryKey: ["identity-candidates", producer],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      listIdentityCandidates({
        disposition: "open",
        ...(producer ? { producer } : {}),
        ...(pageParam ? { cursor: pageParam } : {}),
      }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const candidates = page.data?.pages.flatMap((entry) => entry.candidates) ?? [];
  const preVerified = candidates.filter((candidate) => candidate.pre_verified);
  const revision = page.data?.pages[0]?.revision_id;

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["identity-candidates"] });
  };

  return (
    <section className="queue" aria-labelledby="candidates-heading">
      <header className="queue__head">
        <h2 id="candidates-heading">Identity candidates</h2>
        <label className="queue__filter">
          <span className="muted">Producer</span>
          <select
            value={producer}
            data-testid="candidate-producer-filter"
            onChange={(event) => setProducer(event.target.value)}
          >
            <option value="">Every producer</option>
            <option value="splink">splink</option>
          </select>
        </label>
      </header>

      {page.isPending && <p className="muted">Loading candidates…</p>}
      {page.error && (
        <p className="outcome outcome--error" role="alert">
          {page.error instanceof ApiError
            ? page.error.message
            : "Candidates could not be loaded."}
        </p>
      )}
      {page.data && candidates.length === 0 && (
        <p className="empty" data-testid="candidates-empty">
          No candidates waiting. Run entity resolution to propose some.
        </p>
      )}

      {batchResult && (
        <div className="batch__result" data-testid="batch-result">
          <p>
            Confirmed {batchResult.confirmed.length}
            {batchResult.skipped.length > 0 && `, refused ${batchResult.skipped.length}`}.
          </p>
          {batchResult.skipped.length > 0 && (
            <ul className="batch__skipped">
              {batchResult.skipped.map((skip) => (
                <li key={skip.candidate_id}>
                  <span className="mono">{skip.candidate_id.slice(0, 12)}</span> —{" "}
                  {skip.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {preVerified.length > 0 && revision !== undefined && (
        <BatchConfirm
          candidates={preVerified}
          revisionId={revision}
          onDone={(result) => {
            setBatchResult(result);
            invalidate();
          }}
        />
      )}

      <ul className="queue__list" data-testid="candidate-list">
        {candidates.map((candidate) => (
          <CandidateRow
            key={candidate.candidate_id}
            candidate={candidate}
            revisionId={revision}
            onDecided={invalidate}
          />
        ))}
      </ul>
      {page.hasNextPage && (
        <button
          type="button"
          className="button"
          disabled={page.isFetchingNextPage}
          onClick={() => void page.fetchNextPage()}
        >
          {page.isFetchingNextPage ? "Loading…" : "Load more"}
        </button>
      )}
    </section>
  );
}

/**
 * The pre-verified band, and only it.
 *
 * Bulk approval is offered where a deterministic rule already matched an
 * identifier, and nowhere else: a probabilistic pair is exactly the case a
 * person is supposed to look at, so it is decided one at a time below. The note
 * is required because it is the one thing that makes the batch reviewable
 * afterwards.
 */
function BatchConfirm({
  candidates,
  revisionId,
  onDone,
}: {
  candidates: IdentityCandidate[];
  revisionId: number;
  onDone: (result: BatchConfirmResult) => void;
}) {
  const [note, setNote] = useState("");
  const confirm = useMutation({
    mutationFn: () =>
      batchConfirmCandidates({
        candidate_ids: candidates.map((candidate) => candidate.candidate_id),
        parent_revision_id: revisionId,
        note,
      }),
    onSuccess: (result) => {
      setNote("");
      onDone(result);
    },
  });

  return (
    <div className="batch" data-testid="batch-confirm">
      <p className="batch__lead">
        <strong>{candidates.length}</strong> pre-verified{" "}
        {candidates.length === 1 ? "pair" : "pairs"} — an identifier matched on both
        sides.
      </p>
      <div className="batch__row">
        <label className="field__label batch__note">
          <span className="field__name">Why these are being confirmed</span>
          <input
            value={note}
            data-testid="batch-note"
            placeholder="Reviewed the matching identifiers on each record"
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="button button--primary"
          data-testid="batch-submit"
          disabled={!note.trim() || confirm.isPending}
          onClick={() => confirm.mutate()}
        >
          {confirm.isPending ? "Confirming…" : `Confirm ${candidates.length}`}
        </button>
      </div>
      <p className="field__hint">
        Each pair is recorded as its own decision, so any one of them can be
        reversed later without unpicking the rest.
      </p>

      {confirm.error && (
        <p className="outcome outcome--error" role="alert" data-testid="batch-error">
          {confirm.error instanceof ApiError
            ? confirm.error.message
            : "The batch could not be confirmed."}
        </p>
      )}
    </div>
  );
}

function CandidateRow({
  candidate,
  revisionId,
  onDecided,
}: {
  candidate: IdentityCandidate;
  revisionId: number | undefined;
  onDecided: () => void;
}) {
  // The probabilistic band opens with its evidence showing: it is the band that
  // cannot be batched, so the reason it cannot is the first thing to read.
  const [open, setOpen] = useState(!candidate.pre_verified);

  return (
    <li className="candidate" data-testid="candidate">
      <button
        type="button"
        className="candidate__summary"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="candidate__pair">
          <Side side={candidate.mention_a} />
          <span className="candidate__vs muted">and</span>
          <Side side={candidate.mention_b} />
        </span>
        <span className="candidate__meta">
          {candidate.pre_verified && (
            <span className="chip chip--verified" data-testid="candidate-verified">
              pre-verified
            </span>
          )}
          <span className="mono" data-testid="candidate-score">
            {candidate.score === null ? "no score" : candidate.score.toFixed(2)}
          </span>
        </span>
      </button>

      {open && (
        <div className="candidate__body">
          <Waterfall candidate={candidate} />
          {revisionId !== undefined && (
            <DecideOnPair
              candidate={candidate}
              revisionId={revisionId}
              onDecided={onDecided}
            />
          )}
        </div>
      )}
    </li>
  );
}

function Side({ side }: { side: CandidateSide }) {
  return (
    <span className="side">
      <span className="side__text">{side.raw_text}</span>
      <span className="side__entity muted">{side.entity_label ?? "unresolved"}</span>
    </span>
  );
}

type Mode = "confirm_match" | "reject_match" | "mark_unresolved";

const MODE_LABELS: Record<Mode, string> = {
  confirm_match: "Same person",
  reject_match: "Different people",
  mark_unresolved: "Cannot tell",
};

/**
 * All three answers are offered, including "cannot tell".
 *
 * Leaving a pair undecided and leaving it *marked* undecided look the same in a
 * list and mean opposite things — one is a queue nobody reached, the other is a
 * judgement someone made. Article VIII wants the second to be sayable.
 */
function DecideOnPair({
  candidate,
  revisionId,
  onDecided,
}: {
  candidate: IdentityCandidate;
  revisionId: number;
  onDecided: () => void;
}) {
  const [mode, setMode] = useState<Mode>("confirm_match");
  const [note, setNote] = useState("");
  const [basis, setBasis] = useState("");
  const [stale, setStale] = useState<StaleRevisionProblem | null>(null);

  const decide = useMutation({
    mutationFn: () => {
      const shared = {
        parent_revision_id: revisionId,
        note,
        mention_a: candidate.mention_a.mention_id,
        mention_b: candidate.mention_b.mention_id,
        candidate_id: candidate.candidate_id,
      };
      return recordIdentityDecision(
        mode === "reject_match"
          ? { ...shared, mode, evidence_basis: basis }
          : { ...shared, mode },
      );
    },
    onSuccess: () => {
      setStale(null);
      onDecided();
    },
    onError: (error) => setStale(asStaleRevision(error)),
  });

  const ready = note.trim() !== "" && (mode !== "reject_match" || basis.trim() !== "");

  return (
    <div className="decide">
      <div className="decide__modes" role="group" aria-label="Decision">
        {(Object.keys(MODE_LABELS) as Mode[]).map((option) => (
          <button
            key={option}
            type="button"
            className={`decide__mode${mode === option ? " decide__mode--on" : ""}`}
            aria-pressed={mode === option}
            data-testid={`decide-${option}`}
            onClick={() => setMode(option)}
          >
            {MODE_LABELS[option]}
          </button>
        ))}
      </div>
      <label className="field__label">
        <span className="field__name">Evidence note</span>
        <input
          value={note}
          data-testid="decide-note"
          placeholder="What in the records supports this?"
          onChange={(event) => setNote(event.target.value)}
        />
      </label>

      {mode === "reject_match" && (
        <label className="field__label">
          <span className="field__name">Evidence basis</span>
          <input
            value={basis}
            data-testid="decide-basis"
            placeholder="What rules them out"
            onChange={(event) => setBasis(event.target.value)}
          />
          <span className="field__hint">
            A reject suppresses this pair from future suggestions, so what it rests
            on is recorded with it.
          </span>
        </label>
      )}

      <button
        type="button"
        className="button button--primary"
        data-testid="decide-submit"
        disabled={!ready || decide.isPending}
        onClick={() => decide.mutate()}
      >
        {decide.isPending ? "Recording…" : "Record decision"}
      </button>

      {stale ? (
        <div className="outcome outcome--held" role="alert" data-testid="decide-stale">
          <p>
            Someone decided on these people while this was open. Your decision was
            not applied — read what changed, then decide again.
          </p>
          <ul className="decide__intervening">
            {stale.intervening.map((entry) => (
              <li key={entry.decision_id}>
                <strong>{entry.kind}</strong> by {entry.decided_by} — {entry.note}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        decide.error && (
          <p className="outcome outcome--error" role="alert" data-testid="decide-error">
            {decide.error instanceof ApiError
              ? decide.error.message
              : "The decision could not be recorded."}
          </p>
        )
      )}
    </div>
  );
}
