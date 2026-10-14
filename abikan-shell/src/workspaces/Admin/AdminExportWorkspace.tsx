import { useEffect, useMemo, useState } from "react";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import {
  deleteAdminExport,
  downloadAdminExport,
  fetchAdminExportCatalog,
  fetchAdminExportHistory,
  generateAdminExport,
} from "../../services/adminExport";
import { PatientAccountRequestError } from "../../services/patientAccount";
import type {
  AdminExportCatalog,
  AdminExportDatasetOption,
  AdminExportFormat,
  AdminExportRecord,
} from "../../types/adminExport";
import { customRangeValid } from "./adminAnalytics";
import {
  exportOutcomeTone,
  filterHistory,
  formatExportTime,
  formatFileSize,
  formatRecordCount,
} from "./adminExportView";
import "./AdminWorkspace.css";

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof PatientAccountRequestError || reason instanceof Error
    ? reason.message
    : fallback;
}

export function AdminExportWorkspace() {
  const [catalog, setCatalog] = useState<AdminExportCatalog | null>(null);
  const [history, setHistory] = useState<AdminExportRecord[]>([]);
  const [dataset, setDataset] = useState("patients");
  const [department, setDepartment] = useState("");
  const [period, setPeriod] = useState("today");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [status, setStatus] = useState("");
  const [format, setFormat] = useState<AdminExportFormat>("csv");
  const [search, setSearch] = useState("");
  const [historyDataset, setHistoryDataset] = useState("");
  const [historyOutcome, setHistoryOutcome] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selectedDataset: AdminExportDatasetOption | undefined = catalog?.datasets.find(
    (item) => item.id === dataset,
  );
  const customProblem =
    selectedDataset?.usesDateRange && period === "custom"
      ? customRangeValid(customStart, customEnd)
      : "";

  const filteredHistory = useMemo(
    () => filterHistory(history, search, historyDataset, historyOutcome),
    [history, search, historyDataset, historyOutcome],
  );
  const selected = filteredHistory.find((item) => item.exportId === selectedId) ?? null;

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [nextCatalog, nextHistory] = await Promise.all([
        fetchAdminExportCatalog(),
        fetchAdminExportHistory(),
      ]);
      setCatalog(nextCatalog);
      setHistory(nextHistory.exports);
      if (!nextCatalog.datasets.some((item) => item.id === dataset)) {
        setDataset(nextCatalog.datasets[0]?.id || "patients");
      }
    } catch (reason) {
      setError(errorMessage(reason, "Data exports could not be loaded."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (!selectedDataset) {
      return;
    }
    const allowed = new Set(selectedDataset.statuses.map((item) => item.id));
    if (selectedDataset.statuses.length && !allowed.has(status)) {
      setStatus(selectedDataset.statuses[0].id);
    }
    if (!selectedDataset.usesDepartment) {
      setDepartment("");
    }
    if (!selectedDataset.usesDateRange && period !== "current") {
      setPeriod("today");
    }
  }, [selectedDataset, status, period]);

  const generate = async () => {
    if (!selectedDataset) {
      return;
    }
    if (customProblem) {
      setError(customProblem);
      return;
    }
    setGenerating(true);
    setError("");
    setNotice("");
    try {
      const result = await generateAdminExport({
        dataset,
        format,
        period: selectedDataset.usesDateRange ? period : "today",
        start: period === "custom" ? customStart : "",
        end: period === "custom" ? customEnd : "",
        department: selectedDataset.usesDepartment ? department : "",
        status: selectedDataset.statuses.length ? status : "",
      });
      setHistory((current) => [result.export, ...current.filter((item) => item.exportId !== result.export.exportId)]);
      setSelectedId(result.export.exportId);
      setNotice(
        result.export.recordCount
          ? `${result.export.datasetLabel} export is ready. ${formatRecordCount(result.export.recordCount)} records.`
          : `${result.export.datasetLabel} export is ready. No records matched these filters.`,
      );
      if (result.export.canDownload) {
        await downloadAdminExport(result.export.exportId, result.export.filename);
      }
    } catch (reason) {
      setError(errorMessage(reason, "The export could not be generated."));
      void fetchAdminExportHistory()
        .then((payload) => setHistory(payload.exports))
        .catch(() => undefined);
    } finally {
      setGenerating(false);
    }
  };

  const download = async (item: AdminExportRecord) => {
    setError("");
    try {
      await downloadAdminExport(item.exportId, item.filename);
    } catch (reason) {
      setError(errorMessage(reason, "This export file is no longer available."));
      void load();
    }
  };

  const remove = async (item: AdminExportRecord) => {
    setError("");
    try {
      const result = await deleteAdminExport(item.exportId);
      setHistory((current) =>
        current.map((row) => (row.exportId === item.exportId ? result.export : row)),
      );
      setNotice("The export file was deleted. The history record remains.");
    } catch (reason) {
      setError(errorMessage(reason, "The export file could not be deleted."));
    }
  };

  return (
    <div className="admin-workspace admin-export">
      <PageHeader
        title="Data export"
        description="Download hospital records for the dates and department you choose. Files are removed after one day."
      />

      {error ? <Alert tone="danger" title={error} /> : null}
      {notice ? <Alert tone="success" title={notice} /> : null}
      {loading ? <LoadingState variant="board" label="Loading data exports…" /> : null}

      {!loading && catalog ? (
        <form
          className="admin-export__form"
          onSubmit={(event) => {
            event.preventDefault();
            void generate();
          }}
        >
          <label>
            Data to export
            <select value={dataset} onChange={(event) => setDataset(event.target.value)}>
              {catalog.datasets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          {selectedDataset?.usesDepartment ? (
            <label>
              Department
              <select value={department} onChange={(event) => setDepartment(event.target.value)}>
                {selectedDataset.departments.map((item) => (
                  <option key={item.id || "all"} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          {selectedDataset?.usesDateRange ? (
            <label>
              Date range
              <select value={period} onChange={(event) => setPeriod(event.target.value)}>
                {catalog.periods.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <p className="admin-workspace__hint">This export uses the current hospital list, not a date range.</p>
          )}

          {selectedDataset?.usesDateRange && period === "custom" ? (
            <>
              <label>
                From
                <input
                  type="date"
                  value={customStart}
                  onChange={(event) => setCustomStart(event.target.value)}
                />
              </label>
              <label>
                To
                <input
                  type="date"
                  value={customEnd}
                  onChange={(event) => setCustomEnd(event.target.value)}
                />
              </label>
            </>
          ) : null}

          {selectedDataset?.statuses.length ? (
            <label>
              Status
              <select value={status} onChange={(event) => setStatus(event.target.value)}>
                {selectedDataset.statuses.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          <label>
            Format
            <select
              value={format}
              onChange={(event) => setFormat(event.target.value as AdminExportFormat)}
            >
              {catalog.formats.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <div className="admin-export__actions">
            <Button type="submit" busy={generating} busyLabel="Generating export…" disabled={Boolean(customProblem)}>
              Generate export
            </Button>
            <p className="admin-workspace__hint">
              {selectedDataset?.kind === "financial"
                ? "Money figures come from posted bills and payments only. "
                : ""}
              Files stay available for {catalog.fileHours} hours.
            </p>
          </div>
        </form>
      ) : null}

      <section className="admin-export__history" aria-label="Export history">
        <h2>Export history</h2>
        <p className="admin-analytics__range">Who exported what, and whether the file is still available.</p>

        <div className="admin-export__history-filters">
          <label>
            Search
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by dataset or administrator"
            />
          </label>
          <label>
            Dataset
            <select value={historyDataset} onChange={(event) => setHistoryDataset(event.target.value)}>
              <option value="">All datasets</option>
              {(catalog?.datasets ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Result
            <select value={historyOutcome} onChange={(event) => setHistoryOutcome(event.target.value)}>
              <option value="">All results</option>
              <option value="success">Success</option>
              <option value="failed">Failed</option>
            </select>
          </label>
        </div>

        {!loading && !error && filteredHistory.length === 0 ? (
          <EmptyState
            title="No exports yet"
            description="Generate an export to keep a record here. Ordinary staff cannot see this list."
          />
        ) : null}

        {filteredHistory.length ? (
          <div className="admin-workspace__table admin-export__table">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Format</th>
                  <th>Administrator</th>
                  <th>Date and time</th>
                  <th>Records</th>
                  <th>Status</th>
                  <th>File</th>
                </tr>
              </thead>
              <tbody>
                {filteredHistory.map((item) => (
                  <tr
                    key={item.exportId}
                    className={item.exportId === selectedId ? "admin-export__row--selected" : undefined}
                  >
                    <td>
                      <button
                        type="button"
                        className="admin-export__select"
                        onClick={() => setSelectedId(item.exportId)}
                      >
                        {item.datasetLabel}
                      </button>
                      <span className="admin-audit__meta">{item.periodLabel}</span>
                    </td>
                    <td>{item.formatLabel}</td>
                    <td>{item.adminDisplayName || item.adminUsername}</td>
                    <td>{formatExportTime(item.createdAt)}</td>
                    <td>{formatRecordCount(item.recordCount)}</td>
                    <td>
                      <Badge tone={exportOutcomeTone(item.outcome)}>{item.outcomeLabel}</Badge>
                    </td>
                    <td>
                      <div className="admin-export__row-actions">
                        {item.canDownload ? (
                          <Button variant="secondary" onClick={() => void download(item)}>
                            Download
                          </Button>
                        ) : (
                          <span className="admin-audit__meta">{item.fileStatusLabel}</span>
                        )}
                        {item.canDelete ? (
                          <Button variant="ghost" onClick={() => void remove(item)}>
                            Delete file
                          </Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {selected ? (
          <aside className="admin-export__details" aria-label="Export details">
            <h3>Export details</h3>
            <dl>
              <div>
                <dt>Dataset</dt>
                <dd>{selected.datasetLabel}</dd>
              </div>
              <div>
                <dt>Format</dt>
                <dd>{selected.formatLabel}</dd>
              </div>
              <div>
                <dt>Administrator</dt>
                <dd>{selected.adminDisplayName || selected.adminUsername}</dd>
              </div>
              <div>
                <dt>Department</dt>
                <dd>{selected.departmentLabel}</dd>
              </div>
              <div>
                <dt>Date range</dt>
                <dd>{selected.periodLabel}</dd>
              </div>
              <div>
                <dt>Status filter</dt>
                <dd>{selected.statusLabel}</dd>
              </div>
              <div>
                <dt>Records</dt>
                <dd>{formatRecordCount(selected.recordCount)}</dd>
              </div>
              <div>
                <dt>File size</dt>
                <dd>{formatFileSize(selected.fileSize)}</dd>
              </div>
              <div>
                <dt>File</dt>
                <dd>{selected.fileStatusLabel}</dd>
              </div>
            </dl>
          </aside>
        ) : null}
      </section>
    </div>
  );
}
