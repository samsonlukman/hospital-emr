import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { PageHeader } from "../../components/PageHeader";
import { returnToPreviousScreen, shellRouteHref } from "../../app/hashRoute";
import { resolveDefaultWorkplace } from "../../config/workplaces";
import type { WorkspaceContext } from "../../types";
import "../ComingSoon/ComingSoonWorkspace.css";

interface PageUnavailableWorkspaceProps {
  context: WorkspaceContext;
}

export function PageUnavailableWorkspace({ context }: PageUnavailableWorkspaceProps) {
  const home = resolveDefaultWorkplace(context);
  return (
    <div className="coming-soon">
      <PageHeader
        title="Page not available"
        description="That page is not part of Hospital EMR. You can return to your department."
      />
      <Card>
        <h2>Page not available</h2>
        <p>The address you opened is not a hospital page. Nothing else was changed.</p>
        <div className="coming-soon__action">
          <Button variant="secondary" onClick={() => returnToPreviousScreen(shellRouteHref(home.route) || "#/home")}>
            Back to {home.label}
          </Button>
        </div>
      </Card>
    </div>
  );
}
