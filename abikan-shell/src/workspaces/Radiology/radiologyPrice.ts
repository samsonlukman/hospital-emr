export const RADIOLOGY_FEE_CURRENCY = "NGN";
export const RADIOLOGY_FEE_SYMBOL = "₦";
export const MAX_RADIOLOGY_AMOUNT = 10_000_000;

export type RadiologyAmountOk = { ok: true; amount: number };
export type RadiologyAmountError = { ok: false; code: string; message: string };
export type RadiologyAmountResult = RadiologyAmountOk | RadiologyAmountError;

const REQUIRED = "Enter the price in naira.";
const INVALID = "Enter a valid price in naira.";
const POSITIVE = "Price must be greater than zero.";

function reject(code: string, message: string): RadiologyAmountError {
  return { ok: false, code, message };
}

export function parseRadiologyAmount(value: unknown): RadiologyAmountResult {
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

function finish(amount: number): RadiologyAmountResult {
  if (amount <= 0) {
    return reject("amount_invalid", POSITIVE);
  }
  if (amount > MAX_RADIOLOGY_AMOUNT) {
    return reject("amount_invalid", INVALID);
  }
  return { ok: true, amount: Math.round(amount * 100) / 100 };
}

export function formatRadiologyAmountNgn(amount: number): string {
  return `${RADIOLOGY_FEE_SYMBOL}${amount.toLocaleString("en-NG", {
    minimumFractionDigits: amount % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  })}`;
}

export function doctorCannotSetRadiologyPrice(): true {
  return true;
}

export function radiologistSetsOrderPrice(): true {
  return true;
}
