import type { LabResultSummary } from "../../types/index.ts";

/** A written result such as Positive has no unit or reference range. */
export function resultShowsReferenceRange(result: string): boolean {
  const text = result.trim();
  if (!text || text === "—") {
    return true;
  }
  return /^-?\d+(?:\.\d+)?$/.test(text.replace(/,/g, ""));
}

export function markAmbiguousLabResults(rows: LabResultSummary[]): LabResultSummary[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const key = `${row.accessionUuid}\u0000${row.panelName}\u0000${row.testName}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return rows.map((row) => {
    const key = `${row.accessionUuid}\u0000${row.panelName}\u0000${row.testName}`;
    if ((counts.get(key) ?? 0) < 2) {
      return row;
    }
    return {
      ...row,
      mappingStatus: "ambiguous",
      mappingMessage:
        "Duplicate same-test orders prevent a safe match to one specific order.",
    };
  });
}
