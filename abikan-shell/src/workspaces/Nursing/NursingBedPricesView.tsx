import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { fetchAccommodationTariffs } from "../../services/accommodation";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { AccommodationTariffPayload } from "../../types/accommodation";

export function NursingBedPricesView() {
  const [payload, setPayload] = useState<AccommodationTariffPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchAccommodationTariffs()
      .then((result) => {
        if (!cancelled) {
          setPayload(result);
          setError("");
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setPayload(null);
          setError(
            reason instanceof PatientAccountRequestError
              ? reason.message
              : "Bed prices could not be loaded.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="nursing-desk nursing-bed-prices">
      <PageHeader
        title="Bed Prices"
        description="Daily ward and room prices for inpatient stays. Nursing can view these prices; Hospital Admin sets them."
      />

      {error ? <Alert tone="danger" title={error} /> : null}
      {payload?.message ? (
        <Alert tone="info" title="No patient tax">
          {payload.message}
        </Alert>
      ) : null}

      {loading ? <LoadingState variant="board" label="Loading bed prices…" /> : null}

      {!loading && payload && payload.areas.length === 0 ? (
        <EmptyState title="No wards configured" description="No hospital wards are available yet." />
      ) : null}

      {!loading && payload && payload.areas.length > 0 ? (
        <div className="abikan-table-wrap">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>Ward / room</th>
                <th>How it is priced</th>
                <th>Daily price</th>
                <th>Ready to bill</th>
              </tr>
            </thead>
            <tbody>
              {payload.areas.map((area) => (
                <tr key={area.areaUuid}>
                  <td>
                    <strong>{area.areaName}</strong>
                    <div className="nursing-bed-prices__hint">
                      {area.beds} {area.beds === 1 ? "bed" : "beds"}
                    </div>
                  </td>
                  <td>{area.priceKindLabel}</td>
                  <td>{area.listPrice.formatted}</td>
                  <td>
                    <Badge tone={area.configured ? "success" : "warning"}>
                      {area.configured ? "Yes" : "Price not set"}
                    </Badge>
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
