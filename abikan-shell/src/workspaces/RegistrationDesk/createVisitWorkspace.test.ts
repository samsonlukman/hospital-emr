import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { RECEPTION_NAV } from "../../config/receptionNav.ts";
import { parseShellHash } from "../../app/hashRoute.ts";
import { createVisitShowsCardFee } from "./receptionVisit.ts";

const source = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "CreateVisitWorkspace.tsx"),
  "utf8",
);

describe("Create Visit workspace isolation", () => {
  it("is a dedicated Reception action, not hidden behind a patient profile", () => {
    const item = RECEPTION_NAV[0]?.items.find((entry) => entry.id === "create-visit");
    assert.equal(item && "href" in item ? item.href : "", "#/reception/visit");
    assert.equal(parseShellHash("#/reception/visit").route, "registration-visit");
    assert.equal(parseShellHash("#/reception/register").route, "registration-register");
  });

  it("does not load or render a registration card fee", () => {
    assert.equal(source.includes("fetchRegistrationCharge"), false);
    assert.equal(source.includes("createRegistrationCharge"), false);
    assert.equal(source.includes("fetchRegistrationMetadata"), false);
    assert.equal(source.includes("Individual Card"), false);
    assert.equal(source.includes("Family Card"), false);
    assert.equal(source.includes("Unable to load this patient") && source.includes("fetchPatientIdentity"), true);
    assert.equal(createVisitShowsCardFee(), false);
  });

  it("does not create an antenatal fee or antenatal card on Create Visit", () => {
    assert.equal(source.includes("AncVisitFeeCard"), false);
    assert.equal(source.includes("AncRegistrationFeeCard"), false);
    assert.equal(source.includes("AntenatalCardView"), false);
    assert.equal(source.includes("createAncCharge"), false);
    assert.equal(source.includes("fetchAncSummary"), false);
    assert.equal(source.includes("canOfferAncVisitType"), false);
    assert.equal(source.includes("openAntenatalRegistration"), false);
    assert.equal(source.includes("Antenatal registration required"), false);
    assert.equal(source.includes("isGeneralReceptionVisitType"), true);
    assert.equal(source.includes("createRegistrationCharge"), false);
  });

  it("uses the visit context route, not the card-charge route", () => {
    assert.equal(source.includes("fetchRegistrationVisitContext"), true);
    assert.equal(source.includes("CONTINUE_EXISTING_VISIT_LABEL"), true);
    assert.equal(source.includes("Register a new patient"), true);
  });

  it("offers an explicit Close Visit confirmation for an open OPD visit", () => {
    assert.equal(source.includes("closeRegistrationVisit"), true);
    assert.equal(source.includes("CLOSE_VISIT_CONFIRM_TITLE"), true);
    assert.equal(source.includes("canCloseOutpatientVisit"), true);
    assert.equal(source.includes("outpatientVisitStatus"), true);
    assert.equal(source.includes("Creating visit..."), true);
  });

  it("does not fall through to the generic department home", () => {
    const router = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "../../app/WorkspaceRouter.tsx"),
      "utf8",
    );
    assert.equal(router.includes("!showCreateVisit"), true);
    assert.equal(router.includes("<CreateVisitWorkspace"), true);
    assert.equal(router.includes("<AntenatalRegistrationWorkspace"), true);
  });
});
