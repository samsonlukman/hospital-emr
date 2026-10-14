import { useEffect, useMemo, useState } from "react";
import { openLaboratorySection } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { PatientAccountRequestError } from "../../services/patientAccount";
import {
  disableHospitalLaboratoryTest,
  enableHospitalLaboratoryTest,
  fetchHospitalLaboratoryTests,
  searchMasterLaboratoryTests,
} from "../../services/laboratoryBilling";
import type {
  LaboratoryCatalogueTest,
  LaboratoryMasterTest,
} from "../../types/laboratoryCatalogue";
import { isLabPanel, labCatalogueHitDetails } from "./laboratoryView";

export function LaboratoryHospitalTestsView() {
  const [tests, setTests] = useState<LaboratoryCatalogueTest[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [masterQuery, setMasterQuery] = useState("");
  const [masterHits, setMasterHits] = useState<LaboratoryMasterTest[]>([]);
  const [masterLoading, setMasterLoading] = useState(false);
  const [selectedUuid, setSelectedUuid] = useState("");
  const [busyUuid, setBusyUuid] = useState<string | null>(null);

  const load = (search = query) => {
    setLoading(true);
    setError("");
    fetchHospitalLaboratoryTests(search)
      .then((payload) => {
        setTests(payload.tests);
        setMessage(payload.message || "");
      })
      .catch((reason) => {
        setTests([]);
        setError(
          reason instanceof PatientAccountRequestError
            ? reason.message
            : "Hospital laboratory tests could not be loaded.",
        );
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!adding) {
      return;
    }
    const term = masterQuery.trim();
    if (term.length < 2) {
      setMasterHits([]);
      setMasterLoading(false);
      return;
    }
    let cancelled = false;
    setMasterLoading(true);
    const timer = window.setTimeout(() => {
      searchMasterLaboratoryTests(term)
        .then((payload) => {
          if (!cancelled) {
            setMasterHits(payload.tests);
          }
        })
        .catch((reason) => {
          if (!cancelled) {
            setMasterHits([]);
            setError(
              reason instanceof PatientAccountRequestError
                ? reason.message
                : "Master laboratory catalogue could not be searched.",
            );
          }
        })
        .finally(() => {
          if (!cancelled) {
            setMasterLoading(false);
          }
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [adding, masterQuery]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return tests;
    }
    return tests.filter((row) =>
      [row.name, row.openmrsName, row.type, row.specimen, row.department, row.conceptUuid]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [tests, query]);

  const selected = masterHits.find((row) => row.conceptUuid === selectedUuid) || null;

  const addSelected = async () => {
    if (!selected) {
      setError("Select a test from the master catalogue.");
      return;
    }
    setBusyUuid(selected.conceptUuid);
    setError("");
    setNotice("");
    try {
      const payload = await enableHospitalLaboratoryTest(selected.conceptUuid);
      setNotice(payload.message || "Test added to hospital laboratory catalogue.");
      setAdding(false);
      setMasterQuery("");
      setMasterHits([]);
      setSelectedUuid("");
      load(query);
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "That test could not be added.",
      );
    } finally {
      setBusyUuid(null);
    }
  };

  const removeTest = async (row: LaboratoryCatalogueTest) => {
    const conceptUuid = (row.conceptUuid || "").trim();
    if (!conceptUuid) {
      return;
    }
    const confirmed = window.confirm(
      `Remove “${row.name}” from hospital ordering?\n\nExisting orders and results stay unchanged. The test remains in the master catalogue.`,
    );
    if (!confirmed) {
      return;
    }
    setBusyUuid(conceptUuid);
    setError("");
    setNotice("");
    try {
      const payload = await disableHospitalLaboratoryTest(conceptUuid);
      setNotice(payload.message || "Test removed from hospital ordering.");
      load(query);
    } catch (reason) {
      setError(
        reason instanceof PatientAccountRequestError
          ? reason.message
          : "That test could not be removed.",
      );
    } finally {
      setBusyUuid(null);
    }
  };

  return (
    <div className="lab-hospital-tests">
      <PageHeader
        title="Hospital Tests"
        description="Tests this hospital offers for New Lab Order. Add only existing tests from the master laboratory catalogue — do not type a new test name."
      />

      {message ? (
        <Alert tone="info" title="Hospital catalogue">
          <p>{message}</p>
        </Alert>
      ) : null}
      {notice ? (
        <Alert tone="success" title="Hospital tests">
          <p>{notice}</p>
        </Alert>
      ) : null}
      {error ? (
        <Alert tone="danger" title="Hospital tests">
          <p>{error}</p>
        </Alert>
      ) : null}

      {adding ? (
        <Card>
          <SectionHeader
            title="Add Hospital Test"
            description="Search the master laboratory catalogue, select the exact test or panel, then add it. It becomes available for ordering immediately."
          />
          <label className="lab-desk__search">
            <span>Search master catalogue</span>
            <input
              type="search"
              value={masterQuery}
              onChange={(event) => {
                setMasterQuery(event.target.value);
                setSelectedUuid("");
              }}
              placeholder="e.g. malaria, blood, liver"
              autoFocus
            />
          </label>
          {masterLoading ? <LoadingState variant="board" label="Searching master catalogue…" /> : null}
          {!masterLoading && masterQuery.trim().length >= 2 && masterHits.length === 0 ? (
            <EmptyState
              title="No matching master tests"
              description="That name is not in the master laboratory catalogue. A test must exist there before it can be offered by this hospital."
            />
          ) : null}
          {masterHits.length > 0 ? (
            <div className="abikan-table-wrap">
              <table className="abikan-table">
                <thead>
                  <tr>
                    <th>Test</th>
                    <th>Type</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {masterHits.map((row) => {
                    const selectedRow = selectedUuid === row.conceptUuid;
                    return (
                      <tr
                        key={row.conceptUuid}
                        className={
                          selectedRow ? "lab-hospital-tests__row--selected" : undefined
                        }
                      >
                        <td>
                          <button
                            type="button"
                            className="lab-desk__link"
                            onClick={() => setSelectedUuid(row.conceptUuid)}
                          >
                            {row.name}
                          </button>
                          {row.synonyms.length > 0 ? (
                            <div className="lab-hospital-tests__hint">
                              Also known as: {row.synonyms.slice(0, 3).join(", ")}
                            </div>
                          ) : null}
                        </td>
                        <td>{row.type}</td>
                        <td>
                          {row.alreadyEnabled ? (
                            <Badge tone="success">Already available</Badge>
                          ) : selectedRow ? (
                            <Badge tone="info">Selected</Badge>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
          <div className="lab-hospital-tests__actions">
            <Button
              disabled={!selected || Boolean(busyUuid) || Boolean(selected?.alreadyEnabled)}
              onClick={() => void addSelected()}
            >
              {busyUuid ? "Adding…" : selected?.alreadyEnabled ? "Already available" : "Add Test"}
            </Button>
            <Button
              variant="ghost"
              disabled={Boolean(busyUuid)}
              onClick={() => {
                setAdding(false);
                setMasterQuery("");
                setMasterHits([]);
                setSelectedUuid("");
                setError("");
              }}
            >
              Cancel
            </Button>
            <Button variant="ghost" onClick={() => openLaboratorySection("pricing")}>
              Open Tests & Prices
            </Button>
          </div>
        </Card>
      ) : (
        <Card>
          <SectionHeader
            title="Current Hospital Tests"
            description="These tests appear when staff create a New Lab Order."
            action={
              <Button onClick={() => setAdding(true)}>+ Add Test</Button>
            }
          />
          <label className="lab-desk__search">
            <span>Search hospital tests</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Test name"
            />
          </label>
          {loading ? (
            <LoadingState variant="board" label="Loading hospital tests…" />
          ) : visible.length === 0 ? (
            <EmptyState
              title={query.trim() ? "No matching hospital tests." : "No hospital tests yet."}
              description="Add an existing test from the master laboratory catalogue."
            />
          ) : (
            <div className="abikan-table-wrap">
              <table className="abikan-table">
                <thead>
                  <tr>
                    <th>Test</th>
                    <th>Type</th>
                    <th>Price</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => (
                    <tr key={row.conceptUuid || row.id}>
                      <td>
                        <strong>{row.name}</strong>
                        <div className="lab-hospital-tests__hint">{labCatalogueHitDetails(row)}</div>
                      </td>
                      <td>{isLabPanel(row) ? "Panel" : row.type || "Test"}</td>
                      <td>{row.price?.formatted || "Set in Tests & Prices"}</td>
                      <td>
                        <Badge tone="success">Enabled</Badge>
                      </td>
                      <td>
                        <Button
                          variant="ghost"
                          disabled={!row.conceptUuid || busyUuid === row.conceptUuid}
                          onClick={() => void removeTest(row)}
                        >
                          {busyUuid === row.conceptUuid ? "Removing…" : "Remove"}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
