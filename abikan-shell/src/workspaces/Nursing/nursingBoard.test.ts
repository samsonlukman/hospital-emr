import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseShellHash } from "../../app/hashRoute.ts";
import { mergeNursingDayPatients } from "./nursingDayPatients.ts";

const NURSING_NAV = readFileSync(
  fileURLToPath(new URL("../../config/nursingNav.ts", import.meta.url)),
  "utf8",
);
const NURSING_BOARD = readFileSync(
  fileURLToPath(new URL("./nursingBoard.ts", import.meta.url)),
  "utf8",
);
const NURSING_WORKSPACE = readFileSync(
  fileURLToPath(new URL("./NursingWorkspace.tsx", import.meta.url)),
  "utf8",
);

describe("nursing bed prices", () => {
  it("exposes Bed Prices in the nursing sidebar", () => {
    assert.match(NURSING_NAV, /label: "Bed Prices"/);
    assert.match(NURSING_NAV, /href: "#\/nursing\/pricing"/);
    assert.match(NURSING_BOARD, /"pricing"/);
  });

  it("keeps bed prices inside nursing", () => {
    assert.equal(parseShellHash("#/nursing/pricing").route, "nursing");
    assert.equal(parseShellHash("#/nursing/pricing").navItemId, "pricing");
    assert.equal(parseShellHash("#/nursing/bed-prices").navItemId, "pricing");
    assert.equal(parseShellHash("#/nursing/prices").navItemId, "pricing");
  });
});

describe("nursing patients for the day", () => {
  it("lists today's visits together with ward patients and does not duplicate them", () => {
    const rows = mergeNursingDayPatients(
      [
        {
          areaName: "Hawawu Maternity Ward",
          bed: {
            bedUuid: "bed-1",
            bedId: 1,
            bedNumber: "2",
            status: "OCCUPIED",
            areaName: "Hawawu Maternity Ward",
            areaUuid: "area-1",
            patientUuid: "inpatient-1",
            patientName: "Ada Ward",
            mrn: "ABC200001",
            age: "28",
            sex: "F",
          },
        },
      ],
      [
        {
          patientUuid: "awaiting-1",
          patientName: "Bisi Admit",
          mrn: "ABC200002",
          sex: "F",
          age: "32",
          requested: "2026-09-29T08:00:00.000+0000",
          visitUuid: "ipd-1",
        },
      ],
      [
        {
          id: "visit-opd",
          patientUuid: "opd-1",
          visitUuid: "visit-opd",
          patientName: "Chioma Outpatient",
          mrn: "ABC200003",
          visitType: "OPD",
          time: "09:15",
          status: "Open",
          dailyVisitNumber: "001",
        },
        {
          id: "visit-dup",
          patientUuid: "inpatient-1",
          visitUuid: "visit-dup",
          patientName: "Ada Ward",
          mrn: "ABC200001",
          visitType: "IPD",
          time: "07:00",
          status: "Open",
          dailyVisitNumber: "002",
        },
      ],
    );
    assert.equal(rows.length, 3);
    assert.equal(rows[0].status, "Occupied");
    assert.equal(rows[1].status, "Admit requested");
    assert.equal(rows[2].status, "Visit today");
    assert.equal(rows[2].name, "Chioma Outpatient");
    assert.equal(
      rows.some((row) => row.patientUuid === "inpatient-1" && row.status === "Visit today"),
      false,
    );
  });

  it("loads today's visits on the nursing patients list", () => {
    assert.match(NURSING_WORKSPACE, /fetchNursingTodaysPatients/);
    assert.match(NURSING_WORKSPACE, /Patients with a visit today/);
  });

  it("exposes Today's Visits in the nursing sidebar", () => {
    assert.match(NURSING_NAV, /label: "Today's Visits"/);
    assert.match(NURSING_NAV, /href: "#\/nursing\/visits"/);
    assert.equal(parseShellHash("#/nursing/visits").navItemId, "todays-visits");
    assert.match(NURSING_BOARD, /navItemId === "todays-visits"/);
    assert.match(NURSING_WORKSPACE, /TodaysVisitsView/);
  });
});
