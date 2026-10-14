import type { AdminExportRecord } from "../../types/adminExport";

export function formatExportTime(value: string): string {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Lagos",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export function formatRecordCount(value: number): string {
  return new Intl.NumberFormat("en-NG").format(value);
}

export function formatFileSize(bytes: number): string {
  if (!bytes) {
    return "—";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function filterHistory(
  rows: AdminExportRecord[],
  query: string,
  dataset: string,
  outcome: string,
): AdminExportRecord[] {
  const term = query.trim().toLowerCase();
  return rows.filter((row) => {
    if (dataset && row.dataset !== dataset) {
      return false;
    }
    if (outcome && row.outcome !== outcome) {
      return false;
    }
    if (!term) {
      return true;
    }
    const haystack = [
      row.datasetLabel,
      row.formatLabel,
      row.adminDisplayName,
      row.adminUsername,
      row.periodLabel,
      row.departmentLabel,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(term);
  });
}

export function exportOutcomeTone(outcome: string): "success" | "danger" {
  return outcome === "success" ? "success" : "danger";
}
