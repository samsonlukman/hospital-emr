export type LoadPhase = "loading" | "empty" | "ready" | "error";

export function boardPhase(input: {
  loading: boolean;
  error?: string | null;
  count: number;
}): LoadPhase {
  if (input.loading) {
    return "loading";
  }
  if (input.error) {
    return "error";
  }
  if (input.count === 0) {
    return "empty";
  }
  return "ready";
}

export function isLoadingCopy(title: string): boolean {
  return /^\s*loading\b/i.test(title) || /^\s*searching\b/i.test(title);
}

export function isEmptyCopy(title: string): boolean {
  return /^\s*no\b/i.test(title);
}

export function isErrorCopy(title: string): boolean {
  return /^\s*unable to\b/i.test(title) || /^\s*could not\b/i.test(title);
}

export function pendingActionLabel(label: string): string {
  const exact: Record<string, string> = {
    Save: "Saving…",
    "Save consultation": "Saving consultation…",
    "Save allergy": "Saving…",
    "Save Nursing Note": "Saving…",
    "Save vitals": "Saving…",
    "Record vitals": "Saving…",
    "Admit Patient": "Admitting…",
    "Assign Bed": "Assigning…",
    "Transfer Patient": "Transferring…",
    "Discharge Patient": "Discharging…",
    Prescribe: "Saving prescription…",
    "Start visit": "Creating visit…",
    "Create Visit": "Creating visit…",
    "Register Patient": "Registering…",
    "Close Visit": "Closing visit…",
    "Remove allergy": "Removing…",
    "Confirm and Record": "Recording…",
    Dispense: "Dispensing…",
    "Record Payment": "Recording payment…",
    "Create Charge": "Creating charge…",
  };
  if (exact[label]) {
    return exact[label];
  }
  return `${label.replace(/\.*$/, "")}…`;
}
