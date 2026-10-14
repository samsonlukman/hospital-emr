import type { NavGroup, WorkspaceContext } from "../types";
import { bahmniUrl } from "../config/appConfig";
import { AccountPhoto } from "./AccountPhoto";
import { AppIcon } from "./icons";
import "./Sidebar.css";

interface SidebarProps {
  groups: NavGroup[];
  context: WorkspaceContext;
  departmentLabel: string;
  activeId?: string;
  open: boolean;
  onNavigate: (itemId: string) => void;
}

export function Sidebar({
  groups,
  context,
  departmentLabel,
  activeId = "home",
  open,
  onNavigate,
}: SidebarProps) {
  return (
    <aside className={`abikan-sidebar ${open ? "is-open" : ""}`} aria-label="Workspace">
      <div className="abikan-sidebar__brand">
        <img src={`${import.meta.env.BASE_URL}abikan-logo.png`} alt="Hospital EMR" />
      </div>
      <nav className="abikan-sidebar__nav">
        {groups.map((group) => (
          <div key={group.id} className="abikan-sidebar__group">
            <p className="abikan-sidebar__heading">{group.label}</p>
            <ul>
              {group.items.map((item) => {
                const active = item.id === activeId;
                const body = (
                  <>
                    <AppIcon name={item.icon} size={20} />
                    <span className="abikan-sidebar__label">{item.label}</span>
                    {item.kind === "soon" ? <em>Soon</em> : null}
                  </>
                );
                if (item.kind === "soon") {
                  return (
                    <li key={item.id}>
                      <span className="abikan-sidebar__item is-soon">{body}</span>
                    </li>
                  );
                }
                if (item.kind === "link") {
                  return (
                    <li key={item.id}>
                      <a
                        className={`abikan-sidebar__item ${active ? "is-active" : ""}`}
                        href={bahmniUrl(item.href)}
                      >
                        {body}
                      </a>
                    </li>
                  );
                }
                if (item.kind === "anchor" || item.kind === "route") {
                  return (
                    <li key={item.id}>
                      <a
                        className={`abikan-sidebar__item ${active ? "is-active" : ""}`}
                        href={item.href}
                        onClick={() => onNavigate(item.id)}
                      >
                        {body}
                      </a>
                    </li>
                  );
                }
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`abikan-sidebar__item ${active ? "is-active" : ""}`}
                      onClick={() => onNavigate(item.id)}
                    >
                      {body}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <div className="abikan-sidebar__user">
        <AccountPhoto
          className="abikan-sidebar__avatar"
          fallbackClassName="abikan-sidebar__avatar"
          alt=""
          showIconFallback
        />
        <div>
          <p className="abikan-sidebar__username">{context.username}</p>
          <p className="abikan-sidebar__role">{departmentLabel}</p>
        </div>
        <span className="abikan-sidebar__online">Online</span>
      </div>
    </aside>
  );
}
