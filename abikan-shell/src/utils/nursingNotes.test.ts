import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import type { NursingNote } from "../types/inpatient.ts";
import {
  canCreateNursingNote,
  canSubmitNursingNote,
  notesForAdmission,
  nursingNoteRequestBody,
} from "./nursingNotes.ts";

function row(uuid: string, admissionEncounterUuid: string): NursingNote {
  return {
    uuid,
    patientUuid: "patient",
    admissionEncounterUuid,
    visitUuid: "visit",
    authorUserUuid: "nurse",
    authorPersonUuid: "nurse-person",
    authorName: "Nurse Hospital EMR",
    recordedAt: "2026-08-26T19:30:45.000+0000",
    content: "Patient resting comfortably.",
    requestId: `request-${uuid}`,
  };
}

describe("inpatient nursing notes", () => {
  it("shows nurses only notes from the active admission", () => {
    assert.deepEqual(
      notesForAdmission([row("old", "old-admission"), row("current", "active")], "active").map(
        (note) => note.uuid,
      ),
      ["current"],
    );
  });

  it("shows the create action only for an active admission", () => {
    assert.equal(canCreateNursingNote(true, "active"), true);
    assert.equal(canCreateNursingNote(true, ""), false);
    assert.equal(canCreateNursingNote(false, "active"), false);
  });

  it("prevents blank and duplicate in-flight submission", () => {
    assert.equal(canSubmitNursingNote("Patient stable.", false), true);
    assert.equal(canSubmitNursingNote("   ", false), false);
    assert.equal(canSubmitNursingNote("Patient stable.", true), false);
  });

  it("sends no client-selected author, time, patient or admission", () => {
    assert.deepEqual(nursingNoteRequestBody("Patient stable.", "request-1"), {
      note: "Patient stable.",
      requestId: "request-1",
    });
  });

  it("keeps the doctor view read-only and renders the required empty state", () => {
    const componentPath = fileURLToPath(
      new URL("../components/NursingNotesPanel.tsx", import.meta.url),
    );
    const doctorPath = fileURLToPath(
      new URL("../workspaces/Doctor/ConsultationWorkspace.tsx", import.meta.url),
    );
    const component = readFileSync(componentPath, "utf8");
    const doctor = readFileSync(doctorPath, "utf8");
    assert.match(component, /No nursing notes recorded for this admission\./);
    assert.match(component, /Nurse: \{row\.authorName\}/);
    assert.match(component, /\{noteDate\(row\.recordedAt\)\} · \{noteTime\(row\.recordedAt\)\}/);
    assert.match(doctor, /canCreate=\{false\}/);
  });

  it("includes a mobile-safe note layout", () => {
    const cssPath = fileURLToPath(
      new URL("../components/NursingNotesPanel.css", import.meta.url),
    );
    const css = readFileSync(cssPath, "utf8");
    assert.match(css, /@media \(max-width: 480px\)/);
    assert.match(css, /overflow-wrap: anywhere/);
    assert.match(css, /flex-direction: column/);
  });
});
