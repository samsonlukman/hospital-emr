import type { RegistrationCardType } from "../types";

export const REGISTRATION_CARDS: Record<
  RegistrationCardType,
  { id: RegistrationCardType; label: string; amountNaira: number }
> = {
  individual: {
    id: "individual",
    label: "Individual Card",
    amountNaira: 2000,
  },
  family: {
    id: "family",
    label: "Family Card",
    amountNaira: 5000,
  },
};

export const CARD_TYPE_STORAGE_KEY = "abikan.registration.cardType";

export function rememberCardType(cardType: RegistrationCardType): void {
  sessionStorage.setItem(CARD_TYPE_STORAGE_KEY, cardType);
}
