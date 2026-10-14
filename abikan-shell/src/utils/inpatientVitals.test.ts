import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import type { InpatientVitalsPayload } from "../types/inpatient.ts";
import {
  canRecordInpatientVitals,
  historyFromVitalsPayload,
  vitalsRequestBody,
} from "./inpatientVitals.ts";

const payload: InpatientVitalsPayload = {
  status: "ok",
  patientUuid: "patient-1",
  visitUuid: "visit-1",
  admissionEncounterUuid: "admission-1",
  activeAdmission: true,
  readings: [
    {
      requestId: "later",
      recordedAt: "2026-08-27T12:00:00.000+0000",
      recordedBy: "Nursing Staff",
      authorUserUuid: "nurse-user",
      authorPersonUuid: "nurse-person",
      encounterUuid: "admission-1",
      visitUuid: "visit-1",
      observations: [
        {
          uuid: "obs-3",
          key: "temperature",
          label: "Temperature",
          value: "37.5",
          unit: "°C",
          conceptUuid: "5088AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        },
      ],
    },
    {
      requestId: "earlier",
      recordedAt: "2026-08-27T08:00:00.000+0000",
      recordedBy: "Nursing Staff",
      authorUserUuid: "nurse-user",
      authorPersonUuid: "nurse-person",
      encounterUuid: "admission-1",
      visitUuid: "visit-1",
      observations: [
        {
          uuid: "obs-1",
          key: "temperature",
          label: "Temperature",
          value: "37.2",
          unit: "°C",
          conceptUuid: "5088AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        },
        {
          uuid: "obs-2",
          key: "pulse",
          label: "Pulse",
          value: "82",
          unit: "bpm",
          conceptUuid: "5087AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        },
      ],
    },
  ],
};

describe("inpatient nursing vitals", () => {
  it("records when nursing is allowed and the chart has loaded", () => {
    assert.equal(canRecordInpatientVitals(true, true), true);
    assert.equal(canRecordInpatientVitals(true, false), false);
    assert.equal(canRecordInpatientVitals(false, true), false);
    assert.deepEqual(vitalsRequestBody({ temperature: 37.2, pulse: 82 }, "request-1"), {
      requestId: "request-1",
      temperature: 37.2,
      pulse: 82,
    });
  });

  it("keeps multiple readings and uses the latest value per observation", () => {
    const history = historyFromVitalsPayload(payload);
    assert.equal(history.temperature?.[0]?.value, "37.5");
    assert.equal(history.temperature?.[1]?.value, "37.2");
    assert.equal(history.temperature?.[0]?.recordedBy, "Nursing Staff");
    assert.equal(history.pulse?.[0]?.value, "82");
  });

  it("keeps Doctor read-only and Nursing able to record", () => {
    const doctorPath = fileURLToPath(
      new URL("../workspaces/Doctor/ConsultationWorkspace.tsx", import.meta.url),
    );
    const nursingPath = fileURLToPath(
      new URL("../workspaces/Nursing/NursingPatientWorkspace.tsx", import.meta.url),
    );
    const panelPath = fileURLToPath(
      new URL("../components/InpatientVitalsPanel.tsx", import.meta.url),
    );
    const cardPath = fileURLToPath(
      new URL("../components/VitalSignsCard.tsx", import.meta.url),
    );
    const doctor = readFileSync(doctorPath, "utf8");
    const nursing = readFileSync(nursingPath, "utf8");
    const panel = readFileSync(panelPath, "utf8");
    const card = readFileSync(cardPath, "utf8");
    assert.match(doctor, /<InpatientVitalsPanel[\s\S]*canRecord=\{false\}/);
    assert.match(nursing, /<InpatientVitalsPanel patientUuid=\{patientUuid\} canRecord \/>/);
    assert.doesNotMatch(nursing, /Not enabled in this phase/);
    assert.doesNotMatch(panel, /datetime-local/);
    assert.doesNotMatch(card, /datetime-local/);
    assert.match(panel, /Time is recorded automatically/);
    assert.match(panel, /hideWhenNotAdmitted && !loading && !payload\?\.activeAdmission/);
  });

  it("fits a 390px ward layout", () => {
    const cssPath = fileURLToPath(
      new URL("../components/VitalSignsCard.css", import.meta.url),
    );
    const css = readFileSync(cssPath, "utf8");
    assert.match(css, /@media \(max-width: 480px\)/);
    assert.match(css, /overflow-wrap: anywhere/);
    assert.match(css, /width: 100%/);
  });
});
