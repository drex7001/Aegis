import { useAuth } from "react-oidc-context";

/**
 * The P2 skeleton of spec 07 §4: top bar plus active view. No case column — the
 * case switcher, nav rail and detail panes arrive in P4 with the objects they
 * navigate; a nav bar full of dead links would be a promise the product does
 * not keep.
 */
export function Shell({ children }: { children: React.ReactNode }) {
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
          <a className="shell__link shell__link--active" href="/graph">
            Graph
          </a>
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
