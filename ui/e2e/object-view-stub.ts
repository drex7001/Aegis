import type { Page } from "@playwright/test";

/**
 * `GET /v1/entities/{id}` and `/cases` at the network boundary.
 *
 * Two entities of **different types** are served from the same fixture shape,
 * because the claim T44 makes is that one component renders both. Nothing here
 * stubs an ontology endpoint: the split between properties and links, the link
 * categories and every label come from the generated descriptors compiled into
 * the bundle (ADR-043), so stubbing them would be testing the stub.
 *
 * `person` carries the interesting case: **two dates of birth that contradict
 * each other**, which is Article VIII's rendering obligation in its smallest
 * form.
 */

function claim(overrides: Record<string, unknown>) {
  return {
    claim: {
      claim_id: "clm_x",
      subject_id: "ent_person",
      predicate: "known_as",
      object_id: null,
      object_value: "Fictional A",
      assertion_type: "reported",
      record_id: "rec_1",
      excerpt: null,
      recorded_at: "2026-01-01T00:00:00Z",
      retracted_at: null,
      retraction_reason: null,
      handling_code: "open",
      valid_from: null,
      valid_to: null,
      event_time_earliest: null,
      event_time_latest: null,
      ...(overrides.claim as Record<string, unknown>),
    },
    grading: {
      reliability: "generally_reliable",
      credibility: "probably_true",
      verification: "unverified",
      analytic_confidence: null,
    },
    source: { source_id: "src_1", name: "Fictional Gazette", source_type: "open_source" },
    record: { record_id: "rec_1", source_id: "src_1", status: "landed" },
    corroborated_by: [],
    contradicted_by: [],
    subject_mention: null,
    object_mention: null,
    ...Object.fromEntries(Object.entries(overrides).filter(([k]) => k !== "claim")),
  };
}

export const PERSON = {
  entity: { entity_id: "ent_person", entity_type: "person", label: "Fictional A" },
  resolved_entity_id: "ent_person",
  truncated: false,
  claims_by_predicate: {
    // A property: `known_as` has a literal object.
    known_as: [claim({ claim: { claim_id: "clm_name" } })],
    // Two properties that disagree — the conflict case.
    born_on: [
      claim({
        claim: { claim_id: "clm_dob_a", predicate: "born_on", object_value: "1979-04-02" },
        contradicted_by: ["clm_dob_b"],
      }),
      claim({
        claim: { claim_id: "clm_dob_b", predicate: "born_on", object_value: "1981-11-17" },
        contradicted_by: ["clm_dob_a"],
        source: { source_id: "src_2", name: "Fictional Registry", source_type: "court_record" },
      }),
    ],
    // A link: `member_of` has an entity object, and its category is financial.
    member_of: [
      claim({
        claim: {
          claim_id: "clm_member",
          predicate: "member_of",
          object_id: "ent_org",
          object_value: null,
        },
      }),
    ],
  },
};

export const ORGANIZATION = {
  entity: { entity_id: "ent_org", entity_type: "organization", label: "Fictional Co" },
  resolved_entity_id: "ent_org",
  truncated: false,
  claims_by_predicate: {
    known_as: [
      claim({
        claim: { claim_id: "clm_org_name", subject_id: "ent_org", object_value: "Fictional Co" },
      }),
    ],
  },
};

export async function stubEntityRoutes(
  page: Page,
  { cases = [] as Array<{ case_id: string; title: string; status: string }> } = {},
): Promise<void> {
  await page.route("**/v1/entities/*/cases", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(cases) }),
  );
  await page.route("**/v1/entities/ent_person", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(PERSON) }),
  );
  await page.route("**/v1/entities/ent_org", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(ORGANIZATION) }),
  );
  await page.route("**/v1/entities/ent_missing", (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/problem+json",
      body: JSON.stringify({
        type: "about:blank",
        title: "Not Found",
        status: 404,
        detail: "not found",
      }),
    }),
  );
}
