import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  boardPhase,
  isEmptyCopy,
  isErrorCopy,
  isLoadingCopy,
  pendingActionLabel,
} from "./dataLoadState.ts";

const here = dirname(fileURLToPath(import.meta.url));

function source(relative: string): string {
  return readFileSync(join(here, relative), "utf8");
}

describe("board loading phases", () => {
  it("keeps loading distinct from empty and error", () => {
    assert.equal(boardPhase({ loading: true, count: 0 }), "loading");
    assert.equal(boardPhase({ loading: true, error: "Unable to load", count: 0 }), "loading");
    assert.equal(boardPhase({ loading: false, count: 0 }), "empty");
    assert.equal(boardPhase({ loading: false, error: "Unable to load today's patients.", count: 0 }), "error");
    assert.equal(boardPhase({ loading: false, count: 3 }), "ready");
  });

  it("does not treat loading copy as an empty state", () => {
    assert.equal(isLoadingCopy("Loading today's patients…"), true);
    assert.equal(isLoadingCopy("Searching…"), true);
    assert.equal(isEmptyCopy("No patients found today."), true);
    assert.equal(isErrorCopy("Unable to load today's patients."), true);
    assert.equal(isEmptyCopy("Loading today's patients…"), false);
    assert.equal(isLoadingCopy("No patients found today."), false);
  });
});

describe("mutation pending labels", () => {
  it("enters a clear pending label for important actions", () => {
    assert.equal(pendingActionLabel("Save"), "Saving…");
    assert.equal(pendingActionLabel("Admit Patient"), "Admitting…");
    assert.equal(pendingActionLabel("Assign Bed"), "Assigning…");
    assert.equal(pendingActionLabel("Create Visit"), "Creating visit…");
    assert.equal(pendingActionLabel("Close Visit"), "Closing visit…");
    assert.equal(pendingActionLabel("Prescribe"), "Saving prescription…");
  });
});

describe("production loading copy", () => {
  it("does not use Coming Soon as a loading or empty state on staff boards", () => {
    const files = [
      "../workspaces/RegistrationDesk/RegistrationDeskWorkspace.tsx",
      "../workspaces/RegistrationDesk/CreateVisitWorkspace.tsx",
      "../workspaces/Doctor/DoctorWorkspace.tsx",
      "../workspaces/Doctor/ConsultationWorkspace.tsx",
      "../workspaces/Nursing/NursingWorkspace.tsx",
      "../workspaces/Laboratory/LaboratoryWorkspace.tsx",
      "../workspaces/Pharmacy/PharmacyWorkspace.tsx",
      "../workspaces/Accountant/AccountantWorkspace.tsx",
    ];
    for (const file of files) {
      const text = source(file);
      assert.equal(/Coming Soon|Coming soon|COMING SOON/i.test(text), false, file);
      assert.equal(text.includes("Please wait..."), false, file);
    }
  });

  it("keeps Reception today's patients loading out of the empty-state component", () => {
    const desk = source("../workspaces/RegistrationDesk/RegistrationDeskWorkspace.tsx");
    assert.equal(desk.includes("TableSkeleton"), true);
    assert.equal(desk.includes('title="No patients found today."'), true);
    assert.equal(desk.includes('title="Unable to load today\'s patients."'), true);
    assert.equal(desk.includes("Close Visit"), false);
  });

  it("uses shared loading treatment for consultation and department fee cards", () => {
    const consultFee = source("../workspaces/Doctor/ConsultationFeeCard.tsx");
    const labFee = source("../workspaces/Laboratory/LaboratoryFeeCard.tsx");
    const radFee = source("../workspaces/Radiology/RadiologyFeeCard.tsx");
    assert.equal(consultFee.includes("<LoadingState"), true);
    assert.equal(labFee.includes("<LoadingState"), true);
    assert.equal(radFee.includes("<LoadingState"), true);
    assert.equal(consultFee.includes("<p className=\"consult__muted\">Loading fee"), false);
    assert.equal(labFee.includes("<p className=\"lab-patient__muted\">Loading fee"), false);
    assert.equal(radFee.includes("<p className=\"rad-patient__muted\">Loading price"), false);
  });

  it("shows a pending Close Visit button and blocks a second submit", () => {
    const create = source("../workspaces/RegistrationDesk/CreateVisitWorkspace.tsx");
    assert.equal(create.includes("busyLabel={CLOSING_VISIT_LABEL}"), true);
    assert.equal(create.includes("if (closingVisit || !openVisit?.uuid || !offerClose)"), true);
    assert.equal(create.includes("if (startingVisit || !canSubmitVisit || !resolvedLocationUuid)"), true);
    assert.equal(create.includes("VISIT_CLOSED_SUCCESS_MESSAGE"), true);
  });
});
