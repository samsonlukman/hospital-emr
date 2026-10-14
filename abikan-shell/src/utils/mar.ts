import type { MarOutcome, MarSlotStatus } from "../types/inpatient";

export function marOutcomeLabel(outcome: MarOutcome): string {
  return {
    given: "Given",
    "not-done": "Not done",
    refused: "Refused",
    held: "Held",
  }[outcome];
}

export function marSlotStatusLabel(status: MarSlotStatus): string {
  return {
    SCHEDULED: "Scheduled",
    COMPLETED: "Completed",
    NOT_DONE: "Not done",
    STOPPED: "Stopped",
    MISSED: "Missed",
  }[status];
}

export function marStatusTone(
  status: MarSlotStatus,
): "success" | "warning" | "danger" | "neutral" | "info" {
  const tones = {
    SCHEDULED: "info",
    COMPLETED: "success",
    NOT_DONE: "danger",
    STOPPED: "warning",
    MISSED: "danger",
  } as const;
  return tones[status];
}

export function canSubmitMar(
  outcome: MarOutcome,
  reason: string,
  saving: boolean,
  outsideWindow = false,
): boolean {
  return (
    !saving &&
    !((outcome !== "given" || outsideWindow) && !reason.trim())
  );
}
