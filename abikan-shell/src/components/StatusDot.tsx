import "./StatusDot.css";

type StatusTone = "neutral" | "success" | "warning" | "danger";

interface StatusDotProps {
  tone?: StatusTone;
  label: string;
}

export function StatusDot({ tone = "neutral", label }: StatusDotProps) {
  return (
    <span className={`abikan-status-dot abikan-status-dot--${tone}`}>
      <span className="abikan-status-dot__mark" aria-hidden="true" />
      {label}
    </span>
  );
}
