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
 * `GET /v1/cases`, which the **rail** calls on every page from T46.
 *
 * It belongs to the shell rather than to any screen, which is why the
 * "no endpoint of their own" sweeps list it beside the screen's own calls: the
 * assertion stays exact equality, and the comment there says which call is
 * whose.
 */
export async function stubCases(
  page: Page,
  items: Array<Record<string, unknown>> = [],
): Promise<void> {
  await page.route("**/v1/cases", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items, next_cursor: null }),
    }),
  );
}

/**
 * The version the bundle under test was built against.
 *
 * Read from the generated constants rather than hard-coded: pinning "1.6.1"
 * here would make every ontology bump fail a UI test for no reason, and the
 * journey is about *agreement*, not about a number.
 */
export { ONTOLOGY_VERSION } from "../src/api/ontology";
