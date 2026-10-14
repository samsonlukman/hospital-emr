import type { PatientAccountMoney } from "../types/patientAccount";
import "./MoneyStack.css";

export function MoneyStack({ amounts }: { amounts: PatientAccountMoney[] | undefined }) {
  if (!amounts?.length) {
    return <>—</>;
  }
  if (amounts.length === 1) {
    return <>{amounts[0].formatted}</>;
  }
  return (
    <span className="abikan-money-stack">
      {amounts.map((item) => (
        <span key={item.currencyCode || item.formatted}>{item.formatted}</span>
      ))}
    </span>
  );
}
