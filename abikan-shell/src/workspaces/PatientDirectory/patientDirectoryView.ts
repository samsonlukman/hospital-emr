import type { PatientDirectoryPageSize, PatientRecord } from "../../types/patientDirectory";

export const PATIENT_PAGE_SIZES: PatientDirectoryPageSize[] = [50, 100];

export function parsePatientPageSize(value: string | number): PatientDirectoryPageSize {
  return Number(value) === 100 ? 100 : 50;
}

export function patientPageRange(startIndex: number, count: number, total: number): string {
  if (total <= 0 || count <= 0) {
    return "No patients on this page";
  }
  const start = startIndex + 1;
  const end = startIndex + count;
  return `${formatPatientCount(start)}–${formatPatientCount(end)} of ${formatPatientCount(total)}`;
}

export function formatPatientCount(value: number): string {
  return value.toLocaleString("en-NG");
}

export function displayPatientField(value: string): string {
  return value.trim() || "—";
}

const SEX_LABELS: Record<string, string> = { M: "Male", F: "Female", O: "Other" };
const PHONE_KEYS = ["phoneNumber", "primaryContact", "Phone", "phone"];
const ADDRESS_LABELS: Array<[string, string]> = [
  ["address1", "Address"],
  ["address2", "Area / landmark"],
  ["cityVillage", "City / town"],
  ["stateProvince", "State"],
  ["countyDistrict", "Local government area"],
  ["postalCode", "Postal code"],
  ["country", "Country"],
];

export function patientFullName(record: PatientRecord): string {
  return [record.givenName, record.middleName, record.familyName]
    .map((part) => part.trim())
    .filter(Boolean)
    .join(" ");
}

export function patientSexLabel(value: string): string {
  const key = value.trim().toUpperCase();
  return SEX_LABELS[key] || value.trim();
}

export function formatPatientDate(value: string): string {
  const text = value.trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return "";
  }
  const [year, month, day] = text.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return `${date.getUTCDate()} ${date.toLocaleString("en-GB", { month: "short", timeZone: "UTC" })} ${year}`;
}

/** Date of death for staff display: DD/MM/YYYY. */
export function formatDeathDate(value: string): string {
  const text = value.trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return "";
  }
  const [year, month, day] = text.split("-");
  return `${day}/${month}/${year}`;
}

export function patientStatusLabel(alive: boolean): "Alive" | "Dead" {
  return alive ? "Alive" : "Dead";
}

export function patientAliveLabel(alive: boolean | "Yes" | "No" | undefined): "Yes" | "No" {
  if (alive === "Yes" || alive === true) {
    return "Yes";
  }
  if (alive === "No" || alive === false) {
    return "No";
  }
  return "Yes";
}

export function patientPhone(record: PatientRecord): string {
  for (const key of PHONE_KEYS) {
    const match = Object.entries(record.attributes).find(
      ([name, value]) => name.toLowerCase() === key.toLowerCase() && value.trim(),
    );
    if (match) {
      return match[1].trim();
    }
  }
  return "";
}

export function patientAddressLines(record: PatientRecord): Array<{ label: string; value: string }> {
  return ADDRESS_LABELS.flatMap(([key, label]) => {
    const value = (record.address[key] || "").trim();
    return value ? [{ label, value }] : [];
  });
}

export function patientOtherIdentifiers(record: PatientRecord): Array<{ label: string; value: string }> {
  return record.identifiers
    .filter((item) => item.identifier.trim() && !item.type.toLowerCase().includes("openmrs"))
    .filter((item) => !item.preferred && item.identifier !== record.identifier)
    .map((item) => ({
      label: item.type === "Old Identification Number" ? "Previous hospital number" : item.type,
      value: item.identifier,
    }));
}
