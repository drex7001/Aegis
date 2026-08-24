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

export const STAMP = {
  as_of: null as string | null,
  identity_revision_id: 7,
  ontology_version: "2.0.0",
};

export const PERSON = {
  entity: { entity_id: "ent_person", entity_type: "person", label: "Fictional A" },
  resolved_entity_id: "ent_person",
  truncated: false,
  inbound_truncated: false,
  // Nothing refers to this person: the empty region must still render, saying
  // so, rather than disappearing.
  inbound_claims_by_predicate: {},
  stamp: STAMP,
  // The `marked` mode (T79). Empty by default so the ordinary journeys keep
  // asserting what they always asserted; `withheldPerson` below is the fixture
  // for a low-clearance reader.
  withheld: [] as Array<{ predicate: string; withheld: true }>,
  claims_by_predicate: {
    // A property: `known_as` has a literal object.
    known_as: [claim({ claim: { claim_id: "clm_name" } })],
    // Two properties that disagree — the conflict case.
    born_on: [
      claim({
        claim: {
          claim_id: "clm_dob_a",
          predicate: "born_on",
          object_value: "1979-04-02",
          // An instant: the source stated a date.
          event_time_earliest: "1979-04-02T00:00:00Z",
          event_time_latest: "1979-04-02T00:00:00Z",
        },
        contradicted_by: ["clm_dob_b"],
      }),
      claim({
        claim: {
          claim_id: "clm_dob_b",
          predicate: "born_on",
          object_value: "1981-11-17",
          // An interval: the source said "some time in 1981".
          event_time_earliest: "1981-01-01T00:00:00Z",
          event_time_latest: "1981-12-31T00:00:00Z",
        },
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
  inbound_truncated: false,
  stamp: STAMP,
  claims_by_predicate: {
    known_as: [
      claim({
        claim: { claim_id: "clm_org_name", subject_id: "ent_org", object_value: "Fictional Co" },
      }),
    ],
  },
  /*
   * The other end of `person`'s `member_of` claim (T57). One claim, two pages:
   * a link on the member's page and a reference on the organization's, which is
   * the hole that existed before the inbound set and that events made acute.
   */
  inbound_claims_by_predicate: {
    member_of: [
      claim({
        claim: {
          claim_id: "clm_member",
          subject_id: "ent_person",
          predicate: "member_of",
          object_id: "ent_org",
          object_value: null,
        },
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
  // URL predicates rather than globs: `**/v1/entities/ent_person` does not
  // match `/v1/entities/ent_person?asOf=…`, and as-of is a query parameter.
  await page.route(
    (url) => url.pathname === "/v1/entities/ent_person",
    (route) => {
      const url = new URL(route.request().url());
      const asOf = url.searchParams.get("asOf");
      const revision = url.searchParams.get("asOfRevision");
      const body = asOf
        ? {
            ...PERSON,
            // A historical view drops the later claim, exactly as the server
            // would: the fixture mirrors the recording snapshot rather than
            // inventing a different shape for it.
            claims_by_predicate: { known_as: PERSON.claims_by_predicate.known_as },
            stamp: {
              as_of: asOf,
              identity_revision_id: revision ? Number(revision) : STAMP.identity_revision_id,
              ontology_version: STAMP.ontology_version,
            },
          }
        : PERSON;
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    },
  );
  await page.route(
    (url) => url.pathname === "/v1/entities/ent_org",
    (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify(ORGANIZATION) }),
  );
  await page.route(
    (url) => url.pathname === "/v1/entities/ent_missing",
    (route) =>
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

/** `PERSON` as a low-clearance reader sees it: the claim gone, the marker there.

 * Both halves matter and the pair is the fixture. Dropping the claim without
 * the marker is the old behaviour (a gap that reads as "nothing recorded");
 * showing the marker with the claim still present would be no redaction at all.
 */
export const WITHHELD_PERSON = {
  ...PERSON,
  claims_by_predicate: { known_as: PERSON.claims_by_predicate.known_as },
  withheld: [{ predicate: "has_nic", withheld: true as const }],
};

export async function stubWithheldEntity(page: Page): Promise<void> {
  await page.route("**/v1/entities/*/cases", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify([]) }),
  );
  await page.route(
    (url) => url.pathname === "/v1/entities/ent_person",
    (route) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(WITHHELD_PERSON),
      }),
  );
}
