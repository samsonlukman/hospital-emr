import { useEffect, useMemo, useState } from "react";
import {
  openRadiologyExternalStudy,
  openRadiologyPatient,
  openRadiologyWorklistOrder,
} from "../../app/hashRoute";
import {
  RADIOGRAPHY_GROUP,
  ULTRASOUND_GROUP,
  findRadiologyService,
  radiologyMenuByGroup,
  resolveRadiologyOrderConcept,
  type RadiologyMenuGroup,
} from "../../config/radiologyMenu";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { SectionHeader } from "../../components/SectionHeader";
import { searchPatients } from "../../services/openmrs/patients";
import { fetchPatientVisits, parsePatientDisplay } from "../../services/openmrs/clinicalPatient";
import {
  createDirectRadiologyStudy,
  createExternalRadiologyStudy,
  newRadiologyRequestId,
} from "../../services/radiologyBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { PatientSearchHit, PatientVisitSummary, WorkspaceContext } from "../../types";
import {
  RADIOLOGY_PRICE_HELPER,
} from "./radiologyDesk";
import {
  RADIOLOGY_FEE_SYMBOL,
  parseRadiologyAmount,
} from "./radiologyPrice";
import "./RadiologyFeeCard.css";

type PatientKind = "registered" | "external";

export function RadiologyNewStudyView({ context }: { context: WorkspaceContext }) {
  const [patientKind, setPatientKind] = useState<PatientKind>("registered");
  const [patientQuery, setPatientQuery] = useState("");
  const [hits, setHits] = useState<PatientSearchHit[]>([]);
  const [patient, setPatient] = useState<PatientSearchHit | null>(null);
  const [visits, setVisits] = useState<PatientVisitSummary[]>([]);
  const [visitUuid, setVisitUuid] = useState("");
  const [buyerName, setBuyerName] = useState("");
  const [buyerPhone, setBuyerPhone] = useState("");
  const [buyerSex, setBuyerSex] = useState("");
  const [buyerDob, setBuyerDob] = useState("");
  const [buyerAddress, setBuyerAddress] = useState("");
  const [requestSource, setRequestSource] = useState("external_referral");
  const [referrer, setReferrer] = useState("");
  const [group, setGroup] = useState<RadiologyMenuGroup | "">("");
  const [serviceId, setServiceId] = useState("");
  const [optionId, setOptionId] = useState("");
  const [indication, setIndication] = useState("");
  const [amountInput, setAmountInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const services = group ? radiologyMenuByGroup(group) : [];
  const selected = findRadiologyService(serviceId);
  const concept = resolveRadiologyOrderConcept(selected, optionId);
  const parsedAmount = parseRadiologyAmount(amountInput);
  const openVisits = useMemo(() => visits.filter((visit) => visit.open), [visits]);
  const selectedPatientLabel = patient
    ? (() => {
        const parsed = parsePatientDisplay(patient.display);
        return parsed.mrn && parsed.mrn !== "—"
          ? `${parsed.name} (${parsed.mrn})`
          : parsed.name || patient.display;
      })()
    : patientQuery;

  useEffect(() => {
    if (patientKind !== "registered" || patient || patientQuery.trim().length < 2) {
      setHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      void searchPatients(patientQuery)
        .then(setHits)
        .catch(() => setHits([]));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [patientQuery, patient, patientKind]);

  useEffect(() => {
    if (patientKind !== "registered" || !patient?.uuid) {
      setVisits([]);
      setVisitUuid("");
      return;
    }
    let cancelled = false;
    void fetchPatientVisits(patient.uuid)
      .then((rows) => {
        if (cancelled) {
          return;
        }
        setVisits(rows);
        const open = rows.find((row) => row.open);
        setVisitUuid(open?.uuid || "");
      })
      .catch(() => {
        if (!cancelled) {
          setVisits([]);
          setVisitUuid("");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [patient?.uuid, patientKind]);

  const canSubmitRegistered = Boolean(
    patient?.uuid && visitUuid && selected && concept && parsedAmount.ok && !busy,
  );
  const canSubmitExternal = Boolean(
    buyerName.trim().length >= 2 && selected && concept && parsedAmount.ok && !busy,
  );

  const submit = async () => {
    if (!concept || !selected || busy) {
      return;
    }
    const amount = parseRadiologyAmount(amountInput);
    if (!amount.ok) {
      setError(amount.message);
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (patientKind === "registered") {
        if (!patient?.uuid || !visitUuid) {
          return;
        }
        const saved = await createDirectRadiologyStudy(patient.uuid, {
          visitUuid,
          locationUuid: context.location.uuid,
          requestId: newRadiologyRequestId(),
          indication,
          amount: amount.amount,
          services: [{ serviceId: selected.id, conceptUuid: concept.conceptUuid }],
        });
        setNotice(saved.message || "Imaging study created by Radiology.");
        setServiceId("");
        setOptionId("");
        setIndication("");
        setAmountInput("");
        const first = saved.orders?.[0];
        if (first?.uuid) {
          openRadiologyWorklistOrder({
            orderUuid: first.uuid,
            patientUuid: patient.uuid,
            visitUuid: saved.visitUuid || visitUuid,
          });
        }
        return;
      }
      const saved = await createExternalRadiologyStudy({
        requestId: newRadiologyRequestId(),
        buyerName: buyerName.trim(),
        buyerPhone: buyerPhone.trim(),
        buyerSex,
        buyerDob: buyerDob.trim(),
        buyerAddress: buyerAddress.trim(),
        indication,
        requestSource,
        referrer: referrer.trim(),
        amount: amount.amount,
        services: [{ serviceId: selected.id, conceptUuid: concept.conceptUuid }],
      });
      setNotice(saved.message || "External imaging study created.");
      setBuyerName("");
      setBuyerPhone("");
      setBuyerSex("");
      setBuyerDob("");
      setBuyerAddress("");
      setReferrer("");
      setServiceId("");
      setOptionId("");
      setIndication("");
      setAmountInput("");
      if (saved.studyId || saved.uuid) {
        openRadiologyExternalStudy(saved.studyId || saved.uuid);
      }
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The imaging study could not be created.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card id="new-study">
      <SectionHeader
        title="New Imaging Study"
        description="Start imaging for a registered hospital patient, or for someone who is here only for an imaging service."
      />
      {error ? (
        <Alert tone="warning" title="Imaging study">
          <p>{error}</p>
        </Alert>
      ) : null}
      {notice ? (
        <Alert tone="success" title="Imaging study">
          <p>{notice}</p>
        </Alert>
      ) : null}

      <div className="rad-new-study">
        <fieldset className="rad-new-study__type">
          <legend>Patient type</legend>
          <label className="rad-new-study__radio">
            <input
              type="radio"
              name="patient-type"
              checked={patientKind === "registered"}
              onChange={() => {
                setPatientKind("registered");
                setError("");
                setNotice("");
              }}
            />
            Registered Patient
          </label>
          <label className="rad-new-study__radio">
            <input
              type="radio"
              name="patient-type"
              checked={patientKind === "external"}
              onChange={() => {
                setPatientKind("external");
                setPatient(null);
                setPatientQuery("");
                setHits([]);
                setError("");
                setNotice("");
              }}
            />
            External Patient
          </label>
        </fieldset>

        {patientKind === "registered" ? (
          <>
            <label>
              <span>Patient</span>
              <input
                value={selectedPatientLabel}
                onChange={(event) => {
                  setPatient(null);
                  setPatientQuery(event.target.value);
                }}
                placeholder="Search by name or hospital number"
              />
            </label>
            {!patient && hits.length > 0 ? (
              <ul className="rad-new-study__hits">
                {hits.slice(0, 8).map((hit) => {
                  const parsed = parsePatientDisplay(hit.display);
                  return (
                    <li key={hit.uuid}>
                      <button
                        type="button"
                        onClick={() => {
                          setPatient(hit);
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

            {patient ? (
              <p className="rad-new-study__hint">
                Request source: <strong>Radiology Direct</strong>
                {" · "}
                <button type="button" className="rad-link" onClick={() => openRadiologyPatient(patient.uuid)}>
                  Open patient imaging history
                </button>
              </p>
            ) : null}

            {patient && openVisits.length === 0 ? (
              <Alert tone="warning" title="Open visit needed">
                <p>Start an open visit at Reception for this patient before creating an imaging study.</p>
              </Alert>
            ) : null}

            {patient && openVisits.length > 0 ? (
              <label>
                <span>Visit</span>
                <select value={visitUuid} onChange={(event) => setVisitUuid(event.target.value)}>
                  {openVisits.map((visit) => (
                    <option key={visit.uuid} value={visit.uuid}>
                      {visit.visitType || "Visit"} · {visit.startDatetime || visit.uuid}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </>
        ) : (
          <>
            <p className="rad-new-study__hint">
              External patients are billed for imaging without hospital registration. Payment is collected
              separately by Accounts.
            </p>
            <label>
              <span>Full name</span>
              <input
                value={buyerName}
                onChange={(event) => setBuyerName(event.target.value)}
                placeholder="Full name"
              />
            </label>
            <label>
              <span>Phone</span>
              <input
                value={buyerPhone}
                onChange={(event) => setBuyerPhone(event.target.value)}
                placeholder="Phone number"
              />
            </label>
            <label>
              <span>Sex</span>
              <select value={buyerSex} onChange={(event) => setBuyerSex(event.target.value)}>
                <option value="">Not specified</option>
                <option value="Female">Female</option>
                <option value="Male">Male</option>
              </select>
            </label>
            <label>
              <span>Date of birth or age</span>
              <input
                value={buyerDob}
                onChange={(event) => setBuyerDob(event.target.value)}
                placeholder="e.g. 12 Jan 1990 or 35 years"
              />
            </label>
            <label>
              <span>Address / contact</span>
              <input
                value={buyerAddress}
                onChange={(event) => setBuyerAddress(event.target.value)}
                placeholder="Optional"
              />
            </label>
            <label>
              <span>Request source</span>
              <select value={requestSource} onChange={(event) => setRequestSource(event.target.value)}>
                <option value="external_referral">External Referral / Request</option>
                <option value="radiology_direct">Direct Radiology request</option>
              </select>
            </label>
            <label>
              <span>Referrer or request note</span>
              <input
                value={referrer}
                onChange={(event) => setReferrer(event.target.value)}
                placeholder="Outside doctor or facility, if known"
              />
            </label>
          </>
        )}

        <label>
          <span>Imaging group</span>
          <select
            value={group}
            onChange={(event) => {
              setGroup(event.target.value as RadiologyMenuGroup | "");
              setServiceId("");
              setOptionId("");
            }}
          >
            <option value="">Select group</option>
            <option value={ULTRASOUND_GROUP}>{ULTRASOUND_GROUP}</option>
            <option value={RADIOGRAPHY_GROUP}>{RADIOGRAPHY_GROUP}</option>
          </select>
        </label>

        <label>
          <span>Examination</span>
          <select
            value={serviceId}
            disabled={!group}
            onChange={(event) => {
              setServiceId(event.target.value);
              setOptionId("");
            }}
          >
            <option value="">Select examination</option>
            {services.map((service) => (
              <option key={service.id} value={service.id}>
                {service.hospitalName}
              </option>
            ))}
          </select>
        </label>

        {selected?.options?.length ? (
          <label>
            <span>{selected.optionPrompt || "Option"}</span>
            <select value={optionId} onChange={(event) => setOptionId(event.target.value)}>
              <option value="">Select</option>
              {selected.options.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <label>
          <span>Clinical indication</span>
          <textarea
            value={indication}
            onChange={(event) => setIndication(event.target.value)}
            rows={3}
            placeholder="Why this study is needed"
          />
        </label>

        <div className="rad-fee__amount">
          <label htmlFor="new-study-fee-amount">Price</label>
          <div className="rad-fee__input">
            <span aria-hidden="true">{RADIOLOGY_FEE_SYMBOL}</span>
            <input
              id="new-study-fee-amount"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={amountInput}
              onChange={(event) => setAmountInput(event.target.value)}
              placeholder="Amount"
              aria-describedby="new-study-fee-currency"
            />
          </div>
          <p id="new-study-fee-currency" className="rad-fee__currency">
            {RADIOLOGY_PRICE_HELPER}
          </p>
        </div>

        <div className="rad-new-study__actions">
          <Button
            disabled={patientKind === "registered" ? !canSubmitRegistered : !canSubmitExternal}
            onClick={() => void submit()}
          >
            {busy ? "Creating…" : "Create imaging study"}
          </Button>
        </div>
        {patientKind === "registered" && !patient ? (
          <EmptyState title="Search and select a registered patient." />
        ) : null}
        {patientKind === "external" && buyerName.trim().length < 2 ? (
          <EmptyState title="Enter the person's full name to continue." />
        ) : null}
      </div>
    </Card>
  );
}
