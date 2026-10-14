import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  backWithinPharmacy,
  openLaboratoryExternalPatient,
  openPatientRecord,
  parseShellHash,
  pharmacyCatalogueAddRequested,
  readLaboratoryExternalId,
  readLaboratoryOrderExpectedIdentity,
  rememberScreen,
  resetScreenHistoryForTests,
  returnToPreviousScreen,
  shellRouteHref,
} from "./hashRoute.ts";
import { fallbackRouteForUser } from "../config/routingPolicy.ts";

describe("openPatientRecord", () => {
  it("opens the canonical reception patient profile route", () => {
    const prior = globalThis.window;
    const location = { hash: "" };
    globalThis.window = { location } as Window & typeof globalThis;
    try {
      openPatientRecord("patient-abc", "reception");
      assert.equal(location.hash, "#/reception/record/patient-abc");
      assert.equal(parseShellHash(location.hash).route, "registration-patient-record");
    } finally {
      globalThis.window = prior;
    }
  });
});

describe("parseShellHash", () => {
  it("opens the internal Messages workspace", () => {
    assert.equal(parseShellHash("#/messages").route, "messages");
    const thread = parseShellHash("#/messages/conversation-1");
    assert.equal(thread.route, "messages");
    assert.equal(thread.section, "conversation-1");
    assert.equal(thread.navItemId, "messages");
    assert.equal(parseShellHash("#/messages/call").section, "call");
    assert.equal(parseShellHash("#/messages/call").navItemId, "message-calls");
  });

  it("redirects pharmacy ready-to-dispense to prescriptions", () => {
    const parsed = parseShellHash("#/pharmacy/ready");
    assert.equal(parsed.route, "pharmacy");
    assert.equal(parsed.section, "prescriptions");
    assert.equal(parsed.navItemId, "prescriptions");
  });

  it("accepts the ready-to-dispense alias as prescriptions", () => {
    const parsed = parseShellHash("#/pharmacy/ready-to-dispense");
    assert.equal(parsed.route, "pharmacy");
    assert.equal(parsed.section, "prescriptions");
  });

  it("keeps radiology orders inside radiology", () => {
    const parsed = parseShellHash("#/radiology/orders");
    assert.equal(parsed.route, "radiology");
    assert.equal(parsed.section, "worklist");
    assert.equal(parsed.navItemId, "worklist");
  });

  it("opens the radiology worklist on the radiology desk", () => {
    const parsed = parseShellHash("#/radiology/worklist");
    assert.equal(parsed.route, "radiology");
    assert.equal(parsed.section, "worklist");
    assert.equal(parsed.navItemId, "worklist");
  });

  it("opens radiology new study and imaging history", () => {
    assert.equal(parseShellHash("#/radiology/new-study").navItemId, "new-study");
    assert.equal(parseShellHash("#/radiology/direct").navItemId, "new-study");
    assert.equal(parseShellHash("#/radiology/history").navItemId, "history");
    assert.equal(parseShellHash("#/radiology/studies").section, "history");
  });

  it("opens radiology external study detail", () => {
    assert.equal(
      parseShellHash("#/radiology/external/radiology-ext%3Atoken%3A0").route,
      "radiology-external",
    );
  });

  it("keeps laboratory orders, pending, and lab aliases inside laboratory", () => {
    assert.equal(parseShellHash("#/laboratory/orders").route, "laboratory");
    assert.equal(parseShellHash("#/lab").route, "laboratory");
    assert.equal(parseShellHash("#/lab/pending").navItemId, "pending");
    assert.equal(parseShellHash("#/lab/orders/abc").route, "laboratory-order");
    assert.equal(parseShellHash("#/laboratory/pricing").navItemId, "pricing");
    assert.equal(parseShellHash("#/laboratory/hospital-tests").navItemId, "hospital-tests");
    assert.equal(parseShellHash("#/laboratory/catalogue").navItemId, "hospital-tests");
    assert.equal(parseShellHash("#/laboratory/new-order").navItemId, "new-order");
    assert.equal(parseShellHash("#/laboratory/direct").navItemId, "new-order");
    assert.equal(parseShellHash("#/laboratory/history").navItemId, "history");
    assert.equal(parseShellHash("#/laboratory/studies").section, "history");
    assert.equal(parseShellHash("#/laboratory/not-a-screen").route, "laboratory");
  });

  it("opens laboratory external patient detail", () => {
    assert.equal(
      parseShellHash("#/laboratory/external/EXT-LAB-000001").route,
      "laboratory-external",
    );
    const prior = globalThis.window;
    const location = { hash: "" };
    globalThis.window = { location } as Window & typeof globalThis;
    try {
      openLaboratoryExternalPatient("EXT-LAB-000001");
      assert.equal(location.hash, "#/laboratory/external/EXT-LAB-000001");
      assert.equal(readLaboratoryExternalId(), "EXT-LAB-000001");
    } finally {
      globalThis.window = prior;
    }
  });

  it("opens a laboratory order detail route with patient and visit identity", () => {
    const parsed = parseShellHash(
      "#/laboratory/order/ord-9?patient=pat-1&visit=vis-1",
    );
    assert.equal(parsed.route, "laboratory-order");
    const prior = globalThis.window;
    globalThis.window = {
      location: { hash: "#/laboratory/order/ord-9?patient=pat-1&visit=vis-1" },
    } as Window & typeof globalThis;
    try {
      assert.deepEqual(readLaboratoryOrderExpectedIdentity(), {
        patientUuid: "pat-1",
        visitUuid: "vis-1",
      });
    } finally {
      globalThis.window = prior;
    }
  });

  it("keeps nursing ward board inside nursing", () => {
    const parsed = parseShellHash("#/nursing/ward-board");
    assert.equal(parsed.route, "nursing");
    assert.equal(parsed.section, "ward-board");
    assert.equal(parsed.navItemId, "ward-board");
  });

  it("keeps nursing patients, admissions, and discharges inside nursing", () => {
    assert.equal(parseShellHash("#/nursing/patients").navItemId, "patients");
    assert.equal(parseShellHash("#/nursing/visits").navItemId, "todays-visits");
    assert.equal(parseShellHash("#/nursing/visits").section, "visits");
    assert.equal(parseShellHash("#/nursing/todays-visits").navItemId, "todays-visits");
    assert.equal(parseShellHash("#/nursing/admissions").navItemId, "admissions");
    assert.equal(parseShellHash("#/nursing/transfers").navItemId, "transfers");
    assert.equal(parseShellHash("#/nursing/discharges").navItemId, "discharges");
    assert.equal(parseShellHash("#/nursing/wards").navItemId, "ward-board");
    assert.equal(parseShellHash("#/nursing/discharge").navItemId, "discharges");
  });

  it("opens a nursing treatment visit inside the nursing patient workspace", () => {
    const parsed = parseShellHash(
      "#/nursing/patient/patient-1/treatment/treatment-1",
    );
    assert.equal(parsed.route, "nursing-patient");
  });

  it("keeps unknown nursing suffixes inside nursing", () => {
    assert.equal(parseShellHash("#/nursing/not-a-screen").route, "nursing");
    assert.equal(parseShellHash("#/nursing/not-a-screen").navItemId, null);
  });

  it("keeps registration visits inside registration", () => {
    const parsed = parseShellHash("#/registration-desk/visits");
    assert.equal(parsed.route, "registration-desk");
    assert.equal(parsed.section, "visits");
  });

  it("maps reception hashes to the reception workspace", () => {
    assert.equal(parseShellHash("#/reception").route, "registration-desk");
    assert.equal(parseShellHash("#/reception/visits").route, "registration-desk");
    assert.equal(parseShellHash("#/reception/visits").navItemId, "todays-visits");
    assert.equal(parseShellHash("#/reception/patients").route, "registration-patients");
    assert.equal(parseShellHash("#/reception/patients").navItemId, "patients");
    assert.equal(parseShellHash("#/reception/record/abc").route, "registration-patient-record");
    assert.equal(parseShellHash("#/reception/record/abc").navItemId, "patients");
    assert.equal(parseShellHash("#/reception/visit").route, "registration-visit");
    assert.equal(parseShellHash("#/reception/visit/abc").route, "registration-visit");
    assert.equal(parseShellHash("#/reception/antenatal").route, "registration-antenatal");
    assert.equal(parseShellHash("#/reception/antenatal/abc").route, "registration-antenatal");
    assert.equal(parseShellHash("#/reception/antenatal").navItemId, "antenatal");
    assert.equal(
      parseShellHash("#/reception/antenatal/register").route,
      "registration-antenatal-register",
    );
    assert.equal(parseShellHash("#/reception/antenatal/register").navItemId, "antenatal");
    assert.equal(parseShellHash("#/reception/register").route, "registration-register");
    assert.equal(parseShellHash("#/reception/register/abc").route, "registration-register");
    assert.equal(parseShellHash("#/reception/families").route, "registration-families");
    assert.equal(parseShellHash("#/reception/families").navItemId, "families");
    assert.equal(parseShellHash("#/reception/family/fam-1").route, "registration-family");
    assert.equal(parseShellHash("#/reception/family/fam-1").navItemId, "families");
    assert.equal(parseShellHash("#/reception/patient/abc").route, "registration-patient");
    assert.equal(parseShellHash("#/reception/patient/aaa").route, parseShellHash("#/reception/patient/bbb").route);
    assert.equal(parseShellHash("#/reception/account/abc").route, "patient-account");
    assert.equal(parseShellHash("#/reception/pricing").navItemId, "pricing");
  });

  it("keeps unknown reception suffixes inside reception", () => {
    assert.equal(parseShellHash("#/reception/not-a-screen").route, "registration-desk");
  });

  it("keeps accountant payments inside accountant", () => {
    const parsed = parseShellHash("#/accountant/payments");
    assert.equal(parsed.route, "accountant");
    assert.equal(parsed.section, "payments");
    assert.equal(parseShellHash("#/accountant/outstanding").route, "accountant");
    assert.equal(parseShellHash("#/accountant/receipts").section, "payments");
  });

  it("opens the shared HMO patient list", () => {
    const parsed = parseShellHash("#/hmo");
    assert.equal(parsed.route, "hmo");
    assert.equal(parsed.section, "hmo");
    assert.equal(parsed.navItemId, "hmo");
  });

  it("keeps the doctor queue inside clinical", () => {
    const parsed = parseShellHash("#/doctor/queue");
    assert.equal(parsed.route, "doctor");
    assert.equal(parsed.section, "queue");
  });

  it("opens Pharmacy medicines on the clinical desk", () => {
    const parsed = parseShellHash("#/doctor/pharmacy-medicines");
    assert.equal(parsed.route, "doctor");
    assert.equal(parsed.section, "pharmacy-medicines");
    assert.equal(parsed.navItemId, "pharmacy-medicines");
    assert.equal(parseShellHash("#/doctor/medicines").navItemId, "pharmacy-medicines");
  });

  it("keeps a selected-visit Clinical hash inside consultation", () => {
    assert.equal(parseShellHash("#/doctor/patient/patient-1/visit/visit-1").route, "consultation");
    assert.equal(parseShellHash("#/doctor/patient/patient-1").route, "consultation");
  });

  it("keeps a selected-visit Patient Account hash inside patient-account", () => {
    assert.equal(parseShellHash("#/patient-account/patient-1/visit/visit-1").route, "patient-account");
    assert.equal(parseShellHash("#/patient-account/patient-1").route, "patient-account");
    assert.equal(
      parseShellHash("#/patient-account/patient-1/invoice/12").route,
      "patient-account-invoice",
    );
  });

  it("keeps unknown doctor suffixes inside clinical", () => {
    assert.equal(parseShellHash("#/doctor/not-a-screen").route, "doctor");
    assert.equal(parseShellHash("#/doctor/not-a-screen").navItemId, null);
  });

  it("does not treat a clinical hash as Administration", () => {
    assert.equal(parseShellHash("#/doctor").route, "doctor");
    assert.equal(parseShellHash("#/administration").route, "unavailable");
  });

  it("does not treat a bare in-page id as Administration", () => {
    assert.equal(parseShellHash("#ready").route, "unavailable");
    assert.equal(parseShellHash("#orders").route, "unavailable");
    assert.equal(parseShellHash("#/home").route, "home");
  });

  it("opens only the approved Hospital Administration routes", () => {
    assert.equal(parseShellHash("#/staff-accounts").route, "staff-accounts");
    assert.equal(parseShellHash("#/department-access").route, "department-access");
    assert.equal(parseShellHash("#/admin/analytics").route, "admin-analytics");
    assert.equal(parseShellHash("#/admin/analytics").navItemId, "admin-analytics");
    assert.equal(parseShellHash("#/admin/audit").route, "admin-audit");
    assert.equal(parseShellHash("#/admin/audit").navItemId, "admin-audit");
    assert.equal(parseShellHash("#/admin/export").route, "admin-export");
    assert.equal(parseShellHash("#/admin/export").navItemId, "admin-export");
    assert.equal(parseShellHash("#/admin/log").route, "admin-log");
    assert.equal(parseShellHash("#/admin/log").navItemId, "admin-log");
    assert.equal(parseShellHash("#/admin/patients").route, "admin-patients");
    assert.equal(parseShellHash("#/admin/patients").navItemId, "admin-patients");
    assert.equal(parseShellHash("#/admin/hmo-bills").route, "admin-hmo-bills");
    assert.equal(parseShellHash("#/admin/hmo-bills").navItemId, "admin-hmo-bills");
    assert.equal(parseShellHash("#/admin/certificates").route, "admin-certificates");
    assert.equal(parseShellHash("#/admin/certificates").navItemId, "admin-certificates");
    assert.equal(parseShellHash("#/admin/patient/abc").route, "admin-patient-record");
    assert.equal(parseShellHash("#/admin/patient/abc").navItemId, "admin-patients");
    assert.equal(parseShellHash("#/system-settings").route, "system-settings");
    assert.equal(parseShellHash("#/admin").route, "unavailable");
  });

  it("keeps pharmacy prescriptions inside pharmacy", () => {
    const parsed = parseShellHash("#/pharmacy/prescriptions");
    assert.equal(parsed.route, "pharmacy");
    assert.equal(parsed.section, "prescriptions");
    assert.equal(parsed.navItemId, "prescriptions");
  });

  it("opens pharmacy drug pricing inside pharmacy", () => {
    const parsed = parseShellHash("#/pharmacy/pricing");
    assert.equal(parsed.route, "pharmacy");
    assert.equal(parsed.section, "pricing");
    assert.equal(parsed.navItemId, "pricing");
  });

  it("opens the pharmacy drug catalogue", () => {
    const parsed = parseShellHash("#/pharmacy/catalogue");
    assert.equal(parsed.route, "pharmacy");
    assert.equal(parsed.section, "catalogue");
    assert.equal(parsed.navItemId, "catalogue");
    assert.equal(parseShellHash("#/pharmacy/drugs").navItemId, "catalogue");
  });

  it("opens add medicine from the drug catalogue hash", () => {
    const parsed = parseShellHash("#/pharmacy/catalogue/add");
    assert.equal(parsed.route, "pharmacy");
    assert.equal(parsed.section, "catalogue");
    assert.equal(parsed.navItemId, "catalogue");
    assert.equal(pharmacyCatalogueAddRequested("#/pharmacy/catalogue/add"), true);
    assert.equal(pharmacyCatalogueAddRequested("#/pharmacy/add-medicine"), true);
    assert.equal(pharmacyCatalogueAddRequested("#/pharmacy/catalogue"), false);
    assert.equal(pharmacyCatalogueAddRequested("#/pharmacy/inventory"), false);
  });

  it("opens pharmacy inventory", () => {
    const parsed = parseShellHash("#/pharmacy/inventory");
    assert.equal(parsed.route, "pharmacy");
    assert.equal(parsed.section, "inventory");
    assert.equal(parsed.navItemId, "inventory");
    assert.equal(parseShellHash("#/pharmacy/stock").navItemId, "inventory");
  });

  it("opens pharmacy sales history and aliases dispensed", () => {
    const parsed = parseShellHash("#/pharmacy/sales-history");
    assert.equal(parsed.route, "pharmacy");
    assert.equal(parsed.section, "sales-history");
    assert.equal(parsed.navItemId, "sales-history");
    assert.equal(parseShellHash("#/pharmacy/dispensed").section, "sales-history");
    assert.equal(parseShellHash("#/pharmacy/dispensed").navItemId, "sales-history");
  });

  it("opens a pharmacy prescription detail route", () => {
    const parsed = parseShellHash("#/pharmacy/prescription/abc-order");
    assert.equal(parsed.route, "pharmacy-prescription");
  });

  it("keeps unknown pharmacy suffixes inside pharmacy", () => {
    assert.equal(parseShellHash("#/pharmacy/not-a-screen").route, "pharmacy");
  });

  it("treats an unknown department prefix as unavailable, not Administration", () => {
    assert.equal(parseShellHash("#/not-a-department").route, "unavailable");
    assert.equal(parseShellHash("#/admin").route, "unavailable");
  });

  it("keeps a typed accountant hash as accountant so access control can deny it", () => {
    assert.equal(parseShellHash("#/accountant").route, "accountant");
  });
});

describe("fallbackRouteForUser", () => {
  it("sends a pharmacy user away from Administration for unknown hashes", () => {
    assert.equal(fallbackRouteForUser("unavailable", false, "pharmacy"), "pharmacy");
    assert.equal(fallbackRouteForUser("home", false, "pharmacy"), "pharmacy");
  });

  it("sends a reception user away from Administration for unknown hashes", () => {
    assert.equal(fallbackRouteForUser("unavailable", false, "registration-desk"), "registration-desk");
    assert.equal(fallbackRouteForUser("home", false, "registration-desk"), "registration-desk");
  });

  it("returns other staff to their department, not Administration", () => {
    assert.equal(fallbackRouteForUser("unavailable", false, "radiology"), "radiology");
    assert.equal(fallbackRouteForUser("unavailable", false, "laboratory"), "laboratory");
    assert.equal(fallbackRouteForUser("unavailable", false, "nursing"), "nursing");
    assert.equal(fallbackRouteForUser("unavailable", false, "registration-desk"), "registration-desk");
    assert.equal(fallbackRouteForUser("unavailable", false, "accountant"), "accountant");
    assert.equal(fallbackRouteForUser("unavailable", false, "doctor"), "doctor");
  });

  it("keeps Administration home only for admin", () => {
    assert.equal(fallbackRouteForUser("home", false, "pharmacy"), "pharmacy");
    assert.equal(fallbackRouteForUser("home", true, "home"), "home");
    assert.equal(fallbackRouteForUser("unavailable", true, "home"), "unavailable");
  });

  it("keeps a pharmacy route on a pharmacy user", () => {
    assert.equal(fallbackRouteForUser("pharmacy", false, "pharmacy"), "pharmacy");
  });

  it("does not rewrite a typed other-department hash into Administration", () => {
    assert.equal(fallbackRouteForUser("accountant", false, "pharmacy"), "accountant");
    assert.equal(fallbackRouteForUser("radiology", false, "pharmacy"), "radiology");
  });
});

describe("screen history", () => {
  const prior = globalThis.window;

  function useHash(hash: string) {
    const location = { hash };
    globalThis.window = { location } as Window & typeof globalThis;
    return location;
  }

  it("returns from an order to the pending list, then to the previous department", () => {
    const location = useHash("#/laboratory/pending");
    resetScreenHistoryForTests();
    try {
      rememberScreen();
      location.hash = "#/pharmacy";
      rememberScreen();
      location.hash = "#/laboratory/pending";
      rememberScreen();
      location.hash = "#/laboratory/order/ord-1";
      rememberScreen();
      returnToPreviousScreen("#/laboratory");
      assert.equal(location.hash, "#/laboratory/pending");
      returnToPreviousScreen("#/laboratory");
      assert.equal(location.hash, "#/pharmacy");
    } finally {
      globalThis.window = prior;
      resetScreenHistoryForTests();
    }
  });

  it("walks patient then order back to the list", () => {
    const location = useHash("#/laboratory/pending");
    resetScreenHistoryForTests();
    try {
      rememberScreen("#/laboratory/pending");
      location.hash = "#/laboratory/patient/abc";
      rememberScreen();
      location.hash = "#/laboratory/order/ord-1";
      rememberScreen();
      returnToPreviousScreen("#/laboratory");
      assert.equal(location.hash, "#/laboratory/patient/abc");
      returnToPreviousScreen("#/laboratory");
      assert.equal(location.hash, "#/laboratory/pending");
    } finally {
      globalThis.window = prior;
      resetScreenHistoryForTests();
    }
  });

  it("uses the department home when the page was opened directly", () => {
    const location = useHash("#/laboratory/order/ord-1");
    resetScreenHistoryForTests(["#/laboratory/order/ord-1"]);
    try {
      returnToPreviousScreen("#/laboratory");
      assert.equal(location.hash, "#/laboratory");
    } finally {
      globalThis.window = prior;
      resetScreenHistoryForTests();
    }
  });

  it("does not skip the real previous screen when the same page is recorded twice", () => {
    const location = useHash("#/nursing/ward-board");
    resetScreenHistoryForTests();
    try {
      rememberScreen();
      location.hash = "#/nursing/patient/abc";
      rememberScreen();
      rememberScreen("#/nursing/patient/abc");
      returnToPreviousScreen("#/nursing/ward-board");
      assert.equal(location.hash, "#/nursing/ward-board");
    } finally {
      globalThis.window = prior;
      resetScreenHistoryForTests();
    }
  });

  it("keeps pharmacy back on the screen that opened the prescription", () => {
    const location = useHash("#/pharmacy/prescriptions");
    resetScreenHistoryForTests();
    try {
      rememberScreen();
      location.hash = "#/pharmacy/prescription/ord-1";
      rememberScreen();
      backWithinPharmacy("prescriptions");
      assert.equal(location.hash, "#/pharmacy/prescriptions");
    } finally {
      globalThis.window = prior;
      resetScreenHistoryForTests();
    }
  });

  it("maps a detail route back to its department only as a fallback", () => {
    assert.equal(shellRouteHref("laboratory-order"), "#/laboratory");
    assert.equal(shellRouteHref("registration-patients"), "#/reception/patients");
    assert.equal(shellRouteHref("accountant-patient"), "#/accountant");
    assert.equal(shellRouteHref("unavailable"), "");
  });
});
