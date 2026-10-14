import { useEffect, useState } from "react";
import {
  openCreateVisit,
  openPatientRecord,
  returnToPreviousScreen,
  openRegistrationPatient,
  openRegistrationRegister,
} from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { addFamilyMember, fetchHospitalFamily } from "../../services/hospitalFamily";
import { searchPatients } from "../../services/openmrs/patients";
import { RegistrationRequestError } from "../../services/registration";
import type { HospitalFamily, HospitalFamilyMember } from "../../types/hospitalFamily";
import { FAMILY_RELATIONSHIPS, FAMILY_CARD_ISSUED_COPY } from "./hospitalFamilyView";
import "../Admin/AdminWorkspace.css";
import "../PatientDirectory/PatientDirectoryWorkspace.css";
import "./RegistrationDeskWorkspace.css";

interface FamilyDetailWorkspaceProps {
  familyId: string;
}

function errorMessage(reason: unknown): string {
  return reason instanceof RegistrationRequestError || reason instanceof Error
    ? reason.message
    : "This family could not be loaded.";
}

export function FamilyDetailWorkspace({ familyId }: FamilyDetailWorkspaceProps) {
  const [family, setFamily] = useState<HospitalFamily | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [memberQuery, setMemberQuery] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [hits, setHits] = useState<Array<{ uuid: string; display: string }>>([]);
  const [selectedPatient, setSelectedPatient] = useState<{ uuid: string; display: string } | null>(null);
  const [relationship, setRelationship] = useState("Family member");
  const [confirmTransfer, setConfirmTransfer] = useState(false);
  const [linking, setLinking] = useState(false);

  const load = (keepNotice = false) => {
    setLoading(true);
    setError("");
    if (!keepNotice) {
      setNotice("");
    }
    fetchHospitalFamily(familyId)
      .then((payload) => {
        setFamily(payload.family);
      })
      .catch((reason) => {
        setFamily(null);
        setError(errorMessage(reason));
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    load();
  }, [familyId]);

  useEffect(() => {
    if (searchQuery.trim().length < 2) {
      setHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      void searchPatients(searchQuery.trim())
        .then((rows) => setHits(rows.map((row) => ({ uuid: row.uuid, display: row.display }))))
        .catch(() => setHits([]));
    }, 300);
    return () => window.clearTimeout(handle);
  }, [searchQuery]);

  const members = family?.members || [];
  const visibleMembers = members.filter((member) => {
    const needle = memberQuery.trim().toLowerCase();
    if (!needle) {
      return true;
    }
    return `${member.name} ${member.identifier} ${member.relationship}`.toLowerCase().includes(needle);
  });

  const linkExisting = async () => {
    if (!selectedPatient || linking) {
      return;
    }
    setLinking(true);
    setError("");
    try {
      const payload = await addFamilyMember(familyId, {
        patientUuid: selectedPatient.uuid,
        relationship,
        confirmTransfer,
        memberName: selectedPatient.display,
      });
      setFamily(payload.family);
      setSelectedPatient(null);
      setSearchQuery("");
      setHits([]);
      setConfirmTransfer(false);
      setNotice(
        payload.family?.transferred
          ? "This patient was moved to this family. No Family Card fee was created."
          : "This patient was added to the family. No Family Card fee was created.",
      );
    } catch (reason) {
      if (reason instanceof RegistrationRequestError && reason.code === "family_transfer_required") {
        setConfirmTransfer(true);
        setError(reason.message);
      } else {
        setError(errorMessage(reason));
      }
    } finally {
      setLinking(false);
    }
  };

  if (loading) {
    return <LoadingState label="Loading family…" />;
  }

  if (!family) {
    return (
      <div className="reg-patient">
        <div className="reg-patient__nav">
          <Button variant="ghost" onClick={() => returnToPreviousScreen("#/reception/families")}>
            ← Families
          </Button>
        </div>
        <EmptyState title="This family was not found" description={error || "Go back to Families and try again."} />
      </div>
    );
  }

  return (
    <div className="reg-patient">
      <div className="reg-patient__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/reception/families")}>
          ← Families
        </Button>
      </div>
      <PageHeader
        title={family.familyName}
        description="Each person listed here is a separate patient with their own hospital record. The Family Card only groups them."
      />
      {notice ? <Alert tone="success" title={notice} /> : null}
      {error ? <Alert tone="danger" title="Could not update this family">{error}</Alert> : null}

      <Card>
        <SectionHeader title="Family Card" />
        <dl className="reg-patient__facts">
          <div>
            <dt>Family</dt>
            <dd>{family.familyName}</dd>
          </div>
          <div>
            <dt>Family Card</dt>
            <dd>{family.cardNumber}</dd>
          </div>
          <div>
            <dt>Patients</dt>
            <dd>{family.memberCount === 1 ? "1 patient" : `${family.memberCount} patients`}</dd>
          </div>
        </dl>
        <p className="reg-patient__muted">{FAMILY_CARD_ISSUED_COPY}</p>
        <div className="reg-patient__actions">
          <Button onClick={() => openRegistrationRegister(undefined, family.familyId)}>
            Register another family member
          </Button>
        </div>
      </Card>

      <Card>
        <SectionHeader title="Family members" description="Search this family, or open a patient to start a visit." />
        <label className="reg-family-search">
          Find a family member
          <input
            type="search"
            value={memberQuery}
            onChange={(event) => setMemberQuery(event.target.value)}
            placeholder="Name or hospital number"
          />
        </label>
        {visibleMembers.length === 0 ? (
          <p className="reg-patient__muted">No family member matches this search.</p>
        ) : (
          <ul className="reg-form__matches">
            {visibleMembers.map((member: HospitalFamilyMember) => (
              <li key={member.patientUuid}>
                <button
                  type="button"
                  className="reg-link"
                  onClick={() => openPatientRecord(member.patientUuid, "reception")}
                >
                  {member.name || "Unnamed patient"}
                </button>
                <span>
                  {member.identifier ? `${member.identifier} · ` : ""}
                  {member.relationship}
                </span>
                <Button variant="ghost" onClick={() => openCreateVisit(member.patientUuid)}>
                  Create visit
                </Button>
                <Button variant="ghost" onClick={() => openRegistrationPatient(member.patientUuid)}>
                  Open
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <SectionHeader
          title="Add an already registered patient"
          description="Use this only when the person already has a hospital record. Registering a new person stays on Register Patient."
        />
        <div className="reg-form__grid">
          <label>
            Find patient
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => {
                setSearchQuery(event.target.value);
                setSelectedPatient(null);
                setConfirmTransfer(false);
              }}
              placeholder="Name or hospital number"
            />
          </label>
          <label>
            Relationship to this family
            <select value={relationship} onChange={(event) => setRelationship(event.target.value)}>
              {FAMILY_RELATIONSHIPS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
        </div>
        {hits.length ? (
          <ul className="reg-form__matches">
            {hits.map((hit) => (
              <li key={hit.uuid}>
                <button
                  type="button"
                  className="reg-link"
                  onClick={() => {
                    setSelectedPatient(hit);
                    setSearchQuery(hit.display);
                    setHits([]);
                  }}
                >
                  {hit.display}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        {selectedPatient ? (
          <p className="reg-patient__muted">
            Selected: {selectedPatient.display}
            {confirmTransfer ? " This patient is already on another Family Card." : ""}
          </p>
        ) : null}
        <div className="reg-patient__actions">
          <Button onClick={() => void linkExisting()} disabled={!selectedPatient || linking}>
            {confirmTransfer ? "Move to this family" : "Add to this family"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
