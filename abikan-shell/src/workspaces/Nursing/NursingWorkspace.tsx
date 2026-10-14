import { useEffect, useMemo, useState } from "react";
import {
  openNursingPatient,
  openNursingSection,
  readHashNavItemId,
} from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { KpiCard } from "../../components/KpiCard";
import { PageHeader } from "../../components/PageHeader";
import { QuickAction } from "../../components/QuickAction";
import { SectionHeader } from "../../components/SectionHeader";
import {
  assignInpatientBed,
  cancelWaitingAdmission,
  dischargeInpatient,
  fetchInpatientBoard,
  newInpatientRequestId,
  transferInpatientBed,
} from "../../services/inpatient";
import { fetchNursingTodaysPatients } from "../../services/openmrs/doctorQueue";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { InpatientArea, InpatientAwaiting, InpatientBed, InpatientBoard } from "../../types/inpatient";
import type { DoctorQueueRow, WorkspaceContext } from "../../types";
import { receptionVisitTypeLabel } from "../../config/receptionVisitTypes";
import { formatDate, greetingForNow } from "../../utils/datetime";
import {
  AwaitingPatientSelect,
  InpatientConfirmDialog,
  OccupiedPatientSelect,
  WardBedPicker,
} from "./InpatientDialogs";
import {
  RevenueGeneratedCard,
  RevenuePeriodFilter,
  useDepartmentRevenue,
} from "../shared/DepartmentRevenue";
import {
  bedStatusLabel,
  displayBedNumber,
  isOccupied,
  locationLabel,
  mergeNursingDayPatients,
  nursingViewFromNav,
  staffBedConflictMessage,
  wardRequestError,
  type NursingView,
} from "./nursingBoard";
import { NursingBedPricesView } from "./NursingBedPricesView";
import { NursingTreatmentQueue } from "./NursingTreatmentQueue";
import "./NursingWorkspace.css";

interface NursingWorkspaceProps {
  context: WorkspaceContext;
}

type WardDialog = "assign" | "transfer" | "discharge" | "cancel-admission" | null;

function focusPatientSearch() {
  document.getElementById("global-patient-search")?.focus();
}

export function NursingWorkspace({ context }: NursingWorkspaceProps) {
  const [view, setView] = useState<NursingView>(() => nursingViewFromNav(readHashNavItemId()));
  const [board, setBoard] = useState<InpatientBoard | null>(null);
  const [todaysVisits, setTodaysVisits] = useState<DoctorQueueRow[]>([]);
  const [visitsError, setVisitsError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<WardDialog>(null);
  const [dialogError, setDialogError] = useState("");
  const [assignBed, setAssignBed] = useState<InpatientBed | null>(null);
  const [pickedBedUuid, setPickedBedUuid] = useState("");
  const [pickedPatientUuid, setPickedPatientUuid] = useState("");

  const loadBoard = (silent = false) => {
    if (!silent) {
      setLoading(true);
    }
    setError("");
    setVisitsError("");
    return Promise.allSettled([fetchInpatientBoard(), fetchNursingTodaysPatients()])
      .then(([boardResult, visitsResult]) => {
        if (boardResult.status === "fulfilled") {
          setBoard(boardResult.value);
        } else {
          setBoard(null);
          setError(
            boardResult.reason instanceof PatientAccountRequestError
              ? boardResult.reason.message
              : "The ward board could not be loaded. You can still search for a patient.",
          );
        }
        if (visitsResult.status === "fulfilled") {
          setTodaysVisits(visitsResult.value);
        } else {
          setTodaysVisits([]);
          setVisitsError(
            visitsResult.reason instanceof PatientAccountRequestError
              ? visitsResult.reason.message
              : "Today's visits could not be loaded. You can still search for a patient.",
          );
        }
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    void loadBoard();
  }, []);

  useEffect(() => {
    const sync = () => setView(nursingViewFromNav(readHashNavItemId()));
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  const areas = board?.areas ?? [];
  const awaiting = board?.awaiting ?? [];
  const occupiedPatients = useMemo(
    () =>
      areas.flatMap((area) =>
        area.beds.filter(isOccupied).map((bed) => ({ areaName: area.name, bed })),
      ),
    [areas],
  );

  const closeDialogs = () => {
    setDialog(null);
    setAssignBed(null);
    setPickedBedUuid("");
    setPickedPatientUuid("");
    setDialogError("");
  };

  const openAssign = (options?: { bed?: InpatientBed; patient?: InpatientAwaiting }) => {
    setDialog("assign");
    setAssignBed(options?.bed ?? null);
    setPickedBedUuid(options?.bed?.bedUuid ?? "");
    setPickedPatientUuid(options?.patient?.patientUuid ?? "");
    setDialogError("");
  };

  const openTransfer = (patientUuid?: string) => {
    setDialog("transfer");
    setAssignBed(null);
    setPickedBedUuid("");
    setPickedPatientUuid(patientUuid ?? "");
    setDialogError("");
  };

  const openDischarge = (patientUuid?: string) => {
    setDialog("discharge");
    setAssignBed(null);
    setPickedBedUuid("");
    setPickedPatientUuid(patientUuid ?? "");
    setDialogError("");
  };

  const openCancelAdmission = (patientUuid: string) => {
    setDialog("cancel-admission");
    setAssignBed(null);
    setPickedBedUuid("");
    setPickedPatientUuid(patientUuid);
    setDialogError("");
  };

  const handleBedTaken = async (reason: unknown) => {
    const conflict = staffBedConflictMessage(reason);
    if (!conflict) {
      return false;
    }
    setDialogError(conflict);
    setPickedBedUuid("");
    await loadBoard(true);
    return true;
  };

  const handleAssign = async (patientUuid: string, bedUuid: string) => {
    setBusy(true);
    setDialogError("");
    try {
      const picked = areas.flatMap((area) => area.beds).find((bed) => bed.bedUuid === bedUuid);
      const stay = await assignInpatientBed(
        patientUuid,
        bedUuid,
        newInpatientRequestId(),
        picked?.bedId,
      );
      const billingNote =
        stay.billing?.message && stay.billing.status !== "ok" ? ` ${stay.billing.message}` : "";
      setNotice(`${stay.message || "Bed assigned."}${billingNote}`.trim());
      closeDialogs();
      await loadBoard(true);
    } catch (reason) {
      if (!(await handleBedTaken(reason))) {
        setDialogError(wardRequestError(reason, "We couldn't complete the bed assignment. Please try again."));
      }
    } finally {
      setBusy(false);
    }
  };

  const handleTransfer = async (patientUuid: string, bedUuid: string) => {
    setBusy(true);
    setDialogError("");
    try {
      const picked = areas.flatMap((area) => area.beds).find((bed) => bed.bedUuid === bedUuid);
      const stay = await transferInpatientBed(patientUuid, bedUuid, picked?.bedId);
      const billingNote =
        stay.billing?.message && stay.billing.status !== "ok" ? ` ${stay.billing.message}` : "";
      setNotice(`${stay.message || "Patient transferred."}${billingNote}`.trim());
      closeDialogs();
      await loadBoard(true);
    } catch (reason) {
      if (!(await handleBedTaken(reason))) {
        setDialogError(wardRequestError(reason, "We couldn't complete the transfer. Please try again."));
      }
    } finally {
      setBusy(false);
    }
  };

  const handleDischarge = async (patientUuid: string) => {
    setBusy(true);
    setDialogError("");
    try {
      await dischargeInpatient(patientUuid);
      setNotice("Patient discharged. Bed released.");
      closeDialogs();
      await loadBoard(true);
    } catch (reason) {
      setDialogError(wardRequestError(reason, "We couldn't complete the discharge. Please try again."));
    } finally {
      setBusy(false);
    }
  };

  const handleCancelAdmission = async (patientUuid: string) => {
    setBusy(true);
    setDialogError("");
    try {
      const stay = await cancelWaitingAdmission(patientUuid);
      setNotice(stay.message || "Admission canceled. This patient is no longer waiting for a bed.");
      closeDialogs();
      await loadBoard(true);
    } catch (reason) {
      setDialogError(
        wardRequestError(reason, "We couldn't cancel this admission. Refresh the list and try again."),
      );
    } finally {
      setBusy(false);
    }
  };

  const assignPatient = awaiting.find((row) => row.patientUuid === pickedPatientUuid) ?? null;
  const transferFrom = occupiedPatients.find((row) => row.bed.patientUuid === pickedPatientUuid);
  const dischargeFrom = transferFrom;
  const pageTitle =
    view === "ward-board"
      ? "Ward Board"
      : view === "patients"
        ? "Patients"
      : view === "visits"
        ? "Today's Visits"
      : view === "treatments"
        ? "Treatment Queue"
        : view === "admissions"
          ? "Admissions"
          : view === "transfers"
            ? "Transfers"
            : view === "discharges"
              ? "Discharges"
              : "Nursing";
  const pageDescription =
    view === "ward-board"
      ? "Who is where: ward, room, bed, and patient."
      : view === "patients"
        ? "Patients with a visit today, plus anyone admitted or waiting for a bed."
        : view === "visits"
          ? "Everyone who has a visit today. Open a record to take vitals."
        : view === "treatments"
          ? "Hospital treatments that nurses can give without a bed or doctor consultation."
        : view === "admissions"
          ? "Patients the doctor has admitted who still need a bed."
          : view === "transfers"
            ? "Transfers are managed from the Ward Board."
            : view === "discharges"
              ? "Discharges are managed from the Ward Board."
              : `${greetingForNow()}, ${context.displayName}. Who is on the ward today?`;

  if (view === "pricing") {
    return <NursingBedPricesView />;
  }

  return (
    <div className="nursing-desk">
      <PageHeader title={pageTitle} description={pageDescription} />

      {notice ? (
        <Alert tone="success" title="Ward updated">
          <p>{notice}</p>
        </Alert>
      ) : null}
      {error ? (
        <Alert tone="warning" title="Ward board">
          <p>{error}</p>
        </Alert>
      ) : null}
      {visitsError && (view === "patients" || view === "visits") ? (
        <Alert tone="warning" title="Today's visits">
          <p>{visitsError}</p>
        </Alert>
      ) : null}

      {view === "dashboard" ? (
        <DashboardView
          loading={loading}
          board={board}
          areas={areas}
          awaitingCount={awaiting.length}
          onOpenAssign={() => openAssign()}
          onOpenTransfer={() => openTransfer()}
          onOpenDischarge={() => openDischarge()}
        />
      ) : null}

      {view === "ward-board" ? (
        <WardBoardView
          loading={loading}
          areas={areas}
          awaiting={awaiting}
          onAssignBed={(bed) => openAssign({ bed })}
          onAssignPatient={(patient) => openAssign({ patient })}
          onTransfer={(patientUuid) => openTransfer(patientUuid)}
          onDischarge={(patientUuid) => openDischarge(patientUuid)}
        />
      ) : null}

      {view === "patients" ? (
        <PatientsView
          loading={loading}
          occupiedPatients={occupiedPatients}
          awaiting={awaiting}
          visits={todaysVisits}
          onSearch={focusPatientSearch}
        />
      ) : null}

      {view === "visits" ? (
        <TodaysVisitsView
          loading={loading}
          visits={todaysVisits}
          onSearch={focusPatientSearch}
        />
      ) : null}

      {view === "treatments" ? <NursingTreatmentQueue /> : null}

      {view === "admissions" ? (
        <AdmissionsView
          loading={loading}
          awaiting={awaiting}
          onAssign={(patient) => openAssign({ patient })}
          onDelete={(patient) => openCancelAdmission(patient.patientUuid)}
        />
      ) : null}

      {view === "transfers" ? (
        <TransfersView
          loading={loading}
          occupiedPatients={occupiedPatients}
          onTransfer={(patientUuid) => openTransfer(patientUuid)}
        />
      ) : null}

      {view === "discharges" ? (
        <DischargesView
          loading={loading}
          occupiedPatients={occupiedPatients}
          onDischarge={(patientUuid) => openDischarge(patientUuid)}
        />
      ) : null}

      {dialog === "assign" ? (
        <InpatientConfirmDialog
          title="Assign bed"
          confirmLabel="Assign Bed"
          busy={busy}
          error={dialogError}
          onClose={closeDialogs}
          onConfirm={() => {
            if (!pickedPatientUuid) {
              setDialogError("Choose a patient waiting for a bed, or search from the patient chart.");
              return;
            }
            if (!pickedBedUuid) {
              setDialogError("Choose an available bed.");
              return;
            }
            void handleAssign(pickedPatientUuid, pickedBedUuid);
          }}
        >
          {assignPatient ? (
            <dl>
              <div>
                <dt>Patient</dt>
                <dd>{assignPatient.patientName}</dd>
              </div>
              <div>
                <dt>Hospital number</dt>
                <dd>{assignPatient.mrn}</dd>
              </div>
              <div>
                <dt>Admission status</dt>
                <dd>Admit requested</dd>
              </div>
            </dl>
          ) : (
            <AwaitingPatientSelect
              patients={awaiting}
              value={pickedPatientUuid}
              onChange={setPickedPatientUuid}
            />
          )}
          <WardBedPicker
            areas={areas}
            value={pickedBedUuid}
            onChange={setPickedBedUuid}
            lockedBedUuid={assignBed?.bedUuid}
            emptyLabel="There are currently no available beds."
          />
        </InpatientConfirmDialog>
      ) : null}

      {dialog === "transfer" ? (
        <InpatientConfirmDialog
          title="Transfer patient"
          confirmLabel="Transfer Patient"
          busy={busy}
          error={dialogError}
          onClose={closeDialogs}
          onConfirm={() => {
            if (!pickedPatientUuid) {
              setDialogError("Choose the patient to transfer.");
              return;
            }
            if (!pickedBedUuid) {
              setDialogError("Choose an available bed to transfer to.");
              return;
            }
            void handleTransfer(pickedPatientUuid, pickedBedUuid);
          }}
        >
          {transferFrom ? (
            <dl>
              <div>
                <dt>Patient</dt>
                <dd>
                  {transferFrom.bed.patientName} · {transferFrom.bed.mrn}
                </dd>
              </div>
              <div>
                <dt>Current location</dt>
                <dd>{locationLabel(transferFrom.areaName, transferFrom.bed.bedNumber)}</dd>
              </div>
            </dl>
          ) : (
            <OccupiedPatientSelect
              patients={occupiedPatients}
              value={pickedPatientUuid}
              onChange={setPickedPatientUuid}
            />
          )}
          <p className="nursing-dialog__hint">Transfer to</p>
          <WardBedPicker
            areas={areas}
            value={pickedBedUuid}
            onChange={setPickedBedUuid}
            excludeBedUuid={transferFrom?.bed.bedUuid}
            emptyLabel="There are currently no available beds to transfer to."
          />
        </InpatientConfirmDialog>
      ) : null}

      {dialog === "discharge" ? (
        <InpatientConfirmDialog
          title="Discharge patient"
          confirmLabel="Discharge Patient"
          busy={busy}
          error={dialogError}
          onClose={closeDialogs}
          onConfirm={() => {
            if (!pickedPatientUuid) {
              setDialogError("Choose the patient to discharge.");
              return;
            }
            void handleDischarge(pickedPatientUuid);
          }}
        >
          {dischargeFrom ? (
            <p>
              Discharge this patient and release their bed?
              <br />
              {dischargeFrom.bed.patientName} · {dischargeFrom.bed.mrn} ·{" "}
              {locationLabel(dischargeFrom.areaName, dischargeFrom.bed.bedNumber)}
            </p>
          ) : (
            <>
              <OccupiedPatientSelect
                patients={occupiedPatients}
                value={pickedPatientUuid}
                onChange={setPickedPatientUuid}
              />
              {pickedPatientUuid ? <p>Discharge this patient and release their bed?</p> : null}
            </>
          )}
        </InpatientConfirmDialog>
      ) : null}

      {dialog === "cancel-admission" && assignPatient ? (
        <InpatientConfirmDialog
          title="Delete admission"
          confirmLabel="Delete admission"
          busy={busy}
          error={dialogError}
          onClose={closeDialogs}
          onConfirm={() => {
            void handleCancelAdmission(assignPatient.patientUuid);
          }}
        >
          <p>
            {assignPatient.patientName} is waiting for a bed. Deleting removes this admission
            request. The hospital record stays.
          </p>
        </InpatientConfirmDialog>
      ) : null}
    </div>
  );
}

function DashboardView({
  loading,
  board,
  areas,
  awaitingCount,
  onOpenAssign,
  onOpenTransfer,
  onOpenDischarge,
}: {
  loading: boolean;
  board: InpatientBoard | null;
  areas: InpatientArea[];
  awaitingCount: number;
  onOpenAssign: () => void;
  onOpenTransfer: () => void;
  onOpenDischarge: () => void;
}) {
  const revenue = useDepartmentRevenue();
  return (
    <>
      {loading ? <LoadingState variant="board" label="Loading today's ward…" /> : null}
      {!loading && board ? (
        <>
        <RevenuePeriodFilter revenue={revenue} />
        <section className="nursing-desk__kpis" aria-label="Today's ward">
          <KpiCard
            label="Occupied Beds"
            value={board.occupiedBeds}
            hint={board.occupiedBeds === 0 ? "No patients on a bed" : "Patients on a bed"}
            tone="visits"
            icon="bed"
            actionLabel="Ward Board"
            onAction={() => openNursingSection("ward-board")}
          />
          <KpiCard
            label="Available Beds"
            value={board.availableBeds}
            hint={`${board.totalBeds} beds in total`}
            tone="appointments"
            icon="bed"
            actionLabel="Assign bed"
            onAction={onOpenAssign}
          />
          <KpiCard
            label="New Admissions"
            value={awaitingCount}
            hint={awaitingCount === 0 ? "No one waiting for a bed" : "Waiting for a bed"}
            tone="registration"
            icon="clipboardPlus"
            actionLabel="Admissions"
            onAction={() => openNursingSection("admissions")}
          />
          <RevenueGeneratedCard revenue={revenue} />
        </section>
        </>
      ) : null}

      <Card>
        <SectionHeader title="Quick actions" />
        <div className="nursing-desk__actions">
          <QuickAction
            label="Patients"
            icon="search"
            tone="visits"
            onClick={() => openNursingSection("patients")}
          />
          <QuickAction
            label="Today's Visits"
            icon="clipboardList"
            tone="appointments"
            onClick={() => openNursingSection("visits")}
          />
          <QuickAction
            label="Ward Board"
            icon="bed"
            tone="visits"
            onClick={() => openNursingSection("ward-board")}
          />
          <QuickAction label="Assign Bed" icon="clipboardPlus" tone="registration" onClick={onOpenAssign} />
          <QuickAction label="Transfer Patient" icon="activity" tone="appointments" onClick={onOpenTransfer} />
          <QuickAction label="Discharge Patient" icon="calendar" tone="collection" onClick={onOpenDischarge} />
        </div>
      </Card>

      <Card id="nursing-dashboard">
        <SectionHeader
          title="Ward overview"
          description="Occupied and available counts come from the current bed board."
        />
        {loading ? (
          <LoadingState variant="board" label="Loading wards…" />
        ) : areas.length === 0 ? (
          <EmptyState title="No wards available" description="No hospital wards are available yet." />
        ) : (
          <ul className="nursing-overview">
            {areas.map((area) => (
              <li key={area.uuid}>
                <button
                  type="button"
                  className="nursing-overview__card"
                  onClick={() => openNursingSection("ward-board")}
                >
                  <strong>{area.name}</strong>
                  <span>
                    {area.totalBeds} {area.totalBeds === 1 ? "bed" : "beds"}
                  </span>
                  <span>
                    {area.occupiedBeds} occupied · {area.availableBeds} available
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function WardBoardView({
  loading,
  areas,
  awaiting,
  onAssignBed,
  onAssignPatient,
  onTransfer,
  onDischarge,
}: {
  loading: boolean;
  areas: InpatientArea[];
  awaiting: InpatientAwaiting[];
  onAssignBed: (bed: InpatientBed) => void;
  onAssignPatient: (patient: InpatientAwaiting) => void;
  onTransfer: (patientUuid: string) => void;
  onDischarge: (patientUuid: string) => void;
}) {
  return (
    <div id="ward-board">
      {awaiting.length > 0 ? (
        <Alert tone="info" title="Waiting for a bed">
          <p>
            {awaiting.length === 1
              ? `${awaiting[0].patientName} needs a bed.`
              : `${awaiting.length} patients need a bed.`}{" "}
            <button type="button" className="nursing-desk__patient" onClick={() => onAssignPatient(awaiting[0])}>
              Assign Bed
            </button>
          </p>
        </Alert>
      ) : null}
      {loading ? (
        <LoadingState variant="board" label="Loading the ward board…" />
      ) : areas.length === 0 ? (
        <EmptyState title="No wards available" description="No hospital wards are available yet." />
      ) : (
        <div className="nursing-board">
          {areas.map((area) => (
            <section key={area.uuid} className="nursing-board__area" aria-label={area.name}>
              <header>
                <h2>{area.name}</h2>
                <p>
                  {area.occupiedBeds} occupied · {area.availableBeds} available · {area.totalBeds}{" "}
                  {area.totalBeds === 1 ? "bed" : "beds"}
                </p>
              </header>
              {area.beds.length === 0 ? (
                <EmptyState title="No beds configured" description={`${area.name} has no beds yet.`} />
              ) : (
                <ul className="nursing-bed-board">
                  {area.beds.map((bed) => {
                    const taken = isOccupied(bed);
                    return (
                      <li key={bed.bedUuid || bed.bedNumber}>
                        <div className={`nursing-bed ${taken ? "is-occupied" : "is-free"}`}>
                          <button
                            type="button"
                            className="nursing-bed__main"
                            onClick={() => {
                              if (bed.patientUuid) {
                                openNursingPatient(bed.patientUuid);
                                return;
                              }
                              onAssignBed(bed);
                            }}
                          >
                            <span className="nursing-bed__number">{displayBedNumber(bed.bedNumber)}</span>
                            <Badge tone={taken ? "warning" : "success"}>{bedStatusLabel(bed)}</Badge>
                            {taken ? (
                              <>
                                <strong>{bed.patientName || "Patient assigned"}</strong>
                                <span>{bed.mrn && bed.mrn !== "—" ? bed.mrn : ""}</span>
                              </>
                            ) : (
                              <span className="nursing-bed__empty">Assign Bed</span>
                            )}
                          </button>
                          {taken && bed.patientUuid ? (
                            <div className="nursing-bed__actions">
                              <button type="button" onClick={() => onTransfer(bed.patientUuid!)}>
                                Transfer
                              </button>
                              <button type="button" onClick={() => onDischarge(bed.patientUuid!)}>
                                Discharge
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function TodaysVisitsView({
  loading,
  visits,
  onSearch,
}: {
  loading: boolean;
  visits: DoctorQueueRow[];
  onSearch: () => void;
}) {
  return (
    <Card id="visits">
      <SectionHeader
        title="Today's visits"
        description="Everyone with a visit started today. Open a record to take vitals, even if they are not on a bed."
      />
      <div className="nursing-desk__toolbar">
        <Button variant="secondary" onClick={onSearch}>
          Search patients
        </Button>
      </div>
      {loading ? (
        <LoadingState variant="board" label="Loading today's visits…" />
      ) : visits.length === 0 ? (
        <EmptyState
          title="No visits today"
          description="When Reception starts a visit, they appear here. You can still search for any patient and record vitals."
        />
      ) : (
        <ul className="nursing-person-list">
          {visits.map((visit) => (
            <li key={visit.visitUuid || visit.patientUuid}>
              <button
                type="button"
                className="nursing-person-card"
                onClick={() => visit.patientUuid && openNursingPatient(visit.patientUuid)}
              >
                <strong>{visit.patientName}</strong>
                <span>{visit.mrn}</span>
                <span>
                  {receptionVisitTypeLabel(visit.visitType)}
                  {visit.time && visit.time !== "—" ? ` · ${visit.time}` : ""}
                </span>
                <Badge tone={visit.status === "Ended" ? "neutral" : "success"}>
                  {visit.status === "Ended" ? "Ended" : "Visit today"}
                </Badge>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function PatientsView({
  loading,
  occupiedPatients,
  awaiting,
  visits,
  onSearch,
}: {
  loading: boolean;
  occupiedPatients: Array<{ areaName: string; bed: InpatientBed }>;
  awaiting: InpatientAwaiting[];
  visits: DoctorQueueRow[];
  onSearch: () => void;
}) {
  const rows = mergeNursingDayPatients(occupiedPatients, awaiting, visits);

  return (
    <Card id="patients">
      <SectionHeader
        title="Nursing patients"
        description="Patients with a visit today, plus anyone on a bed or waiting for a bed. Open a record to take vitals."
      />
      <div className="nursing-desk__toolbar">
        <Button variant="secondary" onClick={onSearch}>
          Search patients
        </Button>
      </div>
      {loading ? (
        <LoadingState variant="board" label="Loading patients…" />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No patients for today"
          description="When Reception starts a visit, or a doctor admits a patient, they appear here."
        />
      ) : (
        <ul className="nursing-person-list">
          {rows.map((row) => (
            <li key={row.key}>
              <button
                type="button"
                className="nursing-person-card"
                onClick={() => row.patientUuid && openNursingPatient(row.patientUuid)}
              >
                <strong>{row.name}</strong>
                <span>{row.mrn}</span>
                {row.age !== "—" || row.sex !== "—" ? (
                  <span>
                    {row.age === "—" ? "Age not recorded" : `${row.age} years`}
                    {row.sex !== "—" ? ` · ${row.sex}` : ""}
                  </span>
                ) : null}
                <span>
                  {row.status === "Visit today"
                    ? `${receptionVisitTypeLabel(row.visitType)} · ${row.detail}`
                    : row.detail}
                </span>
                <Badge
                  tone={
                    row.status === "Occupied"
                      ? "warning"
                      : row.status === "Admit requested"
                        ? "info"
                        : "success"
                  }
                >
                  {row.status}
                </Badge>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function AdmissionsView({
  loading,
  awaiting,
  onAssign,
  onDelete,
}: {
  loading: boolean;
  awaiting: InpatientAwaiting[];
  onAssign: (patient: InpatientAwaiting) => void;
  onDelete: (patient: InpatientAwaiting) => void;
}) {
  return (
    <Card id="admissions">
      <SectionHeader
        title="New admissions"
        description="The doctor has asked to admit these patients. Nursing assigns the bed."
      />
      {loading ? (
        <LoadingState variant="board" label="Loading admissions…" />
      ) : awaiting.length === 0 ? (
        <EmptyState
          title="No patients waiting for a bed"
          description="When a doctor admits a patient, they appear here."
        />
      ) : (
        <ul className="nursing-person-list">
          {awaiting.map((row) => (
            <li key={row.patientUuid}>
              <div className="nursing-person-card">
                <button type="button" className="nursing-desk__patient" onClick={() => openNursingPatient(row.patientUuid)}>
                  <strong>{row.patientName}</strong>
                </button>
                <span>{row.mrn}</span>
                <span>{row.requested ? formatDate(row.requested) : "Admission time not recorded"}</span>
                <Badge tone="info">Admit requested</Badge>
                <div className="nursing-person-card__action">
                  <Button variant="primary" onClick={() => onAssign(row)}>
                    Assign Bed
                  </Button>
                  <Button variant="secondary" onClick={() => onDelete(row)}>
                    Delete
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function TransfersView({
  loading,
  occupiedPatients,
  onTransfer,
}: {
  loading: boolean;
  occupiedPatients: Array<{ areaName: string; bed: InpatientBed }>;
  onTransfer: (patientUuid: string) => void;
}) {
  return (
    <Card id="transfers">
      <SectionHeader
        title="Transfers"
        description="Transfers are managed from the Ward Board. Patients currently on a bed can be moved from here."
      />
      {loading ? (
        <LoadingState variant="board" label="Loading occupancy…" />
      ) : occupiedPatients.length === 0 ? (
        <EmptyState
          title="No patients on a bed"
          description="There is no separate transfer history. Transfer a patient from the Ward Board when they are occupying a bed."
        />
      ) : (
        <ul className="nursing-person-list">
          {occupiedPatients.map(({ areaName, bed }) => (
            <li key={bed.bedUuid}>
              <div className="nursing-person-card">
                <button
                  type="button"
                  className="nursing-desk__patient"
                  onClick={() => bed.patientUuid && openNursingPatient(bed.patientUuid)}
                >
                  <strong>{bed.patientName}</strong>
                </button>
                <span>{bed.mrn}</span>
                <span>{locationLabel(areaName, bed.bedNumber)}</span>
                <span>{bed.admitted ? formatDate(bed.admitted) : "Admission time not recorded"}</span>
                <div className="nursing-person-card__action">
                  <Button
                    variant="primary"
                    onClick={() => bed.patientUuid && onTransfer(bed.patientUuid)}
                  >
                    Transfer Patient
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function DischargesView({
  loading,
  occupiedPatients,
  onDischarge,
}: {
  loading: boolean;
  occupiedPatients: Array<{ areaName: string; bed: InpatientBed }>;
  onDischarge: (patientUuid: string) => void;
}) {
  return (
    <Card id="discharges">
      <SectionHeader
        title="Discharges"
        description="Discharges are managed from the Ward Board. There is no separate discharge history in this list."
      />
      {loading ? (
        <LoadingState variant="board" label="Loading occupancy…" />
      ) : occupiedPatients.length === 0 ? (
        <EmptyState
          title="No patients on a bed"
          description="Discharge a patient from the Ward Board when they are occupying a bed."
        />
      ) : (
        <ul className="nursing-person-list">
          {occupiedPatients.map(({ areaName, bed }) => (
            <li key={bed.bedUuid}>
              <div className="nursing-person-card">
                <button
                  type="button"
                  className="nursing-desk__patient"
                  onClick={() => bed.patientUuid && openNursingPatient(bed.patientUuid)}
                >
                  <strong>{bed.patientName}</strong>
                </button>
                <span>{bed.mrn}</span>
                <span>
                  {areaName} · {displayBedNumber(bed.bedNumber)}
                </span>
                <div className="nursing-person-card__action">
                  <Button
                    variant="primary"
                    onClick={() => bed.patientUuid && onDischarge(bed.patientUuid)}
                  >
                    Discharge Patient
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
