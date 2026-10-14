import { REGISTRATION_CARDS } from "../config/registrationCharges";
import { formatNaira } from "../utils/naira";
import "./CollectionSummary.css";

export interface CollectionBreakdown {
  total: number;
  individualCount: number;
  familyCount: number;
  other: number;
}

interface CollectionSummaryProps {
  collection: CollectionBreakdown;
}

export function CollectionSummary({ collection }: CollectionSummaryProps) {
  const individualTotal =
    collection.individualCount * REGISTRATION_CARDS.individual.amountNaira;
  const familyTotal = collection.familyCount * REGISTRATION_CARDS.family.amountNaira;

  return (
    <ul className="abikan-collection">
      <li>
        <span className="abikan-collection__dot is-registration" />
        <div>
          <strong>Individual Cards</strong>
          <em>({formatNaira(REGISTRATION_CARDS.individual.amountNaira)})</em>
        </div>
        <span className="abikan-collection__count">{collection.individualCount}</span>
        <span className="abikan-collection__amount">{formatNaira(individualTotal)}</span>
      </li>
      <li>
        <span className="abikan-collection__dot is-appointments" />
        <div>
          <strong>Family Cards</strong>
          <em>({formatNaira(REGISTRATION_CARDS.family.amountNaira)})</em>
        </div>
        <span className="abikan-collection__count">{collection.familyCount}</span>
        <span className="abikan-collection__amount">{formatNaira(familyTotal)}</span>
      </li>
      <li>
        <span className="abikan-collection__dot is-visits" />
        <div>
          <strong>Other Reception Payments</strong>
        </div>
        <span className="abikan-collection__amount">{formatNaira(collection.other)}</span>
      </li>
      <li className="abikan-collection__total">
        <div>
          <strong>Total Collection</strong>
        </div>
        <span className="abikan-collection__amount">{formatNaira(collection.total)}</span>
      </li>
    </ul>
  );
}
