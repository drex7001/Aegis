import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import {
  getEntity,
  listEntityCases,
  type ClaimProvenance,
  type EntityDetail,
} from "../api/client";
import {
  CATEGORIES,
  OBJECT_TYPES,
  PREDICATES,
  type CategoryName,
  type ObjectTypeName,
  type PredicateName,
} from "../api/ontology";
import { objectTypePath } from "../routing";
import { AsOfBanner, StampLine } from "./claims/AsOfBanner";
import { PredicateGroup, predicateLabel } from "./claims/ClaimGroup";
import { ProvenanceDrawer, type Drill } from "./claims/ProvenanceDrawer";
import { TimelineStrip } from "./claims/TimelineStrip";

/**
 * The entity-360 (spec 09 §6.4): one generic component for any object type.
 *
 * There is no branch on a type name in this file and there must never be one:
 * every declared type renders through the same code, and adding one to a domain
 * module makes a working page for it appear once the descriptors are
 * regenerated — the charter's fourth exit criterion.
 *
 * (`tests/contract/test_workspace_descriptors.py` sweeps this directory for
 * every domain-declared name, and it cannot tell a comment from code — which is
 * why the sentence above names no type. That is the sweep working, not a
 * limitation to route around.)
 *
 * Two divisions do the work, and both come from the generated descriptors
 * rather than from the response:
 *
 * * **Properties vs. links** — a predicate whose object is `literal` states a
 *   property of this entity; one whose object is an entity type is a link to
 *   another. The API returns both in one `claims_by_predicate` map, and only
 *   the ontology knows which is which.
 * * **Link categories** — links group by `PREDICATES[p].category`, rendered
 *   with the ontology's own colour. An uncategorized predicate groups under
 *   "Other" rather than vanishing.
 *
 * Conflicting values render side by side with their `contradicts` badge, via
 * the same `PredicateGroup` the P2 provenance panel uses — one implementation,
 * so Article VIII cannot become true in one screen and false in the other.
 *
 * **Referenced by** (T57) is the third region: claims where this entity is the
 * *object*. It is separate from Links, not merged into it, because who asserted
 * what about whom is the distinction a reader most needs — "this arrest has
 * Nimal as an arrestee" is a statement about the arrest, and it belongs on
 * Nimal's page under a heading that says so. Generic, not event-shaped: an
 * organization's members arrive through exactly the same field.
 */

type Split = { properties: [string, ClaimProvenance[]][]; links: [string, ClaimProvenance[]][] };

function splitClaims(detail: EntityDetail): Split {
  const properties: [string, ClaimProvenance[]][] = [];
  const links: [string, ClaimProvenance[]][] = [];
  for (const [predicate, claims] of Object.entries(detail.claims_by_predicate)) {
    const spec = PREDICATES[predicate as PredicateName];
    // A predicate the descriptors do not know is rendered as a property rather
    // than dropped: the server accepted the claim, so the bundle is stale
    // (the version banner is already saying so) and hiding it would be worse.
    const isLink = spec !== undefined && spec.object !== "literal";
    (isLink ? links : properties).push([predicate, claims]);
  }
  return { properties, links };
}

function categoryOf(predicate: string): { key: string; label: string; color: string | null } {
  const category = PREDICATES[predicate as PredicateName]?.category as CategoryName | null;
  if (category && category in CATEGORIES) {
    return { key: category, label: CATEGORIES[category].label, color: CATEGORIES[category].color };
  }
  return { key: "__other", label: "Other", color: null };
}

/** The distinct sources behind a set of claims, in first-seen order. */
function sourcesOf(detail: EntityDetail) {
  const seen = new Map<string, { name: string; type: string; records: Set<string> }>();
  const sets = [detail.claims_by_predicate, detail.inbound_claims_by_predicate ?? {}];
  for (const claims of sets.flatMap((set) => Object.values(set))) {
    for (const entry of claims) {
      if (!entry.source) continue;
      const bucket = seen.get(entry.source.source_id) ?? {
        name: entry.source.name,
        type: entry.source.source_type,
        records: new Set<string>(),
      };
      if (entry.record) bucket.records.add(entry.record.record_id);
      seen.set(entry.source.source_id, bucket);
    }
  }
  return [...seen.entries()];
}

export function ObjectView() {
  const { entityId = "" } = useParams<{ entityId: string }>();
  const [drill, setDrill] = useState<Drill | null>(null);
  /*
   * As-of lives in the URL, not in component state. A historical view is
   * something an analyst shares, bookmarks and comes back to, and a snapshot
   * that vanished on reload would be a different answer at the same address.
   */
  const [search, setSearch] = useSearchParams();
  const asOf = search.get("asOf") ?? undefined;
  const asOfRevision = search.get("asOfRevision") ?? undefined;

  const entity = useQuery({
    queryKey: ["entity", entityId, asOf ?? null, asOfRevision ?? null],
    queryFn: () =>
      getEntity(entityId, {
        asOf,
        asOfRevision: asOfRevision ? Number(asOfRevision) : undefined,
      }),
  });
  const cases = useQuery({
    queryKey: ["entity-cases", entityId],
    queryFn: () => listEntityCases(entityId),
  });

  if (entity.isPending) {
    return (
      <section className="page" aria-busy="true">
        <p className="muted">Loading…</p>
      </section>
    );
  }
  if (entity.error || !entity.data) {
    return (
      <section className="page" data-testid="object-view-error" role="alert">
        <h1>Not available</h1>
        <p className="muted">
          {/* 404 is both "absent" and "you may not see this" (spec 06 default 4),
              so this must read as absence and never as a permission prompt. */}
          Nothing here for <code>{entityId}</code>.
        </p>
      </section>
    );
  }

  const detail = entity.data;
  const typeName = detail.entity.entity_type as ObjectTypeName;
  const descriptor = OBJECT_TYPES[typeName];
  const { properties, links } = splitClaims(detail);
  const withheld = detail.withheld ?? [];
  const sources = sourcesOf(detail);
  const inboundGroups = Object.entries(detail.inbound_claims_by_predicate ?? {});
  /*
   * The timeline spans both directions. An arrest's date reaches a participant's
   * page only through the inbound claim, and a timeline that silently omitted it
   * would be the "one claim set, two answers" failure this phase exists to
   * remove.
   */
  const allClaims = [
    ...Object.values(detail.claims_by_predicate),
    ...inboundGroups.map(([, claims]) => claims),
  ].flat();

  /** Where did this value come from — the claim's own evidence (T45). */
  const drillClaim = (entry: ClaimProvenance) =>
    setDrill({
      kind: "claim",
      claimId: entry.claim.claim_id,
      label: predicateLabel(entry.claim.predicate),
    });

  /**
   * Why are these two connected — the link's evidence *and* the identity
   * decisions behind its endpoints, which a claim-level view cannot show.
   *
   * "The other end" depends on which end *this* entity is (T57). An outbound
   * claim has us as the subject, so the far side is `object_id`; a claim in
   * "Referenced by" has us as the object, so it is `subject_id`. Reading
   * `object_id` unconditionally would ask why this entity is connected to
   * itself. Falls back to the claim drill when a link has no entity object,
   * which a mixed entity-or-literal predicate can produce (spec 02 §6).
   */
  const drillLink = (entry: ClaimProvenance) => {
    const here = new Set([detail.entity.entity_id, detail.resolved_entity_id]);
    const inbound = entry.claim.object_id !== null && here.has(entry.claim.object_id);
    const other = inbound ? entry.claim.subject_id : entry.claim.object_id;
    if (!other) return drillClaim(entry);
    setDrill({
      kind: "link",
      from: detail.resolved_entity_id,
      to: other,
      label: `Why connected: ${predicateLabel(entry.claim.predicate)}`,
    });
  };

  const grouped = new Map<string, { label: string; color: string | null; predicates: typeof links }>();
  for (const entry of links) {
    const category = categoryOf(entry[0]);
    const bucket = grouped.get(category.key) ?? {
      label: category.label,
      color: category.color,
      predicates: [],
    };
    bucket.predicates.push(entry);
    grouped.set(category.key, bucket);
  }

  return (
    <section className="page" data-testid="object-view">
      <header className="page__head">
        {/*
         * The heading is the entity's own label, not `display.title` resolved
         * against claims. `display` names a *property* and the response is keyed
         * by *predicate*, and the ontology declares no mapping between them —
         * the server's own property/predicate correspondence is a documented
         * heuristic (`aegis/authz/filters.py`). `label` is what search, the
         * graph and the projection already show, and it is authorization-aware.
         */}
        <h1 data-testid="object-view-title">{detail.entity.label}</h1>
        <p className="muted">
          <Link to={objectTypePath(typeName)} data-testid="object-view-type">
            {descriptor?.label ?? typeName}
          </Link>{" "}
          · <code>{detail.entity.entity_id}</code>
        </p>
      </header>

      <AsOfBanner stamp={detail.stamp} />

      <form
        className="case-form as-of"
        data-testid="as-of-form"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const at = String(form.get("as_of") ?? "");
          const revision = String(form.get("as_of_revision") ?? "");
          const next = new URLSearchParams();
          if (at) next.set("asOf", new Date(at).toISOString());
          if (revision) next.set("asOfRevision", revision);
          setSearch(next);
        }}
      >
        <label>
          <span>What was recorded before</span>
          <input type="date" name="as_of" defaultValue={asOf?.slice(0, 10)} data-testid="as-of-date" />
        </label>
        <label>
          <span>Identity revision</span>
          {/*
           * Offered beside the date, because leaving it blank is a real
           * choice with a real consequence: the answer uses today's identity.
           * The banner says which revision was used either way.
           */}
          <input
            type="number"
            min={0}
            name="as_of_revision"
            defaultValue={asOfRevision}
            data-testid="as-of-revision"
          />
        </label>
        <button type="submit" data-testid="as-of-apply">
          Apply
        </button>
        {asOf && (
          <button
            type="button"
            data-testid="as-of-clear"
            onClick={() => setSearch(new URLSearchParams())}
          >
            Back to now
          </button>
        )}
      </form>

      <StampLine stamp={detail.stamp} />

      {detail.resolved_entity_id !== detail.entity.entity_id && (
        <p className="notice" data-testid="object-view-resolved">
          This id was merged. Showing <code>{detail.resolved_entity_id}</code>.
        </p>
      )}
      {detail.truncated && (
        <p className="notice" data-testid="object-view-truncated">
          Showing the first claims only — more is recorded than is shown here.
        </p>
      )}

      <h2>Timeline</h2>
      <TimelineStrip claims={allClaims} />

      <h2>Properties</h2>
      <div data-testid="object-view-properties">
        {properties.length === 0 && withheld.length === 0 ? (
          <p className="notice">No property claims you are cleared to see.</p>
        ) : (
          properties.map(([predicate, claims]) => (
            <PredicateGroup
              key={predicate}
              predicate={predicate}
              claims={claims}
              onDrill={drillClaim}
            />
          ))
        )}
        {/*
         * The `marked` mode (spec 03 §6.2). Without this the absence of a
         * group reads as "nothing recorded", which is a different and false
         * statement — and the reader has no way to tell the two apart.
         *
         * What is shown is the *predicate*, and only that: no value, no count,
         * no grading, no id (ADR-061). The list comes from the ontology rather
         * than from this entity's rows (ADR-067), so it is identical for every
         * object of the type and can never be read as evidence that this one
         * has such a claim.
         */}
        {withheld.length > 0 && (
          <div className="object-view__withheld" data-testid="object-view-withheld">
            {withheld.map((entry) => (
              <p key={entry.predicate} className="notice" data-predicate={entry.predicate}>
                <strong>{PREDICATES[entry.predicate as PredicateName]?.label ?? entry.predicate}</strong>
                {" — withheld at your clearance. This object type declares the field;"}
                {" whether anything is recorded in it is not disclosed."}
              </p>
            ))}
          </div>
        )}
      </div>

      <h2>Links</h2>
      <div data-testid="object-view-links">
        {grouped.size === 0 ? (
          <p className="notice">No links you are cleared to see.</p>
        ) : (
          [...grouped.entries()].map(([key, group]) => (
            <div key={key} className="object-type__group">
              <h3>
                {group.color && (
                  <span
                    className="swatch"
                    style={{ background: group.color }}
                    aria-hidden="true"
                  />
                )}
                {group.label}
              </h3>
              {group.predicates.map(([predicate, claims]) => (
                <PredicateGroup
                  key={predicate}
                  predicate={predicate}
                  claims={claims}
                  onDrill={drillLink}
                />
              ))}
            </div>
          ))
        )}
      </div>

      <h2>Referenced by</h2>
      <div data-testid="object-view-inbound">
        {inboundGroups.length === 0 ? (
          <p className="notice">Nothing you are cleared to see refers to this.</p>
        ) : (
          inboundGroups.map(([predicate, claims]) => (
            <PredicateGroup
              key={predicate}
              predicate={predicate}
              claims={claims}
              onDrill={drillLink}
            />
          ))
        )}
      </div>
      {detail.inbound_truncated && (
        <p className="notice" data-testid="object-view-inbound-truncated">
          Showing the first references only — more is recorded than is shown here.
        </p>
      )}

      <h2>Sources</h2>
      {sources.length === 0 ? (
        <p className="notice">No source you are cleared to see.</p>
      ) : (
        <ul data-testid="object-view-sources">
          {sources.map(([sourceId, source]) => (
            <li key={sourceId}>
              {source.name} <span className="muted">({source.type})</span>
              <span className="muted">
                {" "}
                · {source.records.size} record{source.records.size === 1 ? "" : "s"}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h2>Cases</h2>
      {/*
       * Only cases the viewer may know about, and the empty state must read the
       * same whether the entity is in none or in none they can see — the route
       * returns an identical body for both, and a UI that distinguished them
       * would put H-18's leak back. So: no count, no "some hidden", no
       * difference in wording.
       */}
      {cases.data && cases.data.length > 0 ? (
        <ul data-testid="object-view-cases">
          {cases.data.map((entry) => (
            <li key={entry.case_id}>
              {entry.title} <span className="muted">· {entry.status}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="notice" data-testid="object-view-no-cases">
          Not part of any case.
        </p>
      )}

      {drill && <ProvenanceDrawer drill={drill} onClose={() => setDrill(null)} />}
    </section>
  );
}

/** Re-exported so a caller building a link never assembles the path by hand. */
export { predicateLabel };
