type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger";

export function departmentDisplay(name: string | null | undefined): string {
  if (!name || name === "Department not identified") {
    return "—";
  }
  return name;
}

export function journalDisplay(name: string | null | undefined, code?: string | null): string {
  const raw = (name || "").trim();
  if (!raw) {
    return "—";
  }
  const withoutCode = raw.replace(/\s*\([^)]+\)\s*$/, "").trim();
  if (code && withoutCode.toLowerCase() === code.toLowerCase()) {
    return raw;
  }
  return withoutCode || raw;
}

export function paymentStateTone(label: string): BadgeTone {
  const value = label.toUpperCase();
  if (value.includes("WAIVED")) {
    return "info";
  }
  if (value.includes("REVERSED")) {
    return "warning";
  }
  if (value.includes("PARTIALLY")) {
    return "warning";
  }
  if (value.includes("PROCESSING") || value.includes("IN PAYMENT")) {
    return "info";
  }
  if (value === "PAID") {
    return "success";
  }
  if (value === "UNPAID" || value === "UNBILLED" || value === "OUTSTANDING") {
    return "danger";
  }
  return "neutral";
}

export function pharmacyStaffPaymentLabel(label: string): string {
  const value = label.toUpperCase();
  if (value.includes("REVERSED")) {
    return "REVERSED";
  }
  if (value.includes("PARTIAL")) {
    return "PARTIALLY PAID";
  }
  if (value.includes("PAID") || value.includes("IN PAYMENT") || value.includes("PROCESSING")) {
    return "PAID";
  }
  if (value.includes("UNPAID") || value.includes("UNBILLED") || value.includes("OUTSTANDING")) {
    return "UNPAID";
  }
  return label || "UNPAID";
}

export function pharmacyStatusTone(label: string): BadgeTone {
  if (label === "DISPENSED" || label === "PAID" || label === "REFUNDED" || label === "Refunded") {
    return "success";
  }
  if (
    label === "Partially Refunded" ||
    label === "PARTIALLY REFUNDED" ||
    label === "PARTIALLY DISPENSED" ||
    label === "PARTIALLY PAID"
  ) {
    return "warning";
  }
  if (label === "READY TO DISPENSE") {
    return "info";
  }
  if (label === "NOT IN PHARMACY" || label === "NOT BILLED") {
    return "warning";
  }
  if (label === "UNPAID") {
    return "danger";
  }
  return "neutral";
}
