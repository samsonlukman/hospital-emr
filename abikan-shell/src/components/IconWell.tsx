import { AppIcon, type AppIconName } from "./icons";
import "./IconWell.css";

export type IconWellTone =
  | "registration"
  | "appointments"
  | "visits"
  | "collection"
  | "teal"
  | "neutral";

export type IconWellSize = "sm" | "md" | "lg";

interface IconWellProps {
  name: AppIconName;
  tone?: IconWellTone;
  size?: IconWellSize;
}

const ICON_PX: Record<IconWellSize, number> = {
  sm: 18,
  md: 26,
  lg: 36,
};

export function IconWell({
  name,
  tone = "neutral",
  size = "md",
}: IconWellProps) {
  return (
    <span className={`abikan-icon-well abikan-icon-well--${tone} abikan-icon-well--${size}`}>
      <AppIcon name={name} size={ICON_PX[size]} />
    </span>
  );
}
