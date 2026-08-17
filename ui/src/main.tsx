import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AuthProvider } from "react-oidc-context";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { ApiError } from "./api/client";
import { oidcConfig } from "./auth/config";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Authorization can change under the caller (a case membership is
      // revoked, a clearance lowered), and a cache that outlived it would keep
      // drawing a graph the API would now refuse. Short and never on window
      // focus alone.
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) =>
        error instanceof ApiError && error.status >= 500 && failureCount < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider {...oidcConfig}>
      <QueryClientProvider client={queryClient}>
        {/*
         * Outside `AuthProvider` would be wrong: `SigninCallback` needs both,
         * and the router has to be the single owner of history so nothing
         * rewrites the URL behind it (auth/config.ts).
         */}
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </AuthProvider>
  </StrictMode>,
);
