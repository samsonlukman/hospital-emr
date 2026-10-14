import { Card } from "../../components/Card";
import { PageHeader } from "../../components/PageHeader";
import { WorkspaceTile } from "../../components/WorkspaceTile";
import { setShellRoute } from "../../app/hashRoute";
import { canOpenAdministration } from "../../config/workspaceMap";
import type { WorkspaceContext } from "../../types";
import "./ClinicalHomeWorkspace.css";

interface ClinicalHomeWorkspaceProps {
  context: WorkspaceContext;
}

export function ClinicalHomeWorkspace({ context }: ClinicalHomeWorkspaceProps) {
  const admin = canOpenAdministration(context);

  if (!admin) {
    return (
      <div className="clinical-home">
        <PageHeader
          title="Home"
          description={`${context.displayName}, open your department from the menu to continue.`}
        />
        <Card>
          <h3>Your department is ready</h3>
          <p>Use the menu on the left for the work you can do today.</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="clinical-home">
      <PageHeader
        title="Administration"
        description={`${context.displayName}, manage the staff directory, hospital overview, and staff activity.`}
      />

      <section className="clinical-home__grid" aria-label="Administration">
        <WorkspaceTile
          title="Patients"
          description="See every registered patient."
          icon="users"
          tone="neutral"
          status="ready"
          onOpen={() => setShellRoute("admin-patients")}
        />
        <WorkspaceTile
          title="Staff directory"
          description="Staff records, employment type, and EMR sign-in where it is needed."
          icon="user"
          tone="neutral"
          status="ready"
          onOpen={() => setShellRoute("staff-accounts")}
        />
        <WorkspaceTile
          title="Department access"
          description="Review and assign approved hospital department roles."
          icon="users"
          tone="neutral"
          status="ready"
          onOpen={() => setShellRoute("department-access")}
        />
        <WorkspaceTile
          title="Hospital overview"
          description="Registrations, visits, occupancy, orders, and collections for the hospital."
          icon="chart"
          tone="neutral"
          status="ready"
          onOpen={() => setShellRoute("admin-analytics")}
        />
        <WorkspaceTile
          title="Staff activity"
          description="See who created, disabled, or changed staff access."
          icon="clipboardList"
          tone="neutral"
          status="ready"
          onOpen={() => setShellRoute("admin-audit")}
        />
        <WorkspaceTile
          title="Data export"
          description="Download hospital records and see who exported what."
          icon="fileText"
          tone="neutral"
          status="ready"
          onOpen={() => setShellRoute("admin-export")}
        />
        <WorkspaceTile
          title="Accommodation Prices"
          description="Set the daily price for each ward and room. Changing a price does not change bills already created."
          icon="settings"
          tone="neutral"
          status="ready"
          onOpen={() => setShellRoute("accommodation-settings")}
        />
        <WorkspaceTile
          title="System Settings"
          description="Hospital-wide settings will open from here."
          icon="settings"
          tone="neutral"
          status="soon"
        />
      </section>
    </div>
  );
}
