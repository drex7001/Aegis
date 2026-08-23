import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import {
  getFinding,
  getVocabulary,
  listFindings,
  listObjectSets,
  runAnalytic,
  type AnalyticFinding,
  type AnalyticRun,
} from "../api/client";
import { entityPath } from "../routing";

/**
 * The findings panel (T73, spec 12 §9).
 *
 * One rule shapes this file, and it is structural rather than stylistic:
 * **there is no caveat-free rendering path.** `Finding` takes the caveat from
 * the finding row and renders it unconditionally — not from a lookup table, not
 * behind a disclosure, not conditional on the metric. A caveat fetched from a
 * catalog would be a caveat that can fail to arrive; a caveat behind a
 * "details" toggle would be a caveat nobody reads.
 *
 * The metric *labels* do come from the server (`analytic_metrics` on the
 * vocabulary route), because a label for a machine's reading of a graph is
 * exactly the wording Article IX cares about — and a hand-written map in
 * TypeScript is where "most connected" quietly becomes "most important".
 *
 * A finding always renders **with its manifest**. A number whose provenance a
 * reader has to go and look for is a number nobody checks.
 */

export function Findings() {
  const queryClient = useQueryClient();
  const vocabulary = useQuery({ queryKey: ["vocabulary"], queryFn: getVocabulary });
  const [purpose, setPurpose] = useState("");
  const [metric, setMetric] = useState("degree");
  const [setId, setSetId] = useState("");
  const [opened, setOpened] = useState<string | null>(null);

  const findings = useQuery({ queryKey: ["findings"], queryFn: () => listFindings() });
  const sets = useQuery({ queryKey: ["object-sets"], queryFn: () => listObjectSets() });
  const detail = useQuery({
    queryKey: ["finding", opened],
    queryFn: () => getFinding(opened as string),
    enabled: Boolean(opened),
  });

  const run = useMutation({
    mutationFn: () =>
      runAnalytic(metric, purpose.trim(), setId ? { object_set_id: setId } : {}),
    onSuccess: () => {
      setPurpose("");
      void queryClient.invalidateQueries({ queryKey: ["findings"] });
    },
  });

  const metrics = vocabulary.data?.analytic_metrics ?? [];

  return (
    <section className="panel" data-testid="findings-panel">
      <h2>Findings</h2>
      <p className="muted">
        A finding is a reading of what has been <strong>written down</strong>,
        not an assertion about the world. Every one carries the caveat it was
        issued with, and none of them is a claim.
      </p>

      <form
        className="findings__form"
        onSubmit={(event) => {
          event.preventDefault();
          if (purpose.trim()) run.mutate();
        }}
      >
        <label className="field">
          <span>Metric</span>
          <select
            value={metric}
            onChange={(event) => setMetric(event.target.value)}
            data-testid="metric-select"
          >
            {metrics.map((entry) => (
              <option key={entry.metric} value={entry.metric}>
                {entry.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Over</span>
          <select
            value={setId}
            onChange={(event) => setSetId(event.target.value)}
            data-testid="scope-select"
          >
            <option value="">Everything you can read</option>
            {sets.data?.items.map((row) => (
              <option key={row.set_id} value={row.set_id}>
                {row.name}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>
            Purpose <small className="muted">— recorded in the audit trail</small>
          </span>
          <input
            value={purpose}
            onChange={(event) => setPurpose(event.target.value)}
            data-testid="run-purpose"
          />
        </label>

        <button
          type="submit"
          className="button"
          disabled={!purpose.trim() || run.isPending}
          data-testid="run-metric"
        >
          {run.isPending ? "Running…" : "Run and record"}
        </button>
      </form>

      {findings.data?.items.length === 0 && (
        <p className="muted" data-testid="no-findings">
          No findings you can see.
        </p>
      )}

      <ul className="findings__list" data-testid="findings-list">
        {findings.data?.items.map((finding) => (
          <li key={finding.finding_id}>
            <Finding
              finding={finding}
              label={
                metrics.find((entry) => entry.metric === finding.finding_type)?.label ??
                finding.finding_type
              }
              onOpen={() => setOpened(finding.finding_id)}
            />
          </li>
        ))}
      </ul>

      {opened && detail.data && <Manifest run={detail.data.run} />}
    </section>
  );
}

/**
 * One finding.
 *
 * The caveat is not optional, not collapsible and not conditional. It comes
 * from `finding.caveat_text` — the row — so there is no path through this
 * component that renders a value without the sentence that says how to read
 * it (spec 12 §9.3).
 */
function Finding({
  finding,
  label,
  onOpen,
}: {
  finding: AnalyticFinding;
  label: string;
  onOpen: () => void;
}) {
  return (
    <article className="findings__finding" data-testid={`finding-${finding.finding_id}`}>
      <header>
        <strong data-testid={`finding-label-${finding.finding_id}`}>{label}</strong>
        <span className="muted"> {finding.handling_code}</span>
      </header>

      <dl className="findings__value">
        {Object.entries(finding.value).map(([key, value]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd data-testid={`finding-value-${key}`}>{String(value)}</dd>
          </div>
        ))}
      </dl>

      <ul className="findings__subjects">
        {finding.subjects.map((entityId) => (
          <li key={entityId}>
            <Link to={entityPath(entityId)}>{entityId}</Link>
          </li>
        ))}
      </ul>

      <p className="findings__caveat" data-testid={`caveat-${finding.finding_id}`}>
        {finding.caveat_text}
      </p>

      <button
        type="button"
        className="button button--quiet"
        onClick={onOpen}
        data-testid={`open-${finding.finding_id}`}
      >
        How this was computed
      </button>
    </article>
  );
}

/**
 * The run manifest, rendered as what it is: the answer to "can I trust this
 * number, and can I get it again".
 *
 * `authorization_digest` is shown because it is the field that explains a
 * disagreement. Two analysts running one metric on one corpus under different
 * clearances get different findings, correctly — and without this on screen,
 * that reads as the system contradicting itself.
 */
function Manifest({ run }: { run: AnalyticRun }) {
  const rows: Array<[string, string]> = [
    ["Method", `${run.method} (${run.method_version})`],
    ["Implementation", run.implementation],
    ["Seed", run.seed === null ? "unseeded" : String(run.seed)],
    ["Input", run.object_set_id ? `set ${run.object_set_id} v${run.object_set_version}` : "the readable graph"],
    ["Evaluated members", run.evaluation_digest?.slice(0, 12) ?? "—"],
    ["Edges read", run.edge_digest.slice(0, 12)],
    ["Projection built at revision", String(run.projection_built_at_revision_id ?? "—")],
    ["Projection builder", run.projection_builder_version ?? "—"],
    ["Ontology", run.ontology_version],
    ["Identity revision", String(run.identity_revision_id)],
    ["Code", run.code_version],
    ["Authorization", run.authorization_digest.slice(0, 12)],
    ["Ran by", run.actor],
    ["Purpose", run.purpose ?? "—"],
  ];

  return (
    <div className="panel panel--nested" data-testid="finding-manifest">
      <h3>How this was computed</h3>
      <p className="muted">
        Two runs whose manifests agree produce the same finding. A different
        clearance is a different manifest — so two analysts can correctly
        disagree, and this is where you see why.
      </p>
      <dl className="findings__manifest">
        {rows.map(([term, value]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd data-testid={`manifest-${term.toLowerCase().replace(/\s+/g, "-")}`}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
