import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import { readFileSync as readSrc } from "node:fs";
import { PHARMACY_NAV } from "../../config/pharmacyNav.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "../../..");
const mapPath = join(root, "server/patient-account/data/pharmacy_catalogue_map.json");
const csvPath = join(root, "server/patient-account/data/pharmacy_catalogue.csv");

type MapItem = {
  sn: string;
  hospitalName: string;
  action: "reuse" | "create" | "skip";
  drugUuid?: string;
  createName?: string;
  conceptUuid?: string;
  strength?: string;
  dosageFormUuid?: string;
  skipReason?: string;
};

type CatalogueMap = {
  developmentPriceNgn: number;
  priceLabel: string;
  importSpreadsheetQuantities: boolean;
  doNotTouchTestDrugUuids: string[];
  items: MapItem[];
};

function loadMap(): CatalogueMap {
  return JSON.parse(readFileSync(mapPath, "utf8")) as CatalogueMap;
}

describe("pharmacy catalogue mapping", () => {
  it("covers every hospital row without inventing prices or importing stock", () => {
    const map = loadMap();
    const csv = readFileSync(csvPath, "utf8").trim().split("\n").slice(1);
    assert.equal(map.items.length, 100);
    assert.equal(csv.length, 100);
    assert.equal(map.developmentPriceNgn, 100);
    assert.equal(map.priceLabel, "");
    assert.equal(map.importSpreadsheetQuantities, false);

    const sns = map.items.map((item) => item.sn);
    assert.equal(new Set(sns).size, 100);
    assert.deepEqual(
      sns,
      Array.from({ length: 100 }, (_, index) => String(index + 1)),
    );
  });

  it("reuses existing drugs or creates only unambiguous new ones", () => {
    const map = loadMap();
    const reused = map.items.filter((item) => item.action === "reuse");
    const created = map.items.filter((item) => item.action === "create");
    const skipped = map.items.filter((item) => item.action === "skip");
    assert.equal(reused.length, 16);
    assert.equal(created.length, 5);
    assert.equal(skipped.length, 79);

    const mappedUuids = reused.map((item) => item.drugUuid).filter(Boolean) as string[];
    assert.equal(mappedUuids.length, 16);
    assert.equal(new Set(mappedUuids).size, 16);
    for (const uuid of map.doNotTouchTestDrugUuids) {
      assert.equal(mappedUuids.includes(uuid), false);
    }

    for (const item of created) {
      assert.ok(item.createName);
      assert.ok(item.conceptUuid);
      assert.ok(item.strength);
      assert.ok(item.dosageFormUuid);
    }
    for (const item of skipped) {
      assert.ok(item.skipReason);
    }
  });

  it("does not collapse eye and ointment gentamicin, or map brands without composition", () => {
    const map = loadMap();
    const bySn = Object.fromEntries(map.items.map((item) => [item.sn, item]));
    assert.equal(bySn["13"]?.action, "skip");
    assert.equal(bySn["59"]?.action, "skip");
    assert.equal(bySn["13"]?.skipReason, "would_collapse_distinct_forms");
    assert.equal(bySn["7"]?.action, "skip");
    assert.equal(bySn["1"]?.action, "skip");
    assert.equal(bySn["20"]?.action, "reuse");
    assert.equal(bySn["20"]?.drugUuid, "7e0766e1-b679-4eb3-ab93-d63910ad6eb4");
    assert.equal(bySn["12"]?.drugUuid, "658899ad-f703-4827-80a6-26dea4924640");
    assert.equal(bySn["96"]?.drugUuid, "eb7f981e-0748-4da0-bd42-c49dbd153c0d");
    assert.equal(bySn["97"]?.drugUuid, "081dab88-0929-4148-98e7-f9143a760e8d");
    assert.notEqual(bySn["96"]?.drugUuid, bySn["97"]?.drugUuid);
  });

  it("keeps payment and catalogue administration out of Pharmacy", () => {
    const labels = PHARMACY_NAV.flatMap((group) => group.items.map((item) => item.label.toLowerCase()));
    assert.equal(
      labels.some(
        (label) =>
          label.includes("payment") ||
          label.includes("cashier") ||
          label.includes("cash") ||
          label.includes("accountant"),
      ),
      false,
    );
    assert.equal(
      PHARMACY_NAV.flatMap((group) => group.items).some(
        (item) => item.id === "catalogue" && item.kind === "route" && "href" in item && item.href === "#/pharmacy/catalogue",
      ),
      true,
    );
    assert.equal(
      PHARMACY_NAV.flatMap((group) => group.items).some(
        (item) => item.id === "inventory" && item.kind === "route" && "href" in item && item.href === "#/pharmacy/inventory",
      ),
      true,
    );
    assert.equal(
      PHARMACY_NAV.flatMap((group) => group.items).some((item) => item.id === "stock" && item.kind === "soon"),
      false,
    );
    const pharmacyUi = readSrc(join(root, "src/workspaces/Pharmacy/PharmacyWorkspace.tsx"), "utf8");
    const pharmacyForm = readSrc(join(root, "src/workspaces/Pharmacy/PharmacyDialogs.tsx"), "utf8");
    assert.equal(pharmacyUi.includes("cetirizine"), false);
    assert.equal(pharmacyUi.includes("Marcfix"), false);
    assert.equal(pharmacyUi.includes(">Pay<"), false);
    assert.equal(pharmacyUi.includes("Add medicines"), true);
    assert.equal(pharmacyForm.includes("Quantity on the shelf"), false);
    assert.equal(pharmacyForm.includes("draft.stock"), false);
    assert.equal(pharmacyUi.includes("Receive Stock"), true);
    assert.equal(pharmacyForm.includes("Pay Supplier"), false);
    const stockEntry = readSrc(join(root, "src/workspaces/Pharmacy/PharmacyStockEntryView.tsx"), "utf8");
    assert.equal(stockEntry.includes("Purchase Cost"), true);
    assert.equal(pharmacyUi.includes("Medicine not in catalogue? Add it to Drug Catalogue"), true);
    assert.equal(pharmacyUi.includes("openPharmacyCatalogueAdd"), true);
  });
});
