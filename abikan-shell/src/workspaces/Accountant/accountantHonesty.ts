import type { PatientAccountInvoice, PatientAccountMoney, PatientAccountPayload } from "../../types/patientAccount";

export const MIXED_CURRENCY_MESSAGE = "Select invoices in the same currency.";

export const PROTECTED_TEST_ORDERS = [
  "ORD-6",
  "ORD-14",
  "ORD-15",
  "ORD-16",
  "ORD-17",
  "ORD-18",
  "ORD-19",
  "ORD-20",
  "ORD-21",
] as const;

export const PROTECTED_TEST_INVOICES = [
  "INV/2026/00006",
  "INV/2026/00031",
  "INV/2026/00032",
  "INV/2026/00033",
  "INV/2026/00034",
  "INV/2026/00035",
] as const;

export function invoiceCurrencyCode(invoice: Pick<PatientAccountInvoice, "outstanding" | "total">): string {
  return invoice.outstanding.currencyCode || invoice.total.currencyCode || "";
}

export function selectionIsSameCurrency(
  invoices: Array<Pick<PatientAccountInvoice, "outstanding" | "total">>,
): boolean {
  const codes = new Set(invoices.map(invoiceCurrencyCode).filter(Boolean));
  return codes.size <= 1;
}

export function isReversedInvoice(invoice: Pick<PatientAccountInvoice, "paymentState" | "paymentStateLabel">): boolean {
  return invoice.paymentState === "reversed" || invoice.paymentStateLabel === "REVERSED";
}

export function moneyMinor(value: number | string, places = 2): number {
  let text = String(value ?? "").trim();
  if (!text) {
    return 0;
  }
  if (/[eE]/.test(text)) {
    const numeric = Number(text);
    if (!Number.isFinite(numeric)) {
      return 0;
    }
    text = numeric.toFixed(Math.max(places + 8, 12));
  }
  const negative = text.startsWith("-");
  if (negative || text.startsWith("+")) {
    text = text.slice(1);
  }
  if (!/^\d+(\.\d+)?$/.test(text)) {
    const numeric = Number(text);
    if (!Number.isFinite(numeric)) {
      return 0;
    }
    return moneyMinor(numeric.toFixed(Math.max(places + 8, 12)), places);
  }
  const [whole, frac = ""] = text.split(".");
  const digits = `${frac}${"0".repeat(places + 1)}`.slice(0, places + 1);
  const keep = digits.slice(0, places);
  const next = Number(digits[places] || "0");
  let minor = Number(whole) * 10 ** places + Number(keep || "0");
  if (next >= 5) {
    minor += 1;
  }
  return negative ? -minor : minor;
}

export function moneyMajor(minor: number, places = 2): number {
  return minor / 10 ** places;
}

export type PaymentAmountCheck =
  | { ok: true; amount: number; remaining: number }
  | { ok: false; code: "invalid" | "overpay" | "already_paid"; message: string };

export type DiscountPercentageCheck =
  | { ok: true; percentage: number; amount: number }
  | { ok: false; message: string };

export function checkDiscountPercentage(
  input: string,
  due: number,
  places = 2,
): DiscountPercentageCheck {
  const trimmed = input.trim();
  if (!trimmed) {
    return { ok: true, percentage: 0, amount: 0 };
  }
  if (!Number.isFinite(Number(trimmed))) {
    return { ok: false, message: "Enter a valid discount amount." };
  }
  const percentage = Number(trimmed);
  if (percentage < 0) {
    return { ok: false, message: "Discount percentage cannot be negative." };
  }
  if (percentage > 100) {
    return { ok: false, message: "Discount percentage cannot be more than 100%." };
  }
  const dueMinor = moneyMinor(due, places);
  const amountMinor = Math.round((dueMinor * percentage) / 100);
  return {
    ok: true,
    percentage,
    amount: moneyMajor(amountMinor, places),
  };
}

export function checkPaymentAmount(
  input: string,
  due: number,
  places = 2,
): PaymentAmountCheck {
  const trimmed = input.trim();
  if (!trimmed) {
    return { ok: false, code: "invalid", message: "Enter the payment amount." };
  }
  const amountMinor = moneyMinor(trimmed, places);
  const dueMinor = moneyMinor(due, places);
  if (dueMinor <= 0) {
    return { ok: false, code: "already_paid", message: "This bill is already fully paid." };
  }
  if (amountMinor <= 0) {
    return { ok: false, code: "invalid", message: "Payment amount must be greater than zero." };
  }
  if (amountMinor > dueMinor) {
    return { ok: false, code: "overpay", message: "You cannot take more than the amount due." };
  }
  return {
    ok: true,
    amount: moneyMajor(amountMinor, places),
    remaining: moneyMajor(dueMinor - amountMinor, places),
  };
}

export function isPayableInvoice(invoice: PatientAccountInvoice): boolean {
  const places = invoice.outstanding.decimalPlaces ?? 2;
  return (
    invoice.state === "posted" &&
    moneyMinor(invoice.outstanding.amount, places) > 0 &&
    (invoice.paymentState === "not_paid" || invoice.paymentState === "partial") &&
    !isReversedInvoice(invoice)
  );
}

export function selectedOutstandingTotal(invoices: PatientAccountInvoice[]): number {
  if (!selectionIsSameCurrency(invoices) || invoices.length === 0) {
    return 0;
  }
  const places = invoices[0]?.outstanding.decimalPlaces ?? 2;
  const minor = invoices.reduce(
    (sum, invoice) => sum + moneyMinor(invoice.outstanding.amount, places),
    0,
  );
  return moneyMajor(minor, places);
}

export function formatMoneyAmount(amount: number, sample: PatientAccountMoney): string {
  const places = sample.decimalPlaces ?? 2;
  const number = amount.toLocaleString("en-US", {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  });
  const symbol = sample.currencySymbol || "";
  const code = sample.currencyCode || "";
  // Naira always shows ₦ before the amount.
  if (code === "NGN" || symbol === "₦") {
    return `₦${number}`;
  }
  if (symbol && sample.formatted.endsWith(symbol)) {
    return `${number} ${symbol}`;
  }
  if (symbol) {
    return `${symbol}${number}`;
  }
  return `${number} ${code}`.trim();
}

export function paymentStateDisplay(state: string | null | undefined): string {
  switch (state) {
    case "not_paid":
      return "UNPAID";
    case "partial":
      return "PARTIALLY PAID";
    case "in_payment":
      return "PAYMENT PROCESSING / IN PAYMENT";
    case "paid":
      return "PAID";
    case "reversed":
      return "REVERSED";
    default:
      return (state || "UNPAID").replace(/_/g, " ").toUpperCase();
  }
}

export function accountSummaryAmounts(
  summary: PatientAccountPayload["summary"] | undefined,
  kind: "outstanding" | "paid" | "billed",
): PatientAccountMoney[] {
  if (!summary) {
    return [];
  }
  if (kind === "outstanding") {
    return summary.outstandingByCurrency ?? [];
  }
  if (kind === "paid") {
    return summary.paidByCurrency ?? [];
  }
  return summary.billedByCurrency ?? [];
}

export function mixedCurrencyTotalsAreHonest(amounts: PatientAccountMoney[]): boolean {
  const codes = amounts.map((item) => item.currencyCode).filter(Boolean);
  return new Set(codes).size === codes.length;
}
