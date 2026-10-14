import { useEffect, useState } from "react";
import { returnToPreviousScreen } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import {
  fetchAccommodationTariffs,
  newTariffRequestId,
  saveAccommodationTariff,
} from "../../services/accommodation";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { AccommodationTariff, AccommodationTariffPayload } from "../../types/accommodation";
import "./AccommodationSettingsWorkspace.css";

function draftFrom(areas: AccommodationTariff[]): Record<string, string> {
  const next: Record<string, string> = {};
  for (const area of areas) {
    next[area.areaUuid] = area.listPrice.amount.toFixed(area.listPrice.decimalPlaces);
  }
  return next;
}

export function AccommodationSettingsWorkspace() {
  const [payload, setPayload] = useState<AccommodationTariffPayload | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [savingUuid, setSavingUuid] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchAccommodationTariffs()
      .then((result) => {
        setPayload(result);
        setDrafts(draftFrom(result.areas));
      })
      .catch((reason) => {
        setPayload(null);
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "The accommodation prices could not be loaded.",
        );
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const save = async (area: AccommodationTariff) => {
    const raw = drafts[area.areaUuid];
    const amount = Number(raw);
    if (!Number.isFinite(amount) || amount < 0) {
      setError("Enter a daily price of zero or more.");
      return;
    }
    setSavingUuid(area.areaUuid);
    setError(null);
    setNotice("");
    try {
      const result = await saveAccommodationTariff(area.areaUuid, amount, newTariffRequestId());
      setPayload(result);
      setDrafts(draftFrom(result.areas));
      setNotice(`Saved the daily price for ${area.areaName}.`);
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The daily price could not be saved.",
      );
    } finally {
      setSavingUuid(null);
    }
  };

  return (
    <div className="acc-settings">
      <div className="acc-settings__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/home")}>
          ← Administration
        </Button>
      </div>

      <PageHeader
        title="Accommodation prices"
        description="Set the daily price for each ward and room. A price of 0 means the room is not ready to bill. Changing a price does not change bills already created."
      />

      {payload?.message ? (
        <Alert tone="info" title="No patient tax">
          {payload.message}
        </Alert>
      ) : null}

      {notice ? <Alert tone="success" title={notice} /> : null}
      {error ? <Alert tone="danger" title={error} /> : null}

      {loading ? <LoadingState variant="board" label="Loading prices…" /> : null}

      {!loading && payload ? (
        <div className="abikan-table-wrap">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>Ward / room</th>
                <th>How it is priced</th>
                <th>Daily price ({payload.currency?.code || "NGN"})</th>
                <th>Ready to bill</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {payload.areas.map((area) => (
                <tr key={area.areaUuid}>
                  <td>
                    <strong>{area.areaName}</strong>
                    <p className="acc-settings__hint">
                      {area.beds === 1 ? "1 bed" : `${area.beds} beds`}
                    </p>
                  </td>
                  <td>{area.priceKindLabel}</td>
                  <td>
                    <label className="acc-settings__price">
                      <span className="acc-settings__sr">
                        Daily price for {area.areaName} in {payload.currency?.code || "NGN"}
                      </span>
                      <span className="acc-settings__currency" aria-hidden="true">
                        {payload.currency?.symbol || "₦"}
                      </span>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={drafts[area.areaUuid] ?? ""}
                        onChange={(event) =>
                          setDrafts((current) => ({
                            ...current,
                            [area.areaUuid]: event.target.value,
                          }))
                        }
                      />
                    </label>
                  </td>
                  <td>
                    <Badge tone={area.configured ? "success" : "warning"}>
                      {area.configured ? "Ready" : "Not set"}
                    </Badge>
                  </td>
                  <td>
                    <Button
                      variant="secondary"
                      disabled={savingUuid === area.areaUuid}
                      onClick={() => {
                        void save(area);
                      }}
                    >
                      {savingUuid === area.areaUuid ? "Saving…" : "Save"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
