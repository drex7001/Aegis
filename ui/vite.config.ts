import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * The dev server proxies `/v1` to the API so the workspace runs same-origin in
 * development exactly as it does when FastAPI serves the built bundle. Same
 * origin is not a convenience here: it is what keeps the CSP's `connect-src`
 * down to `'self'` plus the identity provider, and what means no CORS policy
 * has to exist to be got wrong.
 *
 * `127.0.0.1`, never `localhost` — on Windows the latter resolves to `::1`
 * first and the API publishes IPv4, so every proxied call pays a failed-IPv6
 * stall (see aegis/config.py for the measurement).
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
  preview: {
    // Literal IPv4, for the reason in the header comment: Vite's default host
    // is `localhost`, which resolves to `::1` first on Windows while the smoke
    // journey dials 127.0.0.1 — the server would come up and the test would
    // still time out waiting for it.
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    /**
     * A copy of the production policy so the smoke journey runs under a
     * realistic CSP — a bundle that only works unpoliced is not a shipped
     * bundle. `aegis/api/security.py` is the authority and the only policy that
     * reaches a user; this is a test fixture, kept in step by hand and asserted
     * against nothing.
     */
    headers: {
      "Content-Security-Policy": [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self' http://localhost:8180",
        "object-src 'none'",
        "frame-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
      ].join("; "),
    },
  },
  build: {
    // Source maps ship: the workspace is an internal tool, and a stack trace an
    // analyst can paste into a bug report is worth more than the bytes.
    sourcemap: true,
  },
});
