import type { Page } from "@playwright/test";

/**
 * Network-boundary fakes for the T23c journey (search → graph → provenance).
 *
 * These stand in for the API, so they have to keep the properties the panel is
 * being tested for rather than just returning plausible JSON: contradictions
 * are recorded from both ends (directionality is a recording artefact), the
 * three grading dimensions arrive apart, and search results say *how* each hit
 * was found. A fixture that flattened any of those would let the panel pass a
 * test the real route would fail.
 *
 * Fictional throughout.
 */

export const ENTITY_A = "ent_fictional_a";
export const ENTITY_B = "ent_fictional_b";

export const EARLIER_DOB = "1985-03-12";
export const LATER_DOB = "1987-11-02";

function grading(reliability: string | null) {
  return {
    reliability,
    credibility: "possibly_true",
    verification: "unverified",
    analytic_confidence: null,
  };
}

function source(name: string) {
  return {
    source_id: "src_fictional_1",
    source_type: "open_source",
    name,
    reliability_normalized: "usually_reliable",
  };
}

function record(id: string) {
  return {
    record_id: id,
    source_id: "src_fictional_1",
    ingest_key: `key_${id}`,
    content_hash: "a".repeat(64),
    storage_uri: `test://${id}`,
    status: "extracted",
  };
}

function claim(over: Record<string, unknown>) {
  return {
    claim_id: "clm_x",
    subject_id: ENTITY_A,
    predicate: "date_of_birth",
    object_id: null,
    object_value: EARLIER_DOB,
    assertion_type: "reported",
    record_id: "rec_1",
    excerpt: null,
    collection_method: null,
    credibility_scheme: null,
    credibility_original: null,
    credibility_normalized: "possibly_true",
    verification_status: "unverified",
    analytic_confidence: null,
    valid_from: null,
    valid_to: null,
    recorded_at: "2026-01-01T00:00:00Z",
    retracted_at: null,
    retraction_reason: null,
    handling_code: "open",
    case_id: null,
    location_text: null,
    ontology_version: "1.2.0",
    ...over,
  };
}

/**
 * One entity with two stated dates of birth that contradict each other, plus an
 * uncontested alias — so a test can tell "marked contested" apart from "marks
 * everything contested".
 */
export const ENTITY_DETAIL = {
  entity: {
    entity_id: ENTITY_A,
    entity_type: "person",
    label: "Fictional A",
    created_at: "2026-01-01T00:00:00Z",
  },
  resolved_entity_id: ENTITY_A,
  truncated: false,
  claims_by_predicate: {
    date_of_birth: [
      {
        claim: claim({ claim_id: "clm_dob_early", object_value: EARLIER_DOB }),
        grading: grading("usually_reliable"),
        source: source("Fictional Registry"),
        record: record("rec_1"),
        corroborated_by: [],
        // Both directions recorded, as the real route reports them.
        contradicted_by: ["clm_dob_late"],
        subject_mention: null,
        object_mention: null,
      },
      {
        claim: claim({ claim_id: "clm_dob_late", object_value: LATER_DOB }),
        grading: grading("fairly_reliable"),
        source: source("Fictional Court Filing"),
        record: record("rec_2"),
        corroborated_by: [],
        contradicted_by: ["clm_dob_early"],
        subject_mention: null,
        object_mention: null,
      },
    ],
    known_as: [
      {
        claim: claim({
          claim_id: "clm_alias_1",
          predicate: "known_as",
          object_value: "Fictional Al",
        }),
        grading: grading("usually_reliable"),
        source: source("Fictional Registry"),
        record: record("rec_1"),
        corroborated_by: [],
        contradicted_by: [],
        subject_mention: null,
        object_mention: null,
      },
    ],
  },
};

export const WHY_CONNECTED = {
  subject_id: ENTITY_A,
  object_id: ENTITY_B,
  resolved_subject_id: ENTITY_A,
  resolved_object_id: ENTITY_B,
  record_count: 2,
  contradiction_count: 0,
  corroboration_count: 1,
  truncated: false,
  claims: [
    {
      claim: claim({
        claim_id: "clm_edge_1",
        predicate: "allied_with",
        object_id: ENTITY_B,
        object_value: null,
      }),
      grading: grading("usually_reliable"),
      source: source("Fictional Registry"),
      record: record("rec_1"),
      corroborated_by: ["clm_edge_2"],
      contradicted_by: [],
      subject_mention: null,
      object_mention: null,
    },
  ],
  identity_line: [
    {
      decision_id: "dec_fictional_1",
      kind: "confirm_match",
      decided_by: "analyst@example.test",
      decision_note: "Same NIC on both records.",
      parent_revision_id: 6,
      result_revision_id: 7,
      decided_at: "2026-01-02T00:00:00Z",
      entity_id: ENTITY_A,
    },
  ],
};

export const SEARCH_RESULTS = {
  query: "fictional",
  next_cursor: null,
  results: [
    {
      entity_id: ENTITY_B,
      label: "Fictional B",
      entity_type: "person",
      score: 0.92,
      matched: "label",
    },
    {
      // A phonetic hit: scored low and labelled, because metaphone collapses
      // genuinely different names.
      entity_id: "ent_fictional_c",
      label: "Fictional Sea",
      entity_type: "person",
      score: 0.5,
      matched: "phonetic",
    },
  ],
};

export async function stubProvenanceRoutes(page: Page): Promise<void> {
  await page.route("**/v1/entities/*/why-connected/*", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(WHY_CONNECTED) }),
  );
  // Registered after why-connected so the more specific pattern wins.
  await page.route(/\/v1\/entities\/[^/?]+(\?.*)?$/, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(ENTITY_DETAIL) }),
  );
  await page.route("**/v1/search/entities**", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(SEARCH_RESULTS) }),
  );
}
