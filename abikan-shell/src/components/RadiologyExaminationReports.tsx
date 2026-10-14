import type { RadiologyNoteSummary, RadiologyOrderSummary } from "../types";
import { radiologyExaminationReportView } from "../workspaces/Radiology/radiologyReport";
import "./RadiologyExaminationReports.css";

interface RadiologyExaminationReportsProps {
  orders: RadiologyOrderSummary[];
  notes: RadiologyNoteSummary[];
  patientUuid: string;
  visitUuid: string | null | undefined;
  loading?: boolean;
  unavailable?: boolean;
}

export function RadiologyExaminationReports({
  orders,
  notes,
  patientUuid,
  visitUuid,
  loading,
  unavailable,
}: RadiologyExaminationReportsProps) {
  if (unavailable) {
    return <p className="consult__muted">Radiology reports unavailable</p>;
  }
  if (loading) {
    return <p className="consult__muted">Loading radiology reports…</p>;
  }
  const selected = (visitUuid || "").trim();
  if (!selected) {
    return (
      <p className="consult__muted">
        Open a visit to see imaging reports for that visit.
      </p>
    );
  }
  if (orders.length === 0) {
    return (
      <p className="rad-exam-reports__empty">No imaging orders on this visit yet.</p>
    );
  }
  return (
    <ul className="rad-exam-reports">
      {orders.map((order) => {
        const view = radiologyExaminationReportView(order, notes, {
          patientUuid,
          visitUuid: selected,
        });
        return (
          <li key={order.uuid} className="rad-exam-reports__item">
            <h5>{view.examination}</h5>
            {view.payment ? <p className="rad-exam-reports__meta">{view.payment}</p> : null}
            <p className="rad-exam-reports__label">Report</p>
            {view.report ? (
              <>
                <p className="rad-exam-reports__text">{view.report}</p>
                {view.reportedBy ? (
                  <p className="rad-exam-reports__meta">Reported by: {view.reportedBy}</p>
                ) : null}
                {view.reportedAt ? (
                  <p className="rad-exam-reports__meta">Reported: {view.reportedAt}</p>
                ) : null}
              </>
            ) : (
              <p className="rad-exam-reports__empty">{view.empty}</p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
