import { useAuth } from "react-oidc-context";

import { ROUTES, type Route, navigate } from "../routing";

/**
 * The P2 skeleton of spec 07 §4: top bar plus active view. No case column — the
 * case switcher, nav rail and detail panes arrive in P4 with the objects they
 * navigate; a nav bar full of dead links would be a promise the product does
 * not keep.
 */
// Ordered as the work flows: land a record, review what was proposed from it,
// then look at the graph that results.
const VIEWS: Array<{ route: Route; label: string }> = [
  { route: ROUTES.sources, label: "Sources" },
  { route: ROUTES.review, label: "Review" },
  { route: ROUTES.graph, label: "Graph" },
];

export function Shell({ route, children }: { route: Route; children: React.ReactNode }) {
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
        <nav className="shell__nav" aria-label="Views">
          {VIEWS.map((view) => (
            <a
              key={view.route}
              // A real href, so the link opens in a new tab and shows its
              // target in the status bar; the click is intercepted only for
              // the same-document case.
              href={view.route}
              className={`shell__link${route === view.route ? " shell__link--active" : ""}`}
              aria-current={route === view.route ? "page" : undefined}
              onClick={(event) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey) return;
                event.preventDefault();
                navigate(view.route);
              }}
            >
              {view.label}
            </a>
          ))}
        </nav>
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
      <main className="shell__main">{children}</main>
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
