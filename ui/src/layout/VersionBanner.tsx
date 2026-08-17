import { useQuery } from "@tanstack/react-query";

import { getVocabulary } from "../api/client";
import { ONTOLOGY_VERSION } from "../api/ontology";

/**
 * "This bundle was built against a different ontology than the server is
 * running" (spec 09 §6.3, ADR-043).
 *
 * The descriptors are compiled in, which is what makes them type-checked and
 * drift-gated — and is also the one thing they cannot know. `ONTOLOGY_VERSION`
 * travels with them; `GET /v1/ontology/vocabulary` reports the server's. A
 * difference means labels and vocabulary in this tab may be stale.
 *
 * **Non-blocking, deliberately.** The server remains authoritative for every
 * value that matters — claims, grading, authorization — so a stale bundle
 * renders correct data with possibly outdated captions. Refusing to render
 * would turn a cosmetic drift into an outage, which is a worse failure than the
 * one being reported.
 *
 * Silent while the query is in flight or has failed: a banner that appears
 * during every cold start would be noise, and an unreachable vocabulary route
 * is a problem the screens themselves already surface.
 */
export function VersionBanner() {
  const { data } = useQuery({
    queryKey: ["ontology-vocabulary"],
    queryFn: getVocabulary,
    // The server's ontology version changes on deploy, not on interaction.
    staleTime: 5 * 60_000,
  });

  const server = data?.version;
  if (!server || server === ONTOLOGY_VERSION) return null;

  return (
    <div className="banner banner--caution" role="status" data-testid="ontology-mismatch">
      <strong>Ontology version mismatch.</strong>{" "}
      <span>
        This workspace was built against <code>{ONTOLOGY_VERSION}</code>; the server is
        running <code>{server}</code>. Labels and vocabulary shown here may be out of
        date — the data itself comes from the server and is current.
      </span>
    </div>
  );
}
