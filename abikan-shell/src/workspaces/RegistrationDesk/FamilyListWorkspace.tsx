import { useEffect, useState } from "react";
import { openReceptionFamily, openRegistrationRegister, returnToPreviousScreen } from "../../app/hashRoute";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { TableSkeleton } from "../../components/TableSkeleton";
import { searchHospitalFamilies } from "../../services/hospitalFamily";
import { RegistrationRequestError } from "../../services/registration";
import type { HospitalFamily } from "../../types/hospitalFamily";
import "../Admin/AdminWorkspace.css";
import "../PatientDirectory/PatientDirectoryWorkspace.css";
import "./RegistrationDeskWorkspace.css";

const HEADERS = ["Family", "Family Card", "Members", "Action"];

function errorMessage(reason: unknown): string {
  return reason instanceof RegistrationRequestError || reason instanceof Error
    ? reason.message
    : "Families could not be loaded.";
}

export function FamilyListWorkspace() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [families, setFamilies] = useState<HospitalFamily[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    searchHospitalFamilies(submittedQuery)
      .then((payload) => {
        if (!cancelled) {
          setFamilies(payload.families || []);
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setFamilies([]);
          setError(errorMessage(reason));
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
  }, [submittedQuery]);

  return (
    <div className="admin-workspace patient-directory">
      <div className="admin-workspace__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/reception")}>
          ← Reception
        </Button>
      </div>
      <PageHeader
        title="Families"
        description="A Family Card belongs to the family, not to one person. Open a family to see every patient who shares that card."
      />

      {error ? (
        <Alert tone="danger" title="Families could not be loaded">
          {error}
        </Alert>
      ) : null}

      <form
        className="admin-workspace__filters patient-directory__filters"
        aria-label="Find families"
        onSubmit={(event) => {
          event.preventDefault();
          setSubmittedQuery(query.trim());
        }}
      >
        <label className="admin-workspace__search">
          <span>Find family</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Family name, card number, or family member"
          />
        </label>
        <div className="patient-directory__find">
          <Button type="submit">Find</Button>
        </div>
      </form>

      {loading ? <TableSkeleton label="Loading families…" headers={HEADERS} /> : null}

      {!loading && !error && families.length === 0 ? (
        <EmptyState
          title={submittedQuery ? "No family matches this search." : "No families have a Family Card yet."}
          description={
            submittedQuery
              ? "Try another family name, card number, or member name."
              : "Create a new family when you register the first patient."
          }
        />
      ) : null}

      {!loading && families.length > 0 ? (
        <div className="abikan-table-wrap admin-workspace__table">
          <table className="abikan-table">
            <thead>
              <tr>
                {HEADERS.map((header) => (
                  <th key={header}>{header === "Action" ? "" : header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {families.map((family) => (
                <tr key={family.familyId}>
                  <td>
                    <button
                      type="button"
                      className="patient-directory__name"
                      onClick={() => openReceptionFamily(family.familyId)}
                    >
                      {family.familyName}
                    </button>
                  </td>
                  <td>{family.cardNumber}</td>
                  <td>{family.memberCount === 1 ? "1 patient" : `${family.memberCount} patients`}</td>
                  <td>
                    <Button variant="secondary" onClick={() => openReceptionFamily(family.familyId)}>
                      Open
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="reg-patient__actions">
        <Button onClick={() => openRegistrationRegister()}>Register a new family</Button>
      </div>
    </div>
  );
}
