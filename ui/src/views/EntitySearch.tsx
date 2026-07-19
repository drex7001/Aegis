import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { searchEntities, type EntityHit } from "../api/client";

/**
 * Entity search (T23c) — the "search first, expand second" half of spec 07 §5
 * that the bounded overview was standing in for.
 *
 * Two things it deliberately shows. **How** each hit was found: a phonetic
 * match is a lead, not a name match, and a list that renders them identically
 * invites the reader to treat them alike. And **nothing about what it cannot
 * see**: the result set is authorization-filtered in candidate generation, so
 * an empty list means "nothing you are cleared to see" — never "no such
 * person", which would answer a question the caller was not permitted to ask.
 */

/** Long enough that a two-letter prefix does not scan the corpus on every key. */
const MIN_QUERY = 2;
const DEBOUNCE_MS = 250;

export interface EntitySearchProps {
  /** Seed the canvas on a hit. */
  onPick: (entityId: string) => void;
}

export function EntitySearch({ onPick }: EntitySearchProps) {
  const [text, setText] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(text.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text]);

  const enabled = debounced.length >= MIN_QUERY;
  const query = useInfiniteQuery({
    queryKey: ["search", debounced],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => searchEntities(debounced, 10, pageParam),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled,
  });

  const hits = query.data?.pages.flatMap((page) => page.results) ?? [];
  return (
    <div className="search" data-testid="entity-search">
      <label className="search__field">
        <span className="visually-hidden">Search entities</span>
        <input
          type="search"
          value={text}
          placeholder="Search people and organisations"
          onChange={(event) => setText(event.target.value)}
          data-testid="search-input"
        />
      </label>

      {enabled && query.isFetching && <p className="muted">Searching…</p>}
      {enabled && !query.isFetching && hits.length === 0 && (
        <p className="muted" data-testid="search-empty">
          Nothing you are cleared to see matches “{debounced}”.
        </p>
      )}
      {hits.length > 0 && (
        <>
          <ul className="search__results" data-testid="search-results">
            {hits.map((hit) => (
              <li key={hit.entity_id}>
                <button
                  type="button"
                  className="search__hit"
                  onClick={() => {
                    onPick(hit.entity_id);
                    setText("");
                    setDebounced("");
                  }}
                  data-testid={`search-hit-${hit.entity_id}`}
                >
                  <span className="search__label">{hit.label}</span>
                  <span className="search__meta">
                    {hit.entity_type}
                    <MatchedBy matched={hit.matched} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {query.hasNextPage && (
            <button
              type="button"
              className="button"
              disabled={query.isFetchingNextPage}
              onClick={() => void query.fetchNextPage()}
            >
              {query.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          )}
        </>
      )}
    </div>
  );
}

/**
 * How the hit was found, in the reader's words rather than the index's.
 *
 * "phonetic" is the one that matters: metaphone collapses genuinely different
 * names, so a hit found that way is a lead to check, and saying "sounds like"
 * is the honest description of the confidence behind it.
 */
const MATCHED_LABELS: Record<string, string> = {
  label: "name",
  alias: "alias",
  mention: "mentioned as",
  phonetic: "sounds like",
};

function MatchedBy({ matched }: { matched: string }) {
  const label = MATCHED_LABELS[matched] ?? matched;
  return (
    <span
      className={`chip chip--match${matched === "phonetic" ? " chip--weak" : ""}`}
      data-testid={`matched-${matched}`}
    >
      {label}
    </span>
  );
}

export type { EntityHit };
