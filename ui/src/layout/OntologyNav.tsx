import { NavLink } from "react-router-dom";

import {
  INTERFACES,
  OBJECT_TYPES,
  type InterfaceName,
  type ObjectTypeName,
} from "../api/ontology";
import { interfacePath, objectTypePath } from "../routing";

/**
 * The rail's ontology section, built from the generated descriptors and nothing
 * else (Article XI, ADR-043).
 *
 * There is no list of types in this file, and there must never be one: adding
 * `vessel` to a domain module and regenerating puts a working `vessel` entry
 * here, and removing `vehicle` removes it. That is the whole claim T42 makes,
 * and `tests/contract/test_second_domain.py` enforces the negative half of it —
 * no file under `ui/src` may name a domain term.
 *
 * Ordering is by label rather than by the descriptor's key order, because the
 * key order is the generator's (alphabetical by name) and a reader is looking
 * for the word they can see. Ties fall back to the name so the order is total
 * and two runs render the same rail.
 */

type Entry = { key: string; label: string; to: string; module: string };

function byLabelThenKey(a: Entry, b: Entry): number {
  return a.label.localeCompare(b.label) || a.key.localeCompare(b.key);
}

export function objectTypeEntries(): Entry[] {
  return (Object.keys(OBJECT_TYPES) as ObjectTypeName[])
    .map((name) => ({
      key: name,
      label: OBJECT_TYPES[name].label,
      to: objectTypePath(name),
      module: OBJECT_TYPES[name].module,
    }))
    .sort(byLabelThenKey);
}

export function interfaceEntries(): Entry[] {
  return (Object.keys(INTERFACES) as InterfaceName[])
    .map((name) => ({
      key: name,
      label: INTERFACES[name].label,
      to: interfacePath(name),
      module: INTERFACES[name].module,
    }))
    .sort(byLabelThenKey);
}

function Group({ title, entries, testId }: { title: string; entries: Entry[]; testId: string }) {
  if (entries.length === 0) return null;
  return (
    <div className="rail__group">
      <h2 className="rail__heading">{title}</h2>
      <ul className="rail__list" data-testid={testId}>
        {entries.map((entry) => (
          <li key={entry.key}>
            <NavLink
              to={entry.to}
              className={({ isActive }) =>
                `rail__link${isActive ? " rail__link--active" : ""}`
              }
            >
              {entry.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function OntologyNav() {
  return (
    <>
      <Group title="Object types" entries={objectTypeEntries()} testId="nav-object-types" />
      <Group title="Interfaces" entries={interfaceEntries()} testId="nav-interfaces" />
    </>
  );
}
