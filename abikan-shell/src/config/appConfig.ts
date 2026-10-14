const configuredOrigin = import.meta.env.VITE_BAHMNI_ORIGIN ?? "";

export const BAHMNI_ORIGIN = configuredOrigin.replace(/\/$/, "");

export const BAHMNI_ROUTES = {
  registerPatient: "/bahmni/registration/index.html#/patient/new",
  findPatient: "/bahmni/registration/index.html#/search",
  viewPatient: (patientUuid: string) =>
    `/bahmni/registration/index.html#/patient/${patientUuid}`,
  appointments: "/appointments",
  patientDashboard: (patientUuid: string) =>
    `/bahmni/clinical/index.html#/default/patient/${patientUuid}/dashboard`,
  openElis: "/openelis",
  pacs: "/dcm4chee-web3",
  orders: "/bahmni/orders",
} as const;

export function oviyamUrl(patientId: string, accessionNumber: string): string {
  const query = new URLSearchParams({
    patientID: patientId,
    accessionNumber,
  });
  return bahmniUrl(`/oviyam2/oviyam?${query.toString()}`);
}

export function bahmniUrl(path: string): string {
  return `${BAHMNI_ORIGIN}${path}`;
}

export const USER_COOKIE = "bahmni.user";
export const LOCATION_COOKIE = "bahmni.user.location";
export const REGISTRATION_PRIVILEGE = "app:registration";
export const REGISTRATION_DESK_NAME = "Registration Desk";

export const PRIVILEGES = {
  registration: "app:registration",
  appointments: "app:appointments",
  clinical: "app:clinical",
  emergency: "app:emergency",
  adt: "app:adt",
  reports: "app:reports",
  admin: "app:admin",
  documents: "app:patient-documents",
  radiology: "app:radiology-upload",
  labLite: "app:lab-lite",
  pharmacy: "bahmni:clinical:dispense",
  accountant: "abikan:accountant",
  adminStaff: "abikan:admin:staff",
  adminAnalytics: "abikan:admin:analytics",
  adminAuditRead: "abikan:admin:audit-read",
} as const;
