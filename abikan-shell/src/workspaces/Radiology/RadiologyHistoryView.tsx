import { useEffect, useState } from "react";
import {
  openRadiologyExternalStudy,
  openRadiologyPatient,
  openRadiologyWorklistOrder,
} from "../../app/hashRoute";
import { RADIOGRAPHY_GROUP, ULTRASOUND_GROUP } from "../../config/radiologyMenu";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { SectionHeader } from "../../components/SectionHeader";
import { fetchRadiologyHistory } from "../../services/radiologyBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { RadiologyWorklistRow } from "../../types/radiologyBilling";
import { formatClinicalWhen } from "../../utils/datetime";
import {
  radiologyPatientTypeLabel,
  radiologyPaymentTone,
  radiologyRequestSourceLabel,
  radiologyVisitLabel,
} from "./radiologyDesk";
import { canOpenWorklistRow } from "./radiologyWorklist";

const PAGE_SIZE = 25;

export function RadiologyHistoryView() {
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [requestSource, setRequestSource] = useState("");
  const [patientType, setPatientType] = useState("");
  const [report, setReport] = useState("");
  const [category, setCategory] = useState("");
  const [applied, setApplied] = useState({
    q: "",
    from: "",
    to: "",
    requestSource: "",
    patientType: "",
    report: "",
    category: "",
  });
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<RadiologyWorklistRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    void fetchRadiologyHistory({
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
            : "Imaging history could not be loaded.",
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
  const appliedFilters = {
    q,
    from,
    to,
    requestSource,
    patientType,
    report,
    category,
  };

  return (
    <Card id="history">
      <SectionHeader
        title="Imaging History"
        description="Registered and external patients. Doctor Order, Radiology Direct, and External Referral are shown separately from report status."
      />
      <div className="rad-worklist__filters">
        <label className="rad-worklist__search">
          <span>Search</span>
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Name, phone, hospital number, or record number"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                setOffset(0);
                setApplied(appliedFilters);
              }
            }}
          />
        </label>
        <label className="rad-worklist__search">
          <span>From</span>
          <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        </label>
        <label className="rad-worklist__search">
          <span>To</span>
          <input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
        </label>
        <label className="rad-worklist__search">
          <span>Patient type</span>
          <select value={patientType} onChange={(event) => setPatientType(event.target.value)}>
            <option value="">Any</option>
            <option value="registered">Registered Patient</option>
            <option value="external">External Patient</option>
          </select>
        </label>
        <label className="rad-worklist__search">
          <span>Request source</span>
          <select value={requestSource} onChange={(event) => setRequestSource(event.target.value)}>
            <option value="">Any</option>
            <option value="doctor_order">Doctor Order</option>
            <option value="radiology_direct">Radiology Direct</option>
            <option value="external_referral">External Referral</option>
          </select>
        </label>
        <label className="rad-worklist__search">
          <span>Report</span>
          <select value={report} onChange={(event) => setReport(event.target.value)}>
            <option value="">Any</option>
            <option value="pending">Report pending</option>
            <option value="reported">Reported</option>
          </select>
        </label>
        <label className="rad-worklist__search">
          <span>Examination</span>
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="">All</option>
            <option value={ULTRASOUND_GROUP}>Ultrasound Scan</option>
            <option value={RADIOGRAPHY_GROUP}>Radiography / Fluoroscopy</option>
          </select>
        </label>
        <div className="rad-history__actions">
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
              setFrom("");
              setTo("");
              setRequestSource("");
              setPatientType("");
              setReport("");
              setCategory("");
              setOffset(0);
              setApplied({
                q: "",
                from: "",
                to: "",
                requestSource: "",
                patientType: "",
                report: "",
                category: "",
              });
            }}
          >
            Clear
          </Button>
        </div>
      </div>

      {error ? (
        <Alert tone="warning" title="Imaging History">
          <p>{error}</p>
        </Alert>
      ) : null}

      <p className="rad-history__period">
        {total > 0 ? `Showing ${pageStart}–${pageEnd} of ${total}` : "No matching studies"}
      </p>

      {loading ? (
        <LoadingState variant="board" label="Loading imaging history…" />
      ) : items.length === 0 ? (
        <EmptyState title="No imaging studies match these filters." />
      ) : (
        <div className="abikan-table-wrap">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Patient</th>
                <th>Type</th>
                <th>Study</th>
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
                        className="rad-link"
                        onClick={() => openRadiologyPatient(row.patientUuid)}
                      >
                        {row.patientName}
                      </button>
                    ) : (
                      row.patientName
                    )}
                    <div className="rad-history__muted">
                      {row.isExternal ? row.buyerPhone || row.studyId || "" : row.mrn}
                    </div>
                  </td>
                  <td>{radiologyPatientTypeLabel(row.patientType, row.isExternal)}</td>
                  <td>
                    {row.investigation}
                    <div className="rad-history__muted">
                      {row.isExternal ? "External imaging" : radiologyVisitLabel(row)}
                    </div>
                  </td>
                  <td>
                    {row.requestSourceLabel ||
                      radiologyRequestSourceLabel(row.requestSource, row.comment)}
                  </td>
                  <td>{row.reportStatus}</td>
                  <td>
                    <Badge tone={radiologyPaymentTone(row.billingStatus)}>{row.billingStatus}</Badge>
                  </td>
                  <td>
                    {canOpenWorklistRow(row) ? (
                      <button
                        type="button"
                        className="rad-link"
                        onClick={() => {
                          if (row.isExternal) {
                            openRadiologyExternalStudy(row.studyId || row.uuid);
                            return;
                          }
                          openRadiologyWorklistOrder({
                            orderUuid: row.uuid,
                            patientUuid: row.patientUuid,
                            visitUuid: row.visitUuid,
                          });
                        }}
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
        <div className="rad-history__actions">
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
