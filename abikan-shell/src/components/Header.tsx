import { useEffect, useState } from "react";
import type { WorkspaceContext } from "../types";
import type { WorkplaceId } from "../config/workplaces";
import { switchableWorkplaces, workplaceFromRoute } from "../config/workplaces";
import type { ShellRoute } from "../app/hashRoute";
import { AccountPhoto } from "./AccountPhoto";
import { AppIcon } from "./icons";
import { PatientSearch } from "./PatientSearch";
import "./Header.css";

interface HeaderProps {
  context: WorkspaceContext;
  workspaceLabel: string;
  pageTitle?: string;
  route: ShellRoute;
  onWorkplaceChange: (workplaceId: WorkplaceId) => void;
  onSignOut: () => void;
  onMenuToggle: () => void;
  onPatientSelect?: (patientUuid: string) => void;
  notificationCount?: number;
  onNotificationsClick?: () => void;
  notificationsOpen?: boolean;
}

function hospitalClock(): { time: string; period: string } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Africa/Lagos",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).formatToParts(new Date());
  const hour = parts.find((part) => part.type === "hour")?.value || "";
  const minute = parts.find((part) => part.type === "minute")?.value || "";
  const period = (parts.find((part) => part.type === "dayPeriod")?.value || "").toUpperCase();
  return { time: `${hour}:${minute}`, period };
}

function useHospitalClock(): { time: string; period: string } {
  const [clock, setClock] = useState(hospitalClock);
  useEffect(() => {
    const timer = window.setInterval(() => setClock(hospitalClock()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  return clock;
}

export function Header({
  context,
  workspaceLabel,
  pageTitle,
  route,
  onWorkplaceChange,
  onSignOut,
  onMenuToggle,
  onPatientSelect,
  notificationCount = 0,
  onNotificationsClick,
  notificationsOpen = false,
}: HeaderProps) {
  const clock = useHospitalClock();
  const workplaces = switchableWorkplaces(context);
  const currentWorkplace = workplaceFromRoute(route) ?? workplaces[0]?.id ?? "";
  const showSwitcher = workplaces.length > 1;
  const showPatientSearch =
    route !== "home" &&
    route !== "staff-accounts" &&
    route !== "department-access" &&
    route !== "admin-analytics" &&
    route !== "admin-audit" &&
    route !== "admin-export" &&
    route !== "admin-patients" &&
    route !== "admin-patient-record" &&
    route !== "accommodation-settings" &&
    route !== "admin-certificates";

  return (
    <header className="abikan-header">
      <a className="abikan-skip" href="#main">
        Skip to content
      </a>
      <div className="abikan-header__left">
        <button
          type="button"
          className="abikan-header__icon-btn"
          onClick={onMenuToggle}
          aria-label="Toggle menu"
        >
          <AppIcon name="menu" size={20} />
        </button>
        <div>
          <p className="abikan-header__product">Hospital EMR</p>
          <h1 className="abikan-header__title">
            {pageTitle || workspaceLabel}
          </h1>
        </div>
      </div>
      {showPatientSearch ? (
        <PatientSearch
          onSelect={onPatientSelect}
          showAdmissionStatus={route === "nursing" || route === "nursing-patient"}
          hospitalNumberSearch={
            route === "pharmacy" ||
            route === "pharmacy-patient" ||
            route === "pharmacy-prescription" ||
            route === "laboratory" ||
            route === "laboratory-patient" ||
            route === "laboratory-order" ||
            route === "registration-desk" ||
            route === "registration-patient" ||
            route === "registration-register" ||
            route === "registration-visit" ||
            route === "registration-patients" ||
            route === "registration-patient-record" ||
            route === "registration-families" ||
            route === "registration-family" ||
            ((route === "patient-account" || route === "patient-account-invoice") &&
              workspaceLabel === "Pharmacy")
          }
        />
      ) : null}
      <div className="abikan-header__right">
        <p className="abikan-header__clock" aria-label={`${clock.time} ${clock.period}`}>
          <time>{clock.time}</time>
          <span>{clock.period}</span>
        </p>
        <button
          type="button"
          className={`abikan-header__icon-btn${notificationCount > 0 ? " abikan-header__icon-btn--alert" : ""}`}
          onClick={onNotificationsClick}
          aria-expanded={notificationsOpen}
          aria-label={
            notificationCount > 0
              ? `${notificationCount} notification${notificationCount === 1 ? "" : "s"} waiting`
              : "Notifications"
          }
          title={
            notificationCount > 0
              ? `${notificationCount} notification${notificationCount === 1 ? "" : "s"} waiting`
              : "Open notifications"
          }
        >
          <AppIcon name="bell" size={20} />
          {notificationCount > 0 ? (
            <span className="abikan-header__badge" aria-hidden="true">
              {notificationCount > 9 ? "9+" : notificationCount}
            </span>
          ) : null}
        </button>
        <label className="abikan-header__fact">
          <span className="abikan-header__label">
            {showSwitcher ? "Switch department" : "Department"}
          </span>
          {showSwitcher ? (
            <select
              className="abikan-header__select"
              value={currentWorkplace}
              onChange={(event) => onWorkplaceChange(event.target.value as WorkplaceId)}
              aria-label="Switch department"
            >
              {workplaces.map((workplace) => (
                <option key={workplace.id} value={workplace.id}>
                  {workplace.label}
                </option>
              ))}
            </select>
          ) : (
            <span className="abikan-header__value">{workspaceLabel}</span>
          )}
        </label>
        <details className="abikan-header__user">
          <summary className="abikan-header__user-toggle">
            <AccountPhoto
              className="abikan-header__avatar"
              fallbackClassName="abikan-header__avatar abikan-header__avatar--empty"
              alt=""
            />
            <span className="abikan-header__user-copy">
              <span className="abikan-header__user-name">{context.displayName}</span>
              <span className="abikan-header__user-id">{context.username}</span>
            </span>
          </summary>
          <div className="abikan-header__user-menu">
            <AccountPhoto
              className="abikan-header__menu-photo"
              fallbackClassName="abikan-header__menu-photo abikan-header__avatar--empty"
              alt=""
            />
            <p className="abikan-header__user-menu-name">{context.displayName}</p>
            <p className="abikan-header__user-menu-id">{context.username}</p>
            <button type="button" className="abikan-header__signout" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        </details>
      </div>
    </header>
  );
}
