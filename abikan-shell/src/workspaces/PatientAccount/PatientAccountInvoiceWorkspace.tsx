import { useEffect, useState } from "react";
import { patientAccountHref, returnToPreviousScreen } from "../../app/hashRoute";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { ClinicalSection } from "../../components/ClinicalSection";
import { EmptyState } from "../../components/EmptyState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { PatientIdentityHeader } from "../../components/PatientIdentityHeader";
import { SectionHeader } from "../../components/SectionHeader";
import { fetchPatientIdentity } from "../../services/openmrs/clinicalPatient";
import { fetchPatientAccountInvoice } from "../../services/patientAccount";
import type { PatientIdentity, WorkspaceContext } from "../../types";
import type { PatientAccountInvoicePayload } from "../../types/patientAccount";
import { canOpenAccountant, canOpenPharmacy } from "../../config/workspaceMap";
import { departmentDisplay, paymentStateTone, pharmacyStaffPaymentLabel, pharmacyStatusTone } from "./accountBadges";
import "./PatientAccountWorkspace.css";

interface PatientAccountInvoiceWorkspaceProps {
  patientUuid: string;
  invoiceId: string;
  context: WorkspaceContext;
}

export function PatientAccountInvoiceWorkspace({
  patientUuid,
  invoiceId,
  context,
}: PatientAccountInvoiceWorkspaceProps) {
  const [patient, setPatient] = useState<PatientIdentity | null>(null);
  const [payload, setPayload] = useState<PatientAccountInvoicePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.allSettled([
      fetchPatientIdentity(patientUuid),
      fetchPatientAccountInvoice(patientUuid, invoiceId),
    ]).then(([identity, invoiceResult]) => {
      if (cancelled) {
        return;
      }
      if (identity.status === "fulfilled") {
        setPatient(identity.value);
      }
      if (invoiceResult.status === "fulfilled") {
        setPayload(invoiceResult.value);
      } else {
        setPayload(null);
        setError(
          invoiceResult.reason instanceof Error
            ? invoiceResult.reason.message
            : "Unable to load this invoice.",
        );
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [patientUuid, invoiceId]);

  const invoice = payload?.invoice;
  const pharmacyAccount = canOpenPharmacy(context) && !canOpenAccountant(context);

  return (
    <div className="acct">
      <div className="acct__nav">
        <Button variant="ghost" onClick={() => returnToPreviousScreen(patientAccountHref(patientUuid))}>
          ← Patient Account
        </Button>
      </div>

      <PageHeader
        title={invoice?.number || "Bill"}
        description="Bill details. Payment is collected at the cashier desk."
      />

      {patient ? (
        <PatientIdentityHeader patient={patient} />
      ) : (
        <p className="acct__muted">Loading patient…</p>
      )}

      {loading ? <LoadingState variant="board" label="Loading invoice…" /> : null}
      {!loading && error ? <EmptyState title="Bill unavailable" description={error} /> : null}
      {!loading && payload?.status === "account_not_found" ? (
        <EmptyState title="No bills for this patient." />
      ) : null}

      {!loading && invoice ? (
        <>
          <Card>
            <SectionHeader title="Bill summary" />
            <dl className="acct__facts">
              <div>
                <dt>Bill</dt>
                <dd>{invoice.number}</dd>
              </div>
              <div>
                <dt>Date</dt>
                <dd>{invoice.date || "—"}</dd>
              </div>
              <div>
                <dt>Department</dt>
                <dd>{departmentDisplay(invoice.department)}</dd>
              </div>
              <div>
                <dt>Payment state</dt>
                <dd>
                  <Badge tone={paymentStateTone(invoice.paymentStateLabel)}>
                    {pharmacyAccount
                      ? pharmacyStaffPaymentLabel(invoice.paymentStateLabel)
                      : invoice.paymentStateLabel}
                  </Badge>
                  {invoice.waivedBy ? <div>{invoice.waivedBy}</div> : null}
                  {invoice.createdBy ? <div>Created by {invoice.createdBy}</div> : null}
                </dd>
              </div>
              {invoice.pharmacyStatus ? (
                <div>
                  <dt>Pharmacy</dt>
                  <dd>
                    <Badge tone={pharmacyStatusTone(invoice.pharmacyStatus)}>
                      {invoice.pharmacyStatus}
                    </Badge>
                  </dd>
                </div>
              ) : null}
              <div>
                <dt>Total</dt>
                <dd>{invoice.total.formatted}</dd>
              </div>
              <div>
                <dt>Paid</dt>
                <dd>{invoice.paid.formatted}</dd>
              </div>
              <div>
                <dt>Outstanding</dt>
                <dd>{invoice.outstanding.formatted}</dd>
              </div>
            </dl>
            {invoice.hasTax ? (
              <dl className="acct__facts acct__facts--tax">
                <div>
                  <dt>Subtotal</dt>
                  <dd>{invoice.untaxed.formatted}</dd>
                </div>
                <div>
                  <dt>Tax</dt>
                  <dd>{invoice.tax.formatted}</dd>
                </div>
                <div>
                  <dt>Total</dt>
                  <dd>{invoice.total.formatted}</dd>
                </div>
              </dl>
            ) : null}
          </Card>

          <ClinicalSection
            id="lines"
            title="Line items"
          >
            {invoice.lines.length === 0 ? (
              <EmptyState title="No invoice lines returned." />
            ) : (
              <div className="abikan-table-wrap">
                <table className="abikan-table">
                  <thead>
                    <tr>
                      <th>Description</th>
                      <th>Quantity</th>
                      <th>Unit price</th>
                      {invoice.lines.some((line) => (line.discountPercent || 0) > 0) ? (
                        <th>Discount</th>
                      ) : null}
                      <th>Taxes</th>
                      <th>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoice.lines.map((line, index) => {
                      const showDiscount = invoice.lines.some((item) => (item.discountPercent || 0) > 0);
                      const discount = line.discountPercent || 0;
                      const discountLabel =
                        discount > 0 ? `${discount % 1 === 0 ? discount.toFixed(0) : discount}%` : "—";
                      return (
                      <tr key={`${line.description}-${index}`}>
                        <td>{line.description}</td>
                        <td>{line.quantity}</td>
                        <td>{line.unitPrice.formatted}</td>
                        {showDiscount ? <td>{discountLabel}</td> : null}
                        <td>{line.taxNames.join(", ") || "—"}</td>
                        <td>{line.total.formatted}</td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </ClinicalSection>

        </>
      ) : null}
    </div>
  );
}
