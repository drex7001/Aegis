import { useEffect, useState } from "react";

/**
 * Path-based view selection, on the History API directly.
 *
 * P2 has three views, and a router library is not what three views need. What
 * they do need is real URLs — the back button, a deep link to `/sources`, and a
 * path the auth guard can hand to `returnTo` — which is all this provides.
 *
 * The reason it is here rather than `react-router` is narrower than "fewer
 * dependencies": the OIDC callback finishes by rewriting the URL with
 * `history.replaceState` (auth/config.ts), and a router that owns the history
 * stack would not observe that write. Swapping in a router therefore means
 * re-testing the sign-in round trip, and it is worth doing once, in P4, when
 * the view count actually justifies it — not now, for two.
 */

export const ROUTES = {
  graph: "/graph",
  sources: "/sources",
  review: "/review",
} as const;

export type Route = (typeof ROUTES)[keyof typeof ROUTES];

/**
 * Neither `pushState` nor `replaceState` fires an event, so any code that moves
 * the URL has to say so. `notifyNavigated` is that announcement, and the
 * sign-in callback is the caller that is easy to forget: it rewrites the URL to
 * the page the user originally asked for, *after* the app has already mounted
 * at `/auth/callback`. Without the notification the app renders the fallback
 * view at the right URL — which is what happened, and what the sources journey
 * caught.
 */
const NAVIGATED = "aegis:navigated";

export function notifyNavigated(): void {
  window.dispatchEvent(new Event(NAVIGATED));
}

export function usePath(): string {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const sync = () => setPath(window.location.pathname);
    window.addEventListener("popstate", sync);
    window.addEventListener(NAVIGATED, sync);
    // The signin callback replaces the URL after this component mounts, so read
    // it once more on mount rather than trusting the initial render's value.
    sync();
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener(NAVIGATED, sync);
    };
  }, []);

  return path;
}

export function navigate(to: Route): void {
  if (window.location.pathname === to) return;
  window.history.pushState({}, "", to);
  notifyNavigated();
}

/** `/` opens the graph; anything unrecognised does too, rather than 404-ing. */
export function activeRoute(path: string): Route {
  if (path.startsWith(ROUTES.sources)) return ROUTES.sources;
  if (path.startsWith(ROUTES.review)) return ROUTES.review;
  return ROUTES.graph;
}
