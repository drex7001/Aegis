import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "react-oidc-context";

import { ROUTES } from "../routing";
import { CaseSwitcher } from "./CaseSwitcher";
import { OntologyNav } from "./OntologyNav";
import { VersionBanner } from "./VersionBanner";

/**
 * Spec 07 §4's layout, as far as P4 has destinations for it: a top bar, a left
 * rail, and the active view.
 *
 * P2 shipped the top bar alone and said why the rail was absent — "a nav bar
 * full of dead links would be a promise the product does not keep". That rule
 * still governs what is here: the case switcher, the workspace views that
 * exist, and the ontology's own types and interfaces, each with a screen behind
 * it.
 *
 * The ontology section is generated, not written (ADR-043) — see `OntologyNav`.
 * The case switcher arrived at T46, when `GET /v1/cases` gave it something to
 * switch between; until then the slot was empty rather than filled with a
 * control that led nowhere.
 */

// Ordered as the work flows: land a record, review what was proposed from it,
// then look at the graph that results.
const WORKSPACE_VIEWS: Array<{ to: string; label: string }> = [
  { to: ROUTES.sources, label: "Sources" },
  { to: ROUTES.review, label: "Review" },
  { to: ROUTES.graph, label: "Graph" },
];

export function Shell() {
  const auth = useAuth();
  const profile = auth.user?.profile;
  const roles = extractRoles(auth.user?.profile);

  return (
    <div className="shell">
      <header className="shell__bar">
        <div className="shell__brand">
          <strong>Aegis</strong>
          <span className="muted">investigation workspace</span>
        </div>
        <div className="shell__spacer" />
        <div className="shell__user">
          <span data-testid="username">
            {(profile?.preferred_username as string | undefined) ?? profile?.sub}
          </span>
          {roles.length > 0 && <span className="muted">{roles.join(", ")}</span>}
          <button
            type="button"
            onClick={() => void auth.signoutRedirect()}
            className="shell__signout"
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="shell__body">
        <nav className="rail" aria-label="Workspace">
          <CaseSwitcher />
          <div className="rail__group">
            <h2 className="rail__heading">Workspace</h2>
            <ul className="rail__list" data-testid="nav-workspace">
              {WORKSPACE_VIEWS.map((view) => (
                <li key={view.to}>
                  <NavLink
                    to={view.to}
                    className={({ isActive }) =>
                      `rail__link${isActive ? " rail__link--active" : ""}`
                    }
                  >
                    {view.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
          <OntologyNav />
        </nav>

        <div className="shell__content">
          <VersionBanner />
          <main className="shell__main">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}

/**
 * Displayed for orientation only. Every authorization decision is the API's:
 * a role claim rendered here says what the token asserts, not what the caller
 * may do, and no view is unlocked by reading it (Article VI).
 */
function extractRoles(profile: Record<string, unknown> | undefined): string[] {
  const realmAccess = profile?.["realm_access"] as { roles?: string[] } | undefined;
  return realmAccess?.roles ?? [];
}
