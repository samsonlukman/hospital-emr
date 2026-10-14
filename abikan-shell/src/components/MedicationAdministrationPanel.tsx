import { useCallback, useEffect, useState } from "react";
import { Alert } from "./Alert";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { ClinicalSection } from "./ClinicalSection";
import { EmptyState } from "./EmptyState";
import { fetchMar, recordScheduledDose } from "../services/inpatient";
import { PatientAccountRequestError } from "../services/patientAccount";
import type { MarOrder, MarOutcome, MarPayload, MarSlot } from "../types/inpatient";
import { HOSPITAL_TIMEZONE } from "../utils/datetime";
import {
  canSubmitMar,
  marOutcomeLabel,
  marSlotStatusLabel,
  marStatusTone,
} from "../utils/mar";
import { InpatientConfirmDialog } from "../workspaces/Nursing/InpatientDialogs";
import "./MedicationAdministrationPanel.css";

interface Props {
  patientUuid: string;
  patientName: string;
  canRecord: boolean;
  visitUuid?: string;
  hideWhenNotAdmitted?: boolean;
}

interface Selection {
  order: MarOrder;
  slot: MarSlot;
  outsideWindow: boolean;
}

function formatWhen(value: number | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-NG", {
    timeZone: HOSPITAL_TIMEZONE,
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function doseLabel(order: MarOrder): string {
  return order.dose == null
    ? "Dose not recorded"
    : `${order.dose} ${order.doseUnits}`.trim();
}

function requestError(error: unknown): string {
  return error instanceof PatientAccountRequestError
    ? error.message
    : "Medication administration could not be loaded. Try again.";
}

export function MedicationAdministrationPanel({
  patientUuid,
  patientName,
  canRecord,
  visitUuid,
  hideWhenNotAdmitted = false,
}: Props) {
  const [payload, setPayload] = useState<MarPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [notAdmitted, setNotAdmitted] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [outcome, setOutcome] = useState<MarOutcome>("given");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setPayload(await fetchMar(patientUuid, visitUuid));
      setNotAdmitted(false);
      setLoadError("");
    } catch (error) {
      setPayload(null);
      setNotAdmitted(
        error instanceof PatientAccountRequestError &&
          (error.code === "not_admitted" ||
            error.code === "admission_history_not_found"),
      );
      setLoadError(requestError(error));
    } finally {
      setLoading(false);
    }
  }, [patientUuid, visitUuid]);

  useEffect(() => {
    void load();
  }, [load]);

  if (hideWhenNotAdmitted && !loading && notAdmitted) return null;

  const open = (order: MarOrder, slot: MarSlot, outsideWindow: boolean) => {
    setSelection({ order, slot, outsideWindow });
    setOutcome("given");
    setReason("");
    setSaveError("");
  };

  const save = async () => {
    if (
      !selection ||
      !canSubmitMar(outcome, reason, saving, selection.outsideWindow)
    )
      return;
    setSaving(true);
    setSaveError("");
    try {
      await recordScheduledDose(
        patientUuid,
        selection.slot.uuid,
        outcome,
        reason,
        selection.outsideWindow,
      );
      setSelection(null);
      await load();
    } catch (error) {
      setSaveError(requestError(error));
    } finally {
      setSaving(false);
    }
  };

  const canRecordForAdmission = canRecord && Boolean(payload?.activeAdmission);

  return (
    <>
      <ClinicalSection
        id="mar"
        title="Medication Administration"
        description="The doctor prescribes an inpatient medicine. The ward schedule is created from that order. Give the dose here. Nursing cannot write a new prescription from this sheet."
      >
        {loading ? (
          <p className="mar__muted">Loading scheduled medicines…</p>
        ) : loadError && !notAdmitted ? (
          <Alert tone="danger" title="Medication administration unavailable">
            {loadError}
          </Alert>
        ) : notAdmitted ? (
          <EmptyState
            title="Medication administration is available after admission."
            description="The patient must have an active inpatient stay."
          />
        ) : !payload?.orders.length ? (
          <>
            {payload?.scheduleIssues?.length ? (
              <Alert tone="danger" title="Ward schedule not created">
                {payload.scheduleIssues[0].message}
              </Alert>
            ) : (
              <EmptyState
                title={
                  payload?.activeAdmission
                    ? "No scheduled medications"
                    : "No medication history for this admission"
                }
                description={
                  payload?.activeAdmission
                    ? "Scheduled inpatient doses appear here after the doctor prescribes an inpatient medicine and the ward schedule is created. When-needed (PRN) medicines are not listed on this sheet."
                    : "No medication administrations were recorded during this stay."
                }
              />
            )}
          </>
        ) : (
          <div className="mar__orders">
            {payload.scheduleIssues?.length ? (
              <Alert tone="danger" title="Some prescriptions could not be scheduled">
                {payload.scheduleIssues[0].message}
              </Alert>
            ) : null}
            {!payload.activeAdmission ? (
              <Alert tone="info" title="Historical medication record">
                This admission is closed. Previous doses remain readable, but no new
                administration can be recorded.
              </Alert>
            ) : null}
            {payload.orders.map((order) => (
              <article className="mar__order" key={order.orderUuid}>
                <header className="mar__order-header">
                  <div>
                    <h4>{order.medication}</h4>
                    <p>
                      {doseLabel(order)} · {order.route || "Route not recorded"}
                    </p>
                    {order.instructions ? (
                      <p className="mar__instructions">
                        Instructions: {order.instructions}
                      </p>
                    ) : null}
                  </div>
                  <Badge tone="neutral">{order.frequency || "Scheduled"}</Badge>
                </header>

                <ol className="mar__slots">
                  {order.slots.map((slot) => (
                    <li key={slot.uuid}>
                      <div className="mar__slot-heading">
                        <div>
                          <time dateTime={new Date(slot.scheduledTime).toISOString()}>
                            {formatWhen(slot.scheduledTime)}
                          </time>
                          <Badge tone={marStatusTone(slot.status)}>
                            {marSlotStatusLabel(slot.status)}
                          </Badge>
                        </div>
                        {canRecordForAdmission && slot.status === "SCHEDULED" ? (
                          slot.timing.canAdministerNormally ? (
                            <Button
                              variant="primary"
                              onClick={() => open(order, slot, false)}
                            >
                              Administer
                            </Button>
                          ) : slot.timing.status !== "unknown" ? (
                            <Button
                              variant="secondary"
                              onClick={() => open(order, slot, true)}
                            >
                              Administer outside scheduled window
                            </Button>
                          ) : (
                            <span className="mar__muted">
                              Scheduled time unavailable
                            </span>
                          )
                        ) : null}
                      </div>

                      {slot.administration ? (
                        <div className="mar__administration">
                          <strong>
                            {marOutcomeLabel(slot.administration.outcome)}
                          </strong>
                          <dl>
                            <div>
                              <dt>Scheduled</dt>
                              <dd>{formatWhen(slot.administration.scheduledTime)}</dd>
                            </div>
                            <div>
                              <dt>Actual</dt>
                              <dd>{formatWhen(slot.administration.actualTime)}</dd>
                            </div>
                            <div>
                              <dt>Nurse</dt>
                              <dd>{slot.administration.nurseName}</dd>
                            </div>
                          </dl>
                          {slot.administration.reason ? (
                            <p>Reason: {slot.administration.reason}</p>
                          ) : null}
                          {slot.administration.outsideWindow ? (
                            <p>Recorded outside the scheduled window.</p>
                          ) : null}
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </article>
            ))}
          </div>
        )}
      </ClinicalSection>

      {selection ? (
        <InpatientConfirmDialog
          title="Record Medication Administration"
          confirmLabel="Confirm and Record"
          busy={saving}
          confirmDisabled={
            !canSubmitMar(outcome, reason, saving, selection.outsideWindow)
          }
          error={saveError}
          onClose={() => !saving && setSelection(null)}
          onConfirm={() => void save()}
        >
          {selection.outsideWindow ? (
            <Alert tone="warning" title="Outside scheduled window">
              This dose is outside the normal administration window. Confirm the
              clinical decision and record the reason. The current time will be
              recorded automatically.
            </Alert>
          ) : null}
          <dl className="mar__confirm">
            <div>
              <dt>Patient</dt>
              <dd>{patientName}</dd>
            </div>
            <div>
              <dt>Medication</dt>
              <dd>{selection.order.medication}</dd>
            </div>
            <div>
              <dt>Dose</dt>
              <dd>{doseLabel(selection.order)}</dd>
            </div>
            <div>
              <dt>Route</dt>
              <dd>{selection.order.route || "Not recorded"}</dd>
            </div>
            <div>
              <dt>Scheduled</dt>
              <dd>{formatWhen(selection.slot.scheduledTime)}</dd>
            </div>
          </dl>

          <label className="mar__field">
            <span>Outcome</span>
            <select
              value={outcome}
              disabled={saving}
              onChange={(event) => setOutcome(event.target.value as MarOutcome)}
            >
              <option value="given">Given</option>
              <option value="not-done">Not done</option>
              <option value="refused">Refused</option>
              <option value="held">Held</option>
            </select>
          </label>

          <label className="mar__field">
            <span>
              {outcome === "given" && !selection.outsideWindow
                ? "Note (optional)"
                : "Reason"}
            </span>
            <textarea
              rows={4}
              maxLength={1000}
              value={reason}
              disabled={saving}
              onChange={(event) => setReason(event.target.value)}
              placeholder={
                outcome === "given" && !selection.outsideWindow
                  ? "Optional administration note"
                  : selection.outsideWindow
                    ? "Record the clinical reason for administering outside the scheduled window"
                  : "Record why this dose was not given"
              }
            />
          </label>
          <p className="mar__muted">
            Actual time and administering nurse are recorded automatically.
          </p>
        </InpatientConfirmDialog>
      ) : null}
    </>
  );
}
