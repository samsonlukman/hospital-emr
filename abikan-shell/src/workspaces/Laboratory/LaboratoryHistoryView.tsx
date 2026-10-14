import { useEffect, useState } from "react";
import {
  openLaboratoryExternalPatient,
  openLaboratoryPatient,
  openLaboratoryWorklistOrder,
} from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { SectionHeader } from "../../components/SectionHeader";
import { fetchLaboratoryHistory } from "../../services/laboratoryBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { LaboratoryBoardOrder } from "../../types/laboratoryCatalogue";
import { formatClinicalWhen } from "../../utils/datetime";
import { paymentStateTone } from "../PatientAccount/accountBadges";
import {
  laboratoryPatientTypeLabel,
  laboratoryRequestSourceLabel,
} from "./laboratoryView";
import "./LaboratoryWorkspace.css";

const PAGE_SIZE = 25;

export function LaboratoryHistoryView() {
  const [q, setQ] = useState("");
  const [requestSource, setRequestSource] = useState("");
  const [patientType, setPatientType] = useState("");
  const [applied, setApplied] = useState({
    q: "",
    requestSource: "",
    patientType: "",
  });
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<LaboratoryBoardOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    void fetchLaboratoryHistory({
      ...applied,
      offset,
      limit: PAGE_SIZE,
    })
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setItems(payload.items ?? []);
        setTotal(Number(payload.total) || 0);
      })
      .catch((reason) => {
        if (cancelled) {
          return;
        }
        setItems([]);
        setTotal(0);
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "Laboratory history could not be loaded.",
        );
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [applied, offset]);

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);
  const appliedFilters = { q, requestSource, patientType };

  return (
    <Card id="history">
      <SectionHeader
        title="Lab History"
        description="Registered and external patients. Doctor Order, Laboratory Direct, and External Referral are shown separately."
      />
      <div className="lab-history__filters">
        <label className="lab-desk__search">
          <span>Search</span>
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Name, phone, hospital number, or External Lab ID"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                setOffset(0);
                setApplied(appliedFilters);
              }
            }}
          />
        </label>
        <label className="lab-desk__search">
          <span>Patient type</span>
          <select value={patientType} onChange={(event) => setPatientType(event.target.value)}>
            <option value="">Any</option>
            <option value="registered">Registered Patient</option>
            <option value="external">External Patient</option>
          </select>
        </label>
        <label className="lab-desk__search">
          <span>Request source</span>
          <select value={requestSource} onChange={(event) => setRequestSource(event.target.value)}>
            <option value="">Any</option>
            <option value="doctor_order">Doctor Order</option>
            <option value="laboratory_direct">Laboratory Direct</option>
            <option value="external_referral">External Referral</option>
          </select>
        </label>
        <div className="lab-history__actions">
          <Button
            onClick={() => {
              setOffset(0);
              setApplied(appliedFilters);
            }}
          >
            Apply
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setQ("");
              setRequestSource("");
              setPatientType("");
              setOffset(0);
              setApplied({ q: "", requestSource: "", patientType: "" });
            }}
          >
            Clear
          </Button>
        </div>
      </div>

      {error ? (
        <Alert tone="warning" title="Lab History">
          <p>{error}</p>
        </Alert>
      ) : null}

      <p className="lab-history__period">
        {total > 0 ? `Showing ${pageStart}–${pageEnd} of ${total}` : "No matching orders"}
      </p>

      {loading ? (
        <LoadingState variant="board" label="Loading laboratory history…" />
      ) : items.length === 0 ? (
        <EmptyState title="No laboratory orders match these filters." />
      ) : (
        <div className="abikan-table-wrap">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Patient</th>
                <th>Type</th>
                <th>Test</th>
                <th>Source</th>
                <th>Status</th>
                <th>Payment</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.uuid}>
                  <td>{formatClinicalWhen(row.ordered)}</td>
                  <td>
                    {row.patientUuid && !row.isExternal ? (
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
                    <div className="lab-history__muted">
                      {row.isExternal ? row.buyerPhone || row.externalId || "" : row.mrn}
                    </div>
                  </td>
                  <td>{laboratoryPatientTypeLabel(row.patientType, row.isExternal)}</td>
                  <td>
                    {row.testName}
                    {row.outsourced ? <div className="lab-history__muted">Outsourced</div> : null}
                  </td>
                  <td>
                    {row.requestSourceLabel ||
                      laboratoryRequestSourceLabel(row.requestSource, row.comment)}
                  </td>
                  <td>{row.laboratoryStatus}</td>
                  <td>
                    <Badge tone={paymentStateTone(row.paymentStatus)}>{row.paymentStatus}</Badge>
                  </td>
                  <td>
                    {row.isExternal && row.externalId ? (
                      <button
                        type="button"
                        className="lab-desk__link"
                        onClick={() => openLaboratoryExternalPatient(row.externalId || "")}
                      >
                        Open
                      </button>
                    ) : row.patientUuid && row.visitUuid ? (
                      <button
                        type="button"
                        className="lab-desk__link"
                        onClick={() =>
                          openLaboratoryWorklistOrder({
                            orderUuid: row.uuid,
                            patientUuid: row.patientUuid,
                            visitUuid: row.visitUuid,
                          })
                        }
                      >
                        Open
                      </button>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {total > PAGE_SIZE ? (
        <div className="lab-history__actions">
          <Button
            variant="ghost"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </Button>
          <Button
            variant="ghost"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      ) : null}
    </Card>
  );
}
