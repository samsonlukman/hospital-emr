/** Local browser speech for staff notifications. No external TTS. */

export const NOTIFICATION_VOICE_MUTED_KEY = "abikan.notifications.voiceMuted";
export const NOTIFICATION_VOICE_UNLOCKED_KEY = "abikan.notifications.voiceUnlocked";
export const NOTIFICATION_SPOKEN_IDS_KEY = "abikan.notifications.spokenIds";
export const VOICE_SETTINGS_CHANGED_EVENT = "abikan:voice-settings-changed";

/** @deprecated Prefer NOTIFICATION_* keys. Kept for Phase-1 migration. */
export const PATIENT_CALL_VOICE_MUTED_KEY = "abikan.patientCall.voiceMuted";
/** @deprecated Prefer NOTIFICATION_* keys. */
export const PATIENT_CALL_VOICE_UNLOCKED_KEY = "abikan.patientCall.voiceUnlocked";
/** @deprecated Prefer NOTIFICATION_* keys. */
export const PATIENT_CALL_SPOKEN_IDS_KEY = "abikan.patientCall.spokenIds";

/** Keep repeating spoken high-priority alerts for this long unless acknowledged sooner. */
export const PATIENT_CALL_ANNOUNCE_MS = 15_000;
export const NOTIFICATION_ANNOUNCE_MS = PATIENT_CALL_ANNOUNCE_MS;
const PATIENT_CALL_REPEAT_GAP_MS = 650;

/** Short message sound; normal messages never use speech synthesis. */
export function playMessageBeep(): void {
  if (typeof window === "undefined") return;
  try {
    const AudioContextClass =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) return;
    const context = new AudioContextClass();
    if (context.state === "suspended") {
      void context.resume();
    }
    const now = context.currentTime;
    const gain = context.createGain();
    gain.connect(context.destination);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.12, now + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.24);
    const oscillator = context.createOscillator();
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(988, now);
    oscillator.frequency.exponentialRampToValueAtTime(1318, now + 0.12);
    oscillator.connect(gain);
    oscillator.start(now);
    oscillator.stop(now + 0.25);
    window.setTimeout(() => void context.close(), 350);
  } catch {
    // Audio is optional; the message remains available in the thread.
  }
}

const SPOKEN_IDS_CAP = 80;

type AnnouncementSession = {
  token: number;
  callId: string;
};

let announcementToken = 0;
let activeAnnouncement: AnnouncementSession | null = null;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, ms);
  });
}

function storageGet(storage: Storage | null, primary: string, legacy: string): string | null {
  try {
    return storage?.getItem(primary) ?? storage?.getItem(legacy) ?? null;
  } catch {
    return null;
  }
}

function storageSet(storage: Storage | null, primary: string, legacy: string, value: string): void {
  try {
    storage?.setItem(primary, value);
    storage?.setItem(legacy, value);
  } catch {
    // Ignore private-mode storage failures.
  }
}

/** Stop any in-progress repeating announcement (Acknowledge / Mute / unmount). */
export function stopPatientCallAnnouncement(synth?: SpeechSynthesis | null): void {
  activeAnnouncement = null;
  announcementToken += 1;
  const engine = synth === undefined ? defaultSynth() : synth;
  try {
    engine?.cancel();
  } catch {
    // best-effort
  }
}

export const stopNotificationAnnouncement = stopPatientCallAnnouncement;

export function activePatientCallAnnouncementId(): string | null {
  return activeAnnouncement?.callId || null;
}

export const activeNotificationAnnouncementId = activePatientCallAnnouncementId;

export function sanitizeSpokenName(value: string | null | undefined): string {
  return String(value || "")
    .replace(/[\r\n\t]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
}

/** Minimum announcement: doctor + patient only. */
export function spokenPatientCallText(input: {
  doctorName?: string | null;
  patientName?: string | null;
}): string {
  const doctorRaw = sanitizeSpokenName(input.doctorName) || "Doctor";
  const patient = sanitizeSpokenName(input.patientName) || "a patient";
  const doctor = /^dr\.?\s/i.test(doctorRaw) ? doctorRaw : `Dr. ${doctorRaw}`;
  return `${doctor} is calling ${patient}.`;
}

/** Speak only the staff-facing notification message (already minimized by the server). */
export function spokenNotificationText(input: {
  message?: string | null;
  title?: string | null;
  senderDisplay?: string | null;
  patientName?: string | null;
  eventType?: string | null;
}): string {
  if ((input.eventType || "") === "patient_called") {
    return spokenPatientCallText({
      doctorName: input.senderDisplay,
      patientName: input.patientName,
    });
  }
  const message = sanitizeSpokenName(input.message);
  if (message) {
    return message.endsWith(".") ? message : `${message}.`;
  }
  const title = sanitizeSpokenName(input.title);
  return title ? (title.endsWith(".") ? title : `${title}.`) : "New notification.";
}

export function readVoiceMuted(storage: Storage | null = defaultStorage()): boolean {
  return storageGet(storage, NOTIFICATION_VOICE_MUTED_KEY, PATIENT_CALL_VOICE_MUTED_KEY) === "1";
}

export function writeVoiceMuted(muted: boolean, storage: Storage | null = defaultStorage()): void {
  storageSet(storage, NOTIFICATION_VOICE_MUTED_KEY, PATIENT_CALL_VOICE_MUTED_KEY, muted ? "1" : "0");
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(VOICE_SETTINGS_CHANGED_EVENT));
  }
}

export function readVoiceUnlocked(storage: Storage | null = defaultStorage()): boolean {
  return storageGet(storage, NOTIFICATION_VOICE_UNLOCKED_KEY, PATIENT_CALL_VOICE_UNLOCKED_KEY) === "1";
}

export function writeVoiceUnlocked(unlocked: boolean, storage: Storage | null = defaultStorage()): void {
  storageSet(
    storage,
    NOTIFICATION_VOICE_UNLOCKED_KEY,
    PATIENT_CALL_VOICE_UNLOCKED_KEY,
    unlocked ? "1" : "0",
  );
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(VOICE_SETTINGS_CHANGED_EVENT));
  }
}

export function loadSpokenCallIds(storage: Storage | null = defaultSessionStorage()): Set<string> {
  try {
    const raw =
      storageGet(storage, NOTIFICATION_SPOKEN_IDS_KEY, PATIENT_CALL_SPOKEN_IDS_KEY) || "";
    if (!raw) {
      return new Set();
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return new Set();
    }
    return new Set(parsed.filter((id): id is string => typeof id === "string" && id.length > 0));
  } catch {
    return new Set();
  }
}

export function rememberSpokenCallId(
  callId: string,
  storage: Storage | null = defaultSessionStorage(),
  existing: Set<string> = loadSpokenCallIds(storage),
): Set<string> {
  const next = new Set(existing);
  next.add(callId);
  const trimmed = [...next].slice(-SPOKEN_IDS_CAP);
  try {
    const encoded = JSON.stringify(trimmed);
    storage?.setItem(NOTIFICATION_SPOKEN_IDS_KEY, encoded);
    storage?.setItem(PATIENT_CALL_SPOKEN_IDS_KEY, encoded);
  } catch {
    // Ignore private-mode storage failures.
  }
  return new Set(trimmed);
}

export const loadSpokenNotificationIds = loadSpokenCallIds;
export const rememberSpokenNotificationId = rememberSpokenCallId;

export function speechSupported(synth: SpeechSynthesis | null | undefined = defaultSynth()): boolean {
  return Boolean(synth && typeof SpeechSynthesisUtterance !== "undefined");
}

export function resolveSpeechLocale(preferred?: string | null): string {
  const fromDoc =
    typeof document !== "undefined" ? document.documentElement.lang?.trim() || "" : "";
  const raw = (preferred || fromDoc || "en").trim() || "en";
  if (raw.toLowerCase().startsWith("en")) {
    return raw.includes("-") ? raw : "en-NG";
  }
  return raw;
}

function pickVoice(voices: SpeechSynthesisVoice[], locale: string): SpeechSynthesisVoice | null {
  if (!voices.length) {
    return null;
  }
  const lower = locale.toLowerCase();
  const exact = voices.find((voice) => voice.lang.toLowerCase() === lower);
  if (exact) {
    return exact;
  }
  const prefix = lower.split("-")[0] || "en";
  const byLang = voices.find((voice) => voice.lang.toLowerCase().startsWith(prefix));
  if (byLang) {
    return byLang;
  }
  const english = voices.find((voice) => voice.lang.toLowerCase().startsWith("en"));
  return english || voices[0] || null;
}

function waitForVoices(synth: SpeechSynthesis, timeoutMs = 600): Promise<void> {
  if (synth.getVoices().length > 0) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const done = () => {
      try {
        synth.removeEventListener("voiceschanged", done);
      } catch {
        // Older engines may not implement removeEventListener the same way.
      }
      resolve();
    };
    try {
      synth.addEventListener("voiceschanged", done);
    } catch {
      resolve();
      return;
    }
    globalThis.setTimeout(done, timeoutMs);
  });
}

export type SpeakPatientCallResult =
  | { status: "spoken" }
  | { status: "skipped"; reason: "muted" | "duplicate" | "unsupported" }
  | { status: "failed"; reason: "error" | "blocked" };

function buildUtterance(
  text: string,
  locale: string,
  synth: SpeechSynthesis,
): SpeechSynthesisUtterance {
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = locale;
  utterance.volume = 1;
  utterance.rate = 1;
  utterance.pitch = 1;
  const voice = pickVoice(synth.getVoices(), locale);
  if (voice) {
    utterance.voice = voice;
  }
  return utterance;
}

function speakPhrase(
  text: string,
  locale: string,
  synth: SpeechSynthesis,
  isAborted: () => boolean,
): Promise<"ok" | "error" | "aborted"> {
  if (isAborted()) {
    return Promise.resolve("aborted");
  }
  return new Promise((resolve) => {
    try {
      try {
        synth.resume();
      } catch {
        // best-effort
      }
      const utterance = buildUtterance(text, locale, synth);
      let settled = false;
      const finish = (result: "ok" | "error" | "aborted") => {
        if (settled) {
          return;
        }
        settled = true;
        resolve(result);
      };
      utterance.onend = () => finish(isAborted() ? "aborted" : "ok");
      utterance.onerror = () => finish(isAborted() ? "aborted" : "error");
      synth.speak(utterance);
      if (isAborted()) {
        try {
          synth.cancel();
        } catch {
          // best-effort
        }
        finish("aborted");
      }
    } catch {
      resolve(isAborted() ? "aborted" : "error");
    }
  });
}

/**
 * Speak a patient-call announcement once (used for unlock / tests).
 * Marks the call id spoken only after the browser starts (or accepts) speech.
 */
export async function speakPatientCall(input: {
  callId: string;
  doctorName?: string | null;
  patientName?: string | null;
  text?: string | null;
  muted?: boolean;
  /** True after a receptionist gesture unlocked voice on this browser. */
  unlocked?: boolean;
  locale?: string | null;
  synth?: SpeechSynthesis | null;
  spokenIds?: Set<string>;
  storage?: Storage | null;
  confirmMs?: number;
}): Promise<SpeakPatientCallResult> {
  const callId = String(input.callId || "").trim();
  if (!callId) {
    return { status: "skipped", reason: "duplicate" };
  }
  if (input.muted) {
    return { status: "skipped", reason: "muted" };
  }
  const storage = input.storage === undefined ? defaultSessionStorage() : input.storage;
  const spokenIds = input.spokenIds || loadSpokenCallIds(storage);
  if (spokenIds.has(callId)) {
    return { status: "skipped", reason: "duplicate" };
  }
  const synth = input.synth === undefined ? defaultSynth() : input.synth;
  if (!synth || typeof SpeechSynthesisUtterance === "undefined") {
    return { status: "skipped", reason: "unsupported" };
  }

  const unlocked = input.unlocked ?? readVoiceUnlocked();
  const text = String(input.text || "").trim() || spokenPatientCallText(input);
  const confirmMs = input.confirmMs ?? 900;
  const locale = resolveSpeechLocale(input.locale);

  await waitForVoices(synth);

  return new Promise((resolve) => {
    let settled = false;
    const finish = (result: SpeakPatientCallResult) => {
      if (settled) {
        return;
      }
      settled = true;
      resolve(result);
    };

    try {
      try {
        synth.resume();
      } catch {
        // resume() is best-effort on engines that pause speechSynthesis.
      }
      const utterance = buildUtterance(text, locale, synth);
      utterance.onstart = () => {
        rememberSpokenCallId(callId, storage, spokenIds);
        finish({ status: "spoken" });
      };
      utterance.onerror = () => {
        finish({ status: "failed", reason: "blocked" });
      };
      synth.speak(utterance);
      globalThis.setTimeout(() => {
        if (settled) {
          return;
        }
        if (synth.speaking || synth.pending) {
          rememberSpokenCallId(callId, storage, spokenIds);
          finish({ status: "spoken" });
          return;
        }
        if (unlocked) {
          rememberSpokenCallId(callId, storage, spokenIds);
          finish({ status: "spoken" });
          return;
        }
        finish({ status: "failed", reason: "blocked" });
      }, confirmMs);
    } catch {
      finish({ status: "failed", reason: "error" });
    }
  });
}

/**
 * Repeat the call announcement until Reception acknowledges or duration elapses.
 * Stops immediately when stopPatientCallAnnouncement() is called.
 */
export async function startPatientCallAnnouncement(input: {
  callId: string;
  doctorName?: string | null;
  patientName?: string | null;
  text?: string | null;
  muted?: boolean;
  unlocked?: boolean;
  locale?: string | null;
  synth?: SpeechSynthesis | null;
  spokenIds?: Set<string>;
  storage?: Storage | null;
  confirmMs?: number;
  durationMs?: number;
  gapMs?: number;
}): Promise<SpeakPatientCallResult> {
  const callId = String(input.callId || "").trim();
  if (!callId) {
    return { status: "skipped", reason: "duplicate" };
  }
  if (input.muted) {
    return { status: "skipped", reason: "muted" };
  }
  const storage = input.storage === undefined ? defaultSessionStorage() : input.storage;
  const spokenIds = input.spokenIds || loadSpokenCallIds(storage);
  if (spokenIds.has(callId)) {
    return { status: "skipped", reason: "duplicate" };
  }
  const synth = input.synth === undefined ? defaultSynth() : input.synth;
  if (!synth || typeof SpeechSynthesisUtterance === "undefined") {
    return { status: "skipped", reason: "unsupported" };
  }

  stopPatientCallAnnouncement(synth);
  const token = ++announcementToken;
  activeAnnouncement = { token, callId };

  const first = await speakPatientCall({
    ...input,
    synth,
    storage,
    spokenIds,
  });
  if (activeAnnouncement?.token !== token) {
    // Reception acknowledged (or muted) while the first phrase was starting.
    return { status: "spoken" };
  }
  if (first.status !== "spoken") {
    if (activeAnnouncement?.token === token) {
      activeAnnouncement = null;
    }
    return first;
  }

  const text = String(input.text || "").trim() || spokenPatientCallText(input);
  const locale = resolveSpeechLocale(input.locale);
  const durationMs = input.durationMs ?? PATIENT_CALL_ANNOUNCE_MS;
  const gapMs = input.gapMs ?? PATIENT_CALL_REPEAT_GAP_MS;
  const deadline = Date.now() + durationMs;
  const isAborted = () => activeAnnouncement?.token !== token;

  // Let the opening phrase finish before repeating.
  const waitEndBy = Date.now() + 8_000;
  while (!isAborted() && (synth.speaking || synth.pending) && Date.now() < waitEndBy) {
    await delay(120);
  }

  while (!isAborted() && Date.now() < deadline) {
    await delay(gapMs);
    if (isAborted() || Date.now() >= deadline) {
      break;
    }
    const phrase = await speakPhrase(text, locale, synth, isAborted);
    if (phrase !== "ok") {
      break;
    }
  }

  if (activeAnnouncement?.token === token) {
    activeAnnouncement = null;
  }
  return { status: "spoken" };
}

export async function startNotificationAnnouncement(input: {
  id: string;
  eventType?: string | null;
  message?: string | null;
  title?: string | null;
  senderDisplay?: string | null;
  patientName?: string | null;
  muted?: boolean;
  unlocked?: boolean;
  locale?: string | null;
  synth?: SpeechSynthesis | null;
  spokenIds?: Set<string>;
  storage?: Storage | null;
  confirmMs?: number;
  durationMs?: number;
  gapMs?: number;
}): Promise<SpeakPatientCallResult> {
  return startPatientCallAnnouncement({
    callId: input.id,
    doctorName: input.senderDisplay,
    patientName: input.patientName,
    text: spokenNotificationText(input),
    muted: input.muted,
    unlocked: input.unlocked,
    locale: input.locale,
    synth: input.synth,
    spokenIds: input.spokenIds,
    storage: input.storage,
    confirmMs: input.confirmMs,
    durationMs: input.durationMs,
    gapMs: input.gapMs,
  });
}

/** One-time unlock after a receptionist gesture. */
export function unlockPatientCallVoice(input?: {
  synth?: SpeechSynthesis | null;
  locale?: string | null;
  storage?: Storage | null;
}): boolean {
  const synth = input?.synth === undefined ? defaultSynth() : input.synth;
  const storage = input?.storage === undefined ? defaultStorage() : input.storage;
  if (!speechSupported(synth) || !synth) {
    writeVoiceUnlocked(false, storage);
    return false;
  }
  try {
    try {
      synth.resume();
    } catch {
      // best-effort
    }
    const utterance = new SpeechSynthesisUtterance("Voice notifications enabled.");
    utterance.lang = resolveSpeechLocale(input?.locale);
    utterance.volume = 1;
    utterance.rate = 1;
    const voice = pickVoice(synth.getVoices(), resolveSpeechLocale(input?.locale));
    if (voice) {
      utterance.voice = voice;
    }
    synth.cancel();
    synth.speak(utterance);
    writeVoiceUnlocked(true, storage);
    return true;
  } catch {
    writeVoiceUnlocked(false, storage);
    return false;
  }
}

function defaultStorage(): Storage | null {
  try {
    return typeof localStorage !== "undefined" ? localStorage : null;
  } catch {
    return null;
  }
}

function defaultSessionStorage(): Storage | null {
  try {
    return typeof sessionStorage !== "undefined" ? sessionStorage : null;
  } catch {
    return null;
  }
}

function defaultSynth(): SpeechSynthesis | null {
  try {
    return typeof window !== "undefined" && "speechSynthesis" in window
      ? window.speechSynthesis
      : null;
  } catch {
    return null;
  }
}
