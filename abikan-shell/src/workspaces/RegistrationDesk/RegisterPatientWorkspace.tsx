import { useEffect, useMemo, useState } from "react";
import {
  openAntenatalRegistration,
  openCreateVisit,
  openReceptionFamily,
  openRegistrationPatient,
  readRegistrationFamilyId,
  returnToPreviousScreen,
  setShellRoute,
} from "../../app/hashRoute";
import { rememberCardType } from "../../config/registrationCharges";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { IconWell } from "../../components/IconWell";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { fetchHospitalFamily, searchHospitalFamilies } from "../../services/hospitalFamily";
import { searchPatients } from "../../services/openmrs/patients";
import {
  createRegistrationPatient,
  emptyRegistrationDraft,
  fetchRegistrationMetadata,
  fetchRegistrationProfile,
  RegistrationRequestError,
  updateRegistrationPatient,
} from "../../services/registration";
import type { FamilyRegistrationMode, HospitalFamily } from "../../types/hospitalFamily";
import type { RegistrationCardType } from "../../types/registration";
import type {
  RegistrationMatch,
  RegistrationMetadata,
  RegistrationPatientDraft,
} from "../../types/registration";
import {
  EXISTING_FAMILY_NO_FEE_COPY,
  FAMILY_RELATIONSHIPS,
  NEW_FAMILY_FEE_COPY,
  cardTypeForMode,
  defaultHouseholdName,
  familySummary,
} from "./hospitalFamilyView";
import "./RegistrationDeskWorkspace.css";

interface RegisterPatientWorkspaceProps {
  patientUuid: string | null;
  /** antenatal = dedicated new-patient path from Antenatal Care (not general Reception register). */
  purpose?: "hospital" | "antenatal";
}

function draftFromProfile(
  profile: {
    givenName: string;
    middleName: string;
    familyName: string;
    gender: string;
    birthdate: string;
    birthdateEstimated: boolean;
    attributes: Record<string, string>;
    address: Record<string, string>;
    nhis?: boolean;
  },
): RegistrationPatientDraft {
  const gender = profile.gender === "M" || profile.gender === "F" || profile.gender === "O" ? profile.gender : "";
  return {
    ...emptyRegistrationDraft(),
    givenName: profile.givenName,
    middleName: profile.middleName,
    familyName: profile.familyName,
    gender,
    birthdate: profile.birthdate,
    birthdateEstimated: profile.birthdateEstimated,
    attributes: { ...profile.attributes },
    address: { ...profile.address },
    nhis: Boolean(profile.nhis),
  };
}

export function RegisterPatientWorkspace({
  patientUuid,
  purpose = "hospital",
}: RegisterPatientWorkspaceProps) {
  const editing = Boolean(patientUuid);
  const antenatalPurpose = purpose === "antenatal" && !editing;
  const [meta, setMeta] = useState<RegistrationMetadata | null>(null);
  const [draft, setDraft] = useState<RegistrationPatientDraft>(() => ({
    ...emptyRegistrationDraft(),
    gender: antenatalPurpose ? "F" : "",
  }));
  const [cardType, setCardType] = useState<RegistrationCardType>("individual");
  const [familyMode, setFamilyMode] = useState<FamilyRegistrationMode>("none");
  const [selectedFamily, setSelectedFamily] = useState<HospitalFamily | null>(null);
  const [familyQuery, setFamilyQuery] = useState("");
  const [familyHits, setFamilyHits] = useState<HospitalFamily[]>([]);
  const [similarFamilies, setSimilarFamilies] = useState<HospitalFamily[]>([]);
  const [confirmCreateFamily, setConfirmCreateFamily] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [matches, setMatches] = useState<RegistrationMatch[]>([]);
  const [liveMatches, setLiveMatches] = useState<RegistrationMatch[]>([]);

  const chooseMode = (mode: FamilyRegistrationMode) => {
    setFamilyMode(mode);
    const nextCard = cardTypeForMode(mode);
    setCardType(nextCard);
    rememberCardType(nextCard);
    setConfirmCreateFamily(false);
    setSimilarFamilies([]);
    setDraft((current) => ({
      ...current,
      familyMode: mode,
      familyId: mode === "existing" ? current.familyId : "",
      householdName:
        mode === "new" && !current.householdName.trim()
          ? defaultHouseholdName(current.familyName)
          : current.householdName,
    }));
    if (mode !== "existing") {
      setSelectedFamily(null);
    }
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotice(null);
    const stored = sessionStorage.getItem("abikan.registration.cardType");
    if (!antenatalPurpose && (stored === "family" || stored === "individual")) {
      setCardType(stored);
    }
    if (antenatalPurpose) {
      setCardType("individual");
      setFamilyMode("none");
      rememberCardType("individual");
    }
    const presetFamilyId = antenatalPurpose ? null : readRegistrationFamilyId();
    Promise.all([
      fetchRegistrationMetadata(),
      patientUuid ? fetchRegistrationProfile(patientUuid) : Promise.resolve(null),
      !patientUuid && presetFamilyId ? fetchHospitalFamily(presetFamilyId).catch(() => null) : Promise.resolve(null),
    ])
      .then(([nextMeta, profile, presetFamily]) => {
        if (cancelled) {
          return;
        }
        setMeta(nextMeta);
        if (profile) {
          setDraft(draftFromProfile(profile));
        }
        if (presetFamily?.family) {
          setFamilyMode("existing");
          setCardType("family");
          rememberCardType("family");
          setSelectedFamily(presetFamily.family);
          setDraft((current) => ({
            ...current,
            familyMode: "existing",
            familyId: presetFamily.family?.familyId || "",
          }));
        } else if (!antenatalPurpose && stored === "family") {
          setFamilyMode("new");
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Registration could not be loaded.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [patientUuid, antenatalPurpose]);

  useEffect(() => {
    const query = `${draft.givenName} ${draft.familyName}`.trim();
    if (editing || query.length < 3) {
      setLiveMatches([]);
      return;
    }
    const handle = window.setTimeout(() => {
      void searchPatients(query)
        .then((hits) => {
          setLiveMatches(
            hits.map((hit) => ({
              uuid: hit.uuid,
              display: hit.display,
              name: hit.display,
              mrn: "",
              age: "",
              sex: "",
            })),
          );
        })
        .catch(() => setLiveMatches([]));
    }, 300);
    return () => window.clearTimeout(handle);
  }, [draft.givenName, draft.familyName, editing]);

  useEffect(() => {
    if (editing || familyMode !== "existing") {
      setFamilyHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      void searchHospitalFamilies(familyQuery.trim())
        .then((payload) => setFamilyHits(payload.families || []))
        .catch(() => setFamilyHits([]));
    }, 300);
    return () => window.clearTimeout(handle);
  }, [familyQuery, familyMode, editing]);

  const phoneField = useMemo(
    () => meta?.personAttributes.find((field) => field.name === "phoneNumber"),
    [meta],
  );

  const update = <K extends keyof RegistrationPatientDraft>(key: K, value: RegistrationPatientDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const save = async (confirmDuplicate = false, createFamilyAnyway = false) => {
    if (saving) {
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    rememberCardType(cardType);
    try {
      if (editing && patientUuid) {
        const updated = await updateRegistrationPatient(patientUuid, draft);
        setDraft(draftFromProfile(updated));
        setNotice("Patient updated successfully.");
        return;
      }
      if (familyMode === "existing" && !draft.familyId) {
        setError("Select an existing family before registering this patient.");
        return;
      }
      if (familyMode === "new" && !draft.householdName.trim() && !defaultHouseholdName(draft.familyName)) {
        setError("Enter a family name for the new Family Card.");
        return;
      }
      const effectiveMode: FamilyRegistrationMode = antenatalPurpose ? "none" : familyMode;
      const effectiveCard: RegistrationCardType = antenatalPurpose ? "individual" : cardType;
      const payload = {
        ...draft,
        cardType: effectiveCard,
        familyMode: effectiveMode,
        familyId: effectiveMode === "existing" ? draft.familyId : "",
        householdName:
          effectiveMode === "new"
            ? draft.householdName.trim() || defaultHouseholdName(draft.familyName)
            : "",
        attributes: {
          ...draft.attributes,
          cardType: effectiveCard,
        },
      };
      const created = await createRegistrationPatient(payload, {
        confirmDuplicate,
        confirmCreateFamily: confirmCreateFamily || createFamilyAnyway,
      });
      if (created.uuid) {
        sessionStorage.setItem("abikan.registration.cardType", effectiveCard);
        if (antenatalPurpose) {
          openAntenatalRegistration(created.uuid);
        } else {
          openRegistrationPatient(created.uuid);
        }
      }
    } catch (reason) {
      if (reason instanceof RegistrationRequestError && reason.code === "possible_duplicate") {
        setMatches(reason.matches);
        setError(reason.message);
      } else if (reason instanceof RegistrationRequestError && reason.code === "family_exists") {
        setSimilarFamilies(reason.families);
        setError(reason.message);
      } else {
        setError(reason instanceof Error ? reason.message : "The patient could not be registered.");
      }
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <LoadingState label={editing ? "Loading patient…" : "Loading registration…"} />;
  }

  if (!meta) {
    return (
      <EmptyState
        title="Unable to load registration"
        description={error || "Refresh and try again."}
      />
    );
  }

  return (
    <div className="reg-patient">
      <div className="reg-patient__nav">
        <Button
          variant="ghost"
          onClick={() =>
            returnToPreviousScreen(antenatalPurpose ? "#/reception/antenatal" : "#/reception")
          }
        >
          {antenatalPurpose ? "← Antenatal Care" : "← Reception"}
        </Button>
      </div>
      <PageHeader
        title={
          editing ? "Edit patient" : antenatalPurpose ? "Register antenatal patient" : "Register Patient"
        }
        description={
          editing
            ? "Update the details already stored for this patient."
            : antenatalPurpose
              ? "Create the hospital record for a new antenatal patient. After save, continue to the ANC card. This does not use the Family Card registration screen."
              : undefined
        }
      />
      {notice ? <Alert tone="success" title={notice} /> : null}
      {error ? (
        <Alert
          tone="danger"
          title={
            matches.length
              ? "Similar patients found"
              : similarFamilies.length
                ? "A family with this name already exists"
                : "Could not save"
          }
        >
          {error}
        </Alert>
      ) : null}

      {!editing && (matches.length > 0 || liveMatches.length > 0) ? (
        <Card>
          <SectionHeader
            title="Existing patients"
            description={
              antenatalPurpose
                ? "This person is already registered. Open Antenatal Care instead of creating another hospital record."
                : "This person is already registered. Create a visit instead of registering again."
            }
          />
          <ul className="reg-form__matches">
            {(matches.length ? matches : liveMatches).map((match) => (
              <li key={match.uuid}>
                <button
                  type="button"
                  className="reg-link"
                  onClick={() =>
                    antenatalPurpose
                      ? openAntenatalRegistration(match.uuid)
                      : openCreateVisit(match.uuid)
                  }
                >
                  {match.display || match.name}
                </button>
                {match.mrn ? <span>{match.mrn}</span> : null}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <form
        className="reg-form"
        onSubmit={(event) => {
          event.preventDefault();
          void save(false);
        }}
      >
        {!editing && antenatalPurpose ? (
          <Card>
            <SectionHeader
              title="Antenatal registration"
              description="This creates a normal hospital patient with an Individual Card, then opens the ANC card for this pregnancy. Family registration is not used here."
            />
            <p className="reg-patient__muted">
              After you save, continue on the antenatal screen to create the ANC card and one-time fee.
              Starting an ANC visit remains a separate step.
            </p>
          </Card>
        ) : null}

        {!editing && !antenatalPurpose ? (
          <Card>
            <div className="reg-form__cards reg-form__cards--three reg-form__cards--choice" role="radiogroup" aria-label="Hospital card">
              <label className={familyMode === "none" ? "is-selected" : ""}>
                <input
                  type="radio"
                  name="familyMode"
                  checked={familyMode === "none"}
                  onChange={() => chooseMode("none")}
                />
                <IconWell name="user" tone="registration" size="md" />
                <strong>Individual Card</strong>
                <span>Own hospital card</span>
              </label>
              <label className={familyMode === "existing" ? "is-selected" : ""}>
                <input
                  type="radio"
                  name="familyMode"
                  checked={familyMode === "existing"}
                  onChange={() => chooseMode("existing")}
                />
                <IconWell name="users" tone="visits" size="md" />
                <strong>Existing Family</strong>
                <span>Join a family card</span>
              </label>
              <label className={familyMode === "new" ? "is-selected" : ""}>
                <input
                  type="radio"
                  name="familyMode"
                  checked={familyMode === "new"}
                  onChange={() => chooseMode("new")}
                />
                <IconWell name="userPlus" tone="appointments" size="md" />
                <strong>New Family</strong>
                <span>Start a family card</span>
              </label>
            </div>

            {familyMode === "existing" ? (
              <div className="reg-family-panel">
                <label className="reg-family-search">
                  Search family, card, or member
                  <input
                    type="search"
                    value={familyQuery}
                    onChange={(event) => setFamilyQuery(event.target.value)}
                    placeholder="Lukman, FAM-001, or Ade Lukman"
                  />
                </label>
                {familyHits.length ? (
                  <ul className="reg-form__matches">
                    {familyHits.map((family) => (
                      <li key={family.familyId}>
                        <button
                          type="button"
                          className="reg-link"
                          onClick={() => {
                            setSelectedFamily(family);
                            update("familyId", family.familyId);
                            update("familyMode", "existing");
                          }}
                        >
                          {familySummary(family)}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : familyQuery.trim() ? (
                  <p className="reg-patient__muted">
                    No family matches this search. Create a new family instead of another Family Card.
                  </p>
                ) : (
                  <p className="reg-patient__muted">Search by family name, Family Card number, or a family member.</p>
                )}
                {selectedFamily ? (
                  <div className="reg-family-selected">
                    <SectionHeader title="Selected family" />
                    <dl className="reg-patient__facts">
                      <div>
                        <dt>Family</dt>
                        <dd>{selectedFamily.familyName}</dd>
                      </div>
                      <div>
                        <dt>Family Card</dt>
                        <dd>{selectedFamily.cardNumber}</dd>
                      </div>
                      <div>
                        <dt>Members</dt>
                        <dd>
                          {selectedFamily.memberCount === 1
                            ? "1 patient"
                            : `${selectedFamily.memberCount} patients`}
                        </dd>
                      </div>
                    </dl>
                    <p className="reg-patient__muted">{EXISTING_FAMILY_NO_FEE_COPY}</p>
                    <Button variant="ghost" onClick={() => openReceptionFamily(selectedFamily.familyId)}>
                      View this family
                    </Button>
                  </div>
                ) : null}
                <label>
                  Relationship to this family
                  <select
                    value={draft.familyRelationship}
                    onChange={(event) => update("familyRelationship", event.target.value)}
                  >
                    {FAMILY_RELATIONSHIPS.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            ) : null}

            {familyMode === "new" ? (
              <div className="reg-family-panel">
                <div className="reg-form__grid">
                  <label>
                    Family name
                    <input
                      required
                      value={draft.householdName}
                      onChange={(event) => update("householdName", event.target.value)}
                      placeholder={defaultHouseholdName(draft.familyName) || "Ibrahim Family"}
                    />
                  </label>
                  <label>
                    Relationship
                    <select
                      value={draft.familyRelationship}
                      onChange={(event) => update("familyRelationship", event.target.value)}
                    >
                      {FAMILY_RELATIONSHIPS.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <p className="reg-patient__muted">{NEW_FAMILY_FEE_COPY}</p>
                {similarFamilies.length ? (
                  <div>
                    <SectionHeader
                      title="A family with this name already exists"
                      description="Use the existing Family Card unless you are sure this is a different family."
                    />
                    <ul className="reg-form__matches">
                      {similarFamilies.map((family) => (
                        <li key={family.familyId}>
                          <button
                            type="button"
                            className="reg-link"
                            onClick={() => {
                              chooseMode("existing");
                              setSelectedFamily(family);
                              update("familyId", family.familyId);
                            }}
                          >
                            {familySummary(family)}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}
          </Card>
        ) : null}

        <Card>
          <SectionHeader title="Patient details" />
          <div className="reg-form__grid">
            <label>
              First name
              <input
                required
                value={draft.givenName}
                onChange={(event) => update("givenName", event.target.value)}
              />
            </label>
            <label>
              Middle name
              <input
                value={draft.middleName}
                onChange={(event) => update("middleName", event.target.value)}
              />
            </label>
            <label>
              Last name
              <input
                required
                value={draft.familyName}
                onChange={(event) => update("familyName", event.target.value)}
              />
            </label>
            <label>
              Sex
              <select
                required
                value={draft.gender}
                onChange={(event) => update("gender", event.target.value as RegistrationPatientDraft["gender"])}
              >
                <option value="">Select</option>
                <option value="M">Male</option>
                <option value="F">Female</option>
                <option value="O">Other</option>
              </select>
            </label>
            <label>
              Date of birth
              <input
                type="date"
                value={draft.birthdate}
                onChange={(event) => update("birthdate", event.target.value)}
              />
            </label>
            <label>
              Age in years
              <input
                inputMode="numeric"
                value={draft.age}
                onChange={(event) => update("age", event.target.value)}
                placeholder="If date of birth is unknown"
              />
            </label>
            <label className="reg-form__check">
              <input
                type="checkbox"
                checked={draft.birthdateEstimated}
                onChange={(event) => update("birthdateEstimated", event.target.checked)}
              />
              Date of birth is estimated
            </label>
            <label className="reg-form__check">
              <input
                type="checkbox"
                checked={draft.nhis}
                onChange={(event) => update("nhis", event.target.checked)}
              />
              NHIS patient
            </label>
          </div>
        </Card>

        {meta.personAttributes.length ? (
          <Card>
            <SectionHeader
              title="Contact"
              description={
                phoneField?.searchable
                  ? "Phone can be used in search when a number is stored."
                  : undefined
              }
            />
            <div className="reg-form__grid">
              {meta.personAttributes
                .filter((field) => field.name !== "cardType")
                .map((field) => (
                <label key={field.uuid}>
                  {field.label}
                  <input
                    value={draft.attributes[field.name] || ""}
                    onChange={(event) =>
                      update("attributes", { ...draft.attributes, [field.name]: event.target.value })
                    }
                  />
                </label>
              ))}
            </div>
          </Card>
        ) : null}

        <Card>
          <SectionHeader title="Address" />
          <div className="reg-form__grid">
            {meta.addressFields.map((field) => (
              <label key={field.name}>
                {field.label}
                <input
                  value={draft.address[field.name] || ""}
                  onChange={(event) =>
                    update("address", { ...draft.address, [field.name]: event.target.value })
                  }
                />
              </label>
            ))}
          </div>
        </Card>

        {meta.identifier.otherTypes.length ? (
          <Card>
            <SectionHeader title="Other identifiers" description="The hospital number is created automatically when you save." />
            <div className="reg-form__grid">
              {meta.identifier.otherTypes.map((ident) => {
                const current = draft.otherIdentifiers.find((row) => row.identifierType === ident.uuid)?.identifier || "";
                return (
                  <label key={ident.uuid}>
                    {ident.name}
                    <input
                      value={current}
                      onChange={(event) => {
                        const next = draft.otherIdentifiers.filter((row) => row.identifierType !== ident.uuid);
                        if (event.target.value.trim()) {
                          next.push({ identifierType: ident.uuid, identifier: event.target.value });
                        }
                        update("otherIdentifiers", next);
                      }}
                    />
                  </label>
                );
              })}
            </div>
          </Card>
        ) : null}

        {meta.relationshipTypes.length ? (
          <Card>
            <SectionHeader title="Next of kin" />
            <div className="reg-form__grid">
              <label>
                First name
                <input
                  value={draft.nextOfKin.givenName}
                  onChange={(event) =>
                    update("nextOfKin", { ...draft.nextOfKin, givenName: event.target.value })
                  }
                />
              </label>
              <label>
                Last name
                <input
                  value={draft.nextOfKin.familyName}
                  onChange={(event) =>
                    update("nextOfKin", { ...draft.nextOfKin, familyName: event.target.value })
                  }
                />
              </label>
              <label>
                Relationship
                <select
                  value={draft.nextOfKin.relationshipType}
                  onChange={(event) =>
                    update("nextOfKin", { ...draft.nextOfKin, relationshipType: event.target.value })
                  }
                >
                  <option value="">Select</option>
                  {meta.relationshipTypes.map((type) => (
                    <option key={type.uuid} value={type.uuid}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </Card>
        ) : null}

        <p className="reg-patient__muted">
          Hospital number is assigned when the patient is saved. Hospital EMR does not create its own numbers.
        </p>
        <div className="reg-patient__actions">
          <Button type="submit" busy={saving} busyLabel={editing ? "Saving…" : "Registering…"}>
            {editing
              ? "Save changes"
              : antenatalPurpose
                ? "Register & continue to ANC"
                : familyMode === "existing"
                  ? "Register Patient Under This Family"
                  : familyMode === "new"
                    ? "Create Family & Register Patient"
                    : "Register patient"}
          </Button>
          {matches.length ? (
            <Button
              type="button"
              variant="secondary"
              disabled={saving}
              onClick={() => void save(true)}
            >
              Register anyway
            </Button>
          ) : null}
          {similarFamilies.length && !antenatalPurpose ? (
            <Button
              type="button"
              variant="secondary"
              disabled={saving}
              onClick={() => {
                setConfirmCreateFamily(true);
                void save(false, true);
              }}
            >
              Create a different family
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              antenatalPurpose ? openAntenatalRegistration() : setShellRoute("registration-desk")
            }
          >
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}
