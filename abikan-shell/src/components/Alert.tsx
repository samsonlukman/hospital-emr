import type { ReactNode } from "react";
import "./Alert.css";

type AlertTone = "info" | "warning" | "danger" | "success";

interface AlertProps {
  tone?: AlertTone;
  title: string;
  children?: ReactNode;
}

export function Alert({ tone = "info", title, children }: AlertProps) {
  return (
    <div className={`abikan-alert abikan-alert--${tone}`} role="status">
      <p className="abikan-alert__title">{title}</p>
      {children ? <div className="abikan-alert__body">{children}</div> : null}
    </div>
  );
}
