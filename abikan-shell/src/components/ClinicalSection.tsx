import type { ReactNode } from "react";
import { Card } from "./Card";
import { SectionHeader } from "./SectionHeader";
import "./ClinicalSection.css";

interface ClinicalSectionProps {
  id?: string;
  title: string;
  description?: string;
  action?: ReactNode;
  variant?: "card" | "panel";
  children: ReactNode;
}

export function ClinicalSection({
  id,
  title,
  description,
  action,
  variant = "card",
  children,
}: ClinicalSectionProps) {
  const body = (
    <>
      <SectionHeader title={title} description={description} action={action} />
      {children}
    </>
  );

  if (variant === "panel") {
    return (
      <section id={id} className="abikan-clinical-panel">
        {body}
      </section>
    );
  }

  return (
    <section id={id}>
      <Card>{body}</Card>
    </section>
  );
}
