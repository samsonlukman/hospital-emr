import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import {
  allergyStateFromPayload,
  emptyAllergyDraft,
  validateAllergyDraft,
} from "./allergies.ts";

describe("allergy draft validation", () => {
  it("requires a substance and a recognised type", () => {
    assert.equal(validateAllergyDraft(emptyAllergyDraft()), "Enter the substance the patient reacts to.");
    assert.equal(
      validateAllergyDraft({ ...emptyAllergyDraft(), allergenType: "ANIMAL", allergenName: "Cat" }),
      "Choose whether this is a medicine, food, environment, or other allergy.",
    );
    assert.equal(
      validateAllergyDraft({ ...emptyAllergyDraft(), allergenName: "Penicillin" }),
      "",
    );
  });

  it("maps OpenMRS allergy rows without inventing storage", () => {
    const recorded = allergyStateFromPayload({
      canWrite: true,
      allergies: [
        {
          uuid: "a1",
          allergen: "Penicillin",
          allergenType: "DRUG",
          allergenTypeLabel: "Medicine",
          severity: "Severe",
          reactions: ["Rash"],
          comment: "",
          display: "Penicillin (Severe — Rash)",
        },
      ],
    });
    assert.equal(recorded.status, "recorded");
    if (recorded.status === "recorded") {
      assert.deepEqual(recorded.items, ["Penicillin (Severe — Rash)"]);
      assert.equal(recorded.canWrite, true);
    }
    const empty = allergyStateFromPayload({ canWrite: false, allergies: [] });
    assert.equal(empty.status, "none-recorded");
    if (empty.status === "none-recorded") {
      assert.equal(empty.canWrite, false);
    }
  });
});

describe("allergy production surfaces", () => {
  it("lets doctor and nurse record allergies and does not add a local table", () => {
    const nursing = readFileSync(new URL("../workspaces/Nursing/NursingPatientWorkspace.tsx", import.meta.url), "utf8");
    const doctor = readFileSync(new URL("../workspaces/Doctor/ConsultationWorkspace.tsx", import.meta.url), "utf8");
    const server = readFileSync(new URL("../../server/patient-account/allergies.py", import.meta.url), "utf8");
    assert.match(nursing, /AllergyPanel/);
    assert.match(doctor, /AllergyPanel/);
    assert.match(server, /openmrs\/ws\/rest\/v1\/patient/);
    assert.match(server, /OTHER_NON_CODED_CONCEPT/);
    assert.match(server, /codedAllergen/);
    assert.doesNotMatch(server, /CREATE TABLE|sqlite|allergies_abikan/i);
    assert.doesNotMatch(server, /Cannot create allergy/);
    const provision = readFileSync(new URL("../../scripts/provision-dev-users.py", import.meta.url), "utf8");
    assert.match(provision, /ALLERGY_WRITE_PRIVILEGES/);
    assert.match(provision, /"Get Allergies"/);
    assert.match(provision, /"Add Allergies"/);
    assert.match(provision, /"Edit Allergies"/);
    assert.match(provision, /"Remove Allergies"/);
    assert.match(provision, /"name": "Abikan:Doctor"[\s\S]*ALLERGY_WRITE_PRIVILEGES/);
    assert.match(provision, /"name": "Abikan:Nursing"[\s\S]*ALLERGY_WRITE_PRIVILEGES/);
    assert.doesNotMatch(
      provision,
      /"name": "Abikan:Pharmacy"[\s\S]*ALLERGY_WRITE_PRIVILEGES[\s\S]*"name": "Abikan:Pharmacy Inventory"/,
    );
  });

  it("does not present an unavailable allergy record as an empty list", () => {
    const panel = readFileSync(new URL("../components/AllergyPanel.tsx", import.meta.url), "utf8");
    assert.match(panel, /allergy.status === "unavailable"/);
    assert.match(panel, /Allergy record unavailable/);
  });
});
