import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { consultationHref, parseShellHash, readConsultationVisitUuid } from "../../app/hashRoute.ts";
import { DOCTOR_NAV } from "../../config/doctorNav.ts";
import { bindConsultationVisit, firstOpenVisit, VISIT_NOT_SELECTED_MESSAGE } from "./consultationVisit.ts";
import type { MyPatientRow } from "../../types/index.ts";
import {
  chartViewDoesNotQualifyForMyPatients,
  filterMyPatients,
  mapMyPatientRow,
  matchesMyPatientsSearch,
  myPatientsEmptyTitle,
  myPatientsHref,
  myPatientsOpensVisit,
  myPatientsScopedToSessionProvider,
  myPatientsUsesConsultationProvider,
  MY_PATIENTS_EMPTY,
  MY_PATIENTS_EMPTY_HELP,
  MY_PATIENTS_SEARCH_EMPTY,
  radiologyOrdererDoesNotQualifyForMyPatients,
  sortMyPatientsMostRecent,
  uniqueMyPatients,
} from "./myPatients.ts";

const ABC16 = "f242364e-b70f-4fec-b29e-8ad4fbe147b5";
const ABC18 = "26b50a91-0e06-4153-b872-530a9c67a4c8";

function row(overrides: Partial<MyPatientRow> = {}): MyPatientRow {
  return {
    id: ABC16,
    patientUuid: ABC16,
    patientName: "ABIKAN E2E TEST PATIENT",
    mrn: "ABC200016",
    ageSex: "36 / M",
    visitType: "OPD",
    lastAttended: "2026-08-24T23:41:59.000+0000",
    dailyVisitNumber: "001",
    attendedBy: "Clinical Doctor",
    ...overrides,
  };
}

describe("My Patients", () => {
  it("is a live Clinical route, not Coming soon", () => {
    const item = DOCTOR_NAV[0]?.items.find((entry) => entry.id === "my-patients");
    assert.equal(item?.kind, "route");
    assert.equal(item && "href" in item ? item.href : "", "#/doctor/my-patients");
    assert.equal(parseShellHash("#/doctor/my-patients").section, "my-patients");
    assert.equal(parseShellHash("#/doctor/my-patients").navItemId, "my-patients");
  });

  it("uses Consultation encounter_provider, not viewing or radiology ordering", () => {
    assert.equal(myPatientsUsesConsultationProvider(), true);
    assert.equal(chartViewDoesNotQualifyForMyPatients(), true);
    assert.equal(radiologyOrdererDoesNotQualifyForMyPatients(), true);
    assert.equal(myPatientsScopedToSessionProvider(), true);
    assert.equal(mapMyPatientRow({ patient: "Viewed only" }), null);
    assert.equal(
      mapMyPatientRow({
        patient: "Radiology only",
        visitUuid: "visit-from-order",
      }),
      null,
    );
  });

  it("shows ABC200016 once using the most recent consultation", () => {
    const older = row({
      lastAttended: "2026-08-16T10:00:00.000+0000",
      dailyVisitNumber: "002",
    });
    const newer = row({
      lastAttended: "2026-08-24T23:41:59.000+0000",
      dailyVisitNumber: "001",
    });
    const listed = uniqueMyPatients([older, newer, row({ lastAttended: "2026-08-20T12:00:00.000+0000" })]);
    assert.equal(listed.length, 1);
    assert.equal(listed[0]?.patientUuid, ABC16);
    assert.equal(listed[0]?.lastAttended, newer.lastAttended);
    assert.equal(listed[0]?.dailyVisitNumber, "001");
  });

  it("lists the same patient independently for each attending doctor", () => {
    const clinical = row({ attendedBy: "Clinical Doctor" });
    const other = row({
      attendedBy: "Hospital EMR Development Admin",
      lastAttended: "2026-08-15T09:00:00.000+0000",
    });
    assert.equal(clinical.patientUuid, other.patientUuid);
    assert.notEqual(clinical.attendedBy, other.attendedBy);
    assert.equal(uniqueMyPatients([clinical]).some((item) => item.attendedBy === "Clinical Doctor"), true);
    assert.equal(
      uniqueMyPatients([other]).some((item) => item.attendedBy === "Hospital EMR Development Admin"),
      true,
    );
  });

  it("sorts most recently attended first and searches only this list", () => {
    const older = row({
      id: ABC18,
      patientUuid: ABC18,
      patientName: "Test User Testing",
      mrn: "ABC200018",
      lastAttended: "2026-08-20T10:00:00.000+0000",
    });
    const sorted = sortMyPatientsMostRecent([older, row()]);
    assert.equal(sorted[0]?.mrn, "ABC200016");
    assert.equal(matchesMyPatientsSearch(row(), "ABC200016"), true);
    assert.equal(matchesMyPatientsSearch(row(), "ABIKAN"), true);
    assert.equal(matchesMyPatientsSearch(row(), "ABC200018"), false);
    assert.equal(filterMyPatients([row(), older], "018")[0]?.mrn, "ABC200018");
  });

  it("opens the patient without selecting a visit", () => {
    const href = myPatientsHref(ABC16);
    assert.equal(href, `#/doctor/patient/${ABC16}`);
    assert.equal(href, consultationHref(ABC16));
    assert.equal(myPatientsOpensVisit(href), false);
    assert.equal(readConsultationVisitUuid(href), null);
    const bound = bindConsultationVisit({
      selectedVisitUuid: readConsultationVisitUuid(href),
      patientUuid: ABC16,
      visits: [
        {
          uuid: "732bc9b8-dd6a-4063-862e-304dc02c9f13",
          start: "00:41",
          startDate: "25 Aug 2026",
          startDatetime: "2026-08-24T23:41:57.000+0000",
          stop: null,
          visitType: "OPD",
          location: "OPD-1",
          open: true,
          dailyVisitNumber: "001",
          attendedBy: "Clinical Doctor",
        },
      ],
    });
    assert.equal(bound.status, "no-selection");
    assert.match(VISIT_NOT_SELECTED_MESSAGE, /Previous visits/);
    assert.equal(firstOpenVisit(bound.status === "selected" ? [bound.visit] : [])?.uuid, undefined);
  });

  it("requires an explicit visit hash before a visit is selected", () => {
    const visitUuid = "2857db49-c8fa-46d0-be38-2213f4cc54bc";
    const href = consultationHref(ABC16, visitUuid);
    assert.equal(myPatientsOpensVisit(href), true);
    assert.equal(readConsultationVisitUuid(href), visitUuid);
    assert.notEqual(myPatientsHref(ABC16), href);
  });

  it("uses the attended empty state, not a search-failure message", () => {
    assert.equal(MY_PATIENTS_EMPTY, "No patients have been attended by you yet.");
    assert.equal(MY_PATIENTS_EMPTY_HELP, "Patients appear here after you save a Consultation for them.");
    assert.equal(myPatientsEmptyTitle({ hasRows: false }), MY_PATIENTS_EMPTY);
    assert.equal(
      myPatientsEmptyTitle({ hasRows: true, query: "ZZZ" }),
      MY_PATIENTS_SEARCH_EMPTY,
    );
    assert.equal(MY_PATIENTS_EMPTY.includes("No patients found"), false);
  });

  it("does not treat another doctor's patients as visible to this session", () => {
    const mine = [row()];
    const otherDoctorOnly = row({
      id: "other-patient",
      patientUuid: "other-patient",
      patientName: "Other Doctor Patient",
      mrn: "ABC199999",
      attendedBy: "Neha Anand",
    });
    assert.equal(
      filterMyPatients(mine, "ABC199999").some((item) => item.patientUuid === otherDoctorOnly.patientUuid),
      false,
    );
    assert.equal(mine.some((item) => item.attendedBy === "Neha Anand"), false);
  });
});
