import type { OptionalClinicalSection as OptionalClinicalSectionConfig } from "../config/optionalClinicalSections";

interface OptionalClinicalSectionProps {
  section: OptionalClinicalSectionConfig;
}

export function OptionalClinicalSection({ section }: OptionalClinicalSectionProps) {
  return (
    <details className="abikan-docs__optional">
      <summary>
        <span>{section.title}</span>
      </summary>
      <p className="abikan-docs__muted">{section.explanation}</p>
    </details>
  );
}
