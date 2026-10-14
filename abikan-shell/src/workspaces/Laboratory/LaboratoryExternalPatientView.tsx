import { useEffect, useState } from "react";
import {
  openLaboratoryPatient,
  openLaboratoryWorklistOrder,
  returnToPreviousScreen,
} from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { searchPatients } from "../../services/openmrs/patients";
import { parsePatientDisplay } from "../../services/openmrs/clinicalPatient";
import {
  fetchExternalLaboratoryPatient,
  linkExternalLaboratoryPatient,
} from "../../services/laboratoryBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { PatientSearchHit } from "../../types";
import type { LaboratoryExternalPatientPayload } from "../../types/laboratoryBilling";
import { formatClinicalWhen } from "../../utils/datetime";
import { paymentStateTone } from "../PatientAccount/accountBadges";
import {
  EXTERNAL_PATIENT_LABEL,
  laboratoryRequestSourceLabel,
} from "./laboratoryView";
import "./LaboratoryWorkspace.css";

export function LaboratoryExternalPatientView({ externalId }: { externalId: string }) {
  const [record, setRecord] = useState<LaboratoryExternalPatientPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [patientQuery, setPatientQuery] = useState("");
  const [hits, setHits] = useState<PatientSearchHit[]>([]);
  const [linkPatient, setLinkPatient] = useState<PatientSearchHit | null>(null);
  const [confirmLink, setConfirmLink] = useState(false);
  const [linking, setLinking] = useState(false);

  const reload = () => {
    setLoading(true);
    setError("");
    return fetchExternalLaboratoryPatient(externalId)
      .then((payload) => {
        setRecord(payload);
      })
      .catch((reason) => {
        setRecord(null);
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "This external laboratory patient could not be loaded.",
        );
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    void reload();
  }, [externalId]);

  useEffect(() => {
    if (linkPatient || patientQuery.trim().length < 2) {
      setHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      void searchPatients(patientQuery)
        .then(setHits)
        .catch(() => setHits([]));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [patientQuery, linkPatient]);

  const link = async () => {
    if (!linkPatient?.uuid || !confirmLink || linking) {
      return;
    }
    setLinking(true);
    setError("");
    setNotice("");
    try {
      const saved = await linkExternalLaboratoryPatient(externalId, linkPatient.uuid);
      setRecord(saved);
      setNotice(saved.message || "Laboratory history linked to the registered patient.");
      setConfirmLink(false);
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The laboratory history could not be linked.",
      );
    } finally {
      setLinking(false);
    }
  };

  if (loading) {
    return <LoadingState variant="board" label="Loading external laboratory patient…" />;
  }

  if (!record) {
    return (
      <div className="lab-patient">
        <div className="lab-patient__nav">
          <Button variant="ghost" onClick={() => returnToPreviousScreen("#/laboratory")}>
            ← Laboratory
          </Button>
        </div>
        <EmptyState title={error || "External laboratory patient not found."} />
      </div>
    );
  }

  const linked = Boolean(record.linkedPatientUuid);
  const orders = record.orders ?? [];

  return (
    <div className="lab-patient">
      <div className="lab-patient__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/laboratory")}>
          ← Laboratory
        </Button>
      </div>

      <PageHeader
        title={record.patientName || "External patient"}
        description={`${EXTERNAL_PATIENT_LABEL} · External Lab ID ${record.externalId || externalId}`}
      />

      {error ? (
        <Alert tone="warning" title="External laboratory">
          <p>{error}</p>
        </Alert>
      ) : null}
      {notice ? (
        <Alert tone="success" title="External laboratory">
          <p>{notice}</p>
        </Alert>
      ) : null}

      <Card>
        <SectionHeader
          title="Patient details"
          description="External laboratory record. No hospital registration was created."
        />
        <dl className="lab-external__meta">
          <div>
            <dt>Patient type</dt>
            <dd>{EXTERNAL_PATIENT_LABEL}</dd>
          </div>
          <div>
            <dt>External Lab ID</dt>
            <dd>{record.externalId || externalId}</dd>
          </div>
          <div>
            <dt>Phone</dt>
            <dd>{record.buyerPhone || "—"}</dd>
          </div>
          <div>
            <dt>Sex</dt>
            <dd>{record.buyerSex || "—"}</dd>
          </div>
          <div>
            <dt>Date of birth / age</dt>
            <dd>{record.buyerDob || "—"}</dd>
          </div>
          <div>
            <dt>Address</dt>
            <dd>{record.buyerAddress || "—"}</dd>
          </div>
          <div>
            <dt>Request source</dt>
            <dd>
              {record.requestSourceLabel ||
                laboratoryRequestSourceLabel(record.requestSource)}
            </dd>
          </div>
          <div>
            <dt>Referrer</dt>
            <dd>{record.referrer || "—"}</dd>
          </div>
        </dl>
      </Card>

      <Card>
        <SectionHeader
          title="Order history"
          description="Laboratory orders for this external patient. Payment is collected at Accounts."
        />
        {orders.length === 0 ? (
          <EmptyState title="No laboratory orders yet for this external patient." />
        ) : (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Test</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Payment</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((row) => (
                  <tr key={row.uuid}>
                    <td>{formatClinicalWhen(row.ordered)}</td>
                    <td>{row.testName}</td>
                    <td>
                      {row.requestSourceLabel ||
                        laboratoryRequestSourceLabel(row.requestSource, row.comment)}
                    </td>
                    <td>{row.laboratoryStatus}</td>
                    <td>
                      <Badge tone={paymentStateTone(row.paymentStatus)}>{row.paymentStatus}</Badge>
                    </td>
                    <td>
                      {row.patientUuid && row.visitUuid ? (
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
      </Card>

      <Card>
        <SectionHeader
          title="Link to registered patient"
          description="If this person later registers at the hospital, link this laboratory history. Orders are not duplicated."
        />
        {linked ? (
          <Alert tone="success" title="Already linked">
            <p>
              Linked {formatClinicalWhen(record.linkedAt)}
              {record.linkedBy ? ` by ${record.linkedBy}` : ""}.{" "}
              <button
                type="button"
                className="lab-desk__link"
                onClick={() => openLaboratoryPatient(record.linkedPatientUuid || "")}
              >
                Open registered patient laboratory history
              </button>
            </p>
          </Alert>
        ) : (
          <div className="lab-new-order">
            <label>
              <span>Registered patient</span>
              <input
                value={
                  linkPatient
                    ? (() => {
                        const parsed = parsePatientDisplay(linkPatient.display);
                        return parsed.mrn && parsed.mrn !== "—"
                          ? `${parsed.name} (${parsed.mrn})`
                          : parsed.name || linkPatient.display;
                      })()
                    : patientQuery
                }
                onChange={(event) => {
                  setLinkPatient(null);
                  setConfirmLink(false);
                  setPatientQuery(event.target.value);
                }}
                placeholder="Search by name or hospital number"
              />
            </label>
            {!linkPatient && hits.length > 0 ? (
              <ul className="lab-new-order__hits">
                {hits.slice(0, 8).map((hit) => {
                  const parsed = parsePatientDisplay(hit.display);
                  return (
                    <li key={hit.uuid}>
                      <button
                        type="button"
                        onClick={() => {
                          setLinkPatient(hit);
                          setPatientQuery(parsed.name || hit.display);
                          setHits([]);
                        }}
                      >
                        {parsed.name || hit.display}
                        {parsed.mrn && parsed.mrn !== "—" ? ` · ${parsed.mrn}` : ""}
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : null}
            <label className="lab-new-order__radio">
              <input
                type="checkbox"
                checked={confirmLink}
                onChange={(event) => setConfirmLink(event.target.checked)}
                disabled={!linkPatient}
              />
              I confirm these laboratory orders belong to this registered patient
            </label>
            <div className="lab-new-order__actions">
              <Button
                disabled={!linkPatient || !confirmLink || linking}
                onClick={() => void link()}
              >
                {linking ? "Linking…" : "Link laboratory history"}
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
