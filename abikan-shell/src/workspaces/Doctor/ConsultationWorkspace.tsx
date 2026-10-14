import { useCallback, useEffect, useRef, useState } from "react";
import { consultationHref, openConsultation, returnToPreviousScreen } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { LoadingState } from "../../components/LoadingState";
import { AllergyPanel } from "../../components/AllergyPanel";
import { ClinicalAlertBar } from "../../components/ClinicalAlertBar";
import { ClinicalSection } from "../../components/ClinicalSection";
import { ConsultationFeeCard } from "./ConsultationFeeCard";
import { DiagnosisPanel } from "../../components/DiagnosisPanel";
import { PrescriptionPanel } from "../../components/PrescriptionPanel";
import { LabOrderPanel } from "../../components/LabOrderPanel";
import { LabOrderTable, LabResultTable } from "../../components/LabTables";
import { RadiologyOrderPanel } from "../../components/RadiologyOrderPanel";
import { RadiologyExaminationReports } from "../../components/RadiologyExaminationReports";
import { RadiologyOrderTable } from "../../components/RadiologyTables";
import { PatientAccountLink } from "../../components/PatientAccountLink";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import { MedicationAdministrationPanel } from "../../components/MedicationAdministrationPanel";
import { NursingNotesPanel } from "../../components/NursingNotesPanel";
import { VitalSignsCard } from "../../components/VitalSignsCard";
import { InpatientVitalsPanel } from "../../components/InpatientVitalsPanel";
import { receptionVisitTypeLabel } from "../../config/receptionVisitTypes";
import { formatDailyVisitNumber, visitNumberLabel } from "../../utils/dailyVisitNumber";
import { EncounterHistory } from "./EncounterHistory";
import { AntenatalCardView } from "../Antenatal/AntenatalCardView";
import { isAncVisitType } from "../Antenatal/antenatalView";
import { fetchAncSummary } from "../../services/antenatal";
import {
  confirmLeaveConsultation,
  setConsultationLeaveGuard,
} from "../../services/consultationLeaveGuard";
import { DocumentationPanel } from "../../components/DocumentationPanel";
import {
  diagnosesFromDraft,
  fetchOpenConsultationEncounter,
  fetchPatientDiagnoses,
  fetchProviderUuidForUser,
  saveConsultation,
  startOpdVisit,
  vitalObservationsFromDraft,
  type OpenConsultationEncounter,
  type VitalDraftValues,
} from "../../services/openmrs/clinicalEncounter";
import {
  cloneDocumentationDraft,
  documentationIsDirty,
  documentationObservationsFromDraft,
  emptyDocumentationDraft,
  fetchConsultationDocumentation,
  keepUnsavedDocumentation,
  validateDocumentationDraft,
  type DocumentationDraft,
} from "../../services/openmrs/clinicalDocumentation";
import {
  calculateBmi,
  fetchAllergyState,
  fetchDrugOrders,
  fetchPatientEncounters,
  fetchPatientIdentity,
  fetchPatientVisits,
  fetchVisitByUuid,
  fetchVitalHistory,
} from "../../services/openmrs/clinicalPatient";
import { fetchLabOrders, fetchLabResults } from "../../services/openmrs/laboratory";
import { fetchRadiologyNotesForVisit, fetchRadiologyOrdersForVisit } from "../../services/openmrs/radiology";
import { fetchRadiologyCharge } from "../../services/radiologyBilling";
import { radiologyBillingStatus } from "../Radiology/radiologyOrder";
import { OpenmrsRequestError } from "../../services/openmrs/client";
import {
  VISIT_NOT_STARTED_MESSAGE,
  visitHasStarted,
} from "../../services/openmrs/visitWindow";
import {
  buildDrugOrderPayload,
  careSettingForVisitType,
  collectNewDrugOrderUuids,
  isOpenmrsOrderUuid,
  medicationsForChart,
  type MedicationAdministrationMode,
  type OrderAdministration,
  type PrescriptionDraftItem,
} from "../../services/openmrs/drugOrders";
import {
  ensureMedicationSchedule,
  fetchInpatientStay,
  fetchMar,
  requestAdmission,
} from "../../services/inpatient";
import { PatientAccountRequestError } from "../../services/patientAccount";
import { announcePharmacyPrescriptions } from "../../services/pharmacy";
import {
  CLINICAL_BACK_LABEL,
  CLINICAL_LOAD_FAIL_BACK_LABEL,
  CONSULTATION_FLOW,
  LAB_ORDERS_EMPTY_DESCRIPTION,
  PREVIOUS_VISITS_DESCRIPTION,
} from "./doctorChart";
import type { InpatientStay } from "../../types/inpatient";
import type {
  AllergyState,
  DiagnosisDraftItem,
  DiagnosisRecord,
  DrugOrderSummary,
  EncounterSummary,
  LabOrderSummary,
  LabResultSummary,
  PatientIdentity,
  PatientVisitSummary,
  RadiologyNoteSummary,
  RadiologyOrderSummary,
  VitalReading,
  WorkspaceContext,
} from "../../types";
import {
  ADMIT_NURSING_ASSIGNS_BED,
  INPATIENT_ORDER_USES_ADMISSION,
  VISIT_MISMATCH_MESSAGE,
  VISIT_NOT_FOUND_MESSAGE,
  VISIT_NOT_SELECTED_MESSAGE,
  activeConsultationVisit,
  bindConsultationVisit,
  canRequestAdmission,
  clinicalOrderVisit,
  clinicalOrderVisitType,
  consultationVisitHeaderLabel,
  doctorVisitLocationLabel,
  orderBlockedReason,
  resolveClinicalOrderContext,
  shouldOfferStartOpdVisit,
} from "./consultationVisit";
import { MISSING_ATTENDING_DOCTOR, attendedByLabel } from "../../services/openmrs/visitAttendingProvider";
import "./ConsultationWorkspace.css";

interface ConsultationWorkspaceProps {
  patientUuid: string;
  selectedVisitUuid: string | null;
  context: WorkspaceContext;
}


function allergyStickyLabel(allergy: AllergyState): string {
  if (allergy.status === "recorded") {
    return allergy.items[0] ? `Allergy: ${allergy.items[0]}` : "Allergies recorded";
  }
  if (allergy.status === "unavailable") {
    return "Allergies unavailable";
  }
  return "Allergies: Not recorded";
}

export function ConsultationWorkspace({
  patientUuid,
  selectedVisitUuid,
  context,
}: ConsultationWorkspaceProps) {
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [visits, setVisits] = useState<PatientVisitSummary[]>([]);
  const [vitalHistory, setVitalHistory] = useState<Record<string, VitalReading[]>>({});
  const [bmi, setBmi] = useState<VitalReading | null>(null);
  const [diagnoses, setDiagnoses] = useState<DiagnosisRecord[]>([]);
  const [diagnosesUnavailable, setDiagnosesUnavailable] = useState(false);
  const [medications, setMedications] = useState<DrugOrderSummary[]>([]);
  const [wardAdministration, setWardAdministration] = useState<OrderAdministration[] | null>(null);
  const [medicationsUnavailable, setMedicationsUnavailable] = useState(false);
  const [encounters, setEncounters] = useState<EncounterSummary[]>([]);
  const [encountersUnavailable, setEncountersUnavailable] = useState(false);
  const [labOrders, setLabOrders] = useState<LabOrderSummary[]>([]);
  const [labResults, setLabResults] = useState<LabResultSummary[]>([]);
  const [labOrdersUnavailable, setLabOrdersUnavailable] = useState(false);
  const [labResultsUnavailable, setLabResultsUnavailable] = useState(false);
  const [radiologyOrders, setRadiologyOrders] = useState<RadiologyOrderSummary[]>([]);
  const [radiologyNotes, setRadiologyNotes] = useState<RadiologyNoteSummary[]>([]);
  const [radiologyOrdersUnavailable, setRadiologyOrdersUnavailable] = useState(false);
  const [radiologyNotesUnavailable, setRadiologyNotesUnavailable] = useState(false);
  const [allergyState, setAllergyState] = useState<AllergyState>({
    status: "none-recorded",
  });
  const [loading, setLoading] = useState(true);
  const [showFullHistory, setShowFullHistory] = useState(false);
  const [stuck, setStuck] = useState(false);
  const [vitalDraft, setVitalDraft] = useState<VitalDraftValues | null>(null);
  const [diagnosisDraft, setDiagnosisDraft] = useState<DiagnosisDraftItem[]>([]);
  const [prescriptionDraft, setPrescriptionDraft] = useState<PrescriptionDraftItem[]>([]);
  const [documentationDraft, setDocumentationDraft] = useState<DocumentationDraft>(
    emptyDocumentationDraft,
  );
  const [documentationRecorded, setDocumentationRecorded] = useState<DocumentationDraft>(
    emptyDocumentationDraft,
  );
  const [consultationEncounter, setConsultationEncounter] =
    useState<OpenConsultationEncounter | null>(null);
  const [saveState, setSaveState] = useState<
    "idle" | "saving" | "saved" | "error" | "starting-visit"
  >("idle");
  const [saveMessage, setSaveMessage] = useState("");
  const [stay, setStay] = useState<InpatientStay | null>(null);
  const [admitBusy, setAdmitBusy] = useState(false);
  const [admitMessage, setAdmitMessage] = useState("");
  const [hasAnc, setHasAnc] = useState(false);
  const [extraVisit, setExtraVisit] = useState<{
    visit: PatientVisitSummary;
    patientUuid: string;
  } | null | undefined>(undefined);
  const identityRef = useRef<HTMLDivElement>(null);
  const prescribeLock = useRef(false);
  const documentationDraftRef = useRef(documentationDraft);
  const documentationRecordedRef = useRef(documentationRecorded);
  documentationDraftRef.current = documentationDraft;
  documentationRecordedRef.current = documentationRecorded;
  const dirty =
    vitalDraft != null ||
    diagnosisDraft.length > 0 ||
    prescriptionDraft.length > 0 ||
    documentationIsDirty(documentationDraft, documentationRecorded);

  const loadClinical = useCallback((options?: { preserveUnsaved?: boolean }) => {
    let cancelled = false;
    setLoading(true);
    const preserveUnsaved = Boolean(options?.preserveUnsaved);
    const recordedAtStart = cloneDocumentationDraft(documentationRecordedRef.current);
    const keepNotes = keepUnsavedDocumentation(
      preserveUnsaved,
      documentationDraftRef.current,
      recordedAtStart,
    );
    if (!keepNotes) {
      const emptyDocs = emptyDocumentationDraft();
      setDocumentationRecorded(cloneDocumentationDraft(emptyDocs));
      setDocumentationDraft(cloneDocumentationDraft(emptyDocs));
    }
    fetchInpatientStay(patientUuid)
      .catch(() => null)
      .then((stayValue) => {
        if (cancelled) {
          return Promise.resolve(null);
        }
        if (stayValue) {
          setStay(stayValue);
        } else {
          setStay(null);
        }
        const ipdVisitUuid =
          stayValue?.assignment && stayValue.patient?.uuid === patientUuid
            ? stayValue.visitUuid || ""
            : "";
        const radiologyVisitUuid = ipdVisitUuid || selectedVisitUuid || null;
        const documentationVisitUuid = selectedVisitUuid || ipdVisitUuid || null;
        return Promise.allSettled([
      fetchPatientIdentity(patientUuid),
      fetchPatientVisits(patientUuid),
      fetchVitalHistory(patientUuid),
      fetchPatientDiagnoses(patientUuid),
      fetchDrugOrders(patientUuid),
      fetchAllergyState(patientUuid),
      fetchPatientEncounters(patientUuid),
      fetchLabOrders(patientUuid),
      fetchLabResults(patientUuid),
      fetchRadiologyOrdersForVisit(patientUuid, radiologyVisitUuid),
      fetchRadiologyNotesForVisit(patientUuid, radiologyVisitUuid),
      fetchRadiologyCharge(patientUuid).catch(() => null),
      fetchConsultationDocumentation(patientUuid, documentationVisitUuid),
    ]);
      })
      .then((results) => {
        if (!results || cancelled) {
          return;
        }
        const [
        identity,
        visitResult,
        vitalResult,
        conditionResult,
        drugResult,
        allergyResult,
        encounterResult,
        labOrderResult,
        labResultResult,
        radiologyOrderResult,
        radiologyNoteResult,
        radiologyChargeResult,
        documentationResult,
      ] = results;
        if (cancelled) {
          return;
        }
        if (identity.status === "fulfilled") {
          setPatient(identity.value);
        }
        if (visitResult.status === "fulfilled") {
          setVisits(visitResult.value);
        }
        if (vitalResult.status === "fulfilled") {
          setVitalHistory(vitalResult.value);
          setBmi(calculateBmi(vitalResult.value));
        }
        if (conditionResult.status === "fulfilled") {
          setDiagnoses(conditionResult.value);
          setDiagnosesUnavailable(false);
        } else {
          setDiagnosesUnavailable(true);
        }
        if (drugResult.status === "fulfilled") {
          setMedications(drugResult.value);
          setMedicationsUnavailable(false);
        } else {
          setMedicationsUnavailable(true);
        }
        if (allergyResult.status === "fulfilled") {
          setAllergyState(allergyResult.value);
        } else {
          setAllergyState({ status: "unavailable" });
        }
        if (encounterResult.status === "fulfilled") {
          setEncounters(encounterResult.value);
          setEncountersUnavailable(false);
        } else {
          setEncountersUnavailable(true);
        }
        if (labOrderResult.status === "fulfilled") {
          setLabOrders(labOrderResult.value);
          setLabOrdersUnavailable(false);
        } else {
          setLabOrders([]);
          setLabOrdersUnavailable(true);
        }
        if (labResultResult.status === "fulfilled") {
          setLabResults(labResultResult.value);
          setLabResultsUnavailable(false);
        } else {
          setLabResults([]);
          setLabResultsUnavailable(true);
        }
        if (radiologyOrderResult.status === "fulfilled") {
          const listedVisits =
            visitResult.status === "fulfilled" ? visitResult.value : [];
          const charges =
            radiologyChargeResult.status === "fulfilled" ? radiologyChargeResult.value : null;
          const exams = charges?.examinations ?? [];
          setRadiologyOrders(
            radiologyOrderResult.value.map((row) => {
              const exam = exams.find((item) => item.orderUuid === row.uuid);
              const visit = listedVisits.find((item) => item.uuid === row.visitUuid);
              return {
                ...row,
                dailyVisitNumber: visit?.dailyVisitNumber,
                visitType: row.visitType || visit?.visitType,
                billingStatus: exam
                  ? radiologyBillingStatus({
                      hasCharge: exam.hasCharge,
                      paymentStatus: exam.paymentStatus,
                    })
                  : "Price pending",
              };
            }),
          );
          setRadiologyOrdersUnavailable(false);
        } else {
          setRadiologyOrders([]);
          setRadiologyOrdersUnavailable(true);
        }
        if (radiologyNoteResult.status === "fulfilled") {
          setRadiologyNotes(radiologyNoteResult.value);
          setRadiologyNotesUnavailable(false);
        } else {
          setRadiologyNotes([]);
          setRadiologyNotesUnavailable(true);
        }
        if (documentationResult.status === "fulfilled") {
          const recorded = cloneDocumentationDraft(documentationResult.value);
          setDocumentationRecorded(recorded);
          const stillUnsaved = keepUnsavedDocumentation(
            preserveUnsaved,
            documentationDraftRef.current,
            recordedAtStart,
          );
          setDocumentationDraft(stillUnsaved ? cloneDocumentationDraft(documentationDraftRef.current) : recorded);
        } else if (!keepNotes) {
          const empty = emptyDocumentationDraft();
          setDocumentationRecorded(empty);
          setDocumentationDraft(empty);
        }
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patientUuid, selectedVisitUuid]);

  useEffect(() => {
    return loadClinical();
  }, [loadClinical]);

  useEffect(() => {
    let cancelled = false;
    setHasAnc(false);
    fetchAncSummary(patientUuid)
      .then((summary) => {
        if (!cancelled) {
          setHasAnc(Boolean(summary.hasAnc));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHasAnc(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [patientUuid]);

  const boundVisit = bindConsultationVisit({
    selectedVisitUuid,
    patientUuid,
    visits,
    extraVisit,
  });
  const activeVisit = activeConsultationVisit(boundVisit);
  const orderContext = resolveClinicalOrderContext({
    patientUuid,
    selectedVisit: activeVisit,
    stay,
    visits,
  });
  const orderVisit = clinicalOrderVisit(orderContext);
  const defaultAdministrationMode: MedicationAdministrationMode =
    orderVisit?.visitType === "IPD" ? "INPATIENT" : "HOME";
  const usingInpatientOrders =
    orderContext.status === "ready" && orderContext.source === "active-admission";

  useEffect(() => {
    if (!selectedVisitUuid) {
      setExtraVisit(undefined);
      return;
    }
    if (visits.some((visit) => visit.uuid === selectedVisitUuid)) {
      setExtraVisit(undefined);
      return;
    }
    if (loading) {
      return;
    }
    let cancelled = false;
    fetchVisitByUuid(selectedVisitUuid).then((result) => {
      if (!cancelled) {
        setExtraVisit(result);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [selectedVisitUuid, visits, loading]);

  useEffect(() => {
    if (!orderVisit) {
      setConsultationEncounter(null);
      return;
    }
    let cancelled = false;
    fetchOpenConsultationEncounter(orderVisit.uuid)
      .then((encounter) => {
        if (!cancelled) {
          setConsultationEncounter(encounter);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setConsultationEncounter(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [orderVisit?.uuid]);

  useEffect(() => {
    setConsultationLeaveGuard({
      dirty,
      hash: consultationHref(patientUuid, selectedVisitUuid),
    });
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) {
        return;
      }
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      setConsultationLeaveGuard({ dirty: false, hash: "" });
    };
  }, [dirty, patientUuid, selectedVisitUuid]);

  useEffect(() => {
    const node = identityRef.current;
    if (!node) {
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        setStuck(!entry.isIntersecting);
      },
      { threshold: 0, rootMargin: "-8px 0px 0px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [patient]);

  const [activeSection, setActiveSection] = useState("allergies");

  const openVisit = activeVisit?.open ? activeVisit : null;
  const currentVisit = activeVisit;
  const isHistoricalVisit = Boolean(activeVisit && !activeVisit.open);
  const canWrite = !isHistoricalVisit && Boolean(orderVisit);
  const canWriteDocumentation =
    canWrite &&
    (!selectedVisitUuid || !orderVisit || selectedVisitUuid === orderVisit.uuid);
  const inpatientSelected =
    (activeVisit?.visitType || "").toUpperCase() === "IPD" || usingInpatientOrders;
  const chartVisitUuid = currentVisit?.uuid || "";
  const chartIsInpatient = (currentVisit?.visitType || "").toUpperCase() === "IPD";
  useEffect(() => {
    if (!chartIsInpatient || !chartVisitUuid) {
      setWardAdministration(null);
      return;
    }
    let cancelled = false;
    fetchMar(patientUuid, chartVisitUuid)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setWardAdministration(
          payload.orders.map((order) => ({
            orderUuid: order.orderUuid,
            slots: order.slots.map((slot) => ({
              status: slot.status,
              outcome: slot.administration?.outcome,
            })),
          })),
        );
      })
      .catch(() => {
        if (!cancelled) {
          setWardAdministration(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [chartIsInpatient, patientUuid, chartVisitUuid]);
  const chartMedications = medicationsForChart(medications, {
    visitUuid: chartVisitUuid,
    inpatient: chartIsInpatient,
    administration: wardAdministration,
  });
  const visitStarted = visitHasStarted(orderVisit?.startDatetime);
  const canRecordOpdVitals =
    Boolean(openVisit) && (openVisit?.visitType || "").toUpperCase() !== "IPD";
  const showAncCard =
    isAncVisitType(currentVisit?.visitType) ||
    isAncVisitType(openVisit?.visitType) ||
    hasAnc;
  const consultationFlow = CONSULTATION_FLOW.filter(
    (item) => item.id !== "anc" || showAncCard,
  );
  useEffect(() => {
    const nodes = consultationFlow
      .map((item) => document.getElementById(item.id))
      .filter((node): node is HTMLElement => Boolean(node));
    if (nodes.length === 0) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        if (visible?.target.id) {
          setActiveSection(visible.target.id);
        }
      },
      { rootMargin: "-15% 0px -60% 0px", threshold: [0.15, 0.4] },
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [consultationFlow, loading, showAncCard]);
  const offerStartOpd =
    !isHistoricalVisit &&
    shouldOfferStartOpdVisit({
      orderContext,
      stay,
      patientUuid,
    });
  const visitProblem =
    boundVisit.status === "missing"
      ? VISIT_NOT_FOUND_MESSAGE
      : boundVisit.status === "mismatch"
        ? VISIT_MISMATCH_MESSAGE
        : boundVisit.status === "no-selection" && !usingInpatientOrders
          ? VISIT_NOT_SELECTED_MESSAGE
          : "";

  const goBack = () => {
    if (!confirmLeaveConsultation()) {
      return;
    }
    returnToPreviousScreen("#/doctor");
  };

  const handleStartVisit = async () => {
    if (stay?.assignment && stay.patient?.uuid === patientUuid) {
      setSaveState("error");
      setSaveMessage(
        "This patient is already admitted. Use the current admission instead of starting another visit.",
      );
      return;
    }
    setSaveState("starting-visit");
    setSaveMessage("");
    try {
      const started = await startOpdVisit({
        patientUuid,
        locationUuid: context.location.uuid,
      });
      openConsultation(patientUuid, started.uuid);
      setSaveState("idle");
      setSaveMessage("OPD visit started. You can record vitals and save the consultation.");
    } catch (error) {
      setSaveState("error");
      setSaveMessage(
        error instanceof OpenmrsRequestError
          ? error.message
          : "The visit could not be started.",
      );
    }
  };

  const handleAdmitPatient = async () => {
    if (!canRequestAdmission(stay, patientUuid)) {
      setAdmitMessage(
        stay?.assignment
          ? `This patient is already admitted to ${stay.assignment.areaName} · ${stay.assignment.bedNumber}.`
          : "Admission requested. Nursing will assign a bed.",
      );
      return;
    }
    setAdmitBusy(true);
    setAdmitMessage("");
    try {
      const result = await requestAdmission(
        patientUuid,
        openVisit?.uuid || "",
        context.location.uuid,
      );
      if (result.patient?.uuid && result.patient.uuid !== patientUuid) {
        throw new PatientAccountRequestError(
          "This admission does not belong to this patient.",
          409,
          "wrong_patient",
        );
      }
      setStay((current) => ({ ...(current ?? result), ...result, awaiting: true }));
      setAdmitMessage(result.message || "Admission requested. Nursing will assign a bed.");
      const admittedVisit = (result.visitUuid || "").trim();
      if (admittedVisit) {
        openConsultation(patientUuid, admittedVisit);
      }
    } catch (error) {
      setAdmitMessage(
        error instanceof PatientAccountRequestError || error instanceof OpenmrsRequestError
          ? error.message
          : "We couldn't complete the admission request. Please try again.",
      );
    } finally {
      setAdmitBusy(false);
    }
  };

  const drugOrdersFromDraft = () =>
    prescriptionDraft.map((item) =>
      buildDrugOrderPayload(
        item,
        item.administrationMode === "INPATIENT"
          ? "INPATIENT"
          : "OUTPATIENT",
      ),
    );

  const announceNewPrescriptions = async (priorUuids: Set<string>, expectedCount: number) => {
    if (expectedCount <= 0) {
      return;
    }
    try {
      // One immediate read; server retries if Bahmni has not surfaced the order yet.
      const created = await collectNewDrugOrderUuids(patientUuid, priorUuids, {
        expectedCount,
        delaysMs: [0],
      });
      await announcePharmacyPrescriptions({
        orderUuids: created,
        patientUuid,
        priorOrderUuids: [...priorUuids].filter(isOpenmrsOrderUuid),
        expectedCount,
      });
    } catch {
      // Clinical write already succeeded; Pharmacy can still see the order on the queue.
    }
  };

  const confirmIpdSchedule = async (hadDrugs: boolean): Promise<string> => {
    if (
      !hadDrugs ||
      careSettingForVisitType(orderVisit?.visitType) !== "INPATIENT" ||
      !prescriptionDraft.some((item) => item.administrationMode === "INPATIENT")
    ) {
      return "";
    }
    try {
      const result = await ensureMedicationSchedule(patientUuid);
      const issue = result.issues?.[0];
      if (!issue) {
        return "";
      }
      if (
        (result.createdOrderUuids?.length || result.alreadyScheduledOrderUuids?.length) &&
        issue.message
      ) {
        return issue.message;
      }
      return (
        issue.message ||
        "The prescription was saved, but the ward schedule could not be created. Try again."
      );
    } catch (error) {
      return error instanceof PatientAccountRequestError
        ? error.message
        : "The prescription was saved, but the ward schedule could not be created. Try again.";
    }
  };

  const handleSaveConsultation = async () => {
    const documentationError = validateDocumentationDraft(documentationDraft);
    if (documentationError) {
      setSaveState("error");
      setSaveMessage(documentationError);
      return;
    }
    const observations = [
      ...(vitalDraft && canRecordOpdVitals && !usingInpatientOrders
        ? vitalObservationsFromDraft(vitalDraft)
        : []),
      ...(canWriteDocumentation
        ? documentationObservationsFromDraft(documentationDraft, documentationRecorded)
        : []),
    ];
    const bahmniDiagnoses = diagnosesFromDraft(diagnosisDraft);
    const drugOrders = drugOrdersFromDraft();
    if (
      !orderVisit ||
      (observations.length === 0 && bahmniDiagnoses.length === 0 && drugOrders.length === 0)
    ) {
      return;
    }
    if (!visitHasStarted(orderVisit.startDatetime)) {
      setSaveState("error");
      setSaveMessage(VISIT_NOT_STARTED_MESSAGE);
      return;
    }
    if (prescribeLock.current || saveState === "saving") {
      return;
    }
    prescribeLock.current = true;
    setSaveState("saving");
    setSaveMessage("");
    try {
      const priorOrderUuids = new Set(
        medications.map((row) => row.uuid).filter(isOpenmrsOrderUuid),
      );
      const providerUuid = await fetchProviderUuidForUser(context.userUuid);
      const saved = await saveConsultation({
        patientUuid,
        visitUuid: orderVisit.uuid,
        visitType: clinicalOrderVisitType(orderVisit.visitType),
        visitStartDatetime: orderVisit.startDatetime,
        locationUuid: context.location.uuid,
        providerUuid,
        encounterUuid: consultationEncounter?.uuid,
        encounterDateTime: consultationEncounter?.encounterDatetime,
        observations,
        bahmniDiagnoses,
        drugOrders,
      });
      if (saved.encounterUuid) {
        setConsultationEncounter({
          uuid: saved.encounterUuid,
          encounterDatetime: consultationEncounter?.encounterDatetime,
        });
      }
      if ((saved.savedDrugCount || 0) > 0) {
        await announceNewPrescriptions(priorOrderUuids, saved.savedDrugCount || drugOrders.length);
      }
      const scheduleError = await confirmIpdSchedule((saved.savedDrugCount || 0) > 0);
      setVitalDraft(null);
      setDiagnosisDraft([]);
      setPrescriptionDraft([]);
      const alreadyPrescribed = saved.alreadyPrescribed ?? [];
      if (scheduleError) {
        setSaveState("error");
        setSaveMessage(scheduleError);
      } else if (alreadyPrescribed.length && (saved.savedDrugCount || 0) > 0) {
        setSaveState("saved");
        setSaveMessage(
          `${alreadyPrescribed.join(", ")} is already prescribed. The other medicines were saved.`,
        );
      } else if (alreadyPrescribed.length && drugOrders.length > 0) {
        setSaveState("error");
        setSaveMessage("This medicine is already prescribed for this patient.");
      } else {
        setSaveState("saved");
        setSaveMessage("Consultation saved successfully.");
      }
      loadClinical();
    } catch (error) {
      setSaveState("error");
      setSaveMessage(
        error instanceof OpenmrsRequestError
          ? error.message.includes("more than one")
            ? "This medicine is already prescribed for this patient."
            : error.message
          : "The consultation could not be saved.",
      );
    } finally {
      prescribeLock.current = false;
    }
  };

  const handlePrescribe = async () => {
    if (!orderVisit || prescriptionDraft.length === 0) {
      return;
    }
    if (!visitHasStarted(orderVisit.startDatetime)) {
      setSaveState("error");
      setSaveMessage(VISIT_NOT_STARTED_MESSAGE);
      return;
    }
    if (prescribeLock.current || saveState === "saving") {
      return;
    }
    prescribeLock.current = true;
    setSaveState("saving");
    setSaveMessage("");
    try {
      const priorOrderUuids = new Set(
        medications.map((row) => row.uuid).filter(isOpenmrsOrderUuid),
      );
      const drugOrders = drugOrdersFromDraft();
      const providerUuid = await fetchProviderUuidForUser(context.userUuid);
      const saved = await saveConsultation({
        patientUuid,
        visitUuid: orderVisit.uuid,
        visitType: clinicalOrderVisitType(orderVisit.visitType),
        visitStartDatetime: orderVisit.startDatetime,
        locationUuid: context.location.uuid,
        providerUuid,
        encounterUuid: consultationEncounter?.uuid,
        encounterDateTime: consultationEncounter?.encounterDatetime,
        drugOrders,
      });
      if (saved.encounterUuid) {
        setConsultationEncounter({
          uuid: saved.encounterUuid,
          encounterDatetime: consultationEncounter?.encounterDatetime,
        });
      }
      if ((saved.savedDrugCount || 0) > 0) {
        await announceNewPrescriptions(priorOrderUuids, saved.savedDrugCount || drugOrders.length);
      }
      const scheduleError = await confirmIpdSchedule((saved.savedDrugCount || 0) > 0);
      const alreadyPrescribed = saved.alreadyPrescribed ?? [];
      if ((saved.savedDrugCount || 0) > 0) {
        setPrescriptionDraft([]);
      }
      if (scheduleError) {
        setSaveState("error");
        setSaveMessage(scheduleError);
      } else if (alreadyPrescribed.length && (saved.savedDrugCount || 0) > 0) {
        setSaveState("saved");
        setSaveMessage(
          `${alreadyPrescribed.join(", ")} is already prescribed. The other medicines were saved.`,
        );
      } else if (alreadyPrescribed.length) {
        setSaveState("error");
        setSaveMessage("This medicine is already prescribed for this patient.");
      } else {
        setSaveState("saved");
        setSaveMessage("Prescription saved.");
      }
      loadClinical({ preserveUnsaved: true });
    } catch (error) {
      setSaveState("error");
      setSaveMessage(
        error instanceof OpenmrsRequestError
          ? error.message.includes("more than one")
            ? "This medicine is already prescribed for this patient."
            : error.message
          : "The prescription could not be saved.",
      );
    } finally {
      prescribeLock.current = false;
    }
  };
  const recentVisits = visits.slice(0, 3);
  const historyVisits = showFullHistory ? visits : recentVisits;

  if (!patient && !loading) {
    return (
      <div className="consult">
        <p>This patient record could not be loaded.</p>
        <Button variant="secondary" onClick={() => returnToPreviousScreen("#/doctor")}>
          {CLINICAL_LOAD_FAIL_BACK_LABEL}
        </Button>
      </div>
    );
  }

  return (
    <div className="consult">
      <div className={`consult-sticky ${stuck && patient ? "is-on" : ""}`}>
        {patient ? (
          <div className="consult-sticky__inner">
            <strong>{patient.name}</strong>
            <span>{patient.mrn}</span>
            <span>
              {patient.age === "—" ? "Age not recorded" : `${patient.age} years`}
            </span>
            <span
              className={
                allergyState.status === "recorded"
                  ? "consult-sticky__allergy is-recorded"
                  : "consult-sticky__allergy"
              }
            >
              {allergyStickyLabel(allergyState)}
            </span>
            <span>
              {currentVisit
                ? [
                    visitNumberLabel(currentVisit.dailyVisitNumber),
                    receptionVisitTypeLabel(currentVisit.visitType),
                    currentVisit.startDate,
                  ]
                    .filter((part) => part && part !== "—")
                    .join(" · ")
                : "No visit selected"}
            </span>
          </div>
        ) : null}
      </div>

      <div className="consult__nav">
        <Button variant="ghost" onClick={goBack}>
          {CLINICAL_BACK_LABEL}
        </Button>
        <div className="abikan-account-nav">
          <PatientAccountLink patientUuid={patientUuid} visitUuid={selectedVisitUuid} />
        </div>
      </div>

      <div className="consult__top">
        <div ref={identityRef}>
          {patient ? (
            <PatientIdentityHeader
              compact
              patient={patient}
              queueNumber={
                formatDailyVisitNumber(currentVisit?.dailyVisitNumber) === "—"
                  ? undefined
                  : formatDailyVisitNumber(currentVisit?.dailyVisitNumber)
              }
              visitLabel={
                currentVisit
                  ? [
                      consultationVisitHeaderLabel(currentVisit),
                      currentVisit.startDate !== "—" ? currentVisit.startDate : "",
                      doctorVisitLocationLabel(currentVisit.location),
                      attendedByLabel(currentVisit.attendedBy) !== MISSING_ATTENDING_DOCTOR
                        ? attendedByLabel(currentVisit.attendedBy)
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")
                  : undefined
              }
            />
          ) : (
            <LoadingState variant="inline" label="Loading patient record…" />
          )}
        </div>

        {activeVisit ? (
          <ConsultationFeeCard
            patientUuid={patientUuid}
            patientName={patient?.name}
            patientMrn={patient?.mrn}
            visitUuid={activeVisit.uuid}
            readOnly={isHistoricalVisit}
          />
        ) : null}
      </div>

      <div className="consult__sheet">
      <div className="consult__main">
      <ClinicalSection
        id="allergies"
        title="Allergies"
      >
        <ClinicalAlertBar
          allergy={allergyState}
          diagnoses={diagnoses}
          diagnosesUnavailable={diagnosesUnavailable}
          medications={chartMedications}
          medicationsUnavailable={medicationsUnavailable}
        />
        <AllergyPanel
          patientUuid={patientUuid}
          allergy={allergyState}
          readOnly={isHistoricalVisit}
          onChanged={setAllergyState}
        />
      </ClinicalSection>

      {showAncCard ? (
        <ClinicalSection
          id="anc"
          title="ANC Card"
          description="Antenatal pregnancy card and visit measurements."
        >
          <AntenatalCardView
            patientUuid={patientUuid}
            patientName={patient?.name}
            patientMrn={patient?.mrn}
            patientDob={patient?.birthdate}
            openmrsVisitUuid={activeVisit?.uuid}
            canEdit={!isHistoricalVisit}
          />
        </ClinicalSection>
      ) : null}

      {visitProblem && !loading ? (
        <Alert
          tone={
            boundVisit.status === "missing" || boundVisit.status === "mismatch"
              ? "danger"
              : "warning"
          }
          title={
            boundVisit.status === "missing" || boundVisit.status === "mismatch"
              ? "This visit could not be opened"
              : boundVisit.status === "no-selection"
                ? "No visit selected"
                : "No open visit"
          }
        >
          <p>{visitProblem}</p>
        </Alert>
      ) : null}

      {boundVisit.status === "selected" && !openVisit && !usingInpatientOrders && !loading ? (
        <Alert tone="warning" title="This visit is closed">
          <p>Documentation cannot be saved on a closed visit.</p>
        </Alert>
      ) : null}

      {usingInpatientOrders && !loading ? (
        <Alert tone="info" title="Current admission">
          <p>{INPATIENT_ORDER_USES_ADMISSION}</p>
        </Alert>
      ) : null}

      {offerStartOpd && !loading && visits.every((visit) => !visit.open) ? (
        <Alert tone="warning" title="No open visit">
          <p>
            An open OPD visit is required before a consultation can be saved.
            Existing visits on this record are already closed.
          </p>
          <div className="consult__visit-action">
            <Button
              variant="secondary"
              busy={saveState === "starting-visit"}
              busyLabel="Creating visit..."
              onClick={() => void handleStartVisit()}
            >
              Start OPD visit
            </Button>
          </div>
        </Alert>
      ) : null}

      {orderVisit && !visitStarted && !loading ? (
        <Alert tone="warning" title="Visit has not started">
          <p>{VISIT_NOT_STARTED_MESSAGE}</p>
        </Alert>
      ) : null}

      {saveMessage ? (
        <Alert
          tone={saveState === "error" ? "danger" : saveState === "saved" ? "success" : "info"}
          title={
            saveState === "error"
              ? "Could not save"
              : saveState === "saved"
                ? "Saved"
                : "Visit"
          }
        >
          <p>{saveMessage}</p>
        </Alert>
      ) : null}

      <div id="vitals">
        {inpatientSelected ? null : (
          <VitalSignsCard
            history={vitalHistory}
            bmi={bmi}
            loading={loading}
            canRecord={canRecordOpdVitals}
            recordBlockedReason={
              loading ? undefined : "Start an open OPD visit to record vitals."
            }
            draft={vitalDraft}
            onDraftChange={setVitalDraft}
          />
        )}
        <InpatientVitalsPanel
          patientUuid={patientUuid}
          canRecord={false}
          visitUuid={selectedVisitUuid ?? undefined}
          hideWhenNotAdmitted
        />
      </div>

      <ClinicalSection
        id="document"
        variant="panel"
        title="History and Examinations"
      >
        <DocumentationPanel
          draft={documentationDraft}
          recorded={documentationRecorded}
          canEdit={canWriteDocumentation}
          blockedReason={
            usingInpatientOrders && selectedVisitUuid && selectedVisitUuid !== orderVisit?.uuid
              ? "These notes belong to the selected visit. Open the current admission to add inpatient notes."
              : orderBlockedReason(orderContext, "document")
          }
          onChange={setDocumentationDraft}
        />
      </ClinicalSection>

      <NursingNotesPanel
        patientUuid={patientUuid}
        canCreate={false}
        hideWhenEmptyAndNotAdmitted
      />

      <MedicationAdministrationPanel
        patientUuid={patientUuid}
        patientName={patient?.name || "Patient"}
        canRecord={false}
        visitUuid={selectedVisitUuid ?? undefined}
        hideWhenNotAdmitted
      />

      <ClinicalSection
        id="visits"
        variant="panel"
        title="Visits"
        description={PREVIOUS_VISITS_DESCRIPTION}
        action={
          visits.length > 3 ? (
            <button
              type="button"
              className="consult__link"
              onClick={() => setShowFullHistory((value) => !value)}
            >
              {showFullHistory ? "Show recent only" : "View all visits"}
            </button>
          ) : null
        }
      >
        {visits.length === 0 && encounters.length === 0 && !encountersUnavailable ? (
          <p className="consult__muted">No previous visits recorded.</p>
        ) : (
          <div className="consult__history">
            <ol className="consult__timeline">
              {historyVisits.map((visit) => {
                const current = visit.uuid === activeVisit?.uuid;
                return (
                  <li key={visit.uuid} className={current ? "is-current" : undefined}>
                    <button
                      type="button"
                      className="consult__visit-pick"
                      onClick={() => {
                        if (current) {
                          return;
                        }
                        if (!confirmLeaveConsultation()) {
                          return;
                        }
                        openConsultation(patientUuid, visit.uuid);
                      }}
                    >
                      <p className="consult__timeline-date">{visit.startDate}</p>
                      <p className="consult__timeline-title">
                        {visitNumberLabel(visit.dailyVisitNumber)}
                        {current ? " · This visit" : ""}
                      </p>
                      <p className="consult__timeline-title">
                        {receptionVisitTypeLabel(visit.visitType)}
                        {visit.open ? " · Open" : ""}
                      </p>
                      <p className="consult__muted">
                        Attended by: {attendedByLabel(visit.attendedBy)}
                      </p>
                      {doctorVisitLocationLabel(visit.location) || visit.start !== "—" ? (
                        <p className="consult__muted">
                          {[doctorVisitLocationLabel(visit.location), visit.start !== "—" ? visit.start : ""]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ol>
            <EncounterHistory
              patientUuid={patientUuid}
              encounters={encounters}
              unavailable={encountersUnavailable}
              showAll={showFullHistory}
            />
          </div>
        )}
      </ClinicalSection>

      <ClinicalSection
        id="diagnose"
        variant="panel"
        title="Diagnoses"
      >
        <DiagnosisPanel
          recorded={diagnoses}
          recordedUnavailable={diagnosesUnavailable}
          draft={diagnosisDraft}
          canEdit={canWrite}
          onChange={setDiagnosisDraft}
        />
      </ClinicalSection>

      <ClinicalSection
        variant="panel"
        title="Orders"
      >
        <div className="consult__orders">
          <div id="laboratory">
            <h4>Lab Investigations</h4>
            {labOrdersUnavailable ? (
              <p className="consult__muted">Laboratory orders unavailable</p>
            ) : (
              <LabOrderTable
                rows={labOrders}
                loading={loading}
                showPatient={false}
                showAction={false}
                emptyTitle="No laboratory orders"
                emptyDescription={LAB_ORDERS_EMPTY_DESCRIPTION}
              />
            )}
            <LabOrderPanel
              patientUuid={patientUuid}
              visitUuid={orderVisit?.uuid}
              visitStartDatetime={orderVisit?.startDatetime}
              encounterUuid={consultationEncounter?.uuid}
              locationUuid={context.location.uuid}
              canEdit={canWrite}
              blockedReason={orderBlockedReason(orderContext, "laboratory")}
              onSaved={(encounterUuid) => {
                if (encounterUuid) {
                  setConsultationEncounter({
                    uuid: encounterUuid,
                    encounterDatetime: consultationEncounter?.encounterDatetime,
                  });
                }
                setSaveState("saved");
                setSaveMessage("Laboratory order saved.");
                loadClinical({ preserveUnsaved: true });
              }}
            />
          </div>
          <div>
            <h4>Lab Results</h4>
            {labResultsUnavailable ? (
              <p className="consult__muted">Laboratory results unavailable</p>
            ) : (
              <LabResultTable
                rows={labResults}
                loading={loading}
                emptyTitle="No laboratory results"
                emptyDescription="Results appear here when the laboratory releases them."
              />
            )}
          </div>
          <div id="radiology">
            <h4>Radiology Orders</h4>
            {radiologyOrdersUnavailable ? (
              <p className="consult__muted">Radiology orders unavailable</p>
            ) : (
              <RadiologyOrderTable
                rows={radiologyOrders}
                notes={radiologyNotes}
                patientUuid={patientUuid}
                visitUuid={orderVisit?.uuid || selectedVisitUuid || ""}
                loading={loading}
                showPatient={false}
                showAction={false}
                showVisit={false}
                emptyTitle="No radiology orders"
                emptyDescription="No imaging orders on this visit yet."
              />
            )}
            <RadiologyOrderPanel
              patientUuid={patientUuid}
              visitUuid={orderVisit?.uuid}
              visitStartDatetime={orderVisit?.startDatetime}
              encounterUuid={consultationEncounter?.uuid}
              locationUuid={context.location.uuid}
              canEdit={canWrite}
              blockedReason={orderBlockedReason(orderContext, "imaging")}
              onSaved={(encounterUuid) => {
                if (encounterUuid) {
                  setConsultationEncounter({
                    uuid: encounterUuid,
                    encounterDatetime: consultationEncounter?.encounterDatetime,
                  });
                }
                setSaveState("saved");
                setSaveMessage("Radiology order created.");
                loadClinical({ preserveUnsaved: true });
              }}
            />
          </div>
          <div>
            <h4>Radiology</h4>
            {radiologyOrdersUnavailable || radiologyNotesUnavailable ? (
              <p className="consult__muted">Radiology reports unavailable</p>
            ) : (
              <RadiologyExaminationReports
                orders={radiologyOrders}
                notes={radiologyNotes}
                patientUuid={patientUuid}
                visitUuid={orderVisit?.uuid || selectedVisitUuid}
                loading={loading}
              />
            )}
          </div>
        </div>
        <p className="consult__hint">Laboratory and imaging fees are paid at Accounts.</p>
      </ClinicalSection>

      <ClinicalSection
        id="prescribe"
        variant="panel"
        title="Treatments"
      >
        <PrescriptionPanel
          recorded={chartMedications}
          recordedUnavailable={medicationsUnavailable}
          loading={loading}
          draft={prescriptionDraft}
          canEdit={canWrite}
          blockedReason={orderBlockedReason(orderContext, "prescribe")}
          submitting={saveState === "saving"}
          defaultAdministrationMode={defaultAdministrationMode}
          allergyWarning={
            allergyState.status === "recorded" ? allergyState.items.join(", ") : ""
          }
          onChange={setPrescriptionDraft}
          onPrescribe={() => void handlePrescribe()}
        />
      </ClinicalSection>

      <ClinicalSection
        id="disposition"
        variant="panel"
        title="Disposition"
      >
        <div className="consult__disposition">
          <button
            type="button"
            disabled={
              admitBusy || isHistoricalVisit || !canRequestAdmission(stay, patientUuid)
            }
            onClick={() => void handleAdmitPatient()}
          >
            {admitBusy ? "Admitting…" : "Admit Patient"}
          </button>
        </div>
        {stay?.assignment ? (
          <p className="consult__hint">
            This patient is already admitted to {stay.assignment.areaName} · {stay.assignment.bedNumber}.
          </p>
        ) : stay?.awaiting || admitMessage ? (
          <p className="consult__hint">{admitMessage || "Admission requested. Nursing will assign a bed."}</p>
        ) : (
          <p className="consult__hint">{ADMIT_NURSING_ASSIGNS_BED}</p>
        )}
      </ClinicalSection>
      </div>
      <nav className="consult__index" aria-label="Consultation sections">
        {consultationFlow.map((item) => (
          <button
            key={item.id}
            type="button"
            className={activeSection === item.id ? "is-active" : undefined}
            onClick={() => {
              setActiveSection(item.id);
              document.getElementById(item.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          >
            {item.label}
          </button>
        ))}
      </nav>
      </div>

      <div className="consult__savebar">
        <div>
          <p className="consult__savebar-title">
            {saveState === "saving" ? "Saving consultation…" : "Save consultation"}
          </p>
          <p className="consult__savebar-copy">
            {orderVisit && !visitStarted
              ? VISIT_NOT_STARTED_MESSAGE
              : dirty
                ? "Draft items are saved only when you save this consultation."
                : canWrite
                  ? "Add a chief complaint, notes, vitals, diagnoses, or a prescription, then save."
                  : orderBlockedReason(orderContext, "save")}
          </p>
        </div>
        <Button
          variant="primary"
          disabled={!dirty || !canWrite || !visitStarted}
          busy={saveState === "saving"}
          busyLabel="Saving consultation…"
          onClick={() => void handleSaveConsultation()}
        >
          Save consultation
        </Button>
      </div>
    </div>
  );
}
