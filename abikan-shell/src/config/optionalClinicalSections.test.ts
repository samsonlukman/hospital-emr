import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  OPTIONAL_CLINICAL_SECTIONS,
  optionalSectionsVisibleInWorkspace,
} from "./optionalClinicalSections.ts";

const HIDDEN_UNAVAILABLE_TITLES = [
  "Examination",
  "Review of Systems",
  "Family History",
  "Social History",
  "Past Medical History",
  "Medication History",
];

describe("optional clinical sections", () => {
  it("hides unavailable Examination, ROS, Family History, and Social History from the workspace", () => {
    const visibleTitles = optionalSectionsVisibleInWorkspace().map((row) => row.title);
    for (const title of HIDDEN_UNAVAILABLE_TITLES) {
      assert.equal(visibleTitles.includes(title), false);
    }
    assert.equal(optionalSectionsVisibleInWorkspace().length, 0);
  });

  it("does not invent examination, family, or social forms", () => {
    const examination = OPTIONAL_CLINICAL_SECTIONS.find((row) => row.id === "examination");
    const family = OPTIONAL_CLINICAL_SECTIONS.find((row) => row.id === "family-history");
    const social = OPTIONAL_CLINICAL_SECTIONS.find((row) => row.id === "social-history");
    assert.equal(examination?.status, "not-configured");
    assert.equal(family?.status, "not-configured");
    assert.equal(social?.status, "not-configured");
    assert.equal(examination?.visibleInWorkspace, false);
    assert.equal(family?.visibleInWorkspace, false);
    assert.equal(social?.visibleInWorkspace, false);
  });

  it("does not duplicate medicines or invent a review-of-systems checklist", () => {
    const medication = OPTIONAL_CLINICAL_SECTIONS.find((row) => row.id === "medication-history");
    const ros = OPTIONAL_CLINICAL_SECTIONS.find((row) => row.id === "review-of-systems");
    assert.equal(medication?.status, "exists-elsewhere");
    assert.match(medication?.explanation || "", /Medications/);
    assert.equal(medication?.visibleInWorkspace, false);
    assert.equal(ros?.status, "dictionary-only");
    assert.equal(ros?.visibleInWorkspace, false);
    for (const section of OPTIONAL_CLINICAL_SECTIONS) {
      assert.equal(section.defaultOpen, false);
      assert.equal(section.required, false);
      assert.doesNotMatch(section.explanation, /\b(None|Negative|Normal|Not applicable)\b/i);
      assert.doesNotMatch(section.explanation, /\b(uuid|OpenMRS|Bahmni|API|concept)\b/i);
    }
  });
});
