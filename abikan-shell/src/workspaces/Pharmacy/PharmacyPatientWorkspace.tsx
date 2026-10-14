import { useCallback, useEffect, useState } from "react";
import { backWithinPharmacy, openPharmacyPrescription } from "../../app/hashRoute";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { ClinicalAlertBar } from "../../components/ClinicalAlertBar";
import { ClinicalSection } from "../../components/ClinicalSection";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PatientAccountLink } from "../../components/PatientAccountLink";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import { SectionIndex } from "../../components/SectionIndex";
import {
  fetchAllergyState,
  fetchPatientIdentity,
  fetchPatientVisits,
} from "../../services/openmrs/clinicalPatient";
import { fetchPatientDiagnoses } from "../../services/openmrs/clinicalEncounter";
import { fetchPharmacyOrders } from "../../services/openmrs/pharmacy";
import { fetchPharmacyPatientQueue, quantityLabel } from "../../services/pharmacy";
import type {
  AllergyState,
  DiagnosisRecord,
  DrugOrderSummary,
  PatientIdentity,
  PatientVisitSummary,
  WorkspaceContext,
} from "../../types";
import type { PharmacyPrescription } from "../../types/pharmacy";
import { pharmacyStatusTone } from "../PatientAccount/accountBadges";
import {
  groupPrescriptionsForList,
  medicineDisplayName,
  pharmacyLinePaymentLabel,
} from "./pharmacyView";
import "./PharmacyWorkspace.css";

interface PharmacyPatientWorkspaceProps {
  patientUuid: string;
  context: WorkspaceContext;
}

export function PharmacyPatientWorkspace({
  patientUuid,
}: PharmacyPatientWorkspaceProps) {
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [visits, setVisits] = useState<PatientVisitSummary[]>([]);
  const [ready, setReady] = useState<PharmacyPrescription[]>([]);
  const [other, setOther] = useState<PharmacyPrescription[]>([]);
  const [unavailable, setUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [allergyState, setAllergyState] = useState<AllergyState>({
    status: "none-recorded",
  });
  const [diagnoses, setDiagnoses] = useState<DiagnosisRecord[]>([]);
  const [diagnosesUnavailable, setDiagnosesUnavailable] = useState(false);
  const [medications, setMedications] = useState<DrugOrderSummary[]>([]);
  const [nhis, setNhis] = useState(false);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    Promise.allSettled([
      fetchPatientIdentity(patientUuid),
      fetchPatientVisits(patientUuid),
      fetchPharmacyPatientQueue(patientUuid),
      fetchAllergyState(patientUuid),
      fetchPatientDiagnoses(patientUuid),
      fetchPharmacyOrders(patientUuid),
    ]).then(([identity, visitResult, queueResult, allergyResult, diagnosisResult, medicationResult]) => {
      if (cancelled) {
        return;
      }
      if (identity.status === "fulfilled") {
        setPatient(identity.value);
      }
      if (visitResult.status === "fulfilled") {
        setVisits(visitResult.value);
      }
      if (queueResult.status === "fulfilled") {
        setReady(queueResult.value.ready ?? []);
        setOther(queueResult.value.other ?? []);
        setNhis(Boolean(queueResult.value.nhis));
        setUnavailable(false);
      } else {
        setReady([]);
        setOther([]);
        setNhis(false);
        setUnavailable(true);
      }
      if (allergyResult.status === "fulfilled") {
        setAllergyState(allergyResult.value);
      } else {
        setAllergyState({ status: "unavailable" });
      }
      if (diagnosisResult.status === "fulfilled") {
        setDiagnoses(diagnosisResult.value);
        setDiagnosesUnavailable(false);
      } else {
        setDiagnosesUnavailable(true);
      }
      if (medicationResult.status === "fulfilled") {
        setMedications(
          medicationResult.value.map((row) => ({
            uuid: row.uuid,
            display: row.drugName,
          })),
        );
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [patientUuid]);

  useEffect(() => {
    const cancel = load();
    return cancel;
  }, [load]);

  const openVisit = visits.find((visit) => visit.open);
  const visitLabel = openVisit
    ? `${openVisit.visitType} · ${openVisit.startDate}`
    : visits[0]
      ? `${visits[0].visitType} · ${visits[0].startDate}`
      : undefined;
  const dispensed = other.filter((row) => row.dispensingStatus === "DISPENSED");
  const remaining = other.filter((row) => row.dispensingStatus !== "DISPENSED");
  const none = !loading && !unavailable && ready.length === 0 && remaining.length === 0 && dispensed.length === 0;

  return (
    <div className="pharm-patient">
      <div className="pharm-patient__nav">
        <Button variant="ghost" onClick={() => backWithinPharmacy()}>
          ← Back
        </Button>
        <div className="abikan-account-nav">
          <PatientAccountLink patientUuid={patientUuid} label="View Patient Account" />
        </div>
      </div>

      {patient ? (
        <PatientIdentityHeader compact patient={patient} visitLabel={visitLabel} />
      ) : (
        <p className="pharm-patient__muted">Loading patient…</p>
      )}
      {nhis ? <Badge tone="info">NHIS patient</Badge> : null}

      <ClinicalAlertBar
        allergy={allergyState}
        diagnoses={diagnoses}
        diagnosesUnavailable={diagnosesUnavailable}
        medications={medications}
      />

      {none ? (
        <EmptyState title="No prescriptions found." />
      ) : null}

      <div className="abikan-sheet">
      <div className="abikan-sheet__main">
      <ClinicalSection id="ready" title="Ready to dispense">
        {unavailable ? (
          <EmptyState
            title="Prescriptions unavailable"
            description="Prescriptions could not be loaded. Try again in a moment."
          />
        ) : loading ? (
          <LoadingState variant="board" label="Loading prescriptions…" />
        ) : ready.length === 0 ? (
          <EmptyState
            title="Nothing waiting to dispense"
            description="Paid prescriptions for this patient will appear here."
          />
        ) : (
          <ul className="pharm-ready">
            {ready.map((row) => {
              const paymentLabel = pharmacyLinePaymentLabel(row);
              return (
              <li key={row.orderUuid}>
                <div>
                  <p className="pharm-ready__drug">{row.drugName}</p>
                  <p className="pharm-ready__meta">
                    {row.paymentStatus === "NOT BILLED"
                      ? [row.frequency, row.duration].filter(Boolean).join(" · ") || "Quantity not set"
                      : quantityLabel(row)}
                  </p>
                </div>
                {paymentLabel ? (
                  <Badge tone={pharmacyStatusTone(row.paymentStatus)}>{paymentLabel}</Badge>
                ) : null}
                {row.canDispense ? (
                  <Button onClick={() => openPharmacyPrescription(row.orderUuid)}>Dispense</Button>
                ) : (
                  <Button variant="secondary" onClick={() => openPharmacyPrescription(row.orderUuid)}>
                    Open
                  </Button>
                )}
              </li>
              );
            })}
          </ul>
        )}
      </ClinicalSection>

      <ClinicalSection id="other" title="Other prescriptions">
        {remaining.length === 0 ? (
          <EmptyState title="No other prescriptions." />
        ) : (
          <PrescriptionList rows={remaining} />
        )}
      </ClinicalSection>

      <ClinicalSection id="dispensing" title="Already dispensed">
        {dispensed.length === 0 ? (
          <EmptyState
            title="Nothing dispensed yet"
            description="Medicines handed over at the counter will appear here."
          />
        ) : (
          <PrescriptionList rows={dispensed} />
        )}
      </ClinicalSection>
      </div>
      <SectionIndex
        label="Pharmacy sections"
        items={[
          { id: "ready", label: "Ready to dispense" },
          { id: "other", label: "Other prescriptions" },
          { id: "dispensing", label: "Already dispensed" },
        ]}
      />
      </div>
    </div>
  );
}

function PrescriptionList({ rows }: { rows: PharmacyPrescription[] }) {
  const groups = groupPrescriptionsForList(rows);
  return (
    <ul className="pharm-person-list">
      {groups.map((group) => (
        <li key={group.key}>
          <button
            type="button"
            className="pharm-rx-list-card"
            onClick={() => openPharmacyPrescription(group.orderUuid)}
          >
            <strong className="pharm-rx-list-card__count">
              {group.medicineCount} {group.medicineCount === 1 ? "medicine" : "medicines"}
            </strong>
            <span className="pharm-rx-list-card__summary">
              {group.lines.map((line) => medicineDisplayName(line)).join(", ")}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
