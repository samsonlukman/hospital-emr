import { useEffect, useMemo, useState } from "react";
import { openPatientAccountInvoice, returnToPreviousScreen } from "../../app/hashRoute";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { ClinicalSection } from "../../components/ClinicalSection";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { KpiCard } from "../../components/KpiCard";
import { MoneyStack } from "../../components/MoneyStack";
import { SectionIndex } from "../../components/SectionIndex";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import {
  fetchPatientIdentity,
  fetchPatientVisits,
  fetchVisitByUuid,
} from "../../services/openmrs/clinicalPatient";
import { accountantReceiptHref } from "../../services/accountant";
import { canOpenAccountant, canOpenPharmacy } from "../../config/workspaceMap";
import { fetchPatientAccount } from "../../services/patientAccount";
import type { PatientIdentity, PatientVisitSummary, WorkspaceContext } from "../../types";
import type { PatientAccountActivity, PatientAccountPayload } from "../../types/patientAccount";
import { accountSummaryAmounts } from "../Accountant/accountantHonesty";
import { departmentDisplay, paymentStateTone, pharmacyStaffPaymentLabel, pharmacyStatusTone } from "./accountBadges";
import {
  PATIENT_ACCOUNT_SHOWS_LOCATION,
  bindPatientAccountVisit,
  patientAccountVisitLabel,
  selectedPatientAccountVisit,
} from "./patientAccountVisit";
import "./PatientAccountWorkspace.css";

interface PatientAccountWorkspaceProps {
  patientUuid: string;
  selectedVisitUuid?: string | null;
  context: WorkspaceContext;
}

export function PatientAccountWorkspace({
  patientUuid,
  selectedVisitUuid = null,
  context,
}: PatientAccountWorkspaceProps) {
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [visits, setVisits] = useState<PatientVisitSummary[]>([]);
  const [extraVisit, setExtraVisit] = useState<{
    visit: PatientVisitSummary;
    patientUuid: string;
  } | null | undefined>(undefined);
  const [account, setAccount] = useState<PatientAccountPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [department, setDepartment] = useState("All");
  const pharmacyAccount = canOpenPharmacy(context) && !canOpenAccountant(context);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDepartment("All");
    setVisits([]);
    setExtraVisit(undefined);
    Promise.allSettled([
      fetchPatientIdentity(patientUuid),
      fetchPatientVisits(patientUuid),
      fetchPatientAccount(patientUuid),
    ]).then(([identity, visitResult, accountResult]) => {
      if (cancelled) {
        return;
      }
      if (identity.status === "fulfilled") {
        setPatient(identity.value);
      }
      if (visitResult.status === "fulfilled") {
        setVisits(visitResult.value);
      }
      if (accountResult.status === "fulfilled") {
        setAccount(accountResult.value);
        if (identity.status !== "fulfilled" && accountResult.value.patient) {
          const fromAccount = accountResult.value.patient;
          setPatient({
            uuid: fromAccount.uuid,
            name: fromAccount.name,
            mrn: fromAccount.mrn,
            age: "—",
            sex: "—",
            birthdate: "",
          });
        }
      } else {
        setAccount(null);
        setError(
          accountResult.reason instanceof Error
            ? accountResult.reason.message
            : "Unable to load this patient's bills.",
        );
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [patientUuid]);

  const boundVisit = bindPatientAccountVisit({
    selectedVisitUuid,
    patientUuid,
    visits,
    extraVisit,
  });
  const selectedVisit = selectedPatientAccountVisit(boundVisit);

  useEffect(() => {
    if (!selectedVisitUuid) {
      setExtraVisit(undefined);
      return;
    }
    if (visits.some((visit) => visit.uuid === selectedVisitUuid)) {
      setExtraVisit(undefined);
      return;
    }
    if (loading) {
      return;
    }
    let cancelled = false;
    fetchVisitByUuid(selectedVisitUuid).then((result) => {
      if (!cancelled) {
        setExtraVisit(result);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [selectedVisitUuid, visits, loading]);
  const filters = useMemo(() => {
    const names = account?.departments ?? [];
    return names.length > 0 ? ["All", ...names] : [];
  }, [account]);
  const bills = useMemo(() => {
    const rows = account?.activity ?? [];
    if (department === "All") {
      return rows;
    }
    return rows.filter((row) => row.department === department);
  }, [account, department]);

  return (
    <div className="acct">
      <div className="acct__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen("#/home")}>
          ← Back
        </Button>
      </div>

      {patient ? (
        <PatientIdentityHeader
          compact
          patient={patient}
          visitLabel={patientAccountVisitLabel(selectedVisit)}
          locationName={
            PATIENT_ACCOUNT_SHOWS_LOCATION && !pharmacyAccount
              ? selectedVisit?.location
              : undefined
          }
        />
      ) : (
        <p className="acct__muted">Loading patient…</p>
      )}

      {loading ? <LoadingState variant="board" label="Loading bills…" /> : null}

      {!loading && error ? (
        <EmptyState title="Unable to load bills" description={error} />
      ) : null}

      {!loading && account?.status === "account_not_found" ? (
        <EmptyState
          title="No bills for this patient"
          description="This patient does not have a billing account yet."
        />
      ) : null}

      {!loading && account?.status === "no_activity" ? (
        <EmptyState title="No bills recorded." />
      ) : null}

      {!loading && account?.status === "ok" && account.summary ? (
        <div className="abikan-sheet">
        <div className="abikan-sheet__main">
          <section className="acct__kpis" aria-label="Account summary">
            <KpiCard
              label="Amount"
              value={<MoneyStack amounts={accountSummaryAmounts(account.summary, "billed")} />}
              hint="Billed so far"
              icon="receipt"
              tone="visits"
            />
            <KpiCard
              label="Paid"
              value={<MoneyStack amounts={accountSummaryAmounts(account.summary, "paid")} />}
              hint="Already received"
              icon="receipt"
              tone="teal"
            />
            <KpiCard
              label="Outstanding"
              value={<MoneyStack amounts={accountSummaryAmounts(account.summary, "outstanding")} />}
              hint="Still unpaid"
              icon="creditCard"
              tone="collection"
            />
          </section>

          {filters.length > 0 ? (
            <nav className="acct__filters" aria-label="Department filter">
              {filters.map((name) => (
                <button
                  key={name}
                  type="button"
                  className={name === department ? "is-active" : undefined}
                  onClick={() => setDepartment(name)}
                >
                  {name}
                </button>
              ))}
            </nav>
          ) : null}

          <ClinicalSection id="bills" title="Bills">
            {bills.length === 0 ? (
              <EmptyState title="No bills recorded." />
            ) : (
              <BillsTable rows={bills} patientUuid={patientUuid} hideInvoiceNumbers={pharmacyAccount} />
            )}
          </ClinicalSection>

          <ClinicalSection id="payments" title="Payments">
            {(account.payments ?? []).length === 0 ? (
              <EmptyState title="No payments recorded." />
            ) : (
              <div className="abikan-table-wrap">
                <table className="abikan-table">
                  <thead>
                    <tr>
                      {pharmacyAccount ? null : <th>Reference</th>}
                      <th>Date</th>
                      <th>Amount</th>
                      <th>Method</th>
                      <th>Accountant</th>
                      {pharmacyAccount ? null : <th>Related bill</th>}
                      {canOpenAccountant(context) ? <th>Receipt</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {(account.payments ?? []).map((payment) => (
                      <tr key={payment.id}>
                        {pharmacyAccount ? null : <td>{payment.reference || "—"}</td>}
                        <td>{payment.date || "—"}</td>
                        <td>{payment.amount.formatted}</td>
                        <td>
                          {[payment.journal, payment.method].filter(Boolean).join(" · ") || "—"}
                        </td>
                        <td>{payment.recordedBy || "—"}</td>
                        {pharmacyAccount ? null : (
                          <td>
                            {payment.allocationConfirmed
                              ? payment.relatedInvoices
                                  .map((item) => item.number)
                                  .filter(Boolean)
                                  .join(", ") || "—"
                              : "—"}
                          </td>
                        )}
                        {canOpenAccountant(context) ? (
                          <td>
                            <a href={accountantReceiptHref(payment.id)} target="_blank" rel="noreferrer">
                              Print receipt
                            </a>
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </ClinicalSection>

          {(account.pharmacy ?? []).length > 0 ? (
            <ClinicalSection id="pharmacy" title="Pharmacy">
              <div className="abikan-table-wrap">
                <table className="abikan-table">
                  <thead>
                    <tr>
                      {pharmacyAccount ? null : <th>Order</th>}
                      <th>Description</th>
                      {pharmacyAccount ? null : <th>Bill</th>}
                      <th>Payment</th>
                      <th>Dispensing</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(account.pharmacy ?? []).map((row) => (
                      <tr key={row.orderName}>
                        {pharmacyAccount ? null : <td>{row.orderName}</td>}
                        <td>{row.description}</td>
                        {pharmacyAccount ? null : (
                          <td>
                            {row.invoiceId ? (
                              <button
                                type="button"
                                className="acct__link"
                                onClick={() =>
                                  openPatientAccountInvoice(patientUuid, row.invoiceId as number)
                                }
                              >
                                {row.invoiceNumber}
                              </button>
                            ) : (
                              "—"
                            )}
                          </td>
                        )}
                        <td>
                          <Badge tone={paymentStateTone(row.paymentStateLabel)}>
                            {pharmacyAccount
                              ? pharmacyStaffPaymentLabel(row.paymentStateLabel)
                              : row.paymentStateLabel}
                          </Badge>
                        </td>
                        <td>
                          <Badge tone={pharmacyStatusTone(row.dispensingStatus)}>
                            {row.dispensingStatus}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </ClinicalSection>
          ) : null}
        </div>
        <SectionIndex
          label="Account sections"
          items={[
            { id: "bills", label: "Bills" },
            { id: "payments", label: "Payments" },
            ...((account.pharmacy ?? []).length > 0 ? [{ id: "pharmacy", label: "Pharmacy" }] : []),
          ]}
        />
        </div>
      ) : null}
    </div>
  );
}

function BillsTable({
  rows,
  patientUuid,
  hideInvoiceNumbers,
}: {
  rows: PatientAccountActivity[];
  patientUuid: string;
  hideInvoiceNumbers?: boolean;
}) {
  return (
    <div className="abikan-table-wrap">
      <table className="abikan-table">
        <thead>
          <tr>
            <th>Department</th>
            <th>Description</th>
            {hideInvoiceNumbers ? null : <th>Bill</th>}
            <th>Status</th>
            <th>Amount</th>
            <th>Amount due</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.kind}-${row.invoiceId ?? row.orderName ?? index}`}>
              <td>{departmentDisplay(row.department)}</td>
              <td>{row.description}</td>
              {hideInvoiceNumbers ? null : (
                <td>
                  {row.invoiceId ? (
                    <button
                      type="button"
                      className="acct__link"
                      onClick={() => openPatientAccountInvoice(patientUuid, row.invoiceId as number)}
                    >
                      {row.invoiceNumber}
                    </button>
                  ) : (
                    "—"
                  )}
                </td>
              )}
              <td>
                <Badge
                  tone={
                    row.pharmacyStatus
                      ? pharmacyStatusTone(row.pharmacyStatus)
                      : paymentStateTone(row.statusLabel)
                  }
                >
                  {hideInvoiceNumbers
                    ? pharmacyStaffPaymentLabel(row.statusLabel)
                    : row.pharmacyStatus || row.statusLabel}
                </Badge>
              </td>
              <td>{row.amount.formatted}</td>
              <td>{row.outstanding.formatted}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
