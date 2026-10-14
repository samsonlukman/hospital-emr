import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import type { InpatientStay, MarPayload } from "../../types/inpatient.ts";
import {
  marAttention,
  nursingTasksFromState,
  stayIsOccupied,
  stayNeedsBed,
} from "./nursingTasks.ts";

const occupied: InpatientStay = {
  status: "ok",
  patient: { uuid: "p1", name: "Test", mrn: "ABC1", sex: "F", age: "30" },
  assignment: {
    areaName: "General Ward",
    areaUuid: "area-1",
    bedNumber: "1",
    status: "OCCUPIED",
  },
};

const awaiting: InpatientStay = {
  status: "ok",
  patient: { uuid: "p1", name: "Test", mrn: "ABC1", sex: "F", age: "30" },
  assignment: null,
  awaiting: true,
};

const marDue: MarPayload = {
  status: "ok",
  patientUuid: "p1",
  visitUuid: "v1",
  admissionEncounterUuid: "adm-1",
  activeAdmission: true,
  administrationWindow: { earlyMinutes: 30, lateMinutes: 60 },
  orders: [
    {
      orderUuid: "ord-1",
      orderNumber: "ORD-1",
      medication: "Amoxicillin",
      drugUuid: "drug-1",
      dose: 500,
      doseUnits: "mg",
      route: "Oral",
      frequency: "Twice a day",
      asNeeded: false,
      instructions: "Take after food for five days.",
      slots: [
        {
          uuid: "slot-1",
          scheduleUuid: "sch-1",
          status: "SCHEDULED",
          scheduledTime: Date.now(),
          timing: {
            status: "eligible",
            canAdministerNormally: true,
            minutesFromScheduled: 0,
          },
          administration: null,
        },
      ],
    },
  ],
};

describe("nursing tasks from ward state", () => {
  it("asks the nurse to assign a bed when admission is requested", () => {
    assert.equal(stayNeedsBed(awaiting), true);
    assert.equal(stayIsOccupied(awaiting), false);
    const tasks = nursingTasksFromState({
      stay: awaiting,
      admissionEncounterUuid: "",
      vitals: [],
      notes: [],
      mar: null,
    });
    assert.deepEqual(
      tasks.map((row) => row.id),
      ["assign-bed"],
    );
  });

  it("surfaces vitals, MAR, and notes from the live admission only", () => {
    const tasks = nursingTasksFromState({
      stay: occupied,
      admissionEncounterUuid: "adm-1",
      vitals: [],
      notes: [],
      mar: marDue,
    });
    assert.deepEqual(
      tasks.map((row) => row.id),
      ["record-vitals", "administer-mar", "write-note"],
    );
    assert.equal(marAttention(marDue).eligible, 1);
    assert.match(tasks[0].action, /Vitals/);
    assert.match(tasks[1].action, /Medication/);
    assert.match(tasks[2].action, /Notes/);
  });

  it("does not invent tasks when the admission is already documented", () => {
    const tasks = nursingTasksFromState({
      stay: occupied,
      admissionEncounterUuid: "adm-1",
      vitals: [
        {
          requestId: "v1",
          recordedAt: "2026-09-01T10:00:00.000+0000",
          recordedBy: "Nurse",
          authorUserUuid: "n1",
          authorPersonUuid: "n1p",
          encounterUuid: "adm-1",
          visitUuid: "v1",
          observations: [],
        },
      ],
      notes: [
        {
          uuid: "note-1",
          patientUuid: "p1",
          admissionEncounterUuid: "adm-1",
          visitUuid: "v1",
          authorUserUuid: "n1",
          authorPersonUuid: "n1p",
          authorName: "Nurse",
          recordedAt: "2026-09-01T10:05:00.000+0000",
          content: "Settled.",
          requestId: "r1",
        },
      ],
      mar: { ...marDue, orders: [] },
    });
    assert.deepEqual(tasks, []);
  });

  it("tells the nurse to contact Hospital Admin when the accommodation tariff is missing", () => {
    const source = readFileSync(new URL("./NursingPatientWorkspace.tsx", import.meta.url), "utf8");
    assert.match(
      source,
      /Accommodation price is not configured for this bed\/ward\. Please contact Hospital Admin to configure the accommodation tariff\./,
    );
    assert.doesNotMatch(source, /Daily room price is not set yet/);
    const assign = source.split('dialog === "assign"')[1]?.split('dialog === "transfer"')[0] || "";
    assert.match(assign, /Assign Bed/);
    assert.doesNotMatch(assign, /listPrice|roomPrice|dailyPrice|amountInput|₦/);
  });

  it("does not expose unimplemented Care Plan or Coming Soon on the nursing chart", () => {
    const source = readFileSync(new URL("./NursingPatientWorkspace.tsx", import.meta.url), "utf8");
    assert.doesNotMatch(source, /ComingSoonMark|Coming soon|COMING SOON/i);
    assert.doesNotMatch(source, /Care plan|Intake & output|will consume real work later/i);
    assert.match(source, /NursingTasksPanel/);
    assert.match(source, /AllergyPanel/);
  });

  it("does not stay loading when there is no admission stay", () => {
    const panel = readFileSync(new URL("../../components/NursingTasksPanel.tsx", import.meta.url), "utf8");
    assert.match(panel, /if \(!stay\) \{\n      setTasks\(\[\]\);\n      setLoading\(false\);/);
  });

  it("keeps a professional empty state that explains completed work", () => {
    const panel = readFileSync(new URL("../../components/NursingTasksPanel.tsx", import.meta.url), "utf8");
    assert.match(panel, /First vitals, the first nursing note, and any due scheduled doses/);
    assert.doesNotMatch(panel, /Coming soon|placeholder|not configured/i);
    const mar = readFileSync(new URL("../../components/MedicationAdministrationPanel.tsx", import.meta.url), "utf8");
    assert.match(mar, /after the doctor prescribes an inpatient medicine/);
    assert.match(mar, /Nursing cannot write a new prescription/);
  });
});
