import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { search, type SearchHit } from "../api/client";
import { entityPath } from "../routing";

/**
 * Search (T23c, widened to entities, claims and documents by T67).
 *
 * Three things it deliberately shows, and one it deliberately does not.
 *
 * **How** each hit was found: a phonetic match is a lead, not a name match, and
 * a list that renders them identically invites the reader to treat them alike.
 *
 * **What kind of thing** each hit is, as a group heading taken from the server.
 * The group names come from the ontology, so a new domain module's types appear
 * here with no change to this file (Article XIV).
 *
 * **One "load more"**, never one per group. Groups are how a page is displayed,
 * never how it is fetched: per-group cursors would leave informative gaps where
 * restricted rows were removed (B-17, spec 11 §5.1).
 *
 * And **nothing about what it cannot see**: results are authorization-filtered
 * in candidate generation, so an empty list means "nothing you are cleared to
 * see" — never "no such person", which would answer a question the caller was
 * not permitted to ask. There is no total to render, in any group, for the same
 * reason.
 */

/** Long enough that a two-letter prefix does not scan the corpus on every key. */
const MIN_QUERY = 2;
const DEBOUNCE_MS = 250;

export interface SearchPanelProps {
  /** Seed the canvas on an entity hit. */
  onPick: (entityId: string) => void;
}

export function SearchPanel({ onPick }: SearchPanelProps) {
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
    queryFn: ({ pageParam }) => search(debounced, { limit: 10, cursor: pageParam }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled,
  });

  /*
   * Pages arrive already grouped, and a group can appear on more than one page.
   * Merging by group name keeps one heading per kind instead of repeating it
   * every time "load more" is pressed — the alternative reads as if the corpus
   * held several different sets of people.
   */
  const merged = new Map<string, { label: string; hits: SearchHit[] }>();
  for (const page of query.data?.pages ?? []) {
    for (const group of page.groups) {
      const existing = merged.get(group.group);
      if (existing) existing.hits.push(...group.hits);
      else merged.set(group.group, { label: group.label, hits: [...group.hits] });
    }
  }
  const groups = [...merged.entries()];
  const empty = groups.length === 0;

  return (
    <div className="search" data-testid="search-panel">
      <label className="search__field">
        <span className="visually-hidden">Search</span>
        <input
          type="search"
          value={text}
          placeholder="Search people, organisations, claims and documents"
          onChange={(event) => setText(event.target.value)}
          data-testid="search-input"
        />
      </label>

      {enabled && query.isFetching && !query.isFetchingNextPage && (
        <p className="muted">Searching…</p>
      )}
      {enabled && !query.isFetching && empty && (
        <p className="muted" data-testid="search-empty">
          Nothing you are cleared to see matches “{debounced}”.
        </p>
      )}
      {!empty && (
        <div className="search__panel" data-testid="search-results">
          {groups.map(([name, group]) => (
            <section key={name} data-testid={`search-group-${name}`}>
              <h3 className="search__group">{group.label}</h3>
              <ul className="search__results">
                {group.hits.map((hit) => (
                  <li key={`${hit.kind}:${hit.id}`}>
                    <Hit
                      hit={hit}
                      onPick={(entityId) => {
                        onPick(entityId);
                        setText("");
                        setDebounced("");
                      }}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))}
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
        </div>
      )}
    </div>
  );
}

/**
 * One hit, and where it goes.
 *
 * An entity hit answers two questions, so it keeps two destinations: the button
 * seeds the canvas ("show me around this"), the link opens the object view
 * ("tell me about this"). The button's behaviour is unchanged from P2 on
 * purpose — the journey that asserts search-then-focus still passes.
 *
 * A claim hit goes to its **subject entity**, because a claim's page is the
 * page of the thing it is about. A document hit has no detail view yet and
 * says so by not offering one, rather than by offering a link that goes
 * nowhere.
 */
function Hit({ hit, onPick }: { hit: SearchHit; onPick: (entityId: string) => void }) {
  const meta = (
    <span className="search__meta">
      {hit.detail ?? hit.group}
      <MatchedBy matched={hit.matched} />
    </span>
  );

  if (hit.kind === "entity") {
    return (
      <>
        <button
          type="button"
          className="search__hit"
          onClick={() => onPick(hit.id)}
          data-testid={`search-hit-${hit.id}`}
        >
          <span className="search__label">{hit.label}</span>
          {meta}
        </button>
        <Link
          to={entityPath(hit.id)}
          className="search__open"
          data-testid={`search-open-${hit.id}`}
        >
          Open
        </Link>
      </>
    );
  }

  return (
    <span className="search__hit search__hit--passive" data-testid={`search-hit-${hit.id}`}>
      <span className="search__label">{hit.label}</span>
      {meta}
      {hit.kind === "claim" && hit.parent_id && (
        <Link
          to={entityPath(hit.parent_id)}
          className="search__open"
          data-testid={`search-open-${hit.id}`}
        >
          Open
        </Link>
      )}
    </span>
  );
}

/**
 * How the hit was found, in the reader's words rather than the index's.
 *
 * Two matter. "phonetic": metaphone collapses genuinely different names, so a
 * hit found that way is a lead to check, and "sounds like" is the honest
 * description of the confidence behind it. "identifier": an exact equality and
 * nothing else (ADR-053) — a near-miss never appears here, so "exact match" is
 * a promise the index actually keeps.
 */
const MATCHED_LABELS: Record<string, string> = {
  label: "name",
  alias: "alias",
  mention: "mentioned as",
  transliterated: "romanized as",
  phonetic: "sounds like",
  identifier: "exact match",
  excerpt: "in the excerpt",
  value: "in the value",
  text: "in the text",
};

/**
 * Matches that are a lead rather than an answer, drawn dashed so the list does
 * not present them as equally strong evidence.
 *
 * `transliterated` joins `phonetic` here because it is the same kind of claim:
 * a Latin query reached a name written in another script through two different
 * romanization systems, at a similarity the same-script floor would reject
 * outright (T68 measured 6 of 8 such names found, and 2 not found at all).
 */
const WEAK = new Set(["phonetic", "transliterated"]);

function MatchedBy({ matched }: { matched: string }) {
  const label = MATCHED_LABELS[matched] ?? matched;
  return (
    <span
      className={`chip chip--match${WEAK.has(matched) ? " chip--weak" : ""}`}
      data-testid={`matched-${matched}`}
    >
      {label}
    </span>
  );
}

export type { SearchHit };
