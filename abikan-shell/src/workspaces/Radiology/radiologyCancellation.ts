import { WORKLIST_PROTECTED_INVOICES, WORKLIST_PROTECTED_ORDERS } from "./radiologyWorklist.ts";

/** OpenMRS/Bahmni can discontinue or void orders. Radiology must not. */
export type RadiologyCancellationClass = "A" | "B" | "C" | "D";

export const RADIOLOGY_CANCELLATION_CLASS: RadiologyCancellationClass = "C";
export const RADIOLOGY_SHOWS_DELETE_BUTTON = false;
export const RADIOLOGY_SHOWS_CANCEL_BUTTON = false;
export const RADIOLOGY_MAY_VOID_ORDERS = false;
export const RADIOLOGY_MAY_DISCONTINUE_ORDERS = false;
export const RADIOLOGY_ORDER_WRITE_PRIVILEGE_REQUIRED = "Edit Orders";
export const RADIOLOGY_SHOULD_RECEIVE_ORDER_WRITE_PRIVILEGE = false;
export const RADIOLOGY_CANCELLATION_UPDATES_ODOO = false;
export const RADIOLOGY_CANCELLATION_DELETES_REPORTS = false;

export function radiologyCanDeleteOrdersFromUi(): boolean {
  return RADIOLOGY_SHOWS_DELETE_BUTTON || RADIOLOGY_SHOWS_CANCEL_BUTTON;
}

export function radiologyCancellationIsSafeToExpose(): boolean {
  return (
    (RADIOLOGY_CANCELLATION_CLASS === "A" || RADIOLOGY_CANCELLATION_CLASS === "B") &&
    RADIOLOGY_SHOULD_RECEIVE_ORDER_WRITE_PRIVILEGE &&
    RADIOLOGY_CANCELLATION_UPDATES_ODOO
  );
}

export function radiologyProtectedCancellationTargets(): {
  orders: readonly string[];
  invoices: readonly string[];
} {
  return {
    orders: WORKLIST_PROTECTED_ORDERS,
    invoices: WORKLIST_PROTECTED_INVOICES,
  };
}
