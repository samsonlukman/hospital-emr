import { useCallback, useEffect, useRef, useState } from "react";
import { WorkspaceRouter } from "./app/WorkspaceRouter";
import { readShellRoute, rememberScreen, setShellRoute, type ShellRoute } from "./app/hashRoute";
import { allowConsultationLeave } from "./services/consultationLeaveGuard";
import { LoadingState } from "./components/LoadingState";
import { ErrorState } from "./components/ErrorState";
import { BrandBar } from "./components/BrandBar";
import { canOpenAdministration, resolveWorkspaceId } from "./config/workspaceMap";
import {
  resolveDefaultWorkplace,
  resolveRouteForUser,
  workplaceById,
  type WorkplaceId,
} from "./config/workplaces";
import { changeLoginLocation, fetchLocationByName } from "./services/openmrs/location";
import {
  loadWorkspaceContext,
  MissingLocationError,
  UnauthenticatedError,
} from "./services/openmrs/loadWorkspaceContext";
import { destroySession } from "./services/openmrs/session";
import type { LoadState } from "./types";
import { SessionInitError } from "./services/openmrs/signIn";
import { LoginWorkspace } from "./workspaces/Login/LoginWorkspace";
import { StaffLogTerminal } from "./workspaces/StaffLog/StaffLogTerminal";
import { isAttendanceTerminalLocation } from "./workspaces/StaffLog/staffLogView";
import "./layouts/AppShell.css";
import { applyTheme, readTheme } from "./utils/appearanceSettings";

function friendlyError(): { title: string; description: string } {
  return {
    title: "Unable to load your workspace",
    description:
      "Please try again. If this continues, contact your administrator.",
  };
}

function applyLandingIfNeeded(
  route: ShellRoute,
  defaultRoute: ShellRoute,
  admin: boolean,
): void {
  if (route === "workspace" || route === "unavailable") {
    setShellRoute(defaultRoute);
    return;
  }
  if (route === "home" && !admin) {
    setShellRoute(defaultRoute);
  }
}

export function App() {
  const [terminal, setTerminal] = useState(isAttendanceTerminalLocation);
  useEffect(() => {
    const sync = () => setTerminal(isAttendanceTerminalLocation());
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);
  if (terminal) {
    return <StaffLogTerminal />;
  }
  return <HospitalApp />;
}

function HospitalApp() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [route, setRoute] = useState<ShellRoute>(readShellRoute);
  const [hash, setHash] = useState(() => window.location.hash);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    applyTheme(readTheme());
  }, []);

  const load = useCallback(async (): Promise<"ready" | "unauthenticated" | "error"> => {
    setState((current) =>
      current.status === "unauthenticated" ? current : { status: "loading" },
    );
    try {
      const context = await loadWorkspaceContext();
      const landing = resolveDefaultWorkplace(context);
      applyLandingIfNeeded(readShellRoute(), landing.route, canOpenAdministration(context));
      const visible = resolveRouteForUser(readShellRoute(), context);
      if (visible !== "unavailable" && visible !== readShellRoute()) {
        setShellRoute(visible);
      }
      setRoute(visible);
      setState({
        status: "ready",
        context,
        workspaceId: resolveWorkspaceId(context),
      });
      return "ready";
    } catch (error) {
      if (error instanceof UnauthenticatedError) {
        setState({ status: "unauthenticated" });
        return "unauthenticated";
      }
      if (error instanceof MissingLocationError) {
        setState({ status: "error", message: "location" });
        return "error";
      }
      const code = error instanceof Error ? error.message : "session";
      console.error("Hospital EMR workspace load failed", error);
      setState({ status: "error", message: code });
      return "error";
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    rememberScreen();
  }, []);

  useEffect(() => {
    const onHashChange = () => {
      const next = readShellRoute();
      if (!allowConsultationLeave(next)) {
        return;
      }
      const current = stateRef.current;
      if (current.status !== "ready") {
        setRoute(next);
        setHash(window.location.hash);
        rememberScreen();
        return;
      }
      const resolved = resolveRouteForUser(next, current.context);
      if (resolved !== next && resolved !== "unavailable") {
        setShellRoute(resolved);
      }
      setRoute(resolved);
      setHash(window.location.hash);
      rememberScreen();
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const handleWorkplaceChange = async (workplaceId: WorkplaceId) => {
    if (state.status !== "ready") {
      return;
    }
    const workplace = workplaceById(workplaceId);
    try {
      const location = await fetchLocationByName(workplace.sessionLocationName);
      if (location) {
        await changeLoginLocation(location);
      }
      const context = await loadWorkspaceContext();
      setState({
        status: "ready",
        context,
        workspaceId: resolveWorkspaceId(context),
      });
      setShellRoute(workplace.route);
      setRoute(workplace.route);
    } catch (error) {
      console.error("Unable to change workplace", error);
      setState({ status: "error", message: "location" });
    }
  };

  const handleSignOut = async () => {
    try {
      await destroySession();
    } catch (error) {
      console.error("Unable to sign out cleanly", error);
    }
    const loggedOut: LoadState = { status: "unauthenticated" };
    stateRef.current = loggedOut;
    setState(loggedOut);
    setRoute("home");
    window.location.hash = "#/home";
  };

  if (state.status === "unauthenticated") {
    return (
      <LoginWorkspace
        onComplete={async () => {
          const result = await load();
          if (result === "unauthenticated") {
            throw new SessionInitError();
          }
        }}
      />
    );
  }

  if (state.status === "loading") {
    return (
      <div className="abikan-shell">
        <BrandBar />
        <LoadingState />
      </div>
    );
  }

  if (state.status === "error") {
    const copy = friendlyError();
    return (
      <div className="abikan-shell">
        <BrandBar />
        <ErrorState
          title={copy.title}
          description={copy.description}
          onRetry={() => {
            void load();
          }}
        />
      </div>
    );
  }

  return (
    <WorkspaceRouter
      context={state.context}
      workspaceId={state.workspaceId}
      route={route}
      hash={hash}
      onWorkplaceChange={(id) => {
        void handleWorkplaceChange(id);
      }}
      onSignOut={() => {
        void handleSignOut();
      }}
    />
  );
}
