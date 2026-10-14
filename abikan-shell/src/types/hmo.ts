export interface HmoAssignment {
  patientUuid: string;
  patientName: string;
  hospitalNumber: string;
  scheme: "NHIA" | "HMO (Private)";
  body: string;
  assignedAt?: string;
}

export interface HmoMetadata {
  schemes: Record<string, string[]>;
}

export interface HmoAssignmentsPayload {
  assignments: HmoAssignment[];
}

export interface HmoBillLine {
  date: string;
  description: string;
  department: string;
  amount: number;
  amountLabel: string;
}

export interface HmoBillPatient {
  patientUuid: string;
  patientName: string;
  hospitalNumber: string;
  scheme: string;
  lines: HmoBillLine[];
  totalLabel: string;
}

export interface HmoStatement {
  hospital: { name: string; phone: string; email: string };
  body: string;
  scheme: string;
  start: string;
  end: string;
  patients: HmoBillPatient[];
  patientCount: number;
  totalLabel: string;
}

export interface HmoBodyOption {
  scheme: string;
  body: string;
  patients: number;
}

export interface HmoBillsPayload {
  bodies: HmoBodyOption[];
  hospital: { name: string; phone: string; email: string };
  statement?: HmoStatement;
  sent?: string;
  message?: string;
}
