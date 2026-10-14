import { useEffect, useState } from "react";
import { openPatientRecord } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { TableSkeleton } from "../../components/TableSkeleton";
import { fetchPatientDirectory, setPatientNhis } from "../../services/patientDirectory";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type {
  PatientDirectoryPageSize,
  PatientDirectoryPayload,
  PatientLifeStatusFilter,
} from "../../types/patientDirectory";
import {
  PATIENT_PAGE_SIZES,
  displayPatientField,
  parsePatientPageSize,
  patientAliveLabel,
  patientPageRange,
} from "./patientDirectoryView";
import "../Admin/AdminWorkspace.css";
import "./PatientDirectoryWorkspace.css";

interface PatientDirectoryWorkspaceProps {
  workplace: "reception" | "administration";
}

const HEADERS = [
  "Patient",
  "Hospital number",
  "Sex",
  "Age",
  "Phone",
  "Card Type",
  "Alive",
  "NHIS",
  "Registered",
  "Action",
];

function errorMessage(reason: unknown): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : "The patient list could not be loaded.";
}

function parseLifeStatus(value: string): PatientLifeStatusFilter {
  if (value === "alive" || value === "deceased") {
    return value;
  }
  return "all";
}

export function PatientDirectoryWorkspace({ workplace }: PatientDirectoryWorkspaceProps) {
  const showLifeFilter = workplace === "administration";
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [lifeStatus, setLifeStatus] = useState<PatientLifeStatusFilter>("all");
  const [submittedLifeStatus, setSubmittedLifeStatus] = useState<PatientLifeStatusFilter>("all");
  const [pageSize, setPageSize] = useState<PatientDirectoryPageSize>(50);
  const [startIndex, setStartIndex] = useState(0);
  const [payload, setPayload] = useState<PatientDirectoryPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [nhisBusy, setNhisBusy] = useState("");
  const [nhisError, setNhisError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    fetchPatientDirectory({
      q: submittedQuery,
      limit: pageSize,
      startIndex,
      lifeStatus: showLifeFilter ? submittedLifeStatus : "all",
    })
      .then((next) => {
        if (!cancelled) {
          setPayload(next);
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setPayload(null);
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
  }, [pageSize, showLifeFilter, startIndex, submittedLifeStatus, submittedQuery]);

  const applySearch = () => {
    setStartIndex(0);
    setSubmittedQuery(query.trim());
    setSubmittedLifeStatus(showLifeFilter ? lifeStatus : "all");
  };

  const openPatient = (patientUuid: string) => {
    openPatientRecord(patientUuid, workplace);
  };

  const rows = payload?.patients ?? [];
  const total = payload?.total ?? 0;
  const canPrevious = startIndex > 0;
  const canNext = payload?.hasMore === true;
  const emptyTitle =
    submittedQuery || submittedLifeStatus !== "all"
      ? "No patients match this search."
      : "No patients are registered yet.";
  const emptyDescription = submittedQuery
    ? "Try another name, hospital number, or phone."
    : submittedLifeStatus === "deceased"
      ? "No deceased patients match this list."
      : submittedLifeStatus === "alive"
        ? "No living patients match this list."
        : workplace === "reception"
          ? "Register a patient to see them here."
          : undefined;

  return (
    <div
      className={`admin-workspace patient-directory${
        showLifeFilter ? " patient-directory--admin" : ""
      }`}
    >
      <PageHeader
        title="Patients"
        description={
          showLifeFilter
            ? "Every registered patient. Find a name or filter by Alive or Dead. Only Hospital Administration can change status."
            : "Every registered patient. Find a name, hospital number, or phone, then open the record."
        }
      />

      {error ? (
        <Alert tone="danger" title="The patient list could not be loaded">
          {error}
        </Alert>
      ) : null}
      {nhisError ? (
        <Alert tone="danger" title="NHIS could not be saved">
          {nhisError}
        </Alert>
      ) : null}

      <form
        className="admin-workspace__filters patient-directory__filters"
        aria-label="Find patients"
        onSubmit={(event) => {
          event.preventDefault();
          applySearch();
        }}
      >
        <label className="admin-workspace__search">
          <span>Find patient</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Name, hospital number, or phone"
          />
        </label>
        {showLifeFilter ? (
          <label>
            Status
            <select
              value={lifeStatus}
              onChange={(event) => {
                setLifeStatus(parseLifeStatus(event.target.value));
                setStartIndex(0);
                setSubmittedLifeStatus(parseLifeStatus(event.target.value));
              }}
            >
              <option value="all">All patients</option>
              <option value="alive">Alive patients</option>
              <option value="deceased">Dead patients</option>
            </select>
          </label>
        ) : null}
        <label>
          Patients per page
          <select
            value={pageSize}
            onChange={(event) => {
              setPageSize(parsePatientPageSize(event.target.value));
              setStartIndex(0);
            }}
          >
            {PATIENT_PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <div className="patient-directory__find">
          <Button type="submit">Find</Button>
        </div>
      </form>

      {loading ? <TableSkeleton label="Loading patients…" headers={HEADERS} /> : null}

      {!loading && !error && rows.length === 0 ? (
        <EmptyState title={emptyTitle} description={emptyDescription} />
      ) : null}

      {!loading && rows.length > 0 ? (
        <>
          <div className="abikan-table-wrap admin-workspace__table patient-directory__table">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th scope="col">Patient</th>
                  <th scope="col">Hospital number</th>
                  <th scope="col">Sex</th>
                  <th scope="col">Age</th>
                  <th scope="col">Phone</th>
                  <th scope="col">Card Type</th>
                  <th scope="col">Alive</th>
                  <th scope="col">NHIS</th>
                  <th scope="col">Registered</th>
                  <th className="patient-directory__action" scope="col">
                    <span className="patient-directory__sr">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((patient) => (
                  <tr key={patient.uuid}>
                    <td>
                      <button
                        type="button"
                        className="patient-directory__name"
                        onClick={() => openPatient(patient.uuid)}
                      >
                        {patient.name}
                      </button>
                    </td>
                    <td>{displayPatientField(patient.hospitalNumber)}</td>
                    <td>{displayPatientField(patient.sex)}</td>
                    <td>{displayPatientField(patient.age)}</td>
                    <td>{displayPatientField(patient.phone)}</td>
                    <td>{displayPatientField(patient.cardType)}</td>
                    <td>{patientAliveLabel(patient.alive)}</td>
                    <td>
                      <label className="patient-directory__nhis">
                        <input
                          type="checkbox"
                          checked={Boolean(patient.nhis)}
                          disabled={nhisBusy === patient.uuid}
                          aria-label={`NHIS for ${patient.name}`}
                          onChange={(event) => {
                            const next = event.target.checked;
                            setNhisBusy(patient.uuid);
                            setNhisError("");
                            setPatientNhis(patient.uuid, next)
                              .then(() => {
                                setPayload((current) =>
                                  current
                                    ? {
                                        ...current,
                                        patients: current.patients.map((row) =>
                                          row.uuid === patient.uuid ? { ...row, nhis: next } : row,
                                        ),
                                      }
                                    : current,
                                );
                              })
                              .catch((reason) => {
                                setNhisError(
                                  reason instanceof Error
                                    ? reason.message
                                    : "NHIS could not be saved. Try again.",
                                );
                              })
                              .finally(() => setNhisBusy(""));
                          }}
                        />
                        <span>NHIS</span>
                      </label>
                    </td>
                    <td>{displayPatientField(patient.registeredOn)}</td>
                    <td className="patient-directory__action">
                      <Button variant="secondary" onClick={() => openPatient(patient.uuid)}>
                        Open
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="patient-directory__pager">
            <p>{patientPageRange(startIndex, rows.length, total)}</p>
            <div className="patient-directory__pager-actions">
              <Button
                variant="secondary"
                disabled={!canPrevious || loading}
                onClick={() => setStartIndex(Math.max(0, startIndex - pageSize))}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                disabled={!canNext || loading}
                onClick={() => setStartIndex(startIndex + pageSize)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
