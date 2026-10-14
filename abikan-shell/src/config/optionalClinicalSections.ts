/**
 * Optional consultation sections. These are labels only.
 * Do not treat dictionary concepts as a hospital OPD form.
 *
 * Examination, Review of Systems, Family History, and Social History
 * are not shown in the Doctor Workspace until the hospital configures
 * usable Bahmni forms. Past medical and medication history are not
 * shown here either: Known Diagnoses and Medications already appear
 * on the chart.
 */

export type OptionalClinicalSectionStatus =
  | "not-configured"
  | "exists-elsewhere"
  | "dictionary-only";

export interface OptionalClinicalSection {
  id: string;
  title: string;
  status: OptionalClinicalSectionStatus;
  /** Staff-facing. No UUIDs, form names, or system jargon. */
  explanation: string;
  required: false;
  defaultOpen: false;
  /** Doctor Workspace must not show unavailable clinical titles. */
  visibleInWorkspace: boolean;
}

export const OPTIONAL_CLINICAL_SECTIONS: OptionalClinicalSection[] = [
  {
    id: "examination",
    title: "Examination",
    status: "not-configured",
    explanation:
      "A general examination is not configured for this consultation yet.",
    required: false,
    defaultOpen: false,
    visibleInWorkspace: false,
  },
  {
    id: "review-of-systems",
    title: "Review of Systems",
    status: "dictionary-only",
    explanation:
      "A system-by-system checklist is not part of this consultation.",
    required: false,
    defaultOpen: false,
    visibleInWorkspace: false,
  },
  {
    id: "past-medical-history",
    title: "Past Medical History",
    status: "exists-elsewhere",
    explanation:
      "Known diagnoses already appear at the top of this chart. A separate past-history form is not configured.",
    required: false,
    defaultOpen: false,
    visibleInWorkspace: false,
  },
  {
    id: "medication-history",
    title: "Medication History",
    status: "exists-elsewhere",
    explanation:
      "Medicines already on this chart are listed under Medications. This is not a second medicine list.",
    required: false,
    defaultOpen: false,
    visibleInWorkspace: false,
  },
  {
    id: "family-history",
    title: "Family History",
    status: "not-configured",
    explanation:
      "Family history is not configured for this consultation.",
    required: false,
    defaultOpen: false,
    visibleInWorkspace: false,
  },
  {
    id: "social-history",
    title: "Social History",
    status: "not-configured",
    explanation:
      "Social history is not configured for this consultation.",
    required: false,
    defaultOpen: false,
    visibleInWorkspace: false,
  },
];

/** Doctor Workspace shows only configured, usable sections. None today. */
export function optionalSectionsVisibleInWorkspace(
  sections: readonly OptionalClinicalSection[] = OPTIONAL_CLINICAL_SECTIONS,
): OptionalClinicalSection[] {
  return sections.filter((section) => section.visibleInWorkspace);
}
