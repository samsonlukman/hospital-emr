import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  consultationHref,
  parseShellHash,
  readConsultationVisitUuid,
} from "../../app/hashRoute.ts";
import { DOCTOR_NAV } from "../../config/doctorNav.ts";
import { optionalSectionsVisibleInWorkspace } from "../../config/optionalClinicalSections.ts";
import {
  NO_CHIEF_COMPLAINT_FOR_VISIT,
  NO_CLINICAL_NOTES_FOR_VISIT,
  NO_HISTORY_FOR_VISIT,
} from "../../services/openmrs/clinicalDocumentation.ts";
import type { PatientVisitSummary } from "../../types/index.ts";
import { doctorCannotSetRadiologyPrice } from "../Radiology/radiologyPrice.ts";
import {
  bindConsultationVisit,
  firstOpenVisit,
  VISIT_MISMATCH_MESSAGE,
  VISIT_NOT_FOUND_MESSAGE,
  VISIT_NOT_SELECTED_MESSAGE,
} from "./consultationVisit.ts";
import {
  CLINICAL_BACK_LABEL,
  CLINICAL_LOAD_FAIL_BACK_LABEL,
  CONSULTATION_FLOW,
  LAB_ORDERS_EMPTY_DESCRIPTION,
  PREVIOUS_VISITS_DESCRIPTION,
} from "./doctorChart.ts";
import { myPatientsHref, radiologyOrdererDoesNotQualifyForMyPatients } from "./myPatients.ts";

const CHART_SOURCE = readFileSync(
  fileURLToPath(new URL("./ConsultationWorkspace.tsx", import.meta.url)),
  "utf8",
);
const FEE_SOURCE = readFileSync(
  fileURLToPath(new URL("./ConsultationFeeCard.tsx", import.meta.url)),
  "utf8",
);
const RAD_ORDER_SOURCE = readFileSync(
  fileURLToPath(new URL("../../components/RadiologyOrderPanel.tsx", import.meta.url)),
  "utf8",
);
const RX_SOURCE = readFileSync(
  fileURLToPath(new URL("../../components/PrescriptionPanel.tsx", import.meta.url)),
  "utf8",
);
const DESK_SOURCE = readFileSync(
  fileURLToPath(new URL("./DoctorWorkspace.tsx", import.meta.url)),
  "utf8",
);
const MAP_SOURCE = readFileSync(
  fileURLToPath(new URL("../../config/workspaceMap.ts", import.meta.url)),
  "utf8",
);

function visit(overrides: Partial<PatientVisitSummary> & { uuid: string }): PatientVisitSummary {
  return {
    start: "04:16",
    startDate: "23 Aug 2026",
    startDatetime: "2026-08-23T03:16:00.000+0000",
    stop: null,
    visitType: "OPD",
    location: "OPD-1",
    open: true,
    dailyVisitNumber: "001",
    attendedBy: "",
    ...overrides,
  };
}

describe("Doctor Workspace audit", () => {
  it("keeps Today's Patients, My Patients, Pharmacy medicines, and Search as distinct Clinical destinations", () => {
    const items = DOCTOR_NAV[0]?.items ?? [];
    const dashboard = items.find((entry) => entry.id === "doctor-queue");
    const today = items.find((entry) => entry.id === "queue");
    const mine = items.find((entry) => entry.id === "my-patients");
    const medicines = items.find((entry) => entry.id === "pharmacy-medicines");
    const search = items.find((entry) => entry.id === "search");
    assert.equal(dashboard && "href" in dashboard ? dashboard.href : "", "#/doctor");
    assert.equal(today && "href" in today ? today.href : "", "#/doctor/queue");
    assert.equal(mine && "href" in mine ? mine.href : "", "#/doctor/my-patients");
    assert.equal(
      medicines && "href" in medicines ? medicines.href : "",
      "#/doctor/pharmacy-medicines",
    );
    assert.equal(search?.kind, "action");
    assert.equal(parseShellHash("#/doctor").section, null);
    assert.equal(parseShellHash("#/doctor/queue").section, "queue");
    assert.equal(parseShellHash("#/doctor/my-patients").section, "my-patients");
    assert.equal(parseShellHash("#/doctor/pharmacy-medicines").section, "pharmacy-medicines");
  });

  it("opens Today's Patients with an explicit visit and My Patients without selecting one", () => {
    const today = consultationHref("patient-a", "visit-today");
    const mine = myPatientsHref("patient-a");
    assert.equal(readConsultationVisitUuid(today), "visit-today");
    assert.equal(readConsultationVisitUuid(mine), null);
    assert.equal(mine, "#/doctor/patient/patient-a");
  });

  it("does not put a searched patient onto My Patients or invent a visit", () => {
    const searched = consultationHref("patient-searched");
    assert.equal(readConsultationVisitUuid(searched), null);
    assert.equal(radiologyOrdererDoesNotQualifyForMyPatients(), true);
  });

  it("keeps patient-only charts from silently selecting a visit", () => {
    const visits = [
      visit({ uuid: "visit-003", dailyVisitNumber: "003" }),
      visit({ uuid: "visit-001", dailyVisitNumber: "001" }),
    ];
    const bound = bindConsultationVisit({
      selectedVisitUuid: null,
      patientUuid: "patient-a",
      visits,
    });
    assert.equal(bound.status, "no-selection");
    assert.notEqual(firstOpenVisit(visits), undefined);
    assert.match(VISIT_NOT_SELECTED_MESSAGE, /Previous visits/);
  });

  it("aligns section navigation with the visual chart order", () => {
    assert.deepEqual(
      CONSULTATION_FLOW.map((item) => item.id),
      [
        "allergies",
        "anc",
        "vitals",
        "document",
        "visits",
        "diagnose",
        "laboratory",
        "radiology",
        "prescribe",
        "disposition",
      ],
    );
    assert.match(CHART_SOURCE, /id="allergies"/);
    assert.match(CHART_SOURCE, /id="vitals"/);
    assert.match(CHART_SOURCE, /id="document"/);
    assert.match(CHART_SOURCE, /id="laboratory"/);
    assert.match(CHART_SOURCE, /id="radiology"/);
    assert.match(CHART_SOURCE, /id="anc"/);
    assert.equal(CHART_SOURCE.includes("href={`#${item.id}`}"), false);
    assert.equal(CHART_SOURCE.indexOf('id="vitals"') < CHART_SOURCE.indexOf('id="document"'), true);
    assert.equal(CHART_SOURCE.indexOf('id="laboratory"') < CHART_SOURCE.indexOf('id="radiology"'), true);
  });

  it("returns to Clinical instead of implying Today's Patients", () => {
    assert.equal(CLINICAL_BACK_LABEL, "← Clinical");
    assert.equal(CLINICAL_LOAD_FAIL_BACK_LABEL, "Back to Clinical");
    assert.equal(CHART_SOURCE.includes("← Today's Patients"), false);
    assert.equal(CHART_SOURCE.includes("Back to Doctor Queue"), false);
    assert.equal(VISIT_NOT_FOUND_MESSAGE.includes("Today's Patients"), false);
    assert.equal(VISIT_MISMATCH_MESSAGE.includes("Today's Patients"), false);
    assert.match(VISIT_NOT_FOUND_MESSAGE, /Return to Clinical/);
  });

  it("keeps consultation empty states on the selected visit", () => {
    assert.equal(NO_CHIEF_COMPLAINT_FOR_VISIT, "No chief complaint recorded for this visit.");
    assert.equal(NO_HISTORY_FOR_VISIT, "No history recorded for this visit.");
    assert.equal(NO_CLINICAL_NOTES_FOR_VISIT, "No clinical notes recorded for this visit.");
    assert.match(PREVIOUS_VISITS_DESCRIPTION, /Choose one to open it/);
  });

  it("does not label patient-level laboratory orders as this visit", () => {
    assert.equal(LAB_ORDERS_EMPTY_DESCRIPTION, "No laboratory orders recorded for this patient.");
    assert.equal(CHART_SOURCE.includes("No laboratory orders on this visit yet."), false);
  });

  it("does not expose unimplemented Refer or Follow-up, or Bahmni Clinical", () => {
    assert.equal(CHART_SOURCE.includes("ComingSoonMark"), false);
    assert.equal(CHART_SOURCE.includes(">Refer<"), false);
    assert.equal(CHART_SOURCE.includes("Open full chart"), false);
    assert.match(CHART_SOURCE, /Admit Patient/);
  });

  it("keeps unavailable clinical forms hidden", () => {
    assert.equal(optionalSectionsVisibleInWorkspace().length, 0);
  });

  it("lets the doctor order Radiology but not set price or write the report", () => {
    assert.equal(doctorCannotSetRadiologyPrice(), true);
    assert.equal(CHART_SOURCE.includes("Set Price"), false);
    assert.equal(CHART_SOURCE.includes("Save Price"), false);
    assert.equal(CHART_SOURCE.includes("Write Report"), false);
    assert.match(CHART_SOURCE, /showAction=\{false\}/);
    assert.match(CHART_SOURCE, /showVisit=\{false\}/);
    assert.match(RAD_ORDER_SOURCE, /Radiology sets the fee/);
    assert.equal(RAD_ORDER_SOURCE.includes("Set Price"), false);
    assert.equal(RAD_ORDER_SOURCE.includes("Save Price"), false);
  });

  it("keeps Patient Account as navigation and does not collect payment on the chart", () => {
    assert.match(CHART_SOURCE, /PatientAccountLink/);
    assert.equal(CHART_SOURCE.includes("Collect payment"), false);
    assert.equal(CHART_SOURCE.includes("Record payment"), false);
    assert.equal(FEE_SOURCE.includes("Waive consultation fee"), false);
    assert.equal(FEE_SOURCE.includes("Pharmacy bills are reduced"), false);
    assert.match(FEE_SOURCE, /Create fee/);
    assert.match(FEE_SOURCE, /No consultation fee/);
    assert.match(FEE_SOURCE, /Clinical does not collect money/);
    assert.equal(FEE_SOURCE.includes("Collect payment"), false);
  });

  it("does not require an open OPD visit before the doctor can admit", () => {
    assert.match(CHART_SOURCE, /canRequestAdmission/);
    assert.match(CHART_SOURCE, /ADMIT_NURSING_ASSIGNS_BED/);
    assert.equal(CHART_SOURCE.includes("Start an open visit before admitting this patient."), false);
    assert.equal(CHART_SOURCE.includes("if (!openVisit)"), false);
    assert.match(CHART_SOURCE, /requestAdmission\(/);
    assert.match(CHART_SOURCE, /openVisit\?\.uuid/);
  });

  it("uses the shared busy spinner when the doctor starts an OPD visit", () => {
    assert.match(CHART_SOURCE, /busy=\{saveState === "starting-visit"\}/);
    assert.match(CHART_SOURCE, /busyLabel="Creating visit..."/);
    assert.equal(CHART_SOURCE.includes("Starting visit…"), false);
    assert.equal(FEE_SOURCE.includes("<LoadingState"), true);
    assert.equal(FEE_SOURCE.includes("<p className=\"consult__muted\">Loading fee"), false);
  });

  it("does not require starting an OPD visit when the patient is already admitted", () => {
    assert.match(CHART_SOURCE, /resolveClinicalOrderContext/);
    assert.match(CHART_SOURCE, /orderBlockedReason/);
    assert.equal(CHART_SOURCE.includes("const canWrite = Boolean(openVisit)"), false);
    assert.equal(CHART_SOURCE.includes('blockedReason="Start an open visit before prescribing."'), false);
    assert.match(CHART_SOURCE, /visitUuid=\{orderVisit\?\.uuid\}/);
  });

  it("does not grant Doctor Radiology, Laboratory, Pharmacy, Reception, or Accountant workplaces", () => {
    assert.match(MAP_SOURCE, /function canOpenDoctor[\s\S]*PRIVILEGES\.clinical/);
    assert.match(MAP_SOURCE, /function canOpenRadiology[\s\S]*PRIVILEGES\.radiology/);
    assert.match(MAP_SOURCE, /function canOpenLaboratory[\s\S]*PRIVILEGES\.labLite/);
    assert.match(MAP_SOURCE, /function canOpenPharmacy[\s\S]*PRIVILEGES\.pharmacy/);
    assert.match(MAP_SOURCE, /function canOpenAccountant[\s\S]*PRIVILEGES\.accountant/);
    assert.match(MAP_SOURCE, /Clinical and pharmacy privileges do not grant payment rights/);
    assert.match(MAP_SOURCE, /function canOpenPatientAccount[\s\S]*PRIVILEGES\.clinical/);
    assert.match(DESK_SOURCE, /PharmacyMedicinesDesk/);
    assert.equal(DESK_SOURCE.includes('href: "#/pharmacy"'), false);
  });

  it("lets the doctor type a medicine name when it is not in Pharmacy", () => {
    assert.match(RX_SOURCE, /searchMedicinesForPrescription/);
    assert.match(RX_SOURCE, /chooseTypedName/);
    assert.match(RX_SOURCE, /If this medicine is not in Pharmacy/);
    assert.match(RX_SOURCE, /nonCoded: !selected\?\.uuid/);
  });
});
