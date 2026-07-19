import { useEffect, type ReactNode } from "react";
import { useAuth } from "react-oidc-context";

/**
 * Nothing renders before there is an authenticated caller.
 *
 * The guard redirects rather than showing a login form: there is no local
 * password to collect, and a form that looked like one would be a phishing
 * template. An unauthenticated visit therefore leaves for Keycloak immediately
 * — which is the T22 acceptance criterion, and also the only way a page reload
 * recovers a session whose tokens deliberately died with the tab.
 */
export function AuthGuard({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const { isAuthenticated, isLoading, activeNavigator, error, signinRedirect } = auth;

  useEffect(() => {
    if (!isAuthenticated && !isLoading && !activeNavigator && !error) {
      // Carry where they were through the round trip: a deep link that lands on
      // the login redirect must come back to the same place, not to the root.
      void signinRedirect({
        state: { returnTo: window.location.pathname + window.location.search },
      });
    }
  }, [isAuthenticated, isLoading, activeNavigator, error, signinRedirect]);

  if (error) {
    return (
      <main className="panel panel--centered" role="alert">
        <h1>Sign-in failed</h1>
        <p className="muted">{error.message}</p>
        <button type="button" onClick={() => void signinRedirect()}>
          Try again
        </button>
      </main>
    );
  }

  if (!isAuthenticated) {
    return (
      <main className="panel panel--centered" aria-busy="true">
        <p className="muted">Redirecting to sign in…</p>
      </main>
    );
  }

  return <>{children}</>;
}
