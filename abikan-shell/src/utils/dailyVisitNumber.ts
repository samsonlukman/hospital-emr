export const MISSING_DAILY_VISIT_NUMBER = "—";

export function parseDailyVisitNumber(value: unknown): number | null {
  if (value === undefined || value === null) {
    return null;
  }
  const text = String(value).trim().replace(/^#/, "").trim();
  if (!/^[0-9]{1,6}$/.test(text)) {
    return null;
  }
  const number = Number(text);
  return number > 0 ? number : null;
}

export function formatDailyVisitNumber(value: unknown): string {
  const parsed = parseDailyVisitNumber(value);
  return parsed ? String(parsed).padStart(3, "0") : MISSING_DAILY_VISIT_NUMBER;
}

export function dailyVisitNumberSortKey(value: unknown): [number, number] {
  const parsed = parseDailyVisitNumber(value);
  return parsed === null ? [1, 0] : [0, parsed];
}

export function compareDailyVisitNumber(left: unknown, right: unknown): number {
  const [leftGroup, leftValue] = dailyVisitNumberSortKey(left);
  const [rightGroup, rightValue] = dailyVisitNumberSortKey(right);
  return leftGroup - rightGroup || leftValue - rightValue;
}

export function dailyVisitNumberFromAttributes(
  attributes:
    | Array<{
        value?: string;
        display?: string;
        attributeType?: { uuid?: string; name?: string };
      }>
    | undefined,
): string {
  const match = (attributes ?? []).find((item) => {
    const name = (item.attributeType?.name || "").trim();
    return name === "Daily Visit Number";
  });
  return formatDailyVisitNumber(match?.value || match?.display);
}

export function visitNumberLabel(value: unknown): string {
  const formatted = formatDailyVisitNumber(value);
  return formatted === MISSING_DAILY_VISIT_NUMBER ? MISSING_DAILY_VISIT_NUMBER : `Visit #${formatted}`;
}
