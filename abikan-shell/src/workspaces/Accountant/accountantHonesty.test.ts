import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { parseShellHash } from "../../app/hashRoute.ts";
import { ACCOUNTANT_NAV } from "../../config/accountantNav.ts";
import type { PatientAccountInvoice, PatientAccountMoney } from "../../types/patientAccount.ts";
import {
  MIXED_CURRENCY_MESSAGE,
  PROTECTED_TEST_INVOICES,
  PROTECTED_TEST_ORDERS,
  accountSummaryAmounts,
  checkPaymentAmount,
  formatMoneyAmount,
  invoiceCurrencyCode,
  isPayableInvoice,
  isReversedInvoice,
  mixedCurrencyTotalsAreHonest,
  moneyMinor,
  paymentStateDisplay,
  selectedOutstandingTotal,
  selectionIsSameCurrency,
} from "./accountantHonesty.ts";

const CASHIER_SOURCE = readFileSync(
  fileURLToPath(new URL("./AccountantWorkspace.tsx", import.meta.url)),
  "utf8",
);
const COLLECT_SOURCE = readFileSync(
  fileURLToPath(new URL("./AccountantPatientWorkspace.tsx", import.meta.url)),
  "utf8",
);
const ACCOUNTANT_API = readFileSync(
  fileURLToPath(new URL("../../../server/patient-account/accountant.py", import.meta.url)),
  "utf8",
);
const ACCOUNT_API = readFileSync(
  fileURLToPath(new URL("../../../server/patient-account/server.py", import.meta.url)),
  "utf8",
);
const NAV_SOURCE = readFileSync(
  fileURLToPath(new URL("../../config/accountantNav.ts", import.meta.url)),
  "utf8",
);
const MAP_SOURCE = readFileSync(
  fileURLToPath(new URL("../../config/workspaceMap.ts", import.meta.url)),
  "utf8",
);

function money(amount: number, code: string, symbol: string, formatted: string): PatientAccountMoney {
  return {
    amount,
    formatted,
    currencyCode: code,
    currencySymbol: symbol,
    decimalPlaces: 2,
  };
}

function invoice(
  overrides: Partial<PatientAccountInvoice> & { id: number; paymentState: string },
): PatientAccountInvoice {
  const outstanding = overrides.outstanding ?? money(100, "NGN", "₦", "₦100.00");
  const total = overrides.total ?? money(100, "NGN", "₦", "₦100.00");
  return {
    number: `INV/${overrides.id}`,
    date: "2026-08-25",
    department: "Radiology",
    departmentIdentified: true,
    state: "posted",
    paymentStateLabel: paymentStateDisplay(overrides.paymentState),
    origin: "",
    description: "Examination",
    untaxed: total,
    tax: money(0, outstanding.currencyCode, outstanding.currencySymbol, "0.00"),
    hasTax: false,
    paid: money(0, outstanding.currencyCode, outstanding.currencySymbol, "0.00"),
    outstanding,
    total,
    lines: [],
    pharmacyStatus: null,
    ...overrides,
  };
}

describe("mixed-currency totals", () => {
  it("does not treat NGN and USD as one number", () => {
    const amounts = [
      money(20000, "NGN", "₦", "₦20,000.00"),
      money(100, "USD", "$", "$100.00"),
    ];
    assert.equal(mixedCurrencyTotalsAreHonest(amounts), true);
    assert.notEqual(amounts[0]?.formatted.includes("20,100"), true);
    assert.equal(amounts.some((item) => item.formatted.includes("20,100")), false);
    assert.equal(accountSummaryAmounts({
      outstandingByCurrency: amounts,
      paidByCurrency: [],
      billedByCurrency: [],
    }, "outstanding").length, 2);
  });
});

describe("same-currency payment selection", () => {
  const naira = invoice({
    id: 1,
    paymentState: "not_paid",
    outstanding: money(5000, "NGN", "₦", "₦5,000.00"),
    total: money(5000, "NGN", "₦", "₦5,000.00"),
  });
  const dollars = invoice({
    id: 2,
    paymentState: "not_paid",
    outstanding: money(100, "USD", "$", "$100.00"),
    total: money(100, "USD", "$", "$100.00"),
    department: "Accommodation",
  });

  it("allows invoices that share a currency", () => {
    const secondNaira = invoice({
      id: 3,
      paymentState: "partial",
      outstanding: money(10, "NGN", "₦", "₦10.00"),
      total: money(11111, "NGN", "₦", "₦11,111.00"),
    });
    assert.equal(selectionIsSameCurrency([naira, secondNaira]), true);
    assert.equal(selectedOutstandingTotal([naira, secondNaira]), 5010);
    assert.equal(invoiceCurrencyCode(naira), "NGN");
  });

  it("rejects mixed-currency selection before payment", () => {
    assert.equal(selectionIsSameCurrency([naira, dollars]), false);
    assert.equal(selectedOutstandingTotal([naira, dollars]), 0);
    assert.equal(MIXED_CURRENCY_MESSAGE, "Select invoices in the same currency.");
    assert.match(COLLECT_SOURCE, /MIXED_CURRENCY_MESSAGE/);
    assert.match(ACCOUNTANT_API, /mixed_currency/);
    assert.match(ACCOUNTANT_API, /MIXED_CURRENCY_MESSAGE/);
    assert.match(ACCOUNT_API, /Select invoices in the same currency/);
  });

  it("formats the selected due in the invoice currency", () => {
    assert.equal(formatMoneyAmount(5000, naira.outstanding), "₦5,000.00");
  });
});

describe("residual amount and payable invoices", () => {
  it("uses residual, not total, for what remains payable", () => {
    const partial = invoice({
      id: 36,
      paymentState: "partial",
      total: money(11111, "NGN", "₦", "₦11,111.00"),
      outstanding: money(10, "NGN", "₦", "₦10.00"),
    });
    assert.equal(isPayableInvoice(partial), true);
    assert.equal(partial.outstanding.amount, 10);
    assert.notEqual(partial.outstanding.amount, partial.total.amount);
    assert.match(ACCOUNTANT_API, /amount_residual/);
    assert.match(ACCOUNTANT_API, /\("amount_residual", ">", 0\)/);
  });

  it("does not treat a draft invoice as payable", () => {
    const draft = invoice({
      id: 99,
      paymentState: "not_paid",
      state: "draft",
    });
    assert.equal(isPayableInvoice(draft), false);
  });
});

describe("payment-state mapping", () => {
  it("maps unpaid, partial, in payment, paid, and reversed distinctly", () => {
    assert.equal(paymentStateDisplay("not_paid"), "UNPAID");
    assert.equal(paymentStateDisplay("partial"), "PARTIALLY PAID");
    assert.equal(paymentStateDisplay("in_payment"), "PAYMENT PROCESSING / IN PAYMENT");
    assert.equal(paymentStateDisplay("paid"), "PAID");
    assert.equal(paymentStateDisplay("reversed"), "REVERSED");
    assert.match(ACCOUNT_API, /"reversed": "REVERSED"/);
  });

  it("does not call a reversed invoice paid or collectible", () => {
    const reversed = invoice({
      id: 31,
      number: "INV/2026/00031",
      paymentState: "reversed",
      paymentStateLabel: "REVERSED",
      outstanding: money(0, "USD", "$", "$0.00"),
      total: money(15000, "USD", "$", "$15,000.00"),
    });
    assert.equal(isReversedInvoice(reversed), true);
    assert.equal(isPayableInvoice(reversed), false);
    assert.notEqual(reversed.paymentStateLabel, "PAID");
    assert.match(COLLECT_SOURCE, /Reversed bills/);
    assert.equal(COLLECT_SOURCE.includes("Paid and closed bills"), false);
  });

  it("keeps a paid invoice as paid and not collectible", () => {
    const paid = invoice({
      id: 6,
      number: "INV/2026/00006",
      paymentState: "paid",
      paymentStateLabel: "PAID",
      outstanding: money(0, "USD", "$", "$0.00"),
      total: money(15, "USD", "$", "$15.00"),
    });
    assert.equal(isPayableInvoice(paid), false);
    assert.equal(isReversedInvoice(paid), false);
    assert.equal(paymentStateDisplay(paid.paymentState), "PAID");
  });
});

describe("Accountant navigation", () => {
  it("exposes HMO patients alongside billing and patient search", () => {
    const items = ACCOUNTANT_NAV.flatMap((group) => group.items);
    const ids = items.map((item) => item.id);
    assert.deepEqual(ids, [
      "accountant-cashier",
      "accountant-create",
      "accountant-outstanding",
      "accountant-deleted",
      "accountant-waived",
      "search",
      "hmo",
      "accountant-payments",
      "accountant-refunds",
      "accountant-revenue",
    ]);
    assert.equal(items[0] && "href" in items[0] ? items[0].href : "", "#/accountant");
    assert.ok(NAV_SOURCE.includes("#/accountant/outstanding"));
    assert.ok(NAV_SOURCE.includes("#/accountant/deleted"));
    assert.ok(NAV_SOURCE.includes("#/accountant/payments"));
    assert.ok(NAV_SOURCE.includes("#/accountant/refunds"));
    assert.equal(NAV_SOURCE.includes("#/accountant/receipts"), false);
    assert.equal(NAV_SOURCE.includes("Highest balances first."), false);
    assert.equal(NAV_SOURCE.includes("highest outstanding balance"), false);
    assert.ok(CASHIER_SOURCE.includes("Newest bills first."));
  });

  it("routes accountant sections to the accountant workplace", () => {
    assert.equal(parseShellHash("#/accountant").route, "accountant");
    assert.equal(parseShellHash("#/accountant/outstanding").route, "accountant");
    assert.equal(parseShellHash("#/accountant/create-bill").section, "create");
    assert.equal(parseShellHash("#/accountant/create-bill").navItemId, "accountant-create");
    assert.equal(parseShellHash("#/accountant/outstanding").section, "outstanding");
    assert.equal(parseShellHash("#/accountant/deleted").section, "deleted");
    assert.equal(parseShellHash("#/accountant/deleted").navItemId, "accountant-deleted");
    assert.equal(parseShellHash("#/accountant/waived").section, "waived");
    assert.equal(parseShellHash("#/accountant/waived").navItemId, "accountant-waived");
    assert.equal(parseShellHash("#/accountant/payments").route, "accountant");
    assert.equal(parseShellHash("#/accountant/payments").section, "payments");
    assert.equal(parseShellHash("#/accountant/refunds").section, "refunds");
    assert.equal(parseShellHash("#/accountant/revenue").section, "revenue");
    assert.equal(parseShellHash("#/accountant/receipts").section, "payments");
    assert.equal(parseShellHash("#/accountant/patient/abc").route, "accountant-patient");
  });
});

describe("receipt behavior", () => {
  it("prints the Odoo payment as a Hospital EMR receipt and does not invent a number", () => {
    assert.match(COLLECT_SOURCE, /Print receipt/);
    assert.match(CASHIER_SOURCE, /Recent payments/);
    assert.match(ACCOUNTANT_API, /PAYMENT_RECEIPT/);
    assert.equal(ACCOUNTANT_API.includes("receiptReport"), false);
    assert.equal(ACCOUNT_API.includes("receiptsNote"), false);
    assert.equal(ACCOUNT_API.includes("Receipt viewing will be available"), false);
    assert.match(ACCOUNTANT_API, /Hospital EMR does not invent receipt numbers/);
  });
});

describe("role restrictions", () => {
  it("lets only Accountant collect payment", () => {
    assert.match(MAP_SOURCE, /function canOpenAccountant[\s\S]*PRIVILEGES\.accountant/);
    assert.match(MAP_SOURCE, /Clinical and pharmacy privileges do not grant payment rights/);
    assert.match(ACCOUNTANT_API, /ACCOUNTANT_PRIVILEGE = "abikan:accountant"/);
    assert.match(ACCOUNTANT_API, /require_accountant/);
    assert.match(ACCOUNTANT_API, /account.payment.register/);
    assert.equal(COLLECT_SOURCE.includes("Refund"), false);
    assert.equal(CASHIER_SOURCE.includes("Flutterwave"), false);
    assert.equal(ACCOUNTANT_API.includes("Flutterwave"), false);
    assert.equal(COLLECT_SOURCE.includes("Collect payment"), true);
  });
});

describe("protected Radiology invoices", () => {
  it("does not pay or rewrite the protected TEST orders and invoices", () => {
    assert.deepEqual([...PROTECTED_TEST_ORDERS], [
      "ORD-6",
      "ORD-14",
      "ORD-15",
      "ORD-16",
      "ORD-17",
      "ORD-18",
      "ORD-19",
      "ORD-20",
      "ORD-21",
    ]);
    assert.ok(PROTECTED_TEST_INVOICES.includes("INV/2026/00006"));
    assert.ok(PROTECTED_TEST_INVOICES.includes("INV/2026/00031"));
    assert.ok(PROTECTED_TEST_INVOICES.includes("INV/2026/00035"));
    assert.equal(COLLECT_SOURCE.includes("INV/2026/00033"), false);
    assert.match(ACCOUNTANT_API, /IDEMPOTENCY/);
    assert.match(ACCOUNTANT_API, /invoice_already_paid/);
  });
});

describe("exact payment amount", () => {
  it("accepts an amount equal to the due balance", () => {
    const check = checkPaymentAmount("5000.00", 5000, 2);
    assert.equal(check.ok, true);
    if (check.ok) {
      assert.equal(check.amount, 5000);
      assert.equal(check.remaining, 0);
    }
  });

  it("accepts a typed exact due that differs from a noisy float residual", () => {
    const due = 4999.99999999;
    const check = checkPaymentAmount("5000.00", due, 2);
    assert.equal(check.ok, true);
    if (check.ok) {
      assert.equal(check.remaining, 0);
    }
    assert.equal(moneyMinor(due, 2), moneyMinor("5000.00", 2));
  });

  it("accepts a partial amount and shows the remaining balance", () => {
    const check = checkPaymentAmount("2000", 5000, 2);
    assert.equal(check.ok, true);
    if (check.ok) {
      assert.equal(check.amount, 2000);
      assert.equal(check.remaining, 3000);
    }
  });

  it("rejects an overpayment", () => {
    const check = checkPaymentAmount("5000.01", 5000, 2);
    assert.equal(check.ok, false);
    if (!check.ok) {
      assert.equal(check.code, "overpay");
    }
  });

  it("rejects zero and negative amounts", () => {
    assert.equal(checkPaymentAmount("0", 5000, 2).ok, false);
    assert.equal(checkPaymentAmount("-10", 5000, 2).ok, false);
    assert.equal(checkPaymentAmount("", 5000, 2).ok, false);
  });

  it("uses the collect form without a float slop comparison", () => {
    assert.match(COLLECT_SOURCE, /checkPaymentAmount/);
    assert.equal(COLLECT_SOURCE.includes("selectedDue + 0.0001"), false);
    assert.match(ACCOUNTANT_API, /validate_payment_amount/);
    assert.match(ACCOUNTANT_API, /money_minor/);
  });
});

describe("cashier identity", () => {
  it("does not show Registration Desk on the collect-payment identity", () => {
    assert.equal(COLLECT_SOURCE.includes("locationName="), false);
    assert.equal(COLLECT_SOURCE.includes("Registration Desk"), false);
  });
});
