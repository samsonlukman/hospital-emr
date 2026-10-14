import { Badge } from "./Badge";
import { EmptyState } from "./EmptyState";
import { LoadingState } from "./LoadingState";
import { openLaboratoryOrder, openLaboratoryPatient } from "../app/hashRoute";
import { resultFlag } from "../services/openmrs/laboratory";
import { resultShowsReferenceRange } from "../services/openmrs/laboratoryResult";
import type { LabOrderSummary, LabResultSummary } from "../types";
import "./LabTables.css";

interface LabOrderTableProps {
  rows: LabOrderSummary[];
  loading?: boolean;
  emptyTitle: string;
  emptyDescription: string;
  showPatient?: boolean;
  showAction?: boolean;
  openPatientUuid?: string;
}

export function LabOrderTable({
  rows,
  loading,
  emptyTitle,
  emptyDescription,
  showPatient = true,
  showAction = true,
  openPatientUuid,
}: LabOrderTableProps) {
  if (loading) {
    return <LoadingState variant="board" label="Loading laboratory orders…" />;
  }
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }
  return (
    <div className="abikan-table-wrap">
      <table className="abikan-table">
        <thead>
          <tr>
            {showPatient ? <th>Patient</th> : null}
            {showPatient ? <th>MRN</th> : null}
            <th>Test</th>
            <th>Priority</th>
            <th>Ordered</th>
            <th>Sample</th>
            {showAction ? <th>Action</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.uuid}>
              {showPatient ? (
                <td>
                  {row.patientUuid ? (
                    <button
                      type="button"
                      className="lab-desk__link"
                      onClick={() => openLaboratoryPatient(row.patientUuid)}
                    >
                      {row.patientName}
                    </button>
                  ) : (
                    row.patientName
                  )}
                </td>
              ) : null}
              {showPatient ? <td>{row.mrn}</td> : null}
              <td>{row.testName}</td>
              <td>
                <Badge tone={row.urgency === "STAT" ? "danger" : "neutral"}>{row.urgency}</Badge>
              </td>
              <td>{row.ordered}</td>
              <td>{row.accession}</td>
              {showAction ? (
                <td>
                  <button
                    type="button"
                    className="lab-desk__link"
                    onClick={() =>
                      openLaboratoryOrder(
                        row.uuid,
                        openPatientUuid || row.patientUuid,
                        row.visitUuid,
                      )
                    }
                  >
                    Open
                  </button>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface LabResultTableProps {
  rows: LabResultSummary[];
  loading?: boolean;
  emptyTitle: string;
  emptyDescription: string;
}

export function LabResultTable({
  rows,
  loading,
  emptyTitle,
  emptyDescription,
}: LabResultTableProps) {
  if (loading) {
    return <LoadingState variant="board" label="Loading laboratory results…" />;
  }
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }
  const hasAmbiguousMapping = rows.some((row) => row.mappingStatus === "ambiguous");
  return (
    <div className="abikan-table-wrap">
      <table className="abikan-table">
        <thead>
          <tr>
            <th>Test</th>
            <th>Result</th>
            <th>Unit</th>
            <th>Reference</th>
            <th>Flag</th>
            {hasAmbiguousMapping ? <th>Order match</th> : null}
            <th>Date / time</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const flag = resultFlag(row);
            const numeric = resultShowsReferenceRange(row.result);
            const range = numeric
              ? row.minNormal === "—" && row.maxNormal === "—"
                ? "—"
                : `${row.minNormal} – ${row.maxNormal}`
              : "";
            return (
              <tr key={`${row.orderUuid}-${row.testName}-${index}`}>
                <td>
                  {row.testName}
                  {row.panelName ? <span className="lab-desk__panel">{row.panelName}</span> : null}
                </td>
                <td>{row.result}</td>
                <td>{numeric ? row.unit || "—" : ""}</td>
                <td>{range}</td>
                <td>
                  <Badge
                    tone={flag === "Abnormal" ? "danger" : flag === "Normal" ? "success" : "neutral"}
                  >
                    {flag}
                  </Badge>
                </td>
                {hasAmbiguousMapping ? (
                  <td title={row.mappingMessage || undefined}>
                    {row.mappingStatus === "ambiguous" ? (
                      <Badge tone="warning">Needs review</Badge>
                    ) : (
                      "Matched"
                    )}
                  </td>
                ) : null}
                <td>{row.resultAt !== "—" ? row.resultAt : row.accessionAt}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
