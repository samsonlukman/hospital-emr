import {
  canOrderRadiologyService,
  findRadiologyService,
  HISTORICAL_ORD_6,
  resolveRadiologyOrderConcept,
  type RadiologyMenuService,
} from "../../config/radiologyMenu.ts";

export type BoundRadiologyVisit =
  | { status: "selected"; visitUuid: string; patientUuid: string }
  | { status: "no-selection" }
  | { status: "mismatch" };

export type RadiologyBillingStatus = "Price pending" | "Unpaid" | "Partially paid" | "Paid";

/**
 * The selected visit is authoritative. Never substitute first-open / latest / billed.
 */
export function bindRadiologyOrderVisit(input: {
  selectedVisitUuid: string | null | undefined;
  patientUuid: string;
  visitPatientUuid?: string;
}): BoundRadiologyVisit {
  const selected = (input.selectedVisitUuid || "").trim();
  if (!selected) {
    return { status: "no-selection" };
  }
  if (input.visitPatientUuid && input.visitPatientUuid !== input.patientUuid) {
    return { status: "mismatch" };
  }
  return { status: "selected", visitUuid: selected, patientUuid: input.patientUuid };
}

export function radiologyOrdersForSelectedVisit<T extends { visitUuid?: string }>(
  orders: T[],
  selectedVisitUuid: string | null | undefined,
): T[] {
  const selected = (selectedVisitUuid || "").trim();
  if (!selected) {
    return [];
  }
  return orders.filter((order) => (order.visitUuid || "").trim() === selected);
}

export function canSubmitRadiologyOrder(input: {
  selectedVisitUuid: string | null | undefined;
  service: RadiologyMenuService | undefined;
  optionId?: string;
}): boolean {
  if (!(input.selectedVisitUuid || "").trim() || !canOrderRadiologyService(input.service)) {
    return false;
  }
  if (input.service?.options?.length) {
    return Boolean(input.optionId && input.service.options.some((row) => row.id === input.optionId));
  }
  return true;
}

export function radiologyOrderPayload(input: {
  selectedVisitUuid: string | null | undefined;
  patientUuid: string;
  serviceId: string;
  optionId?: string;
}): { visitUuid: string; patientUuid: string; conceptUuid: string; hospitalName: string } | null {
  const bound = bindRadiologyOrderVisit({
    selectedVisitUuid: input.selectedVisitUuid,
    patientUuid: input.patientUuid,
  });
  if (bound.status !== "selected") {
    return null;
  }
  const service = findRadiologyService(input.serviceId);
  const concept = resolveRadiologyOrderConcept(service, input.optionId);
  if (!concept) {
    return null;
  }
  return {
    visitUuid: bound.visitUuid,
    patientUuid: bound.patientUuid,
    conceptUuid: concept.conceptUuid,
    hospitalName: concept.optionLabel
      ? `${service?.hospitalName} — ${concept.optionLabel}`
      : service?.hospitalName || concept.conceptName,
  };
}

export function radiologyBillingStatus(input: {
  hasCharge?: boolean;
  paymentStatus?: string;
}): RadiologyBillingStatus {
  if (!input.hasCharge) {
    return "Price pending";
  }
  if (input.paymentStatus === "PAID") {
    return "Paid";
  }
  if (input.paymentStatus === "PARTIALLY PAID") {
    return "Partially paid";
  }
  return "Unpaid";
}

export function historicalOrd6Unchanged(): typeof HISTORICAL_ORD_6 {
  return HISTORICAL_ORD_6;
}
