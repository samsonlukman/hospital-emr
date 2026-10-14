import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import type { PharmacyCatalogueItem, PharmacyPrescription } from "../../types/pharmacy.ts";
import {
  catalogueDraftError,
  catalogueLineErrors,
  catalogueStockLabel,
  emptyCatalogueDraft,
  emptyCatalogueLine,
  emptyReceiveDraft,
  emptyReceiveLine,
  emptyAdjustDraft,
  emptyAdjustLine,
  dosageFormChoices,
  isUnlistedDosageForm,
  resolvedDosageForm,
  UNLISTED_DOSAGE_FORM,
  groupPrescriptionsByPatient,
  groupPrescriptionsForList,
  isReady,
  matchesCatalogueSearch,
  matchesPharmacySearch,
  needsAttention,
  canChangePharmacyMedicine,
  canDeletePharmacyMedicine,
  medicineNeedsQuantity,
  paymentNeeded,
  pharmacyStaffError,
  pharmacyLineStatusLabel,
  prescriptionDispenseLabel,
  listIsNotInPharmacy,
  pharmacyViewFromNav,
  receiveDraftError,
  receiveLineErrors,
  adjustDraftError,
  adjustLineErrors,
  resultingOnHand,
} from "./pharmacyView.ts";

const PHARMACY_PATIENT_SOURCE = readFileSync(
  fileURLToPath(new URL("./PharmacyPatientWorkspace.tsx", import.meta.url)),
  "utf8",
);
function row(overrides: Partial<PharmacyPrescription> = {}): PharmacyPrescription {
  return {
    status: "ok",
    orderUuid: "order-1",
    orderNumber: "ORD-1",
    patientUuid: "patient-1",
    patientName: "Aisha Bello",
    mrn: "ABC200011",
    prescriber: "Dr Test",
    ordered: "2026-08-19",
    drugName: "Paracetamol",
    strength: "500 mg",
    dose: "500",
    doseUnits: "mg",
    route: "Oral",
    frequency: "TDS",
    duration: "3 days",
    instructions: "",
    quantity: 2,
    quantityUnits: "Tablet",
    paymentStatus: "PAID",
    dispensingStatus: "READY TO DISPENSE",
    canDispense: true,
    blockReason: null,
    stockOnHand: 10,
    stockAfter: 8,
    delivered: 0,
    ...overrides,
  };
}

describe("canDeletePharmacyMedicine", () => {
  it("allows delete before the medicine is handed over, including when it is already paid", () => {
    assert.equal(canDeletePharmacyMedicine(row({ paymentStatus: "UNPAID", dispensingStatus: "UNPAID" })), true);
    assert.equal(canDeletePharmacyMedicine(row({ paymentStatus: "PAID", dispensingStatus: "READY TO DISPENSE" })), true);
    assert.equal(canDeletePharmacyMedicine(row({ paymentStatus: "PAID", dispensingStatus: "DISPENSED" })), false);
    assert.equal(canDeletePharmacyMedicine(row({ paymentStatus: "PARTIALLY PAID", dispensingStatus: "UNPAID" })), false);
    assert.equal(canDeletePharmacyMedicine(row({ paymentStatus: "NOT BILLED", dispensingStatus: "NOT IN PHARMACY" })), true);
  });
});

describe("medicineNeedsQuantity", () => {
  it("asks for a quantity only before the bill exists", () => {
    assert.equal(medicineNeedsQuantity(row({ paymentStatus: "NOT BILLED", dispensingStatus: "UNPAID" })), true);
    assert.equal(medicineNeedsQuantity(row({ paymentStatus: "UNPAID", dispensingStatus: "UNPAID" })), false);
    assert.equal(medicineNeedsQuantity(row({ paymentStatus: "NOT BILLED", dispensingStatus: "DISPENSED" })), false);
    assert.equal(
      medicineNeedsQuantity(row({ paymentStatus: "NOT BILLED", notInPharmacy: true, dispensingStatus: "NOT IN PHARMACY" })),
      false,
    );
  });
});

describe("canChangePharmacyMedicine", () => {
  it("allows a change only before the medicine is handed over or paid", () => {
    assert.equal(canChangePharmacyMedicine(row({ paymentStatus: "UNPAID", dispensingStatus: "UNPAID", canDispense: false })), true);
    assert.equal(canChangePharmacyMedicine(row({ paymentStatus: "PAID" })), false);
    assert.equal(canChangePharmacyMedicine(row({ paymentStatus: "PARTIALLY PAID", dispensingStatus: "UNPAID" })), false);
    assert.equal(canChangePharmacyMedicine(row({ dispensingStatus: "DISPENSED", paymentStatus: "UNPAID" })), false);
    assert.equal(canChangePharmacyMedicine(row({ dispensingStatus: "STOPPED", paymentStatus: "UNPAID" })), false);
    assert.equal(canChangePharmacyMedicine(row({ notInPharmacy: true, dispensingStatus: "NOT IN PHARMACY", paymentStatus: "NOT BILLED" })), false);
  });
});

describe("pharmacyViewFromNav", () => {
  it("maps known pharmacy sections and defaults unknown ones to the dashboard", () => {
    assert.equal(pharmacyViewFromNav("prescriptions"), "prescriptions");
    assert.equal(pharmacyViewFromNav("new-sale"), "new-sale");
    assert.equal(pharmacyViewFromNav("ready"), "prescriptions");
    assert.equal(pharmacyViewFromNav("sales-history"), "sales-history");
    assert.equal(pharmacyViewFromNav("dispensed"), "sales-history");
    assert.equal(pharmacyViewFromNav("catalogue"), "catalogue");
    assert.equal(pharmacyViewFromNav("pricing"), "pricing");
    assert.equal(pharmacyViewFromNav("inventory"), "inventory");
    assert.equal(pharmacyViewFromNav(null), "dashboard");
    assert.equal(pharmacyViewFromNav("not-a-screen"), "dashboard");
  });
});

describe("pharmacy staff labels", () => {
  it("keeps unpaid and partial payment visible while still allowing ready-to-dispense", () => {
    assert.equal(isReady(row({ dispensingStatus: "READY TO DISPENSE", paymentStatus: "UNPAID" })), true);
    assert.equal(paymentNeeded(row({ paymentStatus: "PARTIALLY PAID" })), true);
    assert.equal(isReady(row()), true);
  });

  it("surfaces unpaid, partial, and ready rows as needing attention", () => {
    const attention = needsAttention([
      row({ orderUuid: "1", dispensingStatus: "READY TO DISPENSE" }),
      row({ orderUuid: "2", paymentStatus: "UNPAID", dispensingStatus: "UNPAID" }),
      row({ orderUuid: "3", paymentStatus: "PARTIALLY PAID", dispensingStatus: "UNPAID" }),
      row({ orderUuid: "4", paymentStatus: "PAID", dispensingStatus: "DISPENSED" }),
    ]);
    assert.equal(attention.length, 3);
  });

  it("maps staff-facing dispense errors", () => {
    assert.equal(
      pharmacyStaffError({ code: "already_dispensed" }, "fallback"),
      "Already dispensed.",
    );
    assert.equal(
      pharmacyStaffError({ code: "insufficient_stock" }, "fallback"),
      "Not enough stock to dispense this medication.",
    );
    assert.equal(
      pharmacyStaffError({ code: "unpaid" }, "fallback"),
      "Payment is still outstanding. Dispensing can continue; settle payment at the cashier when ready.",
    );
    assert.equal(
      pharmacyStaffError({ code: "not_in_pharmacy" }, "fallback"),
      "Not in Pharmacy — do not dispense.",
    );
  });

  it("searches by name, hospital number, and medicine without requiring a UUID", () => {
    const prescription = row();
    assert.equal(matchesPharmacySearch(prescription, "aisha"), true);
    assert.equal(matchesPharmacySearch(prescription, "ABC200011"), true);
    assert.equal(matchesPharmacySearch(prescription, "paracetamol"), true);
    assert.equal(matchesPharmacySearch(prescription, "unknown-uuid"), false);
  });

  it("groups multiple medicines for the same patient", () => {
    const groups = groupPrescriptionsByPatient([
      row({ orderUuid: "a", drugName: "Paracetamol" }),
      row({ orderUuid: "b", drugName: "Amoxicillin" }),
      row({
        orderUuid: "c",
        patientUuid: "patient-2",
        patientName: "John Adewale",
        mrn: "ABC200012",
        drugName: "ORS",
      }),
    ]);
    assert.equal(groups.length, 2);
    assert.equal(groups[0]?.lines.length, 2);
    assert.equal(groups[1]?.patientName, "John Adewale");
  });

  it("lists one card per sale with patient and truncated order summary", () => {
    const list = groupPrescriptionsForList([
      row({ orderUuid: "a", saleId: "39", drugName: "Paracetamol 500 mg — TEST" }),
      row({ orderUuid: "b", saleId: "39", drugName: "Amoxicillin 500 mg" }),
      row({
        orderUuid: "c",
        saleId: "40",
        patientUuid: "patient-2",
        patientName: "John Adewale",
        mrn: "ABC200012",
        drugName: "ORS",
        strength: "",
      }),
    ]);
    assert.equal(list.length, 2);
    assert.equal(list[0]?.patientName, "Aisha Bello");
    assert.equal(list[0]?.medicineCount, 2);
    assert.match(list[0]?.summary || "", /2 medicines/);
    assert.match(list[0]?.summary || "", /Paracetamol/);
    assert.match(list[0]?.summary || "", /Amoxicillin/);
    assert.equal(list[1]?.summary, "1 medicine: ORS");
  });

  it("keeps a later order off an earlier prescription and shows how many are dispensed", () => {
    const list = groupPrescriptionsForList([
      row({
        orderUuid: "early-1",
        groupKey: "enc-1|2026-10-11T16:38",
        drugName: "Fluconazole",
        dispensingStatus: "DISPENSED",
      }),
      row({
        orderUuid: "early-2",
        groupKey: "enc-1|2026-10-11T16:38",
        drugName: "Vitamin",
        dispensingStatus: "UNPAID",
      }),
      row({
        orderUuid: "later",
        groupKey: "enc-1|2026-10-11T17:02",
        drugName: "Equate Paracetamol",
        dispensingStatus: "PARTIALLY DISPENSED",
      }),
    ]);
    assert.equal(list.length, 2);
    assert.equal(prescriptionDispenseLabel(list[0]?.lines || []), "1 of 2 dispensed");
    assert.equal(prescriptionDispenseLabel(list[1]?.lines || []), "Part dispensed");
    assert.equal(pharmacyLineStatusLabel(list[1]?.lines[0] as PharmacyPrescription), "Part dispensed");
    assert.equal(
      pharmacyLineStatusLabel(row({ dispensingStatus: "READY TO DISPENSE" })),
      "Not dispensed",
    );
  });

  it("keeps typed medicines on the same prescription card and off the bill", () => {
    const list = groupPrescriptionsForList([
      row({
        orderUuid: "sale-line",
        saleId: "39",
        groupKey: "enc-1",
        encounterUuid: "enc-1",
        drugName: "Paracetamol 500 mg — TEST",
      }),
      row({
        orderUuid: "typed",
        saleId: null,
        groupKey: "enc-1",
        encounterUuid: "enc-1",
        drugName: "Calamine lotion extra",
        notInPharmacy: true,
        canDispense: false,
        paymentStatus: "NOT BILLED",
        dispensingStatus: "NOT IN PHARMACY",
      }),
    ]);
    assert.equal(list.length, 1);
    assert.equal(list[0]?.medicineCount, 2);
    assert.equal(list[0]?.paymentStatus, "PAID");
    assert.equal(paymentNeeded(list[0]?.lines[1] as PharmacyPrescription), false);
    assert.equal(
      pharmacyLineStatusLabel(list[0]?.lines[1] as PharmacyPrescription),
      "Not in Pharmacy — do not dispense",
    );
    assert.equal(
      needsAttention([
        row({ notInPharmacy: true, paymentStatus: "NOT BILLED", dispensingStatus: "NOT IN PHARMACY" }),
      ]).length,
      0,
    );
    assert.equal(listIsNotInPharmacy(list[0]?.lines || []), false);
    assert.equal(
      listIsNotInPharmacy([
        row({ notInPharmacy: true, paymentStatus: "NOT BILLED", dispensingStatus: "NOT IN PHARMACY" }),
      ]),
      true,
    );
  });
});

function catalogueRow(overrides: Partial<PharmacyCatalogueItem> = {}): PharmacyCatalogueItem {
  return {
    id: "20",
    name: "Cetirizine 10 mg",
    hospitalName: "cetirizine 10mg",
    listedAs: "",
    brandName: "",
    strength: "10 mg",
    form: "Tablet",
    stockOnHand: 0,
    stockUnits: "Tablet",
    price: { amount: 100, formatted: "₦100", currencyCode: "NGN", currencySymbol: "₦" },
    developmentPrice: false,
    developmentPriceNote: "",
    available: true,
    status: "Available",
    ...overrides,
  };
}

describe("pharmacy catalogue search", () => {
  it("finds mapped medicines by name, strength, and form without collapsing distinct products", () => {
    const tablet = catalogueRow({
      id: "96",
      name: "Ondansetron 4 mg",
      hospitalName: "ondasetron",
      strength: "4 mg",
      form: "Tablet",
    });
    const injection = catalogueRow({
      id: "97",
      name: "Ondansetron 2 mg/ml",
      hospitalName: "ondansetron",
      strength: "2 mg/ml",
      form: "Injection",
    });
    assert.equal(matchesCatalogueSearch(catalogueRow(), "cetirizine"), true);
    assert.equal(matchesCatalogueSearch(tablet, "ondansetron"), true);
    assert.equal(matchesCatalogueSearch(injection, "ondansetron"), true);
    assert.equal(matchesCatalogueSearch(tablet, "injection"), false);
    assert.equal(matchesCatalogueSearch(injection, "tablet"), false);
    assert.equal(catalogueStockLabel(catalogueRow()), "None in stock");
    assert.equal(catalogueStockLabel(catalogueRow({ stockOnHand: 2 })), "2 in stock · Tablet");
  });

  it("requires product name, selected generic, strength, form, and selling price before saving", () => {
    assert.equal(catalogueDraftError(emptyCatalogueDraft(), "add"), "Enter the medicine or product name.");
    assert.equal(
      catalogueDraftError(
        {
          ...emptyCatalogueDraft(),
          name: "Panadol 500mg Tablet",
        },
        "add",
      ),
      "Search and select a generic.",
    );
    assert.equal(
      catalogueDraftError(
        {
          ...emptyCatalogueDraft(),
          name: "Panadol 500mg Tablet",
          conceptUuid: "concept-1",
          genericName: "Paracetamol",
          strength: "",
        },
        "add",
      ),
      "Enter the strength as written on the pack.",
    );
    assert.equal(
      catalogueDraftError(
        {
          ...emptyCatalogueDraft(),
          name: "Panadol 500mg Tablet",
          conceptUuid: "concept-1",
          genericName: "Paracetamol",
          strength: "500 mg",
          form: "Tablet",
          price: "100",
        },
        "add",
      ),
      "",
    );
    assert.equal("stock" in emptyCatalogueDraft(), false);
  });

  it("includes Consumables and lets pharmacy write a form that is not listed", () => {
    const choices = dosageFormChoices(["Tablet", "Injection"]);
    assert.equal(choices.includes("Consumables"), true);
    assert.equal(choices.includes(UNLISTED_DOSAGE_FORM), true);
    assert.equal(isUnlistedDosageForm(UNLISTED_DOSAGE_FORM), true);
    assert.equal(resolvedDosageForm("Consumables", "ignored"), "Consumables");
    assert.equal(resolvedDosageForm(UNLISTED_DOSAGE_FORM, "Sachet"), "Sachet");
    assert.equal(
      catalogueDraftError(
        {
          ...emptyCatalogueDraft(),
          name: "Cotton wool",
          conceptUuid: "concept-1",
          genericName: "Cotton wool",
          strength: "100g",
          form: UNLISTED_DOSAGE_FORM,
          customForm: "",
          price: "100",
        },
        "add",
      ),
      "Write the dosage form.",
    );
    assert.equal(
      catalogueLineErrors({
        ...emptyCatalogueLine(),
        name: "Cotton wool 100g",
        conceptUuid: "concept-1",
        genericName: "Cotton wool",
        strength: "100g",
        form: UNLISTED_DOSAGE_FORM,
        customForm: "Roll",
        price: "100",
      }).form,
      undefined,
    );
  });

  it("validates multi-item catalogue lines", () => {
    const blank = emptyCatalogueLine();
    assert.equal(catalogueLineErrors(blank).name, "Enter the medicine or product name.");
    assert.equal(catalogueLineErrors(blank).generic, "Search and select a generic.");
    assert.equal(catalogueLineErrors(blank).strength, "Enter the strength as written on the pack.");
    assert.deepEqual(
      catalogueLineErrors({
        ...blank,
        name: "Paracetamol 500mg Tablet",
        conceptUuid: "concept-1",
        genericName: "Paracetamol",
        strength: "500 mg",
        form: "Tablet",
        price: "100",
      }),
      {},
    );
  });
});

describe("pharmacy inventory drafts", () => {
  it("requires a received quantity and purchase price, not a selling price", () => {
    assert.equal(receiveDraftError(emptyReceiveDraft()), "Enter how many units arrived.");
    assert.equal(
      receiveDraftError({ ...emptyReceiveDraft(), quantity: "10", purchasePrice: "" }),
      "Enter the purchase price paid for this receipt. This is not the selling price.",
    );
    assert.equal(
      receiveDraftError({ ...emptyReceiveDraft(), quantity: "10", purchasePrice: "300" }),
      "",
    );
  });

  it("validates multi-item receive lines", () => {
    const blank = emptyReceiveLine();
    assert.equal(receiveLineErrors(blank).drug, "Choose a medicine.");
    assert.equal(receiveLineErrors(blank).quantity, "Enter how many units arrived.");
    assert.equal(
      receiveLineErrors(blank).purchasePrice,
      "Enter the purchase price paid. This is not the selling price.",
    );
    assert.deepEqual(
      receiveLineErrors({
        ...blank,
        drugUuid: "drug-1",
        quantity: "10",
        purchasePrice: "50",
      }),
      {},
    );
  });

  it("requires an adjustment quantity and reason, and calculates the resulting quantity", () => {
    assert.equal(adjustDraftError(emptyAdjustDraft(), 10), "Enter how many units to adjust.");
    assert.equal(
      adjustDraftError({ ...emptyAdjustDraft(), quantity: "3", direction: "decrease" }, 10),
      "Choose why the stock is being adjusted.",
    );
    assert.equal(
      adjustDraftError(
        { ...emptyAdjustDraft(), quantity: "3", direction: "decrease", reason: "Correction" },
        10,
      ),
      "",
    );
    assert.equal(resultingOnHand(10, "decrease", 3), 7);
    assert.equal(resultingOnHand(7, "increase", 5), 12);
    assert.equal(
      adjustDraftError(
        { ...emptyAdjustDraft(), quantity: "20", direction: "decrease", reason: "Correction" },
        10,
      ),
      "Stock cannot go below zero.",
    );
  });

  it("validates multi-item adjust lines including reserved stock", () => {
    const blank = emptyAdjustLine();
    assert.equal(adjustLineErrors(blank).drug, "Choose a medicine.");
    assert.equal(adjustLineErrors(blank).quantity, "Enter how many units to adjust.");
    assert.equal(adjustLineErrors(blank).reason, "Choose why the stock is being adjusted.");
    assert.equal(
      adjustLineErrors({
        ...blank,
        drugUuid: "drug-1",
        onHand: 10,
        reserved: 4,
        direction: "decrease",
        quantity: "8",
        reason: "Correction",
      }).quantity,
      "Some of this medicine is already reserved. Enter a smaller decrease.",
    );
    assert.deepEqual(
      adjustLineErrors({
        ...blank,
        drugUuid: "drug-1",
        onHand: 10,
        reserved: 4,
        direction: "decrease",
        quantity: "5",
        reason: "Correction",
      }),
      {},
    );
  });
});

describe("Pharmacy patient chart navigation", () => {
  it("does not send pharmacy staff to the Bahmni patient chart", () => {
    assert.equal(PHARMACY_PATIENT_SOURCE.includes("Open full chart"), false);
    assert.equal(PHARMACY_PATIENT_SOURCE.includes("See Full Chart"), false);
    assert.equal(PHARMACY_PATIENT_SOURCE.includes("bahmniUrl"), false);
    assert.equal(PHARMACY_PATIENT_SOURCE.includes("patientDashboard"), false);
  });
});
