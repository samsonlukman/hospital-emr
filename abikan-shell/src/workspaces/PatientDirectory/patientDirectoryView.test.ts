import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { PatientRecord } from "../../types/patientDirectory.ts";
import {
  displayPatientField,
  formatDeathDate,
  formatPatientDate,
  parsePatientPageSize,
  patientAddressLines,
  patientAliveLabel,
  patientFullName,
  patientPageRange,
  patientPhone,
  patientSexLabel,
  patientStatusLabel,
} from "./patientDirectoryView.ts";

describe("Patient directory paging", () => {
  it("keeps only 50 or 100 patients on a page", () => {
    assert.equal(parsePatientPageSize(50), 50);
    assert.equal(parsePatientPageSize("100"), 100);
    assert.equal(parsePatientPageSize("25"), 50);
  });

  it("shows a hospital-readable page range", () => {
    assert.equal(patientPageRange(0, 50, 240), "1–50 of 240");
    assert.equal(patientPageRange(100, 40, 140), "101–140 of 140");
    assert.equal(patientPageRange(0, 0, 0), "No patients on this page");
  });

  it("keeps empty register fields as a dash", () => {
    assert.equal(displayPatientField("ABC123"), "ABC123");
    assert.equal(displayPatientField("  "), "—");
  });
});

describe("Patient record details", () => {
  const record: PatientRecord = {
    status: "ok",
    uuid: "pat-1",
    identifier: "ABC123",
    givenName: "Adaeze",
    middleName: "",
    familyName: "Okafor",
    gender: "F",
    birthdate: "1990-01-15",
    birthdateEstimated: false,
    age: 36,
    attributes: { phoneNumber: "08012345678" },
    address: { address1: "12 Hospital Road", cityVillage: "Ilorin" },
    identifiers: [{ identifier: "ABC123", preferred: true, type: "Patient Identifier" }],
    registeredOn: "2026-09-07",
    alive: true,
    deathDate: "",
  };

  it("shows hospital-readable name, sex, date of birth, and phone", () => {
    assert.equal(patientFullName(record), "Adaeze Okafor");
    assert.equal(patientSexLabel("F"), "Female");
    assert.equal(formatPatientDate("1990-01-15"), "15 Jan 1990");
    assert.equal(patientPhone(record), "08012345678");
    assert.deepEqual(patientAddressLines(record), [
      { label: "Address", value: "12 Hospital Road" },
      { label: "City / town", value: "Ilorin" },
    ]);
  });

  it("formats date of death as DD/MM/YYYY", () => {
    assert.equal(formatDeathDate("2026-08-15"), "15/08/2026");
    assert.equal(patientStatusLabel(true), "Alive");
    assert.equal(patientStatusLabel(false), "Dead");
    assert.equal(patientAliveLabel("No"), "No");
  });
});
