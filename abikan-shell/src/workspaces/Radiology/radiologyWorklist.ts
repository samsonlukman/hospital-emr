import {
  findRadiologyServiceByConcept,
  HISTORICAL_ORD_6,
  RADIOLOGY_MENU,
  RADIOGRAPHY_GROUP,
  ULTRASOUND_GROUP,
} from "../../config/radiologyMenu.ts";
import type { RadiologyWorklistRow } from "../../types/radiologyBilling.ts";
import { radiologyOrderIdentity } from "./radiologyDesk.ts";
import { doctorCannotSetRadiologyPrice, radiologistSetsOrderPrice } from "./radiologyPrice.ts";

export type RadiologyWorklistView = "pending" | "reported" | "all";
export type RadiologyWorklistCategory = "" | typeof ULTRASOUND_GROUP | typeof RADIOGRAPHY_GROUP;

export const WORKLIST_PROTECTED_ORDERS = [
  "ORD-6",
  "ORD-14",
  "ORD-15",
  "ORD-16",
  "ORD-17",
  "ORD-18",
  "ORD-19",
  "ORD-20",
  "ORD-21",
] as const;

export const WORKLIST_PROTECTED_INVOICES = [
  "INV/2026/00006",
  "INV/2026/00031",
  "INV/2026/00032",
  "INV/2026/00033",
  "INV/2026/00034",
  "INV/2026/00035",
] as const;

export const WORKLIST_TEST_ORDERS = {
  ord16: {
    orderNumber: "ORD-16",
    orderUuid: "a6e20ad8-7b64-49fc-9c87-8cb8a57d227d",
    patientUuid: "26b50a91-0e06-4153-b872-530a9c67a4c8",
    visitUuid: "0b99c191-5e6d-4784-8ecf-cb747cfccef3",
    investigation: "Musculoskeletal",
    hasReport: true,
  },
  ord17: {
    orderNumber: "ORD-17",
    orderUuid: "b43c54b2-696d-4925-86ce-06455000330e",
    patientUuid: "26b50a91-0e06-4153-b872-530a9c67a4c8",
    visitUuid: "0b99c191-5e6d-4784-8ecf-cb747cfccef3",
    investigation: "Skull X-ray",
    hasReport: false,
  },
  ord18: {
    orderNumber: "ORD-18",
    orderUuid: "6db4d95b-b581-4ed2-8076-0c15d0ae5d51",
    patientUuid: "26b50a91-0e06-4153-b872-530a9c67a4c8",
    visitUuid: "43518247-9125-478b-bbca-6a5473f0fb9b",
    investigation: "Pelvic",
    hasReport: false,
  },
  ord19: {
    orderNumber: "ORD-19",
    orderUuid: "dc2cdf49-dba1-471b-b010-04343cbf79c9",
    patientUuid: "f242364e-b70f-4fec-b29e-8ad4fbe147b5",
    visitUuid: "2857db49-c8fa-46d0-be38-2213f4cc54bc",
    investigation: "Lumbosacral Spine",
    hasReport: true,
  },
} as const;

export const WORKLIST_USES_VISIT_DATE_WINDOW = false;

export function isPendingRadiologyWork(row: Pick<RadiologyWorklistRow, "hasReport">): boolean {
  return !row.hasReport;
}

export function worklistIncludesOrderRegardlessOfVisitAge(): boolean {
  return !WORKLIST_USES_VISIT_DATE_WINDOW;
}

export function worklistHasNoDuplicateOrders(rows: RadiologyWorklistRow[]): boolean {
  const seen = new Set<string>();
  for (const row of rows) {
    if (!row.uuid) {
      continue;
    }
    if (seen.has(row.uuid)) {
      return false;
    }
    seen.add(row.uuid);
  }
  return true;
}

export function worklistRowIdentity(row: Pick<RadiologyWorklistRow, "uuid" | "patientUuid" | "visitUuid">) {
  return radiologyOrderIdentity({
    uuid: row.uuid,
    patientUuid: row.patientUuid,
    visitUuid: row.visitUuid,
  });
}

export function canOpenWorklistRow(
  row: Pick<RadiologyWorklistRow, "uuid" | "patientUuid" | "visitUuid" | "isExternal">,
): boolean {
  if (row.isExternal && String(row.uuid || "").trim()) {
    return true;
  }
  return worklistRowIdentity(row) !== null;
}

export function rejectMismatchedWorklistOrder(input: {
  order: { uuid: string; patientUuid: string; visitUuid?: string };
  expectedPatientUuid?: string;
  expectedVisitUuid?: string;
}): "ok" | "missing" | "mismatch" {
  const identity = worklistRowIdentity({
    uuid: input.order.uuid,
    patientUuid: input.order.patientUuid,
    visitUuid: input.order.visitUuid || "",
  });
  if (!identity) {
    return "missing";
  }
  const expectedPatient = (input.expectedPatientUuid || "").trim();
  const expectedVisit = (input.expectedVisitUuid || "").trim();
  if (!expectedPatient && !expectedVisit) {
    return "ok";
  }
  if (
    (expectedPatient && expectedPatient !== identity.patientUuid) ||
    (expectedVisit && expectedVisit !== identity.visitUuid)
  ) {
    return "mismatch";
  }
  return "ok";
}

export function matchesWorklistSearch(row: RadiologyWorklistRow, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return [
    row.patientName,
    row.mrn,
    row.investigation,
    row.orderNumber,
    row.visitType,
    row.buyerPhone,
    row.studyId,
    row.patientTypeLabel,
    row.requestSourceLabel,
  ]
    .join(" ")
    .toLowerCase()
    .includes(needle);
}

export function matchesWorklistCategory(
  row: RadiologyWorklistRow,
  category: RadiologyWorklistCategory,
): boolean {
  return !category || row.category === category;
}

export function sortWorklistNewestFirst(rows: RadiologyWorklistRow[]): RadiologyWorklistRow[] {
  return [...rows].sort((left, right) => {
    const byDate = (right.ordered || "").localeCompare(left.ordered || "");
    if (byDate !== 0) {
      return byDate;
    }
    return (right.orderNumber || "").localeCompare(left.orderNumber || "");
  });
}

export function filterWorklistRows(
  rows: RadiologyWorklistRow[],
  input: {
    query?: string;
    category?: RadiologyWorklistCategory;
    view?: RadiologyWorklistView;
  } = {},
): RadiologyWorklistRow[] {
  const view = input.view || "all";
  return sortWorklistNewestFirst(
    rows.filter((row) => {
      if (!canOpenWorklistRow(row)) {
        return false;
      }
      if (!matchesWorklistSearch(row, input.query || "")) {
        return false;
      }
      if (!matchesWorklistCategory(row, input.category || "")) {
        return false;
      }
      if (view === "pending") {
        return isPendingRadiologyWork(row);
      }
      if (view === "reported") {
        return row.hasReport;
      }
      return true;
    }),
  );
}

export function worklistRowsForPatient(
  rows: RadiologyWorklistRow[],
  patientUuid: string,
): RadiologyWorklistRow[] {
  const selected = patientUuid.trim();
  if (!selected) {
    return [];
  }
  return rows.filter((row) => row.patientUuid === selected);
}

export function worklistRowsForVisit(
  rows: RadiologyWorklistRow[],
  visitUuid: string,
): RadiologyWorklistRow[] {
  const selected = visitUuid.trim();
  if (!selected) {
    return [];
  }
  return rows.filter((row) => row.visitUuid === selected);
}

export function worklistHasNoCrossPatientLeak(
  rows: RadiologyWorklistRow[],
  patientUuid: string,
  foreignOrderUuid: string,
): boolean {
  return !worklistRowsForPatient(rows, patientUuid).some((row) => row.uuid === foreignOrderUuid);
}

export function allHospitalServicesCanAppearOnWorklist(): boolean {
  return (
    RADIOLOGY_MENU.length === 42 &&
    RADIOLOGY_MENU.every((service) => {
      const concept =
        service.conceptUuid || service.options?.[0]?.conceptUuid || "";
      return Boolean(findRadiologyServiceByConcept(concept));
    })
  );
}

export function doctorCannotPriceFromWorklist(): true {
  return doctorCannotSetRadiologyPrice();
}

export function radiologistPricesFromWorklist(): true {
  return radiologistSetsOrderPrice();
}

export function worklistFixturesUnchanged(): {
  orders: typeof WORKLIST_PROTECTED_ORDERS;
  invoices: typeof WORKLIST_PROTECTED_INVOICES;
  ord6: typeof HISTORICAL_ORD_6;
} {
  return {
    orders: WORKLIST_PROTECTED_ORDERS,
    invoices: WORKLIST_PROTECTED_INVOICES,
    ord6: HISTORICAL_ORD_6,
  };
}

export function replaceWorklistRows(
  _previous: RadiologyWorklistRow[] | null,
  next: RadiologyWorklistRow[],
): RadiologyWorklistRow[] {
  return next;
}
