export const HOSPITAL_TIMEZONE = "Africa/Lagos";

/** OpenMRS REST datetimes look like `2026-08-19T07:40:00.000+0000`. */
export function parseOpenmrsDateTime(
  value: string | number | Date | undefined | null,
): Date | null {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  if (typeof value === "number") {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const text = (value || "").trim();
  if (!text) {
    return null;
  }
  const normalized = text.replace(/Z$/i, "+00:00").replace(/([+-]\d{2})(\d{2})$/, "$1:$2");
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function todayDateString(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

export function tomorrowDateString(): string {
  const now = new Date();
  now.setDate(now.getDate() + 1);
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function isDateOnly(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value.trim());
}

function hospitalDayKey(date: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: HOSPITAL_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

export function formatDate(value: string | number | undefined): string {
  if (value === undefined || value === null || value === "") {
    return "—";
  }
  const date = typeof value === "number" ? new Date(value) : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return date.toLocaleDateString("en-NG", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: HOSPITAL_TIMEZONE,
  });
}

export function formatClinicalWhen(value: string | number | undefined): string {
  if (value === undefined || value === null || value === "") {
    return "—";
  }
  if (typeof value === "string" && isDateOnly(value)) {
    return formatDate(value);
  }
  const date = typeof value === "number" ? new Date(value) : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  const time = formatClock(value);
  if (hospitalDayKey(date) === hospitalDayKey(new Date())) {
    return `Today · ${time}`;
  }
  return `${formatDate(value)} · ${time}`;
}

export function formatDateTime(value: string | number | undefined): string {
  const date = formatDate(value);
  const time = formatClock(value);
  if (date === "—" && time === "—") {
    return "—";
  }
  if (date === "—") {
    return time;
  }
  if (time === "—") {
    return date;
  }
  return `${date} · ${time}`;
}

export function greetingForNow(): string {
  const hour = new Date().getHours();
  if (hour < 12) {
    return "Good morning";
  }
  if (hour < 17) {
    return "Good afternoon";
  }
  return "Good evening";
}

export function formatClock(value: string | number | undefined): string {
  if (value === undefined || value === null || value === "") {
    return "—";
  }
  const date = typeof value === "number" ? new Date(value) : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return date.toLocaleTimeString("en-NG", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: HOSPITAL_TIMEZONE,
  });
}
