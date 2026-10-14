import { Button } from "./Button";
import "./Status.css";

interface ErrorStateProps {
  title?: string;
  description?: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = "Unable to load your workspace",
  description = "Please try again. If the problem continues, contact your administrator.",
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="abikan-status abikan-status--center" role="alert">
      <p className="abikan-status__title">{title}</p>
      <p className="abikan-status__copy">{description}</p>
      {onRetry ? (
        <div className="abikan-status__action">
          <Button onClick={onRetry}>Try again</Button>
        </div>
      ) : null}
    </div>
  );
}
