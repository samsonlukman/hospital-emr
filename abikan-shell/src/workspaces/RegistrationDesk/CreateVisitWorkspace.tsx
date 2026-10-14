import { useEffect, useMemo, useState } from "react";
import {
  openCreateVisit,
  openRegistrationRegister,
  returnToPreviousScreen,
  setShellRoute,
} from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import { SectionHeader } from "../../components/SectionHeader";
import {
  RECEPTION_VISIT_TYPE_COPY,
  isGeneralReceptionVisitType,
  receptionLocationChoiceMode,
  receptionVisitTypeLabel,
} from "../../config/receptionVisitTypes";
import { fetchPatientIdentity, fetchPatientVisits } from "../../services/openmrs/clinicalPatient";
import { searchPatients } from "../../services/openmrs/patients";
import {
  closeRegistrationVisit,
  fetchRegistrationVisitContext,
  newRegistrationRequestId,
  startRegistrationVisit,
} from "../../services/registration";
import type { PatientIdentity, PatientSearchHit, PatientVisitSummary } from "../../types";
import type { RegistrationVisitContext, RegistrationVisitTypeOption } from "../../types/registration";
import { MISSING_DAILY_VISIT_NUMBER, formatDailyVisitNumber } from "../../utils/dailyVisitNumber";
import {
  CLOSE_VISIT_CONFIRM_COPY,
  CLOSE_VISIT_CONFIRM_TITLE,
  CLOSE_VISIT_LABEL,
  CLOSING_VISIT_LABEL,
  CONTINUE_EXISTING_VISIT_LABEL,
  CREATE_VISIT_NO_CARD_COPY,
  VISIT_ALREADY_OPEN_MESSAGE,
  VISIT_CLOSED_SUCCESS_MESSAGE,
  canCloseOutpatientVisit,
  existingVisitNotice,
  outpatientVisitStatus,
  readStartVisitResult,
  shouldOfferStartVisit,
} from "./receptionVisit";
import "./RegistrationDeskWorkspace.css";

interface CreateVisitWorkspaceProps {
  patientUuid: string | null;
}

export function CreateVisitWorkspace({ patientUuid }: CreateVisitWorkspaceProps) {
  if (!patientUuid) {
    return <CreateVisitSearch />;
  }
  return <CreateVisitPatient key={patientUuid} patientUuid={patientUuid} />;
}

function CreateVisitSearch() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PatientSearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setHits([]);
      setSearching(false);
      return;
    }
    setSearching(false);
    const handle = window.setTimeout(() => {
      setSearching(true);
      void searchPatients(term)
        .then((results) => {
          setHits(results);
          setError(null);
        })
        .catch((reason) => {
          setHits([]);
          setError(reason instanceof Error ? reason.message : "Patients could not be searched.");
        })
        .finally(() => setSearching(false));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [query]);

  const searched = query.trim().length >= 2;

  return (
    <div className="reg-patient">
      <div className="reg-patient__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/reception")}>
          ← Reception
        </Button>
      </div>
      <PageHeader
        title="Create Visit"
        description="Find a patient who is already registered, then start or continue their visit. No hospital card fee is created here."
      />
      <Card>
        <SectionHeader title="Find the patient" description="Search by name, hospital number, or phone." />
        <label className="reg-form__grid">
          Patient
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Name, hospital number, or phone"
            autoFocus
          />
        </label>
        {searching ? <LoadingState variant="inline" label="Searching…" /> : null}
        {error ? (
          <Alert tone="danger" title="Search could not be completed">
            {error}
          </Alert>
        ) : null}
        {searched && !searching && hits.length === 0 && !error ? (
          <EmptyState
            title="No matching patient"
            description="Do not register a new patient from this screen. If this person has never been registered, use Register Patient."
          />
        ) : null}
        {hits.length > 0 ? (
          <ul className="reg-form__matches">
            {hits.map((hit) => (
              <li key={hit.uuid}>
                <button type="button" className="reg-link" onClick={() => openCreateVisit(hit.uuid)}>
                  {hit.display}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <div className="reg-patient__actions">
          <Button variant="ghost" onClick={() => openRegistrationRegister()}>
            Register a new patient
          </Button>
        </div>
      </Card>
    </div>
  );
}

function CreateVisitPatient({ patientUuid }: { patientUuid: string }) {
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [visits, setVisits] = useState<PatientVisitSummary[]>([]);
  const [context, setContext] = useState<RegistrationVisitContext | null>(null);
  const [visitTypes, setVisitTypes] = useState<RegistrationVisitTypeOption[]>([]);
  const [visitTypeUuid, setVisitTypeUuid] = useState("");
  const [locationUuid, setLocationUuid] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startingVisit, setStartingVisit] = useState(false);
  const [closingVisit, setClosingVisit] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [closeError, setCloseError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [visitNumberNotice, setVisitNumberNotice] = useState<string | null>(null);
  const [visitRequestId, setVisitRequestId] = useState(newRegistrationRequestId);
  const [continued, setContinued] = useState(false);

  const selectedType = useMemo(
    () => visitTypes.find((item) => item.uuid === visitTypeUuid) || visitTypes[0] || null,
    [visitTypes, visitTypeUuid],
  );
  const locationOptions = selectedType?.locations || [];
  const locationMode = receptionLocationChoiceMode(selectedType?.name, locationOptions.length);
  const resolvedLocationUuid =
    locationMode === "auto"
      ? selectedType?.defaultLocationUuid || locationOptions[0]?.uuid || ""
      : locationUuid;
  const canSubmitVisit =
    Boolean(visitTypeUuid) && locationMode !== "none" && (locationMode === "auto" || Boolean(locationUuid));

  const load = (keepNotice = false) => {
    setLoading(true);
    setError(null);
    if (!keepNotice) {
      setNotice(null);
      setVisitNumberNotice(null);
      setContinued(false);
    }
    Promise.allSettled([
      fetchPatientIdentity(patientUuid),
      fetchPatientVisits(patientUuid),
      fetchRegistrationVisitContext(patientUuid),
    ]).then(([identity, visitResult, contextResult]) => {
      if (identity.status === "fulfilled") {
        setPatient(identity.value);
      } else {
        setError(
          identity.reason instanceof Error ? identity.reason.message : "Unable to load this patient.",
        );
      }
      if (visitResult.status === "fulfilled") {
        setVisits(visitResult.value.filter((visit) => visit.uuid));
      }
      if (contextResult.status === "fulfilled") {
        setContext(contextResult.value);
        const types = (contextResult.value.visitTypes || []).filter((item) =>
          isGeneralReceptionVisitType(item.name),
        );
        setVisitTypes(types);
        const initial = types.find((item) => item.name === "OPD") || types[0];
        if (initial) {
          setVisitTypeUuid((current) => {
            if (current && types.some((item) => item.uuid === current)) {
              return current;
            }
            return initial.uuid;
          });
          const mode = receptionLocationChoiceMode(initial.name, initial.locations.length);
          setLocationUuid((current) => {
            if (current) {
              return current;
            }
            return mode === "auto" ? initial.defaultLocationUuid || initial.locations[0]?.uuid || "" : "";
          });
        } else {
          setVisitTypeUuid("");
        }
      } else {
        setContext(null);
      }
      setLoading(false);
    });
  };

  useEffect(() => {
    load();
    setVisitRequestId(newRegistrationRequestId());
  }, [patientUuid]);

  const openVisit =
    visits.find((visit) => visit.open) ||
    (context?.visit?.open && context.visit.uuid
      ? {
          uuid: context.visit.uuid,
          start: "",
          startDate: "",
          startDatetime: context.visit.startDatetime,
          stop: null,
          visitType: context.visit.visitType,
          location: context.visit.location,
          open: true,
          dailyVisitNumber: "",
          attendedBy: "",
        }
      : undefined);
  const admissionActive = Boolean(context?.admissionActive);
  const offerStart = shouldOfferStartVisit({ openVisit, admissionActive });
  const visitStatus = openVisit
    ? outpatientVisitStatus({
        open: openVisit.open,
        stop: openVisit.stop,
        attendedBy: openVisit.attendedBy,
      })
    : null;
  const offerClose = canCloseOutpatientVisit({
    visit: openVisit,
    admissionActive,
    patientUuid,
    visitPatientUuid: patientUuid,
  });
  const visitNotice =
    context?.message || existingVisitNotice({ openVisit, admissionActive });

  const startVisit = async () => {
    if (startingVisit || !canSubmitVisit || !resolvedLocationUuid) {
      return;
    }
    setStartingVisit(true);
    setError(null);
    setNotice(null);
    try {
      const started = readStartVisitResult(
        await startRegistrationVisit(
          patientUuid,
          visitTypeUuid,
          resolvedLocationUuid,
          visitRequestId,
          selectedType?.name,
        ),
      );
      const number = formatDailyVisitNumber(started.visit.dailyVisitNumber);
      setNotice(started.message);
      setVisitNumberNotice(number === MISSING_DAILY_VISIT_NUMBER ? null : `Visit number: ${number}`);
      setVisitRequestId(newRegistrationRequestId());
      load(true);
    } catch (reason) {
      setNotice(null);
      setVisitNumberNotice(null);
      setError(reason instanceof Error ? reason.message : "The visit could not be started.");
    } finally {
      setStartingVisit(false);
    }
  };

  const closeVisit = async () => {
    if (closingVisit || !openVisit?.uuid || !offerClose) {
      return;
    }
    setClosingVisit(true);
    setCloseError(null);
    setError(null);
    try {
      await closeRegistrationVisit(patientUuid, openVisit.uuid);
      setConfirmClose(false);
      setNotice(VISIT_CLOSED_SUCCESS_MESSAGE);
      setVisitNumberNotice(null);
      setContinued(false);
      load(true);
    } catch (reason) {
      setCloseError(reason instanceof Error ? reason.message : "The visit could not be closed.");
    } finally {
      setClosingVisit(false);
    }
  };

  return (
    <div className="reg-patient">
      <div className="reg-patient__nav">
        <Button variant="ghost" onClick={() => openCreateVisit()}>
          ← Find another patient
        </Button>
        <Button variant="ghost" onClick={() => setShellRoute("registration-desk")}>
          Reception
        </Button>
      </div>
      <PageHeader title="Create Visit" description={CREATE_VISIT_NO_CARD_COPY} />

      {patient ? (
        <PatientIdentityHeader
          patient={patient}
          queueNumber={
            formatDailyVisitNumber(openVisit?.dailyVisitNumber) === MISSING_DAILY_VISIT_NUMBER
              ? undefined
              : formatDailyVisitNumber(openVisit?.dailyVisitNumber)
          }
          visitLabel={
            openVisit
              ? `${receptionVisitTypeLabel(openVisit.visitType)}${openVisit.startDate ? ` · ${openVisit.startDate}` : ""}`
              : undefined
          }
        />
      ) : loading ? (
        <LoadingState variant="inline" label="Loading patient…" />
      ) : null}

      {loading ? <LoadingState variant="board" label="Loading patient record…" /> : null}
      {!loading && error && !patient ? (
        <ErrorState title="Unable to load this patient" description={error} onRetry={() => load()} />
      ) : null}
      {notice ? (
        <Alert tone="success" title={notice}>
          {visitNumberNotice ? <p>{visitNumberNotice}</p> : null}
        </Alert>
      ) : null}
      {!loading && error && patient ? (
        <Alert tone="danger" title="Could not complete this step">
          {error}
        </Alert>
      ) : null}
      {continued ? (
        <Alert tone="success" title={visitNotice || VISIT_ALREADY_OPEN_MESSAGE} />
      ) : null}

      {!loading && patient ? (
        <Card>
          <SectionHeader
            title={offerStart ? "Start visit" : "Current visit"}
            description={visitNotice || "Start the outpatient visit for this arrival."}
          />
          {!offerStart && openVisit ? (
            <dl className="reg-patient__facts">
              <div>
                <dt>Visit</dt>
                <dd>{receptionVisitTypeLabel(openVisit.visitType)}</dd>
              </div>
              {openVisit.startDate ? (
                <div>
                  <dt>Started</dt>
                  <dd>
                    {openVisit.startDate}
                    {openVisit.start ? ` · ${openVisit.start}` : ""}
                  </dd>
                </div>
              ) : null}
              {visitStatus ? (
                <div>
                  <dt>Status</dt>
                  <dd>{visitStatus.label}</dd>
                </div>
              ) : null}
            </dl>
          ) : null}
          {offerStart ? (
            <>
              <fieldset className="reg-visit-types">
                <legend>Kind of visit</legend>
                <div className="reg-visit-types__list">
                  {visitTypes.map((item) => {
                    const copy = RECEPTION_VISIT_TYPE_COPY[item.name];
                    return (
                      <label key={item.uuid} className={visitTypeUuid === item.uuid ? "is-selected" : ""}>
                        <input
                          type="radio"
                          name="createVisitType"
                          checked={visitTypeUuid === item.uuid}
                          onChange={() => setVisitTypeUuid(item.uuid)}
                        />
                        <span>
                          <strong>{copy?.label || item.label}</strong>
                          {copy?.helper || item.helper ? <em>{copy?.helper || item.helper}</em> : null}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>
              {locationMode === "choose" ? (
                <div className="reg-form__grid">
                  <label>
                    Ward
                    <select value={locationUuid} onChange={(event) => setLocationUuid(event.target.value)}>
                      <option value="">Select the ward</option>
                      {locationOptions.map((item) => (
                        <option key={item.uuid} value={item.uuid}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              ) : null}
              {locationMode === "none" ? (
                <Alert tone="warning" title="This visit cannot be started">
                  The hospital location for this kind of visit is not configured. Ask an administrator to
                  review the location setup.
                </Alert>
              ) : null}
              <div className="reg-patient__actions">
                <Button
                  onClick={() => void startVisit()}
                  busy={startingVisit}
                  busyLabel="Creating visit..."
                  disabled={!canSubmitVisit}
                >
                  Start visit
                </Button>
              </div>
            </>
          ) : (
            <div className="reg-patient__actions">
              <Button
                onClick={() => {
                  setContinued(true);
                  setNotice(visitNotice || VISIT_ALREADY_OPEN_MESSAGE);
                }}
              >
                {CONTINUE_EXISTING_VISIT_LABEL}
              </Button>
              {offerClose ? (
                <Button variant="secondary" onClick={() => setConfirmClose(true)} disabled={closingVisit}>
                  {CLOSE_VISIT_LABEL}
                </Button>
              ) : null}
            </div>
          )}
        </Card>
      ) : null}

      {confirmClose && offerClose ? (
        <ConfirmDialog
          title={CLOSE_VISIT_CONFIRM_TITLE}
          description={CLOSE_VISIT_CONFIRM_COPY}
          confirmLabel={CLOSE_VISIT_LABEL}
          busyLabel={CLOSING_VISIT_LABEL}
          busy={closingVisit}
          error={closeError}
          onClose={() => {
            if (!closingVisit) {
              setConfirmClose(false);
              setCloseError(null);
            }
          }}
          onConfirm={() => void closeVisit()}
        />
      ) : null}

      <p className="reg-patient__muted">{CREATE_VISIT_NO_CARD_COPY}</p>
    </div>
  );
}
