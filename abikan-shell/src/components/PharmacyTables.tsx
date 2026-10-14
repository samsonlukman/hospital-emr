import { Badge } from "./Badge";
import { EmptyState } from "./EmptyState";
import { LoadingState } from "./LoadingState";
import { openPharmacyPatient, openPharmacyPrescription } from "../app/hashRoute";
import { pharmacyStatusTone } from "../services/openmrs/pharmacy";
import type { PharmacyOrderSummary } from "../types";
import "./LabTables.css";

interface PharmacyOrderTableProps {
  rows: PharmacyOrderSummary[];
  loading?: boolean;
  emptyTitle: string;
  emptyDescription: string;
  showPatient?: boolean;
  showAction?: boolean;
}

export function PharmacyOrderTable({
  rows,
  loading,
  emptyTitle,
  emptyDescription,
  showPatient = true,
  showAction = true,
}: PharmacyOrderTableProps) {
  if (loading) {
    return <LoadingState variant="board" label="Loading prescriptions…" />;
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
            <th>Prescription</th>
            <th>Doctor</th>
            <th>Ordered</th>
            <th>Quantity</th>
            <th>Status</th>
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
                      onClick={() => openPharmacyPatient(row.patientUuid)}
                    >
                      {row.patientName}
                    </button>
                  ) : (
                    row.patientName
                  )}
                </td>
              ) : null}
              {showPatient ? <td>{row.mrn || "—"}</td> : null}
              <td>
                {row.drugName}
                {row.strength && row.strength !== "—" ? (
                  <span className="lab-desk__panel">{row.strength}</span>
                ) : null}
              </td>
              <td>{row.provider}</td>
              <td>{row.ordered}</td>
              <td>
                {row.quantity}
                {row.quantityUnits ? ` ${row.quantityUnits}` : ""}
              </td>
              <td>
                <Badge tone={pharmacyStatusTone(row.status)}>{row.status}</Badge>
              </td>
              {showAction ? (
                <td>
                  <button
                    type="button"
                    className="lab-desk__link"
                    onClick={() => openPharmacyPrescription(row.uuid)}
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
