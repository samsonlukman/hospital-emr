export type CreateTestColumnDraft = {
  key: string;
  name: string;
};

export type CreateTestRowDraft = {
  key: string;
  name: string;
  values: Record<string, string>;
};

export type CreateTestDraft = {
  testName: string;
  price: string;
  columns: CreateTestColumnDraft[];
  rows: CreateTestRowDraft[];
};

function newKey(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export function emptyCreateTestColumn(): CreateTestColumnDraft {
  return { key: newKey("col"), name: "" };
}

export function emptyCreateTestRow(columnKeys: string[] = []): CreateTestRowDraft {
  const values: Record<string, string> = {};
  for (const key of columnKeys) {
    values[key] = "";
  }
  return { key: newKey("row"), name: "", values };
}

export function emptyCreateTestDraft(): CreateTestDraft {
  const column = emptyCreateTestColumn();
  return {
    testName: "",
    price: "",
    columns: [column],
    rows: [emptyCreateTestRow([column.key])],
  };
}

export function addCreateTestColumn(draft: CreateTestDraft): CreateTestDraft {
  const column = emptyCreateTestColumn();
  return {
    ...draft,
    columns: [...draft.columns, column],
    rows: draft.rows.map((row) => ({
      ...row,
      values: { ...row.values, [column.key]: "" },
    })),
  };
}

export function removeCreateTestColumn(draft: CreateTestDraft, columnKey: string): CreateTestDraft {
  if (draft.columns.length <= 1) {
    return draft;
  }
  return {
    ...draft,
    columns: draft.columns.filter((column) => column.key !== columnKey),
    rows: draft.rows.map((row) => {
      const values = { ...row.values };
      delete values[columnKey];
      return { ...row, values };
    }),
  };
}

export function addCreateTestRow(draft: CreateTestDraft): CreateTestDraft {
  return {
    ...draft,
    rows: [...draft.rows, emptyCreateTestRow(draft.columns.map((column) => column.key))],
  };
}

export function removeCreateTestRow(draft: CreateTestDraft, rowKey: string): CreateTestDraft {
  if (draft.rows.length <= 1) {
    return draft;
  }
  return {
    ...draft,
    rows: draft.rows.filter((row) => row.key !== rowKey),
  };
}

export function createTestDraftError(draft: CreateTestDraft): string {
  if (!draft.testName.trim()) {
    return "Enter a test name.";
  }
  const price = draft.price.trim();
  if (price) {
    const amount = Number(price.replace(/[₦,\s]/g, ""));
    if (!Number.isFinite(amount) || amount < 0) {
      return "Enter a price of zero or more, or leave price blank.";
    }
  }
  if (draft.columns.every((column) => !column.name.trim())) {
    return "Name at least one result column.";
  }
  if (draft.rows.every((row) => !row.name.trim())) {
    return "Add at least one property name in the Name column.";
  }
  return "";
}

export function serializeCreateTestDraft(draft: CreateTestDraft): {
  name: string;
  price: number | null;
  columns: string[];
  properties: Array<{ name: string; values: string[] }>;
} {
  const columns = draft.columns.map((column) => column.name.trim());
  const priceRaw = draft.price.trim();
  const price = priceRaw
    ? Math.round(Number(priceRaw.replace(/[₦,\s]/g, "")) * 100) / 100
    : null;
  return {
    name: draft.testName.trim(),
    price: Number.isFinite(price as number) ? price : null,
    columns,
    properties: draft.rows
      .filter((row) => row.name.trim())
      .map((row) => ({
        name: row.name.trim(),
        values: draft.columns.map((column) => (row.values[column.key] || "").trim()),
      })),
  };
}
