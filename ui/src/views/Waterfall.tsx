import type { IdentityCandidate } from "../api/client";

/**
 * Why the machine thinks these two are the same person.
 *
 * The shape of `features` depends on the producer, so this reads it rather than
 * assuming: a rule writes `{rule, predicate, …}`, Splink writes `gamma_`/`bf_`/
 * `tf_` per compared column. Rendering a single number instead would be the one
 * thing a reviewer cannot check — and checking it is the job (GOAL.md §10.4).
 *
 * For Splink, `bf_x` is a Bayes factor: above 1 the column argues *for* the
 * match, below 1 it argues *against*. That is why the scale runs both ways from
 * a centre line rather than left-to-right — a pair can be strong on name and
 * actively contradicted on date of birth, and a one-directional bar would show
 * only the half that agrees.
 */
export function Waterfall({ candidate }: { candidate: IdentityCandidate }) {
  const features = candidate.features as Record<string, unknown>;
  const rule = String(features["rule"] ?? "unknown");

  return (
    <div className="waterfall" data-testid="candidate-waterfall">
      <p className="waterfall__producer">
        <span className="mono">{candidate.producer}</span>
        <span className="muted"> {candidate.producer_version}</span>
        {candidate.graph_snapshot_id && (
          <span className="muted"> · graph {candidate.graph_snapshot_id}</span>
        )}
      </p>
      {rule === "splink" ? (
        <SplinkRungs features={features} />
      ) : (
        <RuleFacts features={features} />
      )}
    </div>
  );
}

interface Rung {
  column: string;
  bayesFactor: number;
  gamma: number | null;
  termFrequency: number | null;
}

/**
 * Regroup the flat `bf_x` / `gamma_x` / `tf_x` keys by the column they describe.
 * The API ships them flat because that is how they were persisted; flattening
 * is the storage shape, not the reading shape.
 */
export function toRungs(features: Record<string, unknown>): Rung[] {
  const columns = new Map<string, Partial<Rung>>();
  for (const [key, value] of Object.entries(features)) {
    const match = /^(bf|gamma|tf)_(.+)$/.exec(key);
    if (!match) continue;
    const [, kind, column] = match;
    if (column === undefined || kind === undefined) continue;
    const entry = columns.get(column) ?? { column };
    if (kind === "bf") entry.bayesFactor = Number(value);
    if (kind === "gamma") entry.gamma = Number(value);
    if (kind === "tf") entry.termFrequency = Number(value);
    columns.set(column, entry);
  }
  return [...columns.values()]
    .filter((entry): entry is Rung => typeof entry.bayesFactor === "number")
    .map((entry) => ({
      column: entry.column,
      bayesFactor: entry.bayesFactor,
      gamma: entry.gamma ?? null,
      termFrequency: entry.termFrequency ?? null,
    }))
    .sort((a, b) => Math.abs(Math.log10(b.bayesFactor)) - Math.abs(Math.log10(a.bayesFactor)));
}

function SplinkRungs({ features }: { features: Record<string, unknown> }) {
  const rungs = toRungs(features);
  if (rungs.length === 0) {
    return <p className="muted">This candidate carries no per-feature explanation.</p>;
  }

  return (
    <ul className="waterfall__rungs">
      {rungs.map((rung) => {
        const supports = rung.bayesFactor >= 1;
        // Log scale, because Bayes factors span orders of magnitude: on a
        // linear bar a 12× and a 200× look equally decisive.
        const magnitude = Math.min(Math.abs(Math.log10(rung.bayesFactor)) / 3, 1);
        return (
          <li key={rung.column} className="rung" data-testid="waterfall-rung">
            <span className="rung__column">{rung.column.replace(/_/g, " ")}</span>
            <span className="rung__scale" aria-hidden="true">
              <span
                className={`rung__bar rung__bar--${supports ? "for" : "against"}`}
                style={{ width: `${Math.max(magnitude * 50, 2)}%` }}
              />
            </span>
            <span className="rung__value mono">
              {rung.bayesFactor >= 1
                ? `×${rung.bayesFactor.toFixed(1)}`
                : `÷${(1 / rung.bayesFactor).toFixed(1)}`}
            </span>
            <span className="rung__reading muted">
              {supports ? "supports" : "argues against"}
              {rung.gamma !== null && ` · level ${rung.gamma}`}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function RuleFacts({ features }: { features: Record<string, unknown> }) {
  const entries = Object.entries(features).filter(([key]) => key !== "rule");
  return (
    <dl className="waterfall__facts">
      <dt>Rule</dt>
      <dd className="mono">{String(features["rule"])}</dd>
      {entries.map(([key, value]) => (
        <FactRow key={key} label={key.replace(/_/g, " ")} value={value} />
      ))}
    </dl>
  );
}

function FactRow({ label, value }: { label: string; value: unknown }) {
  return (
    <>
      <dt>{label}</dt>
      <dd className={Array.isArray(value) ? "" : "mono"}>
        {Array.isArray(value) ? value.join(", ") : String(value)}
      </dd>
    </>
  );
}
