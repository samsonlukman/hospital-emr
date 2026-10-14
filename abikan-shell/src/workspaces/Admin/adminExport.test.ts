import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import type { AdminExportRecord } from "../../types/adminExport.ts";
import {
  filterHistory,
  formatFileSize,
  formatRecordCount,
  formatExportTime,
} from "./adminExportView.ts";

const SOURCE = readFileSync(fileURLToPath(new URL("./AdminExportWorkspace.tsx", import.meta.url)), "utf8");
const SERVICE = readFileSync(fileURLToPath(new URL("../../services/adminExport.ts", import.meta.url)), "utf8");
const NAV = readFileSync(fileURLToPath(new URL("../../config/adminNav.ts", import.meta.url)), "utf8");
const ROUTER = readFileSync(fileURLToPath(new URL("../../app/WorkspaceRouter.tsx", import.meta.url)), "utf8");

function record(overrides: Partial<AdminExportRecord> = {}): AdminExportRecord {
  return {
    exportId: "export-1",
    createdAt: "2026-09-07T16:00:00+00:00",
    adminUsername: "hospitaladmin.abikan",
    adminDisplayName: "Hospital Administrator",
    dataset: "patients",
    datasetLabel: "Patients",
    format: "xlsx",
    formatLabel: "Excel",
    department: "",
    departmentLabel: "All departments",
    statusFilter: "",
    statusLabel: "All",
    period: "today",
    periodLabel: "Today",
    startDate: "2026-09-07",
    endDate: "2026-09-07",
    recordCount: 1245,
    fileSize: 2048,
    filename: "Hospital EMR-Patients-Today.xlsx",
    outcome: "success",
    outcomeLabel: "Success",
    fileStatus: "available",
    fileStatusLabel: "Available",
    expiresAt: "2026-09-08T16:00:00+00:00",
    canDownload: true,
    canDelete: true,
    expired: false,
    ...overrides,
  };
}

describe("Admin data export", () => {
  it("formats history values the way staff will read them", () => {
    assert.equal(formatRecordCount(1245), "1,245");
    assert.equal(formatFileSize(2048), "2.0 KB");
    assert.match(formatExportTime("2026-09-07T16:00:00+00:00"), /07 Sep/);
    assert.match(formatExportTime("2026-09-07T16:00:00+00:00"), /2026/);
  });

  it("filters export history by dataset, result, and search", () => {
    const rows = [
      record(),
      record({
        exportId: "export-2",
        dataset: "revenue",
        datasetLabel: "Revenue by department",
        formatLabel: "CSV",
        adminUsername: "admin.abikan",
        outcome: "failed",
        outcomeLabel: "Failed",
      }),
    ];
    assert.equal(filterHistory(rows, "", "patients", "").length, 1);
    assert.equal(filterHistory(rows, "revenue", "", "failed").length, 1);
    assert.equal(filterHistory(rows, "excel", "", "").length, 1);
  });

  it("keeps the Admin-only screen and API paths hospital-facing", () => {
    assert.match(NAV, /Data export/);
    assert.match(NAV, /#\/admin\/export/);
    assert.match(ROUTER, /showAdminExport/);
    assert.match(SOURCE, /Generate export/);
    assert.match(SOURCE, /Export history/);
    assert.doesNotMatch(SOURCE, /OpenMRS|Bahmni|Odoo|UUID|API|ledger|Atomfeed/i);
    assert.match(SERVICE, /\/openmrs\/abikan-api\/admin\/export/);
  });
});
