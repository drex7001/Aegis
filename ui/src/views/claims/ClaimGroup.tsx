import type { ClaimProvenance } from "../../api/client";
import { PREDICATES, type PredicateName } from "../../api/ontology";

/**
 * How a claim renders, wherever a claim renders.
 *
 * Extracted from `ProvenancePanel` at T44 unchanged, because the object view
 * needs exactly the same thing: two disagreeing claims **side by side** with a
 * `contradicts` badge, three grading dimensions kept apart, and both relation
 * directions reported. Copying it into a second screen would have meant two
 * places where Article VIII could quietly stop being true.
 *
 * The one addition is the label: a predicate's caption now comes from the
 * generated descriptors (ADR-043) rather than being the raw name.
 */

export function predicateLabel(predicate: string): string {
  return PREDICATES[predicate as PredicateName]?.label ?? predicate;
}

/**
 * One predicate's claims — side by side when they disagree.
 *
 * The comparison grid is not decoration: two dates of birth are only
 * meaningfully contested when the reader can see, on one line, that the
 * *values* differ while reading what each source was and how each was graded.
 * A vertical list makes that a memory exercise.
 */
export function PredicateGroup({
  predicate,
  claims,
}: {
  predicate: string;
  claims: ClaimProvenance[];
}) {
  const contested = claims.some((entry) => entry.contradicted_by.length > 0);
  return (
    <section
      className={`provenance__section${contested ? " provenance__section--contested" : ""}`}
      data-testid={`predicate-${predicate}`}
      data-contested={contested ? "true" : "false"}
    >
      <h3>
        {predicateLabel(predicate)}
        {contested && (
          <span className="chip chip--contested" data-testid="contradicts-badge">
            contradicts
          </span>
        )}
      </h3>
      {contested && (
        <p className="muted provenance__hint">
          Sources disagree. Both readings are shown — neither has been chosen.
        </p>
      )}
      <div className={contested ? "compare" : "stack"}>
        {claims.map((entry) => (
          <ClaimCard key={entry.claim.claim_id} entry={entry} compare={contested} />
        ))}
      </div>
    </section>
  );
}

export function ClaimGroups({ claims }: { claims: ClaimProvenance[] }) {
  if (claims.length === 0) {
    return (
      <p className="notice" data-testid="no-claims">
        No claims you are cleared to see.
      </p>
    );
  }
  const byPredicate = new Map<string, ClaimProvenance[]>();
  for (const entry of claims) {
    const key = entry.claim.predicate;
    byPredicate.set(key, [...(byPredicate.get(key) ?? []), entry]);
  }
  return (
    <>
      {[...byPredicate].map(([predicate, group]) => (
        <PredicateGroup key={predicate} predicate={predicate} claims={group} />
      ))}
    </>
  );
}

export function ClaimCard({
  entry,
  compare,
}: {
  entry: ClaimProvenance;
  compare: boolean;
}) {
  const { claim, grading, source, record } = entry;
  return (
    <article
      className={compare ? "claim claim--compare" : "claim"}
      data-testid={`claim-${claim.claim_id}`}
    >
      <p className="claim__value">{claimValue(entry)}</p>
      <dl className="claim__meta">
        <dt>Source</dt>
        <dd>{source?.name ?? "—"}</dd>
        <dt>Record</dt>
        <dd>
          <code>{record?.record_id ?? "—"}</code>
        </dd>
        {claim.excerpt && (
          <>
            <dt>Excerpt</dt>
            <dd className="claim__excerpt">“{claim.excerpt}”</dd>
          </>
        )}
      </dl>
      <Grading grading={grading} assertion={claim.assertion_type} />
      <Relations entry={entry} />
      {claim.retracted_at && (
        <p className="claim__retracted">
          Retracted — {claim.retraction_reason ?? "no reason recorded"}
        </p>
      )}
    </article>
  );
}

/**
 * The three dimensions, kept apart (Article III).
 *
 * Reliability grades the *source*, credibility grades the *claim*, and
 * verification records what was independently checked. There is deliberately
 * no combined figure: it is the number every reader would reach for, and it
 * cannot be turned back into the judgements that produced it.
 */
function Grading({
  grading,
  assertion,
}: {
  grading: ClaimProvenance["grading"];
  assertion: string;
}) {
  return (
    <ul className="grading" data-testid="grading">
      <li>
        <span className="grading__label">Source reliability</span>
        <span className="grading__value">{grading.reliability ?? "ungraded"}</span>
      </li>
      <li>
        <span className="grading__label">Claim credibility</span>
        <span className="grading__value">{grading.credibility}</span>
      </li>
      <li>
        <span className="grading__label">Verification</span>
        <span className="grading__value">{grading.verification}</span>
      </li>
      <li>
        <span className="grading__label">Analytic confidence</span>
        <span className="grading__value">
          {grading.analytic_confidence ?? "not assessed"}
        </span>
      </li>
      <li>
        {/* Article I: what is recorded is that someone asserted this, not that
            it is so. The assertion type is the difference between the two. */}
        <span className="grading__label">Asserted as</span>
        <span className="grading__value">{assertion}</span>
      </li>
    </ul>
  );
}

function Relations({ entry }: { entry: ClaimProvenance }) {
  const { contradicted_by: against, corroborated_by: supporting } = entry;
  if (against.length === 0 && supporting.length === 0) return null;
  return (
    <ul className="relations">
      {against.map((id) => (
        <li key={id} className="chip chip--contested">
          contradicts <code>{id}</code>
        </li>
      ))}
      {supporting.map((id) => (
        <li key={id} className="chip chip--corroborated">
          corroborates <code>{id}</code>
        </li>
      ))}
    </ul>
  );
}

export function claimValue(entry: ClaimProvenance): string {
  const { claim } = entry;
  if (claim.object_value !== null && claim.object_value !== undefined) {
    return typeof claim.object_value === "string"
      ? claim.object_value
      : JSON.stringify(claim.object_value);
  }
  if (claim.object_id) return claim.object_id;
  return "—";
}
