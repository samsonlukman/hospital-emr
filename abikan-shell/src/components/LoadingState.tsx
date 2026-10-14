import "./Status.css";

interface LoadingStateProps {
  label?: string;
  variant?: "page" | "inline" | "board";
}

export function LoadingState({
  label = "Loading your workspace…",
  variant = "page",
}: LoadingStateProps) {
  const layout =
    variant === "inline"
      ? "abikan-status abikan-status--inline"
      : variant === "board"
        ? "abikan-status abikan-status--board"
        : "abikan-status abikan-status--center";
  return (
    <div className={layout} role="status" aria-live="polite">
      <div
        className={
          variant === "inline" ? "abikan-status__spinner abikan-status__spinner--inline" : "abikan-status__spinner"
        }
        aria-hidden="true"
      />
      <p className={variant === "inline" ? "abikan-status__copy" : "abikan-status__title"}>{label}</p>
    </div>
  );
}
