import { useEffect, useRef, useState } from "react";
import {
  fetchAttendanceTerminalConfig,
  lookupStaffAttendance,
  signInWithStaffCode,
  signOutWithStaffCode,
} from "../../services/attendance";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type {
  AttendanceActionPayload,
  AttendanceLookupPayload,
  AttendanceTerminalConfig,
} from "../../types/attendance";
import { formatLogClockShort } from "../Admin/adminStaffLogView";
import "./StaffLogTerminal.css";

const AUTO_RESET_MS = 4000;
const LOGO = `${import.meta.env.BASE_URL}abikan-logo.png`;

type Screen = "entry" | "ready" | "result" | "error";

function errorCopy(reason: unknown): string {
  if (reason instanceof PatientAccountRequestError || reason instanceof Error) {
    return reason.message;
  }
  return "Staff log could not be completed.";
}

function captureJpeg(video: HTMLVideoElement): string | null {
  if (!video.videoWidth || !video.videoHeight) {
    return null;
  }
  const longest = Math.max(video.videoWidth, video.videoHeight);
  const scale = Math.min(1, 480 / longest);
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
  canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.7);
}

export function StaffLogTerminal() {
  const [config, setConfig] = useState<AttendanceTerminalConfig | null>(null);
  const [screen, setScreen] = useState<Screen>("entry");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [lookup, setLookup] = useState<AttendanceLookupPayload | null>(null);
  const [result, setResult] = useState<AttendanceActionPayload | null>(null);
  const [error, setError] = useState("");
  const [cameraError, setCameraError] = useState("");
  const [cameraReady, setCameraReady] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const usedCodeRef = useRef("");

  const reset = () => {
    setScreen("entry");
    setBusy(false);
    setCode("");
    setLookup(null);
    setResult(null);
    setError("");
    setCameraError("");
    setCameraReady(false);
    usedCodeRef.current = "";
    window.setTimeout(() => inputRef.current?.focus(), 50);
  };

  useEffect(() => {
    void fetchAttendanceTerminalConfig()
      .then(setConfig)
      .catch(() => {
        setConfig(null);
      });
    inputRef.current?.focus();
  }, []);

  const needsCamera = screen === "ready" && lookup?.availableAction === "SIGN_IN";

  useEffect(() => {
    if (!needsCamera) {
      return;
    }
    let stream: MediaStream | null = null;
    let cancelled = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("This device cannot take a photo. Use the front-desk tablet.");
      return;
    }
    void navigator.mediaDevices
      .getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      })
      .then((media) => {
        if (cancelled) {
          media.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = media;
        const video = videoRef.current;
        if (video) {
          video.srcObject = media;
          void video.play();
        }
        setCameraReady(true);
      })
      .catch(() => {
        if (!cancelled) {
          setCameraError("This device cannot take a photo. Use the front-desk tablet.");
        }
      });
    return () => {
      cancelled = true;
      setCameraReady(false);
      stream?.getTracks().forEach((track) => track.stop());
      const video = videoRef.current;
      if (video) {
        video.srcObject = null;
      }
    };
  }, [needsCamera]);

  useEffect(() => {
    if (screen !== "result" && !(screen === "ready" && lookup?.attendanceStatus === "SIGNED_OUT")) {
      return;
    }
    const timer = window.setTimeout(() => {
      reset();
    }, AUTO_RESET_MS);
    return () => window.clearTimeout(timer);
  }, [screen, lookup?.attendanceStatus, result?.session.id, result?.attendanceStatus]);

  const checkCode = async () => {
    const value = code.trim();
    if (!value) {
      setError("Enter your staff code");
      setScreen("error");
      return;
    }
    setBusy(true);
    setError("");
    usedCodeRef.current = value;
    try {
      const payload = await lookupStaffAttendance(value);
      setLookup(payload);
      setScreen("ready");
    } catch (reason) {
      setError(errorCopy(reason));
      setScreen("error");
    } finally {
      setBusy(false);
    }
  };

  const confirmAction = async () => {
    const value = usedCodeRef.current;
    const action = lookup?.availableAction;
    if (!value || !action || busy) {
      return;
    }
    let photo = "";
    if (action === "SIGN_IN") {
      const video = videoRef.current;
      photo = (video && captureJpeg(video)) || "";
      if (!photo) {
        setError(cameraError || "Look at the camera, then tap Sign in.");
        setScreen("error");
        return;
      }
    }
    setBusy(true);
    try {
      const payload =
        action === "SIGN_IN"
          ? await signInWithStaffCode(value, photo)
          : await signOutWithStaffCode(value);
      setResult(payload);
      setScreen("result");
    } catch (reason) {
      setError(errorCopy(reason));
      setScreen("error");
    } finally {
      setBusy(false);
    }
  };

  const signedIn = result?.attendanceStatus === "SIGNED_IN";
  const signedOut = result?.attendanceStatus === "SIGNED_OUT";
  const lookupComplete = lookup?.attendanceStatus === "SIGNED_OUT";
  const signingIn = lookup?.availableAction === "SIGN_IN";

  return (
    <div className="staff-log">
      <aside className="staff-log__brand">
        <div className="staff-log__brand-mark">
          <img src={LOGO} alt="Hospital EMR" />
          <h1>Staff log</h1>
        </div>
        <p className="staff-log__copy">Enter your staff code to start or finish your day.</p>
        {config?.displayDate ? <p className="staff-log__date">{config.displayDate}</p> : null}
      </aside>

      <main className="staff-log__stage">
        {screen === "entry" ? (
          <div className="staff-log__panel">
            <h1 className="staff-log__title">Your staff code</h1>
            <label className="staff-log__code">
              <span>Staff Code</span>
              <input
                ref={inputRef}
                value={code}
                onChange={(event) => setCode(event.target.value.toUpperCase())}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void checkCode();
                  }
                }}
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="characters"
                spellCheck={false}
                disabled={busy}
                maxLength={8}
                aria-label="Staff code"
              />
            </label>
            <button
              type="button"
              className="staff-log__action staff-log__action--in"
              onClick={() => void checkCode()}
              disabled={busy}
            >
              {busy ? "Please wait" : "Continue"}
            </button>
          </div>
        ) : null}

        {screen === "ready" && lookup ? (
          lookupComplete ? (
            <div className="staff-log__panel staff-log__panel--done">
              <p className="staff-log__kicker">Finished for today</p>
              <h1 className="staff-log__title">{lookup.staff.displayName}</h1>
              <p className="staff-log__meta">
                {lookup.session?.signInLocalTime
                  ? `In ${formatLogClockShort(lookup.session.signInLocalTime)}`
                  : ""}
                {lookup.session?.signOutLocalTime
                  ? `  ·  Out ${formatLogClockShort(lookup.session.signOutLocalTime)}`
                  : ""}
              </p>
            </div>
          ) : (
            <div className="staff-log__panel">
              <p className="staff-log__kicker">{lookup.staff.workplaceLabel}</p>
              <h1 className="staff-log__title">{lookup.staff.displayName}</h1>
              {signingIn ? (
                <div className={`staff-log__portrait${cameraReady ? " staff-log__portrait--live" : ""}`}>
                  <video ref={videoRef} autoPlay playsInline muted />
                </div>
              ) : null}
              <p className="staff-log__help">
                {signingIn
                  ? cameraError || "Look at the camera, then tap Sign in."
                  : "Tap Sign out to finish today."}
              </p>
              <button
                type="button"
                className={`staff-log__action ${
                  lookup.availableAction === "SIGN_OUT"
                    ? "staff-log__action--out"
                    : "staff-log__action--in"
                }`}
                onClick={() => void confirmAction()}
                disabled={busy || (signingIn && (!cameraReady || Boolean(cameraError)))}
              >
                {busy ? "Please wait" : lookup.availableAction === "SIGN_OUT" ? "Sign out" : "Sign in"}
              </button>
              <button type="button" className="staff-log__back" onClick={reset} disabled={busy}>
                Use a different code
              </button>
            </div>
          )
        ) : null}

        {screen === "result" && result ? (
          <div className="staff-log__panel staff-log__panel--done">
            <p className="staff-log__kicker">{signedOut ? "Finished for today" : "Signed in"}</p>
            <h1 className="staff-log__title">{result.staff.displayName}</h1>
            {signedIn ? <p className="staff-log__workplace">{result.staff.workplaceLabel}</p> : null}
            <p className="staff-log__meta">
              In {formatLogClockShort(result.session.signInLocalTime)}
              {signedOut && result.session.signOutLocalTime
                ? `  ·  Out ${formatLogClockShort(result.session.signOutLocalTime)}`
                : ""}
            </p>
          </div>
        ) : null}

        {screen === "error" ? (
          <div className="staff-log__panel">
            <h1 className="staff-log__title">{error || "That staff code is not recognized."}</h1>
            <p className="staff-log__help">If this continues, contact Administration.</p>
            <button type="button" className="staff-log__action staff-log__action--in" onClick={reset}>
              Try again
            </button>
          </div>
        ) : null}
      </main>
    </div>
  );
}
