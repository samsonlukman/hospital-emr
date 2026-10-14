import { Badge } from "./Badge";
import { EmptyState } from "./EmptyState";
import { LoadingState } from "./LoadingState";
import { openRadiologyOrder, openRadiologyPatient } from "../app/hashRoute";
import type { RadiologyNoteSummary, RadiologyOrderSummary } from "../types";
import {
  radiologyNoteForListedOrder,
  radiologyReportOpenLabel,
  radiologyReportStatusLabel,
} from "../workspaces/Radiology/radiologyReport";
import { radiologyVisitLabel, radiologyPaymentTone, radiologyRequestSourceLabel } from "../workspaces/Radiology/radiologyDesk";
import "./LabTables.css";

interface RadiologyOrderTableProps {
  rows: RadiologyOrderSummary[];
  notes?: RadiologyNoteSummary[];
  patientUuid?: string;
  visitUuid?: string;
  loading?: boolean;
  emptyTitle: string;
  emptyDescription: string;
  showPatient?: boolean;
  showAction?: boolean;
  showVisit?: boolean;
}

export function RadiologyOrderTable({
  rows,
  notes = [],
  patientUuid = "",
  visitUuid = "",
  loading,
  emptyTitle,
  emptyDescription,
  showPatient = true,
  showAction = true,
  showVisit = true,
}: RadiologyOrderTableProps) {
  if (loading) {
    return <LoadingState variant="board" label="Loading radiology orders…" />;
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
            {showPatient ? <th>Hospital number</th> : null}
            {showVisit ? <th>Visit</th> : null}
            <th>Examination</th>
            <th>Source</th>
            <th>Ordered</th>
            <th>Price / payment</th>
            <th>Report</th>
            {showAction ? <th>Action</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const note = radiologyNoteForListedOrder(notes, row, {
              patientUuid,
              visitUuid,
            });
            return (
              <tr key={row.uuid}>
                {showPatient ? (
                  <td>
                    {row.patientUuid ? (
                      <button
                        type="button"
                        className="lab-desk__link"
                        onClick={() => openRadiologyPatient(row.patientUuid)}
                      >
                        {row.patientName}
                      </button>
                    ) : (
                      row.patientName
                    )}
                  </td>
                ) : null}
                {showPatient ? <td>{row.mrn || "—"}</td> : null}
                {showVisit ? <td>{radiologyVisitLabel(row)}</td> : null}
                <td>{row.investigation}</td>
                <td>
                  {row.requestSourceLabel ||
                    radiologyRequestSourceLabel(row.requestSource, row.comment)}
                </td>
                <td>{row.ordered}</td>
                <td>
                  {row.feeFormatted ? <div>{row.feeFormatted}</div> : null}
                  <Badge
                    tone={radiologyPaymentTone(row.billingStatus || "Price pending")}
                  >
                    {row.billingStatus || "Price pending"}
                  </Badge>
                </td>
                <td>{note ? radiologyReportStatusLabel(note) : "Report pending"}</td>
                {showAction ? (
                  <td>
                    <button
                      type="button"
                      className="lab-desk__link"
                      onClick={() => openRadiologyOrder(row.uuid)}
                    >
                      {radiologyReportOpenLabel(note)}
                    </button>
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
