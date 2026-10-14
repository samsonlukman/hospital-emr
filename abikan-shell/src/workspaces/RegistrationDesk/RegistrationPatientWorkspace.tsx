import { useEffect, useMemo, useState } from "react";
import {
  openAntenatalRegistration,
  openReceptionFamily,
  openRegistrationRegister,
  returnToPreviousScreen,
} from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { SectionIndex } from "../../components/SectionIndex";
import { PatientAccountLink } from "../../components/PatientAccountLink";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { fetchAncSummary } from "../../services/antenatal";
import { fetchPatientIdentity, fetchPatientVisits } from "../../services/openmrs/clinicalPatient";
import { PatientAccountRequestError } from "../../services/patientAccount";
import {
  createRegistrationCharge,
  fetchRegistrationCharge,
  fetchRegistrationMetadata,
  newRegistrationRequestId,
  startRegistrationVisit,
} from "../../services/registration";
import type { PatientIdentity, PatientVisitSummary, WorkspaceContext } from "../../types";
import type { RegistrationCardType } from "../../types/registration";
import {
  RECEPTION_VISIT_TYPE_COPY,
  isGeneralReceptionVisitType,
  receptionLocationChoiceMode,
  receptionVisitTypeLabel,
} from "../../config/receptionVisitTypes";
import type { RegistrationChargePayload, RegistrationVisitTypeOption } from "../../types/registration";
import { MISSING_DAILY_VISIT_NUMBER, formatDailyVisitNumber } from "../../utils/dailyVisitNumber";
import { paymentStateTone } from "../PatientAccount/accountBadges";
import { canOfferAncVisitType } from "../Antenatal/antenatalView";
import { EXISTING_FAMILY_NO_FEE_COPY, FAMILY_CARD_ISSUED_COPY } from "./hospitalFamilyView";
import {
  existingVisitNotice,
  readStartVisitResult,
  shouldOfferCardFee,
  shouldOfferStartVisit,
  shouldShowCardFeeCard,
} from "./receptionVisit";
import "./RegistrationDeskWorkspace.css";

interface RegistrationPatientWorkspaceProps {
  patientUuid: string;
  context: WorkspaceContext;
}

export function RegistrationPatientWorkspace({
  patientUuid,
}: RegistrationPatientWorkspaceProps) {
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [visits, setVisits] = useState<PatientVisitSummary[]>([]);
  const [charge, setCharge] = useState<RegistrationChargePayload | null>(null);
  const [visitTypes, setVisitTypes] = useState<RegistrationVisitTypeOption[]>([]);
  const [visitTypeUuid, setVisitTypeUuid] = useState("");
  const [locationUuid, setLocationUuid] = useState("");
  const [cardType, setCardType] = useState<RegistrationCardType>("individual");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [startingVisit, setStartingVisit] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [visitNumberNotice, setVisitNumberNotice] = useState<string | null>(null);
  const [requestId, setRequestId] = useState(newRegistrationRequestId);
  const [visitRequestId, setVisitRequestId] = useState(newRegistrationRequestId);
  const [ancEnrolled, setAncEnrolled] = useState(false);

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
  const canStartVisit =
    Boolean(visitTypeUuid) && locationMode !== "none" && (locationMode === "auto" || Boolean(locationUuid));

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
      fetchRegistrationCharge(patientUuid),
      fetchRegistrationMetadata(),
      fetchAncSummary(patientUuid),
    ]).then(([identity, visitResult, chargeResult, metaResult, ancResult]) => {
      if (identity.status === "fulfilled") {
        setPatient(identity.value);
      } else if (!keepNotice) {
        setError(
          identity.reason instanceof Error
            ? identity.reason.message
            : "Unable to load this patient.",
        );
      }
      if (visitResult.status === "fulfilled") {
        setVisits(visitResult.value);
      }
      if (chargeResult.status === "fulfilled") {
        setCharge(chargeResult.value);
        const stored = sessionStorage.getItem("abikan.registration.cardType");
        const fromCharge = chargeResult.value.cardType;
        if (fromCharge === "family" || fromCharge === "individual") {
          setCardType(fromCharge);
        } else if (stored === "family" || stored === "individual") {
          setCardType(stored);
        }
      } else {
        setCharge(null);
      }
      const enrolled =
        ancResult.status === "fulfilled" ? canOfferAncVisitType(ancResult.value.enrolled) : false;
      setAncEnrolled(enrolled);
      if (metaResult.status === "fulfilled") {
        const types = (metaResult.value.visitTypes || []).filter((item) =>
          isGeneralReceptionVisitType(item.name),
        );
        setVisitTypes(types);
        const initial = types[0];
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
      }
      setLoading(false);
    });
  };

  useEffect(() => {
    load();
    setConfirming(false);
    setRequestId(newRegistrationRequestId());
    setVisitRequestId(newRegistrationRequestId());
  }, [patientUuid]);

  useEffect(() => {
    if (!selectedType) {
      return;
    }
    const options = selectedType.locations;
    const mode = receptionLocationChoiceMode(selectedType.name, options.length);
    if (mode === "auto") {
      const only = selectedType.defaultLocationUuid || options[0]?.uuid || "";
      if (locationUuid !== only) {
        setLocationUuid(only);
      }
      return;
    }
    if (mode === "none") {
      if (locationUuid) {
        setLocationUuid("");
      }
      return;
    }
    const allowed = new Set(options.map((item) => item.uuid));
    if (locationUuid && !allowed.has(locationUuid)) {
      setLocationUuid("");
    }
  }, [selectedType, locationUuid]);

  const openVisit = visits.find((visit) => visit.open);
  const visitUuid = charge?.visit?.uuid || openVisit?.uuid;
  const admissionActive = Boolean(charge?.admissionActive);
  const offerStartVisit = shouldOfferStartVisit({ openVisit, admissionActive });
  const visitNotice = existingVisitNotice({ openVisit, admissionActive });
  const offerCardFee = shouldOfferCardFee(charge);
  const showCardFeeCard = shouldShowCardFeeCard(charge);
  const paid = Boolean(charge?.hasCharge && charge.paymentStatus === "PAID" && !charge.cardAlreadyRegistered);
  const selectedCard = (charge?.cards || []).find((card) => card.id === cardType);
  const feeLabel = selectedCard?.label || charge?.feeName;
  const feeAmount = charge?.hasCharge ? charge.feeAmount.formatted : selectedCard?.amount.formatted || charge?.feeAmount.formatted;

  const startVisit = async () => {
    if (startingVisit || !canStartVisit || !resolvedLocationUuid) {
      return;
    }
    setStartingVisit(true);
    setError(null);
    setNotice(null);
    setVisitNumberNotice(null);
    try {
      const started = readStartVisitResult(
        await startRegistrationVisit(
          patientUuid,
          visitTypeUuid,
          resolvedLocationUuid,
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
      setError(reason instanceof Error ? reason.message : "The visit could not be started.");
    } finally {
      setStartingVisit(false);
    }
  };

  const submit = async () => {
    if (submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = await createRegistrationCharge(patientUuid, visitUuid || "", requestId, cardType);
      setCharge(payload);
      setConfirming(false);
      setRequestId(newRegistrationRequestId());
    } catch (reason) {
      if (reason instanceof PatientAccountRequestError && reason.code === "charge_in_progress") {
        load();
        setConfirming(false);
        return;
      }
      setError(reason instanceof Error ? reason.message : "The registration fee could not be created.");
      setConfirming(false);
      load();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="reg-patient">
      <div className="reg-patient__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/reception")}>
          ← Reception
        </Button>
        <div className="abikan-account-nav">
          <Button variant="ghost" onClick={() => openRegistrationRegister(patientUuid)}>
            Edit details
          </Button>
          <PatientAccountLink patientUuid={patientUuid} />
        </div>
      </div>

      {patient ? (
        <PatientIdentityHeader
          compact
          patient={patient}
          queueNumber={
            formatDailyVisitNumber(openVisit?.dailyVisitNumber || visits[0]?.dailyVisitNumber) ===
            MISSING_DAILY_VISIT_NUMBER
              ? undefined
              : formatDailyVisitNumber(openVisit?.dailyVisitNumber || visits[0]?.dailyVisitNumber)
          }
          visitLabel={
            openVisit
              ? `${receptionVisitTypeLabel(openVisit.visitType)} · ${openVisit.startDate}`
              : visits[0]
                ? `${receptionVisitTypeLabel(visits[0].visitType)} · ${visits[0].startDate}`
                : undefined
          }
        />
      ) : (
        <p className="reg-patient__muted">Loading patient…</p>
      )}

      {loading ? <LoadingState variant="board" label="Loading patient…" /> : null}
      {!loading && error && !patient ? (
        <EmptyState title="Unable to load this patient" description={error} />
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

      <div className="abikan-sheet">
      <div className="abikan-sheet__main">
      {!loading && patient ? (
        <Card id="antenatal">
          <SectionHeader
            title="Other services"
            description="Hospital registration is separate from antenatal care. Open Antenatal Care only when this patient needs pregnancy care."
          />
          <div className="reg-patient__actions">
            <Button variant="secondary" onClick={() => openAntenatalRegistration(patientUuid)}>
              {ancEnrolled ? "Open antenatal card" : "Open Antenatal Care"}
            </Button>
          </div>
        </Card>
      ) : null}

      {paid ? (
        <Alert tone="success" title="Payment received">
          <p>
            {charge?.feeName}: {charge?.paymentStatus}
          </p>
          <p>Receipt is available on the patient account.</p>
        </Alert>
      ) : null}

      {charge?.family ? (
        <Card id="family">
          <SectionHeader
            title="Family Card"
            description={
              charge.hasCharge
                ? "The Family Card fee is with Accountant."
                : charge.familyCardIssued
                  ? FAMILY_CARD_ISSUED_COPY
                  : EXISTING_FAMILY_NO_FEE_COPY
            }
          />
          <dl className="reg-patient__facts">
            <div>
              <dt>Family</dt>
              <dd>{charge.family.familyName}</dd>
            </div>
            <div>
              <dt>Family Card</dt>
              <dd>{charge.family.cardNumber}</dd>
            </div>
            <div>
              <dt>Patients</dt>
              <dd>
                {charge.family.memberCount === 1
                  ? "1 patient"
                  : `${charge.family.memberCount} patients`}
              </dd>
            </div>
            {charge.family.relationship ? (
              <div>
                <dt>Relationship</dt>
                <dd>{charge.family.relationship}</dd>
              </div>
            ) : null}
          </dl>
          <div className="reg-patient__actions">
            <Button variant="secondary" onClick={() => openReceptionFamily(charge.family!.familyId)}>
              View family
            </Button>
            <Button
              variant="secondary"
              onClick={() => openRegistrationRegister(undefined, charge.family!.familyId)}
            >
              Register another family member
            </Button>
          </div>
        </Card>
      ) : null}

      {!loading && patient ? (
        <Card id="visit">
          <SectionHeader
            title={offerStartVisit ? "Start visit" : "Current visit"}
            description={
              visitNotice
                ? visitNotice
                : "Every hospital visit starts here."
            }
          />
          {!offerStartVisit && openVisit ? (
            <dl className="reg-patient__facts">
              <div>
                <dt>Visit</dt>
                <dd>{receptionVisitTypeLabel(openVisit.visitType)}</dd>
              </div>
              <div>
                <dt>Started</dt>
                <dd>{openVisit.startDate}</dd>
              </div>
              {formatDailyVisitNumber(openVisit.dailyVisitNumber) !== MISSING_DAILY_VISIT_NUMBER ? (
                <div>
                  <dt>Visit number</dt>
                  <dd>{formatDailyVisitNumber(openVisit.dailyVisitNumber)}</dd>
                </div>
              ) : null}
            </dl>
          ) : null}
          {offerStartVisit ? (
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
                          name="visitType"
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
                    <select
                      value={locationUuid}
                      onChange={(event) => setLocationUuid(event.target.value)}
                    >
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
                  disabled={!canStartVisit}
                >
                  Start visit
                </Button>
              </div>
            </>
          ) : null}
        </Card>
      ) : null}

      {!loading && showCardFeeCard && charge ? (
        <Card id="card-fee">
          <SectionHeader
            title="Registration card fee"
            description="For a new hospital card only. A returning patient does not pay this again to start a visit."
          />
          <dl className="reg-patient__facts">
            <div>
              <dt>Patient</dt>
              <dd>{patient?.name || charge.patient.name}</dd>
            </div>
            <div>
              <dt>Hospital number</dt>
              <dd>{patient?.mrn || charge.patient.mrn}</dd>
            </div>
            <div>
              <dt>Card</dt>
              <dd>{feeLabel}</dd>
            </div>
            <div>
              <dt>Amount</dt>
              <dd>{feeAmount}</dd>
            </div>
            <div>
              <dt>Payment</dt>
              <dd>
                {charge.hasCharge ? (
                  <Badge tone={paymentStateTone(charge.paymentStatus)}>{charge.paymentStatus}</Badge>
                ) : (
                  "Not billed yet"
                )}
              </dd>
            </div>
          </dl>
          {offerCardFee && (charge.cards || []).length > 0 && !charge.family ? (
            <div className="reg-form__cards">
              {(charge.cards || []).map((card) => (
                <label key={card.id} className={cardType === card.id ? "is-selected" : ""}>
                  <input
                    type="radio"
                    name="feeCard"
                    checked={cardType === card.id}
                    onChange={() => setCardType(card.id)}
                  />
                  <strong>{card.label}</strong>
                  <span>{card.amount.formatted}</span>
                </label>
              ))}
            </div>
          ) : null}
          <div className="reg-patient__actions">
            {offerCardFee ? (
              <Button onClick={() => setConfirming(true)} disabled={submitting}>
                Create registration fee
              </Button>
            ) : (
              <p className="reg-patient__block">
                {charge.blockReason ||
                  (paid
                    ? "This registration fee has been paid."
                    : "This registration fee cannot be created yet.")}
              </p>
            )}
          </div>
        </Card>
      ) : null}
      </div>
      <SectionIndex
        label="Reception sections"
        items={[
          ...(patient
            ? [
                { id: "antenatal", label: "Antenatal" },
                { id: "visit", label: offerStartVisit ? "Start visit" : "Current visit" },
              ]
            : []),
          ...(charge?.family ? [{ id: "family", label: "Family card" }] : []),
          ...(showCardFeeCard && charge ? [{ id: "card-fee", label: "Card fee" }] : []),
        ]}
      />
      </div>

      {confirming && charge ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="reg-fee-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="reg-fee-title">Confirm registration fee</h2>
            <p>This sends the bill to Accountant. Reception does not collect payment.</p>
            <dl>
              <div>
                <dt>Patient</dt>
                <dd>{patient?.name || charge.patient.name}</dd>
              </div>
              <div>
                <dt>Hospital number</dt>
                <dd>{patient?.mrn || charge.patient.mrn}</dd>
              </div>
              <div>
                <dt>Card</dt>
                <dd>{feeLabel}</dd>
              </div>
              <div>
                <dt>Amount</dt>
                <dd>{feeAmount}</dd>
              </div>
            </dl>
            <div className="cashier-confirm__actions">
              <Button onClick={() => void submit()} disabled={submitting}>
                {submitting ? "Creating…" : "Confirm fee"}
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)} disabled={submitting}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
