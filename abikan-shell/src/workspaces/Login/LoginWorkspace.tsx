import { useRef, useState, type FormEvent } from "react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import {
  InvalidCredentialsError,
  NetworkError,
  SessionInitError,
  signInToHospital EMR,
} from "../../services/openmrs/signIn";
import "./LoginWorkspace.css";

interface LoginWorkspaceProps {
  onComplete: () => Promise<void> | void;
}

function messageFor(error: unknown): { title: string; body: string } {
  if (error instanceof InvalidCredentialsError) {
    return {
      title: "Could not sign in",
      body: "Incorrect username or password.",
    };
  }
  if (error instanceof NetworkError) {
    return {
      title: "Unable to connect",
      body: "Unable to connect. Please try again.",
    };
  }
  if (error instanceof SessionInitError) {
    return {
      title: "Session did not start",
      body: "Signed in, but Hospital EMR could not start your session. Please try again.",
    };
  }
  return {
    title: "Could not sign in",
    body: "Unable to connect. Please try again.",
  };
}

export function LoginWorkspace({ onComplete }: LoginWorkspaceProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ title: string; body: string } | null>(null);
  const inFlight = useRef(false);

  const handleSignIn = async (event: FormEvent) => {
    event.preventDefault();
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setError(null);
    setBusy(true);
    try {
      await signInToHospital EMR(username.trim(), password);
      await onComplete();
    } catch (reason) {
      setError(messageFor(reason));
      setBusy(false);
      inFlight.current = false;
    }
  };

  return (
    <div className="abikan-login">
      <aside className="abikan-login__brand">
        <img src={`${import.meta.env.BASE_URL}abikan-logo.png`} alt="Hospital EMR" />
        <p className="abikan-login__product">Hospital EMR</p>
        <p className="abikan-login__copy">
          Sign in with your hospital username. You will open your department directly.
        </p>
      </aside>
      <main className="abikan-login__panel">
        <form className="abikan-login__form" onSubmit={(event) => void handleSignIn(event)}>
          <p className="abikan-login__kicker">Welcome back</p>
          <h2>Sign in</h2>
          <p className="abikan-login__lead">Use your hospital username.</p>
          {error ? (
            <Alert tone="danger" title={error.title}>
              <p>{error.body}</p>
            </Alert>
          ) : null}
          <label className="abikan-field">
            <span>Username</span>
            <input
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
          <label className="abikan-field">
            <span>Password</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <Button type="submit" disabled={busy || !username.trim() || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </main>
    </div>
  );
}
