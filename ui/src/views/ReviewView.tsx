import { useState } from "react";

import { CandidateQueue } from "./CandidateQueue";
import { SuggestionQueue } from "./SuggestionQueue";

/**
 * The review inbox (ADR-031 §3, spec 04 §4).
 *
 * A composition over two sources, not one merged feed. `review_queue` and
 * `er_candidate` are different questions — "should this be recorded?" against
 * "are these the same person?" — with different evidence, different actions and
 * different consequences. Interleaving them would force a row that serves
 * neither, and would put a bulk-confirm control next to things nobody should
 * ever confirm in bulk.
 */
const TABS = [
  { id: "suggestions", label: "Suggestions" },
  { id: "identity", label: "Identity" },
] as const;

type Tab = (typeof TABS)[number]["id"];

export function ReviewView() {
  const [tab, setTab] = useState<Tab>("suggestions");

  return (
    <div className="review">
      <header className="review__head">
        <h1>Review</h1>
        <p className="muted">
          Everything here is a proposal. Nothing is recorded until you decide.
        </p>
      </header>

      <div className="tabs" role="tablist" aria-label="Review sources">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            id={`tab-${entry.id}`}
            aria-selected={tab === entry.id}
            aria-controls={`panel-${entry.id}`}
            className={`tab${tab === entry.id ? " tab--active" : ""}`}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`panel-${tab}`}
        aria-labelledby={`tab-${tab}`}
        className="review__panel"
      >
        {tab === "suggestions" ? <SuggestionQueue /> : <CandidateQueue />}
      </div>
    </div>
  );
}
