import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { hasAdminAnalyticsAccess, hasAdminAuditReadAccess, hasHospitalAdminAccess, isTechnicalSuperAdmin } from "./adminAccess.ts";
import { hasReceptionAccess } from "./receptionAccess.ts";

const RADIOLOGY = "app:radiology-upload";
const ACCOUNTANT = "abikan:accountant";
const CLINICAL = "app:clinical";
const NURSING = "app:adt";
const LABORATORY = "app:lab-lite";
const PHARMACY = "bahmni:clinical:dispense";
const RECEPTION = "app:registration";

describe("Reception access", () => {
  it("allows the existing Reception role and registration privilege", () => {
    assert.equal(hasReceptionAccess(["Abikan:Reception"], []), true);
    assert.equal(hasReceptionAccess(["Abikan:Registration"], []), true);
    assert.equal(hasReceptionAccess([], ["app:registration"]), true);
  });

  it("does not allow other departments into Reception", () => {
    assert.equal(hasReceptionAccess(["Abikan:Doctor"], ["app:clinical"]), false);
    assert.equal(hasReceptionAccess(["Abikan:Accountant"], ["abikan:accountant"]), false);
    assert.equal(hasReceptionAccess(["Abikan:Nursing"], ["app:adt"]), false);
    assert.equal(hasReceptionAccess(["Abikan:Pharmacy"], ["bahmni:clinical:dispense"]), false);
    assert.equal(hasReceptionAccess(["Abikan:Laboratory"], ["app:lab-lite"]), false);
    assert.equal(hasReceptionAccess([], []), false);
  });
});

describe("Hospital Administration access", () => {
  it("allows the dedicated Hospital Admin privilege and existing technical admins", () => {
    assert.equal(hasHospitalAdminAccess([], ["abikan:admin:staff"]), true);
    assert.equal(hasHospitalAdminAccess(["SuperAdmin"], []), true);
    assert.equal(hasHospitalAdminAccess(["System Developer"], []), true);
  });

  it("distinguishes technical superadmin from hospital administrator privilege", () => {
    assert.equal(isTechnicalSuperAdmin(["SuperAdmin"]), true);
    assert.equal(isTechnicalSuperAdmin(["System Developer"]), true);
    assert.equal(isTechnicalSuperAdmin(["Abikan:Hospital Admin"]), false);
    assert.equal(hasHospitalAdminAccess(["Abikan:Hospital Admin"], ["abikan:admin:staff"]), true);
    assert.equal(
      hasAdminAnalyticsAccess(
        ["Abikan:Hospital Admin"],
        ["abikan:admin:staff", "abikan:admin:analytics"],
      ),
      true,
    );
    assert.equal(
      hasAdminAuditReadAccess(
        ["Abikan:Hospital Admin"],
        ["abikan:admin:staff", "abikan:admin:audit-read"],
      ),
      true,
    );
    assert.equal(
      hasAdminAnalyticsAccess(["Abikan:Hospital Admin"], ["abikan:admin:staff"]),
      false,
    );
    assert.equal(hasAdminAnalyticsAccess(["Abikan:Doctor"], ["app:clinical"]), false);
    assert.equal(hasAdminAuditReadAccess(["Abikan:Nursing"], ["app:adt"]), false);
  });

  it("lets a Hospital Administrator open every department", () => {
    const source = readFileSync(new URL("./workspaceMap.ts", import.meta.url), "utf8");
    assert.match(source, /role === "Abikan:Hospital Admin"/);
    assert.match(source, /canOpenPharmacy[\s\S]*isFullAccessAdmin\(context\)/);
    assert.match(source, /canOpenRadiology[\s\S]*isFullAccessAdmin\(context\)/);
  });

  it("denies every operational department", () => {
    assert.equal(hasHospitalAdminAccess(["Abikan:Doctor"], ["app:clinical"]), false);
    assert.equal(
      hasHospitalAdminAccess(["Abikan:Radiology"], ["app:radiology-upload"]),
      false,
    );
    assert.equal(
      hasHospitalAdminAccess(["Abikan:Accountant"], ["abikan:accountant"]),
      false,
    );
    assert.equal(hasHospitalAdminAccess(["Abikan:Reception"], ["app:registration"]), false);
    assert.equal(hasHospitalAdminAccess(["Abikan:Nursing"], ["app:adt"]), false);
  });
});

describe("Runtime department access", () => {
  it("allows Radiology only for a radiologist", () => {
    const roles = ["Abikan:Radiology"];
    const privileges = [RADIOLOGY];
    assert.equal(privileges.includes(RADIOLOGY), true);
    assert.equal(hasReceptionAccess(roles, privileges), false);
    assert.equal(privileges.includes(ACCOUNTANT), false);
    assert.equal(privileges.includes(CLINICAL), false);
    assert.equal(privileges.includes(NURSING), false);
    assert.equal(privileges.includes(LABORATORY), false);
    assert.equal(privileges.includes(PHARMACY), false);
    assert.equal(hasHospitalAdminAccess(roles, privileges), false);
  });

  it("allows Radiology and Reception together", () => {
    const roles = ["Abikan:Radiology", "Abikan:Reception"];
    const privileges = [RADIOLOGY, RECEPTION];
    assert.equal(privileges.includes(RADIOLOGY), true);
    assert.equal(hasReceptionAccess(roles, privileges), true);
    assert.equal(privileges.includes(ACCOUNTANT), false);
    assert.equal(privileges.includes(CLINICAL), false);
  });

  it("allows Radiology and Accountant together", () => {
    const roles = ["Abikan:Radiology", "Abikan:Accountant"];
    const privileges = [RADIOLOGY, ACCOUNTANT];
    assert.equal(privileges.includes(RADIOLOGY), true);
    assert.equal(privileges.includes(ACCOUNTANT), true);
    assert.equal(hasReceptionAccess(roles, privileges), false);
    assert.equal(hasHospitalAdminAccess(roles, privileges), false);
  });

  it("allows Radiology, Reception, and Accountant together without other departments", () => {
    const roles = ["Abikan:Radiology", "Abikan:Reception", "Abikan:Accountant"];
    const privileges = [RADIOLOGY, RECEPTION, ACCOUNTANT];
    assert.equal(privileges.includes(RADIOLOGY), true);
    assert.equal(hasReceptionAccess(roles, privileges), true);
    assert.equal(privileges.includes(ACCOUNTANT), true);
    assert.equal(privileges.includes(CLINICAL), false);
    assert.equal(privileges.includes(NURSING), false);
    assert.equal(privileges.includes(LABORATORY), false);
    assert.equal(privileges.includes(PHARMACY), false);
    assert.equal(hasHospitalAdminAccess(roles, privileges), false);
  });

  it("does not forbid Clinical + Radiology or Nursing + Radiology at the session layer", () => {
    const clinicalRadiology = {
      roles: ["Abikan:Doctor", "Abikan:Radiology"],
      privileges: [CLINICAL, RADIOLOGY],
    };
    const nursingRadiology = {
      roles: ["Abikan:Nursing", "Abikan:Radiology"],
      privileges: [NURSING, RADIOLOGY],
    };
    assert.equal(clinicalRadiology.privileges.includes(CLINICAL), true);
    assert.equal(clinicalRadiology.privileges.includes(RADIOLOGY), true);
    assert.equal(nursingRadiology.privileges.includes(NURSING), true);
    assert.equal(nursingRadiology.privileges.includes(RADIOLOGY), true);
    assert.equal(hasHospitalAdminAccess(clinicalRadiology.roles, clinicalRadiology.privileges), false);
  });
});

describe("Accommodation price access", () => {
  it("opens accommodation prices for Hospital Admin, not Nursing", () => {
    const source = readFileSync(new URL("./workspaceMap.ts", import.meta.url), "utf8");
    assert.match(source, /canOpenAccommodationSettings[\s\S]*return canOpenAdministration\(context\)/);
    assert.equal(hasHospitalAdminAccess(["Abikan:Hospital Admin"], ["abikan:admin:staff"]), true);
    assert.equal(hasHospitalAdminAccess(["Abikan:Nursing"], [NURSING]), false);
    assert.equal(hasHospitalAdminAccess(["Abikan:Doctor"], [CLINICAL]), false);
  });
});
