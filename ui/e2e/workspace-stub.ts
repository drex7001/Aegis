import type { Page } from "@playwright/test";

/**
 * Stubs for the T42 foundation journeys.
 *
 * Only `GET /v1/ontology/vocabulary` is needed: the rail and both descriptor
 * screens read the *generated* constants and call nothing, which is the
 * property those journeys exist to check. The vocabulary route matters for one
 * reason — it is the runtime half of the bundle/server version comparison
 * (spec 09 §6.3).
 */

export interface VocabularyStub {
  /** How many times the app asked. */
  calls(): number;
}

export async function stubVocabulary(
  page: Page,
  { version }: { version: string },
): Promise<VocabularyStub> {
  let calls = 0;
  await page.route("**/v1/ontology/vocabulary", async (route) => {
    calls += 1;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        version,
        handling_codes: ["open", "restricted", "sensitive"],
        source_types: ["open_source", "court_record"],
        assertion_types: ["observed", "reported", "assessed", "analyst"],
      }),
    });
  });
  return { calls: () => calls };
}

/**
 * The version the bundle under test was built against.
 *
 * Read from the generated constants rather than hard-coded: pinning "1.6.1"
 * here would make every ontology bump fail a UI test for no reason, and the
 * journey is about *agreement*, not about a number.
 */
export { ONTOLOGY_VERSION } from "../src/api/ontology";
