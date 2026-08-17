import { Link, useParams } from "react-router-dom";

import {
  CATEGORIES,
  INTERFACES,
  OBJECT_TYPES,
  PREDICATES,
  type CategoryName,
  type InterfaceName,
  type ObjectTypeName,
  type PredicateName,
} from "../api/ontology";
import { interfacePath, objectTypePath } from "../routing";

/**
 * What the ontology says an object type *is* — its properties, the interfaces
 * it implements, and every link that can attach to it.
 *
 * Entirely descriptor-driven and entirely offline: it reads the generated
 * constants and calls no endpoint. That is the point. Adding a type to a domain
 * module and regenerating yields this page with no React change, which is the
 * schema half of the charter's fourth exit criterion; T44 adds the instance
 * half (an actual entity's claims, sources and provenance) over the same
 * descriptors.
 *
 * It renders governance, not decoration: a `restricted` property says so here,
 * because "why can I not see this field" is a question the schema can answer
 * before anyone goes looking for the row.
 */

function predicateLabel(name: PredicateName): string {
  return PREDICATES[name].label;
}

/**
 * `display.title` names a property, and a reader wants its caption.
 *
 * Falls back to the raw name rather than throwing: `display` and `properties`
 * are validated against each other by the loader, so a mismatch cannot reach a
 * generated file — and if one ever did, a slightly ugly line beats a blank page.
 */
function propertyLabel(type: ObjectTypeName, property: string): string {
  const properties = OBJECT_TYPES[type].properties as Record<string, { label: string }>;
  return properties[property]?.label ?? property;
}

function categoryOf(name: PredicateName): { key: string; label: string; color: string | null } {
  const category = PREDICATES[name].category as CategoryName | null;
  if (category && category in CATEGORIES) {
    return {
      key: category,
      label: CATEGORIES[category].label,
      color: CATEGORIES[category].color,
    };
  }
  // An uncategorized predicate groups under "Other" rather than vanishing
  // (spec 09 §6.4) — a link nobody grouped is still a link.
  return { key: "__other", label: "Other", color: null };
}

type Role = "subject" | "object";

function linksFor(type: ObjectTypeName): Array<{ name: PredicateName; role: Role }> {
  const names = Object.keys(PREDICATES) as PredicateName[];
  const links: Array<{ name: PredicateName; role: Role }> = [];
  for (const name of names) {
    const spec = PREDICATES[name];
    if ((spec.subject as readonly string[]).includes(type)) {
      links.push({ name, role: "subject" });
    }
    if (spec.object !== "literal" && (spec.object as readonly string[]).includes(type)) {
      links.push({ name, role: "object" });
    }
  }
  return links.sort(
    (a, b) => predicateLabel(a.name).localeCompare(predicateLabel(b.name)) || a.role.localeCompare(b.role),
  );
}

function objectSummary(name: PredicateName): string {
  const spec = PREDICATES[name];
  if (spec.object === "literal") return "a value";
  const types = (spec.object as readonly string[]).map((t) =>
    t === "literal" ? "a value" : (OBJECT_TYPES[t as ObjectTypeName]?.label ?? t),
  );
  return types.join(" or ");
}

export function ObjectTypeView() {
  const { name } = useParams<{ name: string }>();
  const key = name as ObjectTypeName | undefined;

  if (!key || !(key in OBJECT_TYPES)) {
    return (
      <section className="panel panel--centered" data-testid="object-type-unknown">
        <h1>No such object type</h1>
        <p className="muted">
          <code>{name}</code> is not declared in this ontology. It may belong to a module
          that is not part of this composition.
        </p>
      </section>
    );
  }

  const spec = OBJECT_TYPES[key];
  // Widened for the same reason as `InterfaceView`'s implementors: the
  // generated tuples carry literal lengths, and this branch is about types
  // that implement nothing — which `location` does today and a second domain
  // may not.
  const implemented: readonly string[] = spec.implements;
  const properties = Object.entries(spec.properties);
  const links = linksFor(key);
  const grouped = new Map<string, { label: string; color: string | null; items: typeof links }>();
  for (const link of links) {
    const category = categoryOf(link.name);
    const bucket = grouped.get(category.key) ?? {
      label: category.label,
      color: category.color,
      items: [],
    };
    bucket.items.push(link);
    grouped.set(category.key, bucket);
  }

  return (
    <section className="page" data-testid="object-type">
      <header className="page__head">
        <h1 data-testid="object-type-label">{spec.label}</h1>
        <p className="muted">
          <code>{key}</code> · declared by module <code>{spec.module}</code>
        </p>
      </header>

      {implemented.length > 0 && (
        <p data-testid="object-type-implements">
          Implements{" "}
          {implemented.map((iface, index) => (
            <span key={iface}>
              {index > 0 && ", "}
              <Link to={interfacePath(iface)}>
                {INTERFACES[iface as InterfaceName]?.label ?? iface}
              </Link>
            </span>
          ))}
        </p>
      )}

      {spec.display && (
        <p data-testid="object-type-display">
          Shown as <strong>{propertyLabel(key, spec.display.title)}</strong>
          {spec.display.subtitle && (
            <>
              {" over "}
              <strong>{propertyLabel(key, spec.display.subtitle)}</strong>
            </>
          )}
          <span className="muted">
            {" "}
            — which properties an entity of this type is titled by (spec 09 §6.4)
          </span>
        </p>
      )}

      <h2>Properties</h2>
      {properties.length === 0 ? (
        <p className="muted">This type declares no properties.</p>
      ) : (
        <table className="table" data-testid="object-type-properties">
          <thead>
            <tr>
              <th scope="col">Property</th>
              <th scope="col">Type</th>
              <th scope="col">Notes</th>
            </tr>
          </thead>
          <tbody>
            {properties.map(([propertyName, property]) => (
              <tr key={propertyName}>
                <th scope="row">
                  {property.label}
                  <span className="muted"> ({propertyName})</span>
                </th>
                <td>
                  {property.type}
                  {property.many && <span className="muted"> · many</span>}
                </td>
                <td>
                  {property.required && <span className="tag">required</span>}
                  {property.sensitivity && (
                    <span className="tag tag--hold">{property.sensitivity}</span>
                  )}
                  {/* Article VIII in the schema: two values may both stand. */}
                  {property.conflicts === "preserve" && (
                    <span className="tag">conflicts preserved</span>
                  )}
                  {property.shared && (
                    <span className="muted">shared: {property.shared}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Links</h2>
      {grouped.size === 0 ? (
        <p className="muted">No declared predicate attaches to this type.</p>
      ) : (
        [...grouped.entries()].map(([categoryKey, group]) => (
          <div key={categoryKey} className="object-type__group">
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
            <ul>
              {group.items.map((link) => (
                <li key={`${link.name}:${link.role}`}>
                  <strong>{predicateLabel(link.name)}</strong>{" "}
                  <span className="muted">
                    {link.role === "subject"
                      ? `— this ${spec.label.toLowerCase()} → ${objectSummary(link.name)}`
                      : `— ${subjectSummary(link.name)} → this ${spec.label.toLowerCase()}`}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}

function subjectSummary(name: PredicateName): string {
  const spec = PREDICATES[name];
  const declared = spec.subjectInterfaces as readonly string[];
  if (declared.length > 0) {
    // Say `party` rather than listing its implementors: the declaration is what
    // the ontology means, and the expansion is an implementation detail the
    // store needs (spec 08 §4).
    return declared
      .map((iface) => INTERFACES[iface as InterfaceName]?.label ?? iface)
      .join(" or ");
  }
  return (spec.subject as readonly string[])
    .map((t) => OBJECT_TYPES[t as ObjectTypeName]?.label ?? t)
    .join(" or ");
}

/** Linked from the interface page; kept here so both pages agree on the path. */
export { objectTypePath };
