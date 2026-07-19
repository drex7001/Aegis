import { AuthGuard } from "./auth/AuthGuard";
import { Shell } from "./layout/Shell";
import { GraphView } from "./views/GraphView";

export function App() {
  return (
    <AuthGuard>
      <Shell>
        <GraphView />
      </Shell>
    </AuthGuard>
  );
}
