import type { ReactNode } from "react";
import { IconWell, type IconWellTone } from "./IconWell";
import type { AppIconName } from "./icons";
import "./KpiCard.css";

interface KpiCardProps {
  label: string;
  value: ReactNode;
  hint?: string;
  actionLabel?: string;
  tone?: IconWellTone;
  icon: AppIconName;
  onAction?: () => void;
  onClick?: () => void;
}

export function KpiCard({
  label,
  value,
  hint,
  actionLabel,
  tone = "registration",
  icon,
  onAction,
  onClick,
}: KpiCardProps) {
  return (
    <article
      className={`abikan-kpi abikan-kpi--${tone}${onClick ? " is-clickable" : ""}`}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className="abikan-kpi__top">
        <IconWell name={icon} tone={tone} size="lg" />
        <p className="abikan-kpi__label">{label}</p>
      </div>
      <p className="abikan-kpi__value">{value}</p>
      {hint ? <p className="abikan-kpi__hint">{hint}</p> : null}
      {actionLabel && onAction ? (
        <button
          type="button"
          className="abikan-kpi__action"
          onClick={(event) => {
            event.stopPropagation();
            onAction();
          }}
        >
          {actionLabel} →
        </button>
      ) : actionLabel && onClick ? (
        <span className="abikan-kpi__action">{actionLabel} →</span>
      ) : null}
    </article>
  );
}
