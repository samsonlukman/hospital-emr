import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { DRUG_OTHER_CONCEPT } from "../../config/clinicalConcepts.ts";
import {
  buildDrugOrderPayload,
  careSettingForVisitType,
  clinicalMedicationStatus,
  displayedDoseUnit,
  dosingUnitForForm,
  extractDrugOrderRows,
  FLEXIBLE_DOSING_INSTRUCTIONS_CLASS,
  mapClinicalMedication,
  mapDrugCatalogueHits,
  mapDrugOrderConfig,
  medicationsForChart,
  mergeClinicalMedications,
  suggestedQuantity,
  validatePrescription,
  type BahmniDrugOrderRaw,
  type DrugOrderConfig,
} from "./drugOrderMap.ts";
import type { DrugOrderSummary } from "../../types";

const NOW = Date.parse("2026-08-19T12:00:00+01:00");

const TUNDE_ACTIVE: BahmniDrugOrderRaw = {
  uuid: "270b6a0d-48d3-430d-b096-01e040b1cb5a",
  action: "NEW",
  dateActivated: 1786928039000,
  dateStopped: null,
  autoExpireDate: 1787344890000,
  duration: 5,
  durationUnits: "Days",
  drug: { name: "Paracetamol 500 mg", strength: "500 mg", form: "Tablet" },
  dosingInstructions: {
    dose: 1,
    doseUnits: "Tablet",
    route: "Oral",
    frequency: "Twice a day",
    quantity: 10,
    quantityUnits: "Tablet",
  },
};

const AISHA_VISIT_ORDER: BahmniDrugOrderRaw = {
  drugOrder: {
    uuid: "8e62a279-22e8-4e55-b97b-19d0bf438891",
    action: "NEW",
    dateActivated: 1786928039000,
    dateStopped: null,
    autoExpireDate: 1787014438000,
    duration: 1,
    durationUnits: "Days",
    drug: { name: "Paracetamol 500 mg — TEST" },
    dosingInstructions: {
      dose: 1,
      doseUnits: "Tablet",
      route: "Oral",
      frequency: "Twice a day",
    },
  },
  uuid: "8e62a279-22e8-4e55-b97b-19d0bf438891",
};

const CONFIG: DrugOrderConfig = {
  doseUnits: [{ name: "Tablet" }],
  routes: [{ name: "Oral" }, { name: "Intravenous" }],
  frequencies: [
    { name: "Once a day", frequencyPerDay: 1 },
    { name: "Twice a day", frequencyPerDay: 2 },
  ],
  durationUnits: [{ name: "Days" }, { name: "Weeks" }],
  dispensingUnits: [{ name: "Tablet" }],
  instructions: [{ name: "As directed" }],
};

describe("extractDrugOrderRows", () => {
  it("treats the unfiltered list payload as empty when Bahmni returns []", () => {
    assert.deepEqual(extractDrugOrderRows([]), []);
  });

  it("reads visitDrugOrders from prescribedAndActive", () => {
    const rows = extractDrugOrderRows({ visitDrugOrders: [AISHA_VISIT_ORDER] });
    assert.equal(rows.length, 1);
    assert.equal(rows[0].uuid, "8e62a279-22e8-4e55-b97b-19d0bf438891");
  });

  it("reads the active list as an array", () => {
    assert.equal(extractDrugOrderRows([TUNDE_ACTIVE]).length, 1);
  });

  it("keeps the visit on each medicine from a visit group", () => {
    const rows = extractDrugOrderRows({
      visitDrugOrders: [
        {
          visit: { uuid: "visit-today" },
          drugOrder: { ...TUNDE_ACTIVE, uuid: "order-today" },
          uuid: "order-today",
        },
        {
          visitUuid: "visit-last",
          drugOrders: [
            { ...TUNDE_ACTIVE, uuid: "order-last", drug: { name: "Amoxicillin" } },
          ],
        },
      ],
    });
    assert.deepEqual(
      rows.map((row) => [row.uuid, row.visitUuid]),
      [
        ["order-today", "visit-today"],
        ["order-last", "visit-last"],
      ],
    );
  });
});

describe("mapClinicalMedication", () => {
  it("maps dose, route, frequency, duration, and Ordered without exposing a technical id", () => {
    const row = mapClinicalMedication(TUNDE_ACTIVE, NOW);
    assert.equal(row?.drugName, "Paracetamol 500 mg");
    assert.equal(row?.dose, "1 Tablet");
    assert.equal(row?.route, "Oral");
    assert.equal(row?.frequency, "Twice a day");
    assert.equal(row?.duration, "5 Days");
    assert.equal(row?.status, "Ordered");
    assert.equal(row?.display.includes("270b6a0d"), false);
  });

  it("shows an injection as an injection when the saved unit says tablet", () => {
    const row = mapClinicalMedication(
      {
        ...TUNDE_ACTIVE,
        drug: { name: "Ceftriaxone 1 g", form: "Injection" },
        dosingInstructions: {
          ...TUNDE_ACTIVE.dosingInstructions,
          doseUnits: "Tablet",
          quantityUnits: "Tablet",
        },
      },
      NOW,
    );
    assert.equal(row?.dose, "1 Injection");
    assert.equal(row?.quantity, "10 Injection");
    assert.equal(
      dosingUnitForForm("Injection", [{ name: "Tablet(s)" }, { name: "Injection" }]),
      "Injection",
    );
    assert.equal(
      dosingUnitForForm("Injection", [{ name: "Tablet" }, { name: "Unit" }]),
      "Unit",
    );
    assert.equal(displayedDoseUnit("Unit", "Injection"), "Injection");
    assert.equal(displayedDoseUnit("mg", "Injection"), "mg");
  });

  it("marks auto-expired orders as Expired, not Dispensed", () => {
    const row = mapClinicalMedication(AISHA_VISIT_ORDER, NOW);
    assert.equal(row?.status, "Expired");
    assert.equal(row?.drugName, "Paracetamol 500 mg — TEST");
  });

  it("marks stopped orders as Stopped", () => {
    assert.equal(
      clinicalMedicationStatus({ ...TUNDE_ACTIVE, dateStopped: 1787000000000 }, NOW),
      "Stopped",
    );
    assert.equal(clinicalMedicationStatus({ ...TUNDE_ACTIVE, action: "DISCONTINUE" }, NOW), "Stopped");
  });
});

function chartRow(overrides: Partial<DrugOrderSummary>): DrugOrderSummary {
  return {
    uuid: "order-1",
    display: "Paracetamol",
    drugName: "Paracetamol",
    status: "Ordered",
    visitUuid: "visit-now",
    administrationMode: "HOME",
    ...overrides,
  };
}

describe("medicationsForChart", () => {
  const previous = chartRow({
    uuid: "order-old",
    drugName: "Amoxicillin",
    display: "Amoxicillin",
    visitUuid: "visit-old",
  });
  const current = chartRow({ uuid: "order-now", drugName: "Paracetamol" });
  const earlierWard = chartRow({
    uuid: "order-ward-old",
    drugName: "Ceftriaxone",
    display: "Ceftriaxone",
    administrationMode: "INPATIENT",
  });
  const latestWard = chartRow({
    uuid: "order-ward-new",
    drugName: "Metronidazole",
    display: "Metronidazole",
    administrationMode: "INPATIENT",
  });

  it("shows only the selected visit for an outpatient", () => {
    const rows = medicationsForChart([previous, current], {
      visitUuid: "visit-now",
      inpatient: false,
    });
    assert.deepEqual(rows.map((row) => row.drugName), ["Paracetamol"]);
  });

  it("keeps unadministered and not-given inpatient doses from earlier prescriptions", () => {
    const rows = medicationsForChart([previous, earlierWard, latestWard, current], {
      visitUuid: "visit-now",
      inpatient: true,
      administration: [
        {
          orderUuid: "order-ward-old",
          slots: [{ status: "SCHEDULED" }, { status: "NOT_DONE", outcome: "not-done" }],
        },
        {
          orderUuid: "order-ward-new",
          slots: [{ status: "COMPLETED", outcome: "given" }],
        },
      ],
    });
    assert.deepEqual(
      rows.map((row) => row.drugName),
      ["Ceftriaxone", "Paracetamol"],
    );
  });

  it("keeps an inpatient medicine when the ward sheet has not been written yet", () => {
    const rows = medicationsForChart([earlierWard, latestWard], {
      visitUuid: "visit-now",
      inpatient: true,
      administration: null,
    });
    assert.deepEqual(
      rows.map((row) => row.drugName),
      ["Ceftriaxone", "Metronidazole"],
    );
  });
});

describe("mergeClinicalMedications", () => {
  it("fills the doctor list from prescribedAndActive even when the empty list endpoint has nothing", () => {
    const rows = mergeClinicalMedications([[], [AISHA_VISIT_ORDER], [TUNDE_ACTIVE]], NOW);
    assert.equal(rows.length, 2);
    assert.equal(rows.some((row) => row.drugName === "Paracetamol 500 mg"), true);
    assert.equal(rows.some((row) => row.drugName === "Paracetamol 500 mg — TEST"), true);
  });

  it("deduplicates the same order from active and prescribedAndActive", () => {
    const rows = mergeClinicalMedications([[TUNDE_ACTIVE], [TUNDE_ACTIVE]], NOW);
    assert.equal(rows.length, 1);
  });
});

describe("drug catalogue and config", () => {
  it("keeps active catalogue rows and drops retired ones", () => {
    const hits = mapDrugCatalogueHits({
      results: [
        {
          uuid: "drug-1",
          name: "Paracetamol 500 mg",
          strength: "500 mg",
          retired: false,
          dosageForm: { display: "Tablet" },
          concept: { display: "Acetaminophen" },
        },
        { uuid: "drug-2", name: "Retired", retired: true },
      ],
    });
    assert.equal(hits.length, 1);
    assert.equal(hits[0].genericName, "Acetaminophen");
    assert.equal(hits[0].form, "Tablet");
  });

  it("maps configured dose units, routes, and frequencies by name", () => {
    const config = mapDrugOrderConfig({
      doseUnits: [{ name: "Tablet" }],
      routes: [{ name: "Oral" }],
      frequencies: [{ name: "Twice a day", frequencyPerDay: 2 }],
      durationUnits: [{ name: "Days" }],
      dispensingUnits: [{ name: "Tablet" }],
      dosingInstructions: [{ name: "As directed" }],
    });
    assert.deepEqual(config.routes.map((item) => item.name), ["Oral"]);
    assert.equal(config.frequencies[0].frequencyPerDay, 2);
    assert.equal(config.instructions[0].name, "As directed");
  });
});

describe("prescription validation and payload", () => {
  it("requires a medicine and written instructions", () => {
    const errors = validatePrescription(
      {
        drugUuid: "",
        dose: "",
        doseUnits: "Tablet",
        route: "Skin",
        frequency: "Whenever",
        duration: 0,
        durationUnits: "Days",
        quantity: -1,
        quantityUnits: "Tablet",
      },
      CONFIG,
    );
    assert.equal(errors.includes("Choose a medicine from the list, or type the medicine name."), true);
    assert.equal(errors.includes("Enter instructions for this medicine."), true);
    assert.equal(errors.includes("Enter the quantity."), true);
  });

  it("accepts a typed medicine name when the drug is not in Pharmacy", () => {
    assert.deepEqual(
      validatePrescription(
        {
          drugUuid: "",
          drugName: "Amoxicillin paediatric syrup",
          dose: 1,
          doseUnits: "Tablet",
          route: "Oral",
          frequency: "Twice a day",
          duration: 5,
          durationUnits: "Days",
          quantity: 1,
          quantityUnits: "Tablet",
          instructions: "Give 5 ml twice daily for five days.",
        },
        CONFIG,
      ),
      [],
    );
  });

  it("accepts a complete prescription using configured options", () => {
    assert.deepEqual(
      validatePrescription(
        {
          drugUuid: "e8265115-66d3-459c-852e-b9963b2e38eb",
          dose: 1,
          doseUnits: "Tablet",
          route: "Oral",
          frequency: "Twice a day",
          duration: 5,
          durationUnits: "Days",
          quantity: 10,
          quantityUnits: "Tablet",
          instructions: "Take one tablet twice daily for five days.",
        },
        CONFIG,
      ),
      [],
    );
  });

  it("suggests quantity for day-based schedules only", () => {
    assert.equal(suggestedQuantity(1, 2, 5, "Days"), 10);
    assert.equal(suggestedQuantity(1, 2, 1, "Weeks"), 14);
    assert.equal(suggestedQuantity(1, 2, 5, "Hours"), null);
  });

  it("builds the existing Bahmni drug-order payload without a second ledger", () => {
    const payload = buildDrugOrderPayload({
      id: "local-draft",
      drugUuid: "e8265115-66d3-459c-852e-b9963b2e38eb",
      drugName: "Paracetamol 500 mg",
      dose: 1,
      doseUnits: "Tablet",
      route: "Oral",
      frequency: "Twice a day",
      duration: 5,
      durationUnits: "Days",
      quantity: 10,
      quantityUnits: "Tablet",
      instructions: "As directed",
      administrationMode: "HOME",
    });
    assert.equal(payload.orderType, "Drug Order");
    assert.equal(payload.dosingInstructionType, FLEXIBLE_DOSING_INSTRUCTIONS_CLASS);
    assert.equal(payload.careSetting, "OUTPATIENT");
    assert.deepEqual(payload.drug, { uuid: "e8265115-66d3-459c-852e-b9963b2e38eb" });
    assert.equal(payload.drugNonCoded, undefined);
    assert.equal(payload.concept, undefined);
    assert.equal(payload.dosingInstructions.dose, 1);
    assert.equal(payload.dosingInstructions.route, "Oral");
    assert.equal(payload.durationUnits, "Days");
    assert.equal(
      payload.dosingInstructions.administrationInstructions,
      JSON.stringify({ instructions: "As directed", administrationMode: "HOME" }),
    );
  });

  it("sends a typed medicine name when the drug is not coded", () => {
    const payload = buildDrugOrderPayload({
      id: "typed-draft",
      drugUuid: "",
      drugName: "  Cough  mixture  ",
      dose: 1,
      doseUnits: "Tablet",
      route: "Oral",
      frequency: "Twice a day",
      duration: 5,
      durationUnits: "Days",
      quantity: 1,
      quantityUnits: "Tablet",
      instructions: "As directed",
      administrationMode: "HOME",
      nonCoded: true,
    });
    assert.equal(payload.drugNonCoded, "Cough mixture");
    assert.deepEqual(payload.concept, { uuid: DRUG_OTHER_CONCEPT.uuid });
    assert.equal(payload.drug, undefined);
  });

  it("uses inpatient care setting only for an IPD visit", () => {
    assert.equal(careSettingForVisitType("IPD"), "INPATIENT");
    assert.equal(careSettingForVisitType("OPD"), "OUTPATIENT");
    assert.equal(careSettingForVisitType("EMERGENCY"), "OUTPATIENT");
  });
});
