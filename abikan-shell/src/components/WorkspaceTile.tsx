import { IconWell, type IconWellTone } from "./IconWell";
import type { AppIconName } from "./icons";
import type { WorkspaceCardStatus } from "../config/clinicalWorkspaces";
import "./WorkspaceTile.css";

interface WorkspaceTileProps {
  title: string;
  description: string;
  icon: AppIconName;
  tone: IconWellTone;
  status: WorkspaceCardStatus;
  current?: boolean;
  locationHint?: string;
  onOpen?: () => void;
}

export function WorkspaceTile({
  title,
  description,
  icon,
  tone,
  status,
  current,
  locationHint,
  onOpen,
}: WorkspaceTileProps) {
  const ready = status === "ready";
  return (
    <article
      className={`abikan-workspace-tile abikan-workspace-tile--${tone} ${ready ? "is-ready" : ""}`}
    >
      <div className="abikan-workspace-tile__top">
        <IconWell name={icon} tone={tone} size="md" />
        <div>
          <h3>{title}</h3>
          {current ? <p className="abikan-workspace-tile__current">Current location</p> : null}
        </div>
      </div>
      <p className="abikan-workspace-tile__copy">{description}</p>
      {ready && onOpen ? (
        <button type="button" className="abikan-workspace-tile__action" onClick={onOpen}>
          Open →
        </button>
      ) : null}
      {status === "soon" ? (
        <p className="abikan-workspace-tile__status">Coming soon</p>
      ) : null}
      {status === "needs-location" ? (
        <p className="abikan-workspace-tile__status">
          Switch the location selector to {locationHint ?? title} to open this workspace.
        </p>
      ) : null}
    </article>
  );
}
