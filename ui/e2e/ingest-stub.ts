import { createHash } from "node:crypto";

import type { Page, Route } from "@playwright/test";

/**
 * A stand-in for the ingestion API that keeps its *rules*, not just its shapes.
 *
 * A stub that answered every landing with "landed" would let the journey pass
 * while the screen was incapable of telling an operator that nothing happened.
 * So this one is content-addressed the way the real service is: the same bytes
 * under the same name are a no-op, a different body under a used name is a
 * version conflict, and extraction only runs on a record that is not held.
 * Those are the behaviours T23a's acceptance criteria are about, so they are
 * the behaviours the fake has to have.
 *
 * It is not a second implementation of the service — it has no vault, no audit
 * log and no authorization — and the tests that prove those live in
 * `tests/integration/test_ingest_routes.py`, against the real thing.
 */

export interface LandedRecord {
  record_id: string;
  source_id: string;
  content_hash: string;
  media_type: string | null;
  status: string;
  quarantine_reason: string | null;
  handling_code: string;
  received_at: string;
  provenance: Record<string, unknown>;
}

export interface IngestStub {
  records(): LandedRecord[];
  /** `Authorization` headers seen, in call order. */
  bearerTokens(): string[];
}

interface Part {
  name: string;
  filename?: string;
  body: Buffer;
}

/**
 * Enough multipart parsing to read one small upload.
 *
 * `latin1` is a byte-preserving round trip, so splitting on the boundary as
 * text does not corrupt the binary body the way `utf8` would.
 */
function parseMultipart(buffer: Buffer, contentType: string): Part[] {
  const marker = contentType.split("boundary=")[1];
  if (!marker) return [];
  const raw = buffer.toString("latin1");
  const parts: Part[] = [];

  for (const chunk of raw.split(`--${marker}`)) {
    const split = chunk.indexOf("\r\n\r\n");
    if (split === -1) continue;
    const headers = chunk.slice(0, split);
    const name = /name="([^"]*)"/.exec(headers)?.[1];
    if (!name) continue;
    parts.push({
      name,
      filename: /filename="([^"]*)"/.exec(headers)?.[1],
      // The body is terminated by the CRLF that precedes the next boundary.
      body: Buffer.from(chunk.slice(split + 4).replace(/\r\n$/, ""), "latin1"),
    });
  }
  return parts;
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

export async function stubIngest(page: Page): Promise<IngestStub> {
  const records: LandedRecord[] = [];
  const derivatives = new Map<string, Array<Record<string, unknown>>>();
  const suggestions = new Map<string, Array<Record<string, unknown>>>();
  const bearers: string[] = [];
  let counter = 0;

  const track = async (route: Route) => {
    const headers = await route.request().allHeaders();
    if (headers["authorization"]) bearers.push(headers["authorization"]);
  };

  function land(
    data: Buffer,
    filename: string,
    mediaType: string | null,
    form: Record<string, string>,
  ) {
    const contentHash = createHash("sha256").update(data).digest("hex");
    const existing = records.find(
      (row) => row.provenance["original_filename"] === filename,
    );

    if (existing && existing.content_hash === contentHash) {
      return { outcome: "already_landed", record: existing };
    }

    const conflict = existing !== undefined;
    const record: LandedRecord = {
      record_id: `rec_stub_${++counter}`,
      source_id: form["source_id"] || "src_manual_upload",
      content_hash: contentHash,
      media_type: mediaType,
      status: conflict ? "quarantined" : "landed",
      quarantine_reason: conflict
        ? `version conflict: 1 earlier record(s) of '${filename}' with different content`
        : null,
      handling_code: form["handling_code"] || "open",
      received_at: new Date().toISOString(),
      provenance: {
        source_system: "manual-upload",
        original_filename: filename,
        connector: "aegis.ingestion",
        connector_version: "0.1.0",
        operator: "0d3f4d3a-fictional-subject",
        ...(form["source_url"] ? { source_url: form["source_url"] } : {}),
        ...(form["collection_policy"]
          ? { collection_policy: form["collection_policy"] }
          : {}),
        ...(form["notes"] ? { notes: form["notes"] } : {}),
      },
    };
    records.unshift(record);
    return { outcome: record.status === "quarantined" ? "quarantined" : "landed", record };
  }

  await page.route("**/v1/ontology/vocabulary", (route) =>
    json(route, {
      version: "1.2.0",
      handling_codes: ["open", "restricted", "sensitive"],
      source_types: ["open_source", "court_record", "commission_report"],
    }),
  );

  await page.route("**/v1/sources*", (route) =>
    route.request().method() === "POST"
      ? json(
          route,
          {
            source_id: "src_stub_new",
            source_type: "court_record",
            name: "Fictional Court Registry",
            url: null,
            reliability_normalized: null,
            created_at: new Date().toISOString(),
          },
          201,
        )
      : json(route, { items: [], next_cursor: null }),
  );

  await page.route("**/v1/ingest/file", async (route) => {
    await track(route);
    const request = route.request();
    const parts = parseMultipart(
      request.postDataBuffer() ?? Buffer.alloc(0),
      (await request.allHeaders())["content-type"] ?? "",
    );
    const file = parts.find((part) => part.name === "file");
    const form = Object.fromEntries(
      parts.filter((part) => part.name !== "file").map((p) => [p.name, p.body.toString()]),
    );
    const result = land(
      file?.body ?? Buffer.alloc(0),
      file?.filename ?? "upload",
      "application/pdf",
      form,
    );
    await json(route, result, 201);
  });

  await page.route("**/v1/ingest/text", async (route) => {
    await track(route);
    const body = route.request().postDataJSON() as Record<string, string>;
    const result = land(
      Buffer.from(body["text"] ?? "", "utf8"),
      body["filename"] ?? "note.txt",
      "text/plain",
      body,
    );
    await json(route, result, 201);
  });

  await page.route("**/v1/source-records?*", (route) => {
    const status = new URL(route.request().url()).searchParams.get("status");
    return json(route, {
      items: status ? records.filter((r) => r.status === status) : records,
      next_cursor: null,
    });
  });
  await page.route("**/v1/source-records", (route) =>
    json(route, { items: records, next_cursor: null }),
  );

  await page.route("**/v1/source-records/*/derivatives", (route) => {
    const id = route.request().url().split("/").at(-2)!;
    return json(route, derivatives.get(id) ?? []);
  });

  await page.route("**/v1/source-records/*/extract", async (route) => {
    await track(route);
    const id = route.request().url().split("/").at(-2)!;
    const record = records.find((row) => row.record_id === id);
    if (record?.status === "quarantined") {
      return json(
        route,
        {
          type: "about:blank",
          title: "Conflict",
          status: 409,
          detail: `record is quarantined (${record.quarantine_reason}); release it before extracting`,
        },
        409,
      );
    }

    const isPdf = record?.media_type === "application/pdf";
    if (isPdf && !derivatives.has(id)) {
      derivatives.set(id, [
        {
          derivative_id: `der_stub_${id}`,
          kind: "text",
          tool: "pdfplumber",
          tool_version: "0.11.10",
          params: {},
          content_hash: "f".repeat(64),
          operator: "0d3f4d3a-fictional-subject",
          created_at: new Date().toISOString(),
        },
      ]);
    }
    // Replay adds nothing already suggested (spec 04 §5), so the count only
    // moves on the first run — which is what the journey asserts.
    if (!suggestions.has(id)) {
      suggestions.set(id, [
        {
          suggestion_id: `sug_stub_${id}`,
          suggestion_kind: "claim_draft",
          status: "suggested",
          producer: "structural_pass",
          producer_version: "v1",
          payload: { predicate: "co_located_in_prison_with" },
          producer_meta: { rule: "remand-overlap" },
          record_id: id,
        },
      ]);
    }
    await json(route, {
      record_id: id,
      producer: "structural",
      suggestions_created: 1,
      derivative: derivatives.get(id)?.[0] ?? null,
      derivative_created: isPdf,
    });
  });

  await page.route("**/v1/source-records/*/release", async (route) => {
    await track(route);
    const id = route.request().url().split("/").at(-2)!;
    const record = records.find((row) => row.record_id === id);
    if (record) {
      record.status = "landed";
      record.quarantine_reason = null;
    }
    await json(route, record);
  });

  await page.route("**/v1/review-queue?*", (route) => {
    const id = new URL(route.request().url()).searchParams.get("record");
    return json(route, {
      items: id ? (suggestions.get(id) ?? []) : [],
      next_cursor: null,
    });
  });

  return { records: () => records, bearerTokens: () => bearers };
}

/** The same fictional annex the Python fixtures land, as bytes for an upload. */
export const ANNEX_PDF = Buffer.from(
  "%PDF-1.4 fictional annex fixture — ALPHA and BRAVO at Northgate\n",
  "utf8",
);
