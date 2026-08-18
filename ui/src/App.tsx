import { Navigate, Route, Routes } from "react-router-dom";

import { AuthGuard } from "./auth/AuthGuard";
import { SigninCallback } from "./auth/SigninCallback";
import { Shell } from "./layout/Shell";
import { ROUTES } from "./routing";
import { GraphView } from "./views/GraphView";
import { InterfaceView } from "./views/InterfaceView";
import { ObjectTypeView } from "./views/ObjectTypeView";
import { ObjectView } from "./views/ObjectView";
import { ReviewView } from "./views/ReviewView";
import { SourcesView } from "./views/SourcesView";

/**
 * The route table, rendered. `Shell` is a layout route, so every view below it
 * gets the bar, the rail and the version banner without knowing they exist.
 *
 * `AuthGuard` wraps the whole table rather than sitting inside it: there is no
 * unauthenticated destination in this application (ADR-026), and putting the
 * guard on individual routes is how one eventually gets forgotten.
 * `/auth/callback` is inside the guard too — it is reached mid-sign-in, when
 * `activeNavigator` is set and the guard is already standing aside.
 */
export function App() {
  return (
    <AuthGuard>
      <Routes>
        <Route path={ROUTES.signinCallback} element={<SigninCallback />} />
        <Route element={<Shell />}>
          <Route path={ROUTES.graph} element={<GraphView />} />
          <Route path={ROUTES.sources} element={<SourcesView />} />
          <Route path={ROUTES.review} element={<ReviewView />} />
          <Route path={ROUTES.entity} element={<ObjectView />} />
          <Route path={ROUTES.objectType} element={<ObjectTypeView />} />
          <Route path={ROUTES.interface} element={<InterfaceView />} />
          {/*
           * `/` opens the graph, and so does anything unrecognised — the P2
           * behaviour, kept. A 404 page for a mistyped internal URL would be
           * accurate and useless.
           */}
          <Route path="*" element={<Navigate to={ROUTES.graph} replace />} />
        </Route>
      </Routes>
    </AuthGuard>
  );
}
