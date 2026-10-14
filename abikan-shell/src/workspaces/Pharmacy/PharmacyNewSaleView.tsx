import { useEffect, useMemo, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { searchPatients } from "../../services/openmrs/patients";
import {
  createPharmacySale,
  fetchPharmacyCatalogue,
  newDispenseRequestId,
} from "../../services/pharmacy";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { PatientSearchHit } from "../../types";
import type {
  PharmacyCatalogueItem,
  PharmacySale,
  PharmacySaleBuyerType,
  PharmacySaleLineDraft,
} from "../../types/pharmacy";
import { pharmacyStatusTone } from "../PatientAccount/accountBadges";
import { matchesCatalogueSearch, pharmacyStaffError } from "./pharmacyView";

function emptyLine(): PharmacySaleLineDraft {
  return {
    drugUuid: "",
    drugName: "",
    quantity: "1",
    dose: "",
    instructions: "",
    unitPrice: null,
  };
}

export function PharmacyNewSaleView({
  onCompleted,
}: {
  onCompleted?: (sale: PharmacySale) => void;
}) {
  const [buyerType, setBuyerType] = useState<PharmacySaleBuyerType>("registered");
  const [patientQuery, setPatientQuery] = useState("");
  const [patientHits, setPatientHits] = useState<PatientSearchHit[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<PatientSearchHit | null>(null);
  const [buyerName, setBuyerName] = useState("");
  const [buyerPhone, setBuyerPhone] = useState("");
  const [catalogue, setCatalogue] = useState<PharmacyCatalogueItem[]>([]);
  const [lines, setLines] = useState<PharmacySaleLineDraft[]>([emptyLine()]);
  const [lineQueries, setLineQueries] = useState<string[]>([""]);
  const [activeLine, setActiveLine] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [completed, setCompleted] = useState<PharmacySale | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchPharmacyCatalogue()
      .then((payload) => {
        if (!cancelled) {
          setCatalogue(payload.items ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCatalogue([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (buyerType !== "registered" || patientQuery.trim().length < 2 || selectedPatient) {
      setPatientHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      void searchPatients(patientQuery)
        .then(setPatientHits)
        .catch(() => setPatientHits([]));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [buyerType, patientQuery, selectedPatient]);

  const medicineHits = useMemo(
    () =>
      catalogue
        .filter((row) => row.available && matchesCatalogueSearch(row, lineQueries[activeLine] || ""))
        .slice(0, 6),
    [catalogue, lineQueries, activeLine],
  );

  const subtotal = lines.reduce((sum, line) => {
    const qty = Number(line.quantity);
    const price = line.unitPrice ?? 0;
    if (!Number.isFinite(qty) || qty <= 0 || !line.drugUuid) {
      return sum;
    }
    return sum + qty * price;
  }, 0);

  const updateLine = (index: number, patch: Partial<PharmacySaleLineDraft>) => {
    setLines((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };

  const chooseMedicine = (index: number, item: PharmacyCatalogueItem) => {
    updateLine(index, {
      drugUuid: item.id,
      drugName: item.name,
      unitPrice: item.price?.amount ?? null,
    });
    setLineQueries((current) => current.map((value, i) => (i === index ? "" : value)));
  };

  const addLine = () => {
    setLines((current) => [...current, emptyLine()]);
    setLineQueries((current) => [...current, ""]);
    setActiveLine(lines.length);
  };

  const removeLine = (index: number) => {
    setLines((current) => current.filter((_, i) => i !== index));
    setLineQueries((current) => current.filter((_, i) => i !== index));
    setActiveLine(0);
  };

  const submit = async () => {
    setError("");
    setNotice("");
    const prepared = lines
      .filter((line) => line.drugUuid)
      .map((line) => ({
        drugUuid: line.drugUuid,
        quantity: Number(line.quantity),
        dose: line.dose.trim(),
        instructions: line.instructions.trim(),
      }));
    if (prepared.length === 0) {
      setError("Add at least one medicine.");
      return;
    }
    if (prepared.some((line) => !Number.isFinite(line.quantity) || line.quantity <= 0)) {
      setError("Enter a quantity greater than zero for each medicine.");
      return;
    }
    if (buyerType === "registered" && !selectedPatient) {
      setError("Select a registered patient.");
      return;
    }
    if (buyerType === "other" && buyerName.trim().length < 2) {
      setError("Enter the buyer's name.");
      return;
    }
    setBusy(true);
    try {
      const sale = await createPharmacySale({
        requestId: newDispenseRequestId(),
        buyerType,
        patientUuid: selectedPatient?.uuid,
        buyerName: buyerName.trim(),
        buyerPhone: buyerPhone.trim(),
        dispense: true,
        lines: prepared,
      });
      setCompleted(sale);
      if (sale.code === "dispense_failed" || sale.success === false) {
        setNotice(sale.message || "Sale charged. Dispensing still needs finishing.");
        setError(sale.message || "Dispensing did not finish. Open Ready to Dispense and try again.");
      } else {
        setNotice(
          sale.dispensingStatus === "DISPENSED"
            ? sale.paymentStatus === "PAID"
              ? "Sale completed and dispensed."
              : "Sale dispensed. Payment can be settled later at the cashier."
            : "Sale recorded.",
        );
      }
      onCompleted?.(sale);
      setLines([emptyLine()]);
      setLineQueries([""]);
      setActiveLine(0);
      setSelectedPatient(null);
      setPatientQuery("");
      setBuyerName("");
      setBuyerPhone("");
    } catch (reason) {
      setError(pharmacyStaffError(reason, "The pharmacy sale could not be completed."));
      if (reason instanceof PatientAccountRequestError && reason.code === "insufficient_stock") {
        setNotice("");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card id="new-sale" className="pharm-sale">
      {notice ? (
        <Alert tone="success" title="Sale recorded">
          <p>{notice}</p>
        </Alert>
      ) : null}
      {error ? (
        <Alert tone="danger" title="Could not complete sale">
          <p>{error}</p>
        </Alert>
      ) : null}

      {completed ? (
        <div className="pharm-sale__result">
          <p>
            <strong>{completed.buyerName}</strong>
            {completed.mrn ? ` · ${completed.mrn}` : ""} · {completed.saleName || completed.saleId}
          </p>
          <div className="pharm-person-card__status">
            <Badge tone={pharmacyStatusTone(completed.paymentStatus)}>{completed.paymentStatus}</Badge>
            <Badge tone={pharmacyStatusTone(completed.dispensingStatus)}>
              {completed.dispensingStatus}
            </Badge>
          </div>
          <Button
            variant="secondary"
            onClick={() => {
              setCompleted(null);
              setNotice("");
            }}
          >
            Start another sale
          </Button>
        </div>
      ) : null}

      {!completed ? (
        <>
          <div className="pharm-sale__buyer">
            <div className="pharm-sale__buyer-type" role="group" aria-label="Buyer">
              <button
                type="button"
                className={buyerType === "registered" ? "is-active" : undefined}
                onClick={() => {
                  setBuyerType("registered");
                  setBuyerName("");
                  setBuyerPhone("");
                }}
              >
                Registered patient
              </button>
              <button
                type="button"
                className={buyerType === "other" ? "is-active" : undefined}
                onClick={() => {
                  setBuyerType("other");
                  setSelectedPatient(null);
                  setPatientQuery("");
                }}
              >
                Other buyer
              </button>
            </div>
            {buyerType === "registered" ? (
              selectedPatient ? (
                <p className="pharm-sale__chosen">
                  <strong>{selectedPatient.display}</strong>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedPatient(null);
                      setPatientQuery("");
                    }}
                  >
                    Change
                  </button>
                </p>
              ) : (
                <label className="pharm-sale__find">
                  Patient
                  <input
                    value={patientQuery}
                    onChange={(event) => setPatientQuery(event.target.value)}
                    placeholder="Name or hospital number"
                  />
                  {patientHits.length > 0 ? (
                    <ul className="pharm-sale__hits">
                      {patientHits.map((hit) => (
                        <li key={hit.uuid}>
                          <button type="button" onClick={() => setSelectedPatient(hit)}>
                            {hit.display}
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </label>
              )
            ) : (
              <div className="pharm-sale__walkin">
                <label>
                  Name
                  <input
                    value={buyerName}
                    onChange={(event) => setBuyerName(event.target.value)}
                    placeholder="Buyer name"
                  />
                </label>
                <label>
                  Phone
                  <input
                    value={buyerPhone}
                    onChange={(event) => setBuyerPhone(event.target.value)}
                    placeholder="Optional"
                  />
                </label>
              </div>
            )}
          </div>

          <ul className="pharm-sale__lines">
            {lines.map((line, index) => (
              <li key={`line-${index}`} className="pharm-sale__line">
                <label className="pharm-sale__find">
                  Medicine
                  {line.drugUuid ? (
                    <span className="pharm-sale__picked">
                      {line.drugName}
                      <button
                        type="button"
                        onClick={() =>
                          updateLine(index, { drugUuid: "", drugName: "", unitPrice: null })
                        }
                      >
                        Change
                      </button>
                    </span>
                  ) : (
                    <>
                      <input
                        value={lineQueries[index] || ""}
                        onFocus={() => setActiveLine(index)}
                        onChange={(event) => {
                          setActiveLine(index);
                          setLineQueries((current) =>
                            current.map((value, i) => (i === index ? event.target.value : value)),
                          );
                        }}
                        placeholder="Search medicine"
                      />
                      {activeLine === index && (lineQueries[index] || "").trim().length >= 1 && medicineHits.length > 0 ? (
                        <ul className="pharm-sale__hits">
                          {medicineHits.map((item) => (
                            <li key={item.id}>
                              <button type="button" onClick={() => chooseMedicine(index, item)}>
                                {item.name}
                                {item.strength ? ` · ${item.strength}` : ""}
                                {item.price ? ` · ${item.price.formatted}` : ""}
                              </button>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </>
                  )}
                </label>
                <label>
                  Qty
                  <input
                    value={line.quantity}
                    onChange={(event) => updateLine(index, { quantity: event.target.value })}
                    inputMode="decimal"
                  />
                </label>
                <label>
                  Note
                  <input
                    value={line.instructions || line.dose}
                    onChange={(event) =>
                      updateLine(index, { instructions: event.target.value, dose: event.target.value })
                    }
                    placeholder="Optional"
                  />
                </label>
                <span className="pharm-sale__price">
                  {line.unitPrice != null
                    ? line.unitPrice.toLocaleString("en-NG", {
                        style: "currency",
                        currency: "NGN",
                        maximumFractionDigits: 0,
                      })
                    : ""}
                </span>
                {lines.length > 1 ? (
                  <button type="button" className="pharm-sale__remove" onClick={() => removeLine(index)}>
                    Remove
                  </button>
                ) : (
                  <span />
                )}
              </li>
            ))}
          </ul>
          <div className="pharm-sale__review">
            <Button variant="secondary" onClick={addLine}>
              + Add medicine
            </Button>
            <p>
              <strong>
                {subtotal.toLocaleString("en-NG", {
                  style: "currency",
                  currency: "NGN",
                  maximumFractionDigits: 0,
                })}
              </strong>
            </p>
            <Button onClick={() => void submit()} disabled={busy}>
              {busy ? "Saving…" : "Complete sale"}
            </Button>
          </div>
        </>
      ) : null}

      {!completed && catalogue.length === 0 ? (
        <EmptyState title="No medicines available" description="Add medicines in the Drug Catalogue first." />
      ) : null}
    </Card>
  );
}
