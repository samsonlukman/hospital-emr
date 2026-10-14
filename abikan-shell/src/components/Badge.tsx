import "./Badge.css";

type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger";

interface BadgeProps {
  tone?: BadgeTone;
  children: string;
}

export function Badge({ tone = "neutral", children }: BadgeProps) {
  return <span className={`abikan-badge abikan-badge--${tone}`}>{children}</span>;
}

export function statusTone(status: string): BadgeTone {
  const value = status.toLowerCase();
  if (value === "open") {
    return "info";
  }
  if (value.includes("check") || value.includes("complete")) {
    return "success";
  }
  if (value.includes("cancel") || value.includes("miss")) {
    return "danger";
  }
  if (value.includes("closed") || value.includes("ended")) {
    return "neutral";
  }
  if (value.includes("attend")) {
    return "info";
  }
  if (value.includes("wait") || value.includes("await") || value.includes("arriv")) {
    return "warning";
  }
  if (value.includes("schedul")) {
    return "info";
  }
  return "neutral";
}
