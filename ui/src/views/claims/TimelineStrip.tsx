import type { ClaimProvenance } from "../../api/client";
import { predicateLabel } from "./ClaimGroup";

/**
 * A compact strip of an entity's claims over time (T45, spec 09 §7).
 *
 * The whole design problem here is **honesty about what is not known**, and
 * three rules follow from it:
 *
 * 1. **Uncertainty renders as an interval, not a point.** A source that said
 *    "some time in 2019" stated a range, and drawing it at 1 January would
 *    invent precision nobody asserted. `event_time_earliest` and
 *    `event_time_latest` are rendered as a span; equal values as an instant.
 * 2. **A claim with no stated time says so.** It is *not* placed at
 *    `recorded_at` — when we wrote something down is a fact about us, not
 *    about the world, and putting it on a world-time axis silently converts
 *    one into the other. Untimed claims are listed apart, below the axis.
 * 3. **Nothing is inferred.** No midpoint, no "circa", no interpolation
 *    between neighbouring claims.
 *
 * T49 grows this into the full timeline with as-of; the shape it needs is the
 * same, so the time model lives here rather than in the object view.
 */

export type Extent = { from: number; to: number };

export interface TimedClaim {
  entry: ClaimProvenance;
  /** Milliseconds since epoch; equal when the claim states an instant. */
  from: number;
  to: number;
  exact: boolean;
}

/** Split claims into those that state a world time and those that do not. */
export function partitionByTime(claims: ClaimProvenance[]): {
  timed: TimedClaim[];
  untimed: ClaimProvenance[];
} {
  const timed: TimedClaim[] = [];
  const untimed: ClaimProvenance[] = [];
  for (const entry of claims) {
    const { event_time_earliest, event_time_latest, valid_from, valid_to } = entry.claim;
    // Event time first: it is when the thing happened. Validity is the fallback
    // because "held this passport from X to Y" is also a statement about the
    // world, unlike `recorded_at`, which never is.
    const earliest = event_time_earliest ?? valid_from ?? null;
    const latest = event_time_latest ?? valid_to ?? earliest;
    if (earliest === null) {
      untimed.push(entry);
      continue;
    }
    const from = Date.parse(earliest);
    const to = latest === null ? from : Date.parse(latest);
    if (Number.isNaN(from) || Number.isNaN(to)) {
      untimed.push(entry);
      continue;
    }
    timed.push({ entry, from, to: Math.max(from, to), exact: from === to });
  }
  timed.sort((a, b) => a.from - b.from || a.to - b.to);
  return { timed, untimed };
}

export function extentOf(timed: TimedClaim[]): Extent | null {
  if (timed.length === 0) return null;
  const from = Math.min(...timed.map((item) => item.from));
  const to = Math.max(...timed.map((item) => item.to));
  // A single instant has no width. Give the axis a nominal day so the marker
  // has somewhere to sit, rather than dividing by zero and rendering nothing.
  return from === to ? { from, to: from + 86_400_000 } : { from, to };
}

function percent(value: number, extent: Extent): number {
  return ((value - extent.from) / (extent.to - extent.from)) * 100;
}

function label(item: TimedClaim): string {
  const from = new Date(item.from).toISOString().slice(0, 10);
  if (item.exact) return from;
  return `${from} → ${new Date(item.to).toISOString().slice(0, 10)}`;
}

export function TimelineStrip({ claims }: { claims: ClaimProvenance[] }) {
  const { timed, untimed } = partitionByTime(claims);
  const extent = extentOf(timed);

  return (
    <div className="timeline" data-testid="timeline-strip">
      {extent === null ? (
        <p className="notice" data-testid="timeline-empty">
          No claim here states when it happened.
        </p>
      ) : (
        <>
          <div className="timeline__axis" aria-hidden="true">
            <span>{new Date(extent.from).toISOString().slice(0, 10)}</span>
            <span>{new Date(extent.to).toISOString().slice(0, 10)}</span>
          </div>
          <ul className="timeline__rows">
            {timed.map((item) => (
              <li key={item.entry.claim.claim_id} className="timeline__row">
                <span className="timeline__label">
                  {predicateLabel(item.entry.claim.predicate)}
                </span>
                <span className="timeline__track">
                  <span
                    className={`timeline__bar${item.exact ? " timeline__bar--exact" : ""}`}
                    data-testid={`timeline-${item.entry.claim.claim_id}`}
                    data-exact={item.exact ? "true" : "false"}
                    style={{
                      left: `${percent(item.from, extent)}%`,
                      // An instant gets a fixed hairline rather than a
                      // proportional width, so it cannot be mistaken for a
                      // very short interval.
                      width: item.exact
                        ? undefined
                        : `${Math.max(percent(item.to, extent) - percent(item.from, extent), 1)}%`,
                    }}
                    title={label(item)}
                  />
                </span>
                <span className="timeline__when muted">{label(item)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {untimed.length > 0 && (
        <p className="muted timeline__untimed" data-testid="timeline-untimed">
          {untimed.length} claim{untimed.length === 1 ? "" : "s"} state
          {untimed.length === 1 ? "s" : ""} no time.{" "}
          {/* Said out loud rather than shown at `recorded_at`: when we wrote
              something down is a fact about us, not about the world. */}
          When a claim was recorded is not when it happened, so they are not
          placed on this axis.
        </p>
      )}
    </div>
  );
}
