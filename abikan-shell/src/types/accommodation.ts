import type { PatientAccountMoney } from "./patientAccount";

export interface AccommodationTariff {
  areaUuid: string;
  areaName: string;
  beds: number;
  priceKind: "bed" | "room" | string;
  priceKindLabel: string;
  listPrice: PatientAccountMoney;
  configured: boolean;
}

export interface AccommodationTariffPayload {
  status: string;
  currency?: {
    code?: string;
    symbol?: string;
    decimalPlaces?: number;
  };
  areas: AccommodationTariff[];
  canEdit?: boolean;
  message?: string | null;
  savedAreaUuid?: string;
}
