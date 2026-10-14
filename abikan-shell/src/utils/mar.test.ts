import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  canSubmitMar,
  marOutcomeLabel,
  marSlotStatusLabel,
} from "./mar.ts";

describe("inpatient medication administration", () => {
  it("uses installed slot statuses with clear staff labels", () => {
    assert.equal(marSlotStatusLabel("SCHEDULED"), "Scheduled");
    assert.equal(marSlotStatusLabel("COMPLETED"), "Completed");
    assert.equal(marSlotStatusLabel("NOT_DONE"), "Not done");
    assert.equal(marSlotStatusLabel("STOPPED"), "Stopped");
    assert.equal(marSlotStatusLabel("MISSED"), "Missed");
  });

  it("preserves the supported administration outcomes", () => {
    assert.equal(marOutcomeLabel("given"), "Given");
    assert.equal(marOutcomeLabel("not-done"), "Not done");
    assert.equal(marOutcomeLabel("refused"), "Refused");
    assert.equal(marOutcomeLabel("held"), "Held");
  });

  it("requires a reason for every non-given outcome", () => {
    assert.equal(canSubmitMar("given", "", false), true);
    assert.equal(canSubmitMar("not-done", "", false), false);
    assert.equal(canSubmitMar("refused", "Patient refused", false), true);
    assert.equal(canSubmitMar("held", "Clinical instruction", false), true);
    assert.equal(canSubmitMar("given", "", true), false);
    assert.equal(canSubmitMar("given", "", false, true), false);
    assert.equal(
      canSubmitMar("given", "Timing changed by prescriber", false, true),
      true,
    );
  });

  it("shows administration only for scheduled slots and keeps Doctor read-only", () => {
    const panelPath = fileURLToPath(
      new URL("../components/MedicationAdministrationPanel.tsx", import.meta.url),
    );
    const doctorPath = fileURLToPath(
      new URL("../workspaces/Doctor/ConsultationWorkspace.tsx", import.meta.url),
    );
    const panel = readFileSync(panelPath, "utf8");
    const doctor = readFileSync(doctorPath, "utf8");
    assert.match(panel, /slot\.status === "SCHEDULED"/);
    assert.match(panel, /slot\.timing\.canAdministerNormally/);
    assert.match(panel, /Administer outside scheduled window/);
    assert.match(panel, /payload\?\.activeAdmission/);
    assert.doesNotMatch(panel, /datetime-local/);
    assert.doesNotMatch(panel, /Document earlier administration/);
    assert.match(panel, /<dt>Scheduled<\/dt>/);
    assert.match(panel, /<dt>Actual<\/dt>/);
    assert.match(panel, /<dt>Nurse<\/dt>/);
    assert.match(doctor, /<MedicationAdministrationPanel[\s\S]*canRecord=\{false\}/);
  });

  it("uses mobile cards without a page-wide medication table", () => {
    const cssPath = fileURLToPath(
      new URL("../components/MedicationAdministrationPanel.css", import.meta.url),
    );
    const panelPath = fileURLToPath(
      new URL("../components/MedicationAdministrationPanel.tsx", import.meta.url),
    );
    const css = readFileSync(cssPath, "utf8");
    const panel = readFileSync(panelPath, "utf8");
    assert.match(css, /@media \(max-width: 480px\)/);
    assert.match(css, /grid-template-columns: 1fr/);
    assert.match(css, /overflow-wrap: anywhere/);
    assert.doesNotMatch(panel, /<table/);
  });
});
