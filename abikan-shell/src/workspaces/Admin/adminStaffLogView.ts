export function formatLogClock(localTime: string): string {
  const [hours, minutes, seconds] = localTime.split(":").map((part) => Number(part));
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return localTime;
  }
  const suffix = hours >= 12 ? "PM" : "AM";
  const hour12 = hours % 12 || 12;
  const mm = String(minutes).padStart(2, "0");
  const ss = Number.isFinite(seconds) ? String(seconds).padStart(2, "0") : "";
  return ss ? `${hour12}:${mm}:${ss} ${suffix}` : `${hour12}:${mm} ${suffix}`;
}

export function formatLogClockShort(localTime: string): string {
  const [hours, minutes] = localTime.split(":").map((part) => Number(part));
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return localTime;
  }
  const suffix = hours >= 12 ? "PM" : "AM";
  const hour12 = hours % 12 || 12;
  return `${hour12}:${String(minutes).padStart(2, "0")} ${suffix}`;
}

export function shiftIsoDate(value: string, days: number): string {
  const [year, month, day] = value.split("-").map((part) => Number(part));
  const next = new Date(Date.UTC(year, month - 1, day + days));
  return next.toISOString().slice(0, 10);
}

export function statusTone(status: string): "success" | "info" | "warning" | "danger" | "neutral" {
  if (status === "SIGNED_IN") {
    return "info";
  }
  if (status === "SIGNED_OUT") {
    return "success";
  }
  return "neutral";
}

export function clockOrDash(localTime: string): string {
  return localTime ? formatLogClockShort(localTime) : "—";
}
