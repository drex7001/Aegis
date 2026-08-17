import { Link, useParams } from "react-router-dom";

import {
  INTERFACES,
  OBJECT_TYPES,
  PREDICATES,
  type InterfaceName,
  type ObjectTypeName,
  type PredicateName,
} from "../api/ontology";
import { objectTypePath } from "../routing";

/**
 * An interface is a shape over object types (spec 08 §4), and this page says
 * which types wear it and which links were declared against it.
 *
 * Worth its own screen rather than a line on the type page because the
 * declaration is the thing that survives: `controls` targets `party`, and a
 * third party implementor widens it without the predicate being touched.
 * Reading the ontology from the interface's side is how that becomes visible.
 *
 * Like `ObjectTypeView`, this calls no endpoint — it is the generated
 * descriptors rendered, and nothing here names a domain term (Article XIV).
 */

function predicatesTargeting(name: InterfaceName): Array<{
  predicate: PredicateName;
  role: "subject" | "object";
}> {
  const rows: Array<{ predicate: PredicateName; role: "subject" | "object" }> = [];
  for (const predicate of Object.keys(PREDICATES) as PredicateName[]) {
    const spec = PREDICATES[predicate];
    if ((spec.subjectInterfaces as readonly string[]).includes(name)) {
      rows.push({ predicate, role: "subject" });
    }
    if ((spec.objectInterfaces as readonly string[]).includes(name)) {
      rows.push({ predicate, role: "object" });
    }
  }
  return rows.sort(
    (a, b) =>
      PREDICATES[a.predicate].label.localeCompare(PREDICATES[b.predicate].label) ||
      a.role.localeCompare(b.role),
  );
}

export function InterfaceView() {
  const { name } = useParams<{ name: string }>();
  const key = name as InterfaceName | undefined;

  if (!key || !(key in INTERFACES)) {
    return (
      <section className="panel panel--centered" data-testid="interface-unknown">
        <h1>No such interface</h1>
        <p className="muted">
          <code>{name}</code> is not declared in this ontology.
        </p>
      </section>
    );
  }

  const spec = INTERFACES[key];
  const targeting = predicatesTargeting(key);
  // Widened from the generated `as const` tuple: with two implementors today,
  // TypeScript narrows `.length` to the literal `2` and rejects the empty check
  // as unreachable. It is unreachable *for this composition* — a second domain
  // ships an interface nobody implements, and the branch below is what it
  // renders.
  const implementors: readonly string[] = spec.implementors;

  return (
    <section className="page" data-testid="interface">
      <header className="page__head">
        <h1 data-testid="interface-label">{spec.label}</h1>
        <p className="muted">
          <code>{key}</code> · declared by module <code>{spec.module}</code>
        </p>
      </header>

      <h2>Implemented by</h2>
      {implementors.length === 0 ? (
        <p className="muted">
          No object type in this composition implements it. That is legal — a
          predicate targeting it would not be.
        </p>
      ) : (
        <ul data-testid="interface-implementors">
          {implementors.map((type) => (
            <li key={type}>
              <Link to={objectTypePath(type)}>
                {OBJECT_TYPES[type as ObjectTypeName]?.label ?? type}
              </Link>
            </li>
          ))}
        </ul>
      )}

      <h2>Links declared against it</h2>
      {targeting.length === 0 ? (
        <p className="muted">
          No predicate names this interface as an endpoint. Predicates may still
          target its implementors individually.
        </p>
      ) : (
        <ul data-testid="interface-predicates">
          {targeting.map(({ predicate, role }) => (
            <li key={`${predicate}:${role}`}>
              <strong>{PREDICATES[predicate].label}</strong>{" "}
              <span className="muted">
                — declared with this interface as its {role}; recorded claims
                carry the concrete type
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
