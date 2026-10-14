import type { DrugOrderSummary } from "../../types";
import { openmrsGet } from "./client";
import {
  extractDrugOrderRows,
  mapDrugCatalogueHits,
  mapDrugOrderConfig,
  mergeClinicalMedications,
  type BahmniDrugOrderRaw,
  type DrugCatalogueHit,
  type DrugOrderConfig,
} from "./drugOrderMap";

export * from "./drugOrderMap";
export { isOpenmrsOrderUuid, newDrugOrderUuidsFromList } from "./prescriptionAnnounce";
import { newDrugOrderUuidsFromList } from "./prescriptionAnnounce";

export const DRUG_ORDER_CONFIG_URL = "/openmrs/ws/rest/v1/bahmnicore/config/drugOrders";
export const DRUG_SEARCH_URL = "/openmrs/ws/rest/v1/drug";
export const DRUG_ORDERS_ACTIVE_URL = "/openmrs/ws/rest/v1/bahmnicore/drugOrders/active";
export const DRUG_ORDERS_PRESCRIBED_URL =
  "/openmrs/ws/rest/v1/bahmnicore/drugOrders/prescribedAndActive";

export async function fetchDrugOrderConfig(): Promise<DrugOrderConfig> {
  const payload = await openmrsGet<unknown>(DRUG_ORDER_CONFIG_URL);
  return mapDrugOrderConfig(payload);
}

export async function searchDrugCatalogue(term: string): Promise<DrugCatalogueHit[]> {
  const query = term.trim();
  if (query.length < 2) {
    return [];
  }
  const params = new URLSearchParams({
    q: query,
    v: "custom:(uuid,name,strength,retired,dosageForm:(display),concept:(uuid,display))",
    limit: "20",
  });
  const [openmrsResult, priceResult] = await Promise.allSettled([
    openmrsGet<unknown>(`${DRUG_SEARCH_URL}?${params.toString()}`),
    fetch(`/openmrs/abikan-api/pharmacy/catalogue?q=${encodeURIComponent(query)}`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    }).then(async (response) => {
      if (!response.ok) {
        throw new Error("Medicine prices unavailable.");
      }
      return response.json() as Promise<{
        items?: Array<{
          id?: string;
          price?: string | { formatted?: string };
        }>;
      }>;
    }),
  ]);
  if (openmrsResult.status === "rejected") {
    throw openmrsResult.reason;
  }
  const prices = new Map(
    (priceResult.status === "fulfilled" ? priceResult.value.items || [] : [])
      .filter((item) => item.id && item.price)
      .map((item) => {
        const price =
          typeof item.price === "string"
            ? item.price
            : item.price && typeof item.price === "object"
              ? item.price.formatted
              : "";
        return [item.id as string, price];
      })
      .filter((item): item is [string, string] => Boolean(item[1])),
  );
  return mapDrugCatalogueHits(openmrsResult.value).map((hit) => ({
    ...hit,
    price: prices.get(hit.uuid),
  }));
}

function pharmacyHit(item: {
  id?: string;
  name?: string;
  strength?: string;
  form?: string;
  brandName?: string;
  listedAs?: string;
  available?: boolean;
  stockOnHand?: number;
  stockUnits?: string;
  price?: string | { formatted?: string } | null;
}): DrugCatalogueHit | null {
  const uuid = (item.id || "").trim();
  const name = (item.name || "").trim();
  if (!uuid || !name || item.available === false) {
    return null;
  }
  const qty = Number(item.stockOnHand);
  const units = item.stockUnits || "";
  const qtyText = Number.isFinite(qty) ? String(qty).replace(/\.0$/, "") : "";
  const stockLabel =
    Number.isFinite(qty) && qty > 0
      ? units
        ? `${qtyText} in stock · ${units}`
        : `${qtyText} in stock`
      : "None in stock";
  const price =
    typeof item.price === "string"
      ? item.price
      : item.price && typeof item.price === "object"
        ? item.price.formatted
        : undefined;
  return {
    uuid,
    name,
    strength: item.strength || "—",
    form: item.form || "—",
    genericName: item.brandName || item.listedAs || "—",
    price,
    stockLabel,
  };
}

export async function searchMedicinesForPrescription(term: string): Promise<DrugCatalogueHit[]> {
  const query = term.trim();
  if (query.length < 2) {
    return [];
  }
  try {
    const response = await fetch(
      `/openmrs/abikan-api/pharmacy/catalogue?q=${encodeURIComponent(query)}`,
      { credentials: "include", headers: { Accept: "application/json" } },
    );
    if (response.ok) {
      const payload = (await response.json()) as {
        items?: Array<Parameters<typeof pharmacyHit>[0]>;
      };
      return (payload.items || []).map(pharmacyHit).filter((hit): hit is DrugCatalogueHit => Boolean(hit));
    }
  } catch {
    // Pharmacy list unavailable — fall back to the hospital medicine search.
  }
  return searchDrugCatalogue(query);
}

interface DosageFormDrug {
  uuid?: string;
  form?: string;
  dosageForm?: { display?: string; name?: string };
}

function knownForm(drug: DosageFormDrug | undefined): string {
  return (drug?.dosageForm?.display || drug?.dosageForm?.name || drug?.form || "").trim();
}

export async function attachDosageForms<T extends { drug?: DosageFormDrug; drugOrder?: { drug?: DosageFormDrug } }>(
  rows: T[],
): Promise<void> {
  const pending = new Map<string, DosageFormDrug[]>();
  for (const row of rows) {
    const drug = row.drug || row.drugOrder?.drug;
    const uuid = (drug?.uuid || "").trim();
    if (!drug || !uuid || knownForm(drug)) {
      continue;
    }
    const list = pending.get(uuid) || [];
    list.push(drug);
    pending.set(uuid, list);
  }
  await Promise.all(
    [...pending.entries()].map(async ([uuid, drugs]) => {
      try {
        const payload = await openmrsGet<{ dosageForm?: { display?: string; name?: string } }>(
          `/openmrs/ws/rest/v1/drug/${encodeURIComponent(uuid)}?v=custom:(dosageForm:(display))`,
        );
        const form = (payload.dosageForm?.display || payload.dosageForm?.name || "").trim();
        if (!form) {
          return;
        }
        for (const drug of drugs) {
          drug.form = form;
        }
      } catch {
        // The saved unit stays visible if the medicine record cannot be read.
      }
    }),
  );
}

export async function fetchDrugOrders(patientUuid: string): Promise<DrugOrderSummary[]> {
  const query = `patientUuid=${encodeURIComponent(patientUuid)}`;
  const [prescribed, active] = await Promise.allSettled([
    openmrsGet<unknown>(`${DRUG_ORDERS_PRESCRIBED_URL}?${query}`),
    openmrsGet<unknown>(`${DRUG_ORDERS_ACTIVE_URL}?${query}`),
  ]);
  if (prescribed.status === "rejected" && active.status === "rejected") {
    throw prescribed.reason;
  }
  const prescribedRows: BahmniDrugOrderRaw[] =
    prescribed.status === "fulfilled" ? extractDrugOrderRows(prescribed.value) : [];
  const activeRows: BahmniDrugOrderRaw[] =
    active.status === "fulfilled" ? extractDrugOrderRows(active.value) : [];
  await attachDosageForms([...prescribedRows, ...activeRows]);
  return mergeClinicalMedications([prescribedRows, activeRows]);
}

const DEFAULT_DISCOVER_DELAYS_MS = [0, 300, 700, 1400, 2800];

/**
 * After a clinical save, newly written drug orders can lag briefly in Bahmni
 * read APIs. Retry until enough new UUID-shaped orders appear (or delays end).
 */
export async function collectNewDrugOrderUuids(
  patientUuid: string,
  priorUuids: ReadonlySet<string>,
  options?: { expectedCount?: number; delaysMs?: number[] },
): Promise<string[]> {
  const expected = Math.max(1, options?.expectedCount ?? 1);
  const delays = options?.delaysMs ?? DEFAULT_DISCOVER_DELAYS_MS;
  let found: string[] = [];
  for (const delay of delays) {
    if (delay > 0) {
      await new Promise((resolve) => {
        window.setTimeout(resolve, delay);
      });
    }
    const latest = await fetchDrugOrders(patientUuid);
    found = newDrugOrderUuidsFromList(latest, priorUuids);
    if (found.length >= expected) {
      return found;
    }
  }
  return found;
}
