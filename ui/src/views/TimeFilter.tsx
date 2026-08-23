import { useSearchParams } from "react-router-dom";

/**
 * The one time window, and the one selection (T62, spec 10 §11.2).
 *
 * Both live in the **URL**, which is what makes them shared rather than
 * synchronized. Three surfaces reading one `useSearchParams` cannot disagree;
 * three surfaces each holding their own state and pushing updates to each other
 * can, and would, on whichever path someone forgets.
 *
 * It also means a view is a link. An analyst who has narrowed to a fortnight
 * and selected an incident can send that, and the person who opens it sees the
 * same thing — which is not true of anything held in component state.
 *
 * The window is **event time**: when the thing happened. Deliberately not
 * `valid_from`/`valid_to`, which is when a relationship was true — the graph
 * keeps that as a separate filter because "was a member during 2019" and "an
 * arrest happened in 2019" are different questions, and one control answering
 * both would mean different things on different surfaces.
 */

export interface TimeWindow {
  from?: string;
  to?: string;
  /** The claim-recording snapshot, which composes with the window (B-11). */
  asOf?: string;
  asOfRevision?: number;
}

export interface Selection {
  entityId?: string;
}

/** Read the shared window and selection. One source, three readers. */
export function useSharedFilter(): {
  window: TimeWindow;
  selection: Selection;
  setWindow: (next: TimeWindow) => void;
  select: (entityId: string | null) => void;
} {
  const [search, setSearch] = useSearchParams();

  const revision = search.get("asOfRevision");
  const window: TimeWindow = {
    from: search.get("from") ?? undefined,
    to: search.get("to") ?? undefined,
    asOf: search.get("asOf") ?? undefined,
    asOfRevision: revision ? Number(revision) : undefined,
  };

  const setWindow = (next: TimeWindow) => {
    const params = new URLSearchParams(search);
    for (const key of ["from", "to", "asOf", "asOfRevision"] as const) {
      const value = next[key];
      if (value === undefined || value === "") params.delete(key);
      else params.set(key, String(value));
    }
    setSearch(params);
  };

  const select = (entityId: string | null) => {
    const params = new URLSearchParams(search);
    if (entityId) params.set("selected", entityId);
    else params.delete("selected");
    setSearch(params);
  };

  return {
    window,
    selection: { entityId: search.get("selected") ?? undefined },
    setWindow,
    select,
  };
}

/** Carry the shared window from one surface's URL to another's. */
export function withSharedParams(path: string, search: URLSearchParams): string {
  const carried = new URLSearchParams();
  for (const key of ["from", "to", "asOf", "asOfRevision", "selected"]) {
    const value = search.get(key);
    if (value) carried.set(key, value);
  }
  const query = carried.toString();
  return query ? `${path}?${query}` : path;
}

export function TimeFilter({ testId = "time-filter" }: { testId?: string }) {
  const { window, setWindow } = useSharedFilter();

  return (
    <form
      className="map__filter"
      data-testid={testId}
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const read = (name: string) => {
          const value = String(form.get(name) ?? "");
          return value ? new Date(value).toISOString() : undefined;
        };
        setWindow({ ...window, from: read("from"), to: read("to") });
      }}
    >
      <label>
        <span>From</span>
        <input type="date" name="from" defaultValue={window.from?.slice(0, 10)} data-testid={`${testId}-from`} />
      </label>
      <label>
        <span>To</span>
        <input type="date" name="to" defaultValue={window.to?.slice(0, 10)} data-testid={`${testId}-to`} />
      </label>
      <button type="submit" data-testid={`${testId}-apply`}>
        Apply
      </button>
      {(window.from || window.to) && (
        <button
          type="button"
          data-testid={`${testId}-clear`}
          onClick={() => setWindow({ ...window, from: undefined, to: undefined })}
        >
          All time
        </button>
      )}
    </form>
  );
}

/**
 * The links between surfaces, carrying the window and the selection.
 *
 * Rendered on all three so moving between them is a click rather than a
 * re-narrowing — which is also what makes "narrowing the filter updates all
 * three consistently" something a person can actually check.
 */
export function SurfaceLinks({ current }: { current: "map" | "timeline" | "graph" }) {
  const [search] = useSearchParams();
  const links = [
    { key: "map", path: "/map", label: "Map" },
    { key: "timeline", path: "/timeline", label: "Timeline" },
    { key: "graph", path: "/graph", label: "Graph" },
  ] as const;

  return (
    <nav className="surface-links" data-testid="surface-links">
      {links.map((link) => (
        <a
          key={link.key}
          href={withSharedParams(link.path, search)}
          aria-current={link.key === current ? "page" : undefined}
          data-testid={`surface-link-${link.key}`}
        >
          {link.label}
        </a>
      ))}
    </nav>
  );
}
