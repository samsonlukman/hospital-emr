import { useEffect, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { KpiCard } from "../../components/KpiCard";
import { SectionHeader } from "../../components/SectionHeader";
import { TableSkeleton } from "../../components/TableSkeleton";
import {
  fetchBloodBankUnits,
  receiveBloodBankUnit,
  updateBloodBankUnitStatus,
} from "../../services/laboratoryBilling";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type { BloodBankUnit } from "../../types/laboratoryCatalogue";

function unitTone(status: string): "success" | "warning" | "info" | "danger" | "neutral" {
  if (status === "available") {
    return "success";
  }
  if (status === "reserved") {
    return "info";
  }
  if (status === "issued") {
    return "neutral";
  }
  if (status === "expired" || status === "discarded") {
    return "danger";
  }
  return "warning";
}

export function BloodBankUnitsPanel() {
  const [units, setUnits] = useState<BloodBankUnit[]>([]);
  const [components, setComponents] = useState<string[]>([]);
  const [aboGroups, setAboGroups] = useState<string[]>([]);
  const [rhTypes, setRhTypes] = useState<string[]>([]);
  const [counts, setCounts] = useState({ available: 0, reserved: 0, total: 0, expiringOrExpired: 0 });
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [component, setComponent] = useState("Whole blood");
  const [abo, setAbo] = useState("O");
  const [rh, setRh] = useState("Positive");
  const [bagNumber, setBagNumber] = useState("");
  const [expiresOn, setExpiresOn] = useState("");
  const [collectedOn, setCollectedOn] = useState("");
  const [volumeMl, setVolumeMl] = useState("");
  const [source, setSource] = useState("");
  const [receiveOpen, setReceiveOpen] = useState(false);

  const [actionId, setActionId] = useState("");
  const [actionStatus, setActionStatus] = useState("reserved");
  const [patientName, setPatientName] = useState("");
  const [discardReason, setDiscardReason] = useState("");

  const load = (search = query, status = statusFilter) => {
    setLoading(true);
    fetchBloodBankUnits(search, status === "all" ? "" : status)
      .then((payload) => {
        setUnits(payload.units || []);
        setComponents(payload.components || []);
        setAboGroups(payload.aboGroups || []);
        setRhTypes(payload.rhTypes || []);
        setCounts(payload.counts || { available: 0, reserved: 0, total: 0, expiringOrExpired: 0 });
        if (payload.components?.[0] && !payload.components.includes(component)) {
          setComponent(payload.components[0]);
        }
        setError("");
      })
      .catch((reason) => {
        setUnits([]);
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "Blood Bank units could not be loaded.",
        );
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load("", "all");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onReceive = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = await receiveBloodBankUnit({
        component,
        abo,
        rh,
        bagNumber,
        expiresOn,
        collectedOn: collectedOn || undefined,
        volumeMl: volumeMl ? Number(volumeMl) : null,
        source: source || undefined,
      });
      setNotice(payload.message || "Blood unit added.");
      setBagNumber("");
      setExpiresOn("");
      setCollectedOn("");
      setVolumeMl("");
      setSource("");
      setReceiveOpen(false);
      load(query, statusFilter);
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The blood unit could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  };

  const onUpdateStatus = async () => {
    if (!actionId) {
      setError("Choose a blood unit.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = await updateBloodBankUnitStatus(actionId, {
        status: actionStatus,
        patientName: patientName || undefined,
        discardReason: discardReason || undefined,
      });
      setNotice(payload.message || "Blood unit updated.");
      setPatientName("");
      setDiscardReason("");
      load(query, statusFilter);
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The blood unit could not be updated.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="lab-blood-units">
      {error ? <Alert tone="danger" title={error} /> : null}
      {notice ? <Alert tone="success" title={notice} /> : null}

      <section className="lab-desk__kpis" aria-label="Blood unit stock">
        <KpiCard label="Available" value={loading ? "—" : counts.available} hint="Ready to cross-match or issue" tone="teal" icon="flask" />
        <KpiCard label="Reserved" value={loading ? "—" : counts.reserved} hint="Held for a patient" tone="visits" icon="clipboardList" />
        <KpiCard label="In bank" value={loading ? "—" : counts.total} hint="All tracked units" tone="collection" icon="dashboard" />
        <KpiCard
          label="Expiry watch"
          value={loading ? "—" : counts.expiringOrExpired}
          hint="Past expiry while still on shelf"
          tone="appointments"
          icon="activity"
        />
      </section>

      <div className="lab-blood-units__receive-action">
        <div>
          <h2>Blood unit stock</h2>
          <p>Add newly received blood bags before they are available for use.</p>
        </div>
        <Button onClick={() => setReceiveOpen(true)}>Receive blood unit</Button>
      </div>

      {receiveOpen ? (
        <div className="lab-blood-units__modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="receive-blood-title">
          <div className="lab-blood-units__modal">
            <div className="lab-blood-units__modal-header">
              <div>
                <h2 id="receive-blood-title">Receive blood unit</h2>
                <p>Record a bag or unit into the bank. Use ABO, Rh, bag number, and expiry.</p>
              </div>
              <button type="button" className="lab-blood-units__close" onClick={() => setReceiveOpen(false)} disabled={busy}>
                Close
              </button>
            </div>
            <Card>
          <SectionHeader
            title="Unit details"
            description="Required fields are component, blood group, bag number, and expiry date."
          />
          <div className="lab-inventory__form">
            <label className="lab-desk__search">
              Component
              <select value={component} onChange={(event) => setComponent(event.target.value)} disabled={busy}>
                {(components.length ? components : ["Whole blood"]).map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="lab-desk__search">
              ABO
              <select value={abo} onChange={(event) => setAbo(event.target.value)} disabled={busy}>
                {(aboGroups.length ? aboGroups : ["A", "B", "AB", "O"]).map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="lab-desk__search">
              Rh
              <select value={rh} onChange={(event) => setRh(event.target.value)} disabled={busy}>
                {(rhTypes.length ? rhTypes : ["Positive", "Negative"]).map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="lab-desk__search">
              Bag / unit number
              <input value={bagNumber} onChange={(event) => setBagNumber(event.target.value)} disabled={busy} />
            </label>
            <label className="lab-desk__search">
              Expiry date
              <input type="date" value={expiresOn} onChange={(event) => setExpiresOn(event.target.value)} disabled={busy} />
            </label>
            <label className="lab-desk__search">
              Collection date
              <input type="date" value={collectedOn} onChange={(event) => setCollectedOn(event.target.value)} disabled={busy} />
            </label>
            <label className="lab-desk__search">
              Volume (ml)
              <input value={volumeMl} onChange={(event) => setVolumeMl(event.target.value)} inputMode="decimal" disabled={busy} />
            </label>
            <label className="lab-desk__search">
              Source
              <input
                value={source}
                onChange={(event) => setSource(event.target.value)}
                placeholder="Donor centre or hospital note"
                disabled={busy}
              />
            </label>
            <Button disabled={busy || !bagNumber.trim() || !expiresOn} onClick={() => void onReceive()}>
              {busy ? "Saving…" : "Add to blood bank"}
            </Button>
          </div>
            </Card>
          </div>
        </div>
      ) : null}

      <div className="lab-inventory__grid">
        <Card>
          <SectionHeader
            title="Update unit status"
            description="Reserve for cross-match, issue to a patient, or discard. Issued and discarded units stay closed."
          />
          <div className="lab-inventory__form">
            <label className="lab-desk__search">
              Blood unit
              <select value={actionId} onChange={(event) => setActionId(event.target.value)} disabled={busy}>
                <option value="">Choose unit</option>
                {units.map((unit) => (
                  <option key={unit.id} value={unit.id}>
                    {unit.bagNumber} · {unit.bloodGroupLabel} · {unit.statusLabel}
                  </option>
                ))}
              </select>
            </label>
            <label className="lab-desk__search">
              New status
              <select value={actionStatus} onChange={(event) => setActionStatus(event.target.value)} disabled={busy}>
                <option value="available">Available</option>
                <option value="reserved">Reserved</option>
                <option value="issued">Issued</option>
                <option value="discarded">Discarded</option>
              </select>
            </label>
            {actionStatus === "reserved" || actionStatus === "issued" ? (
              <label className="lab-desk__search">
                Patient name
                <input value={patientName} onChange={(event) => setPatientName(event.target.value)} disabled={busy} />
              </label>
            ) : null}
            {actionStatus === "discarded" ? (
              <label className="lab-desk__search">
                Discard reason
                <input value={discardReason} onChange={(event) => setDiscardReason(event.target.value)} disabled={busy} />
              </label>
            ) : null}
            <Button disabled={busy || !actionId} onClick={() => void onUpdateStatus()}>
              {busy ? "Saving…" : "Update unit"}
            </Button>
          </div>
        </Card>
      </div>

      <Card>
        <SectionHeader title="Units in the bank" description="Hospital blood unit stock with ABO/Rh, bag number, expiry, and status." />
        <div className="lab-blood-units__filters">
          <label className="lab-desk__search">
            Search
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Bag number, group, patient"
            />
          </label>
          <label className="lab-desk__search">
            Status
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All</option>
              <option value="available">Available</option>
              <option value="reserved">Reserved</option>
              <option value="issued">Issued</option>
              <option value="expired">Expired</option>
              <option value="discarded">Discarded</option>
            </select>
          </label>
          <Button variant="secondary" disabled={loading} onClick={() => load(query, statusFilter)}>
            Refresh
          </Button>
        </div>
        {loading ? (
          <TableSkeleton
            label="Loading blood units…"
            headers={["Bag", "Group", "Component", "Expiry", "Status", "Patient"]}
          />
        ) : null}
        {!loading && units.length === 0 ? (
          <EmptyState
            title="No blood units yet"
            description="Receive the first bag above. Grouping and cross-match requests stay on the Requests tab."
          />
        ) : null}
        {!loading && units.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Bag / unit</th>
                  <th>Group</th>
                  <th>Component</th>
                  <th>Expiry</th>
                  <th>Status</th>
                  <th>Patient</th>
                </tr>
              </thead>
              <tbody>
                {units.map((unit) => (
                  <tr key={unit.id}>
                    <td>
                      <strong>{unit.bagNumber}</strong>
                      {unit.volumeMl ? <div className="lab-blood-bank__subtle">{unit.volumeMl} ml</div> : null}
                    </td>
                    <td>{unit.bloodGroupLabel}</td>
                    <td>{unit.component}</td>
                    <td>{unit.expiresOn || "—"}</td>
                    <td>
                      <Badge tone={unitTone(unit.status)}>{unit.statusLabel}</Badge>
                    </td>
                    <td>{unit.patientName || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
