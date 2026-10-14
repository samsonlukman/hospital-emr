import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  EXISTING_FAMILY_NO_FEE_COPY,
  FAMILY_CARD_ISSUED_COPY,
  NEW_FAMILY_FEE_COPY,
  cardTypeForMode,
  defaultHouseholdName,
  familySummary,
  shouldChargeNewFamilyCard,
} from "./hospitalFamilyView.ts";
import { parseShellHash } from "../../app/hashRoute.ts";
import { RECEPTION_NAV } from "../../config/receptionNav.ts";
import { shouldOfferCardFee, shouldShowCardFeeCard } from "./receptionVisit.ts";

describe("Family Card registration rules", () => {
  it("charges a Family Card only when a new family is created", () => {
    assert.equal(shouldChargeNewFamilyCard("new"), true);
    assert.equal(shouldChargeNewFamilyCard("existing"), false);
    assert.equal(shouldChargeNewFamilyCard("none"), false);
    assert.equal(cardTypeForMode("new"), "family");
    assert.equal(cardTypeForMode("existing"), "family");
    assert.equal(cardTypeForMode("none"), "individual");
  });

  it("names a new family from the first patient's last name", () => {
    assert.equal(defaultHouseholdName("Ibrahim"), "Ibrahim Family");
    assert.equal(defaultHouseholdName("  "), "");
  });

  it("summarizes a selected family for Reception", () => {
    assert.equal(
      familySummary({
        familyId: "fam-1",
        familyName: "Lukman Family",
        cardNumber: "FAM-001",
        memberCount: 4,
        feeStatus: "billed",
        feePatientUuid: "mr-lukman",
      }),
      "Lukman Family · FAM-001 · 4 members",
    );
  });

  it("does not offer a card fee when the family already has a Family Card", () => {
    const issued = {
      canCreateCharge: false,
      cardAlreadyRegistered: true,
      familyCardIssued: true,
      hasCharge: false,
    };
    assert.equal(shouldOfferCardFee(issued), false);
    assert.equal(shouldShowCardFeeCard(issued), false);
    assert.equal(FAMILY_CARD_ISSUED_COPY.includes("already has a Family Card"), true);
    assert.equal(EXISTING_FAMILY_NO_FEE_COPY.includes("No new Family Card fee"), true);
    assert.equal(NEW_FAMILY_FEE_COPY.includes("billed once"), true);
  });

  it("opens Families from Reception navigation and hashes", () => {
    const item = RECEPTION_NAV[0]?.items.find((entry) => entry.id === "families");
    assert.equal(item && "href" in item ? item.href : "", "#/reception/families");
    assert.equal(parseShellHash("#/reception/families").route, "registration-families");
    assert.equal(parseShellHash("#/reception/families").navItemId, "families");
    assert.equal(parseShellHash("#/reception/family/fam-1").route, "registration-family");
    assert.equal(parseShellHash("#/reception/register?family=fam-1").route, "registration-register");
  });
});
