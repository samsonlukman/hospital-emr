import { useEffect, useRef, useState } from "react";
import { Button } from "./Button";
import { AppIcon } from "./icons";
import {
  acknowledgeNotification,
  dailyVisitNumberFromNotification,
  fetchStaffNotifications,
  markNotificationRead,
  type StaffNotification,
} from "../services/notifications";
import { acknowledgeAttention } from "../services/messaging";
import { ACTIVE_MESSAGE_CONVERSATION_EVENT } from "../services/messaging";
import type { WorkspaceContext } from "../types";
import type { ShellRoute } from "../app/hashRoute";
import { formatDailyVisitNumber } from "../utils/dailyVisitNumber";
import {
  NOTIFICATION_ANNOUNCE_MS,
  loadSpokenNotificationIds,
  readVoiceMuted,
  readVoiceUnlocked,
  rememberSpokenNotificationId,
  playMessageBeep,
  speechSupported,
  startNotificationAnnouncement,
  stopNotificationAnnouncement,
  VOICE_SETTINGS_CHANGED_EVENT,
  writeVoiceUnlocked,
} from "../utils/patientCallSpeech";
import "./StaffNotificationCenter.css";

const POLL_MS = 4000;
const CHIME_REPEAT_MS = 2000;

interface StaffNotificationCenterProps {
  context: WorkspaceContext;
  route: ShellRoute;
  onPendingCountChange?: (count: number) => void;
  listOpen?: boolean;
  onListClose?: () => void;
}

function unlockAudio(ctx: AudioContext) {
  if (ctx.state === "suspended") {
    void ctx.resume();
  }
}

function playCallChime(ctx: AudioContext | null) {
  if (!ctx) {
    return false;
  }
  try {
    unlockAudio(ctx);
    const now = ctx.currentTime;
    const gain = ctx.createGain();
    gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.22, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.55);

    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, now);
    osc.frequency.setValueAtTime(1174.7, now + 0.18);
    osc.connect(gain);
    osc.start(now);
    osc.stop(now + 0.56);
    return true;
  } catch {
    return false;
  }
}

function displayLine(note: StaffNotification): string {
  if (note.eventType === "message_received") {
    return `${note.senderDisplay || "A staff member"} sent you a message.`;
  }
  if (note.eventType === "department_attention_requested") {
    return note.message || "A department is calling you.";
  }
  if (note.eventType === "patient_called") {
    const doctor = (note.senderDisplay || "Doctor").trim();
    const patient = (note.patientName || "a patient").trim();
    const doctorLabel = /^dr\.?\s/i.test(doctor) ? doctor : `Dr. ${doctor}`;
    return `${doctorLabel} is calling ${patient}.`;
  }
  if (note.eventType === "prescription_created") {
    const patient = (note.patientName || "a patient").trim();
    return `New prescription for ${patient}.`;
  }
  return note.message || note.title || "New notification.";
}

function notificationDetail(note: StaffNotification): string {
  if (note.eventType !== "prescription_created") {
    return "";
  }
  const detail = String(note.payload?.detail || "").trim();
  if (detail) {
    return detail;
  }
  const doctor = (note.senderDisplay || "").trim();
  const count = Number(note.payload?.medicineCount || 0);
  if (doctor && count > 1) {
    return `${doctor} · ${count} medicines`;
  }
  return doctor;
}

/** Notifications belong to the signed-in staff member, not the screen they opened. */
function centerEnabled(context: WorkspaceContext): boolean {
  return Boolean(context.username?.trim());
}

function notesForWorkplace(notes: StaffNotification[]): StaffNotification[] {
  return notes;
}

function needsAttentionSound(note: StaffNotification): boolean {
  return note.speak || note.priority === "high" || note.priority === "urgent";
}

function attentionIdForNote(note: StaffNotification | undefined): string {
  if (note?.eventType !== "department_attention_requested") {
    return "";
  }
  const value = note.payload?.attentionRequestId;
  return typeof value === "string" ? value : "";
}

function isQuietNotification(note: StaffNotification): boolean {
  return (
    note.eventType === "message_received" ||
    note.eventType === "department_attention_acknowledged"
  );
}

function notificationTime(note: StaffNotification): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(note.createdAt));
}

export function StaffNotificationCenter({
  context,
  onPendingCountChange,
  listOpen = false,
  onListClose,
}: StaffNotificationCenterProps) {
  const enabled = centerEnabled(context);
  const [notes, setNotes] = useState<StaffNotification[]>([]);
  const [acking, setAcking] = useState<string | null>(null);
  const [voiceMuted, setVoiceMuted] = useState(() => readVoiceMuted());
  const [voiceUnlocked, setVoiceUnlocked] = useState(() => readVoiceUnlocked());
  const [activeMessageConversationId, setActiveMessageConversationId] = useState("");
  const knownIds = useRef<Set<string>>(new Set());
  const spokenIds = useRef<Set<string>>(loadSpokenNotificationIds());
  const seeded = useRef(false);
  const audioCtx = useRef<AudioContext | null>(null);
  const mounted = useRef(true);
  const voiceMutedRef = useRef(voiceMuted);
  const voiceUnlockedRef = useRef(voiceUnlocked);
  const notesRef = useRef(notes);
  const activeMessageConversationRef = useRef("");
  const chimeTimer = useRef<number | null>(null);

  const stopChimeLoop = () => {
    if (chimeTimer.current != null) {
      window.clearTimeout(chimeTimer.current);
      chimeTimer.current = null;
    }
  };

  const stopAllAlerts = () => {
    stopNotificationAnnouncement();
    stopChimeLoop();
  };

  useEffect(() => {
    voiceMutedRef.current = voiceMuted;
  }, [voiceMuted]);

  useEffect(() => {
    voiceUnlockedRef.current = voiceUnlocked;
  }, [voiceUnlocked]);

  useEffect(() => {
    const syncVoiceSettings = () => {
      const muted = readVoiceMuted();
      setVoiceMuted(muted);
      setVoiceUnlocked(readVoiceUnlocked());
      if (muted) {
        stopAllAlerts();
      }
    };
    window.addEventListener(VOICE_SETTINGS_CHANGED_EVENT, syncVoiceSettings);
    return () => window.removeEventListener(VOICE_SETTINGS_CHANGED_EVENT, syncVoiceSettings);
  }, []);

  useEffect(() => {
    const syncActiveConversation = (event: Event) => {
      const id = (event as CustomEvent<string>).detail || "";
      activeMessageConversationRef.current = id;
      setActiveMessageConversationId(id);
    };
    window.addEventListener(ACTIVE_MESSAGE_CONVERSATION_EVENT, syncActiveConversation);
    return () => window.removeEventListener(ACTIVE_MESSAGE_CONVERSATION_EVENT, syncActiveConversation);
  }, []);

  useEffect(() => {
    onPendingCountChange?.(
      notes.filter(
        (note) =>
          note.status === "pending" &&
          !(
            note.eventType === "message_received" &&
            note.payload?.conversationId === activeMessageConversationId
          ),
      ).length,
    );
  }, [activeMessageConversationId, notes, onPendingCountChange]);

  useEffect(() => {
    notesRef.current = notes;
  }, [notes]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      stopAllAlerts();
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      stopAllAlerts();
      setNotes([]);
      onPendingCountChange?.(0);
      seeded.current = false;
      knownIds.current.clear();
      return;
    }

    const ensureAudio = () => {
      if (!audioCtx.current) {
        const Ctx =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (Ctx) {
          audioCtx.current = new Ctx();
        }
      }
      if (audioCtx.current) {
        unlockAudio(audioCtx.current);
      }
    };

    const startChimeLoop = () => {
      stopChimeLoop();
      ensureAudio();
      const deadline = Date.now() + NOTIFICATION_ANNOUNCE_MS;
      const tick = () => {
        if (!mounted.current || Date.now() >= deadline) {
          chimeTimer.current = null;
          return;
        }
        playCallChime(audioCtx.current);
        chimeTimer.current = window.setTimeout(tick, CHIME_REPEAT_MS);
      };
      tick();
    };

    const playAttentionChimeOnce = () => {
      ensureAudio();
      playCallChime(audioCtx.current);
    };

    const announceFresh = async (fresh: StaffNotification[]) => {
      if (fresh.length === 0) {
        return;
      }
      const operational = fresh.filter((note) => !isQuietNotification(note));
      const messageNotes = fresh.filter(
        (note) =>
          note.eventType === "message_received" &&
          note.payload?.conversationId !== activeMessageConversationRef.current,
      );
      const speakable = operational.filter((note) => note.speak);
      const audible = operational.filter((note) => needsAttentionSound(note));
      if (voiceMutedRef.current) {
        for (const note of fresh) {
          spokenIds.current = rememberSpokenNotificationId(note.id, undefined, spokenIds.current);
        }
        return;
      }

      if (messageNotes.length > 0) {
        playMessageBeep();
      }

      if (!speechSupported()) {
        if (audible.length > 0) {
          startChimeLoop();
        }
        for (const note of fresh) {
          spokenIds.current = rememberSpokenNotificationId(note.id, undefined, spokenIds.current);
        }
        return;
      }

      if (speakable.length === 0) {
        if (audible.length > 0) {
          playAttentionChimeOnce();
        }
        for (const note of fresh) {
          spokenIds.current = rememberSpokenNotificationId(note.id, undefined, spokenIds.current);
        }
        return;
      }

      const primary = speakable[0];
      for (const note of fresh) {
        if (note.id !== primary.id) {
          spokenIds.current = rememberSpokenNotificationId(note.id, undefined, spokenIds.current);
        }
      }

      stopChimeLoop();
      const result = await startNotificationAnnouncement({
        id: primary.id,
        eventType: primary.eventType,
        message: primary.message,
        title: primary.title,
        senderDisplay: primary.senderDisplay,
        patientName: primary.patientName,
        muted: false,
        unlocked: voiceUnlockedRef.current,
        spokenIds: spokenIds.current,
      });

      if (!mounted.current) {
        return;
      }

      if (result.status === "spoken") {
        spokenIds.current = rememberSpokenNotificationId(primary.id, undefined, spokenIds.current);
        writeVoiceUnlocked(true);
        voiceUnlockedRef.current = true;
        setVoiceUnlocked(true);
        return;
      }
      if (result.status === "failed") {
        startChimeLoop();
        return;
      }
      if (result.status === "skipped" && result.reason === "unsupported") {
        startChimeLoop();
      }
    };

    const poll = async () => {
      try {
        const payload = await fetchStaffNotifications();
        if (!mounted.current) {
          return;
        }
        const scoped = notesForWorkplace(
          (payload.notifications || []).filter(
            (note) => note.status === "pending" || note.status === "read",
          ),
        );
        if (!seeded.current) {
          for (const note of scoped) {
            knownIds.current.add(note.id);
          }
          seeded.current = true;
          setNotes(scoped);
          onPendingCountChange?.(scoped.filter((note) => note.status === "pending").length);
          return;
        }
        const fresh = scoped.filter((note) => !knownIds.current.has(note.id));
        for (const note of scoped) {
          knownIds.current.add(note.id);
        }
        if (fresh.length > 0) {
          await announceFresh(fresh);
        }
        setNotes(scoped);
        onPendingCountChange?.(scoped.filter((note) => note.status === "pending").length);
      } catch {
        // Stay quiet on transient poll failures; UI keeps last known state.
      }
    };

    void poll();
    const timer = window.setInterval(() => {
      void poll();
    }, POLL_MS);
    return () => {
      window.clearInterval(timer);
      stopAllAlerts();
    };
  }, [enabled, onPendingCountChange]);

  if (!enabled) {
    return null;
  }

  const dismiss = async (noteId: string) => {
    setAcking(noteId);
    stopAllAlerts();
    try {
      const attentionId = attentionIdForNote(notesRef.current.find((note) => note.id === noteId));
      if (attentionId) {
        await acknowledgeAttention(attentionId);
      } else {
        await acknowledgeNotification(noteId);
      }
      setNotes((current) => {
        const next = current.filter((note) => note.id !== noteId);
        onPendingCountChange?.(next.filter((note) => note.status === "pending").length);
        return next;
      });
    } catch {
      // Keep the banner visible if ack failed.
    } finally {
      setAcking(null);
    }
  };

  const openNotification = async (note: StaffNotification) => {
    stopAllAlerts();
    try {
      if (note.status === "pending") {
        await markNotificationRead(note.id);
      }
    } catch {
      // Navigation is still useful if the read mutation is temporarily unavailable.
    }
    setNotes((current) => {
      const next = current.map((item) =>
        item.id === note.id ? { ...item, status: "read" as const } : item,
      );
      onPendingCountChange?.(next.filter((item) => item.status === "pending").length);
      return next;
    });
    if (note.actionHref) {
      window.location.hash = note.actionHref.startsWith("#")
        ? note.actionHref
        : `#${note.actionHref}`;
    }
    onListClose?.();
  };

  const operationalNotes = notes.filter(
    (note) => !isQuietNotification(note) && note.status === "pending",
  );
  const visibleNotes = notes.filter(
    (note) =>
      !(
        note.eventType === "message_received" &&
        note.payload?.conversationId === activeMessageConversationId
      ),
  );
  const primary = operationalNotes[0];
  const daily = primary ? dailyVisitNumberFromNotification(primary) : "";
  const detail = primary ? notificationDetail(primary) : "";
  const showHospitalNumber = Boolean(
    primary?.mrn && primary.mrn !== "—" && primary.eventType !== "department_attention_requested",
  );

  return (
    <>
      {primary ? (
        <div
          className="patient-call-banner"
          role="alertdialog"
          aria-live="assertive"
          aria-label={primary.title || "Staff notification"}
          onClick={() => void openNotification(primary)}
        >
          <div className="patient-call-banner__pulse" aria-hidden="true" />
          <div className="patient-call-banner__body">
            <p className="patient-call-banner__eyebrow">
              <AppIcon name="bell" size={14} className="patient-call-banner__bell" />
              {primary.title || "Notification"}
            </p>
            <p className="patient-call-banner__title">{displayLine(primary)}</p>
            <p className="patient-call-banner__meta">
              {detail ? `${detail}${showHospitalNumber ? " · " : ""}` : ""}
              {showHospitalNumber ? `Hospital number ${primary.mrn}` : ""}
              {daily ? ` · Visit No. ${formatDailyVisitNumber(daily)}` : ""}
              {operationalNotes.length > 1 ? ` · +${operationalNotes.length - 1} more waiting` : ""}
            </p>
          </div>
          <div className="patient-call-banner__actions">
            <Button
              variant="primary"
              busy={acking === primary.id}
              busyLabel="Saving…"
              onClick={(event) => {
                event.stopPropagation();
                void dismiss(primary.id);
              }}
            >
              Acknowledge
            </Button>
            {operationalNotes.length > 1 ? (
              <Button
                variant="secondary"
                disabled={acking != null}
                onClick={(event) => {
                  event.stopPropagation();
                  void (async () => {
                    stopAllAlerts();
                    for (const note of operationalNotes) {
                      await dismiss(note.id);
                    }
                  })();
                }}
              >
                Dismiss all
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
      {listOpen ? (
        <section className="staff-notification-list" aria-label="Notifications">
          <div className="staff-notification-list__header">
            <strong>Notifications</strong>
            <Button variant="secondary" onClick={() => onListClose?.()}>Close</Button>
          </div>
          {visibleNotes.length === 0 ? (
            <p className="staff-notification-list__empty">No notifications right now.</p>
          ) : (
            visibleNotes.map((note) => (
              <article
                className={`staff-notification-list__item${note.status === "pending" ? " is-unread" : ""}`}
                key={note.id}
                role="button"
                tabIndex={0}
                onClick={() => void openNotification(note)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    void openNotification(note);
                  }
                }}
              >
                <div>
                  <strong>{note.title || "Notification"}</strong>
                  <p>{displayLine(note)}</p>
                  <time>{notificationTime(note)}</time>
                </div>
                <div className="staff-notification-list__actions">
                  {!isQuietNotification(note) ? (
                    <Button
                      variant="primary"
                      busy={acking === note.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        void dismiss(note.id);
                      }}
                    >
                      Acknowledge
                    </Button>
                  ) : null}
                </div>
              </article>
            ))
          )}
        </section>
      ) : null}
    </>
  );
}

/** @deprecated Use StaffNotificationCenter. Kept as a Phase-1 alias. */
export const PatientCallBanner = StaffNotificationCenter;
