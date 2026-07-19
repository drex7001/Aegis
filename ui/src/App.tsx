import { AuthGuard } from "./auth/AuthGuard";
import { Shell } from "./layout/Shell";
import { ROUTES, activeRoute, usePath } from "./routing";
import { GraphView } from "./views/GraphView";
import { ReviewView } from "./views/ReviewView";
import { SourcesView } from "./views/SourcesView";

// A map rather than a ternary chain: `activeRoute` already narrows to a known
// route, so every route has exactly one entry and adding a view cannot forget
// to add its branch.
const VIEWS = {
  [ROUTES.sources]: SourcesView,
  [ROUTES.review]: ReviewView,
  [ROUTES.graph]: GraphView,
} as const;

export function App() {
  const route = activeRoute(usePath());
  const View = VIEWS[route];

  return (
    <AuthGuard>
      <Shell route={route}>
        <View />
      </Shell>
    </AuthGuard>
  );
}
