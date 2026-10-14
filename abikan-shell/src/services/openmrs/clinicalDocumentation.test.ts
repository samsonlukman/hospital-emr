import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CHIEF_COMPLAINT_CODED_CONCEPT,
  CHIEF_COMPLAINT_DURATION_UNIT_CONCEPT,
  CHIEF_COMPLAINT_DURATION_VALUE_CONCEPT,
  CHIEF_COMPLAINT_RECORD_CONCEPT,
  CHIEF_COMPLAINT_TEXT_CONCEPT,
  CONSULTATION_NOTE_CONCEPT,
  HPI_CONCEPT,
  OTHER_GENERIC_COMPLAINT_UUID,
} from "../../config/clinicalConcepts.ts";
import {
  documentationDraftsEqual,
  encounterDetailFromPayload,
  documentationForSelectedVisit,
  documentationFromObservations,
  documentationHasContent,
  documentationIsDirty,
  keepUnsavedDocumentation,
  documentationObservationsFromDraft,
  emptyChiefComplaint,
  emptyDocumentationDraft,
  formatChiefComplaintSummary,
  parseObsCodedUuid,
  parseObsNumber,
  parseObsText,
  validateDocumentationDraft,
  type ChiefComplaintDraft,
  type DocumentationDraft,
  type VisitDocumentationPayload,
} from "./clinicalDocumentation.ts";

const FEVER_UUID = "140238AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
const DAYS_UUID = "1072AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

function complaint(overrides: Partial<ChiefComplaintDraft> = {}): ChiefComplaintDraft {
  return {
    ...emptyChiefComplaint("complaint-1"),
    codedComplaintUuid: FEVER_UUID,
    codedComplaintName: "Fever",
    durationValue: "3",
    durationUnitUuid: DAYS_UUID,
    ...overrides,
  };
}

function filledDraft(overrides: Partial<DocumentationDraft> = {}): DocumentationDraft {
  return {
    ...emptyDocumentationDraft(),
    complaints: [complaint()],
    hpi: "Fever for three days.",
    consultationNote: "Advise fluids.",
    ...overrides,
  };
}

describe("parseObs helpers", () => {
  it("reads free text and ignores a bare UUID string", () => {
    assert.equal(parseObsText("Fever for three days."), "Fever for three days.");
    assert.equal(parseObsText(FEVER_UUID), "");
    assert.equal(parseObsText({ display: "Fever" }), "Fever");
    assert.equal(parseObsNumber(3), "3");
    assert.equal(parseObsNumber("3"), "3");
  });

  it("reads coded UUIDs from string or object values", () => {
    assert.equal(parseObsCodedUuid({ value: FEVER_UUID }), FEVER_UUID);
    assert.equal(parseObsCodedUuid({ value: { uuid: FEVER_UUID, display: "Fever" } }), FEVER_UUID);
    assert.equal(parseObsCodedUuid({ valueCoded: { uuid: FEVER_UUID } }), FEVER_UUID);
  });
});

describe("documentationFromObservations", () => {
  it("maps a Chief Complaint Record group plus HPI and Consultation Note", () => {
    const draft = documentationFromObservations({
      complaintGroups: [
        {
          uuid: "group-1",
          obsDatetime: "2026-08-19T04:00:00.000+0000",
          concept: { uuid: CHIEF_COMPLAINT_RECORD_CONCEPT.uuid },
          groupMembers: [
            {
              uuid: "coded-1",
              concept: { uuid: CHIEF_COMPLAINT_CODED_CONCEPT.uuid },
              value: { uuid: FEVER_UUID, display: "Fever" },
            },
            {
              uuid: "text-1",
              concept: { uuid: CHIEF_COMPLAINT_TEXT_CONCEPT.uuid },
              value: "High fever at night",
            },
            {
              uuid: "dur-1",
              concept: { uuid: CHIEF_COMPLAINT_DURATION_VALUE_CONCEPT.uuid },
              value: 3,
            },
            {
              uuid: "unit-1",
              concept: { uuid: CHIEF_COMPLAINT_DURATION_UNIT_CONCEPT.uuid },
              value: DAYS_UUID,
            },
          ],
        },
      ],
      hpi: [
        {
          uuid: "hpi-1",
          obsDatetime: "2026-08-19T04:00:00.000+0000",
          concept: { uuid: HPI_CONCEPT.uuid },
          value: "Fever for three days.",
        },
      ],
      notes: [
        {
          uuid: "note-1",
          obsDatetime: "2026-08-19T04:00:00.000+0000",
          concept: { uuid: CONSULTATION_NOTE_CONCEPT.uuid },
          value: "Advise fluids.",
        },
      ],
    });
    assert.equal(draft.complaints.length, 1);
    assert.equal(draft.complaints[0]?.codedComplaintUuid, FEVER_UUID);
    assert.equal(draft.complaints[0]?.codedComplaintName, "Fever");
    assert.equal(draft.complaints[0]?.complaintText, "High fever at night");
    assert.equal(draft.complaints[0]?.durationValue, "3");
    assert.equal(draft.complaints[0]?.durationUnitUuid, DAYS_UUID);
    assert.equal(draft.hpi, "Fever for three days.");
    assert.equal(draft.consultationNote, "Advise fluids.");
    assert.equal(draft.complaints[0]?.obs.complaintGroupUuid, "group-1");
    assert.equal(draft.obs.hpiUuid, "hpi-1");
    assert.equal(draft.obs.noteUuid, "note-1");
  });
});

describe("documentationObservationsFromDraft", () => {
  it("writes the existing Chief Complaint Record group, HPI, and Consultation Note", () => {
    const observations = documentationObservationsFromDraft(filledDraft());
    assert.equal(observations.length, 3);
    const group = observations[0];
    assert.equal(group.concept.uuid, CHIEF_COMPLAINT_RECORD_CONCEPT.uuid);
    assert.equal(group.concept.dataType, "N/A");
    assert.equal(group.groupMembers?.length, 3);
    assert.equal(group.groupMembers?.[0]?.concept.uuid, CHIEF_COMPLAINT_CODED_CONCEPT.uuid);
    assert.equal(group.groupMembers?.[0]?.value, FEVER_UUID);
    assert.equal(group.groupMembers?.[1]?.concept.uuid, CHIEF_COMPLAINT_DURATION_VALUE_CONCEPT.uuid);
    assert.equal(group.groupMembers?.[1]?.value, 3);
    assert.equal(group.groupMembers?.[2]?.concept.uuid, CHIEF_COMPLAINT_DURATION_UNIT_CONCEPT.uuid);
    assert.equal(observations[1]?.concept.uuid, HPI_CONCEPT.uuid);
    assert.equal(observations[1]?.value, "Fever for three days.");
    assert.equal(observations[2]?.concept.uuid, CONSULTATION_NOTE_CONCEPT.uuid);
  });

  it("keeps existing observation UUIDs when updating the same Consultation encounter", () => {
    const baseline = filledDraft({
      complaints: [
        complaint({
          obs: {
            complaintGroupUuid: "group-1",
            codedUuid: "coded-1",
            durationUuid: "dur-1",
            durationUnitUuid: "unit-1",
          },
        }),
      ],
      obs: {
        hpiUuid: "hpi-1",
        noteUuid: "note-1",
      },
    });
    const draft = {
      ...baseline,
      hpi: "Fever for three days, worse at night.",
      complaints: baseline.complaints.map((row) => ({ ...row, obs: { ...row.obs } })),
      obs: { ...baseline.obs },
    };
    const observations = documentationObservationsFromDraft(draft, baseline);
    assert.equal(observations.length, 1);
    assert.equal(observations[0]?.uuid, "hpi-1");
    assert.equal(observations[0]?.concept.uuid, HPI_CONCEPT.uuid);
  });

  it("does not emit observations when the draft matches what OpenMRS already stored", () => {
    const baseline = filledDraft();
    assert.deepEqual(documentationObservationsFromDraft(baseline, baseline), []);
  });

  it("does not invent a coded complaint when only free text is entered", () => {
    const observations = documentationObservationsFromDraft(
      filledDraft({
        complaints: [
          complaint({
            codedComplaintUuid: "",
            codedComplaintName: "",
            complaintText: "Pain behind the left ear",
            durationValue: "",
            durationUnitUuid: "",
          }),
        ],
        hpi: "",
        consultationNote: "",
      }),
    );
    assert.equal(observations.length, 1);
    assert.equal(observations[0]?.groupMembers?.length, 1);
    assert.equal(observations[0]?.groupMembers?.[0]?.concept.uuid, CHIEF_COMPLAINT_TEXT_CONCEPT.uuid);
  });
});

describe("documentation draft state", () => {
  it("treats whitespace-only notes as empty", () => {
    const draft = filledDraft({
      hpi: "  ",
      consultationNote: "",
      complaints: [],
    });
    assert.equal(documentationHasContent(draft), false);
    assert.equal(documentationIsDirty(draft, emptyDocumentationDraft()), false);
  });

  it("requires free text when Other generic is selected", () => {
    assert.equal(
      validateDocumentationDraft(
        filledDraft({
          complaints: [
            complaint({
              codedComplaintUuid: OTHER_GENERIC_COMPLAINT_UUID,
              codedComplaintName: "Other generic",
              complaintText: "",
            }),
          ],
        }),
      ),
      "Enter the chief complaint.",
    );
    assert.equal(
      validateDocumentationDraft(
        filledDraft({
          complaints: [
            complaint({
              codedComplaintUuid: OTHER_GENERIC_COMPLAINT_UUID,
              codedComplaintName: "Other generic",
              complaintText: "Pain behind the left ear",
            }),
          ],
        }),
      ),
      null,
    );
  });

  it("requires a duration unit when a duration number is entered", () => {
    assert.equal(
      validateDocumentationDraft(
        filledDraft({
          complaints: [complaint({ durationUnitUuid: "" })],
        }),
      ),
      "Choose the duration unit for each chief complaint.",
    );
  });

  it("saves each chief complaint with its own duration", () => {
    const cough = "159394AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    const hours = "1822AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    const observations = documentationObservationsFromDraft(
      filledDraft({
        complaints: [
          complaint(),
          complaint({
            key: "complaint-2",
            codedComplaintUuid: cough,
            codedComplaintName: "Cough",
            durationValue: "6",
            durationUnitUuid: hours,
          }),
        ],
        hpi: "",
        consultationNote: "",
      }),
    );
    assert.equal(observations.length, 2);
    assert.equal(observations[0]?.groupMembers?.[1]?.value, 3);
    assert.equal(observations[1]?.groupMembers?.[0]?.value, cough);
    assert.equal(observations[1]?.groupMembers?.[1]?.value, 6);
    assert.equal(observations[1]?.groupMembers?.[2]?.value, hours);
  });

  it("keeps typed notes when a prescription or order is saved", () => {
    const recorded = emptyDocumentationDraft();
    const typed = filledDraft({ complaints: [], hpi: "Fever for three days." });
    assert.equal(keepUnsavedDocumentation(true, typed, recorded), true);
    assert.equal(keepUnsavedDocumentation(false, typed, recorded), false);
    assert.equal(keepUnsavedDocumentation(true, recorded, recorded), false);
  });

  it("summarises complaint without exposing concept names", () => {
    assert.equal(formatChiefComplaintSummary(filledDraft()), "Fever · 3 days");
    assert.equal(documentationDraftsEqual(filledDraft(), filledDraft({ hpi: "Fever for three days. " })), true);
  });
});

const leftoverVisitUuid = "6478a94e-1657-4abe-9271-7cf92b821576";
const todayVisitUuid = "2857db49-c8fa-46d0-be38-2213f4cc54bc";
const patientA = "f242364e-b70f-4fec-b29e-8ad4fbe147b5";
const patientB = "71f9788f-67f7-441c-b520-11979cbc37ec";

const leftoverVisit: VisitDocumentationPayload = {
  uuid: leftoverVisitUuid,
  patient: { uuid: patientA },
  encounters: [
    {
      uuid: "9a88a85d-encounter",
      encounterDatetime: "2026-08-19T03:05:51.000+0000",
      obs: [
        {
          uuid: "cb5a7803-group",
          obsDatetime: "2026-08-19T03:05:51.000+0000",
          concept: { uuid: CHIEF_COMPLAINT_RECORD_CONCEPT.uuid },
          groupMembers: [
            {
              uuid: "e4bc4a6b-coded",
              concept: { uuid: CHIEF_COMPLAINT_CODED_CONCEPT.uuid },
              value: { uuid: FEVER_UUID, display: "Fever" },
            },
            {
              uuid: "9d15ede8-text",
              concept: { uuid: CHIEF_COMPLAINT_TEXT_CONCEPT.uuid },
              value: "High fever at night",
            },
          ],
        },
        {
          uuid: "3022d328-hpi",
          obsDatetime: "2026-08-19T03:05:51.000+0000",
          concept: { uuid: HPI_CONCEPT.uuid },
          value: "Hospital EMR clinical pass 3: fever started three days ago, worse at night.",
        },
        {
          uuid: "0a0d60c6-note",
          obsDatetime: "2026-08-19T03:05:51.000+0000",
          concept: { uuid: CONSULTATION_NOTE_CONCEPT.uuid },
          value: "Hospital EMR clinical pass 3 consultation note. Advise fluids and review.",
        },
      ],
    },
  ],
};

const emptyTodayVisit: VisitDocumentationPayload = {
  uuid: todayVisitUuid,
  patient: { uuid: patientA },
  encounters: [],
};

describe("visit-scoped consultation documentation", () => {
  it("reads complaint, HPI, and notes from the selected visit only", () => {
    const leftover = documentationForSelectedVisit(leftoverVisit, leftoverVisitUuid, patientA);
    assert.equal(leftover.complaints[0]?.codedComplaintName, "Fever");
    assert.equal(leftover.hpi.includes("fever started three days ago"), true);
    assert.equal(leftover.consultationNote.includes("Advise fluids"), true);
    assert.equal(leftover.obs.hpiUuid, "3022d328-hpi");
  });

  it("does not fall back to the latest patient observation for another visit", () => {
    const today = documentationForSelectedVisit(leftoverVisit, todayVisitUuid, patientA);
    assert.equal(today.complaints.length, 0);
    assert.equal(today.hpi, "");
    assert.equal(today.consultationNote, "");
    assert.deepEqual(today.obs, {});
    const emptyToday = documentationForSelectedVisit(emptyTodayVisit, todayVisitUuid, patientA);
    assert.equal(documentationHasContent(emptyToday), false);
  });

  it("keeps multiple visits for the same patient independent", () => {
    const visit002: VisitDocumentationPayload = {
      uuid: "a70cbb56-visit-002",
      patient: { uuid: patientA },
      encounters: [
        {
          uuid: "enc-002",
          obs: [
            {
              uuid: "hpi-002",
              obsDatetime: "2026-08-23T03:16:00.000+0000",
              concept: { uuid: HPI_CONCEPT.uuid },
              value: "Visit two history only.",
            },
          ],
        },
      ],
    };
    const first = documentationForSelectedVisit(leftoverVisit, leftoverVisitUuid, patientA);
    const second = documentationForSelectedVisit(visit002, "a70cbb56-visit-002", patientA);
    const third = documentationForSelectedVisit(
      { uuid: "a3036eb0-visit-003", patient: { uuid: patientA }, encounters: [] },
      "a3036eb0-visit-003",
      patientA,
    );
    assert.equal(first.hpi.includes("fever started"), true);
    assert.equal(second.hpi, "Visit two history only.");
    assert.equal(third.hpi, "");
    assert.notEqual(first.obs.hpiUuid, second.obs.hpiUuid);
  });

  it("does not leak another patient's documentation", () => {
    const leaked = documentationForSelectedVisit(leftoverVisit, leftoverVisitUuid, patientB);
    assert.equal(documentationHasContent(leaked), false);
    assert.deepEqual(leaked.obs, {});
  });

  it("returns an empty draft when no visit is selected", () => {
    const draft = documentationForSelectedVisit(leftoverVisit, null, patientA);
    assert.equal(documentationHasContent(draft), false);
  });

  it("uses the latest observation on that visit when the visit has more than one", () => {
    const visit = {
      uuid: leftoverVisitUuid,
      patient: { uuid: patientA },
      encounters: [
        {
          uuid: "older-enc",
          obs: [
            {
              uuid: "older-hpi",
              obsDatetime: "2026-08-19T03:00:00.000+0000",
              concept: { uuid: HPI_CONCEPT.uuid },
              value: "Older note on the same visit.",
            },
          ],
        },
        {
          uuid: "newer-enc",
          obs: [
            {
              uuid: "newer-hpi",
              obsDatetime: "2026-08-19T05:00:00.000+0000",
              concept: { uuid: HPI_CONCEPT.uuid },
              value: "Later note on the same visit.",
            },
          ],
        },
      ],
    };
    const draft = documentationForSelectedVisit(visit, leftoverVisitUuid, patientA);
    assert.equal(draft.hpi, "Later note on the same visit.");
    assert.equal(draft.obs.hpiUuid, "newer-hpi");
  });

  it("creates new observations on an empty visit instead of rewriting another visit's UUIDs", () => {
    const baseline = documentationForSelectedVisit(emptyTodayVisit, todayVisitUuid, patientA);
    const draft = filledDraft({
      ...baseline,
      hpi: "New history for today's visit.",
      consultationNote: "New note for today's visit.",
      obs: baseline.obs,
    });
    const observations = documentationObservationsFromDraft(draft, baseline);
    const hpi = observations.find((row) => row.concept.uuid === HPI_CONCEPT.uuid);
    const note = observations.find((row) => row.concept.uuid === CONSULTATION_NOTE_CONCEPT.uuid);
    assert.equal(hpi?.uuid, undefined);
    assert.equal(note?.uuid, undefined);
    assert.equal(hpi?.value, "New history for today's visit.");
    assert.equal(note?.value, "New note for today's visit.");
  });

  it("keeps observation UUIDs only when updating the selected visit's own encounter", () => {
    const baseline = documentationForSelectedVisit(leftoverVisit, leftoverVisitUuid, patientA);
    const draft = {
      ...baseline,
      hpi: `${baseline.hpi} Extra sentence.`,
      obs: baseline.obs,
    };
    const observations = documentationObservationsFromDraft(draft, baseline);
    assert.equal(observations.length, 1);
    assert.equal(observations[0]?.uuid, "3022d328-hpi");
  });
});

describe("encounterDetailFromPayload", () => {
  it("reads complaint, notes, vitals, and orders for one encounter", () => {
    const detail = encounterDetailFromPayload(
      {
        encounterProviders: [{ provider: { display: "abikan - Ada Okonkwo" } }],
        obs: [
          {
            concept: { uuid: CHIEF_COMPLAINT_RECORD_CONCEPT.uuid },
            groupMembers: [
              {
                concept: { uuid: CHIEF_COMPLAINT_CODED_CONCEPT.uuid },
                value: { display: "Fever", uuid: FEVER_UUID },
              },
              {
                concept: { uuid: CHIEF_COMPLAINT_TEXT_CONCEPT.uuid },
                value: "Started after travel",
              },
            ],
          },
          {
            concept: { uuid: CONSULTATION_NOTE_CONCEPT.uuid },
            value: "Looks dehydrated.",
          },
          {
            concept: { uuid: "5088AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" },
            value: 38.2,
          },
        ],
        orders: [
          {
            concept: { display: "Malaria parasite" },
            commentToFulfiller: "Fever",
          },
        ],
      },
      ["Malaria"],
    );
    assert.equal(detail.clinician, "Ada Okonkwo");
    assert.match(detail.complaint, /Fever/);
    assert.match(detail.complaint, /Started after travel/);
    assert.equal(detail.notes, "Looks dehydrated.");
    assert.deepEqual(detail.vitals, ["Temperature 38.2 °C"]);
    assert.deepEqual(detail.diagnoses, ["Malaria"]);
    assert.deepEqual(detail.orders, ["Malaria parasite · Fever"]);
  });

  it("shows an injection as an injection when the saved unit says tablet", () => {
    const detail = encounterDetailFromPayload({
      orders: [
        {
          drug: { display: "Paracetamol injection", dosageForm: { display: "Injection" } },
          dose: 1,
          doseUnits: { display: "Tablet" },
          frequency: { display: "Once a day" },
        },
      ],
    });
    assert.equal(detail.orders[0], "Paracetamol injection · 1 Injection · Once a day");
  });
});
