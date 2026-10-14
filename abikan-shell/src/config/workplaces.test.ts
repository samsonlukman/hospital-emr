import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { switchableWorkplaceIds } from "./workplaceSwitcher.ts";

const RADIOLOGY_NAV = readFileSync(
  fileURLToPath(new URL("./radiologyNav.ts", import.meta.url)),
  "utf8",
);
const ACCOUNTANT_NAV = readFileSync(
  fileURLToPath(new URL("./accountantNav.ts", import.meta.url)),
  "utf8",
);

describe("Department workplace switcher", () => {
  it("hides the switcher for a single-department radiologist", () => {
    assert.deepEqual(switchableWorkplaceIds(false, ["radiology"]), []);
  });

  it("exposes only assigned departments for a multi-department staff member", () => {
    assert.deepEqual(
      switchableWorkplaceIds(false, ["registration", "radiology", "accountant"]),
      ["registration", "radiology", "accountant"],
    );
    assert.equal(
      switchableWorkplaceIds(false, ["registration", "radiology", "accountant"]).includes(
        "administration",
      ),
      false,
    );
  });

  it("does not expose unassigned Clinical, Nursing, Laboratory, or Pharmacy", () => {
    const ids = switchableWorkplaceIds(false, ["registration", "radiology", "accountant"]);
    assert.deepEqual(
      ids.filter((id) => ["clinical", "nursing", "laboratory", "pharmacy"].includes(id)),
      [],
    );
  });

  it("lets SuperAdmin keep the full department switcher including Administration", () => {
    const ids = switchableWorkplaceIds(true, []);
    assert.equal(ids[0], "administration");
    assert.ok(ids.length > 3);
  });

  it("keeps Radiology navigation when Accountant access is also assigned", () => {
    assert.match(RADIOLOGY_NAV, /label: "Radiology"/);
    assert.match(RADIOLOGY_NAV, /label: "Worklist"/);
    assert.match(ACCOUNTANT_NAV, /label: "Payments"/);
    assert.match(ACCOUNTANT_NAV, /label: "Outstanding"/);
    assert.doesNotMatch(RADIOLOGY_NAV, /Cashier/);
  });
});
