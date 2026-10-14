import type { PatientIdentity } from "../types";
import "./PatientIdentityHeader.css";

interface PatientIdentityHeaderProps {
  patient: PatientIdentity;
  queueNumber?: string;
  visitLabel?: string;
  locationName?: string;
  extraFacts?: Array<{ label: string; value: string }>;
  compact?: boolean;
}

export function PatientIdentityHeader({
  patient,
  queueNumber,
  visitLabel,
  locationName,
  extraFacts = [],
  compact = false,
}: PatientIdentityHeaderProps) {
  const ageLabel = patient.age === "—" ? "Age not recorded" : `${patient.age} years`;

  return (
    <section className={`abikan-identity${compact ? " abikan-identity--compact" : ""}`} aria-label="Patient identity">
      {queueNumber ? <p className="abikan-identity__queue">{queueNumber}</p> : null}
      <div className="abikan-identity__who">
        <h2>{patient.name}</h2>
        <p className="abikan-identity__mrn">{patient.mrn}</p>
        <p className="abikan-identity__meta">
          {ageLabel}
          {" · "}
          {patient.sex}
        </p>
      </div>
      {(visitLabel || locationName || extraFacts.length > 0) ? (
        <dl>
          {visitLabel ? (
            <div>
              <dt>Visit</dt>
              <dd>{visitLabel}</dd>
            </div>
          ) : null}
          {locationName ? (
            <div>
              <dt>Location</dt>
              <dd>{locationName}</dd>
            </div>
          ) : null}
          {extraFacts.map((fact) => (
            <div key={fact.label}>
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}
