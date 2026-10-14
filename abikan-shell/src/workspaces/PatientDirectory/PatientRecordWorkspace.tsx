import { useEffect, useMemo, useState } from "react";
import {
  openAntenatalRegistration,
  openCreateVisit,
  openPatientAccount,
  openReceptionFamily,
  openRegistrationRegister,
  returnToPreviousScreen,
} from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { canOpenPatientAccount } from "../../config/workspaceMap";
import { hasHospitalAdminAccess } from "../../config/adminAccess";
import { newAdminRequestId } from "../../services/administration";
import { fetchAncSummary } from "../../services/antenatal";
import { fetchPatientFamily } from "../../services/hospitalFamily";
import { fetchPatientRecord, setPatientNhis, updatePatientLifeStatus } from "../../services/patientDirectory";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { WorkspaceContext } from "../../types";
import type { HospitalFamily } from "../../types/hospitalFamily";
import type { PatientRecord } from "../../types/patientDirectory";
import { AntenatalCardView } from "../Antenatal/AntenatalCardView";
import { shouldShowAncTab } from "../Antenatal/antenatalView";
import {
  displayPatientField,
  formatDeathDate,
  formatPatientDate,
  patientAddressLines,
  patientFullName,
  patientOtherIdentifiers,
  patientPhone,
  patientSexLabel,
  patientStatusLabel,
} from "./patientDirectoryView";
import "../Admin/AdminWorkspace.css";
import "../RegistrationDesk/RegistrationDeskWorkspace.css";
import "./PatientDirectoryWorkspace.css";

type PatientRecordTab = "overview" | "anc" | "billing";

interface PatientRecordWorkspaceProps {
  patientUuid: string;
  workplace: "reception" | "administration";
  context: WorkspaceContext;
}

function errorMessage(reason: unknown): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : "This patient could not be loaded.";
}

export function PatientRecordWorkspace({
  patientUuid,
  workplace,
  context,
}: PatientRecordWorkspaceProps) {
  const [record, setRecord] = useState<PatientRecord | null>(null);
  const [family, setFamily] = useState<HospitalFamily | null>(null);
  const [hasAnc, setHasAnc] = useState(false);
  const [ancEnrolled, setAncEnrolled] = useState(false);
  const [activeTab, setActiveTab] = useState<PatientRecordTab>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingStatus, setEditingStatus] = useState(false);
  const [aliveDraft, setAliveDraft] = useState(true);
  const [deathDateDraft, setDeathDateDraft] = useState("");
  const [statusBusy, setStatusBusy] = useState(false);
  const [statusError, setStatusError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [nhisBusy, setNhisBusy] = useState(false);
  const [nhisError, setNhisError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setEditingStatus(false);
    setStatusError("");
    setStatusMessage("");
    setActiveTab("overview");
    setHasAnc(false);
    setAncEnrolled(false);
    Promise.allSettled([
      fetchPatientRecord(patientUuid),
      fetchPatientFamily(patientUuid),
      fetchAncSummary(patientUuid),
    ])
      .then(([recordResult, familyResult, ancResult]) => {
        if (cancelled) {
          return;
        }
        if (recordResult.status === "fulfilled") {
          setRecord(recordResult.value);
        } else {
          setRecord(null);
          setError(errorMessage(recordResult.reason));
        }
        if (familyResult.status === "fulfilled") {
          setFamily(familyResult.value.family);
        }
        if (ancResult.status === "fulfilled") {
          setHasAnc(Boolean(ancResult.value.hasAnc));
          setAncEnrolled(Boolean(ancResult.value.enrolled));
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setRecord(null);
          setError(errorMessage(reason));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [patientUuid]);

  const name = record ? patientFullName(record) : "";
  const phone = record ? patientPhone(record) : "";
  const addressLines = useMemo(() => (record ? patientAddressLines(record) : []), [record]);
  const otherIds = useMemo(() => (record ? patientOtherIdentifiers(record) : []), [record]);
  const birthdate = record ? formatPatientDate(record.birthdate) : "";
  const registeredOn = record ? formatPatientDate(record.registeredOn || "") : "";
  const showAccount = canOpenPatientAccount(context);
  const showAnc = shouldShowAncTab(hasAnc);
  const canEditLifeStatus =
    workplace === "administration" &&
    hasHospitalAdminAccess(context.roles, context.privileges);
  const patientAlive = record?.alive !== false;
  const deathDateDisplay = record && !patientAlive ? formatDeathDate(record.deathDate || "") : "";
  const recordTab = activeTab === "anc" && !showAnc ? "overview" : activeTab;

  const beginStatusEdit = () => {
    if (!record) {
      return;
    }
    setAliveDraft(record.alive !== false);
    setDeathDateDraft(record.deathDate || "");
    setStatusError("");
    setStatusMessage("");
    setEditingStatus(true);
  };

  const saveLifeStatus = async () => {
    if (!record || statusBusy) {
      return;
    }
    if (!aliveDraft && !deathDateDraft.trim()) {
      setStatusError("Enter the date of death.");
      return;
    }
    setStatusBusy(true);
    setStatusError("");
    setStatusMessage("");
    try {
      const updated = await updatePatientLifeStatus(record.uuid, {
        alive: aliveDraft,
        deathDate: aliveDraft ? undefined : deathDateDraft.trim(),
        requestId: newAdminRequestId(),
      });
      setRecord(updated);
      setEditingStatus(false);
      setStatusMessage(
        updated.alive !== false
          ? "Patient status set to Alive."
          : "Patient status set to Dead.",
      );
    } catch (reason) {
      setStatusError(errorMessage(reason));
    } finally {
      setStatusBusy(false);
    }
  };

  return (
    <div className="admin-workspace patient-directory">
      <div className="admin-workspace__nav">
        <Button
          variant="ghost"
          onClick={() =>
            returnToPreviousScreen(
              workplace === "reception" ? "#/reception/patients" : "#/admin/patients",
            )
          }
        >
          ← Patients
        </Button>
      </div>
      <PageHeader
        title="Patient"
        description="Registration details for this patient. Bills and payments stay on the account."
      />

      {error ? (
        <Alert tone="danger" title="This patient could not be loaded">
          {error}
        </Alert>
      ) : null}
      {loading ? <LoadingState variant="board" label="Loading patient…" /> : null}

      {!loading && record ? (
        <>
          <PatientIdentityHeader
            patient={{
              uuid: record.uuid,
              name: name || "Unnamed patient",
              mrn: record.identifier || "No hospital number",
              age: record.age == null ? "—" : String(record.age),
              sex: patientSexLabel(record.gender) || "—",
              birthdate: birthdate,
            }}
            extraFacts={[
              {
                label: "Date of birth",
                value: birthdate
                  ? `${birthdate}${record.birthdateEstimated ? " (estimated)" : ""}`
                  : "—",
              },
              {
                label: "Patient status",
                value: patientAlive
                  ? "Alive"
                  : deathDateDisplay
                    ? `Dead · ${deathDateDisplay}`
                    : "Dead",
              },
            ]}
          />

          <nav className="patient-directory__tabs" aria-label="Patient record sections">
            <button
              type="button"
              className={recordTab === "overview" ? "is-active" : ""}
              onClick={() => setActiveTab("overview")}
            >
              Overview
            </button>
            {showAnc ? (
              <button
                type="button"
                className={recordTab === "anc" ? "is-active" : ""}
                onClick={() => setActiveTab("anc")}
              >
                ANC
              </button>
            ) : null}
            {showAccount ? (
              <button
                type="button"
                className={recordTab === "billing" ? "is-active" : ""}
                onClick={() => setActiveTab("billing")}
              >
                Billing
              </button>
            ) : null}
          </nav>

          {recordTab === "anc" && showAnc ? (
            <AntenatalCardView
              patientUuid={record.uuid}
              patientName={name || undefined}
              patientMrn={record.identifier || undefined}
              patientDob={birthdate || undefined}
              canEdit={workplace === "reception" || workplace === "administration"}
            />
          ) : null}

          {recordTab === "billing" && showAccount ? (
            <Card>
              <SectionHeader
                title="Bills and payments"
                description="Accountant collects payment. Open the account only when you need the bill."
              />
              <Button variant="secondary" onClick={() => openPatientAccount(record.uuid)}>
                Open account
              </Button>
            </Card>
          ) : null}

          {recordTab === "overview" ? (
            <>
          <Card>
            <SectionHeader
              title="NHIS"
              description="Tick this when the patient is covered by NHIS. They will not be charged a consultation fee."
            />
            <label className="patient-directory__nhis">
              <input
                type="checkbox"
                checked={Boolean(record.nhis)}
                disabled={nhisBusy}
                onChange={(event) => {
                  const next = event.target.checked;
                  setNhisBusy(true);
                  setNhisError("");
                  setPatientNhis(record.uuid, next)
                    .then(() => {
                      setRecord((current) => (current ? { ...current, nhis: next } : current));
                    })
                    .catch((reason) => {
                      setNhisError(
                        reason instanceof Error ? reason.message : "NHIS could not be saved. Try again.",
                      );
                    })
                    .finally(() => setNhisBusy(false));
                }}
              />
              <span>NHIS patient</span>
            </label>
            {nhisError ? (
              <Alert tone="danger" title="NHIS could not be saved">
                {nhisError}
              </Alert>
            ) : null}
          </Card>
          <Card>
            <SectionHeader
              title="Cards / services"
              description="The patient keeps one hospital identity and MRN. ANC and other services attach to that record."
            />
            <ul className="patient-directory__services">
              <li>
                <strong>Hospital registration</strong>
                <span>General / OPD and other visits use this patient record.</span>
                {workplace === "reception" ? (
                  <Button variant="secondary" onClick={() => openCreateVisit(record.uuid)}>
                    Create visit
                  </Button>
                ) : null}
              </li>
              <li>
                <strong>ANC</strong>
                <span>
                  {ancEnrolled
                    ? "Antenatal card is on file for this patient."
                    : hasAnc
                      ? "An antenatal card is on file. After one year it is disabled until it is enabled again."
                      : "No antenatal card yet. Open Antenatal Care to create one."}
                </span>
                <div className="reg-patient__actions">
                  {showAnc ? (
                    <Button variant="secondary" onClick={() => setActiveTab("anc")}>
                      Open ANC card
                    </Button>
                  ) : null}
                  {workplace === "reception" && !ancEnrolled ? (
                    <Button variant="secondary" onClick={() => openAntenatalRegistration(record.uuid)}>
                      Open Antenatal Care
                    </Button>
                  ) : null}
                  {workplace === "reception" && ancEnrolled ? (
                    <Button variant="secondary" onClick={() => openAntenatalRegistration(record.uuid)}>
                      New ANC visit
                    </Button>
                  ) : null}
                </div>
              </li>
              <li>
                <strong>Pharmacy</strong>
                <span>Available when medicines are ordered for this patient.</span>
              </li>
              <li>
                <strong>Laboratory</strong>
                <span>Available when lab tests are ordered for this patient.</span>
              </li>
            </ul>
          </Card>

          <Card>
            <SectionHeader title="Personal details" />
            <dl className="reg-patient__facts">
              <div>
                <dt>Full name</dt>
                <dd>{displayPatientField(name)}</dd>
              </div>
              <div>
                <dt>Hospital number</dt>
                <dd>{displayPatientField(record.identifier)}</dd>
              </div>
              <div>
                <dt>Sex</dt>
                <dd>{displayPatientField(patientSexLabel(record.gender))}</dd>
              </div>
              <div>
                <dt>Age</dt>
                <dd>{record.age == null ? "—" : `${record.age} years`}</dd>
              </div>
              <div>
                <dt>Date of birth</dt>
                <dd>
                  {birthdate
                    ? `${birthdate}${record.birthdateEstimated ? " (estimated)" : ""}`
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>Phone</dt>
                <dd>{displayPatientField(phone)}</dd>
              </div>
              {registeredOn ? (
                <div>
                  <dt>Registered</dt>
                  <dd>{registeredOn}</dd>
                </div>
              ) : null}
              {otherIds.map((item) => (
                <div key={`${item.label}:${item.value}`}>
                  <dt>{item.label}</dt>
                  <dd>{item.value}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card>
            <SectionHeader
              title="Patient status"
              description={
                canEditLifeStatus
                  ? "Only Hospital Administration can change Alive or Dead. Clinical records are kept."
                  : "Alive or Dead is shown for reference. Only Hospital Administration can change it."
              }
            />
            <div className="patient-directory__life-status">
              <dl className="reg-patient__facts">
                <div>
                  <dt>Patient status</dt>
                  <dd>{patientStatusLabel(patientAlive)}</dd>
                </div>
                {!patientAlive ? (
                  <div>
                    <dt>Date of death</dt>
                    <dd>{deathDateDisplay || "—"}</dd>
                  </div>
                ) : null}
              </dl>

              {statusMessage ? (
                <Alert tone="success" title="Status updated">
                  {statusMessage}
                </Alert>
              ) : null}
              {statusError ? (
                <Alert tone="danger" title="Status could not be updated">
                  {statusError}
                </Alert>
              ) : null}

              {canEditLifeStatus && !editingStatus ? (
                <div className="patient-directory__life-actions">
                  <Button variant="secondary" onClick={beginStatusEdit}>
                    Change status
                  </Button>
                </div>
              ) : null}

              {canEditLifeStatus && editingStatus ? (
                <form
                  className="patient-directory__life-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void saveLifeStatus();
                  }}
                >
                  <fieldset>
                    <legend>Alive</legend>
                    <div className="patient-directory__life-options">
                      <label>
                        <input
                          type="radio"
                          name="alive"
                          checked={aliveDraft}
                          onChange={() => setAliveDraft(true)}
                        />
                        Yes
                      </label>
                      <label>
                        <input
                          type="radio"
                          name="alive"
                          checked={!aliveDraft}
                          onChange={() => setAliveDraft(false)}
                        />
                        No
                      </label>
                    </div>
                  </fieldset>
                  {!aliveDraft ? (
                    <label>
                      <span>Date of death</span>
                      <input
                        type="date"
                        required
                        value={deathDateDraft}
                        onChange={(event) => setDeathDateDraft(event.target.value)}
                      />
                    </label>
                  ) : null}
                  <div className="patient-directory__life-actions">
                    <Button type="submit" disabled={statusBusy}>
                      {statusBusy ? "Saving…" : "Save status"}
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={statusBusy}
                      onClick={() => {
                        setEditingStatus(false);
                        setStatusError("");
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </form>
              ) : null}
            </div>
          </Card>

          {family ? (
            <Card>
              <SectionHeader
                title="Family Card"
                description="This patient has their own hospital record. The Family Card only shows which family they belong to."
              />
              <dl className="reg-patient__facts">
                <div>
                  <dt>Family</dt>
                  <dd>{family.familyName}</dd>
                </div>
                <div>
                  <dt>Family Card</dt>
                  <dd>{family.cardNumber}</dd>
                </div>
                <div>
                  <dt>Relationship</dt>
                  <dd>{family.relationship || "Family member"}</dd>
                </div>
                <div>
                  <dt>Patients on this card</dt>
                  <dd>
                    {family.memberCount === 1 ? "1 patient" : `${family.memberCount} patients`}
                  </dd>
                </div>
              </dl>
              {workplace === "reception" ? (
                <div className="reg-patient__actions">
                  <Button variant="secondary" onClick={() => openReceptionFamily(family.familyId)}>
                    View family
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => openRegistrationRegister(undefined, family.familyId)}
                  >
                    Register another family member
                  </Button>
                </div>
              ) : null}
            </Card>
          ) : null}

          <Card>
            <SectionHeader title="Address" />
            {addressLines.length === 0 ? (
              <p className="patient-directory__muted">No address is on this record.</p>
            ) : (
              <dl className="reg-patient__facts">
                {addressLines.map((item) => (
                  <div key={item.label}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </Card>

          {workplace === "reception" ? (
            <div className="reg-patient__actions">
              <Button variant="secondary" onClick={() => openRegistrationRegister(record.uuid)}>
                Edit details
              </Button>
              <Button variant="secondary" onClick={() => openCreateVisit(record.uuid)}>
                Create visit
              </Button>
            </div>
          ) : null}
            </>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
