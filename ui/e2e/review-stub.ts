import type { Page, Route } from "@playwright/test";

/**
 * A stand-in for the review and identity APIs that keeps their *rules*.
 *
 * The rules that matter here are the ones the screen is judged on: a confirmed
 * pair leaves the open list, a batch refuses anything outside the pre-verified
 * band, each confirmed pair produces its *own* decision, and a decision sent
 * against a superseded revision comes back 409 carrying what intervened. A stub
 * that answered every write with 200 would let the journey pass while the UI
 * silently merged people nobody approved.
 *
 * Not a second implementation: no ledger, no audit, no authorization. Those are
 * proven in `tests/integration/test_identity_routes.py` against the real thing.
 */

export interface StubCandidate {
  candidate_id: string;
  mention_a: StubSide;
  mention_b: StubSide;
  producer: string;
  producer_version: string;
  graph_snapshot_id: string | null;
  score: number | null;
  features: Record<string, unknown>;
  pre_verified: boolean;
  disposition: string;
  created_at: string;
}

interface StubSide {
  mention_id: string;
  record_id: string;
  raw_text: string;
  norm_key: string;
  script: string | null;
  language: string | null;
  entity_id: string | null;
  entity_label: string | null;
}

export interface ReviewStub {
  decisions(): { kind: string; note: string; candidate_id?: string }[];
  suggestions(): StubSuggestion[];
  /** Force the next decision to collide, as a concurrent reviewer would. */
  advanceRevision(): void;
}

interface StubSuggestion {
  suggestion_id: string;
  suggestion_kind: string;
  schema_version: number;
  payload: Record<string, unknown>;
  target_action: string;
  producer: string;
  producer_version: string;
  producer_meta: Record<string, unknown>;
  record_id: string | null;
  case_id: string | null;
  status: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  result_claim_id: string | null;
  result_decision_id: string | null;
  result_relation: Record<string, unknown> | null;
  created_at: string;
}

function side(id: string, text: string, entity: string, label: string): StubSide {
  return {
    mention_id: id,
    record_id: "rec_stub",
    raw_text: text,
    norm_key: text.toLowerCase().replace(/\s+/g, "_"),
    script: "Latn",
    language: "en",
    entity_id: entity,
    entity_label: label,
  };
}

function seedCandidates(): StubCandidate[] {
  return [
    {
      candidate_id: "cnd_verified",
      mention_a: side("men_a", "Fictional ALPHA", "ent_a", "Fictional ALPHA"),
      mention_b: side("men_b", "F. ALPHA", "ent_b", "F. ALPHA"),
      producer: "rule:identifier:has_passport_number",
      producer_version: "1.0.0",
      graph_snapshot_id: null,
      // A rule computes no probability, and the screen has to say so rather
      // than render a confident-looking zero.
      score: null,
      features: {
        rule: "identifier_match",
        predicate: "has_passport_number",
        claim_ids: ["clm_one", "clm_two"],
      },
      pre_verified: true,
      disposition: "open",
      created_at: "2026-07-01T09:00:00Z",
    },
    {
      candidate_id: "cnd_scored",
      mention_a: side("men_c", "Fictional BRAVO", "ent_c", "Fictional BRAVO"),
      mention_b: side("men_d", "Fictional BRAVA", "ent_d", "Fictional BRAVA"),
      producer: "splink",
      producer_version: "4.0.0",
      graph_snapshot_id: "snap_stub",
      score: 0.94,
      features: {
        rule: "splink",
        gamma_name: 3,
        bf_name: 12.5,
        tf_name: 0.8,
        // Below 1: this column argues *against* the match, which is the case
        // the two-directional scale exists to show.
        gamma_dob: 0,
        bf_dob: 0.25,
      },
      pre_verified: false,
      disposition: "open",
      created_at: "2026-07-01T09:05:00Z",
    },
  ];
}

function seedSuggestions(): StubSuggestion[] {
  return [
    {
      suggestion_id: "sug_one",
      suggestion_kind: "claim_draft",
      schema_version: 1,
      payload: {
        subject_id: "ent_a",
        predicate: "co_located_in_prison_with",
        object_id: "ent_c",
        assertion_type: "reported",
      },
      target_action: "record_claim",
      producer: "semantic",
      producer_version: "0.1.0",
      producer_meta: { model: "mock", prompt_hash: "a1b2c3d4" },
      record_id: "rec_stub",
      case_id: null,
      status: "suggested",
      decided_by: null,
      decided_at: null,
      decision_note: null,
      result_claim_id: null,
      result_decision_id: null,
      result_relation: null,
      created_at: "2026-07-01T09:10:00Z",
    },
  ];
}

export async function stubReview(page: Page): Promise<ReviewStub> {
  let revision = 41;
  let candidates = seedCandidates();
  let suggestions = seedSuggestions();
  const decisions: { kind: string; note: string; candidate_id?: string }[] = [];

  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  await page.route("**/v1/ontology/vocabulary", (route) =>
    json(route, {
      version: "1.2.0",
      handling_codes: ["open", "restricted", "sensitive"],
      source_types: ["open_source"],
      assertion_types: ["assessed", "inferred", "observed", "reported"],
    }),
  );

  await page.route("**/v1/review-queue*", (route) => {
    const status = new URL(route.request().url()).searchParams.get("status");
    return json(
      route,
      {
        items: suggestions.filter((row) => !status || row.status === status),
        next_cursor: null,
      },
    );
  });

  await page.route("**/v1/review-queue/*/accept", (route) => {
    const id = route.request().url().split("/").at(-2);
    const body = JSON.parse(route.request().postData() ?? "{}");
    suggestions = suggestions.map((row) =>
      row.suggestion_id === id
        ? {
            ...row,
            status: "accepted",
            decided_by: "dev-analyst",
            decision_note: body.note ?? null,
            payload: { ...row.payload, ...(body.edits ?? {}) },
            result_claim_id: "clm_accepted",
          }
        : row,
    );
    return json(route, suggestions.find((row) => row.suggestion_id === id));
  });

  await page.route("**/v1/review-queue/*/reject", (route) => {
    const id = route.request().url().split("/").at(-2);
    const body = JSON.parse(route.request().postData() ?? "{}");
    suggestions = suggestions.map((row) =>
      row.suggestion_id === id
        ? { ...row, status: "rejected", decided_by: "dev-analyst", decision_note: body.reason }
        : row,
    );
    return json(route, suggestions.find((row) => row.suggestion_id === id));
  });

  await page.route("**/v1/identity/candidates?*", (route) => {
    const params = new URL(route.request().url()).searchParams;
    const disposition = params.get("disposition");
    const producer = params.get("producer");
    return json(route, {
      revision_id: revision,
      candidates: candidates.filter(
        (row) =>
          (!disposition || row.disposition === disposition) &&
          (!producer || row.producer === producer),
      ),
      next_cursor: null,
    });
  });

  await page.route("**/v1/identity/candidates/batch-confirm", (route) => {
    const body = JSON.parse(route.request().postData() ?? "{}");
    const confirmed: unknown[] = [];
    const skipped: { candidate_id: string; reason: string }[] = [];

    for (const id of body.candidate_ids as string[]) {
      const candidate = candidates.find((row) => row.candidate_id === id);
      if (!candidate) {
        skipped.push({ candidate_id: id, reason: "not found" });
        continue;
      }
      if (!candidate.pre_verified) {
        skipped.push({
          candidate_id: id,
          reason: "not in the pre-verified band — decide this pair on its own",
        });
        continue;
      }
      // One decision per pair, which is the whole point of the batch route.
      revision += 1;
      decisions.push({ kind: "confirm", note: body.note, candidate_id: id });
      candidate.disposition = "confirmed";
      confirmed.push(decisionBody(revision, body.note, body.parent_revision_id));
    }
    return json(route, { confirmed, skipped });
  });

  await page.route("**/v1/identity/decisions", (route) => {
    const body = JSON.parse(route.request().postData() ?? "{}");
    if (body.parent_revision_id !== revision) {
      return json(
        route,
        {
          type: "about:blank",
          title: "stale revision",
          status: 409,
          detail: "decision was computed against a superseded revision",
          parent_revision_id: body.parent_revision_id,
          intervening: [
            {
              decision_id: "dec_other",
              kind: "confirm",
              decided_by: "dev-supervisor",
              note: "merged these two from the other desk",
              result_revision_id: revision,
            },
          ],
        },
        409,
      );
    }
    revision += 1;
    const kind = String(body.mode).replace("_match", "").replace("mark_", "");
    decisions.push({ kind, note: body.note, candidate_id: body.candidate_id });
    const candidate = candidates.find((row) => row.candidate_id === body.candidate_id);
    if (candidate) candidate.disposition = kind === "confirm" ? "confirmed" : "rejected";
    return json(route, decisionBody(revision, body.note, body.parent_revision_id), 201);
  });

  return {
    decisions: () => decisions,
    suggestions: () => suggestions,
    advanceRevision: () => {
      revision += 1;
    },
  };
}

function decisionBody(revision: number, note: string, parent: number) {
  return {
    decision: {
      decision_id: `dec_${revision}`,
      kind: "confirm",
      decided_by: "dev-analyst",
      decision_note: note,
      parent_revision_id: parent,
      result_revision_id: revision,
      decided_at: "2026-07-01T10:00:00Z",
      entity_id: null,
    },
    moved_mentions: ["men_b"],
    surviving_entity_id: "ent_a",
    new_entity_id: null,
    unattributable_claims: [],
  };
}
