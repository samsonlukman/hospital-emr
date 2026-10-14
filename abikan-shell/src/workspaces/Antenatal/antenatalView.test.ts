import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { RECEPTION_NAV } from "../../config/receptionNav.ts";
import { parseShellHash } from "../../app/hashRoute.ts";
import {
  ANC_DEFAULT_FEE_AMOUNT,
  ancNotEnrolledAlertCopy,
  ancNotEnrolledAlertTitle,
  ancVisitTypeLabel,
  canOfferAncVisitType,
  defaultAncFeeInput,
  formatBloodPressure,
  isAncVisitType,
  parseAncFeeAmount,
  shouldShowAncTab,
} from "./antenatalView.ts";
import {
  RECEPTION_START_VISIT_TYPES,
  RECEPTION_VISIT_TYPE_COPY,
  receptionAsksForLocation,
  receptionVisitTypeLabel,
} from "../../config/receptionVisitTypes.ts";

const here = dirname(fileURLToPath(import.meta.url));

describe("antenatal visit type and fee helpers", () => {
  it("uses the Reception ANC label and does not ask for a location", () => {
    assert.equal(RECEPTION_VISIT_TYPE_COPY.ANC.label, "Antenatal Care (ANC)");
    assert.equal(RECEPTION_VISIT_TYPE_COPY.ANC.helper, "Antenatal clinic visit for pregnancy care");
    assert.equal(receptionVisitTypeLabel("ANC"), "Antenatal Care (ANC)");
    assert.equal(ancVisitTypeLabel(), "Antenatal Care (ANC)");
    assert.equal(isAncVisitType("ANC"), true);
    assert.equal(isAncVisitType("anc"), true);
    assert.equal(isAncVisitType("OPD"), false);
    assert.equal(receptionAsksForLocation("ANC"), false);
    assert.equal(RECEPTION_START_VISIT_TYPES.includes("ANC"), true);
  });

  it("defaults the one-time antenatal registration fee to ₦2,000", () => {
    assert.equal(ANC_DEFAULT_FEE_AMOUNT, 2000);
    assert.equal(defaultAncFeeInput(), "2000");
    assert.equal(defaultAncFeeInput(2500), "2500");
    assert.deepEqual(parseAncFeeAmount("2000"), { ok: true, amount: 2000 });
    assert.equal(parseAncFeeAmount("").ok, false);
  });

  it("offers ANC visits only after enrollment", () => {
    assert.equal(canOfferAncVisitType(true), true);
    assert.equal(canOfferAncVisitType(false), false);
    assert.equal(canOfferAncVisitType(undefined), false);
    assert.equal(ancNotEnrolledAlertTitle(), "Antenatal registration required");
    assert.match(ancNotEnrolledAlertCopy(), /Antenatal Care/i);
  });

  it("shows the ANC tab only when the patient has antenatal records", () => {
    assert.equal(shouldShowAncTab(true), true);
    assert.equal(shouldShowAncTab(false), false);
    assert.equal(shouldShowAncTab(undefined), false);
  });

  it("formats blood pressure honestly", () => {
    assert.equal(formatBloodPressure(120, 80), "120/80");
    assert.equal(formatBloodPressure("", ""), "—");
    assert.equal(formatBloodPressure(118, null), "118");
  });
});

describe("antenatal registration reception flow", () => {
  it("routes Reception antenatal search and patient screens", () => {
    assert.equal(parseShellHash("#/reception/antenatal").route, "registration-antenatal");
    assert.equal(parseShellHash("#/reception/antenatal").navItemId, "antenatal");
    assert.equal(parseShellHash("#/reception/antenatal/abc").route, "registration-antenatal");
    assert.equal(parseShellHash("#/reception/anc").route, "registration-antenatal");
    assert.equal(
      parseShellHash("#/reception/antenatal/register").route,
      "registration-antenatal-register",
    );
    assert.equal(parseShellHash("#/reception/antenatal/register").navItemId, "antenatal");
    const item = RECEPTION_NAV[0]?.items.find((entry) => entry.id === "antenatal");
    assert.equal(item && "href" in item ? item.href : "", "#/reception/antenatal");
  });

  it("does not put antenatal enrollment copy on Create Visit", () => {
    const createVisit = readFileSync(
      join(here, "../RegistrationDesk/CreateVisitWorkspace.tsx"),
      "utf8",
    );
    assert.equal(createVisit.includes("Antenatal registration required"), false);
    assert.equal(createVisit.includes("Register this patient for Antenatal Care"), false);
    assert.equal(createVisit.includes("fetchAncSummary"), false);
    assert.equal(createVisit.includes("Open ANC card"), false);
  });

  it("keeps enrollment and one-time fee on the antenatal registration workspace", () => {
    const workspace = readFileSync(join(here, "../RegistrationDesk/AntenatalRegistrationWorkspace.tsx"), "utf8");
    const feeCard = readFileSync(join(here, "AncRegistrationFeeCard.tsx"), "utf8");
    const service = readFileSync(join(here, "../../services/antenatal.ts"), "utf8");
    assert.equal(workspace.includes("AntenatalCardView"), true);
    assert.equal(workspace.includes("AncRegistrationFeeCard"), true);
    assert.equal(workspace.includes("startRegistrationVisit"), true);
    assert.equal(workspace.includes("pregnancyId"), true);
    assert.equal(workspace.includes("Patients with an ANC card"), true);
    assert.equal(workspace.includes("fetchAncCardList"), true);
    assert.equal(workspace.includes("one year"), true);
    assert.equal(workspace.includes("openAntenatalPatientRegister"), true);
    assert.equal(workspace.includes("Register a new antenatal patient"), true);
    assert.equal(workspace.includes("admin-workspace__filters patient-directory__filters"), true);
    assert.equal(workspace.includes("openRegistrationRegister()"), false);
    assert.equal(workspace.includes("Start new pregnancy"), false);
    const cardView = readFileSync(join(here, "AntenatalCardView.tsx"), "utf8");
    assert.equal(cardView.includes("Start new pregnancy"), false);
    assert.equal(cardView.includes("Create antenatal card"), true);
    assert.equal(feeCard.includes("pregnancyId"), true);
    assert.equal(feeCard.includes("visitUuid"), false);
    assert.equal(feeCard.includes("Fee for this antenatal card"), true);
    assert.equal(feeCard.includes("Create antenatal fee"), true);
    assert.equal(feeCard.includes("Enable card"), true);
    assert.equal(service.includes("pregnancyId"), true);
    assert.equal(service.includes("/enroll"), true);
    assert.equal(service.includes("/antenatal/cards"), true);
    assert.match(service, /pregnancyId=\$\{encodeURIComponent\(pregnancyId\)\}/);
  });

  it("lists Antenatal Care separately from patient registration", () => {
    const register = readFileSync(
      join(here, "../RegistrationDesk/RegisterPatientWorkspace.tsx"),
      "utf8",
    );
    const desk = readFileSync(
      join(here, "../RegistrationDesk/RegistrationDeskWorkspace.tsx"),
      "utf8",
    );
    assert.equal(register.includes("Antenatal Card (ANC)"), false);
    assert.equal(register.includes('chooseCard("antenatal")'), false);
    assert.equal(register.includes('purpose="antenatal"') || register.includes("purpose === \"antenatal\""), true);
    assert.equal(register.includes("Register antenatal patient"), true);
    assert.equal(RECEPTION_NAV[0]?.items.find((entry) => entry.id === "antenatal")?.label, "Antenatal Care");
    assert.match(
      desk,
      /onClick=\{\(\) => openAntenatalRegistration\(\)\}>\s*<strong>Antenatal Care<\/strong>/,
    );
  });
});
