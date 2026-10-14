export function rejectMismatchedLaboratoryOrder(input: {
  order: { uuid: string; patientUuid: string; visitUuid?: string };
  expectedPatientUuid?: string;
  expectedVisitUuid?: string;
}): "ok" | "missing" | "mismatch" {
  const patientUuid = (input.order.patientUuid || "").trim();
  const visitUuid = (input.order.visitUuid || "").trim();
  if (!input.order.uuid || !patientUuid) {
    return "missing";
  }
  const expectedPatient = (input.expectedPatientUuid || "").trim();
  const expectedVisit = (input.expectedVisitUuid || "").trim();
  if (!expectedPatient && !expectedVisit) {
    return "ok";
  }
  if (expectedPatient && expectedPatient !== patientUuid) {
    return "mismatch";
  }
  if (expectedVisit && visitUuid && expectedVisit !== visitUuid) {
    return "mismatch";
  }
  return "ok";
}
