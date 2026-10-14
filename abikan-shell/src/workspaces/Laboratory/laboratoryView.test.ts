import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { LaboratoryBoardOrder, LaboratoryCatalogueTest } from "../../types/laboratoryCatalogue.ts";
import {
  canSelectLabTest,
  formatLabPrice,
  isLabPanel,
  labCatalogueHitDetails,
  laboratoryRequestSourceLabel,
  laboratoryPatientTypeLabel,
  laboratoryViewFromNav,
  enteredLaboratoryResult,
  laboratoryChargesForOrder,
  resultIsNumeric,
  matchesLabSearch,
  labStaffSeesPayment,
  doctorCannotCollectPayment,
} from "./laboratoryView.ts";
import { parseShellHash } from "../../app/hashRoute.ts";
import { markAmbiguousLabResults, resultShowsReferenceRange } from "../../services/openmrs/laboratoryResult.ts";
import type { LabResultSummary } from "../../types/index.ts";

function testRow(overrides: Partial<LaboratoryCatalogueTest> = {}): LaboratoryCatalogueTest {
  return {
    id: "1",
    name: "Full Blood Count",
    type: "Haematology",
    outsourced: false,
    orderable: true,
    conceptUuid: "1019AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    price: {
      amount: 3500,
      formatted: "₦3,500",
      currencyCode: "NGN",
      currencySymbol: "₦",
      decimalPlaces: 2,
    },
    ...overrides,
  };
}

function boardRow(overrides: Partial<LaboratoryBoardOrder> = {}): LaboratoryBoardOrder {
  return {
    uuid: "order-1",
    orderNumber: "ORD-9",
    testName: "Full Blood Count",
    patientUuid: "patient-1",
    visitUuid: "visit-1",
    patientName: "Lab Test Patient",
    mrn: "ABC200016",
    ordered: "19 Aug 2026",
    urgency: "Routine",
    accession: "",
    provider: "Doctor Hospital EMR",
    comment: "",
    outsourced: false,
    stage: "pending",
    laboratoryStatus: "Not started",
    resultMapping: "unique",
    statusMessage: "",
    hasResult: false,
    paymentStatus: "UNPAID",
    hasCharge: true,
    ...overrides,
  };
}

function resultRow(overrides: Partial<LabResultSummary> = {}): LabResultSummary {
  return {
    orderUuid: "order-1",
    accessionUuid: "encounter-1",
    testName: "Malarial smear",
    panelName: "",
    result: "Negative",
    unit: "",
    minNormal: "—",
    maxNormal: "—",
    abnormal: false,
    notes: "",
    provider: "—",
    resultAt: "20 Aug 2026",
    accessionAt: "19 Aug 2026",
    mappingStatus: "unique",
    mappingMessage: "",
    ...overrides,
  };
}

describe("resultIsNumeric", () => {
  it("keeps a positive or negative test as a choice", () => {
    assert.equal(resultIsNumeric({ resultType: "D", options: [{ value: "1200", label: "Negative" }] }), false);
    assert.equal(resultIsNumeric({ resultType: "R", options: [] }), false);
    assert.equal(resultIsNumeric({ resultType: "N", options: [] }), true);
  });
});

describe("laboratoryViewFromNav", () => {
  it("maps laboratory sections and keeps unknown hashes on the dashboard", () => {
    assert.equal(laboratoryViewFromNav("pending"), "pending");
    assert.equal(laboratoryViewFromNav("processing"), "processing");
    assert.equal(laboratoryViewFromNav("completed"), "completed");
    assert.equal(laboratoryViewFromNav("patients"), "patients");
    assert.equal(laboratoryViewFromNav("pricing"), "pricing");
    assert.equal(laboratoryViewFromNav("reference-ranges"), "reference-ranges");
    assert.equal(laboratoryViewFromNav("hospital-tests"), "hospital-tests");
    assert.equal(laboratoryViewFromNav("create-test"), "create-test");
    assert.equal(laboratoryViewFromNav("blood-bank"), "blood-bank");
    assert.equal(laboratoryViewFromNav("inventory"), "inventory");
    assert.equal(laboratoryViewFromNav("orders"), "orders");
    assert.equal(laboratoryViewFromNav("new-order"), "new-order");
    assert.equal(laboratoryViewFromNav("history"), "history");
    assert.equal(laboratoryViewFromNav("deleted"), "deleted");
    assert.equal(laboratoryViewFromNav("deleted-orders"), "deleted");
    assert.equal(laboratoryViewFromNav(null), "dashboard");
    assert.equal(laboratoryViewFromNav("not-a-screen"), "dashboard");
  });
});

describe("laboratory request and patient labels", () => {
  it("labels Laboratory Direct, External Referral, and External Patient in hospital language", () => {
    assert.equal(laboratoryRequestSourceLabel("laboratory_direct"), "Laboratory Direct");
    assert.equal(laboratoryRequestSourceLabel("external_referral"), "External Referral");
    assert.equal(laboratoryRequestSourceLabel("doctor_order"), "Doctor Order");
    assert.equal(
      laboratoryRequestSourceLabel(undefined, "[Lab Direct] fasting"),
      "Laboratory Direct",
    );
    assert.equal(laboratoryPatientTypeLabel("external", true), "External Patient");
    assert.equal(laboratoryPatientTypeLabel("registered"), "Registered Patient");
  });
});

describe("laboratory catalogue selection", () => {
  it("lets a doctor select an orderable test or panel with a NGN price", () => {
    const panel = testRow({
      id: "20",
      name: "Lipid Profile",
      type: "Panel",
      conceptClass: "LabSet",
      price: { amount: 6000, formatted: "₦6,000", currencyCode: "NGN", currencySymbol: "₦", decimalPlaces: 2 },
    });
    assert.equal(canSelectLabTest(testRow()), true);
    assert.equal(isLabPanel(panel), true);
    assert.equal(formatLabPrice(panel.price?.amount), "₦6,000");
    assert.match(formatLabPrice(1500), /₦1,500/);
  });

  it("does not select unavailable tests and keeps outsourced tests identifiable", () => {
    assert.equal(canSelectLabTest(testRow({ orderable: false })), false);
    assert.equal(canSelectLabTest(testRow({ conceptUuid: null })), false);
    assert.equal(testRow({ outsourced: true }).outsourced, true);
  });

  it("shows enough detail to distinguish similar catalogue hits", () => {
    const details = labCatalogueHitDetails(
      testRow({
        name: "Blood grouping",
        openmrsName: "Blood grouping test",
        type: "Panel",
        conceptClass: "LabSet",
        specimen: "Blood",
        department: "Haematology",
        price: {
          amount: 2500,
          formatted: "₦2,500",
          currencyCode: "NGN",
          currencySymbol: "₦",
          decimalPlaces: 2,
        },
      }),
    );
    assert.match(details, /Blood grouping test/);
    assert.match(details, /Panel/);
    assert.match(details, /Haematology/);
  });

  it("searches pending laboratory orders by patient, test, and hospital number", () => {
    assert.equal(matchesLabSearch(boardRow(), "abc200016"), true);
    assert.equal(matchesLabSearch(boardRow(), "lipid"), false);
    assert.equal(matchesLabSearch(boardRow({ testName: "Malaria RDT" }), "malaria"), true);
  });
});

describe("laboratory payment visibility", () => {
  it("shows payment status to laboratory staff and never collects money in Clinical", () => {
    assert.equal(labStaffSeesPayment("UNPAID"), true);
    assert.equal(labStaffSeesPayment("PAID"), true);
    assert.equal(labStaffSeesPayment("PARTIALLY PAID"), true);
    assert.equal(doctorCannotCollectPayment(), true);
  });
});

describe("clinical laboratory result layout", () => {
  it("shows a unit and range for a number, and only the answer for a word result", () => {
    assert.equal(resultShowsReferenceRange("13.2"), true);
    assert.equal(resultShowsReferenceRange("1,200"), true);
    assert.equal(resultShowsReferenceRange("Positive"), false);
    assert.equal(resultShowsReferenceRange("Negative"), false);
    assert.equal(resultShowsReferenceRange("—"), true);
  });
});

describe("laboratory result order correlation", () => {
  it("marks duplicate same-test rows on one accession as ambiguous without dropping either order", () => {
    const rows = markAmbiguousLabResults([
      resultRow(),
      resultRow({ orderUuid: "order-2", result: "—" }),
    ]);
    assert.equal(rows.length, 2);
    assert.deepEqual(rows.map((row) => row.orderUuid), ["order-1", "order-2"]);
    assert.equal(rows[0].result, "Negative");
    assert.equal(rows[0].mappingStatus, "ambiguous");
    assert.equal(rows[1].mappingStatus, "ambiguous");
  });

  it("keeps unique same-test results on different accessions safely matched", () => {
    const rows = markAmbiguousLabResults([
      resultRow(),
      resultRow({ orderUuid: "order-2", accessionUuid: "encounter-2" }),
    ]);
    assert.deepEqual(rows.map((row) => row.mappingStatus), ["unique", "unique"]);
  });
});

describe("laboratory routes and access", () => {
  it("keeps #/lab aliases inside Laboratory, including unknown suffixes", () => {
    assert.equal(parseShellHash("#/lab").route, "laboratory");
    assert.equal(parseShellHash("#/lab/orders").route, "laboratory");
    assert.equal(parseShellHash("#/lab/pending").navItemId, "pending");
    assert.equal(parseShellHash("#/lab/processing").navItemId, "processing");
    assert.equal(parseShellHash("#/lab/completed").navItemId, "completed");
    assert.equal(parseShellHash("#/lab/patients").navItemId, "patients");
    assert.equal(parseShellHash("#/lab/new-order").navItemId, "new-order");
    assert.equal(parseShellHash("#/lab/direct").navItemId, "new-order");
    assert.equal(parseShellHash("#/lab/history").navItemId, "history");
    assert.equal(parseShellHash("#/lab/hospital-tests").navItemId, "hospital-tests");
    assert.equal(parseShellHash("#/lab/catalogue").navItemId, "hospital-tests");
    assert.equal(parseShellHash("#/lab/create-test").navItemId, "create-test");
    assert.equal(parseShellHash("#/lab/blood-bank").navItemId, "blood-bank");
    assert.equal(parseShellHash("#/lab/inventory").navItemId, "inventory");
    assert.equal(parseShellHash("#/lab/studies").section, "history");
    assert.equal(parseShellHash("#/lab/patient/abc").route, "laboratory-patient");
    assert.equal(parseShellHash("#/lab/orders/order-1").route, "laboratory-order");
    assert.equal(parseShellHash("#/lab/external/EXT-LAB-1").route, "laboratory-external");
    assert.equal(parseShellHash("#/lab/not-a-screen").route, "laboratory");
    assert.equal(parseShellHash("#/laboratory/not-a-screen").route, "laboratory");
  });

  it("keeps the laboratory order workflow separate from Radiology", () => {
    assert.equal(parseShellHash("#/lab").route, "laboratory");
    assert.equal(canSelectLabTest(testRow()), true);
    assert.equal(doctorCannotCollectPayment(), true);
  });

  it("does not treat a laboratory hash as Administration", () => {
    assert.equal(parseShellHash("#/laboratory").route, "laboratory");
    assert.equal(parseShellHash("#/administration").route, "unavailable");
  });

  it("shows every test ordered together when one of them is opened", () => {
    const culture = { orderUuid: "culture", requestKey: "visit:2026-10-11T16:38" };
    const urine = { orderUuid: "urine", requestKey: "visit:2026-10-11T16:38" };
    const later = { orderUuid: "malaria", requestKey: "visit:2026-10-11T18:05" };
    assert.deepEqual(
      laboratoryChargesForOrder([culture, urine, later], "culture").map((row) => row.orderUuid),
      ["culture", "urine"],
    );
    assert.deepEqual(
      laboratoryChargesForOrder([culture, urine, later]).map((row) => row.orderUuid),
      ["culture", "urine", "malaria"],
    );
  });

  it("does not show another test's answer in a blank result", () => {
    assert.equal(
      enteredLaboratoryResult("1246", [{ value: "1", label: "No growth" }]),
      "",
    );
    assert.equal(
      enteredLaboratoryResult("1246", [{ value: "1246", label: "Non-reactive" }]),
      "1246",
    );
  });
});
