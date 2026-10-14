import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Header } from "../components/Header";
import { StaffTalkDock } from "../components/StaffTalkDock";
import { StaffNotificationCenter } from "../components/StaffNotificationCenter";
import { Sidebar } from "../components/Sidebar";
import type { NavGroup, WorkspaceContext } from "../types";
import type { WorkplaceId } from "../config/workplaces";
import type { ShellRoute } from "../app/hashRoute";
import "./AppShell.css";
import { sendPresenceHeartbeat } from "../services/messaging";

interface AppShellProps {
  context: WorkspaceContext;
  workspaceLabel: string;
  pageTitle?: string;
  route: ShellRoute;
  navGroups: NavGroup[];
  activeId?: string;
  onWorkplaceChange: (workplaceId: WorkplaceId) => void;
  onSignOut: () => void;
  onPatientSelect?: (patientUuid: string) => void;
  children: ReactNode;
}

export function AppShell({
  context,
  workspaceLabel,
  pageTitle,
  route,
  navGroups,
  activeId,
  onWorkplaceChange,
  onSignOut,
  onPatientSelect,
  children,
}: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [patientCallCount, setPatientCallCount] = useState(0);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const handlePatientCallCount = useCallback((count: number) => {
    setPatientCallCount(count);
  }, []);

  useEffect(() => {
    void sendPresenceHeartbeat().catch(() => undefined);
    const timer = window.setInterval(() => {
      void sendPresenceHeartbeat().catch(() => undefined);
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [context.username]);

  const handleNavigate = (itemId: string) => {
    setMobileOpen(false);
    if (itemId === "search" || itemId === "patient-accounts") {
      document.getElementById("global-patient-search")?.focus();
    }
  };

  const handleMenuToggle = () => {
    if (window.matchMedia("(max-width: 900px)").matches) {
      setMobileOpen((open) => !open);
      return;
    }
    setCollapsed((value) => !value);
  };

  return (
    <div
      className={`abikan-shell ${collapsed ? "is-collapsed" : ""} ${mobileOpen ? "is-nav-open" : ""}`}
    >
      {navGroups.length > 0 ? (
        <Sidebar
          groups={navGroups}
          context={context}
          departmentLabel={workspaceLabel}
          activeId={activeId}
          open={mobileOpen}
          onNavigate={handleNavigate}
        />
      ) : null}
      {mobileOpen ? (
        <button
          type="button"
          className="abikan-shell__backdrop"
          aria-label="Close menu"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}
      <div className="abikan-shell__content">
        <Header
          context={context}
          workspaceLabel={workspaceLabel}
          pageTitle={pageTitle}
          route={route}
          onWorkplaceChange={onWorkplaceChange}
          onSignOut={onSignOut}
          onMenuToggle={handleMenuToggle}
          onPatientSelect={onPatientSelect}
          notificationCount={patientCallCount}
          notificationsOpen={notificationsOpen}
          onNotificationsClick={() => setNotificationsOpen((open) => !open)}
        />
        <main
          id="main"
          className={`abikan-shell__main${
            pageTitle || !route.startsWith("admin") ? " abikan-shell__main--tight" : ""
          }`}
        >
          <StaffNotificationCenter
            context={context}
            route={route}
            onPendingCountChange={handlePatientCallCount}
            listOpen={notificationsOpen}
            onListClose={() => setNotificationsOpen(false)}
          />
          {children}
        </main>
        <StaffTalkDock context={context} />
        <footer className="abikan-shell__footer">
          <p>© 2026 Hospital EMR. All rights reserved.</p>
          <p>Hospital EMR v0.1.0</p>
        </footer>
      </div>
    </div>
  );
}
