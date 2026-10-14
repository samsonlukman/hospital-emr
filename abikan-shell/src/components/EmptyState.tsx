import "./Status.css";

interface EmptyStateProps {
  title: string;
  description?: string;
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="abikan-status">
      <p className="abikan-status__title">{title}</p>
      {description ? <p className="abikan-status__copy">{description}</p> : null}
    </div>
  );
}
