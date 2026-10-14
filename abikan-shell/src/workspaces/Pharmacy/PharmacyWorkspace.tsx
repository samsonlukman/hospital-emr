import { useEffect, useMemo, useState } from "react";
import {
  openPharmacyCatalogueAdd,
  openPharmacyPrescription,
  openPharmacySection,
  pharmacyCatalogueAddRequested,
  readHashNavItemId,
} from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { KpiCard } from "../../components/KpiCard";
import { PageHeader } from "../../components/PageHeader";
import { QuickAction } from "../../components/QuickAction";
import { SectionHeader } from "../../components/SectionHeader";
import { PatientAccountRequestError } from "../../services/patientAccount";
import {
  createPharmacyCatalogueItem,
  fetchPharmacyCatalogue,
  fetchPharmacyCatalogueForms,
  fetchPharmacyInventory,
  fetchPharmacyInventoryHistory,
  fetchPharmacyQueue,
  updatePharmacyCatalogueItem,
} from "../../services/pharmacy";
import type {
  PharmacyCatalogueDraft,
  PharmacyCatalogueItem,
  PharmacyInventoryHistoryRow,
  PharmacyInventoryItem,
  PharmacyPrescription,
  PharmacyQueue,
} from "../../types/pharmacy";
import type { WorkspaceContext } from "../../types";
import { PricingDesk } from "../Pricing/PricingDesk";
import { greetingForNow } from "../../utils/datetime";
import { CatalogueFormDialog, InventoryHistoryDialog } from "./PharmacyDialogs";
import { PharmacyNewSaleView } from "./PharmacyNewSaleView";
import { PharmacySalesHistoryView } from "./PharmacySalesHistoryView";
import { PharmacyStockEntryView, type StockEntryMode } from "./PharmacyStockEntryView";
import { PharmacyCatalogueAddView } from "./PharmacyCatalogueAddView";
import {
  RevenueGeneratedCard,
  RevenuePeriodFilter,
  useDepartmentRevenue,
} from "../shared/DepartmentRevenue";
import {
  ADJUST_REASONS,
  catalogueDraftError,
  catalogueStockLabel,
  draftFromCatalogueItem,
  emptyCatalogueDraft,
  formatStockQty,
  groupPrescriptionsForList,
  listIsNotInPharmacy,
  medicineDisplayName,
  pharmacyLineStatusLabel,
  prescriptionDispenseLabel,
  matchesCatalogueSearch,
  matchesInventorySearch,
  matchesPharmacySearch,
  needsAttention,
  pharmacyStaffError,
  pharmacyViewFromNav,
  type PharmacyView,
} from "./pharmacyView";
import "./PharmacyWorkspace.css";

interface PharmacyWorkspaceProps {
  context: WorkspaceContext;
}

function focusPatientSearch() {
  document.getElementById("global-patient-search")?.focus();
}

export function PharmacyWorkspace({ context }: PharmacyWorkspaceProps) {
  const [view, setView] = useState<PharmacyView>(() => pharmacyViewFromNav(readHashNavItemId()));
  const [queue, setQueue] = useState<PharmacyQueue | null>(null);
  const [catalogue, setCatalogue] = useState<PharmacyCatalogueItem[]>([]);
  const [catalogueForms, setCatalogueForms] = useState<string[]>(["Tablet"]);
  const [inventory, setInventory] = useState<PharmacyInventoryItem[]>([]);
  const [inventoryReasons, setInventoryReasons] = useState<string[]>(ADJUST_REASONS);
  const [canManageInventory, setCanManageInventory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [catalogueLoading, setCatalogueLoading] = useState(
    () => pharmacyViewFromNav(readHashNavItemId()) === "catalogue",
  );
  const [inventoryLoading, setInventoryLoading] = useState(
    () => pharmacyViewFromNav(readHashNavItemId()) === "inventory",
  );
  const [error, setError] = useState("");
  const [catalogueError, setCatalogueError] = useState("");
  const [inventoryError, setInventoryError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");
  const [formMode, setFormMode] = useState<"add" | "edit" | null>(null);
  const [formDraft, setFormDraft] = useState<PharmacyCatalogueDraft>(emptyCatalogueDraft);
  const [editingId, setEditingId] = useState("");
  const [stockEntryMode, setStockEntryMode] = useState<StockEntryMode | null>(null);
  const [stockEntrySeed, setStockEntrySeed] = useState<PharmacyInventoryItem | null>(null);
  const [historyItem, setHistoryItem] = useState<PharmacyInventoryItem | null>(null);
  const [historyRows, setHistoryRows] = useState<PharmacyInventoryHistoryRow[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");

  const loadQueue = (silent = false) => {
    if (!silent) {
      setLoading(true);
    }
    setError("");
    return fetchPharmacyQueue()
      .then((payload) => {
        setQueue(payload);
      })
      .catch((reason) => {
        setQueue(null);
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "Prescriptions could not be loaded. You can still search for a patient.",
        );
      })
      .finally(() => setLoading(false));
  };

  const loadCatalogue = () => {
    setCatalogueLoading(true);
    setCatalogueError("");
    return fetchPharmacyCatalogue()
      .then((payload) => {
        setCatalogue(payload.items || []);
      })
      .catch((reason) => {
        setCatalogue([]);
        setCatalogueError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "The medicine list could not be loaded. Refresh and try again.",
        );
      })
      .finally(() => setCatalogueLoading(false));
  };

  const loadInventory = () => {
    setInventoryLoading(true);
    setInventoryError("");
    return fetchPharmacyInventory()
      .then((payload) => {
        setInventory(payload.items || []);
        setCanManageInventory(Boolean(payload.canManageInventory));
        if (payload.adjustmentReasons?.length) {
          setInventoryReasons(payload.adjustmentReasons);
        }
      })
      .catch((reason) => {
        setInventory([]);
        setInventoryError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "Pharmacy stock could not be loaded. Refresh and try again.",
        );
      })
      .finally(() => setInventoryLoading(false));
  };

  useEffect(() => {
    void loadQueue();
  }, []);

  useEffect(() => {
    const sync = () => {
      setView(pharmacyViewFromNav(readHashNavItemId()));
      if (pharmacyCatalogueAddRequested()) {
        setFormMode("add");
        setEditingId("");
        setFormDraft(emptyCatalogueDraft());
        setDialogError("");
      }
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    if (view !== "catalogue") {
      setFormMode(null);
      setEditingId("");
    }
    if (view !== "inventory") {
      setStockEntryMode(null);
      setStockEntrySeed(null);
    }
  }, [view]);

  useEffect(() => {
    if (view === "catalogue") {
      void loadCatalogue();
      void fetchPharmacyCatalogueForms()
        .then((payload) => {
          if (payload.forms?.length) {
            setCatalogueForms(payload.forms);
          }
        })
        .catch(() => undefined);
    }
    if (view === "inventory") {
      void loadInventory();
    }
  }, [view]);

  const ready = queue?.ready ?? [];
  const other = queue?.other ?? [];
  const all = useMemo(
    () =>
      [...ready, ...other].sort((left, right) => (right.ordered || "").localeCompare(left.ordered || "")),
    [ready, other],
  );
  const attention = needsAttention(all);

  const closeForm = () => {
    setFormMode(null);
    setEditingId("");
    setDialogError("");
  };

  const closeStockDialogs = () => {
    setStockEntryMode(null);
    setStockEntrySeed(null);
    setHistoryItem(null);
    setHistoryRows([]);
    setHistoryError("");
    setDialogError("");
  };

  const openStockEntry = (mode: StockEntryMode, seed: PharmacyInventoryItem | null = null) => {
    setStockEntryMode(mode);
    setStockEntrySeed(seed);
    setDialogError("");
    setNotice("");
  };

  const openHistory = (row: PharmacyInventoryItem) => {
    setHistoryItem(row);
    setHistoryRows([]);
    setHistoryError("");
    setHistoryLoading(true);
    void fetchPharmacyInventoryHistory(row.id)
      .then((payload) => {
        setHistoryRows(payload.movements || []);
      })
      .catch((reason) => {
        setHistoryError(pharmacyStaffError(reason, "Stock history could not be loaded."));
      })
      .finally(() => setHistoryLoading(false));
  };

  const handleSaveCatalogue = async () => {
    const problem = catalogueDraftError(formDraft, formMode === "edit" ? "edit" : "add");
    if (problem) {
      setDialogError(problem);
      return;
    }
    setBusy(true);
    setDialogError("");
    try {
      if (formMode === "edit" && editingId) {
        await updatePharmacyCatalogueItem(editingId, formDraft);
        setNotice("Medicine updated.");
      } else {
        await createPharmacyCatalogueItem(formDraft);
        setNotice("Medicine added to the hospital catalogue.");
      }
      closeForm();
      await loadCatalogue();
    } catch (reason) {
      setDialogError(pharmacyStaffError(reason, "The medicine could not be saved."));
    } finally {
      setBusy(false);
    }
  };

  const pageTitle =
    view === "prescriptions"
      ? "Prescriptions"
      : view === "new-sale"
        ? "New Sale"
        : view === "sales-history"
          ? "Sales History"
          : view === "catalogue"
            ? formMode === "add"
              ? "Add Multiple Medicines"
              : "Drug Catalogue"
            : view === "pricing"
              ? "Drug Pricing"
            : view === "inventory"
              ? "Inventory"
            : "Pharmacy";
  const pageDescription =
    view === "prescriptions"
      ? "Open a prescription to dispense or delete medicines."
      : view === "new-sale"
        ? ""
        : view === "sales-history"
          ? "Past pharmacy sales, with payment and dispensing shown separately."
          : view === "catalogue"
            ? formMode === "add"
              ? "Add one or more medicines to the catalogue. Stock levels cannot be changed here."
              : "Medicines available to search at the pharmacy counter."
            : view === "pricing"
              ? "Selling prices for hospital medicines. Changing a price does not change bills already created."
            : view === "inventory"
              ? "How much of each medicine is on the shelf now."
            : `${greetingForNow()}, ${context.displayName}. What needs attention at the counter?`;

  if (view === "pricing") {
    return (
      <PricingDesk
        department="pharmacy"
        title="Drug Pricing"
        description="Change selling prices for hospital medicines. Changing a price does not change bills already created."
        searchPlaceholder="Medicine name or strength"
      />
    );
  }

  return (
    <div className="pharm-desk">
      {view === "dashboard" ? null : <PageHeader title={pageTitle} description={pageDescription} />}

      {notice ? (
        <Alert tone="success" title="Pharmacy updated">
          <p>{notice}</p>
        </Alert>
      ) : null}
      {error && view !== "catalogue" && view !== "inventory" ? (
        <Alert tone="warning" title="Prescriptions">
          <p>{error}</p>
        </Alert>
      ) : null}
      {catalogueError && view === "catalogue" ? (
        <Alert tone="warning" title="Drug Catalogue">
          <p>{catalogueError}</p>
        </Alert>
      ) : null}
      {inventoryError && view === "inventory" ? (
        <Alert tone="warning" title="Inventory">
          <p>{inventoryError}</p>
        </Alert>
      ) : null}

      {view === "dashboard" ? (
        <DashboardView
          loading={loading}
          allCount={groupPrescriptionsForList(all).length}
          attention={attention}
          unlisted={groupPrescriptionsForList(all).filter((row) => listIsNotInPharmacy(row.lines))}
        />
      ) : null}

      {view === "prescriptions" ? (
        <PrescriptionsView loading={loading} rows={all} onSearch={focusPatientSearch} />
      ) : null}

      {view === "new-sale" ? <PharmacyNewSaleView /> : null}

      {view === "sales-history" ? <PharmacySalesHistoryView /> : null}

      {view === "catalogue" && formMode !== "add" ? (
        <CatalogueView
          loading={catalogueLoading}
          rows={catalogue}
          onAdd={() => {
            setFormMode("add");
            setEditingId("");
            setFormDraft(emptyCatalogueDraft());
            setDialogError("");
            setNotice("");
          }}
          onEdit={(row) => {
            setFormMode("edit");
            setEditingId(row.id);
            setFormDraft(draftFromCatalogueItem(row));
            setDialogError("");
          }}
        />
      ) : null}

      {view === "catalogue" && formMode === "add" ? (
        <PharmacyCatalogueAddView
          forms={catalogueForms}
          onCancel={() => {
            setFormMode(null);
            setEditingId("");
            setDialogError("");
          }}
          onCompleted={(message) => {
            setNotice(message);
            setFormMode(null);
            setEditingId("");
            void loadCatalogue();
          }}
        />
      ) : null}

      {view === "inventory" && !stockEntryMode ? (
        <InventoryView
          loading={inventoryLoading}
          rows={inventory}
          canManage={canManageInventory}
          onReceiveBatch={() => openStockEntry("receive")}
          onAdjustBatch={() => openStockEntry("adjust")}
          onReceive={(row) => openStockEntry("receive", row)}
          onAdjust={(row) => openStockEntry("adjust", row)}
          onHistory={openHistory}
          onAddMedicine={openPharmacyCatalogueAdd}
        />
      ) : null}

      {view === "inventory" && stockEntryMode ? (
        <PharmacyStockEntryView
          mode={stockEntryMode}
          inventory={inventory}
          seed={stockEntrySeed}
          reasons={inventoryReasons}
          onCancel={() => {
            setStockEntryMode(null);
            setStockEntrySeed(null);
          }}
          onCompleted={(message) => {
            setNotice(message);
            setStockEntryMode(null);
            setStockEntrySeed(null);
            void loadInventory();
          }}
        />
      ) : null}

      {formMode === "edit" ? (
        <CatalogueFormDialog
          mode="edit"
          draft={formDraft}
          forms={catalogueForms}
          stockLabel={catalogueStockLabel(
            catalogue.find((row) => row.id === editingId) || { stockOnHand: 0, stockUnits: "" },
          )}
          busy={busy}
          error={dialogError}
          onChange={setFormDraft}
          onCancel={closeForm}
          onSave={() => void handleSaveCatalogue()}
          onError={setDialogError}
        />
      ) : null}
      {historyItem ? (
        <InventoryHistoryDialog
          item={historyItem}
          movements={historyRows}
          loading={historyLoading}
          error={historyError}
          onClose={closeStockDialogs}
        />
      ) : null}
    </div>
  );
}

function DashboardView({
  loading,
  allCount,
  attention,
  unlisted,
}: {
  loading: boolean;
  allCount: number;
  attention: PharmacyPrescription[];
  unlisted: ReturnType<typeof groupPrescriptionsForList>;
}) {
  const revenue = useDepartmentRevenue();
  const attentionRows = groupPrescriptionsForList(attention);
  return (
    <>
      {loading ? <LoadingState variant="board" label="Loading today's pharmacy…" /> : null}
      {!loading ? (
        <section className="pharm-desk__top" aria-label="Today's pharmacy">
          <RevenuePeriodFilter revenue={revenue} caption={null} />
          <KpiCard
            label="Prescriptions"
            value={allCount}
            hint={allCount === 0 ? "None waiting" : "Waiting"}
            tone="visits"
            icon="clipboardList"
            onClick={() => openPharmacySection("prescriptions")}
          />
          <RevenueGeneratedCard revenue={revenue} />
        </section>
      ) : null}

      <Card>
        <SectionHeader title="Quick actions" />
        <div className="pharm-desk__actions">
          <QuickAction
            label="New Sale"
            icon="clipboardPlus"
            tone="visits"
            onClick={() => openPharmacySection("new-sale")}
          />
          <QuickAction
            label="Prescriptions"
            icon="clipboardList"
            tone="visits"
            onClick={() => openPharmacySection("prescriptions")}
          />
          <QuickAction
            label="Find Patient"
            icon="search"
            tone="registration"
            onClick={focusPatientSearch}
          />
          <QuickAction
            label="Sales History"
            icon="receipt"
            tone="teal"
            onClick={() => openPharmacySection("sales-history")}
          />
          <QuickAction
            label="Drug Catalogue"
            icon="fileText"
            tone="registration"
            onClick={() => openPharmacySection("catalogue")}
          />
          <QuickAction
            label="Inventory"
            icon="pill"
            tone="teal"
            onClick={() => openPharmacySection("inventory")}
          />
        </div>
      </Card>

      <Card id="pharmacy-dashboard">
        <SectionHeader title="Needs attention" />
        {loading ? (
          <LoadingState variant="board" label="Loading prescriptions…" />
        ) : attentionRows.length === 0 ? (
          <EmptyState title="No prescriptions requiring attention." />
        ) : (
          <ul className="pharm-person-list">
            {attentionRows.map((row) => (
              <li key={row.key}>
                <PrescriptionListCard row={row} />
              </li>
            ))}
          </ul>
        )}
      </Card>
      {unlisted.length > 0 ? (
        <Card>
          <SectionHeader
            title="Not in Pharmacy"
            description="The doctor typed a medicine that is not in the hospital list. Do not dispense it. It is not on the patient bill."
          />
          <ul className="pharm-person-list">
            {unlisted.map((row) => (
              <li key={row.key}>
                <PrescriptionListCard row={row} />
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}

function PrescriptionsView({
  loading,
  rows,
  onSearch,
}: {
  loading: boolean;
  rows: PharmacyPrescription[];
  onSearch: () => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = rows.filter((row) => matchesPharmacySearch(row, query));
  const listRows = groupPrescriptionsForList(filtered);
  return (
    <Card id="prescriptions">
      <SectionHeader
        title="Prescriptions"
        description="Patient and order. Open one to see medicines, then dispense or delete."
      />
      <div className="pharm-desk__toolbar">
        <label className="pharm-desk__search">
          <span className="pharm-desk__search-label">Find a prescription</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by name or hospital number"
          />
        </label>
        <Button variant="secondary" onClick={onSearch}>
          Search patients
        </Button>
      </div>
      {loading ? (
        <LoadingState variant="board" label="Loading prescriptions…" />
      ) : listRows.length === 0 ? (
        <EmptyState title="No prescriptions found." />
      ) : (
          <ul className="pharm-person-list">
          {listRows.map((row) => (
            <li key={row.key}>
              <PrescriptionListCard row={row} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function PrescriptionListCard({
  row,
}: {
  row: ReturnType<typeof groupPrescriptionsForList>[number];
}) {
  const unlisted = listIsNotInPharmacy(row.lines);
  const dispenseLabel = unlisted ? null : prescriptionDispenseLabel(row.lines);
  const cue = unlisted ? null : prescriptionListCue(row);
  return (
    <button
      type="button"
      className="pharm-rx-list-card"
      onClick={() => openPharmacyPrescription(row.orderUuid)}
    >
      <span className="pharm-rx-list-card__who">
        <strong className="pharm-rx-list-card__patient">{row.patientName}</strong>
        <span className="pharm-rx-list-card__meta">
          <span className="pharm-rx-list-card__mrn">{row.mrn || "Hospital number not recorded"}</span>
          {row.lines.some((line) => line.nhis) ? <Badge tone="info">NHIS</Badge> : null}
        </span>
      </span>
      <span className="pharm-rx-list-card__meds">
        {row.lines.map((line) => {
          const handed =
            line.dispensingStatus === "DISPENSED" || line.dispensingStatus === "PARTIALLY DISPENSED";
          return (
            <span key={line.orderUuid} className={`pharm-rx-list-card__chip${handed ? " is-handed" : ""}`}>
              {medicineDisplayName(line)}
              {unlisted ? null : <span className="pharm-rx-list-card__chip-state">{pharmacyLineStatusLabel(line)}</span>}
            </span>
          );
        })}
        {unlisted ? <span className="pharm-rx-list-card__note">Do not dispense</span> : null}
      </span>
      <span className="pharm-rx-list-card__aside">
        <span className="pharm-rx-list-card__count">
          <strong>{row.medicineCount}</strong>
          <span>{row.medicineCount === 1 ? "medicine" : "medicines"}</span>
          {dispenseLabel ? (
            <span className={`pharm-rx-list-card__cue${dispenseLabel === "Not dispensed" ? "" : " is-dispensed"}`}>
              {dispenseLabel}
            </span>
          ) : null}
          {cue && cue !== "Ready" ? <span className="pharm-rx-list-card__cue">{cue}</span> : null}
        </span>
        <span className="pharm-rx-list-card__go" aria-hidden="true">
          →
        </span>
      </span>
    </button>
  );
}

function prescriptionListCue(row: ReturnType<typeof groupPrescriptionsForList>[number]): string | null {
  if (row.paymentStatus === "UNPAID") {
    return "Payment due";
  }
  if (row.paymentStatus === "PARTIALLY PAID") {
    return "Part paid";
  }
  if (row.lines.some((line) => line.dispensingStatus === "READY TO DISPENSE" || line.canDispense)) {
    return "Ready";
  }
  return null;
}

function CatalogueView({
  loading,
  rows,
  onAdd,
  onEdit,
}: {
  loading: boolean;
  rows: PharmacyCatalogueItem[];
  onAdd: () => void;
  onEdit: (row: PharmacyCatalogueItem) => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = rows.filter((row) => matchesCatalogueSearch(row, query));
  return (
    <Card id="catalogue">
      <SectionHeader
        title="Drug Catalogue"
        description="Search, add, or edit hospital medicines. Stock is shown as it is on the shelf now and cannot be changed here."
      />
      <div className="pharm-desk__toolbar">
        <label className="pharm-desk__search">
          <span className="pharm-desk__search-label">Find a medicine</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by medicine name"
          />
        </label>
        <Button onClick={onAdd}>Add medicines</Button>
      </div>
      {loading ? (
        <LoadingState variant="board" label="Loading medicines…" />
      ) : filtered.length === 0 ? (
        <EmptyState title={query.trim() ? "No medicines found." : "No medicines in the catalogue."} />
      ) : (
        <ul className="pharm-person-list">
          {filtered.map((row) => (
            <li key={`${row.id}-${row.name}-${row.strength}-${row.form}`}>
              <div className="pharm-person-card">
                <strong>{row.name}</strong>
                {row.listedAs ? <span>Also listed as {row.listedAs}</span> : null}
                {row.brandName ? <span>Brand: {row.brandName}</span> : null}
                <span>
                  {[row.strength, row.form].filter(Boolean).join(" · ") || "Strength not recorded"}
                </span>
                <span>{catalogueStockLabel(row)}</span>
                <span>
                  {row.price?.formatted || "Price not set"}
                </span>
                <div className="pharm-person-card__status">
                  <Badge tone={row.available ? "success" : "neutral"}>{row.status}</Badge>
                </div>
                {row.canEdit ? (
                  <div className="pharm-person-card__action">
                    <Button variant="secondary" onClick={() => onEdit(row)}>
                      Edit
                    </Button>
                  </div>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function InventoryView({
  loading,
  rows,
  canManage,
  onReceiveBatch,
  onAdjustBatch,
  onReceive,
  onAdjust,
  onHistory,
  onAddMedicine,
}: {
  loading: boolean;
  rows: PharmacyInventoryItem[];
  canManage: boolean;
  onReceiveBatch: () => void;
  onAdjustBatch: () => void;
  onReceive: (row: PharmacyInventoryItem) => void;
  onAdjust: (row: PharmacyInventoryItem) => void;
  onHistory: (row: PharmacyInventoryItem) => void;
  onAddMedicine: () => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = rows.filter((row) => matchesInventorySearch(row, query));
  return (
    <Card id="inventory">
      <SectionHeader
        title="Inventory"
        description="Physical stock on the pharmacy shelf. Receiving stock records that medicine has arrived. It does not pay a supplier."
      />
      <div className="pharm-desk__toolbar">
        <label className="pharm-desk__search">
          <span className="pharm-desk__search-label">Find a medicine</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by medicine name"
          />
        </label>
        {canManage ? (
          <div className="pharm-inventory__toolbar-actions">
            <Button variant="primary" onClick={onReceiveBatch}>
              Receive Stock
            </Button>
            <Button variant="secondary" onClick={onAdjustBatch}>
              Adjust Stock
            </Button>
          </div>
        ) : null}
        <button type="button" className="pharm-inventory__catalogue-link" onClick={onAddMedicine}>
          Medicine not in catalogue? Add it to Drug Catalogue
        </button>
      </div>
      {loading ? (
        <LoadingState variant="board" label="Loading stock…" />
      ) : filtered.length === 0 ? (
        <EmptyState title={query.trim() ? "No medicines found." : "No medicines in inventory."} />
      ) : (
        <div className="abikan-table-wrap">
          <table className="abikan-table">
            <thead>
              <tr>
                <th>Medicine</th>
                <th>Strength</th>
                <th>Form</th>
                <th>On Hand</th>
                <th>Reserved</th>
                <th>Available</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={`${row.id}-${row.strength}-${row.form}`}>
                  <td>
                    <strong>{row.name}</strong>
                    {row.brandName ? <div className="pharm-inventory__muted">Brand: {row.brandName}</div> : null}
                  </td>
                  <td>{row.strength || "—"}</td>
                  <td>{row.form || "—"}</td>
                  <td>{formatStockQty(row.onHand)}</td>
                  <td>{formatStockQty(row.reserved)}</td>
                  <td>{formatStockQty(row.available)}</td>
                  <td>
                    <Badge
                      tone={
                        row.status === "In stock" ? "success" : row.status === "Reserved" ? "warning" : "neutral"
                      }
                    >
                      {row.status}
                    </Badge>
                  </td>
                  <td>
                    <div className="pharm-inventory__actions">
                      {canManage && row.canReceive ? (
                        <Button variant="secondary" onClick={() => onReceive(row)}>
                          Receive
                        </Button>
                      ) : null}
                      {canManage && row.canAdjust ? (
                        <Button variant="secondary" onClick={() => onAdjust(row)}>
                          Adjust
                        </Button>
                      ) : null}
                      <Button variant="ghost" onClick={() => onHistory(row)}>
                        View History
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
