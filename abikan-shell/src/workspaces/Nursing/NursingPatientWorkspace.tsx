import { useCallback, useEffect, useRef, useState } from "react";
import { returnToPreviousScreen } from "../../app/hashRoute";
import { BAHMNI_ROUTES, bahmniUrl } from "../../config/appConfig";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { AllergyPanel } from "../../components/AllergyPanel";
import { ClinicalAlertBar } from "../../components/ClinicalAlertBar";
import { ClinicalSection } from "../../components/ClinicalSection";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { MedicationAdministrationPanel } from "../../components/MedicationAdministrationPanel";
import { NursingTasksPanel } from "../../components/NursingTasksPanel";
import { PatientAccountLink } from "../../components/PatientAccountLink";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import { SectionIndex } from "../../components/SectionIndex";
import { NursingNotesPanel } from "../../components/NursingNotesPanel";
import { InpatientVitalsPanel } from "../../components/InpatientVitalsPanel";
import {
  assignInpatientBed,
  cancelWaitingAdmission,
  dischargeInpatient,
  fetchInpatientBoard,
  fetchInpatientStay,
  fetchMar,
  newInpatientRequestId,
  transferInpatientBed,
} from "../../services/inpatient";
import { fetchPatientDiagnoses } from "../../services/openmrs/clinicalEncounter";
import {
  fetchAllergyState,
  fetchDrugOrders,
  fetchPatientEncounters,
  fetchPatientIdentity,
  fetchPatientVisits,
  fetchVitalHistory,
} from "../../services/openmrs/clinicalPatient";
import {
  medicationsForChart,
  type OrderAdministration,
} from "../../services/openmrs/drugOrders";
import type { InpatientBoard, InpatientStay } from "../../types/inpatient";
import { paymentStateTone } from "../PatientAccount/accountBadges";
import type {
  AllergyState,
  DiagnosisRecord,
  DrugOrderSummary,
  EncounterSummary,
  PatientIdentity,
  PatientVisitSummary,
  VitalReading,
  WorkspaceContext,
} from "../../types";
import { formatDate } from "../../utils/datetime";
import { InpatientConfirmDialog, WardBedPicker, bedLabel } from "./InpatientDialogs";
import { displayBedNumber, locationLabel, staffBedConflictMessage, wardRequestError } from "./nursingBoard";
import "./NursingPatientWorkspace.css";

interface NursingPatientWorkspaceProps {
  patientUuid: string;
  context: WorkspaceContext;
}

const FLOW = [
  { id: "alerts", label: "Alerts" },
  { id: "condition", label: "Condition" },
  { id: "vitals", label: "Vitals" },
  { id: "mar", label: "Medication" },
  { id: "tasks", label: "Tasks" },
  { id: "notes", label: "Notes" },
  { id: "doctor", label: "Doctor" },
  { id: "admission", label: "Admission" },
  { id: "discharge", label: "Discharge" },
] as const;

function allergyStickyLabel(allergy: AllergyState): string {
  if (allergy.status === "recorded") {
    return allergy.items[0] ? `Allergy: ${allergy.items[0]}` : "Allergies recorded";
  }
  if (allergy.status === "unavailable") {
    return "Allergies unavailable";
  }
  return "Allergies: Not recorded";
}

export function NursingPatientWorkspace({ patientUuid }: NursingPatientWorkspaceProps) {
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [visits, setVisits] = useState<PatientVisitSummary[]>([]);
  const [vitalHistory, setVitalHistory] = useState<Record<string, VitalReading[]>>({});
  const [diagnoses, setDiagnoses] = useState<DiagnosisRecord[]>([]);
  const [diagnosesUnavailable, setDiagnosesUnavailable] = useState(false);
  const [medications, setMedications] = useState<DrugOrderSummary[]>([]);
  const [wardAdministration, setWardAdministration] = useState<OrderAdministration[] | null>(null);
  const [medicationsUnavailable, setMedicationsUnavailable] = useState(false);
  const [encounters, setEncounters] = useState<EncounterSummary[]>([]);
  const [encountersUnavailable, setEncountersUnavailable] = useState(false);
  const [allergyState, setAllergyState] = useState<AllergyState>({
    status: "none-recorded",
  });
  const [stay, setStay] = useState<InpatientStay | null>(null);
  const [board, setBoard] = useState<InpatientBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [stuck, setStuck] = useState(false);
  const [notice, setNotice] = useState("");
  const [dialog, setDialog] = useState<"assign" | "transfer" | "discharge" | "cancel-admission" | null>(null);
  const [pickedBedUuid, setPickedBedUuid] = useState("");
  const [dialogError, setDialogError] = useState("");
  const [busy, setBusy] = useState(false);
  const identityRef = useRef<HTMLDivElement>(null);

  const loadClinical = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    Promise.allSettled([
      fetchPatientIdentity(patientUuid),
      fetchPatientVisits(patientUuid),
      fetchVitalHistory(patientUuid),
      fetchPatientDiagnoses(patientUuid),
      fetchDrugOrders(patientUuid),
      fetchAllergyState(patientUuid),
      fetchPatientEncounters(patientUuid),
      fetchInpatientStay(patientUuid),
    ]).then(
      ([
        identity,
        visitResult,
        vitalResult,
        diagnosisResult,
        drugResult,
        allergyResult,
        encounterResult,
        stayResult,
      ]) => {
        if (cancelled) {
          return;
        }
        if (identity.status === "fulfilled") {
          setPatient(identity.value);
        }
        if (visitResult.status === "fulfilled") {
          setVisits(visitResult.value);
        }
        if (vitalResult.status === "fulfilled") {
          setVitalHistory(vitalResult.value);
        }
        if (diagnosisResult.status === "fulfilled") {
          setDiagnoses(diagnosisResult.value);
          setDiagnosesUnavailable(false);
        } else {
          setDiagnosesUnavailable(true);
        }
        if (drugResult.status === "fulfilled") {
          setMedications(drugResult.value);
          setMedicationsUnavailable(false);
        } else {
          setMedicationsUnavailable(true);
        }
        if (allergyResult.status === "fulfilled") {
          setAllergyState(allergyResult.value);
        } else {
          setAllergyState({ status: "unavailable" });
        }
        if (encounterResult.status === "fulfilled") {
          setEncounters(encounterResult.value);
          setEncountersUnavailable(false);
        } else {
          setEncountersUnavailable(true);
        }
        if (stayResult.status === "fulfilled") {
          setStay(stayResult.value);
        }
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [patientUuid]);

  const ensureBoard = useCallback(() => {
    if (board) {
      return;
    }
    fetchInpatientBoard()
      .then(setBoard)
      .catch(() => undefined);
  }, [board]);

  useEffect(() => {
    return loadClinical();
  }, [loadClinical]);

  useEffect(() => {
    const node = identityRef.current;
    if (!node) {
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        setStuck(!entry.isIntersecting);
      },
      { threshold: 0, rootMargin: "-8px 0px 0px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [patient]);

  const openVisit = visits.find((visit) => visit.open);
  const currentVisit = openVisit ?? visits[0];
  const inpatientVisit = visits.find(
    (visit) => visit.visitType.toUpperCase() === "IPD",
  );
  const chartIsInpatient = (currentVisit?.visitType || "").toUpperCase() === "IPD";
  useEffect(() => {
    const visitUuid = chartIsInpatient ? currentVisit?.uuid || "" : "";
    if (!visitUuid) {
      setWardAdministration(null);
      return;
    }
    let cancelled = false;
    fetchMar(patientUuid, visitUuid)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setWardAdministration(
          payload.orders.map((order) => ({
            orderUuid: order.orderUuid,
            slots: order.slots.map((slot) => ({
              status: slot.status,
              outcome: slot.administration?.outcome,
            })),
          })),
        );
      })
      .catch(() => {
        if (!cancelled) {
          setWardAdministration(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [patientUuid, chartIsInpatient, currentVisit?.uuid]);
  const chartMedications = medicationsForChart(medications, {
    visitUuid: currentVisit?.uuid || "",
    inpatient: chartIsInpatient,
    administration: wardAdministration,
  });
  const visitLabel = currentVisit?.startDate;
  const latestVitals = Object.values(vitalHistory)
    .map((rows) => rows[0])
    .filter((row): row is VitalReading => Boolean(row));
  const assignment = stay?.assignment ?? null;
  const areas = board?.areas ?? [];

  const closeDialog = () => {
    setDialog(null);
    setPickedBedUuid("");
    setDialogError("");
  };

  const runWardAction = async (
    work: () => Promise<InpatientStay>,
    successMessage?: string,
  ) => {
    setBusy(true);
    setDialogError("");
    try {
      const result = await work();
      const billingNote =
        result.billing?.message && result.billing.status !== "ok"
          ? ` ${result.billing.message}`
          : "";
      setNotice(`${successMessage || result.message || "Ward updated."}${billingNote}`.trim());
      setStay(result.assignment !== undefined ? result : stay);
      closeDialog();
      loadClinical();
      fetchInpatientBoard()
        .then(setBoard)
        .catch(() => undefined);
    } catch (reason) {
      const conflict = staffBedConflictMessage(reason);
      if (conflict) {
        setDialogError(conflict);
        setPickedBedUuid("");
        loadClinical();
        return;
      }
      setDialogError(
        wardRequestError(reason, "We couldn't complete this ward request. Please try again."),
      );
    } finally {
      setBusy(false);
    }
  };

  if (!patient && !loading) {
    return (
      <div className="nursing-patient">
        <p>This patient record could not be loaded.</p>
        <Button variant="secondary" onClick={() => returnToPreviousScreen("#/nursing/ward-board")}>
          Back to Ward Board
        </Button>
      </div>
    );
  }

  return (
    <div className="nursing-patient">
      <div className={`nursing-patient-sticky ${stuck && patient ? "is-on" : ""}`}>
        {patient ? (
          <div className="nursing-patient-sticky__inner">
            <strong>{patient.name}</strong>
            <span>{patient.mrn}</span>
            <span>
              {patient.age === "—" ? "Age not recorded" : `${patient.age} years`}
            </span>
            <span>
              {assignment
                ? locationLabel(assignment.areaName, assignment.bedNumber)
                : stay?.awaiting
                  ? "Waiting for a bed"
                  : "Not admitted"}
            </span>
            <span
              className={
                allergyState.status === "recorded"
                  ? "nursing-patient-sticky__allergy is-recorded"
                  : undefined
              }
            >
              {allergyStickyLabel(allergyState)}
            </span>
          </div>
        ) : null}
      </div>

      <div className="nursing-patient__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/nursing/ward-board")}>
          ← Ward Board
        </Button>
        <div className="abikan-account-nav">
          <PatientAccountLink patientUuid={patientUuid} />
          <a href={bahmniUrl(BAHMNI_ROUTES.patientDashboard(patientUuid))}>
            Open full chart
          </a>
        </div>
      </div>

      <div ref={identityRef}>
        {patient ? (
          <PatientIdentityHeader
            compact
            patient={patient}
            visitLabel={[
              visitLabel,
              assignment
                ? locationLabel(assignment.areaName, assignment.bedNumber)
                : stay?.awaiting
                  ? "Waiting for a bed"
                  : "Not admitted",
            ]
              .filter(Boolean)
              .join(" · ")}
          />
        ) : (
          <LoadingState variant="inline" label="Loading patient record…" />
        )}
      </div>

      {notice ? (
        <Alert
          tone={
            stay?.billing?.status === "tariff_missing" ||
            stay?.billing?.status === "needs_attention"
              ? "warning"
              : "success"
          }
          title="Ward updated"
        >
          <p>{notice}</p>
        </Alert>
      ) : null}

      <div className="abikan-sheet">
      <div className="abikan-sheet__main">
      <ClinicalSection
        id="alerts"
        title="Alerts"
        description="Allergies belong to the patient. Record or update them here so the ward and the doctor see the same list."
      >
        <ClinicalAlertBar
          allergy={allergyState}
          diagnoses={diagnoses}
          diagnosesUnavailable={diagnosesUnavailable}
          medications={chartMedications}
          medicationsUnavailable={medicationsUnavailable}
        />
        <AllergyPanel
          patientUuid={patientUuid}
          allergy={allergyState}
          onChanged={setAllergyState}
        />
      </ClinicalSection>

      <ClinicalSection
        id="condition"
        title="Current condition"
        description="Diagnoses and recent vitals from this patient's chart."
      >
        {loading ? (
          <p className="nursing-patient__muted">Loading clinical summary…</p>
        ) : diagnoses.length === 0 && latestVitals.length === 0 ? (
          <EmptyState
            title="No current condition recorded"
            description="Diagnoses and recent vitals will appear here when they exist on this record."
          />
        ) : (
          <div className="nursing-condition">
            <div>
              <p className="nursing-condition__label">Doctor diagnosis</p>
              <p>
                {diagnosesUnavailable
                  ? "Diagnoses unavailable"
                  : diagnoses.length > 0
                    ? diagnoses
                        .map((row) =>
                          row.order ? `${row.display} (${row.order.toLowerCase()})` : row.display,
                        )
                        .join("; ")
                    : "None recorded"}
              </p>
            </div>
            <div>
              <p className="nursing-condition__label">Latest vitals</p>
              <p>
                {latestVitals.length > 0
                  ? latestVitals
                      .slice(0, 4)
                      .map((row) => `${row.label} ${row.value}${row.unit ? ` ${row.unit}` : ""}`)
                      .join(" · ")
                  : "No vitals recorded"}
              </p>
            </div>
            <div>
              <p className="nursing-condition__label">Open visit</p>
              <p>
                {openVisit
                  ? `${openVisit.visitType} at ${openVisit.location} · ${openVisit.startDate}`
                  : "No open visit"}
              </p>
            </div>
          </div>
        )}
      </ClinicalSection>

      <div id="vitals">
        <InpatientVitalsPanel patientUuid={patientUuid} canRecord />
      </div>

      <MedicationAdministrationPanel
        patientUuid={patientUuid}
        patientName={patient?.name || "Patient"}
        canRecord
        visitUuid={inpatientVisit?.uuid}
      />

      <NursingTasksPanel patientUuid={patientUuid} stay={stay} />

      <NursingNotesPanel patientUuid={patientUuid} canCreate />

      <ClinicalSection
        id="doctor"
        title="Doctor instructions"
        description="Diagnoses, prescriptions and recent encounters from the shared record."
      >
        {diagnoses.length > 0 ? (
          <ul className="nursing-doctor-list">
            {diagnoses.map((row) => (
              <li key={row.uuid}>
                <strong>{row.display}</strong>
                <span>
                  {[row.order, row.certainty].filter(Boolean).join(" · ") || "Recorded diagnosis"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="nursing-patient__muted">
            {diagnosesUnavailable ? "Diagnoses unavailable." : "No doctor diagnosis recorded."}
          </p>
        )}
        {chartMedications.length > 0 ? (
          <p className="nursing-patient__muted">
            Current medications: {chartMedications.map((row) => row.display).join("; ")}
          </p>
        ) : null}
        {encountersUnavailable ? (
          <p className="nursing-patient__muted">Recent encounters unavailable.</p>
        ) : encounters.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Time</th>
                  <th>Encounter</th>
                </tr>
              </thead>
              <tbody>
                {encounters.slice(0, 6).map((row) => (
                  <tr key={row.uuid}>
                    <td>{row.date}</td>
                    <td>{row.time}</td>
                    <td>{row.type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No doctor instructions"
            description="Orders, disposition and written instructions will appear here from the same patient record."
          />
        )}
      </ClinicalSection>

      <ClinicalSection
        id="admission"
        title="Admission / transfer"
        description="Ward, room and bed. Assign, transfer, or open the chart. Nursing does not collect payment."
      >
        <dl className="nursing-facts">
          <div>
            <dt>Ward / room</dt>
            <dd>{assignment?.areaName || "No ward assignment"}</dd>
          </div>
          <div>
            <dt>Bed</dt>
            <dd>{assignment ? displayBedNumber(assignment.bedNumber) : "No bed assigned"}</dd>
          </div>
          <div>
            <dt>Admitted</dt>
            <dd>{assignment?.admitted ? formatDate(assignment.admitted) : "Not recorded"}</dd>
          </div>
          <div>
            <dt>Accommodation</dt>
            <dd>
              {stay?.billing?.paymentLabel ? (
                <Badge tone={paymentStateTone(stay.billing.paymentLabel)}>
                  {stay.billing.paymentLabel}
                </Badge>
              ) : stay?.billing?.status === "tariff_missing" ? (
                "Accommodation price is not configured for this bed/ward. Please contact Hospital Admin to configure the accommodation tariff."
              ) : (
                "Not recorded"
              )}
            </dd>
          </div>
          <div>
            <dt>Current visit</dt>
            <dd>
              {currentVisit
                ? `${currentVisit.visitType} · ${currentVisit.startDate}`
                : "No visit recorded"}
            </dd>
          </div>
        </dl>
        <div className="nursing-patient__actions">
          {assignment ? (
            <>
              <Button
                variant="primary"
                onClick={() => {
                  setDialog("transfer");
                  setPickedBedUuid("");
                  setDialogError("");
                  ensureBoard();
                }}
              >
                Transfer Patient
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setDialog("discharge");
                  setDialogError("");
                }}
              >
                Discharge Patient
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="primary"
                onClick={() => {
                  setDialog("assign");
                  setPickedBedUuid("");
                  setDialogError("");
                  ensureBoard();
                }}
              >
                Assign Bed
              </Button>
              {stay?.awaiting ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setDialog("cancel-admission");
                    setDialogError("");
                  }}
                >
                  Delete admission
                </Button>
              ) : null}
            </>
          )}
        </div>
        {stay?.awaiting && !assignment ? (
          <p className="nursing-patient__muted">The doctor has asked to admit this patient.</p>
        ) : null}
        {stay?.billing?.status === "tariff_missing" ? (
          <Alert
            tone="warning"
            title="Accommodation price is not configured for this bed/ward. Please contact Hospital Admin to configure the accommodation tariff."
          >
            <p>The bed assignment is complete. Hospital Admin must set the accommodation tariff before a bill can be created.</p>
          </Alert>
        ) : null}
        {stay?.billing?.status === "needs_attention" && stay.billing.message ? (
          <Alert tone="warning" title="Accommodation billing needs attention">
            {stay.billing.message}
          </Alert>
        ) : null}
        {stay?.billing?.status === "policy_required" && stay.billing.message ? (
          <Alert tone="info" title="Room change recorded">
            {stay.billing.message}
          </Alert>
        ) : null}
      </ClinicalSection>

      <ClinicalSection
        id="discharge"
        title="Discharge"
        description="Discharge ends the inpatient stay and releases the bed."
      >
        {assignment ? (
          <p className="nursing-patient__muted">
            This patient is on {locationLabel(assignment.areaName, assignment.bedNumber)}. Discharge
            releases that bed.
          </p>
        ) : (
          <EmptyState
            title="Not on a bed"
            description="Assign a bed before discharge is needed."
          />
        )}
      </ClinicalSection>
      </div>
      <SectionIndex items={FLOW} label="Nursing sections" />
      </div>

      {dialog === "assign" ? (
        <InpatientConfirmDialog
          title="Assign bed"
          confirmLabel="Assign Bed"
          busy={busy}
          error={dialogError}
          onClose={closeDialog}
          onConfirm={() => {
            if (!pickedBedUuid) {
              setDialogError("Choose an available bed.");
              return;
            }
            void runWardAction(() => {
              const picked = areas.flatMap((area) => area.beds).find((bed) => bed.bedUuid === pickedBedUuid);
              return assignInpatientBed(
                patientUuid,
                pickedBedUuid,
                newInpatientRequestId(),
                picked?.bedId,
              );
            });
          }}
        >
          <dl>
            <div>
              <dt>Patient</dt>
              <dd>{patient?.name}</dd>
            </div>
            <div>
              <dt>Hospital number</dt>
              <dd>{patient?.mrn}</dd>
            </div>
            <div>
              <dt>Admission status</dt>
              <dd>{stay?.awaiting ? "Admit requested" : "Not on a bed"}</dd>
            </div>
          </dl>
          {areas.length === 0 ? (
            <p className="nursing-patient__muted">Loading available beds…</p>
          ) : (
            <WardBedPicker areas={areas} value={pickedBedUuid} onChange={setPickedBedUuid} />
          )}
        </InpatientConfirmDialog>
      ) : null}

      {dialog === "transfer" && assignment ? (
        <InpatientConfirmDialog
          title="Transfer patient"
          confirmLabel="Transfer Patient"
          busy={busy}
          error={dialogError}
          onClose={closeDialog}
          onConfirm={() => {
            if (!pickedBedUuid) {
              setDialogError("Choose an available bed to transfer to.");
              return;
            }
            void runWardAction(() =>
              transferInpatientBed(
                patientUuid,
                pickedBedUuid,
                areas.flatMap((area) => area.beds).find((bed) => bed.bedUuid === pickedBedUuid)?.bedId,
              ),
            );
          }}
        >
          <dl>
            <div>
              <dt>Current location</dt>
              <dd>{bedLabel({ areaName: assignment.areaName, bedNumber: assignment.bedNumber })}</dd>
            </div>
          </dl>
          <p className="nursing-dialog__hint">Transfer to</p>
          {areas.length === 0 ? (
            <p className="nursing-patient__muted">Loading available beds…</p>
          ) : (
            <WardBedPicker
              areas={areas}
              value={pickedBedUuid}
              onChange={setPickedBedUuid}
              excludeBedUuid={assignment.bedUuid}
            />
          )}
        </InpatientConfirmDialog>
      ) : null}

      {dialog === "discharge" && assignment ? (
        <InpatientConfirmDialog
          title="Discharge patient"
          confirmLabel="Discharge Patient"
          busy={busy}
          error={dialogError}
          onClose={closeDialog}
          onConfirm={() => {
            void runWardAction(() => dischargeInpatient(patientUuid), "Patient discharged. Bed released.");
          }}
        >
          <p>
            Discharge this patient and release their bed?
            <br />
            {patient?.name} · {assignment.areaName} — {displayBedNumber(assignment.bedNumber)}
          </p>
        </InpatientConfirmDialog>
      ) : null}

      {dialog === "cancel-admission" && stay?.awaiting && !assignment ? (
        <InpatientConfirmDialog
          title="Delete admission"
          confirmLabel="Delete admission"
          busy={busy}
          error={dialogError}
          onClose={closeDialog}
          onConfirm={() => {
            void runWardAction(() => cancelWaitingAdmission(patientUuid));
          }}
        >
          <p>
            {patient?.name || "This patient"} is waiting for a bed. Deleting removes this admission
            request. The hospital record stays.
          </p>
        </InpatientConfirmDialog>
      ) : null}
    </div>
  );
}
