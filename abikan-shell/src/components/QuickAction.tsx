import { IconWell, type IconWellTone } from "./IconWell";
import type { AppIconName } from "./icons";
import "./QuickAction.css";

interface QuickActionProps {
  label: string;
  icon: AppIconName;
  tone: IconWellTone;
  onClick?: () => void;
  disabled?: boolean;
}

export function QuickAction({
  label,
  icon,
  tone,
  onClick,
  disabled,
}: QuickActionProps) {
  return (
    <button
      type="button"
      className={`abikan-quick-action ${disabled ? "is-disabled" : ""}`}
      onClick={onClick}
      disabled={disabled}
    >
      <IconWell name={icon} tone={tone} size="md" />
      <span>{label}</span>
    </button>
  );
}
