import { useState } from "react";
import { Card } from "../../components/Card";
import { PageHeader } from "../../components/PageHeader";
import {
  readTheme,
  writeTheme,
  type AppTheme,
} from "../../utils/appearanceSettings";
import {
  readVoiceMuted,
  readVoiceUnlocked,
  speechSupported,
  unlockPatientCallVoice,
  writeVoiceMuted,
  writeVoiceUnlocked,
} from "../../utils/patientCallSpeech";
import "./SystemSettingsWorkspace.css";

export function SystemSettingsWorkspace() {
  const [theme, setTheme] = useState<AppTheme>(() => readTheme());
  const [voiceMuted, setVoiceMuted] = useState(() => readVoiceMuted());
  const [voiceUnlocked, setVoiceUnlocked] = useState(() => readVoiceUnlocked());
  const voiceAvailable = speechSupported();

  const toggleVoice = () => {
    if (!voiceMuted && !voiceUnlocked) {
      const unlocked = unlockPatientCallVoice();
      if (unlocked) {
        writeVoiceUnlocked(true);
        setVoiceUnlocked(true);
      }
      return;
    }
    if (!voiceMuted) {
      writeVoiceMuted(true);
      setVoiceMuted(true);
      return;
    }

    if (!voiceUnlocked) {
      const unlocked = unlockPatientCallVoice();
      if (!unlocked) {
        setVoiceUnlocked(false);
        return;
      }
      writeVoiceUnlocked(true);
      setVoiceUnlocked(true);
    }
    writeVoiceMuted(false);
    setVoiceMuted(false);
  };

  const toggleTheme = () => {
    const next = theme === "light" ? "dark" : "light";
    writeTheme(next);
    setTheme(next);
  };

  return (
    <div className="system-settings">
      <PageHeader
        title="System Settings"
        description="Personal preferences for this workstation."
      />
      <div className="system-settings__grid">
        <Card>
          <div className="system-settings__row">
            <div>
              <h2>Voice announcements</h2>
              <p>
                Read urgent patient and service alerts aloud. Normal messages
                remain a short notification beep.
              </p>
              {!voiceAvailable ? (
                <small>Voice announcements are not supported in this browser.</small>
              ) : !voiceUnlocked ? (
                <small>Click the toggle once to allow browser voice notifications.</small>
              ) : null}
            </div>
            <button
              type="button"
              className="system-settings__switch"
              role="switch"
              aria-checked={!voiceMuted}
              disabled={!voiceAvailable}
              onClick={toggleVoice}
            >
              <span aria-hidden="true" />
              <strong>{voiceMuted ? "Off" : "On"}</strong>
            </button>
          </div>
        </Card>
        <Card>
          <div className="system-settings__row">
            <div>
              <h2>Appearance</h2>
              <p>Choose the display style used throughout Hospital EMR.</p>
            </div>
            <button
              type="button"
              className="system-settings__switch"
              role="switch"
              aria-checked={theme === "dark"}
              onClick={toggleTheme}
            >
              <span aria-hidden="true" />
              <strong>{theme === "dark" ? "Dark" : "Light"}</strong>
            </button>
          </div>
          <p className="system-settings__current">
            Current mode: <strong>{theme === "light" ? "Light" : "Dark"}</strong>
          </p>
        </Card>
      </div>
    </div>
  );
}
