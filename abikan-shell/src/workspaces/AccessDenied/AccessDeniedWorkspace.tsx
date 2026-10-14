import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { PageHeader } from "../../components/PageHeader";
import { returnToPreviousScreen, shellRouteHref } from "../../app/hashRoute";
import { resolveDefaultWorkplace } from "../../config/workplaces";
import type { WorkspaceContext } from "../../types";
import "../ComingSoon/ComingSoonWorkspace.css";

interface AccessDeniedWorkspaceProps {
  context: WorkspaceContext;
}

export function AccessDeniedWorkspace({ context }: AccessDeniedWorkspaceProps) {
  const home = resolveDefaultWorkplace(context);
  return (
    <div className="coming-soon">
      <PageHeader
        title="You do not have access to this department"
        description="This department is not available for your account."
      />
      <Card>
        <h2>What to do</h2>
        <p>
          Ask your administrator to review your access. You will stay inside Hospital EMR.
        </p>
        <div className="coming-soon__action">
          <Button variant="secondary" onClick={() => returnToPreviousScreen(shellRouteHref(home.route) || "#/home")}>
            Back to {home.label}
          </Button>
        </div>
      </Card>
    </div>
  );
}
