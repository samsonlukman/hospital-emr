import { useEffect, useState } from "react";
import { openRadiologyPatient, returnToPreviousScreen } from "../../app/hashRoute";
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
  fetchExternalRadiologyStudy,
  linkExternalRadiologyStudy,
  saveExternalRadiologyReport,
} from "../../services/radiologyBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { PatientSearchHit } from "../../types";
import type { RadiologyExternalStudyPayload } from "../../types/radiologyBilling";
import { formatClinicalWhen } from "../../utils/datetime";
import {
  EXTERNAL_PATIENT_LABEL,
  radiologyPaymentTone,
  radiologyRequestSourceLabel,
} from "./radiologyDesk";
import "./RadiologyWorkspace.css";

export function RadiologyExternalStudyView({ studyId }: { studyId: string }) {
  const [study, setStudy] = useState<RadiologyExternalStudyPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState("");
  const [savingReport, setSavingReport] = useState(false);
  const [patientQuery, setPatientQuery] = useState("");
  const [hits, setHits] = useState<PatientSearchHit[]>([]);
  const [linkPatient, setLinkPatient] = useState<PatientSearchHit | null>(null);
  const [confirmLink, setConfirmLink] = useState(false);
  const [linking, setLinking] = useState(false);

  const reload = () => {
    setLoading(true);
    setError("");
    return fetchExternalRadiologyStudy(studyId)
      .then((payload) => {
        setStudy(payload);
        setDraft(payload.reportText || "");
      })
      .catch((reason) => {
        setStudy(null);
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "This imaging study could not be loaded.",
        );
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    void reload();
  }, [studyId]);

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

  const saveReport = async () => {
    if (!draft.trim() || savingReport) {
      return;
    }
    setSavingReport(true);
    setError("");
    setNotice("");
    try {
      const saved = await saveExternalRadiologyReport(studyId, draft.trim());
      setStudy(saved);
      setNotice(saved.message || "Report saved.");
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The report could not be saved.",
      );
    } finally {
      setSavingReport(false);
    }
  };

  const link = async () => {
    if (!linkPatient?.uuid || !confirmLink || linking) {
      return;
    }
    setLinking(true);
    setError("");
    setNotice("");
    try {
      const saved = await linkExternalRadiologyStudy(studyId, linkPatient.uuid);
      setStudy(saved);
      setNotice(saved.message || "Imaging study linked to the registered patient.");
      setConfirmLink(false);
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The imaging study could not be linked.",
      );
    } finally {
      setLinking(false);
    }
  };

  if (loading) {
    return <LoadingState variant="board" label="Loading external imaging study…" />;
  }

  if (!study) {
    return (
      <div className="rad-patient">
        <div className="rad-patient__nav">
          <Button variant="ghost" onClick={() => returnToPreviousScreen("#/radiology")}>
            ← Radiology
          </Button>
        </div>
        <EmptyState title={error || "Imaging study not found."} />
      </div>
    );
  }

  const linked = Boolean(study.linkedPatientUuid);

  return (
    <div className="rad-patient">
      <div className="rad-patient__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/radiology")}>
          ← Radiology
        </Button>
      </div>

      <PageHeader
        title={study.patientName || "External patient"}
        description={`${EXTERNAL_PATIENT_LABEL} · ${study.investigation}`}
      />

      {error ? (
        <Alert tone="warning" title="External imaging">
          <p>{error}</p>
        </Alert>
      ) : null}
      {notice ? (
        <Alert tone="success" title="External imaging">
          <p>{notice}</p>
        </Alert>
      ) : null}

      <Card>
        <SectionHeader title="Study details" description="External imaging record. No hospital registration was created." />
        <dl className="rad-external__meta">
          <div>
            <dt>Patient type</dt>
            <dd>{EXTERNAL_PATIENT_LABEL}</dd>
          </div>
          <div>
            <dt>Phone</dt>
            <dd>{study.buyerPhone || "—"}</dd>
          </div>
          <div>
            <dt>Sex</dt>
            <dd>{study.buyerSex || "—"}</dd>
          </div>
          <div>
            <dt>Date of birth / age</dt>
            <dd>{study.buyerDob || "—"}</dd>
          </div>
          <div>
            <dt>Address</dt>
            <dd>{study.buyerAddress || "—"}</dd>
          </div>
          <div>
            <dt>Request source</dt>
            <dd>
              {study.requestSourceLabel ||
                radiologyRequestSourceLabel(study.requestSource, study.comment)}
            </dd>
          </div>
          <div>
            <dt>Referrer</dt>
            <dd>{study.referrer || "—"}</dd>
          </div>
          <div>
            <dt>Ordered</dt>
            <dd>{formatClinicalWhen(study.ordered)}</dd>
          </div>
          <div>
            <dt>Bill</dt>
            <dd>{study.orderNumber || "—"}</dd>
          </div>
          <div>
            <dt>Payment</dt>
            <dd>
              <Badge tone={radiologyPaymentTone(study.billingStatus)}>{study.billingStatus}</Badge>
              {study.feeFormatted ? ` · ${study.feeFormatted}` : ""}
            </dd>
          </div>
          <div>
            <dt>Clinical indication</dt>
            <dd>{study.clinicalIndication || study.comment || "—"}</dd>
          </div>
          <div>
            <dt>Record number</dt>
            <dd>{study.studyId || study.uuid}</dd>
          </div>
        </dl>
      </Card>

      <Card>
        <SectionHeader
          title="Radiology report"
          description="Findings and impression. Payment is separate from reporting."
        />
        {study.hasReport && !draft ? (
          <p className="rad-external__report">{study.reportText}</p>
        ) : (
          <textarea
            className="rad-external__textarea"
            rows={8}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Findings and impression"
          />
        )}
        {study.hasReport ? (
          <p className="rad-new-study__hint">
            Reported {formatClinicalWhen(study.reportedAt)}
            {study.reportedBy ? ` · ${study.reportedBy}` : ""}
          </p>
        ) : null}
        <div className="rad-new-study__actions">
          <Button disabled={!draft.trim() || savingReport} onClick={() => void saveReport()}>
            {savingReport ? "Saving…" : study.hasReport ? "Update report" : "Save report"}
          </Button>
        </div>
      </Card>

      <Card>
        <SectionHeader
          title="Link to registered patient"
          description="If this person later registers at the hospital, link this imaging history. Studies are not duplicated."
        />
        {linked ? (
          <Alert tone="success" title="Already linked">
            <p>
              Linked {formatClinicalWhen(study.linkedAt)}
              {study.linkedBy ? ` by ${study.linkedBy}` : ""}.
              {" "}
              <button
                type="button"
                className="rad-link"
                onClick={() => openRadiologyPatient(study.linkedPatientUuid || "")}
              >
                Open registered patient imaging history
              </button>
            </p>
          </Alert>
        ) : (
          <div className="rad-new-study">
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
              <ul className="rad-new-study__hits">
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
            <label className="rad-new-study__radio">
              <input
                type="checkbox"
                checked={confirmLink}
                onChange={(event) => setConfirmLink(event.target.checked)}
                disabled={!linkPatient}
              />
              I confirm these imaging studies belong to this registered patient
            </label>
            <div className="rad-new-study__actions">
              <Button disabled={!linkPatient || !confirmLink || linking} onClick={() => void link()}>
                {linking ? "Linking…" : "Link imaging history"}
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
