import { useEffect, useMemo, useRef, useState } from "react";
import {
  openLaboratoryExternalPatient,
  openLaboratoryPatient,
  openLaboratoryWorklistOrder,
} from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { SectionHeader } from "../../components/SectionHeader";
import { searchPatients } from "../../services/openmrs/patients";
import { fetchPatientVisits, parsePatientDisplay } from "../../services/openmrs/clinicalPatient";
import {
  createExternalLaboratoryOrder,
  createLaboratoryDirectOrders,
  fetchLaboratoryCatalogue,
  newLaboratoryRequestId,
  searchExternalLaboratoryPatients,
} from "../../services/laboratoryBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { PatientSearchHit, PatientVisitSummary, WorkspaceContext } from "../../types";
import type { LaboratoryExternalPatientSummary } from "../../types/laboratoryBilling";
import type { LaboratoryCatalogueTest, LaboratoryOrderDraftItem } from "../../types/laboratoryCatalogue";
import { canSelectLabTest, labCatalogueHitDetails } from "./laboratoryView";
import "../../components/LabOrderPanel.css";
import "./LaboratoryWorkspace.css";

type PatientKind = "registered" | "external";

function addTest(
  draft: LaboratoryOrderDraftItem[],
  test: LaboratoryCatalogueTest,
): LaboratoryOrderDraftItem[] {
  if (!test.conceptUuid || draft.some((item) => item.conceptUuid === test.conceptUuid)) {
    return draft;
  }
  return [
    ...draft,
    {
      conceptUuid: test.conceptUuid,
      name: test.name,
      type: test.type,
      specimen: test.specimen,
      price: test.price,
      outsourced: test.outsourced,
    },
  ];
}

export function LaboratoryNewOrderView({ context }: { context: WorkspaceContext }) {
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
  const [externalQuery, setExternalQuery] = useState("");
  const [externalHits, setExternalHits] = useState<LaboratoryExternalPatientSummary[]>([]);
  const [selectedExternal, setSelectedExternal] = useState<LaboratoryExternalPatientSummary | null>(
    null,
  );
  const [testQuery, setTestQuery] = useState("");
  const [testHits, setTestHits] = useState<LaboratoryCatalogueTest[]>([]);
  const [testOpen, setTestOpen] = useState(false);
  const [draft, setDraft] = useState<LaboratoryOrderDraftItem[]>([]);
  const [indication, setIndication] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const testBoxRef = useRef<HTMLDivElement>(null);

  const openVisits = useMemo(() => visits.filter((visit) => visit.open), [visits]);
  const visitChoices = useMemo(() => {
    if (openVisits.length > 0) {
      return openVisits;
    }
    const latest = [...visits].sort((left, right) =>
      left.startDatetime < right.startDatetime ? 1 : -1,
    )[0];
    return latest ? [latest] : [];
  }, [openVisits, visits]);
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
        const latest = [...rows].sort((left, right) =>
          left.startDatetime < right.startDatetime ? 1 : -1,
        )[0];
        setVisitUuid(open?.uuid || latest?.uuid || "");
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

  useEffect(() => {
    if (patientKind !== "external" || selectedExternal || externalQuery.trim().length < 2) {
      setExternalHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      void searchExternalLaboratoryPatients(externalQuery)
        .then((payload) => setExternalHits(payload.items ?? []))
        .catch(() => setExternalHits([]));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [externalQuery, selectedExternal, patientKind]);

  useEffect(() => {
    let cancelled = false;
    const needle = testQuery.trim();
    if (needle.length < 2) {
      setTestHits([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void fetchLaboratoryCatalogue(needle)
        .then((payload) => {
          if (!cancelled) {
            setTestHits(payload.tests.filter(canSelectLabTest));
          }
        })
        .catch(() => {
          if (!cancelled) {
            setTestHits([]);
          }
        });
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [testQuery]);

  useEffect(() => {
    const onPointer = (event: MouseEvent) => {
      if (testBoxRef.current && !testBoxRef.current.contains(event.target as Node)) {
        setTestOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, []);

  const canSubmitRegistered = Boolean(patient?.uuid && visitUuid && draft.length > 0 && !busy);
  const canSubmitExternal = Boolean(buyerName.trim().length >= 2 && draft.length > 0 && !busy);

  const clearDraft = () => {
    setDraft([]);
    setTestQuery("");
    setIndication("");
  };

  const submit = async () => {
    if (draft.length === 0 || busy) {
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
        const saved = await createLaboratoryDirectOrders(patient.uuid, {
          visitUuid,
          locationUuid: context.location.uuid,
          requestId: newLaboratoryRequestId(),
          indication,
          tests: draft.map((item) => ({ conceptUuid: item.conceptUuid, name: item.name })),
        });
        setNotice(saved.message || "Laboratory order created. Submit the bill when you are ready.");
        clearDraft();
        const first = saved.orders?.[0];
        if (first?.uuid) {
          openLaboratoryWorklistOrder({
            orderUuid: first.uuid,
            patientUuid: patient.uuid,
            visitUuid: saved.visitUuid || visitUuid,
          });
        }
        return;
      }
      const saved = await createExternalLaboratoryOrder({
        requestId: newLaboratoryRequestId(),
        buyerName: buyerName.trim(),
        buyerPhone: buyerPhone.trim(),
        buyerSex,
        buyerDob: buyerDob.trim(),
        buyerAddress: buyerAddress.trim(),
        indication,
        requestSource,
        externalId: selectedExternal?.externalId,
        locationUuid: context.location.uuid,
        tests: draft.map((item) => ({ conceptUuid: item.conceptUuid, name: item.name })),
      });
      setNotice(saved.message || "External laboratory order created.");
      setBuyerName("");
      setBuyerPhone("");
      setBuyerSex("");
      setBuyerDob("");
      setBuyerAddress("");
      setSelectedExternal(null);
      setExternalQuery("");
      clearDraft();
      if (saved.externalId) {
        openLaboratoryExternalPatient(saved.externalId);
      }
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The laboratory order could not be created.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card id="new-order">
      <SectionHeader
        title="New Lab Order"
        description="Start laboratory tests for a registered hospital patient, or for someone who is here only for laboratory services."
      />
      {error ? (
        <Alert tone="warning" title="Laboratory order">
          <p>{error}</p>
        </Alert>
      ) : null}
      {notice ? (
        <Alert tone="success" title="Laboratory order">
          <p>{notice}</p>
        </Alert>
      ) : null}

      <div className="lab-new-order">
        <fieldset className="lab-new-order__type">
          <legend>Patient type</legend>
          <label className="lab-new-order__radio">
            <input
              type="radio"
              name="lab-patient-type"
              checked={patientKind === "registered"}
              onChange={() => {
                setPatientKind("registered");
                setError("");
                setNotice("");
              }}
            />
            Registered Patient
          </label>
          <label className="lab-new-order__radio">
            <input
              type="radio"
              name="lab-patient-type"
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
              <ul className="lab-new-order__hits">
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
              <p className="lab-new-order__hint">
                Request source: <strong>Laboratory Direct</strong>
                {" · "}
                <button
                  type="button"
                  className="lab-desk__link"
                  onClick={() => openLaboratoryPatient(patient.uuid)}
                >
                  Open patient laboratory history
                </button>
              </p>
            ) : null}

            {patient && visitChoices.length === 0 ? (
              <Alert tone="warning" title="Visit needed">
                <p>Start a visit at Reception for this patient before creating a laboratory order.</p>
              </Alert>
            ) : null}

            {patient && visitChoices.length > 0 ? (
              <label>
                <span>Visit</span>
                <select value={visitUuid} onChange={(event) => setVisitUuid(event.target.value)}>
                  {visitChoices.map((visit) => (
                    <option key={visit.uuid} value={visit.uuid}>
                      {visit.visitType || "Visit"} · {visit.startDate || visit.startDatetime || "Visit"}
                      {visit.open ? "" : " · ended"}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </>
        ) : (
          <>
            <p className="lab-new-order__hint">
              External patients are billed for laboratory tests without hospital registration. Payment is
              collected separately by Accounts.
            </p>
            <label>
              <span>Search previous external patients</span>
              <input
                value={
                  selectedExternal
                    ? `${selectedExternal.patientName}${
                        selectedExternal.externalId ? ` · ${selectedExternal.externalId}` : ""
                      }`
                    : externalQuery
                }
                onChange={(event) => {
                  setSelectedExternal(null);
                  setExternalQuery(event.target.value);
                }}
                placeholder="Name, phone, or External Lab ID"
              />
            </label>
            {!selectedExternal && externalHits.length > 0 ? (
              <ul className="lab-new-order__hits">
                {externalHits.slice(0, 8).map((hit) => (
                  <li key={hit.externalId}>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedExternal(hit);
                        setBuyerName(hit.patientName || "");
                        setBuyerPhone(hit.buyerPhone || "");
                        setBuyerSex(hit.buyerSex || "");
                        setBuyerDob(hit.buyerDob || "");
                        setBuyerAddress(hit.buyerAddress || "");
                        if (hit.requestSource) {
                          setRequestSource(hit.requestSource);
                        }
                        setExternalHits([]);
                      }}
                    >
                      {hit.patientName}
                      {hit.buyerPhone ? ` · ${hit.buyerPhone}` : ""}
                      {hit.externalId ? ` · ${hit.externalId}` : ""}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
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
                <option value="external_referral">External Referral</option>
                <option value="laboratory_direct">Laboratory Direct</option>
              </select>
            </label>
          </>
        )}

        <div className="lab-order-panel__composer" ref={testBoxRef}>
          <label className="lab-order-panel__search-label" htmlFor="lab-direct-test-search">
            Add Laboratory Test
          </label>
          <input
            id="lab-direct-test-search"
            type="search"
            value={testQuery}
            placeholder="Search tests..."
            autoComplete="off"
            onFocus={() => setTestOpen(true)}
            onChange={(event) => {
              setTestQuery(event.target.value);
              setTestOpen(true);
            }}
          />
          {testOpen ? (
            <ul className="lab-order-panel__hits">
              {testQuery.trim().length < 2 ? (
                <li className="lab-order-panel__empty">
                  Type at least 2 letters to search the hospital laboratory catalogue.
                </li>
              ) : testHits.length === 0 ? (
                <li className="lab-order-panel__empty">
                  No matching hospital tests. Open Hospital Tests to add an existing test from the
                  master catalogue.
                </li>
              ) : (
                testHits.slice(0, 12).map((hit) => (
                  <li key={hit.conceptUuid || hit.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setDraft((current) => addTest(current, hit));
                        setTestQuery("");
                        setTestOpen(false);
                      }}
                    >
                      <strong>{hit.name}</strong>
                      <span>{labCatalogueHitDetails(hit)}</span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          ) : null}
        </div>

        {draft.length > 0 ? (
          <ul className="lab-order-panel__draft">
            {draft.map((item) => (
              <li key={item.conceptUuid}>
                <div>
                  <strong>{item.name}</strong>
                  <span>
                    {item.price?.formatted || "Price not set"}
                    {item.type ? ` · ${item.type}` : ""}
                    {item.specimen ? ` · ${item.specimen}` : ""}
                    {item.outsourced ? " · Outsourced" : ""}
                  </span>
                </div>
                {item.outsourced ? <Badge tone="warning">Outsourced</Badge> : null}
                <button
                  type="button"
                  className="lab-order-panel__remove"
                  onClick={() =>
                    setDraft((current) =>
                      current.filter((row) => row.conceptUuid !== item.conceptUuid),
                    )
                  }
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="lab-new-order__hint">
            Search the hospital catalogue and select configured tests or panels. Orders use the
            selected test identity, not free-text names.
          </p>
        )}

        <label>
          <span>Clinical indication</span>
          <textarea
            value={indication}
            onChange={(event) => setIndication(event.target.value)}
            rows={3}
            placeholder="Why these tests are needed (optional)"
          />
        </label>

        <div className="lab-new-order__actions">
          <Button
            disabled={patientKind === "registered" ? !canSubmitRegistered : !canSubmitExternal}
            onClick={() => void submit()}
          >
            {busy ? "Creating…" : "Create Lab Order"}
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
