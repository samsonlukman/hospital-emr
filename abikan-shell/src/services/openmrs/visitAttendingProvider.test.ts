import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { CONSULTATION_ENCOUNTER_TYPE } from "../../config/clinicalConcepts.ts";
import { visitNumberLabel } from "../../utils/dailyVisitNumber.ts";
import {
  MISSING_ATTENDING_DOCTOR,
  attendedByLabel,
  attendingDoctorFromVisitEncounters,
  attendingDoctorName,
  type VisitEncounterProviderSource,
} from "./visitAttendingProvider.ts";

const LAB_RESULT = "d3bf1623-5e07-11ef-8f7c-0242ac120002";

function consultation(
  overrides: Partial<VisitEncounterProviderSource> & { uuid: string },
): VisitEncounterProviderSource {
  return {
    encounterDatetime: "2026-08-20T23:00:20.000+0000",
    encounterType: { uuid: CONSULTATION_ENCOUNTER_TYPE, name: "Consultation" },
    encounterProviders: [
      {
        encounterRole: { display: "Unknown" },
        provider: {
          uuid: "provider-a",
          display: "doctor.abikan - Clinical Doctor",
          person: { display: "Clinical Doctor" },
        },
      },
    ],
    ...overrides,
  };
}

describe("attendingDoctorName", () => {
  it("uses the person name and does not show the login id", () => {
    assert.equal(
      attendingDoctorName({
        display: "doctor.abikan - Clinical Doctor",
        person: { display: "Clinical Doctor" },
      }),
      "Clinical Doctor",
    );
  });

  it("drops a laboratory system provider with no person name", () => {
    assert.equal(
      attendingDoctorName({
        display: "LABSYSTEM - null",
        person: { display: "" },
      }),
      null,
    );
  });
});

describe("attendingDoctorFromVisitEncounters", () => {
  it("reads the provider from the latest Consultation encounter on that visit", () => {
    const name = attendingDoctorFromVisitEncounters([
      consultation({
        uuid: "older",
        encounterDatetime: "2026-08-19T03:05:51.000+0000",
        encounterProviders: [
          {
            provider: {
              display: "other.doctor - Other Doctor",
              person: { display: "Other Doctor" },
            },
          },
        ],
      }),
      consultation({
        uuid: "latest",
        encounterDatetime: "2026-08-20T23:00:20.000+0000",
      }),
    ]);
    assert.equal(name, "Clinical Doctor");
  });

  it("associates each visit with its own Consultation provider", () => {
    const visit001 = attendingDoctorFromVisitEncounters([
      consultation({
        uuid: "c1",
        encounterProviders: [
          {
            provider: {
              display: "doctor.a - Dr A",
              person: { display: "Dr A" },
            },
          },
        ],
      }),
    ]);
    const visit002 = attendingDoctorFromVisitEncounters([
      consultation({
        uuid: "c2",
        encounterProviders: [
          {
            provider: {
              display: "doctor.b - Dr B",
              person: { display: "Dr B" },
            },
          },
        ],
      }),
    ]);
    const visit003 = attendingDoctorFromVisitEncounters([]);
    assert.equal(visit001, "Dr A");
    assert.equal(visit002, "Dr B");
    assert.equal(visit003, MISSING_ATTENDING_DOCTOR);
    assert.notEqual(visit001, visit002);
  });

  it("does not inherit a provider from a laboratory encounter or another visit", () => {
    const name = attendingDoctorFromVisitEncounters([
      {
        uuid: "lab",
        encounterDatetime: "2026-08-20T23:30:00.000+0000",
        encounterType: { uuid: LAB_RESULT, name: "LAB_RESULT" },
        encounterProviders: [
          {
            provider: {
              display: "LABSYSTEM - Super User",
              person: { display: "Super User" },
            },
          },
        ],
      },
    ]);
    assert.equal(name, MISSING_ATTENDING_DOCTOR);
  });

  it("shows an honest empty state when the visit has no Consultation provider", () => {
    assert.equal(attendingDoctorFromVisitEncounters([]), MISSING_ATTENDING_DOCTOR);
    assert.equal(attendedByLabel(""), MISSING_ATTENDING_DOCTOR);
    assert.equal(attendedByLabel(undefined), MISSING_ATTENDING_DOCTOR);
  });

  it("keeps the stored daily visit number beside the attending doctor", () => {
    assert.equal(visitNumberLabel("001"), "Visit #001");
    assert.equal(visitNumberLabel(""), "—");
    assert.equal(attendedByLabel("Clinical Doctor"), "Clinical Doctor");
  });

  it("does not leak another patient's provider when visits are mapped separately", () => {
    const patientA = attendingDoctorFromVisitEncounters([
      consultation({
        uuid: "a",
        encounterProviders: [
          { provider: { person: { display: "Clinical Doctor" } } },
        ],
      }),
    ]);
    const patientB = attendingDoctorFromVisitEncounters([]);
    assert.equal(patientA, "Clinical Doctor");
    assert.equal(patientB, MISSING_ATTENDING_DOCTOR);
  });
});
