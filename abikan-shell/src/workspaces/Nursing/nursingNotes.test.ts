import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { nursingNoteRequestBody } from "../../services/inpatient.ts";
import type { NursingNote } from "../../types/inpatient.ts";
import {
  canCreateNursingNote,
  canSubmitNursingNote,
  notesForAdmission,
} from "./nursingNotes.ts";

const first: NursingNote = {
  uuid: "note-1",
  patientUuid: "patient-1",
  admissionEncounterUuid: "admission-1",
  visitUuid: "visit-1",
  authorUserUuid: "nurse-1",
  authorName: "Nurse One",
  recordedAt: "2026-08-26T19:30:45.000+0000",
  content: "Patient resting comfortably.",
  requestId: "request-1",
};

describe("inpatient nursing notes", () => {
  it("shows the nurse action only for an active admission", () => {
    assert.equal(canCreateNursingNote(true, "admission-1"), true);
    assert.equal(canCreateNursingNote(true, ""), false);
    assert.equal(canCreateNursingNote(false, "admission-1"), false);
  });

  it("keeps notes associated with the selected admission", () => {
    const other = { ...first, uuid: "note-2", admissionEncounterUuid: "admission-2" };
    assert.deepEqual(notesForAdmission([first, other], "admission-1"), [first]);
  });

  it("disables blank and duplicate in-flight submissions", () => {
    assert.equal(canSubmitNursingNote("", false), false);
    assert.equal(canSubmitNursingNote("  ", false), false);
    assert.equal(canSubmitNursingNote("Observation", true), false);
    assert.equal(canSubmitNursingNote("Observation", false), true);
  });

  it("sends only note content and request identity", () => {
    assert.deepEqual(nursingNoteRequestBody("Observation", "request-1"), {
      note: "Observation",
      requestId: "request-1",
    });
  });

  it("keeps the doctor view read-only", () => {
    const source = readFileSync(
      new URL("../Doctor/ConsultationWorkspace.tsx", import.meta.url),
      "utf8",
    );
    assert.match(source, /<NursingNotesPanel[\s\S]*canCreate=\{false\}/);
  });

  it("renders exact identity, time, content, empty, and failure states", () => {
    const source = readFileSync(
      new URL("../../components/NursingNotesPanel.tsx", import.meta.url),
      "utf8",
    );
    assert.match(source, /\{noteDate\(row\.recordedAt\)\} · \{noteTime\(row\.recordedAt\)\}/);
    assert.match(source, /Nurse: \{row\.authorName\}/);
    assert.match(source, /\{row\.content\}/);
    assert.match(source, /No nursing notes recorded for this admission\./);
    assert.match(source, /Nursing notes unavailable/);
  });

  it("has a narrow-screen layout for bedside use", () => {
    const css = readFileSync(
      new URL("../../components/NursingNotesPanel.css", import.meta.url),
      "utf8",
    );
    assert.match(css, /@media \(max-width: 480px\)/);
    assert.match(css, /overflow-wrap: anywhere/);
  });
});
