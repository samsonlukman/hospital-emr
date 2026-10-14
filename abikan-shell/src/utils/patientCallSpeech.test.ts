import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  activePatientCallAnnouncementId,
  loadSpokenCallIds,
  rememberSpokenCallId,
  resolveSpeechLocale,
  sanitizeSpokenName,
  speakPatientCall,
  spokenPatientCallText,
  startPatientCallAnnouncement,
  stopPatientCallAnnouncement,
} from "./patientCallSpeech.ts";

class FakeUtterance {
  text: string;
  lang = "";
  volume = 1;
  rate = 1;
  pitch = 1;
  voice: SpeechSynthesisVoice | null = null;
  onstart: ((event: SpeechSynthesisEvent) => void) | null = null;
  onend: ((event: SpeechSynthesisEvent) => void) | null = null;
  onerror: ((event: SpeechSynthesisErrorEvent) => void) | null = null;
  constructor(text: string) {
    this.text = text;
  }
}

(globalThis as { SpeechSynthesisUtterance?: typeof FakeUtterance }).SpeechSynthesisUtterance =
  FakeUtterance;

describe("patient call speech", () => {
  it("speaks only doctor and patient names", () => {
    assert.equal(
      spokenPatientCallText({ doctorName: "Dr. Musa", patientName: "Ahmed Bello" }),
      "Dr. Musa is calling Ahmed Bello.",
    );
    assert.equal(
      spokenPatientCallText({ doctorName: "Amina Bello", patientName: "Funke Sync Verify" }),
      "Dr. Amina Bello is calling Funke Sync Verify.",
    );
  });

  it("does not invent clinical details into the announcement", () => {
    const text = spokenPatientCallText({
      doctorName: "Dr. Musa",
      patientName: "Ahmed Bello",
    });
    assert.equal(text.includes("MRN"), false);
    assert.equal(text.includes("Visit"), false);
    assert.equal(text.includes("diagnosis"), false);
  });

  it("sanitizes names before speaking", () => {
    assert.equal(sanitizeSpokenName("  Ahmed\nBello\t "), "Ahmed Bello");
    assert.equal(sanitizeSpokenName("a".repeat(100)).length, 80);
  });

  it("defaults locale to English Nigeria when app lang is English", () => {
    assert.equal(resolveSpeechLocale("en"), "en-NG");
    assert.equal(resolveSpeechLocale("en-GB"), "en-GB");
    assert.equal(resolveSpeechLocale(""), "en-NG");
  });

  it("remembers spoken call ids so duplicates and refreshes stay quiet", async () => {
    const storage = memoryStorage();
    const first = rememberSpokenCallId("call-1", storage);
    assert.equal(first.has("call-1"), true);
    assert.equal(loadSpokenCallIds(storage).has("call-1"), true);

    const muted = await speakPatientCall({
      callId: "call-2",
      doctorName: "Dr. Musa",
      patientName: "Ahmed",
      muted: true,
      storage,
      spokenIds: first,
      synth: null,
    });
    assert.deepEqual(muted, { status: "skipped", reason: "muted" });

    const dup = await speakPatientCall({
      callId: "call-1",
      doctorName: "Dr. Musa",
      patientName: "Ahmed",
      muted: false,
      storage,
      spokenIds: first,
      synth: null,
    });
    assert.deepEqual(dup, { status: "skipped", reason: "duplicate" });
  });

  it("speaks through the browser synth and ignores duplicate delivery", async () => {
    const storage = memoryStorage();
    const synth = fakeSynth({ mode: "start" });
    const result = await speakPatientCall({
      callId: "call-9",
      doctorName: "Dr. Musa",
      patientName: "Ahmed Bello",
      muted: false,
      storage,
      synth,
      confirmMs: 20,
    });
    assert.deepEqual(result, { status: "spoken" });
    assert.equal(synth.spoken.length, 1);
    assert.equal(synth.spoken[0], "Dr. Musa is calling Ahmed Bello.");
    assert.equal(loadSpokenCallIds(storage).has("call-9"), true);

    const again = await speakPatientCall({
      callId: "call-9",
      doctorName: "Dr. Musa",
      patientName: "Ahmed Bello",
      muted: false,
      storage,
      synth,
      confirmMs: 20,
    });
    assert.deepEqual(again, { status: "skipped", reason: "duplicate" });
    assert.equal(synth.spoken.length, 1);
  });

  it("reports blocked when the browser accepts speak but does not start", async () => {
    const storage = memoryStorage();
    const synth = fakeSynth({ mode: "silent" });
    const result = await speakPatientCall({
      callId: "call-blocked",
      doctorName: "Dr. Musa",
      patientName: "Ahmed Bello",
      unlocked: false,
      storage,
      synth,
      confirmMs: 20,
    });
    assert.deepEqual(result, { status: "failed", reason: "blocked" });
    assert.equal(loadSpokenCallIds(storage).has("call-blocked"), false);
  });

  it("treats speech as accepted after unlock even if speaking flags lag", async () => {
    const storage = memoryStorage();
    const synth = fakeSynth({ mode: "silent" });
    const result = await speakPatientCall({
      callId: "call-unlocked",
      doctorName: "Dr. Musa",
      patientName: "Ahmed Bello",
      unlocked: true,
      storage,
      synth,
      confirmMs: 20,
    });
    assert.deepEqual(result, { status: "spoken" });
    assert.equal(loadSpokenCallIds(storage).has("call-unlocked"), true);
  });

  it("repeats the announcement until stopped or the duration ends", async () => {
    const storage = memoryStorage();
    const synth = fakeSynth({ mode: "start" });
    const result = await startPatientCallAnnouncement({
      callId: "call-loop",
      doctorName: "Dr. Musa",
      patientName: "Ahmed Bello",
      unlocked: true,
      storage,
      synth,
      confirmMs: 20,
      durationMs: 80,
      gapMs: 10,
    });
    assert.deepEqual(result, { status: "spoken" });
    assert.ok(synth.spoken.length >= 2);
    assert.equal(synth.spoken[0], "Dr. Musa is calling Ahmed Bello.");
  });

  it("stops repeating when acknowledge cancels the announcement", async () => {
    const storage = memoryStorage();
    const synth = fakeSynth({ mode: "start" });
    const pending = startPatientCallAnnouncement({
      callId: "call-stop",
      doctorName: "Dr. Musa",
      patientName: "Ahmed Bello",
      unlocked: true,
      storage,
      synth,
      confirmMs: 20,
      durationMs: 500,
      gapMs: 20,
    });
    await delay(40);
    stopPatientCallAnnouncement(synth);
    const result = await pending;
    assert.deepEqual(result, { status: "spoken" });
    assert.equal(activePatientCallAnnouncementId(), null);
  });
});

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear() {
      map.clear();
    },
    getItem(key: string) {
      return map.has(key) ? map.get(key)! : null;
    },
    key(index: number) {
      return [...map.keys()][index] ?? null;
    },
    removeItem(key: string) {
      map.delete(key);
    },
    setItem(key: string, value: string) {
      map.set(key, String(value));
    },
  };
}

function fakeSynth(state: { mode: "start" | "silent" | "pending" }): SpeechSynthesis & {
  spoken: string[];
} {
  const spoken: string[] = [];
  const synth = {
    spoken,
    speaking: false,
    pending: false,
    paused: false,
    onvoiceschanged: null,
    cancel() {},
    getVoices() {
      return [
        {
          lang: "en-NG",
          name: "Test",
          default: true,
          localService: true,
          voiceURI: "test",
        },
      ] as SpeechSynthesisVoice[];
    },
    pause() {},
    resume() {},
    speak(utterance: SpeechSynthesisUtterance) {
      spoken.push(utterance.text);
      if (state.mode === "start") {
        this.speaking = true;
        queueMicrotask(() => {
          utterance.onstart?.(null as unknown as SpeechSynthesisEvent);
          this.speaking = false;
          utterance.onend?.(null as unknown as SpeechSynthesisEvent);
        });
      } else if (state.mode === "pending") {
        this.pending = true;
      } else {
        this.speaking = false;
        this.pending = false;
      }
    },
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return false;
    },
  };
  return synth as SpeechSynthesis & { spoken: string[] };
}
