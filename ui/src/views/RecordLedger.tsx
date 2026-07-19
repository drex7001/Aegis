import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  ApiError,
  extractRecord,
  listDerivatives,
  listSourceRecords,
  listSuggestions,
  releaseRecord,
  type SourceRecord,
} from "../api/client";
import { Digest } from "./Digest";

/**
 * The register of what has landed, and the per-record work that follows it
 * (spec 04 §1 stages 3–4).
 *
 * Only the exceptional state is marked. A quarantined record carries the same
 * left rail the workspace already uses for a notice — the device means "this
 * needs you" and nothing else — while a landed record carries the same
 * geometry with no colour at all. Colouring the normal case would make the
 * register harder to scan and would say nothing.
 */
export function RecordLedger() {
  const [openId, setOpenId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  const records = useInfiniteQuery({
    queryKey: ["source-records", statusFilter],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      listSourceRecords({
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(pageParam ? { cursor: pageParam } : {}),
      }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const rows = records.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <section className="ledger" aria-labelledby="ledger-heading">
      <header className="ledger__head">
        <h2 id="ledger-heading">Landed records</h2>
        <label className="ledger__filter">
          <span className="muted">Show</span>
          <select
            value={statusFilter}
            data-testid="ledger-filter"
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="">Everything</option>
            <option value="landed">Landed</option>
            <option value="quarantined">Quarantined</option>
            <option value="processed">Processed</option>
          </select>
        </label>
      </header>

      {records.isPending && <p className="muted">Loading records…</p>}
      {records.error && (
        <p className="outcome outcome--error" role="alert">
          {records.error instanceof ApiError
            ? records.error.message
            : "Records could not be loaded."}
        </p>
      )}
      {records.data && rows.length === 0 && (
        <p className="empty" data-testid="ledger-empty">
          Nothing landed yet. Upload a file or paste text to add the first record.
        </p>
      )}

      <ul className="records" data-testid="ledger">
        {rows.map((record) => (
          <Row
            key={record.record_id}
            record={record}
            open={openId === record.record_id}
            onToggle={() =>
              setOpenId(openId === record.record_id ? null : record.record_id)
            }
          />
        ))}
      </ul>
      {records.hasNextPage && (
        <button
          type="button"
          className="button"
          disabled={records.isFetchingNextPage}
          onClick={() => void records.fetchNextPage()}
        >
          {records.isFetchingNextPage ? "Loading…" : "Load more"}
        </button>
      )}
    </section>
  );
}

function Row({
  record,
  open,
  onToggle,
}: {
  record: SourceRecord;
  open: boolean;
  onToggle: () => void;
}) {
  const filename = String(record.provenance?.["original_filename"] ?? record.record_id);
  const held = record.status === "quarantined";

  return (
    <li className={`record${held ? " record--held" : ""}`} data-testid="record">
      <button
        type="button"
        className="record__summary"
        aria-expanded={open}
        onClick={onToggle}
      >
        <span className="record__name">{filename}</span>
        <span className="record__meta">
          {held && (
            <span className="chip chip--held" data-testid="record-status">
              quarantined
            </span>
          )}
          <span className="muted">{record.media_type ?? "unknown type"}</span>
          <time className="muted" dateTime={record.received_at}>
            {new Date(record.received_at).toLocaleDateString(undefined, {
              day: "numeric",
              month: "short",
            })}
          </time>
          <Digest hash={record.content_hash} />
        </span>
      </button>

      {held && (
        <p className="record__reason" data-testid="record-reason">
          {record.quarantine_reason}
        </p>
      )}

      {open && <Detail record={record} />}
    </li>
  );
}

function Detail({ record }: { record: SourceRecord }) {
  const provenance = (record.provenance ?? {}) as Record<string, unknown>;
  const url = provenance["source_url"] as string | undefined;

  return (
    <div className="detail">
      <dl className="detail__facts">
        <Fact label="Landed">{new Date(record.received_at).toLocaleString()}</Fact>
        <Fact label="Handling">{record.handling_code}</Fact>
        <Fact label="Collected by">{String(provenance["operator"] ?? "—")}</Fact>
        <Fact label="Connector">
          {String(provenance["connector"] ?? "—")}{" "}
          {String(provenance["connector_version"] ?? "")}
        </Fact>
        <Fact label="Collected from">
          {url ? (
            // No referrer to the collection target, and no window handle back.
            <a href={url} target="_blank" rel="noreferrer noopener">
              {url}
            </a>
          ) : (
            "—"
          )}
        </Fact>
        <Fact label="Collection policy">
          {record.collection_policy_ref ?? "—"}
        </Fact>
        {record.retention_class != null && (
          <Fact label="Retention class">{record.retention_class}</Fact>
        )}
        {record.authority_ref != null && (
          <Fact label="Legal authority">{record.authority_ref}</Fact>
        )}
        {(record.authority_valid_from != null || record.authority_valid_to != null) && (
          <Fact label="Authority validity">
            {record.authority_valid_from
              ? new Date(record.authority_valid_from).toLocaleDateString()
              : "open"}
            {" — "}
            {record.authority_valid_to
              ? new Date(record.authority_valid_to).toLocaleDateString()
              : "open"}
          </Fact>
        )}
        {provenance["notes"] != null && (
          <Fact label="Notes">{String(provenance["notes"])}</Fact>
        )}
      </dl>

      {record.status === "quarantined" ? (
        <Release record={record} />
      ) : (
        <Extraction record={record} />
      )}
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

/**
 * Releasing is a supervisor's action. The button is shown to everyone and the
 * API decides: hiding it by reading a role claim would put an authorization
 * decision in the bundle, where it is advice rather than enforcement
 * (Article VI). A refusal here is the API's answer, rendered.
 */
function Release({ record }: { record: SourceRecord }) {
  const queryClient = useQueryClient();
  const release = useMutation({
    mutationFn: () => releaseRecord(record.record_id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["source-records"] });
    },
  });

  return (
    <div className="detail__action">
      <p className="muted">
        Held for review. Releasing it records who decided, and lets extraction run.
      </p>
      <button
        type="button"
        className="button"
        data-testid="record-release"
        disabled={release.isPending}
        onClick={() => release.mutate()}
      >
        {release.isPending ? "Releasing…" : "Release from quarantine"}
      </button>
      {release.error && (
        <p className="outcome outcome--error" role="alert" data-testid="release-error">
          {release.error instanceof ApiError
            ? release.error.message
            : "The record could not be released."}
        </p>
      )}
    </div>
  );
}

/**
 * Derivative + extraction, the two stages between a landed artifact and
 * something a reviewer can act on.
 *
 * The count of queued suggestions is read back from the review queue rather
 * than kept from the mutation's reply, so the number on screen is the queue's
 * state and not this tab's memory of it.
 */
function Extraction({ record }: { record: SourceRecord }) {
  const [producer, setProducer] = useState<"structural" | "semantic">("structural");
  const queryClient = useQueryClient();

  const derivatives = useQuery({
    queryKey: ["derivatives", record.record_id],
    queryFn: () => listDerivatives(record.record_id),
  });
  const suggestions = useQuery({
    queryKey: ["suggestions", record.record_id],
    queryFn: () => listSuggestions({ record: record.record_id }),
  });

  const extract = useMutation({
    mutationFn: () => extractRecord(record.record_id, { producer, mock: producer === "semantic" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["derivatives", record.record_id] });
      void queryClient.invalidateQueries({ queryKey: ["suggestions", record.record_id] });
    },
  });

  const queued = suggestions.data?.items.filter((s) => s.status === "suggested").length ?? 0;

  return (
    <div className="detail__action">
      <h3>Extraction</h3>

      <p className="detail__line" data-testid="record-derivative">
        {derivatives.data === undefined
          ? "Checking for a text derivative…"
          : derivatives.data.length === 0
            ? "No derivative recorded. Text is read from the record itself."
            : derivatives.data
                .map((d) => `${d.kind} derivative · ${d.tool} ${d.tool_version}`)
                .join(", ")}
      </p>

      <div className="inline-create">
        <label className="field__label">
          <span className="field__name">Producer</span>
          <select
            value={producer}
            data-testid="extract-producer"
            onChange={(event) =>
              setProducer(event.target.value as "structural" | "semantic")
            }
          >
            <option value="structural">Structural — deterministic rules</option>
            {/* Named for what it actually runs. The browser has no model
                credentials, so offering "semantic" here and quietly running the
                mock would put a fiction in producer_meta's neighbourhood. A
                real model pass runs from `aegis ingest extract --producer
                semantic`, with credentials, off the request path. */}
            <option value="semantic">Semantic — offline mock extractor</option>
          </select>
        </label>
        <button
          type="button"
          className="button button--primary"
          data-testid="record-extract"
          disabled={extract.isPending}
          onClick={() => extract.mutate()}
        >
          {extract.isPending ? "Extracting…" : "Extract"}
        </button>
      </div>

      {/* Article VII, stated where the action is taken rather than in a doc. */}
      <p className="field__hint">
        Extraction proposes. Nothing is recorded until a reviewer accepts it.
      </p>

      {extract.error && (
        <p className="outcome outcome--error" role="alert" data-testid="extract-error">
          {extract.error instanceof ApiError
            ? extract.error.message
            : "Extraction could not run."}
        </p>
      )}

      <p className="detail__line" data-testid="record-suggestions">
        {queued === 0
          ? "No suggestions waiting for review."
          : `${queued} suggestion${queued === 1 ? "" : "s"} waiting for review.`}
      </p>
    </div>
  );
}
