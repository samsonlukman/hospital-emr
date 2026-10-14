import { patientAccountHref } from "../app/hashRoute";
import "./PatientAccountLink.css";

interface PatientAccountLinkProps {
  patientUuid: string;
  visitUuid?: string | null;
  label?: string;
}

export function PatientAccountLink({
  patientUuid,
  visitUuid,
  label = "Patient Account",
}: PatientAccountLinkProps) {
  return (
    <a className="abikan-account-link" href={patientAccountHref(patientUuid, visitUuid)}>
      {label}
    </a>
  );
}
