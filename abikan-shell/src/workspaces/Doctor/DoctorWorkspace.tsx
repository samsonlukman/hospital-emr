import { useEffect, useState } from "react";
import { openConsultation } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge, statusTone } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { TableSkeleton } from "../../components/TableSkeleton";
import { PageHeader } from "../../components/PageHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { receptionVisitTypeLabel } from "../../config/receptionVisitTypes";
import { fetchDoctorQueue } from "../../services/openmrs/doctorQueue";
import { fetchMyPatients } from "../../services/openmrs/myPatients";
import { fetchPharmacyCatalogue } from "../../services/pharmacy";
import { PatientAccountRequestError } from "../../services/patientAccount";
import {
  createPatientCall,
  newPatientCallRequestId,
  PatientCallRequestError,
} from "../../services/patientCall";
import type { DoctorQueueRow, MyPatientRow, WorkspaceContext } from "../../types";
import type { PharmacyCatalogueItem } from "../../types/pharmacy";
import type { AdminPeriodId } from "../../types/administration";
import { formatDailyVisitNumber } from "../../utils/dailyVisitNumber";
import { formatClinicalWhen, greetingForNow } from "../../utils/datetime";
import {
  filterMyPatients,
  MY_PATIENTS_EMPTY_HELP,
  MY_PATIENTS_HELP,
  myPatientsEmptyTitle,
  myPatientsHref,
} from "./myPatients";
import { focusPatientSearch, latestPatientsFirst } from "./todaysPatients";
import {
  DOCTOR_PHARMACY_MEDICINES_EMPTY,
  DOCTOR_PHARMACY_MEDICINES_HELP,
  DOCTOR_PHARMACY_MEDICINES_NONE_FOUND,
  DOCTOR_PHARMACY_MEDICINES_TITLE,
  doctorMedicineStockLabel,
  filterDoctorPharmacyMedicines,
} from "./doctorPharmacyMedicines";
import { DEPARTMENT_REVENUE_PERIODS } from "../shared/departmentRevenueView";
import { useDepartmentRevenue } from "../shared/DepartmentRevenue";
import "./DoctorWorkspace.css";

interface DoctorWorkspaceProps {
  context: WorkspaceContext;
  section?: string | null;
}

export function DoctorWorkspace({ context, section }: DoctorWorkspaceProps) {
  const showMyPatients = section === "my-patients";
  const showPharmacyMedicines = section === "pharmacy-medicines";

  if (showMyPatients) {
    return <MyPatientsDesk context={context} />;
  }
  if (showPharmacyMedicines) {
    return <PharmacyMedicinesDesk context={context} />;
  }

  return <TodaysPatientsDesk context={context} />;
}

function TodaysPatientsDesk({ context }: { context: WorkspaceContext }) {
  const [rows, setRows] = useState<DoctorQueueRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [callingVisit, setCallingVisit] = useState<string | null>(null);
  const [callNotice, setCallNotice] = useState("");
  const [callError, setCallError] = useState("");
  const revenue = useDepartmentRevenue();

  useEffect(() => {
    let cancelled = false;
    fetchDoctorQueue()
      .then((value) => {
        if (!cancelled) {
          setRows(value);
          setError("");
        }
      })
      .catch((reason) => {
        console.error("Unable to load today's patients", reason);
        if (!cancelled) {
          setRows([]);
          setError(
            reason instanceof PatientAccountRequestError
              ? reason.message
              : "Today's patients could not be loaded. You can still search for a patient.",
          );
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
  }, []);

  const callPatient = async (row: DoctorQueueRow) => {
    if (callingVisit) {
      return;
    }
    setCallingVisit(row.visitUuid);
    setCallError("");
    setCallNotice("");
    try {
      const result = await createPatientCall({
        patientUuid: row.patientUuid,
        visitUuid: row.visitUuid,
        patientName: row.patientName,
        mrn: row.mrn,
        dailyVisitNumber: row.dailyVisitNumber,
        requestId: newPatientCallRequestId(),
      });
      setCallNotice(
        result.duplicate
          ? `Reception was already notified for ${row.patientName}.`
          : `Reception notified: please bring ${row.patientName}.`,
      );
    } catch (reason) {
      setCallError(
        reason instanceof PatientCallRequestError || reason instanceof PatientAccountRequestError
          ? reason.message
          : "Reception could not be notified. Try again.",
      );
    } finally {
      setCallingVisit(null);
    }
  };

  const listed = latestPatientsFirst(rows);

  return (
    <div className="doctor-desk doctor-desk--today">
      <header className="doctor-desk__top">
        <p className="doctor-desk__greeting">
          {greetingForNow()}, {context.displayName}
        </p>
        <div className="doctor-desk__stats">
          <p className="doctor-desk__stat">
            <span>Patients</span>
            <strong>{loading ? "…" : rows.length}</strong>
          </p>
          <p className="doctor-desk__stat" title={revenue.error || undefined}>
            <span>Revenue</span>
            <strong>{revenue.loading ? "…" : revenue.error ? "—" : revenue.value}</strong>
          </p>
          <form
            className="doctor-desk__range"
            onSubmit={(event) => {
              event.preventDefault();
              void revenue.load();
            }}
          >
            <label>
              <span>Date range</span>
              <select
                value={revenue.period}
                onChange={(event) => revenue.setPeriod(event.target.value as AdminPeriodId)}
                aria-label="Date range"
              >
                {DEPARTMENT_REVENUE_PERIODS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            {revenue.period === "custom" ? (
              <>
                <label>
                  <span>From</span>
                  <input
                    type="date"
                    value={revenue.customStart}
                    onChange={(event) => revenue.setCustomStart(event.target.value)}
                    aria-label="From"
                  />
                </label>
                <label>
                  <span>To</span>
                  <input
                    type="date"
                    value={revenue.customEnd}
                    onChange={(event) => revenue.setCustomEnd(event.target.value)}
                    aria-label="To"
                  />
                </label>
                <Button type="submit" disabled={Boolean(revenue.customProblem)}>
                  Apply
                </Button>
              </>
            ) : null}
          </form>
          <Button variant="secondary" onClick={focusPatientSearch}>
            Search patient
          </Button>
        </div>
      </header>

      <Card id="queue" className="doctor-desk__queue">
        {error ? (
          <Alert tone="danger" title="Unable to load today's patients.">
            <p>{error}</p>
          </Alert>
        ) : null}
        {callNotice ? (
          <Alert tone="success" title="Reception notified.">
            <p>{callNotice}</p>
          </Alert>
        ) : null}
        {callError ? (
          <Alert tone="danger" title="Call not sent.">
            <p>{callError}</p>
          </Alert>
        ) : null}
        {loading && !error ? (
          <TableSkeleton
            label="Loading today's patients…"
            headers={["No.", "Patient", "Hospital number", "Visit", "Time", "Status", "Action"]}
          />
        ) : null}
        {!error && !loading && rows.length === 0 ? (
          <EmptyState
            title="No patients found today."
            description="Search for a patient to open their record."
          />
        ) : null}
        {!error && !loading && rows.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>No.</th>
                  <th>Patient</th>
                  <th>Hospital number</th>
                  <th>Visit</th>
                  <th>Time</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {listed.map((row) => (
                  <tr
                    key={row.id}
                    className="doctor-desk__visit"
                    onClick={() => openConsultation(row.patientUuid, row.visitUuid)}
                  >
                    <td>{formatDailyVisitNumber(row.dailyVisitNumber)}</td>
                    <td>
                      <button
                        type="button"
                        className="doctor-desk__patient"
                        onClick={() => openConsultation(row.patientUuid, row.visitUuid)}
                      >
                        {row.patientName}
                      </button>
                    </td>
                    <td>{row.mrn}</td>
                    <td>{receptionVisitTypeLabel(row.visitType)}</td>
                    <td>{row.time}</td>
                    <td>
                      <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                    </td>
                    <td onClick={(event) => event.stopPropagation()}>
                      <div className="doctor-desk__row-actions">
                        <Button
                          variant="secondary"
                          className="doctor-desk__call"
                          title="Ask Reception to bring this patient"
                          aria-label={`Ask Reception to bring ${row.patientName}`}
                          busy={callingVisit === row.visitUuid}
                          busyLabel="Calling…"
                          disabled={callingVisit != null && callingVisit !== row.visitUuid}
                          onClick={() => void callPatient(row)}
                        >
                          Call
                        </Button>
                        <Button
                          variant="secondary"
                          onClick={() => openConsultation(row.patientUuid, row.visitUuid)}
                        >
                          Open
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  );
}

function MyPatientsDesk({ context }: { context: WorkspaceContext }) {
  const [rows, setRows] = useState<MyPatientRow[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchMyPatients()
      .then((value) => {
        if (!cancelled) {
          setRows(value);
          setError("");
        }
      })
      .catch((reason) => {
        console.error("Unable to load my patients", reason);
        if (!cancelled) {
          setRows([]);
          setError(
            reason instanceof PatientAccountRequestError
              ? reason.message
              : "Your patients could not be loaded.",
          );
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
  }, []);

  const visible = filterMyPatients(rows, query);

  return (
    <div className="doctor-desk">
      <PageHeader
        title="My Patients"
        description={`${greetingForNow()}, ${context.displayName}. ${MY_PATIENTS_HELP}`}
      >
        <Button variant="secondary" onClick={focusPatientSearch}>
          Search patient
        </Button>
      </PageHeader>

      <Card id="my-patients">
        <SectionHeader
          title="Patients you have attended"
          description="Open a name to see Previous visits. A visit is selected only when you choose one."
        />
        <label className="doctor-desk__search">
          <span>Search</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Name or hospital number"
          />
        </label>
        {error ? (
          <Alert tone="danger" title="Unable to load your patients.">
            <p>{error}</p>
          </Alert>
        ) : null}
        {loading && !error ? (
          <TableSkeleton
            label="Loading your patients…"
            headers={["Patient", "Hospital No.", "Last visit", "Visit type", "Last attended", "Action"]}
          />
        ) : null}
        {!error && !loading && visible.length === 0 ? (
          <EmptyState
            title={myPatientsEmptyTitle({ loading: false, hasRows: rows.length > 0, query })}
            description={rows.length > 0 ? undefined : MY_PATIENTS_EMPTY_HELP}
          />
        ) : null}
        {!error && !loading && visible.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Patient</th>
                  <th>Hospital No.</th>
                  <th>Last visit</th>
                  <th>Visit type</th>
                  <th>Last attended</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={row.id}>
                    <td>
                      {row.patientName}
                      {row.ageSex ? (
                        <span className="doctor-desk__meta"> {row.ageSex}</span>
                      ) : null}
                    </td>
                    <td>{row.mrn}</td>
                    <td>
                      {row.dailyVisitNumber
                        ? formatDailyVisitNumber(row.dailyVisitNumber)
                        : "—"}
                    </td>
                    <td>{receptionVisitTypeLabel(row.visitType)}</td>
                    <td>{formatClinicalWhen(row.lastAttended)}</td>
                    <td>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          window.location.hash = myPatientsHref(row.patientUuid);
                        }}
                      >
                        Open
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  );
}

function PharmacyMedicinesDesk({ context }: { context: WorkspaceContext }) {
  const [items, setItems] = useState<PharmacyCatalogueItem[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchPharmacyCatalogue()
      .then((payload) => {
        if (!cancelled) {
          setItems(payload.items || []);
          setError("");
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setItems([]);
          setError(
            reason instanceof PatientAccountRequestError
              ? reason.message
              : "Pharmacy medicines could not be loaded.",
          );
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
  }, []);

  const visible = filterDoctorPharmacyMedicines(items, query);

  return (
    <div className="doctor-desk">
      <PageHeader
        title={DOCTOR_PHARMACY_MEDICINES_TITLE}
        description={`${greetingForNow()}, ${context.displayName}. ${DOCTOR_PHARMACY_MEDICINES_HELP}`}
      />
      <Card id="pharmacy-medicines">
        <SectionHeader
          title="Available in Pharmacy"
          description="These are the medicines Pharmacy lists today. Prescribe from the patient chart if a name is missing."
        />
        <label className="doctor-desk__search">
          <span>Find a medicine</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by medicine name"
          />
        </label>
        {error ? (
          <Alert tone="danger" title="Unable to load Pharmacy medicines.">
            <p>{error}</p>
          </Alert>
        ) : null}
        {loading && !error ? (
          <TableSkeleton
            label="Loading Pharmacy medicines…"
            headers={["Medicine", "Strength", "Form", "In stock", "Price"]}
          />
        ) : null}
        {!error && !loading && visible.length === 0 ? (
          <EmptyState
            title={query.trim() ? DOCTOR_PHARMACY_MEDICINES_NONE_FOUND : DOCTOR_PHARMACY_MEDICINES_EMPTY}
          />
        ) : null}
        {!error && !loading && visible.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Medicine</th>
                  <th>Strength</th>
                  <th>Form</th>
                  <th>In stock</th>
                  <th>Price</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={`${row.id}-${row.strength}-${row.form}`}>
                    <td>
                      <strong>{row.name}</strong>
                      {row.brandName ? (
                        <div className="doctor-desk__meta">Brand: {row.brandName}</div>
                      ) : null}
                    </td>
                    <td>{row.strength || "—"}</td>
                    <td>{row.form || "—"}</td>
                    <td>{doctorMedicineStockLabel(row)}</td>
                    <td>{row.price?.formatted || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
