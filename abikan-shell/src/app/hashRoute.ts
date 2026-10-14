export type ShellRoute =
  | "home"
  | "messages"
  | "registration-desk"
  | "registration-patient"
  | "registration-register"
  | "registration-visit"
  | "registration-antenatal"
  | "registration-antenatal-register"
  | "registration-patients"
  | "registration-patient-record"
  | "registration-families"
  | "registration-family"
  | "workspace"
  | "doctor"
  | "consultation"
  | "nursing"
  | "nursing-patient"
  | "laboratory"
  | "laboratory-patient"
  | "laboratory-order"
  | "laboratory-external"
  | "radiology"
  | "radiology-patient"
  | "radiology-order"
  | "radiology-external"
  | "pharmacy"
  | "pharmacy-patient"
  | "pharmacy-prescription"
  | "patient-account"
  | "patient-account-invoice"
  | "accountant"
  | "accountant-patient"
  | "hmo"
  | "staff-accounts"
  | "department-access"
  | "admin-analytics"
      | "admin-audit"
      | "admin-export"
      | "admin-log"
      | "admin-patients"
  | "admin-hmo-bills"
  | "admin-certificates"
  | "admin-patient-record"
  | "accommodation-settings"
  | "system-settings"
  | "unavailable";

export interface ParsedShellHash {
  route: ShellRoute;
  section: string | null;
  navItemId: string | null;
}

const SECTION_ALIASES: Record<string, Record<string, { element: string; nav: string }>> = {
  pharmacy: {
    prescriptions: { element: "prescriptions", nav: "prescriptions" },
    "new-sale": { element: "new-sale", nav: "new-sale" },
    sales: { element: "new-sale", nav: "new-sale" },
    ready: { element: "prescriptions", nav: "prescriptions" },
    "ready-to-dispense": { element: "prescriptions", nav: "prescriptions" },
    "sales-history": { element: "sales-history", nav: "sales-history" },
    history: { element: "sales-history", nav: "sales-history" },
    dispensed: { element: "sales-history", nav: "sales-history" },
    catalogue: { element: "catalogue", nav: "catalogue" },
    drugs: { element: "catalogue", nav: "catalogue" },
    "drug-catalogue": { element: "catalogue", nav: "catalogue" },
    "add-medicine": { element: "catalogue", nav: "catalogue" },
    pricing: { element: "pricing", nav: "pricing" },
    "drug-pricing": { element: "pricing", nav: "pricing" },
    inventory: { element: "inventory", nav: "inventory" },
    stock: { element: "inventory", nav: "inventory" },
  },
  radiology: {
    orders: { element: "worklist", nav: "worklist" },
    requests: { element: "worklist", nav: "worklist" },
    worklist: { element: "worklist", nav: "worklist" },
    "new-study": { element: "new-study", nav: "new-study" },
    direct: { element: "new-study", nav: "new-study" },
    "new-imaging": { element: "new-study", nav: "new-study" },
    "desk-order": { element: "new-study", nav: "new-study" },
    history: { element: "history", nav: "history" },
    studies: { element: "history", nav: "history" },
    reported: { element: "history", nav: "history" },
    past: { element: "history", nav: "history" },
  },
  laboratory: {
    orders: { element: "orders", nav: "orders" },
    pending: { element: "pending", nav: "pending" },
    processing: { element: "processing", nav: "processing" },
    completed: { element: "completed", nav: "completed" },
    results: { element: "completed", nav: "completed" },
    patients: { element: "patients", nav: "patients" },
    search: { element: "patients", nav: "patients" },
    "blood-bank": { element: "blood-bank", nav: "blood-bank" },
    bloodbank: { element: "blood-bank", nav: "blood-bank" },
    inventory: { element: "inventory", nav: "inventory" },
    stock: { element: "inventory", nav: "inventory" },
    pricing: { element: "pricing", nav: "pricing" },
    "test-pricing": { element: "pricing", nav: "pricing" },
    "reference-ranges": { element: "reference-ranges", nav: "reference-ranges" },
    "hospital-tests": { element: "hospital-tests", nav: "hospital-tests" },
    catalogue: { element: "hospital-tests", nav: "hospital-tests" },
    "create-test": { element: "create-test", nav: "create-test" },
    "new-order": { element: "new-order", nav: "new-order" },
    direct: { element: "new-order", nav: "new-order" },
    history: { element: "history", nav: "history" },
    studies: { element: "history", nav: "history" },
    deleted: { element: "deleted", nav: "deleted-orders" },
    "deleted-orders": { element: "deleted", nav: "deleted-orders" },
  },
  nursing: {
    wards: { element: "ward-board", nav: "ward-board" },
    "ward-board": { element: "ward-board", nav: "ward-board" },
    patients: { element: "patients", nav: "patients" },
    visits: { element: "visits", nav: "todays-visits" },
    "todays-visits": { element: "visits", nav: "todays-visits" },
    treatments: { element: "treatments", nav: "treatments" },
    admissions: { element: "admissions", nav: "admissions" },
    transfers: { element: "transfers", nav: "transfers" },
    discharge: { element: "discharges", nav: "discharges" },
    discharges: { element: "discharges", nav: "discharges" },
    pricing: { element: "pricing", nav: "pricing" },
    prices: { element: "pricing", nav: "pricing" },
    "bed-prices": { element: "pricing", nav: "pricing" },
  },
  doctor: {
    queue: { element: "queue", nav: "queue" },
    "my-patients": { element: "my-patients", nav: "my-patients" },
    "pharmacy-medicines": { element: "pharmacy-medicines", nav: "pharmacy-medicines" },
    medicines: { element: "pharmacy-medicines", nav: "pharmacy-medicines" },
    pharmacy: { element: "pharmacy-medicines", nav: "pharmacy-medicines" },
  },
  reception: {
    visits: { element: "visits", nav: "todays-visits" },
    visit: { element: "create-visit", nav: "create-visit" },
    antenatal: { element: "antenatal", nav: "antenatal" },
    anc: { element: "antenatal", nav: "antenatal" },
    register: { element: "register", nav: "register" },
    families: { element: "families", nav: "families" },
    accounts: { element: "accounts", nav: "patient-accounts" },
    pricing: { element: "pricing", nav: "pricing" },
    prices: { element: "pricing", nav: "pricing" },
  },
  "registration-desk": {
    visits: { element: "visits", nav: "todays-visits" },
    patients: { element: "visits", nav: "patients" },
  },
  accountant: {
    "create-bill": { element: "create", nav: "accountant-create" },
    outstanding: { element: "outstanding", nav: "accountant-outstanding" },
    deleted: { element: "deleted", nav: "accountant-deleted" },
    waived: { element: "waived", nav: "accountant-waived" },
    attention: { element: "outstanding", nav: "accountant-outstanding" },
    payments: { element: "payments", nav: "accountant-payments" },
    receipts: { element: "payments", nav: "accountant-payments" },
    recent: { element: "payments", nav: "accountant-payments" },
    refunds: { element: "refunds", nav: "accountant-refunds" },
    revenue: { element: "revenue", nav: "accountant-revenue" },
  },
};

function normalizeHash(rawHash: string): string {
  return rawHash.replace(/^#\/?/, "").replace(/[?#].*$/, "").replace(/\/+$/, "");
}

function parsed(
  route: ShellRoute,
  spec: { element: string; nav: string } | null = null,
): ParsedShellHash {
  return { route, section: spec?.element ?? null, navItemId: spec?.nav ?? null };
}

function sectionSpec(
  department: string,
  segment: string | undefined,
): { element: string; nav: string } | null {
  if (!segment) {
    return null;
  }
  return SECTION_ALIASES[department]?.[segment] ?? null;
}

/**
 * Parse a Hospital EMR hash. Department prefixes stay in that department.
 * Bare in-page ids such as `#ready` are not Administration — they are unknown.
 */
export function parseShellHash(rawHash: string): ParsedShellHash {
  const hash = normalizeHash(rawHash);
  if (!hash || hash === "home") {
    return parsed("home");
  }
  if (hash === "messages/call") {
    return parsed("messages", { element: "call", nav: "message-calls" });
  }
  if (hash === "messages") {
    return parsed("messages");
  }
  if (hash.startsWith("messages/")) {
    const conversationId = hash.slice("messages/".length).split("/")[0];
    if (conversationId && conversationId !== "call") {
      return parsed("messages", { element: conversationId, nav: "messages" });
    }
    return parsed("messages");
  }
  if (hash === "workspace") {
    return parsed("workspace");
  }
  if (hash === "accommodation-settings") {
    return parsed("accommodation-settings");
  }
  if (hash === "system-settings") {
    return parsed("system-settings");
  }
  if (hash === "hmo") {
    return parsed("hmo", { element: "hmo", nav: "hmo" });
  }
  if (hash === "staff-accounts") {
    return parsed("staff-accounts");
  }
  if (hash === "department-access") {
    return parsed("department-access");
  }
  if (hash === "admin/analytics" || hash === "admin-analytics") {
    return parsed("admin-analytics", { element: "analytics", nav: "admin-analytics" });
  }
  if (hash === "admin/audit" || hash === "admin-audit") {
    return parsed("admin-audit", { element: "audit", nav: "admin-audit" });
  }
  if (hash === "admin/export" || hash === "admin-export") {
    return parsed("admin-export", { element: "export", nav: "admin-export" });
  }
  if (hash === "admin/log" || hash === "admin-log") {
    return parsed("admin-log", { element: "log", nav: "admin-log" });
  }
  if (hash === "admin/patients" || hash === "admin-patients") {
    return parsed("admin-patients", { element: "patients", nav: "admin-patients" });
  }
  if (hash === "admin/hmo-bills" || hash === "admin-hmo-bills") {
    return parsed("admin-hmo-bills", { element: "hmo-bills", nav: "admin-hmo-bills" });
  }
  if (hash === "admin/certificates" || hash === "admin-certificates") {
    return parsed("admin-certificates", { element: "certificates", nav: "admin-certificates" });
  }

  const parts = hash.split("/").filter(Boolean);
  const head = parts[0];
  const second = parts[1];
  const third = parts[2];

  if (head === "patient-account") {
    if (parts[2] === "invoice" && parts[3]) {
      return parsed("patient-account-invoice");
    }
    if (second) {
      return parsed("patient-account");
    }
    return parsed("unavailable");
  }

  if (head === "accountant") {
    if (second === "patient" && third) {
      return parsed("accountant-patient");
    }
    return parsed("accountant", sectionSpec("accountant", second));
  }

  if (head === "doctor") {
    if (second === "patient" && third) {
      return parsed("consultation");
    }
    return parsed("doctor", sectionSpec("doctor", second));
  }

  if (head === "nursing") {
    if (second === "patient" && third) {
      return parsed("nursing-patient");
    }
    return parsed("nursing", sectionSpec("nursing", second));
  }

  if (head === "laboratory" || head === "lab") {
    if (second === "patient" && third) {
      return parsed("laboratory-patient");
    }
    if ((second === "order" || second === "orders") && third) {
      return parsed("laboratory-order");
    }
    if (second === "external" && third) {
      return parsed("laboratory-external");
    }
    return parsed("laboratory", sectionSpec("laboratory", second));
  }

  if (head === "radiology") {
    if (second === "patient" && third) {
      return parsed("radiology-patient");
    }
    if (second === "order" && third) {
      return parsed("radiology-order");
    }
    if (second === "external" && third) {
      return parsed("radiology-external");
    }
    return parsed("radiology", sectionSpec("radiology", second));
  }

  if (head === "pharmacy") {
    if (second === "patient" && third) {
      return parsed("pharmacy-patient");
    }
    if (second === "prescription" && third) {
      return parsed("pharmacy-prescription");
    }
    if (second === "catalogue" && third === "add") {
      return parsed("pharmacy", { element: "catalogue", nav: "catalogue" });
    }
    return parsed("pharmacy", sectionSpec("pharmacy", second));
  }

  if (head === "admin") {
    if (second === "analytics") {
      return parsed("admin-analytics", { element: "analytics", nav: "admin-analytics" });
    }
    if (second === "audit") {
      return parsed("admin-audit", { element: "audit", nav: "admin-audit" });
    }
    if (second === "export") {
      return parsed("admin-export", { element: "export", nav: "admin-export" });
    }
    if (second === "log") {
      return parsed("admin-log", { element: "log", nav: "admin-log" });
    }
    if (second === "patient" && third) {
      return parsed("admin-patient-record", { element: "patients", nav: "admin-patients" });
    }
    if (second === "patients") {
      return parsed("admin-patients", { element: "patients", nav: "admin-patients" });
    }
    if (second === "hmo-bills") {
      return parsed("admin-hmo-bills", { element: "hmo-bills", nav: "admin-hmo-bills" });
    }
    if (second === "certificates") {
      return parsed("admin-certificates", { element: "certificates", nav: "admin-certificates" });
    }
    return parsed("unavailable");
  }

  if (head === "reception") {
    if (second === "register") {
      return parsed("registration-register", { element: "register", nav: "register" });
    }
    if (second === "families") {
      return parsed("registration-families", { element: "families", nav: "families" });
    }
    if (second === "family" && third) {
      return parsed("registration-family", { element: "families", nav: "families" });
    }
    if (second === "patients" || second === "directory") {
      return parsed("registration-patients", { element: "patients", nav: "patients" });
    }
    if (second === "record" && third) {
      return parsed("registration-patient-record", { element: "patients", nav: "patients" });
    }
    if (second === "visit") {
      return parsed("registration-visit", { element: "create-visit", nav: "create-visit" });
    }
    if (second === "antenatal" || second === "anc") {
      if (third === "register" || third === "new") {
        return parsed("registration-antenatal-register", { element: "antenatal", nav: "antenatal" });
      }
      return parsed("registration-antenatal", { element: "antenatal", nav: "antenatal" });
    }
    if (second === "patient" && third) {
      return parsed("registration-patient");
    }
    if (second === "account" && third) {
      if (parts[3] === "invoice" && parts[4]) {
        return parsed("patient-account-invoice");
      }
      return parsed("patient-account");
    }
    return parsed("registration-desk", sectionSpec("reception", second));
  }

  if (head === "registration-desk") {
    if (second === "patients" || second === "directory") {
      return parsed("registration-patients", { element: "patients", nav: "patients" });
    }
    return parsed(
      "registration-desk",
      sectionSpec("reception", second) ?? sectionSpec("registration-desk", second),
    );
  }

  if (head === "registration") {
    if (second === "register") {
      return parsed("registration-register", { element: "register", nav: "register" });
    }
    if (second === "families") {
      return parsed("registration-families", { element: "families", nav: "families" });
    }
    if (second === "family" && third) {
      return parsed("registration-family", { element: "families", nav: "families" });
    }
    if (second === "patients" || second === "directory") {
      return parsed("registration-patients", { element: "patients", nav: "patients" });
    }
    if (second === "record" && third) {
      return parsed("registration-patient-record", { element: "patients", nav: "patients" });
    }
    if (second === "visit") {
      return parsed("registration-visit", { element: "create-visit", nav: "create-visit" });
    }
    if (second === "antenatal" || second === "anc") {
      if (third === "register" || third === "new") {
        return parsed("registration-antenatal-register", { element: "antenatal", nav: "antenatal" });
      }
      return parsed("registration-antenatal", { element: "antenatal", nav: "antenatal" });
    }
    if (second === "patient" && third) {
      return parsed("registration-patient");
    }
    return parsed(
      "registration-desk",
      sectionSpec("reception", second) ?? sectionSpec("registration-desk", second),
    );
  }

  return parsed("unavailable");
}

export function readShellRoute(): ShellRoute {
  return parseShellHash(window.location.hash).route;
}

export function readHashSection(): string | null {
  return parseShellHash(window.location.hash).section;
}

export function readHashNavItemId(): string | null {
  return parseShellHash(window.location.hash).navItemId;
}

export function consultationHref(patientUuid: string, visitUuid?: string | null): string {
  const patient = encodeURIComponent(patientUuid);
  if (!visitUuid) {
    return `#/doctor/patient/${patient}`;
  }
  return `#/doctor/patient/${patient}/visit/${encodeURIComponent(visitUuid)}`;
}

export function readConsultationPatientUuid(rawHash = window.location.hash): string | null {
  const match = rawHash.match(/doctor\/patient\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function readConsultationVisitUuid(rawHash = window.location.hash): string | null {
  const match = rawHash.match(/doctor\/patient\/[^/?#]+\/visit\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function shellRouteHref(route: ShellRoute): string {
  if (route === "unavailable") {
    return "";
  }
  if (route === "home") return "#/home";
  if (route === "messages") return "#/messages";
  if (route === "system-settings") return "#/system-settings";
  if (route === "consultation") return "#/doctor";
  if (route === "nursing-patient") return "#/nursing";
  if (
    route === "laboratory-patient" ||
    route === "laboratory-order" ||
    route === "laboratory-external"
  ) {
    return "#/laboratory";
  }
  if (
    route === "radiology-patient" ||
    route === "radiology-order" ||
    route === "radiology-external"
  ) {
    return "#/radiology";
  }
  if (route === "pharmacy-patient" || route === "pharmacy-prescription") return "#/pharmacy";
  if (route === "registration-patients" || route === "registration-patient-record") {
    return "#/reception/patients";
  }
  if (route === "registration-families" || route === "registration-family") {
    return "#/reception/families";
  }
  if (route === "admin-patients" || route === "admin-patient-record") return "#/admin/patients";
  if (
    route === "registration-desk" ||
    route === "registration-patient" ||
    route === "registration-register" ||
    route === "registration-visit" ||
    route === "registration-antenatal"
  ) {
    return "#/reception";
  }
  if (route === "patient-account" || route === "patient-account-invoice") return "#/home";
  if (route === "accountant-patient") return "#/accountant";
  if (route === "admin-analytics") return "#/admin/analytics";
  if (route === "admin-audit") return "#/admin/audit";
  if (route === "admin-export") return "#/admin/export";
  if (route === "admin-log") return "#/admin/log";
  if (route === "admin-hmo-bills") return "#/admin/hmo-bills";
  if (route === "admin-certificates") return "#/admin/certificates";
  return `#/${route}`;
}

export function setShellRoute(route: ShellRoute): void {
  const next = shellRouteHref(route);
  if (!next || window.location.hash === next) {
    return;
  }
  window.location.hash = next;
}

export function openConsultation(patientUuid: string, visitUuid?: string | null): void {
  window.location.hash = consultationHref(patientUuid, visitUuid);
}

export function readNursingPatientUuid(): string | null {
  const match = window.location.hash.match(/nursing\/patient\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function readNursingTreatmentVisitUuid(): string | null {
  const match = window.location.hash.match(/nursing\/patient\/[^/?#]+\/treatment\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openNursingPatient(patientUuid: string): void {
  window.location.hash = `#/nursing/patient/${patientUuid}`;
}

export function openNursingTreatmentVisit(patientUuid: string, visitUuid: string): void {
  window.location.hash = `#/nursing/patient/${encodeURIComponent(patientUuid)}/treatment/${encodeURIComponent(visitUuid)}`;
}

export function openNursingSection(section?: string): void {
  window.location.hash = section ? `#/nursing/${section}` : "#/nursing";
}

export function readLaboratoryPatientUuid(): string | null {
  const match = window.location.hash.match(/(?:laboratory|lab)\/patient\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openLaboratoryPatient(patientUuid: string): void {
  window.location.hash = `#/laboratory/patient/${patientUuid}`;
}

export function readLaboratoryOrderUuid(): string | null {
  const match = window.location.hash.match(/(?:laboratory|lab)\/orders?\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openLaboratoryOrder(
  orderUuid: string,
  patientUuid?: string,
  visitUuid?: string,
): void {
  const selected = orderUuid.trim();
  if (!selected) {
    return;
  }
  const patient = (patientUuid || "").trim();
  const visit = (visitUuid || "").trim();
  if (patient) {
    const query = new URLSearchParams({ patient });
    if (visit) {
      query.set("visit", visit);
    }
    window.location.hash = `#/laboratory/order/${encodeURIComponent(selected)}?${query.toString()}`;
    return;
  }
  window.location.hash = `#/laboratory/order/${encodeURIComponent(selected)}`;
}

export function readLaboratoryOrderExpectedIdentity(): {
  patientUuid: string;
  visitUuid: string;
} | null {
  const query = window.location.hash.split("?")[1] || "";
  const params = new URLSearchParams(query);
  const patientUuid = (params.get("patient") || "").trim();
  const visitUuid = (params.get("visit") || "").trim();
  if (!patientUuid) {
    return null;
  }
  return { patientUuid, visitUuid };
}

export function openLaboratoryWorklistOrder(input: {
  orderUuid: string;
  patientUuid: string;
  visitUuid: string;
}): void {
  const orderUuid = input.orderUuid.trim();
  const patientUuid = input.patientUuid.trim();
  const visitUuid = input.visitUuid.trim();
  if (!orderUuid || !patientUuid || !visitUuid) {
    return;
  }
  openLaboratoryOrder(orderUuid, patientUuid, visitUuid);
}

export function openLaboratorySection(section?: string): void {
  window.location.hash = section ? `#/laboratory/${section}` : "#/laboratory";
}

export function readLaboratoryExternalId(): string | null {
  const match = window.location.hash.match(/(?:laboratory|lab)\/external\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openLaboratoryExternalPatient(externalId: string): void {
  const id = externalId.trim();
  if (!id) {
    return;
  }
  window.location.hash = `#/laboratory/external/${encodeURIComponent(id)}`;
}

export function readRadiologyPatientUuid(): string | null {
  const match = window.location.hash.match(/radiology\/patient\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openRadiologyPatient(patientUuid: string): void {
  window.location.hash = `#/radiology/patient/${patientUuid}`;
}

export function readRadiologyOrderUuid(): string | null {
  const match = window.location.hash.match(/radiology\/order\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openRadiologyOrder(orderUuid: string): void {
  window.location.hash = `#/radiology/order/${orderUuid}`;
}

export function readRadiologyOrderExpectedIdentity(): {
  patientUuid: string;
  visitUuid: string;
} | null {
  const query = window.location.hash.split("?")[1] || "";
  const params = new URLSearchParams(query);
  const patientUuid = (params.get("patient") || "").trim();
  const visitUuid = (params.get("visit") || "").trim();
  if (!patientUuid || !visitUuid) {
    return null;
  }
  return { patientUuid, visitUuid };
}

export function openRadiologyWorklistOrder(input: {
  orderUuid: string;
  patientUuid: string;
  visitUuid: string;
}): void {
  const orderUuid = input.orderUuid.trim();
  const patientUuid = input.patientUuid.trim();
  const visitUuid = input.visitUuid.trim();
  if (!orderUuid || !patientUuid || !visitUuid) {
    return;
  }
  const query = new URLSearchParams({ patient: patientUuid, visit: visitUuid });
  window.location.hash = `#/radiology/order/${encodeURIComponent(orderUuid)}?${query.toString()}`;
}

export function readRadiologyExternalStudyId(): string | null {
  const match = window.location.hash.match(/radiology\/external\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openRadiologyExternalStudy(studyId: string): void {
  const id = studyId.trim();
  if (!id) {
    return;
  }
  window.location.hash = `#/radiology/external/${encodeURIComponent(id)}`;
}

export function openRadiologySection(section?: string): void {
  window.location.hash = section ? `#/radiology/${section}` : "#/radiology";
}

export function readPharmacyPatientUuid(): string | null {
  const match = window.location.hash.match(/pharmacy\/patient\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openPharmacyPatient(patientUuid: string): void {
  window.location.hash = `#/pharmacy/patient/${patientUuid}`;
}

export function readPharmacyPrescriptionUuid(): string | null {
  const match = window.location.hash.match(/pharmacy\/prescription\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openPharmacyPrescription(orderUuid: string): void {
  window.location.hash = `#/pharmacy/prescription/${orderUuid}`;
}

export function openPharmacySection(section?: string): void {
  window.location.hash = section ? `#/pharmacy/${section}` : "#/pharmacy";
}

const SCREEN_HISTORY: string[] = [];
let restoringScreen = false;

function screenHash(hash: string): string {
  const text = hash.trim();
  if (!text || text === "#" || text === "#/") {
    return "";
  }
  return text.startsWith("#") ? text : `#${text}`;
}

/** Remember the screen staff are looking at, so Back can return to it. */
export function rememberScreen(hash = typeof window === "undefined" ? "" : window.location.hash): void {
  const next = screenHash(hash);
  if (!next) {
    return;
  }
  if (restoringScreen) {
    restoringScreen = false;
    if (SCREEN_HISTORY[SCREEN_HISTORY.length - 1] !== next) {
      SCREEN_HISTORY.push(next);
    }
    return;
  }
  if (SCREEN_HISTORY[SCREEN_HISTORY.length - 1] === next) {
    return;
  }
  SCREEN_HISTORY.push(next);
  if (SCREEN_HISTORY.length > 50) {
    SCREEN_HISTORY.shift();
  }
}

/** Go back to the previous screen. Use the fallback only when there is nowhere to return. */
export function returnToPreviousScreen(fallback: string): void {
  const here = screenHash(typeof window === "undefined" ? "" : window.location.hash);
  while (SCREEN_HISTORY.length > 0 && SCREEN_HISTORY[SCREEN_HISTORY.length - 1] === here) {
    SCREEN_HISTORY.pop();
  }
  const previous = SCREEN_HISTORY[SCREEN_HISTORY.length - 1] || screenHash(fallback) || "#/home";
  if (typeof window === "undefined") {
    return;
  }
  if (window.location.hash === previous) {
    restoringScreen = false;
    return;
  }
  restoringScreen = true;
  window.location.hash = previous;
}

export function resetScreenHistoryForTests(hashes: string[] = []): void {
  SCREEN_HISTORY.length = 0;
  SCREEN_HISTORY.push(...hashes);
  restoringScreen = false;
}

/**
 * Return to the previous Pharmacy screen.
 * Falls back to a Pharmacy section when this is the first screen opened.
 */
export function backWithinPharmacy(fallbackSection?: string): void {
  returnToPreviousScreen(fallbackSection ? `#/pharmacy/${fallbackSection}` : "#/pharmacy");
}

export function openPharmacyCatalogueAdd(): void {
  window.location.hash = "#/pharmacy/catalogue/add";
}

export function pharmacyCatalogueAddRequested(
  rawHash = typeof window === "undefined" ? "" : window.location.hash,
): boolean {
  const hash = rawHash.replace(/^#\/?/, "").replace(/[?#].*$/, "").replace(/\/+$/, "");
  return hash === "pharmacy/catalogue/add" || hash === "pharmacy/add-medicine";
}

export function patientAccountHref(patientUuid: string, visitUuid?: string | null): string {
  const patient = encodeURIComponent(patientUuid);
  if (!visitUuid) {
    return `#/patient-account/${patient}`;
  }
  return `#/patient-account/${patient}/visit/${encodeURIComponent(visitUuid)}`;
}

export function readPatientAccountUuid(rawHash = window.location.hash): string | null {
  const match = rawHash.match(/(?:patient-account|reception\/account)\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function readPatientAccountVisitUuid(rawHash = window.location.hash): string | null {
  const match = rawHash.match(
    /(?:patient-account|reception\/account)\/[^/?#]+\/visit\/([^/?#]+)/,
  );
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function readPatientAccountInvoiceId(rawHash = window.location.hash): string | null {
  const match = rawHash.match(
    /(?:patient-account|reception\/account)\/[^/]+\/invoice\/([^/?#]+)/,
  );
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openPatientAccount(patientUuid: string, visitUuid?: string | null): void {
  window.location.hash = patientAccountHref(patientUuid, visitUuid);
}

export function openPatientAccountInvoice(patientUuid: string, invoiceId: string | number): void {
  window.location.hash = `${patientAccountHref(patientUuid)}/invoice/${invoiceId}`;
}

export function openAccountantPatient(patientUuid: string): void {
  window.location.hash = `#/accountant/patient/${patientUuid}`;
}

export function readAccountantPatientUuid(): string | null {
  const match = window.location.hash.match(/accountant\/patient\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function readRegistrationPatientUuid(): string | null {
  const match = window.location.hash.match(
    /(?:reception|registration)\/patient\/([^/?#]+)/,
  );
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openRegistrationPatient(patientUuid: string): void {
  window.location.hash = `#/reception/patient/${patientUuid}`;
}

export function readPatientRecordUuid(rawHash = window.location.hash): string | null {
  const match = rawHash.match(/(?:reception|registration)\/record\/([^/?#]+)|admin\/patient\/([^/?#]+)/);
  const uuid = match?.[1] || match?.[2] || "";
  return uuid ? decodeURIComponent(uuid) : null;
}

export function openPatientRecord(
  patientUuid: string,
  workplace: "reception" | "administration",
): void {
  const patient = encodeURIComponent(patientUuid);
  window.location.hash =
    workplace === "administration" ? `#/admin/patient/${patient}` : `#/reception/record/${patient}`;
}

export function openCreateVisit(patientUuid?: string): void {
  window.location.hash = patientUuid
    ? `#/reception/visit/${patientUuid}`
    : "#/reception/visit";
}

export function readCreateVisitPatientUuid(): string | null {
  const match = window.location.hash.match(
    /(?:reception|registration)\/visit\/([^/?#]+)/,
  );
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openAntenatalRegistration(patientUuid?: string): void {
  window.location.hash = patientUuid
    ? `#/reception/antenatal/${encodeURIComponent(patientUuid)}`
    : "#/reception/antenatal";
}

/** New hospital patient who came for antenatal care — not the general Register Patient screen. */
export function openAntenatalPatientRegister(): void {
  window.location.hash = "#/reception/antenatal/register";
}

export function readAntenatalPatientUuid(rawHash = window.location.hash): string | null {
  const match = rawHash.match(/(?:reception|registration)\/(?:antenatal|anc)\/([^/?#]+)/);
  const value = match?.[1] ? decodeURIComponent(match[1]) : null;
  if (!value || value === "register" || value === "new") {
    return null;
  }
  return value;
}

export function openRegistrationRegister(patientUuid?: string, familyId?: string): void {
  if (patientUuid) {
    window.location.hash = `#/reception/register/${patientUuid}`;
    return;
  }
  if (familyId) {
    window.location.hash = `#/reception/register?family=${encodeURIComponent(familyId)}`;
    return;
  }
  window.location.hash = "#/reception/register";
}

export function readRegistrationFamilyId(rawHash = window.location.hash): string | null {
  const query = rawHash.split("?")[1] || "";
  return new URLSearchParams(query).get("family")?.trim() || null;
}

export function readReceptionFamilyId(rawHash = window.location.hash): string | null {
  const match = rawHash.match(/(?:reception|registration)\/family\/([^/?#]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export function openReceptionFamily(familyId: string): void {
  window.location.hash = `#/reception/family/${encodeURIComponent(familyId)}`;
}

export function openReceptionFamilies(): void {
  window.location.hash = "#/reception/families";
}

export function readRegistrationEditUuid(): string | null {
  const match = window.location.hash.match(
    /(?:reception|registration)\/register\/([^/?#]+)/,
  );
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}
