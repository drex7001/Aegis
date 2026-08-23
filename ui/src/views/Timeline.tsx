import { useQuery } from "@tanstack/react-query";

import { getTimeline, type TimelineItem } from "../api/client";
import { entityPath } from "../routing";
import { predicateLabel } from "./claims/ClaimGroup";
import { SurfaceLinks, TimeFilter, useSharedFilter } from "./TimeFilter";

/**
 * The timeline (T61, spec 10 §11).
 *
 * **Items are claims**, not events. An event appears through the claims that
 * assert it, which is what makes "no duplicates" structural rather than a
 * de-duplication pass: there is only ever one row per assertion, and an arrest
 * with three arrestees is four rows because four things were asserted.
 *
 * Certainty is rendered, never resolved:
 *
 * * `exact` — the source stated an instant. A hairline.
 * * `bounded` — the source stated a range. A bar the width of the range, and
 *   **not** a marker at its midpoint: "some time in March" placed at 15 March
 *   is a precision nobody asserted.
 * * `open` — one bound. A bar that fades out at the unknown end.
 * * `undated` — counted and named below the axis. Never placed at
 *   `recorded_at`, because when we wrote something down is a fact about us and
 *   the axis is about the world.
 *
 * The window lives in the URL and is the same `from`/`to` the map reads, which
 * is what T62 composes into one filter across three surfaces.
 */

const CERTAINTY_LABEL: Record<string, string> = {
  exact: "stated exactly",
  bounded: "stated as a range",
  open: "open-ended",
  undated: "no time stated",
};

function bounds(items: TimelineItem[]): { from: number; to: number } | null {
  const stamps = items
    .flatMap((item) => [item.earliest, item.latest])
    .filter((value): value is string => Boolean(value))
    .map((value) => Date.parse(value))
    .filter((value) => !Number.isNaN(value));
  if (stamps.length === 0) return null;
  const from = Math.min(...stamps);
  const to = Math.max(...stamps);
  // A single instant has no width; give the axis a nominal day so the marker
  // has somewhere to sit rather than dividing by zero.
  return from === to ? { from, to: from + 86_400_000 } : { from, to };
}

function placement(item: TimelineItem, extent: { from: number; to: number }) {
  const span = extent.to - extent.from;
  const earliest = item.earliest ? Date.parse(item.earliest) : null;
  const latest = item.latest ? Date.parse(item.latest) : null;
  const start = earliest ?? latest ?? extent.from;
  const end = latest ?? earliest ?? extent.from;
  const left = ((start - extent.from) / span) * 100;
  const width = Math.max(((end - start) / span) * 100, 0.6);
  return { left, width };
}

function describe(item: TimelineItem): string {
  const day = (value: string | null | undefined) =>
    value ? new Date(value).toISOString().slice(0, 10) : "?";
  switch (item.certainty) {
    case "exact":
      return day(item.earliest);
    case "bounded":
      return `${day(item.earliest)} → ${day(item.latest)}`;
    case "open":
      return item.earliest ? `after ${day(item.earliest)}` : `before ${day(item.latest)}`;
    default:
      return "no time stated";
  }
}

export function Timeline() {
  // The same window and the same selection the map and graph read (T62).
  const { window: shared, selection, select } = useSharedFilter();
  const { from, to, asOf } = shared;
  const entityId = selection.entityId;

  const query = useQuery({
    queryKey: ["timeline", from ?? null, to ?? null, entityId ?? null, asOf ?? null],
    queryFn: () => getTimeline({ from, to, entityId, asOf, limit: 200 }),
  });

  const items = query.data?.items ?? [];
  const extent = bounds(items);

  return (
    <section className="timeline-view" data-testid="timeline-view">
      <header className="map__header">
        <h1>Timeline</h1>
        <TimeFilter testId="timeline-filter" />
        <SurfaceLinks current="timeline" />
      </header>

      {entityId && (
        <p className="notice" data-testid="timeline-selection">
          Showing only what involves the selected entity.{" "}
          <button type="button" onClick={() => select(null)} data-testid="timeline-clear-selection">
            Show everything
          </button>
        </p>
      )}

      {query.data?.stamp && (
        <p className="muted" data-testid="timeline-stamp">
          Ontology {query.data.stamp.ontology_version} · identity revision{" "}
          {query.data.stamp.identity_revision_id}
          {asOf ? ` · as of ${asOf}` : ""}
        </p>
      )}

      {query.isPending && <p className="notice">Loading…</p>}

      {!query.isPending && extent === null && (
        <p className="notice" data-testid="timeline-view-empty">
          Nothing you are cleared to see states when it happened.
        </p>
      )}

      {extent !== null && (
        <>
          <div className="timeline__axis" aria-hidden="true">
            <span>{new Date(extent.from).toISOString().slice(0, 10)}</span>
            <span>{new Date(extent.to).toISOString().slice(0, 10)}</span>
          </div>
          <ul className="timeline__rows" data-testid="timeline-items">
            {items
              .filter((item) => item.certainty !== "undated")
              .map((item) => {
                const { left, width } = placement(item, extent);
                return (
                  <li
                    key={item.claim_id}
                    className="timeline__row"
                    data-testid={`timeline-item-${item.claim_id}`}
                    data-certainty={item.certainty}
                    data-selected={
                      item.subject_id === selection.entityId ||
                      item.object_id === selection.entityId
                        ? "true"
                        : undefined
                    }
                  >
                    <span className="timeline__label">
                      <a href={entityPath(item.subject_id)}>
                        {item.subject_label ?? item.subject_id}
                      </a>{" "}
                      <span className="muted">{predicateLabel(item.predicate)}</span>
                    </span>
                    <span className="timeline__track">
                      <span
                        className={`timeline__bar timeline__bar--${item.certainty}`}
                        style={{
                          left: `${left}%`,
                          // An exact claim gets a hairline rather than a
                          // proportional width, so it can never be mistaken
                          // for a very short interval.
                          width: item.certainty === "exact" ? undefined : `${width}%`,
                        }}
                        title={`${describe(item)} — ${CERTAINTY_LABEL[item.certainty]}`}
                      />
                    </span>
                    <span className="timeline__when muted">{describe(item)}</span>
                  </li>
                );
              })}
          </ul>
        </>
      )}

      {(query.data?.undated_count ?? 0) > 0 && (
        <p className="muted timeline__untimed" data-testid="timeline-view-undated">
          {query.data?.undated_count} claim
          {query.data?.undated_count === 1 ? "" : "s"} you can see state no time at all.
          {/*
            * Counted and named rather than dropped. A narrowed window that
            * silently omitted them would look like a complete account of
            * everything known, which is the failure this line exists against
            * (spec 10 §11.2).
            */}{" "}
          They are not placed on this axis: when a claim was recorded is not when
          it happened.
        </p>
      )}
    </section>
  );
}
