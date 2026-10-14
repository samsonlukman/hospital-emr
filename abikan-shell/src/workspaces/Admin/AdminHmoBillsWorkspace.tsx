import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { fetchHmoBills, sendHmoStatement } from "../../services/hmo";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { HmoBodyOption, HmoStatement } from "../../types/hmo";
import "./AdminHmoBillsWorkspace.css";

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : fallback;
}

function localDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function writtenDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day) return iso;
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function StatementSheet({ statement }: { statement: HmoStatement }) {
  return (
    <article className="hmo-statement" aria-label="HMO statement">
      <div className="hmo-statement__bar" />
      <header className="hmo-statement__head">
        <p>HMO statement</p>
        <h2>{statement.hospital.name}</h2>
        <p className="hmo-statement__contact">
          {statement.hospital.phone}
          <span aria-hidden="true"> · </span>
          {statement.hospital.email}
        </p>
      </header>
      <div className="hmo-statement__intro">
        <h3>{statement.body}</h3>
        <p>
          {statement.scheme}
          <span aria-hidden="true"> · </span>
          {writtenDate(statement.start)} to {writtenDate(statement.end)}
        </p>
      </div>
      {statement.patients.map((patient) => (
        <section key={patient.patientUuid} className="hmo-statement__patient">
          <h3>{patient.patientName}</h3>
          <p>{patient.hospitalNumber}</p>
          {patient.lines.length === 0 ? (
            <p className="hmo-statement__empty">No bills in this period.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Description</th>
                  <th>Department</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {patient.lines.map((line, index) => (
                  <tr key={`${line.date}-${line.description}-${index}`}>
                    <td>{writtenDate(line.date)}</td>
                    <td>{line.description}</td>
                    <td>{line.department}</td>
                    <td>{line.amountLabel}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="hmo-statement__patient-total">Patient total {patient.totalLabel}</p>
        </section>
      ))}
      <footer className="hmo-statement__totals">
        <div>
          <span>Amount due from the HMO</span>
          <span>{statement.totalLabel}</span>
        </div>
      </footer>
    </article>
  );
}

export function AdminHmoBillsWorkspace() {
  const today = localDate(new Date());
  const [bodies, setBodies] = useState<HmoBodyOption[]>([]);
  const [scheme, setScheme] = useState("");
  const [body, setBody] = useState("");
  const [start, setStart] = useState(`${today.slice(0, 8)}01`);
  const [end, setEnd] = useState(today);
  const [statement, setStatement] = useState<HmoStatement | null>(null);
  const [recipient, setRecipient] = useState("");
  const [loading, setLoading] = useState(true);
  const [preparing, setPreparing] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    fetchHmoBills({})
      .then((payload) => {
        setBodies(payload.bodies);
        setError("");
      })
      .catch((reason) => setError(errorMessage(reason, "HMO bills could not be loaded.")))
      .finally(() => setLoading(false));
  }, []);

  const schemes = [...new Set(bodies.map((item) => item.scheme))];
  const bodiesForScheme = bodies.filter((item) => item.scheme === scheme);
  const selected = bodiesForScheme.find((item) => item.body === body) ?? null;

  const prepare = () => {
    if (!selected) return;
    setPreparing(true);
    setError("");
    setNotice("");
    fetchHmoBills({ body: selected.body, scheme: selected.scheme, from: start, to: end })
      .then((payload) => {
        setStatement(payload.statement ?? null);
        if (!payload.statement) setError("Choose the HMO this statement is for.");
      })
      .catch((reason) => setError(errorMessage(reason, "HMO bills could not be loaded.")))
      .finally(() => setPreparing(false));
  };

  const send = () => {
    if (!selected || !statement) return;
    setSending(true);
    setError("");
    setNotice("");
    sendHmoStatement({
      body: selected.body,
      scheme: selected.scheme,
      from: start,
      to: end,
      recipient,
    })
      .then((payload) => {
        if (payload.statement) setStatement(payload.statement);
        setNotice(payload.message || "The statement is ready.");
      })
      .catch((reason) => setError(errorMessage(reason, "The statement could not be sent.")))
      .finally(() => setSending(false));
  };

  return (
    <div className="admin-workspace hmo-bills">
      <PageHeader
        title="HMO bills"
        description="Bills for patients covered by an HMO. They pay nothing at the hospital. The full amount is due from the HMO."
      />
      {error ? <Alert tone="danger" title={error} /> : null}
      {notice ? <Alert tone="info" title={notice} /> : null}
      {loading ? <LoadingState variant="board" label="Loading HMO bills…" /> : null}
      {!loading ? (
        <>
          <form
            className="hmo-bills__filters"
            onSubmit={(event) => {
              event.preventDefault();
              prepare();
            }}
          >
            <label>
              Coverage type
              <select
                value={scheme}
                onChange={(event) => {
                  setScheme(event.target.value);
                  setBody("");
                  setStatement(null);
                }}
              >
                <option value="">Choose coverage type</option>
                {schemes.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>
            <label>
              HMO body
              <select
                value={body}
                onChange={(event) => {
                  setBody(event.target.value);
                  setStatement(null);
                }}
                disabled={!scheme}
              >
                <option value="">Choose HMO body</option>
                {bodiesForScheme.map((item) => (
                  <option key={item.body} value={item.body}>
                    {item.body}{item.patients ? ` · ${item.patients} patient${item.patients === 1 ? "" : "s"}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              From
              <input type="date" value={start} onChange={(event) => setStart(event.target.value)} />
            </label>
            <label>
              To
              <input type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
            </label>
            <Button type="submit" busy={preparing} busyLabel="Preparing…" disabled={!selected}>
              Prepare statement
            </Button>
          </form>
          {statement ? (
            <>
              <StatementSheet statement={statement} />
              <form
                className="hmo-bills__send"
                onSubmit={(event) => {
                  event.preventDefault();
                  send();
                }}
              >
                <label>
                  Recipient
                  <input
                    type="email"
                    value={recipient}
                    onChange={(event) => setRecipient(event.target.value)}
                    placeholder="claims@company.com"
                    autoComplete="off"
                  />
                </label>
                <Button type="submit" variant="secondary" busy={sending} busyLabel="Sending…" disabled={!recipient.trim()}>
                  Send statement
                </Button>
              </form>
            </>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
