export interface BirthCertificateForm {
  certificateId?: string;
  referenceNo: string;
  occurredAt: string;
  childName: string;
  gender: string;
  weight: string;
  motherName: string;
  fatherName: string;
  caseId: string;
  address: string;
}

export interface DeathCertificateForm {
  referenceNo: string;
  occurredAt: string;
  patientName: string;
  gender: string;
  caseId: string;
  guardianName: string;
  address: string;
  report: string;
}

export interface CertificatePatient {
  uuid: string;
  name: string;
  hospitalNumber: string;
  alive: boolean;
  status: "Alive" | "Dead";
}

export interface CertificatesPayload {
  status: string;
  message?: string;
  patient: CertificatePatient;
  birth: BirthCertificateForm;
  death: DeathCertificateForm;
  saved: { birth: boolean; death: boolean };
}
