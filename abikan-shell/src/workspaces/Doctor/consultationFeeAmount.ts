export const CONSULTATION_FEE_CURRENCY = "NGN";
export const CONSULTATION_FEE_SYMBOL = "₦";
export const MAX_CONSULTATION_AMOUNT = 10_000_000;

export type ConsultationAmountOk = { ok: true; amount: number };
export type ConsultationAmountError = { ok: false; code: string; message: string };
export type ConsultationAmountResult = ConsultationAmountOk | ConsultationAmountError;

const REQUIRED = "Enter the consultation fee in naira.";
const INVALID = "Enter a valid consultation fee in naira.";
const POSITIVE = "Consultation fee must be greater than zero.";

function reject(code: string, message: string): ConsultationAmountError {
  return { ok: false, code, message };
}

export function parseConsultationAmount(value: unknown): ConsultationAmountResult {
  if (value === null || value === undefined) {
    return reject("amount_required", REQUIRED);
  }
  if (typeof value === "boolean") {
    return reject("amount_invalid", INVALID);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      return reject("amount_invalid", INVALID);
    }
    return finish(value);
  }
  if (typeof value !== "string") {
    return reject("amount_invalid", INVALID);
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return reject("amount_required", REQUIRED);
  }
  if (/[$€£]|USD|EUR|GBP/i.test(trimmed)) {
    return reject("amount_invalid", INVALID);
  }
  const withoutLabel = trimmed.replace(/^(NGN|₦)\s*/i, "");
  if (/[^\d,.\s]/.test(withoutLabel)) {
    return reject("amount_invalid", INVALID);
  }
  const compact = withoutLabel.replace(/[,\s]/g, "");
  if (!/^\d+(\.\d+)?$/.test(compact)) {
    return reject("amount_invalid", INVALID);
  }
  const amount = Number(compact);
  if (!Number.isFinite(amount)) {
    return reject("amount_invalid", INVALID);
  }
  return finish(amount);
}

function finish(amount: number): ConsultationAmountResult {
  if (amount <= 0) {
    return reject("amount_invalid", POSITIVE);
  }
  if (amount > MAX_CONSULTATION_AMOUNT) {
    return reject("amount_invalid", INVALID);
  }
  return { ok: true, amount: Math.round(amount * 100) / 100 };
}

export function formatConsultationAmountNgn(amount: number): string {
  return `${CONSULTATION_FEE_SYMBOL}${amount.toLocaleString("en-NG", {
    minimumFractionDigits: amount % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  })}`;
}
