import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { downloadCertificate, fetchCertificates, saveCertificate } from "../../services/certificates";
import { fetchPatientRecord } from "../../services/patientDirectory";
import { PatientAccountRequestError } from "../../services/patientAccount";
import { searchPatients } from "../../services/openmrs/patients";
import type { BirthCertificateForm, CertificatePatient, DeathCertificateForm } from "../../types/certificates";
import type { PatientRecord } from "../../types/patientDirectory";
import type { PatientSearchHit } from "../../types";
import "./AdminCertificatesWorkspace.css";

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error ? reason.message : fallback;
}

const EMPTY_BIRTH: BirthCertificateForm = {
  certificateId: "",
  referenceNo: "",
  occurredAt: "",
  childName: "",
  gender: "",
  weight: "",
  motherName: "",
  fatherName: "",
  caseId: "",
  address: "",
};

function parentLine(record: PatientRecord): string {
  const name = [record.familyName, record.givenName, record.middleName].filter(Boolean).join(" ").trim();
  if (!name) return record.identifier || "Unnamed patient";
  return record.identifier ? `${name} (${record.identifier})` : name;
}

function parentAddress(record: PatientRecord): string {
  const address = record.address || {};
  return [address.address1, address.address2, address.cityVillage, address.stateProvince]
    .map((part) => (part || "").trim())
    .filter(Boolean)
    .join(", ");
}

function ParentField({
  label,
  value,
  onChange,
  onPickAddress,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onPickAddress: (address: string) => void;
}) {
  const [hits, setHits] = useState<PatientSearchHit[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (value.trim().length < 2) {
      setHits([]);
      return;
    }
    let cancelled = false;
    searchPatients(value)
      .then((rows) => {
        if (!cancelled) setHits(rows);
      })
      .catch(() => {
        if (!cancelled) setHits([]);
      });
    return () => {
      cancelled = true;
    };
  }, [value]);

  const choose = (hit: PatientSearchHit) => {
    setOpen(false);
    setHits([]);
    fetchPatientRecord(hit.uuid)
      .then((record) => {
        onChange(parentLine(record));
        const address = parentAddress(record);
        if (address) onPickAddress(address);
      })
      .catch(() => onChange(hit.display));
  };

  return (
    <label className="certificates__parent">
      {label}
      <input
        value={value}
        placeholder="Type a name, or choose a registered patient"
        onChange={(event) => {
          setOpen(true);
          onChange(event.target.value);
        }}
      />
      {open && hits.length > 0 ? (
        <ul className="certificates__hits">
          {hits.map((hit) => (
            <li key={hit.uuid}>
              <button type="button" onClick={() => choose(hit)}>
                {hit.display}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </label>
  );
}

export function AdminCertificatesWorkspace() {
  const [kind, setKind] = useState<"birth" | "death">("birth");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PatientSearchHit[]>([]);
  const [patient, setPatient] = useState<CertificatePatient | null>(null);
  const [birth, setBirth] = useState<BirthCertificateForm>(EMPTY_BIRTH);
  const [death, setDeath] = useState<DeathCertificateForm | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (kind !== "death" || query.trim().length < 2 || patient) {
      setHits([]);
      return;
    }
    let cancelled = false;
    searchPatients(query)
      .then((rows) => {
        if (!cancelled) setHits(rows);
      })
      .catch(() => {
        if (!cancelled) setHits([]);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, query, patient]);

  const openPatient = (hit: PatientSearchHit) => {
    setLoading(true);
    setError("");
    setNotice("");
    setHits([]);
    setQuery("");
    fetchCertificates(hit.uuid)
      .then((payload) => {
        setPatient(payload.patient);
        setDeath(payload.death);
      })
      .catch((reason) => setError(errorMessage(reason, "The certificate could not be opened.")))
      .finally(() => setLoading(false));
  };

  const persist = () => {
    if (kind === "birth") {
      return saveCertificate({ kind: "birth", ...birth }).then((payload) => {
        if (payload.birth) setBirth(payload.birth);
        setNotice(payload.message || "Birth certificate saved.");
        return payload;
      });
    }
    if (!patient || !death) return Promise.reject(new Error("Choose the patient for this death certificate."));
    return saveCertificate({ patientUuid: patient.uuid, kind, ...death }).then((payload) => {
      setPatient(payload.patient);
      setDeath(payload.death);
      setNotice(payload.message || "Death certificate saved.");
      return payload;
    });
  };

  const save = () => {
    setSaving(true);
    setError("");
    setNotice("");
    persist()
      .catch((reason) => setError(errorMessage(reason, "The certificate could not be saved.")))
      .finally(() => setSaving(false));
  };

  const download = () => {
    setDownloading(true);
    setError("");
    setNotice("");
    persist()
      .then((payload) => {
        if (kind === "birth") {
          const id = payload.birth?.certificateId || "";
          if (!id) throw new Error("Save the birth certificate before downloading it.");
          return downloadCertificate(id, "birth", `${payload.birth?.referenceNo || "birth-certificate"}.pdf`);
        }
        if (!patient) throw new Error("Choose the patient for this death certificate.");
        return downloadCertificate(patient.uuid, "death", `${payload.death?.referenceNo || "death-certificate"}.pdf`);
      })
      .catch((reason) => setError(errorMessage(reason, "The certificate could not be downloaded.")))
      .finally(() => setDownloading(false));
  };

  return (
    <div className="admin-workspace certificates">
      <PageHeader
        title="Birth/Death Certificate"
        description="For a birth, type the child's name. The mother and father can be typed, or chosen from patients already registered. A death certificate is for a registered patient and sets the status to Dead."
      />
      {error ? <Alert tone="danger" title={error} /> : null}
      {notice ? <Alert tone="info" title={notice} /> : null}
      <div className="certificates__kind" role="tablist" aria-label="Certificate type">
        <button type="button" className={kind === "birth" ? "is-active" : ""} onClick={() => setKind("birth")}>
          Birth certificate
        </button>
        <button type="button" className={kind === "death" ? "is-active" : ""} onClick={() => setKind("death")}>
          Death certificate
        </button>
      </div>
      {kind === "death" ? (
        <>
          <label className="certificates__search">
            Patient
            <input
              type="search"
              value={patient ? `${patient.name}${patient.hospitalNumber ? ` · ${patient.hospitalNumber}` : ""}` : query}
              placeholder="Find the patient"
              onChange={(event) => {
                setPatient(null);
                setDeath(null);
                setQuery(event.target.value);
              }}
            />
          </label>
          {hits.length > 0 ? (
            <ul className="certificates__hits">
              {hits.map((hit) => (
                <li key={hit.uuid}>
                  <button type="button" onClick={() => openPatient(hit)}>
                    {hit.display}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {patient ? (
            <p className="certificates__status">
              Patient status: <strong>{patient.status}</strong>
            </p>
          ) : null}
        </>
      ) : null}
      {loading ? <LoadingState variant="board" label="Opening the certificate…" /> : null}
      {kind === "birth" || (patient && death) ? (
        <form
          className="certificates__form"
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          {kind === "birth" ? (
            <div className="certificates__grid">
              <label>
                Reference no.
                <input value={birth.referenceNo} placeholder="Assigned when you save" onChange={(event) => setBirth({ ...birth, referenceNo: event.target.value })} />
              </label>
              <label>
                Birth date
                <input type="datetime-local" required value={birth.occurredAt} onChange={(event) => setBirth({ ...birth, occurredAt: event.target.value })} />
              </label>
              <label>
                Child name
                <input required value={birth.childName} placeholder="Name of the child" onChange={(event) => setBirth({ ...birth, childName: event.target.value })} />
              </label>
              <label>
                Gender
                <select required value={birth.gender} onChange={(event) => setBirth({ ...birth, gender: event.target.value })}>
                  <option value="">Choose</option>
                  <option>Male</option>
                  <option>Female</option>
                </select>
              </label>
              <label>
                Weight (kg)
                <input value={birth.weight} onChange={(event) => setBirth({ ...birth, weight: event.target.value })} />
              </label>
              <ParentField
                label="Mother"
                value={birth.motherName}
                onChange={(motherName) => setBirth((current) => ({ ...current, motherName }))}
                onPickAddress={(address) => setBirth((current) => ({ ...current, address: current.address || address }))}
              />
              <label>
                Case ID
                <input value={birth.caseId} onChange={(event) => setBirth({ ...birth, caseId: event.target.value })} />
              </label>
              <ParentField
                label="Father"
                value={birth.fatherName}
                onChange={(fatherName) => setBirth((current) => ({ ...current, fatherName }))}
                onPickAddress={(address) => setBirth((current) => ({ ...current, address: current.address || address }))}
              />
              <label className="certificates__wide">
                Address
                <input value={birth.address} onChange={(event) => setBirth({ ...birth, address: event.target.value })} />
              </label>
            </div>
          ) : death ? (
            <div className="certificates__grid">
              <label>
                Reference no.
                <input value={death.referenceNo} placeholder="Assigned when you save" onChange={(event) => setDeath({ ...death, referenceNo: event.target.value })} />
              </label>
              <label>
                Death date
                <input type="datetime-local" required value={death.occurredAt} onChange={(event) => setDeath({ ...death, occurredAt: event.target.value })} />
              </label>
              <label>
                Patient name
                <input required value={death.patientName} onChange={(event) => setDeath({ ...death, patientName: event.target.value })} />
              </label>
              <label>
                Case ID
                <input value={death.caseId} onChange={(event) => setDeath({ ...death, caseId: event.target.value })} />
              </label>
              <label>
                Gender
                <select required value={death.gender} onChange={(event) => setDeath({ ...death, gender: event.target.value })}>
                  <option value="">Choose</option>
                  <option>Male</option>
                  <option>Female</option>
                </select>
              </label>
              <label>
                Guardian name
                <input value={death.guardianName} onChange={(event) => setDeath({ ...death, guardianName: event.target.value })} />
              </label>
              <label>
                Address
                <input value={death.address} onChange={(event) => setDeath({ ...death, address: event.target.value })} />
              </label>
              <label>
                Report
                <input value={death.report} onChange={(event) => setDeath({ ...death, report: event.target.value })} />
              </label>
            </div>
          ) : null}
          <div className="certificates__actions">
            <Button type="submit" busy={saving} busyLabel="Saving…">
              Save certificate
            </Button>
            <Button type="button" variant="secondary" busy={downloading} busyLabel="Preparing…" onClick={download}>
              Download PDF
            </Button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
