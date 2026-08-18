import type { components } from "../../api/schema";

type Stamp = components["schemas"]["AsOfStampOut"];

/**
 * The as-of banner (B-11, spec 09 §7).
 *
 * **Persistent and not dismissible.** A snapshot the reader has forgotten they
 * are in is worse than no snapshot: every value on the screen is historical,
 * and there is no other cue that says so. A dismiss control would make the
 * mistake one click away and irreversible for the rest of the session.
 *
 * It states the promise **and its limits**, because the limits are the finding.
 * As-of restores which claims had been recorded and not retracted; it restores
 * nothing else — not labels, not source evaluations, not grading, not policy,
 * not projections, not the ontology. Those are all current-state, and a banner
 * that said only "showing 1 March" would be the overstatement B-11 named.
 *
 * The identity revision is called out separately because it is the one a reader
 * would otherwise assume. `asOf` alone resolves identity as it is *now*: a
 * question about January answered after a February merge answers about the
 * merged person.
 */
export function AsOfBanner({ stamp }: { stamp: Stamp | null | undefined }) {
  if (!stamp?.as_of) return null;

  return (
    <div className="banner banner--caution" role="status" data-testid="as-of-banner">
      <strong>Historical view — {stamp.as_of.slice(0, 10)}.</strong>{" "}
      <span>
        Showing claims recorded and not retracted at that moment, resolved
        through identity revision <code>{stamp.identity_revision_id}</code>.
      </span>{" "}
      <span className="muted">
        Labels, source evaluations, grading, policy and the ontology (
        <code>{stamp.ontology_version}</code>) are current, not historical.
      </span>
    </div>
  );
}

/**
 * The stamp on a *current* read.
 *
 * Quiet, but present: knowing which identity revision produced an answer is
 * what lets a reader compare two answers taken at different times, and the
 * server sends it whether or not as-of was asked for.
 */
export function StampLine({ stamp }: { stamp: Stamp | null | undefined }) {
  if (!stamp || stamp.as_of) return null;
  return (
    <p className="muted stamp" data-testid="stamp-line">
      Identity revision <code>{stamp.identity_revision_id}</code> · ontology{" "}
      <code>{stamp.ontology_version}</code>
    </p>
  );
}
