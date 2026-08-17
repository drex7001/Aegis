import { useEffect } from "react";
import { useAuth } from "react-oidc-context";
import { useNavigate } from "react-router-dom";

import { takeReturnTo } from "./config";

/**
 * The `/auth/callback` destination: land, then leave.
 *
 * `react-oidc-context` has already redeemed the authorization code by the time
 * this renders — all that is left is to go where the user was heading, through
 * the router, replacing this entry. `replace` is what strips the `code`/`state`
 * query and keeps a spent callback out of the back button (auth/config.ts).
 *
 * P2 did this with `history.replaceState` inside `onSigninCallback`, which the
 * router cannot observe. Doing it here means one owner of the URL.
 */
export function SigninCallback() {
  const auth = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (auth.isAuthenticated) navigate(takeReturnTo(), { replace: true });
  }, [auth.isAuthenticated, navigate]);

  return (
    <main className="panel panel--centered" aria-busy="true">
      <p className="muted">Completing sign-in…</p>
    </main>
  );
}
