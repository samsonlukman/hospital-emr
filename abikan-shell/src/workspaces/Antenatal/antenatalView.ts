import { RECEPTION_VISIT_TYPE_COPY } from "../../config/receptionVisitTypes.ts";

/** Default one-time antenatal registration fee in Nigerian naira. */
export const ANC_DEFAULT_FEE_AMOUNT = 2000;

export const ANC_FEE_SYMBOL = "₦";

export const ANC_VISIT_TYPE_NAME = "ANC";

export function isAncVisitType(name: string | undefined | null): boolean {
  return (name || "").trim().toUpperCase() === ANC_VISIT_TYPE_NAME;
}

export function shouldShowAncTab(hasAnc: boolean | undefined | null): boolean {
  return Boolean(hasAnc);
}

/** ANC visits are only offered after antenatal enrollment for this pregnancy. */
export function canOfferAncVisitType(enrolled: boolean | undefined | null): boolean {
  return Boolean(enrolled);
}

export function ancVisitTypeLabel(): string {
  return RECEPTION_VISIT_TYPE_COPY.ANC?.label || "Antenatal Care (ANC)";
}

export function ancNotEnrolledAlertTitle(): string {
  return "Antenatal registration required";
}

export function ancNotEnrolledAlertCopy(): string {
  return "Open Antenatal Care first. Create the ANC card and fee there. Starting an ANC visit is a separate step.";
}

export function formatBloodPressure(
  systolic: number | string | null | undefined,
  diastolic: number | string | null | undefined,
): string {
  const sys = formatMeasurement(systolic);
  const dia = formatMeasurement(diastolic);
  if (!sys && !dia) {
    return "—";
  }
  if (sys && dia) {
    return `${sys}/${dia}`;
  }
  return sys || dia || "—";
}

export function formatMeasurement(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : "";
  }
  return String(value).trim();
}

export function formatAncFeeAmount(amount: number): string {
  return `${ANC_FEE_SYMBOL}${amount.toLocaleString("en-NG", {
    minimumFractionDigits: amount % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  })}`;
}

export function defaultAncFeeInput(defaultAmount?: number | null): string {
  const amount =
    typeof defaultAmount === "number" && Number.isFinite(defaultAmount) && defaultAmount > 0
      ? defaultAmount
      : ANC_DEFAULT_FEE_AMOUNT;
  return String(Math.round(amount * 100) / 100);
}

export type AncFeeAmountOk = { ok: true; amount: number };
export type AncFeeAmountError = { ok: false; message: string };
export type AncFeeAmountResult = AncFeeAmountOk | AncFeeAmountError;

export function parseAncFeeAmount(value: unknown): AncFeeAmountResult {
  if (value === null || value === undefined) {
    return { ok: false, message: "Enter the antenatal registration fee in naira." };
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value) || value <= 0) {
      return { ok: false, message: "Enter a valid antenatal registration fee in naira." };
    }
    return { ok: true, amount: Math.round(value * 100) / 100 };
  }
  if (typeof value !== "string") {
    return { ok: false, message: "Enter a valid antenatal registration fee in naira." };
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return { ok: false, message: "Enter the antenatal registration fee in naira." };
  }
  const withoutLabel = trimmed.replace(/^(NGN|₦)\s*/i, "");
  if (/[^\d,.\s]/.test(withoutLabel)) {
    return { ok: false, message: "Enter a valid antenatal registration fee in naira." };
  }
  const compact = withoutLabel.replace(/[,\s]/g, "");
  if (!/^\d+(\.\d+)?$/.test(compact)) {
    return { ok: false, message: "Enter a valid antenatal registration fee in naira." };
  }
  const amount = Number(compact);
  if (!Number.isFinite(amount) || amount <= 0) {
    return { ok: false, message: "Antenatal registration fee must be greater than zero." };
  }
  return { ok: true, amount: Math.round(amount * 100) / 100 };
}

export function displayAncField(value: number | string | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value);
}

export function shouldOfferNewPregnancy(activePregnancy: { status?: string } | null | undefined): boolean {
  return !activePregnancy || activePregnancy.status !== "active";
}
