import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { PatientAccountRequestError } from "../../services/patientAccount";
import {
  createCustomLaboratoryTest,
  fetchCustomLaboratoryTests,
} from "../../services/laboratoryBilling";
import type { LaboratoryCustomTest } from "../../types/laboratoryCatalogue";
import {
  addCreateTestColumn,
  addCreateTestRow,
  createTestDraftError,
  emptyCreateTestDraft,
  removeCreateTestColumn,
  removeCreateTestRow,
  serializeCreateTestDraft,
  type CreateTestDraft,
} from "./laboratoryCreateTest";

function RemoveButton({
  disabled,
  label,
  onClick,
}: {
  disabled?: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className="lab-create-test__icon-btn" disabled={disabled} aria-label={label} onClick={onClick}>
      <Trash2 size={16} strokeWidth={1.75} aria-hidden="true" />
    </button>
  );
}

export function LaboratoryCreateTestView() {
  const [draft, setDraft] = useState<CreateTestDraft>(() => emptyCreateTestDraft());
  const [saved, setSaved] = useState<LaboratoryCustomTest[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = () => {
    setLoading(true);
    fetchCustomLaboratoryTests()
      .then((payload) => {
        setSaved(payload.tests || []);
        setError("");
      })
      .catch((reason) => {
        setSaved([]);
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "Custom tests could not be loaded.",
        );
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const updateColumnName = (columnKey: string, name: string) => {
    setDraft((current) => ({
      ...current,
      columns: current.columns.map((column) =>
        column.key === columnKey ? { ...column, name } : column,
      ),
    }));
  };

  const updateRowName = (rowKey: string, name: string) => {
    setDraft((current) => ({
      ...current,
      rows: current.rows.map((row) => (row.key === rowKey ? { ...row, name } : row)),
    }));
  };

  const updateCell = (rowKey: string, columnKey: string, value: string) => {
    setDraft((current) => ({
      ...current,
      rows: current.rows.map((row) =>
        row.key === rowKey
          ? { ...row, values: { ...row.values, [columnKey]: value } }
          : row,
      ),
    }));
  };

  const onSave = async () => {
    const validation = createTestDraftError(draft);
    if (validation) {
      setError(validation);
      setNotice("");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = await createCustomLaboratoryTest(serializeCreateTestDraft(draft));
      setNotice(payload.message || "Test created in Hospital EMR.");
      setDraft(emptyCreateTestDraft());
      load();
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "The test could not be saved. Try again.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="lab-create-test">
      <PageHeader
        title="Create Test"
        description="Define a laboratory test for this hospital when it is not already available. Add result columns and property rows below."
      />

      {error ? <Alert tone="danger" title={error} /> : null}
      {notice ? <Alert tone="success" title={notice} /> : null}

      <Card>
        <SectionHeader title="Test details" />
        <div className="lab-create-test__details">
          <label className="lab-desk__search">
            Test name
            <input
              value={draft.testName}
              onChange={(event) => setDraft((current) => ({ ...current, testName: event.target.value }))}
              placeholder="e.g. Extended malaria smear"
              disabled={saving}
            />
          </label>
          <label className="lab-desk__search">
            Selling price (₦)
            <input
              value={draft.price}
              onChange={(event) => setDraft((current) => ({ ...current, price: event.target.value }))}
              placeholder="Optional"
              inputMode="decimal"
              disabled={saving}
            />
          </label>
        </div>
      </Card>

      <Card>
        <SectionHeader
          title="Result columns and properties"
          description="Name column holds property labels. Use + to add more result columns or more property rows."
        />
        <div className="lab-create-test__table-wrap">
          <table className="lab-create-test__table">
            <thead>
              <tr>
                <th scope="col" className="lab-create-test__name-col">
                  Name
                </th>
                {draft.columns.map((column) => (
                  <th key={column.key} scope="col">
                    <div className="lab-create-test__col-head">
                      <input
                        value={column.name}
                        onChange={(event) => updateColumnName(column.key, event.target.value)}
                        placeholder="Column name"
                        aria-label="Result column name"
                        disabled={saving}
                      />
                      <RemoveButton
                        disabled={saving || draft.columns.length <= 1}
                        label={`Remove column ${column.name || "untitled"}`}
                        onClick={() => setDraft((current) => removeCreateTestColumn(current, column.key))}
                      />
                    </div>
                  </th>
                ))}
                <th scope="col" className="lab-create-test__add-col">
                  <button
                    type="button"
                    className="lab-create-test__add"
                    disabled={saving}
                    onClick={() => setDraft((current) => addCreateTestColumn(current))}
                    aria-label="Add result column"
                  >
                    <Plus size={18} strokeWidth={2} aria-hidden="true" />
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {draft.rows.map((row) => (
                <tr key={row.key}>
                  <td className="lab-create-test__name-col">
                    <div className="lab-create-test__row-head">
                      <input
                        value={row.name}
                        onChange={(event) => updateRowName(row.key, event.target.value)}
                        placeholder="Property name"
                        aria-label="Property name"
                        disabled={saving}
                      />
                      <RemoveButton
                        disabled={saving || draft.rows.length <= 1}
                        label={`Remove property ${row.name || "untitled"}`}
                        onClick={() => setDraft((current) => removeCreateTestRow(current, row.key))}
                      />
                    </div>
                  </td>
                  {draft.columns.map((column) => (
                    <td key={column.key}>
                      <input
                        value={row.values[column.key] || ""}
                        onChange={(event) => updateCell(row.key, column.key, event.target.value)}
                        placeholder="Value"
                        aria-label={`${row.name || "Property"} for ${column.name || "column"}`}
                        disabled={saving}
                      />
                    </td>
                  ))}
                  <td className="lab-create-test__add-col" />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="lab-create-test__actions">
          <Button
            variant="secondary"
            disabled={saving}
            onClick={() => setDraft((current) => addCreateTestRow(current))}
          >
            <Plus size={16} strokeWidth={2} aria-hidden="true" /> Add property row
          </Button>
          <Button disabled={saving} onClick={() => void onSave()}>
            {saving ? "Saving…" : "Save test"}
          </Button>
        </div>
      </Card>

      <Card>
        <SectionHeader title="Tests created in Hospital EMR" />
        {loading ? <LoadingState variant="board" label="Loading custom tests…" /> : null}
        {!loading && saved.length === 0 ? (
          <EmptyState
            title="No custom tests yet"
            description="Create the first hospital test above. Saved tests appear here."
          />
        ) : null}
        {!loading && saved.length > 0 ? (
          <div className="abikan-table-wrap">
            <table className="abikan-table">
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Columns</th>
                  <th>Properties</th>
                  <th>Price</th>
                </tr>
              </thead>
              <tbody>
                {saved.map((test) => (
                  <tr key={test.id}>
                    <td>{test.name}</td>
                    <td>{test.columns.filter(Boolean).join(", ") || "—"}</td>
                    <td>{test.properties.length}</td>
                    <td>{test.priceLabel || "—"}</td>
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
