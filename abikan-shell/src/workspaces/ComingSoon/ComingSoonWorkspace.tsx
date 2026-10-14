import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { PageHeader } from "../../components/PageHeader";
import { returnToPreviousScreen, shellRouteHref } from "../../app/hashRoute";
import { resolveDefaultWorkplace } from "../../config/workplaces";
import type { WorkspaceContext } from "../../types";
import "./ComingSoonWorkspace.css";

interface ComingSoonWorkspaceProps {
  context: WorkspaceContext;
}

export function ComingSoonWorkspace({ context }: ComingSoonWorkspaceProps) {
  const home = resolveDefaultWorkplace(context);

  return (
    <div className="coming-soon">
      <PageHeader
        title="Coming soon"
        description="This part of Hospital EMR is not ready yet. Your other department work is still available."
      />
      <Card>
        <h2>Not available yet</h2>
        <p>Return to your department to continue the work that is already in place.</p>
        <div className="coming-soon__action">
          <Button variant="secondary" onClick={() => returnToPreviousScreen(shellRouteHref(home.route) || "#/home")}>
            Back to {home.label}
          </Button>
        </div>
      </Card>
    </div>
  );
}
