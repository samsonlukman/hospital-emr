import type { HospitalFamily } from "../../types/hospitalFamily";
import type { FamilyRegistrationMode } from "../../types/hospitalFamily";

export const FAMILY_RELATIONSHIPS = [
  "Self",
  "Spouse",
  "Child",
  "Parent",
  "Sibling",
  "Family member",
  "Other",
] as const;

export const EXISTING_FAMILY_NO_FEE_COPY =
  "This patient will share the selected Family Card. No new Family Card fee is created.";

export const NEW_FAMILY_FEE_COPY =
  "A new Family Card will be created. The Family Card fee is billed once.";

export const INDIVIDUAL_CARD_COPY =
  "This patient gets their own hospital card. The card fee is billed when the card is created.";

export const FAMILY_CARD_ISSUED_COPY =
  "This family already has a Family Card. No new card fee is created.";

export function defaultHouseholdName(lastName: string): string {
  const last = lastName.trim();
  return last ? `${last} Family` : "";
}

export function familySummary(family: HospitalFamily | null | undefined): string {
  if (!family) {
    return "";
  }
  const members = family.memberCount === 1 ? "1 member" : `${family.memberCount} members`;
  return `${family.familyName} · ${family.cardNumber} · ${members}`;
}

export function registrationModeFromCard(
  cardType: "individual" | "family",
  hasFamilyId: boolean,
): FamilyRegistrationMode {
  if (hasFamilyId) {
    return "existing";
  }
  return cardType === "family" ? "new" : "none";
}

export function cardTypeForMode(mode: FamilyRegistrationMode): "individual" | "family" {
  return mode === "none" ? "individual" : "family";
}

export function shouldChargeNewFamilyCard(mode: FamilyRegistrationMode): boolean {
  return mode === "new";
}
