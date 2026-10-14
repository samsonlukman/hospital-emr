import { useEffect, useMemo, useState } from "react";
import { backWithinPharmacy, openPharmacyPatient } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { PatientAccountLink } from "../../components/PatientAccountLink";
import { SectionHeader } from "../../components/SectionHeader";
import { fetchPatientIdentity } from "../../services/openmrs/clinicalPatient";
import { PatientAccountRequestError } from "../../services/patientAccount";
import {
  addPharmacyPrescriptionMedicine,
  billPharmacyPrescription,
  cancelPharmacyPrescriptions,
  dispensePharmacyPrescriptions,
  fetchPharmacyPrescription,
  newDispenseRequestId,
  quantityLabel,
  revisePharmacyPrescriptionMedicine,
  type PharmacyPrescriptionEdit,
} from "../../services/pharmacy";
import type { PatientIdentity } from "../../types";
import type { PharmacyPrescription } from "../../types/pharmacy";
import { formatClinicalWhen } from "../../utils/datetime";
import { pharmacyStatusTone } from "../PatientAccount/accountBadges";
import { canChangePharmacyMedicine, canDeletePharmacyMedicine, medicineNeedsQuantity, paymentNeeded, pharmacyLinePaymentLabel, pharmacyLineStatusLabel, pharmacyStaffError, prescriptionDispenseLabel } from "./pharmacyView";
import { PharmacyPrescriptionEditor } from "./PharmacyPrescriptionEditor";
import "./PharmacyWorkspace.css";

interface PharmacyPrescriptionWorkspaceProps {
  orderUuid: string;
}

function medicineLabel(row: PharmacyPrescription): string {
  if (row.strength && !row.drugName.toLowerCase().includes(row.strength.toLowerCase())) {
    return `${row.drugName} · ${row.strength}`;
  }
  return row.drugName;
}

function regimenLabel(row: PharmacyPrescription): string {
  const dose = [row.dose, row.doseUnits].filter(Boolean).join(" ");
  return [dose, row.frequency, row.duration].filter(Boolean).join(" · ");
}

function canDeleteMedicine(row: PharmacyPrescription): boolean {
  return canDeletePharmacyMedicine(row);
}

export function PharmacyPrescriptionWorkspace({ orderUuid }: PharmacyPrescriptionWorkspaceProps) {
  const [order, setOrder] = useState<PharmacyPrescription | null>(null);
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmMode, setConfirmMode] = useState<"dispense" | "delete" | null>(null);
  const [confirmScope, setConfirmScope] = useState<"selected" | "all">("selected");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState("");
  const [requestId, setRequestId] = useState(newDispenseRequestId);
  const [editor, setEditor] = useState<null | { mode: "add" | "change"; row?: PharmacyPrescription }>(null);
  const [editorError, setEditorError] = useState("");
  const [quantities, setQuantities] = useState<Record<string, string>>({});

  const medicines = useMemo(() => {
    if (!order) {
      return [] as PharmacyPrescription[];
    }
    return order.medicines?.length ? order.medicines : [order];
  }, [order]);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchPharmacyPrescription(orderUuid)
      .then(async (value) => {
        setOrder(value);
        const lines = value.medicines?.length ? value.medicines : [value];
        setSelected(new Set(lines.filter((row) => row.canDispense).map((row) => row.orderUuid)));
        if (value.patientUuid) {
          const identity = await fetchPatientIdentity(value.patientUuid).catch(() => null);
          if (identity) {
            setPatient(identity);
          }
        }
      })
      .catch((reason) => {
        setOrder(null);
        setError(reason instanceof Error ? reason.message : "Unable to load this prescription.");
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    load();
    setConfirmMode(null);
    setNotice("");
    setRequestId(newDispenseRequestId());
  }, [orderUuid]);

  const unbilled = medicines.filter(medicineNeedsQuantity);
  const quantitiesReady = unbilled.every((row) => {
    const qty = Number(quantities[row.orderUuid]);
    return Number.isFinite(qty) && qty > 0;
  });
  const dispensable = medicines.filter((row) => row.canDispense);
  const deletable = medicines.filter(canDeleteMedicine);
  const selectedDispensable = dispensable.filter((row) => selected.has(row.orderUuid));
  const selectedDeletable = deletable.filter((row) => selected.has(row.orderUuid));
  const unpaid = medicines.some(paymentNeeded);
  const groupStatus =
    order?.groupDispensingStatus || order?.dispensingStatus || medicines[0]?.dispensingStatus || "";
  const groupPayment =
    order?.groupPaymentStatus || order?.paymentStatus || medicines[0]?.paymentStatus || "UNPAID";
  const patientName = patient?.name || order?.patientName || "Patient";

  const toggle = (uuid: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(uuid)) {
        next.delete(uuid);
      } else {
        next.add(uuid);
      }
      return next;
    });
  };

  const selectAllActionable = () => {
    setSelected(
      new Set(
        medicines
          .filter((row) => row.canDispense || canDeleteMedicine(row))
          .map((row) => row.orderUuid),
      ),
    );
  };

  const clearSelection = () => setSelected(new Set());

  const submitBill = async () => {
    if (!order || submitting || !quantitiesReady || unbilled.length === 0) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = await billPharmacyPrescription(
        order.orderUuid,
        unbilled.map((row) => ({
          orderUuid: row.orderUuid,
          quantity: Number(quantities[row.orderUuid]),
        })),
      );
      setOrder(payload);
      setQuantities({});
      setNotice("The bill is with the cashier.");
      const lines = payload.medicines?.length ? payload.medicines : [payload];
      setSelected(new Set(lines.filter((row) => row.canDispense).map((row) => row.orderUuid)));
    } catch (reason) {
      setError(pharmacyStaffError(reason, "The bill could not be created. Check the quantities and try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const saveEditor = async (body: PharmacyPrescriptionEdit) => {
    if (!editor || !order || submitting) {
      return;
    }
    setSubmitting(true);
    setEditorError("");
    try {
      const payload =
        editor.mode === "change" && editor.row
          ? await revisePharmacyPrescriptionMedicine(editor.row.orderUuid, body)
          : await addPharmacyPrescriptionMedicine(order.orderUuid, body);
      setOrder(payload);
      const lines = payload.medicines?.length ? payload.medicines : [payload];
      setSelected(new Set(lines.filter((row) => row.canDispense).map((row) => row.orderUuid)));
      setEditor(null);
      setNotice(editor.mode === "change" ? "Prescription updated." : "Medicine added.");
    } catch (reason) {
      setEditorError(pharmacyStaffError(reason, "The prescription could not be saved."));
    } finally {
      setSubmitting(false);
    }
  };

  const targetsForConfirm = (): PharmacyPrescription[] => {
    if (confirmMode === "dispense") {
      return confirmScope === "all" ? dispensable : selectedDispensable;
    }
    if (confirmMode === "delete") {
      return confirmScope === "all" ? deletable : selectedDeletable;
    }
    return [];
  };

  const submitDispense = async (uuids: string[]) => {
    if (!uuids.length || submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = await dispensePharmacyPrescriptions(uuids, requestId);
      setOrder(payload);
      setConfirmMode(null);
      setRequestId(newDispenseRequestId());
      setNotice(payload.message || "Medication dispensed.");
      const lines = payload.medicines?.length ? payload.medicines : [payload];
      setSelected(new Set(lines.filter((row) => row.canDispense).map((row) => row.orderUuid)));
      if (payload.dispenseErrors?.length) {
        setError(payload.dispenseErrors.map((row) => row.message).join(" "));
      }
    } catch (reason) {
      const message = pharmacyStaffError(reason, "The medication could not be dispensed.");
      if (reason instanceof PatientAccountRequestError && reason.code === "already_dispensed") {
        setNotice("Already dispensed.");
        setConfirmMode(null);
        load();
        return;
      }
      setError(message);
      setConfirmMode(null);
      load();
    } finally {
      setSubmitting(false);
    }
  };

  const submitDelete = async (uuids: string[]) => {
    if (!uuids.length || submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await cancelPharmacyPrescriptions(uuids);
      setConfirmMode(null);
      setNotice(result.message || "Prescription deleted.");
      if (result.errors?.length) {
        setError(result.errors.map((row) => row.message).join(" "));
      }
      const remainingUuids = medicines
        .map((row) => row.orderUuid)
        .filter((uuid) => !uuids.includes(uuid));
      const reloadUuid = remainingUuids[0] || orderUuid;
      try {
        const remaining = await fetchPharmacyPrescription(reloadUuid);
        setOrder(remaining);
        const lines = remaining.medicines?.length ? remaining.medicines : [remaining];
        setSelected(new Set(lines.filter((row) => row.canDispense).map((row) => row.orderUuid)));
        if (reloadUuid !== orderUuid) {
          window.location.hash = `#/pharmacy/prescription/${reloadUuid}`;
        }
      } catch {
        if (result.patientUuid) {
          openPharmacyPatient(result.patientUuid);
          return;
        }
        backWithinPharmacy("prescriptions");
      }
    } catch (reason) {
      setError(pharmacyStaffError(reason, "This prescription could not be deleted."));
      setConfirmMode(null);
      load();
    } finally {
      setSubmitting(false);
    }
  };

  const confirmTargets = targetsForConfirm();

  return (
    <div className="pharm-order">
      <div className="pharm-patient__nav">
        <Button variant="ghost" onClick={() => backWithinPharmacy("prescriptions")}>
          ← Back
        </Button>
        {order?.patientUuid ? (
          <div className="abikan-account-nav">
            <PatientAccountLink patientUuid={order.patientUuid} label="View Patient Account" />
            <Button variant="ghost" onClick={() => openPharmacyPatient(order.patientUuid)}>
              Patient
            </Button>
          </div>
        ) : null}
      </div>

      <PageHeader
        title="Prescription"
        description="Payment and dispensing are separate. Pharmacy does not collect payment."
      />

      {loading ? <LoadingState variant="board" label="Loading prescription…" /> : null}
      {!loading && error && !order ? (
        <EmptyState title="Prescription unavailable" description={error} />
      ) : null}

      {notice ? (
        <Alert tone="success" title="Pharmacy updated">
          <p>{notice}</p>
        </Alert>
      ) : null}

      {!loading && error && order ? (
        <Alert tone="danger" title="Could not complete">
          {error}
        </Alert>
      ) : null}

      {!loading && order && unpaid ? (
        <Alert tone="warning" title={String(groupPayment)}>
          <p>
            Payment is still outstanding. You can dispense now; the charge stays on the patient
            account for the cashier.
          </p>
        </Alert>
      ) : null}

      {!loading && order ? (
        <>
          <Card>
            <SectionHeader title="Patient" />
            <dl className="pharm-order__facts">
              <div>
                <dt>Name</dt>
                <dd>{patientName}</dd>
              </div>
              <div>
                <dt>Hospital number</dt>
                <dd>{patient?.mrn || order.mrn || "Not recorded"}</dd>
              </div>
              {order.nhis ? (
                <div>
                  <dt>NHIS</dt>
                  <dd>
                    <Badge tone="info">NHIS patient</Badge>
                  </dd>
                </div>
              ) : null}
              <div>
                <dt>Prescribed by</dt>
                <dd>{order.prescriber || medicines[0]?.prescriber || "—"}</dd>
              </div>
              <div>
                <dt>Date</dt>
                <dd>
                  {order.ordered || medicines[0]?.ordered
                    ? formatClinicalWhen(order.ordered || medicines[0]?.ordered || "")
                    : "Not recorded"}
                </dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>
                  <Badge tone={pharmacyStatusTone(String(groupStatus))}>
                    {groupPayment === "NOT BILLED"
                      ? "Not billed"
                      : groupStatus === "NOT IN PHARMACY"
                        ? "Not in Pharmacy — do not dispense"
                        : prescriptionDispenseLabel(medicines) || "Not dispensed"}
                  </Badge>
                </dd>
              </div>
              {groupPayment && groupPayment !== "NOT BILLED" ? (
              <div>
                <dt>Payment</dt>
                <dd>
                  <Badge tone={pharmacyStatusTone(String(groupPayment))}>{groupPayment}</Badge>
                </dd>
              </div>
              ) : null}
            </dl>
          </Card>

          {order.doctorNotes?.length ? (
            <Card>
              <SectionHeader
                title="Doctor’s notes"
                description="Notes recorded during the patient’s consultation."
              />
              <ul className="pharm-rx-meds">
                {order.doctorNotes.map((note, index) => (
                  <li key={`${note.recordedAt}-${index}`} className="pharm-rx-med">
                    <span className="pharm-rx-med__body">
                      <strong>{note.authorName}</strong>
                      <span>{note.recordedAt ? formatClinicalWhen(note.recordedAt) : "Date not recorded"}</span>
                      <span>{note.content}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}

          <Card>
            <SectionHeader
              title="Medicines"
              description={
                unbilled.length > 0
                  ? "Enter a quantity for each medicine, then create the bill."
                  : `${medicines.length} medicine${medicines.length === 1 ? "" : "s"} on this prescription.`
              }
            />
            <div className="pharm-rx-toolbar">
              {unbilled.length > 0 ? (
                <Button disabled={submitting || !quantitiesReady} onClick={() => void submitBill()}>
                  Create bill
                </Button>
              ) : null}
              <Button
                variant="secondary"
                disabled={submitting}
                onClick={() => {
                  setEditorError("");
                  setEditor({ mode: "add" });
                }}
              >
                Add medicine
              </Button>
              <Button variant="ghost" onClick={selectAllActionable}>
                Select all
              </Button>
              <Button variant="ghost" onClick={clearSelection}>
                Clear
              </Button>
            </div>
            <ul className="pharm-rx-meds">
              {medicines.map((row) => {
                const actionable = row.canDispense || canDeleteMedicine(row);
                const paymentLabel = pharmacyLinePaymentLabel(row);
                return (
                  <li key={row.orderUuid} className="pharm-rx-med">
                    <label className="pharm-rx-med__select">
                      <input
                        type="checkbox"
                        checked={selected.has(row.orderUuid)}
                        disabled={!actionable}
                        onChange={() => toggle(row.orderUuid)}
                      />
                      <span className="pharm-rx-med__body">
                        <strong>{medicineLabel(row)}</strong>
                        {regimenLabel(row) ? <span>{regimenLabel(row)}</span> : null}
                        {medicineNeedsQuantity(row) ? (
                          <div
                            className="pharm-rx-qty"
                            onMouseDown={(event) => event.stopPropagation()}
                            onClick={(event) => event.stopPropagation()}
                          >
                            <span>Quantity</span>
                            <input
                              type="number"
                              min="1"
                              step="1"
                              inputMode="numeric"
                              aria-label={`Quantity for ${medicineLabel(row)}`}
                              value={quantities[row.orderUuid] ?? ""}
                              disabled={submitting}
                              onChange={(event) =>
                                setQuantities((current) => ({
                                  ...current,
                                  [row.orderUuid]: event.target.value,
                                }))
                              }
                            />
                            {row.quantityUnits ? <span>{row.quantityUnits}</span> : null}
                          </div>
                        ) : (
                          <span>Quantity: {quantityLabel(row)}</span>
                        )}
                        {row.instructions ? <span>{row.instructions}</span> : null}
                        <span className="pharm-rx-med__status">
                          <Badge tone={pharmacyStatusTone(row.dispensingStatus)}>
                            {pharmacyLineStatusLabel(row)}
                          </Badge>
                          {paymentLabel ? (
                          <Badge tone={pharmacyStatusTone(row.paymentStatus)}>
                            {paymentLabel}
                          </Badge>
                          ) : null}
                        </span>
                        {row.blockReason && !row.canDispense && row.dispensingStatus !== "DISPENSED" ? (
                          <span className="pharm-patient__muted">{row.blockReason}</span>
                        ) : null}
                      </span>
                    </label>
                    <div className="pharm-rx-med__actions">
                      {canChangePharmacyMedicine(row) ? (
                        <Button
                          variant="secondary"
                          disabled={submitting}
                          onClick={() => {
                            setEditorError("");
                            setEditor({ mode: "change", row });
                          }}
                        >
                          Change
                        </Button>
                      ) : null}
                      {row.canDispense ? (
                        <Button
                          variant="secondary"
                          disabled={submitting}
                          onClick={() => {
                            setSelected(new Set([row.orderUuid]));
                            setConfirmScope("selected");
                            setConfirmMode("dispense");
                          }}
                        >
                          Dispense
                        </Button>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>

            <div className="pharm-rx-bulk">
              {dispensable.length > 0 ? (
                <>
                  <Button
                    disabled={submitting || selectedDispensable.length === 0}
                    onClick={() => {
                      setConfirmScope("selected");
                      setConfirmMode("dispense");
                    }}
                  >
                    Dispense {selectedDispensable.length || ""} selected
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={submitting || dispensable.length === 0}
                    onClick={() => {
                      setConfirmScope("all");
                      setConfirmMode("dispense");
                    }}
                  >
                    Dispense all
                  </Button>
                </>
              ) : null}
              <Button
                variant="secondary"
                disabled={submitting || selectedDeletable.length === 0}
                onClick={() => {
                  setConfirmScope("selected");
                  setConfirmMode("delete");
                }}
              >
                Delete {selectedDeletable.length || ""} selected
              </Button>
              <Button
                variant="secondary"
                disabled={submitting || deletable.length === 0}
                onClick={() => {
                  setConfirmScope("all");
                  setConfirmMode("delete");
                }}
              >
                Delete all
              </Button>
            </div>
          </Card>
        </>
      ) : null}

      {editor ? (
        <PharmacyPrescriptionEditor
          mode={editor.mode}
          row={editor.row}
          busy={submitting}
          error={editorError}
          onClose={() => {
            if (!submitting) {
              setEditor(null);
              setEditorError("");
            }
          }}
          onSave={(body) => {
            void saveEditor(body);
          }}
        />
      ) : null}

      {confirmMode && confirmTargets.length > 0 ? (
        <div className="abikan-dialog" role="dialog" aria-modal="true" aria-labelledby="rx-confirm-title">
          <div className="abikan-dialog__panel cashier-confirm">
            <h2 id="rx-confirm-title">
              {confirmMode === "dispense" ? "Dispense medicines?" : "Delete medicines?"}
            </h2>
            <p>
              Patient: <strong>{patientName}</strong>
            </p>
            <ul className="pharm-rx-confirm-list">
              {confirmTargets.map((row) => (
                <li key={row.orderUuid}>
                  {medicineLabel(row)} · {quantityLabel(row)}
                </li>
              ))}
            </ul>
            {confirmMode === "dispense" ? (
              <p className="pharm-patient__muted">
                Payment is separate. Dispensing does not mark the bill as paid.
              </p>
            ) : confirmTargets.some((row) => row.paymentStatus === "PAID") ? (
              <p className="pharm-patient__muted">
                Paid medicines that have not been handed over are removed. Accounts can return that payment.
              </p>
            ) : (
              <p className="pharm-patient__muted">
                Unpaid charges for these medicines will be removed from the patient account.
              </p>
            )}
            {error ? <p className="pharm-dialog__error">{error}</p> : null}
            <div className="cashier-confirm__actions">
              <Button
                variant="secondary"
                disabled={submitting}
                onClick={() => setConfirmMode(null)}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                busy={submitting}
                busyLabel={confirmMode === "dispense" ? "Dispensing…" : "Deleting…"}
                onClick={() => {
                  const uuids = confirmTargets.map((row) => row.orderUuid);
                  if (confirmMode === "dispense") {
                    void submitDispense(uuids);
                  } else {
                    void submitDelete(uuids);
                  }
                }}
              >
                {confirmMode === "dispense" ? "Dispense" : "Delete"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
