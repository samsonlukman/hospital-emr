import { useEffect, useMemo, useState } from "react";
import {
  openAntenatalPatientRegister,
  openAntenatalRegistration,
  returnToPreviousScreen,
  setShellRoute,
} from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import { SectionHeader } from "../../components/SectionHeader";
import {
  isReceptionStartVisitType,
  receptionLocationChoiceMode,
  receptionVisitTypeLabel,
} from "../../config/receptionVisitTypes";
import { fetchAncCardList, fetchAncSummary } from "../../services/antenatal";
import { fetchPatientIdentity, fetchPatientVisits } from "../../services/openmrs/clinicalPatient";
import { searchPatients } from "../../services/openmrs/patients";
import {
  fetchRegistrationVisitContext,
  newRegistrationRequestId,
  startRegistrationVisit,
} from "../../services/registration";
import type { PatientIdentity, PatientSearchHit, PatientVisitSummary } from "../../types";
import type { AncCardListPayload, AncPatientSummary } from "../../types/antenatal";
import type { RegistrationVisitTypeOption } from "../../types/registration";
import { MISSING_DAILY_VISIT_NUMBER, formatDailyVisitNumber } from "../../utils/dailyVisitNumber";
import { AncRegistrationFeeCard } from "../Antenatal/AncRegistrationFeeCard";
import { AntenatalCardView } from "../Antenatal/AntenatalCardView";
import {
  ANC_DEFAULT_FEE_AMOUNT,
  canOfferAncVisitType,
  defaultAncFeeInput,
  isAncVisitType,
} from "../Antenatal/antenatalView";
import { parsePatientPageSize, patientPageRange } from "../PatientDirectory/patientDirectoryView";
import { existingVisitNotice, readStartVisitResult, shouldOfferStartVisit } from "./receptionVisit";
import "../Admin/AdminWorkspace.css";
import "../PatientDirectory/PatientDirectoryWorkspace.css";
import "./RegistrationDeskWorkspace.css";

interface AntenatalRegistrationWorkspaceProps {
  patientUuid: string | null;
}

export function AntenatalRegistrationWorkspace({ patientUuid }: AntenatalRegistrationWorkspaceProps) {
  if (!patientUuid) {
    return <AntenatalRegistrationSearch />;
  }
  return <AntenatalRegistrationPatient key={patientUuid} patientUuid={patientUuid} />;
}

function AntenatalRegistrationSearch() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PatientSearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [list, setList] = useState<AncCardListPayload | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [listQuery, setListQuery] = useState("");
  const [submittedListQuery, setSubmittedListQuery] = useState("");
  const [pageSize, setPageSize] = useState(50);
  const [startIndex, setStartIndex] = useState(0);

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

  useEffect(() => {
    let cancelled = false;
    setListLoading(true);
    setListError(null);
    void fetchAncCardList({
      q: submittedListQuery,
      limit: pageSize,
      startIndex,
    })
      .then((payload) => {
        if (!cancelled) {
          setList(payload);
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setList(null);
          setListError(
            reason instanceof Error ? reason.message : "The antenatal list could not be loaded.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setListLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [pageSize, startIndex, submittedListQuery]);

  const searched = query.trim().length >= 2;
  const rows = list?.patients || [];
  const total = list?.total || 0;
  const canPrevious = startIndex > 0;
  const canNext = Boolean(list?.hasMore);

  return (
    <div className="reg-patient">
      <div className="reg-patient__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/reception")}>
          ← Reception
        </Button>
      </div>
      <PageHeader
        title="Antenatal Care"
        description="Find a registered patient to open or create their antenatal card. Creating the card is not an ANC visit."
      />
      <Card>
        <SectionHeader
          title="Find the patient"
          description="ANC attaches to the existing hospital record. It does not create another patient or change their MRN."
        />
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
            description="If this person has never been registered with the hospital, register them first, then return here for antenatal care."
          />
        ) : null}
        {hits.length > 0 ? (
          <ul className="reg-form__matches">
            {hits.map((hit) => (
              <li key={hit.uuid}>
                <button
                  type="button"
                  className="reg-link"
                  onClick={() => openAntenatalRegistration(hit.uuid)}
                >
                  {hit.display}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <div className="reg-patient__actions">
          <Button onClick={() => openAntenatalPatientRegister()}>
            Register a new antenatal patient
          </Button>
        </div>
      </Card>

      <Card>
        <SectionHeader
          title="Patients with an ANC card"
          description="Everyone who has an antenatal card. Creation time is recorded. After one year the card is disabled until the antenatal fee is paid again. Records are not removed from this list."
        />
        <form
          className="admin-workspace__filters patient-directory__filters"
          aria-label="Find antenatal cards"
          onSubmit={(event) => {
            event.preventDefault();
            setStartIndex(0);
            setSubmittedListQuery(listQuery.trim());
          }}
        >
          <label>
            Find on this list
            <input
              type="search"
              value={listQuery}
              onChange={(event) => setListQuery(event.target.value)}
              placeholder="Name or hospital number"
            />
          </label>
          <label>
            Patients per page
            <select
              value={pageSize}
              onChange={(event) => {
                setPageSize(parsePatientPageSize(event.target.value));
                setStartIndex(0);
              }}
            >
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </label>
          <div className="patient-directory__find">
            <Button type="submit">Find</Button>
          </div>
        </form>
        {listLoading ? <LoadingState variant="board" label="Loading antenatal list…" /> : null}
        {listError ? (
          <Alert tone="danger" title="Antenatal list could not be loaded">
            {listError}
          </Alert>
        ) : null}
        {!listLoading && !listError && rows.length === 0 ? (
          <EmptyState
            title="No antenatal cards on this list"
            description={
              submittedListQuery
                ? "No matching patient has an ANC card."
                : "When Reception creates an ANC card, the patient appears here with the creation time."
            }
          />
        ) : null}
        {!listLoading && rows.length > 0 ? (
          <>
            <div className="abikan-table-wrap">
              <table className="abikan-table">
                <thead>
                  <tr>
                    <th>Patient</th>
                    <th>Hospital number</th>
                    <th>ANC card created</th>
                    <th>Card</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={`${row.patientUuid}:${row.pregnancyId}`}>
                      <td>{row.name}</td>
                      <td>{row.hospitalNumber || "—"}</td>
                      <td>{row.enrolledAtLabel || "—"}</td>
                      <td>
                        {row.cardEnabled ? (
                          <Badge tone="success">Enabled</Badge>
                        ) : (
                          <Badge tone="danger">Disabled</Badge>
                        )}
                      </td>
                      <td>
                        <Button
                          variant="secondary"
                          onClick={() => openAntenatalRegistration(row.patientUuid)}
                        >
                          Open ANC card
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="patient-directory__pager">
              <p>{patientPageRange(startIndex, rows.length, total)}</p>
              <div className="patient-directory__pager-actions">
                <Button
                  variant="secondary"
                  disabled={!canPrevious}
                  onClick={() => setStartIndex(Math.max(0, startIndex - pageSize))}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  disabled={!canNext}
                  onClick={() => setStartIndex(startIndex + pageSize)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        ) : null}
      </Card>
    </div>
  );
}

function AntenatalRegistrationPatient({ patientUuid }: { patientUuid: string }) {
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [visits, setVisits] = useState<PatientVisitSummary[]>([]);
  const [ancSummary, setAncSummary] = useState<AncPatientSummary | null>(null);
  const [ancVisitType, setAncVisitType] = useState<RegistrationVisitTypeOption | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startingVisit, setStartingVisit] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [visitNumberNotice, setVisitNumberNotice] = useState<string | null>(null);
  const [visitRequestId, setVisitRequestId] = useState(newRegistrationRequestId);
  const [ancFeeAmount, setAncFeeAmount] = useState(() => defaultAncFeeInput(ANC_DEFAULT_FEE_AMOUNT));

  const enrolled = canOfferAncVisitType(ancSummary?.enrolled);
  const cardEnabled = Boolean(ancSummary?.cardEnabled ?? ancSummary?.activePregnancy?.cardEnabled);
  const cardExpired = Boolean(ancSummary?.cardExpired ?? ancSummary?.activePregnancy?.cardExpired);
  const pregnancyId = ancSummary?.activePregnancy?.pregnancyId || null;
  const openVisit = visits.find((visit) => visit.open);
  const admissionActive = false;
  const offerStart = shouldOfferStartVisit({ openVisit, admissionActive });
  const visitNotice = existingVisitNotice({ openVisit, admissionActive });

  const locationUuid = useMemo(() => {
    if (!ancVisitType) {
      return "";
    }
    const mode = receptionLocationChoiceMode(ancVisitType.name, ancVisitType.locations.length);
    if (mode === "auto") {
      return ancVisitType.defaultLocationUuid || ancVisitType.locations[0]?.uuid || "";
    }
    return ancVisitType.defaultLocationUuid || ancVisitType.locations[0]?.uuid || "";
  }, [ancVisitType]);

  const canStartAncVisit = Boolean(
    enrolled && cardEnabled && ancVisitType?.uuid && locationUuid && offerStart,
  );

  const load = (keepNotice = false) => {
    setLoading(true);
    setError(null);
    if (!keepNotice) {
      setNotice(null);
      setVisitNumberNotice(null);
    }
    Promise.allSettled([
      fetchPatientIdentity(patientUuid),
      fetchPatientVisits(patientUuid),
      fetchAncSummary(patientUuid),
      fetchRegistrationVisitContext(patientUuid),
    ]).then(([identity, visitResult, ancResult, contextResult]) => {
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
      if (ancResult.status === "fulfilled") {
        setAncSummary(ancResult.value);
        setAncFeeAmount(defaultAncFeeInput(ancResult.value.defaultFeeAmount ?? ANC_DEFAULT_FEE_AMOUNT));
      } else {
        setAncSummary(null);
      }
      if (contextResult.status === "fulfilled") {
        const types = (contextResult.value.visitTypes || []).filter(
          (item) => isReceptionStartVisitType(item.name) && isAncVisitType(item.name),
        );
        setAncVisitType(types[0] || null);
      } else {
        setAncVisitType(null);
      }
      setLoading(false);
    });
  };

  useEffect(() => {
    load();
    setVisitRequestId(newRegistrationRequestId());
  }, [patientUuid]);

  const startAncVisit = async () => {
    if (startingVisit || !canStartAncVisit || !ancVisitType) {
      return;
    }
    setStartingVisit(true);
    setError(null);
    setNotice(null);
    try {
      const started = readStartVisitResult(
        await startRegistrationVisit(
          patientUuid,
          ancVisitType.uuid,
          locationUuid,
          visitRequestId,
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
      setError(reason instanceof Error ? reason.message : "The antenatal visit could not be started.");
    } finally {
      setStartingVisit(false);
    }
  };

  return (
    <div className="reg-patient">
      <div className="reg-patient__nav">
        <Button variant="ghost" onClick={() => openAntenatalRegistration()}>
          ← Find another patient
        </Button>
        <Button variant="ghost" onClick={() => setShellRoute("registration-desk")}>
          Reception
        </Button>
      </div>
      <PageHeader
        title="Antenatal Care"
        description={
          enrolled
            ? "This patient already has an antenatal card. After one year the card is disabled until it is enabled again."
            : "Create the antenatal card and enrollment fee. Starting an ANC visit is a separate step when the patient attends."
        }
      />

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

      {loading ? <LoadingState variant="board" label="Loading antenatal registration…" /> : null}
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

      {!loading && patient ? (
        <>
          <section aria-labelledby="anc-step-card">
            <h2 id="anc-step-card" className="reg-patient__muted">
              {enrolled ? "1. Antenatal card" : "1. Create antenatal card"}
            </h2>
            <AntenatalCardView
              patientUuid={patientUuid}
              patientName={patient.name}
              patientMrn={patient.mrn}
              patientDob={patient.birthdate}
              canEdit
              onSummaryChange={(summary) => {
                setAncSummary(summary);
                if (summary?.defaultFeeAmount) {
                  setAncFeeAmount(defaultAncFeeInput(summary.defaultFeeAmount));
                }
              }}
            />
          </section>

          <section aria-labelledby="anc-step-fee">
            <h2 id="anc-step-fee" className="reg-patient__muted">
              {cardExpired ? "2. Enable antenatal card" : "2. Antenatal card fee"}
            </h2>
            <AncRegistrationFeeCard
              patientUuid={patientUuid}
              pregnancyId={pregnancyId}
              patientName={patient.name}
              patientMrn={patient.mrn}
              amountDraft={ancFeeAmount}
              onAmountDraftChange={setAncFeeAmount}
              defaultAmount={ancSummary?.defaultFeeAmount ?? ANC_DEFAULT_FEE_AMOUNT}
              visible
              onChargeChange={(charge) => {
                if (!charge) {
                  return;
                }
                setAncSummary((current) =>
                  current
                    ? {
                        ...current,
                        cardEnabled: Boolean(charge.cardEnabled),
                        cardExpired: Boolean(charge.cardExpired),
                        expiresAt: charge.expiresAt || current.expiresAt,
                        expiresAtLabel: charge.expiresAtLabel || current.expiresAtLabel,
                        fee: charge,
                        canCreateFee: Boolean(charge.canCreate),
                        feeAlreadyRegistered: Boolean(
                          charge.hasCharge || charge.alreadyRegistered,
                        ),
                        activePregnancy: current.activePregnancy
                          ? {
                              ...current.activePregnancy,
                              cardEnabled: Boolean(charge.cardEnabled),
                              cardExpired: Boolean(charge.cardExpired),
                              expiresAt: charge.expiresAt || current.activePregnancy.expiresAt,
                              expiresAtLabel:
                                charge.expiresAtLabel || current.activePregnancy.expiresAtLabel,
                            }
                          : current.activePregnancy,
                      }
                    : current,
                );
              }}
            />
          </section>

          <Card>
            <SectionHeader
              title="3. New ANC visit"
              description={
                !enrolled
                  ? "Finish the antenatal card first. ANC visits are only for enrolled patients."
                  : cardExpired
                    ? "This antenatal card is disabled. Enable the card above, then start the visit."
                    : visitNotice ||
                      "Creating the ANC card does not start a visit. Start an ANC visit only when the patient attends antenatal care."
              }
            />
            {!enrolled ? (
              <Alert tone="warning" title="ANC card not created yet">
                <p>Create the antenatal card above before starting an ANC visit.</p>
              </Alert>
            ) : null}
            {enrolled && cardExpired ? (
              <Alert tone="warning" title="ANC card disabled">
                <p>
                  The antenatal card expired after one year. Enable the card above and collect payment
                  at Accountant before starting a new ANC visit.
                </p>
              </Alert>
            ) : null}
            {enrolled && !cardExpired && !offerStart && openVisit ? (
              <dl className="reg-patient__facts">
                <div>
                  <dt>Current visit</dt>
                  <dd>{receptionVisitTypeLabel(openVisit.visitType)}</dd>
                </div>
                {openVisit.startDate ? (
                  <div>
                    <dt>Started</dt>
                    <dd>{openVisit.startDate}</dd>
                  </div>
                ) : null}
              </dl>
            ) : null}
            {enrolled && !cardExpired && !ancVisitType ? (
              <Alert tone="warning" title="Antenatal visit is not configured">
                Ask an administrator to review antenatal visit setup.
              </Alert>
            ) : null}
            {canStartAncVisit ? (
              <div className="reg-patient__actions">
                <Button
                  onClick={() => void startAncVisit()}
                  busy={startingVisit}
                  busyLabel="Starting visit…"
                >
                  New ANC visit
                </Button>
              </div>
            ) : null}
          </Card>
        </>
      ) : null}
    </div>
  );
}
