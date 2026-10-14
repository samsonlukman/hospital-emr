import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { DepartmentAccessRow, StaffAccount } from "../../types/administration.ts";
import {
  emrAccessLabel,
  filterAccess,
  filterStaff,
  initialPasswordProblem,
  providerStatusLabel,
  selectedAccessStaff,
  showsHrFields,
  signInPasswordProblem,
  staffDepartmentLabel,
  staffRoleLabel,
  validateStaffDraft,
} from "./adminView.ts";

const staff: StaffAccount[] = [
  {
    userUuid: "doctor-1",
    username: "doctor.abikan",
    displayName: "Clinical Doctor",
    enabled: true,
    departments: [{ id: "clinical", label: "Clinical", roleLabel: "Doctor" }],
    preferredDepartment: { id: "clinical", label: "Clinical" },
    providerStatus: "ready",
    providerRequired: true,
  },
  {
    userUuid: "radio-1",
    username: "radiology.abikan",
    displayName: "Radiology Staff",
    enabled: false,
    departments: [{ id: "radiology", label: "Radiology", roleLabel: "Radiologist" }],
    preferredDepartment: { id: "radiology", label: "Radiology" },
    providerStatus: "missing",
    providerRequired: true,
  },
  {
    userUuid: "accountant-1",
    username: "accountant.abikan",
    displayName: "Accountant Staff",
    enabled: true,
    departments: [{ id: "accountant", label: "Accountant", roleLabel: "Accountant" }],
    preferredDepartment: { id: "accountant", label: "Accountant" },
    providerStatus: "not_required",
    providerRequired: false,
  },
];

describe("Staff HR fields", () => {
  it("collects NIN and HR details for every staff type except outsourced doctors", () => {
    assert.equal(showsHrFields("", ""), false);
    assert.equal(showsHrFields("clinical", ""), false);
    assert.equal(showsHrFields("clinical", "external"), false);
    assert.equal(showsHrFields("clinical", "permanent"), true);
    assert.equal(showsHrFields("hospital_admin", ""), true);
    assert.equal(showsHrFields("nursing", ""), true);
    assert.equal(showsHrFields("reception", ""), true);
    assert.equal(showsHrFields("security", ""), true);
    assert.equal(showsHrFields("attendant", ""), true);
  });
});

describe("Admin staff filters", () => {
  it("searches by staff name and username", () => {
    assert.deepEqual(filterStaff(staff, "Clinical Doctor", "all", "all"), [staff[0]]);
    assert.deepEqual(filterStaff(staff, "accountant.abikan", "all", "all"), [staff[2]]);
  });

  it("filters by approved department and status", () => {
    assert.deepEqual(filterStaff(staff, "", "radiology", "all"), [staff[1]]);
    assert.deepEqual(filterStaff(staff, "", "all", "disabled"), [staff[1]]);
    assert.deepEqual(filterStaff(staff, "", "clinical", "active"), [staff[0]]);
  });

  it("filters clinical doctors by employment type", () => {
    const permanent = { ...staff[0], employmentType: "permanent" as const };
    const sourced = { ...staff[0], userUuid: "doctor-2", employmentType: "external" as const };
    assert.deepEqual(filterStaff([permanent, sourced], "", "clinical", "all", "permanent"), [permanent]);
    assert.deepEqual(filterStaff([permanent, sourced], "", "clinical", "all", "external"), [sourced]);
  });

  it("uses plain provider status labels", () => {
    assert.equal(providerStatusLabel(staff[0]), "Ready");
    assert.equal(providerStatusLabel(staff[1]), "Clinical profile needed");
    assert.equal(providerStatusLabel(staff[2]), "Not required");
  });
});

describe("Add staff validation", () => {
  it("accepts the minimum required account fields", () => {
    assert.equal(
      validateStaffDraft({
        fullName: "Test Doctor",
        username: "test.doctor",
        initialPassword: "Temporary123",
        departments: ["clinical"],
      }),
      "",
    );
  });

  it("uses the same sign-in password rules for new accounts and later changes", () => {
    assert.equal(signInPasswordProblem("Temporary123", "nurse.ade"), "");
    assert.match(signInPasswordProblem("short", "nurse.ade"), /8 characters/);
    assert.match(signInPasswordProblem("password1", "nurse.ade"), /uppercase and lowercase/);
    assert.match(signInPasswordProblem("Temporary", "nurse.ade"), /number/);
    assert.match(signInPasswordProblem("Nurse.ade1", "nurse.ade1"), /username/);
    assert.match(initialPasswordProblem("short", "nurse.ade"), /initial sign-in password/);
  });

  it("rejects invalid username, password, and missing department", () => {
    assert.match(
      validateStaffDraft({
        fullName: "Test Doctor",
        username: "Test Doctor",
        initialPassword: "Temporary123",
        departments: ["clinical"],
      }),
      /username/,
    );
    assert.match(
      validateStaffDraft({
        fullName: "Test Doctor",
        username: "test.doctor",
        initialPassword: "short",
        departments: ["clinical"],
      }),
      /8 characters/,
    );
    assert.match(
      validateStaffDraft({
        fullName: "Test Doctor",
        username: "test.doctor",
        initialPassword: "password1",
        departments: ["clinical"],
      }),
      /uppercase and lowercase/,
    );
    assert.match(
      validateStaffDraft({
        fullName: "Test Doctor",
        username: "test.doctor",
        initialPassword: "Password",
        departments: ["clinical"],
      }),
      /number/,
    );
    assert.match(
      validateStaffDraft({
        fullName: "Test Doctor",
        username: "test.doctor",
        initialPassword: "Temporary123",
        departments: [],
      }),
      /department/,
    );
  });

  it("requires employment type for a new clinical doctor", () => {
    assert.match(
      validateStaffDraft({
        fullName: "Test Doctor",
        username: "test.doctor",
        initialPassword: "Temporary123",
        staffCategory: "clinical",
        departments: ["clinical"],
      }),
      /Permanent or External/,
    );
    assert.equal(
      validateStaffDraft({
        fullName: "Test Doctor",
        username: "test.doctor",
        initialPassword: "Temporary123",
        staffCategory: "clinical",
        employmentType: "external",
        departments: ["clinical"],
      }),
      "",
    );
  });

  it("does not require a username for security or attendant records", () => {
    assert.equal(
      validateStaffDraft({
        fullName: "Gate Security",
        username: "",
        initialPassword: "",
        staffCategory: "security",
        departments: [],
      }),
      "",
    );
    assert.equal(
      validateStaffDraft({
        fullName: "Ward Attendant",
        username: "",
        initialPassword: "",
        staffCategory: "attendant",
        departments: [],
      }),
      "",
    );
  });

  it("allows hospital administrator creation without departments", () => {
    assert.equal(
      validateStaffDraft({
        fullName: "Hospital Administrator",
        username: "hospitaladmin.test",
        initialPassword: "Temporary123",
        accountType: "hospital_administrator",
        departments: [],
      }),
      "",
    );
  });
});

describe("Hospital administrator labels", () => {
  const hospitalAdministrator: StaffAccount = {
    userUuid: "hospital-admin-1",
    username: "hospitaladmin.abikan",
    displayName: "Hospital Administrator",
    enabled: true,
    accountType: "hospital_administrator",
    departments: [],
    preferredDepartment: { id: "administration", label: "Administration" },
    providerStatus: "not_required",
    providerRequired: false,
  };

  it("shows administration labels without department roles", () => {
    assert.equal(staffDepartmentLabel(hospitalAdministrator), "Administration");
    assert.equal(staffRoleLabel(hospitalAdministrator), "Hospital Administrator");
  });
});

describe("EMR access labels", () => {
  it("marks security and attendant as having no account", () => {
    const security: StaffAccount = {
      userUuid: "",
      username: "",
      displayName: "Gate Security",
      enabled: true,
      staffCategory: "security",
      emrAccess: "none",
      departments: [],
      preferredDepartment: null,
      providerStatus: "not_required",
      providerRequired: false,
    };
    assert.equal(emrAccessLabel(security), "No account");
  });
});

describe("Department access filters", () => {
  const rows: DepartmentAccessRow[] = staff.map((item) => ({
    userUuid: item.userUuid,
    displayName: item.displayName,
    username: item.username,
    enabled: item.enabled,
    department: item.departments[0],
  }));

  it("filters access rows without raw privileges", () => {
    assert.deepEqual(filterAccess(rows, "radiology", "all", "all"), [rows[1]]);
    assert.deepEqual(filterAccess(rows, "", "accountant", "active"), [rows[2]]);
  });

  it("does not keep the access dialog open after Close when directory-only staff have no login", () => {
    const directory: StaffAccount[] = [
      ...staff,
      {
        userUuid: "",
        username: "",
        displayName: "Gate Security",
        enabled: true,
        staffCategory: "security",
        emrAccess: "none",
        departments: [],
        preferredDepartment: null,
        providerStatus: "not_required",
        providerRequired: false,
      },
    ];
    assert.equal(selectedAccessStaff(directory, "doctor-1")?.displayName, "Clinical Doctor");
    assert.equal(selectedAccessStaff(directory, ""), null);
  });
});
