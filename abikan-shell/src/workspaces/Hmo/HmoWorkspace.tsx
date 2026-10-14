import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { searchPatients } from "../../services/openmrs/patients";
import { assignHmoPatient, fetchHmoAssignments, fetchHmoMetadata } from "../../services/hmo";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { HmoAssignment } from "../../types/hmo";
import type { PatientSearchHit } from "../../types";
import "./HmoWorkspace.css";

interface HmoWorkspaceProps {
  canManage: boolean;
}

function message(reason: unknown, fallback: string): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : fallback;
}

export function HmoWorkspace({ canManage }: HmoWorkspaceProps) {
  const [assignments, setAssignments] = useState<HmoAssignment[]>([]);
  const [schemes, setSchemes] = useState<Record<string, string[]>>({});
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [patientQuery, setPatientQuery] = useState("");
  const [patientHits, setPatientHits] = useState<PatientSearchHit[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<PatientSearchHit | null>(null);
  const [scheme, setScheme] = useState("");
  const [body, setBody] = useState("");
  const [openAdd, setOpenAdd] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = () => {
    setLoading(true);
    Promise.all([fetchHmoAssignments(submittedQuery), fetchHmoMetadata()])
      .then(([list, metadata]) => {
        setAssignments(list.assignments);
        setSchemes(metadata.schemes);
        setError("");
      })
      .catch((reason) => setError(message(reason, "The HMO list could not be loaded.")))
      .finally(() => setLoading(false));
  };

  useEffect(load, [submittedQuery]);

  useEffect(() => {
    if (patientQuery.trim().length < 2) {
      setPatientHits([]);
      return;
    }
    let cancelled = false;
    searchPatients(patientQuery)
      .then((hits) => {
        if (!cancelled) setPatientHits(hits);
      })
      .catch(() => {
        if (!cancelled) setPatientHits([]);
      });
    return () => {
      cancelled = true;
    };
  }, [patientQuery]);

  const closeAdd = () => {
    setOpenAdd(false);
    setPatientQuery("");
    setPatientHits([]);
    setSelectedPatient(null);
    setScheme("");
    setBody("");
  };

  const save = async () => {
    if (!selectedPatient || !scheme || !body) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await assignHmoPatient({ patientUuid: selectedPatient.uuid, scheme, body });
      setNotice(`${selectedPatient.display} was added to the HMO list.`);
      closeAdd();
      load();
    } catch (reason) {
      setError(message(reason, "The patient could not be added to the HMO list."));
    } finally {
      setSaving(false);
    }
  };

  const schemeBodies = schemes[scheme] || [];

  return (
    <div className="hmo-workspace">
      <PageHeader
        title="HMO patients"
        description="See patients covered by NHIA or a private HMO and the body responsible for their care."
      />
      {error ? <Alert tone="danger" title={error} /> : null}
      {notice ? <Alert tone="success" title={notice} /> : null}

      <Card>
        <div className="hmo-workspace__toolbar">
          <label>
            Find HMO patient
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") setSubmittedQuery(query);
              }}
              placeholder="Name, hospital number, or HMO body"
            />
          </label>
          <Button onClick={() => setSubmittedQuery(query)}>Find</Button>
          {canManage ? <Button onClick={() => setOpenAdd(true)}>Add patient</Button> : null}
        </div>
      </Card>

      <Card>
        <SectionHeader
          title="Patients on the HMO list"
          description={`${assignments.length} patient${assignments.length === 1 ? "" : "s"} currently listed.`}
        />
        {loading ? <p className="hmo-workspace__loading">Loading HMO patients…</p> : null}
        {!loading && assignments.length === 0 ? (
          <EmptyState
            title="No HMO patients yet"
            description={canManage ? "Use Add patient to place an existing patient on the list." : "Reception will add patients to this list."}
          />
        ) : null}
        {!loading && assignments.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Patient</th>
                  <th>Hospital number</th>
                  <th>Type</th>
                  <th>HMO body</th>
                </tr>
              </thead>
              <tbody>
                {assignments.map((assignment) => (
                  <tr key={assignment.patientUuid}>
                    <td>{assignment.patientName}</td>
                    <td>{assignment.hospitalNumber}</td>
                    <td><Badge tone={assignment.scheme === "NHIA" ? "info" : "warning"}>{assignment.scheme}</Badge></td>
                    <td>{assignment.body}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>

      {openAdd ? (
        <div className="hmo-workspace__backdrop" role="dialog" aria-modal="true" aria-labelledby="hmo-add-title">
          <div className="hmo-workspace__modal">
            <div className="hmo-workspace__modal-heading">
              <div>
                <h2 id="hmo-add-title">Add patient to HMO list</h2>
                <p>Choose an existing patient, then select the coverage type and HMO body.</p>
              </div>
              <button type="button" onClick={closeAdd} disabled={saving}>Close</button>
            </div>
            <label>
              Patient
              {selectedPatient ? (
                <div className="hmo-workspace__selected">
                  <span>{selectedPatient.display}</span>
                  <button type="button" onClick={() => setSelectedPatient(null)} disabled={saving}>Change</button>
                </div>
              ) : (
                <>
                  <input
                    value={patientQuery}
                    onChange={(event) => setPatientQuery(event.target.value)}
                    placeholder="Search by name or hospital number"
                    autoFocus
                  />
                  {patientHits.length > 0 ? (
                    <ul className="hmo-workspace__patient-hits">
                      {patientHits.map((hit) => (
                        <li key={hit.uuid}>
                          <button type="button" onClick={() => { setSelectedPatient(hit); setPatientHits([]); }}>
                            {hit.display}
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </>
              )}
            </label>
            <label>
              Coverage type
              <select value={scheme} onChange={(event) => { setScheme(event.target.value); setBody(""); }} disabled={!selectedPatient || saving}>
                <option value="">Choose coverage type</option>
                {Object.keys(schemes).map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
            <label>
              HMO body
              <select value={body} onChange={(event) => setBody(event.target.value)} disabled={!scheme || saving}>
                <option value="">Choose HMO body</option>
                {schemeBodies.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </label>
            <div className="hmo-workspace__actions">
              <Button onClick={closeAdd} disabled={saving}>Cancel</Button>
              <Button onClick={() => void save()} disabled={saving || !selectedPatient || !scheme || !body}>
                {saving ? "Saving…" : "Add to HMO list"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
