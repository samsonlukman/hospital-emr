export interface PatientDirectoryRow {
  uuid: string;
  name: string;
  hospitalNumber: string;
  sex: string;
  age: string;
  phone: string;
  cardType: string;
  registeredOn: string;
  alive: "Yes" | "No";
  deathDate?: string;
  nhis?: boolean;
}

export interface PatientDirectoryPayload {
  status: "ok";
  q: string;
  lifeStatus?: PatientLifeStatusFilter;
  limit: number;
  startIndex: number;
  total: number;
  hasMore: boolean;
  patients: PatientDirectoryRow[];
}

export type PatientDirectoryPageSize = 50 | 100;
export type PatientLifeStatusFilter = "all" | "alive" | "deceased";

export interface PatientRecord {
  status: "ok";
  uuid: string;
  identifier: string;
  givenName: string;
  middleName: string;
  familyName: string;
  gender: string;
  birthdate: string;
  birthdateEstimated: boolean;
  age?: number | null;
  attributes: Record<string, string>;
  address: Record<string, string>;
  identifiers: Array<{ identifier: string; preferred: boolean; type: string }>;
  registeredOn?: string;
  alive: boolean;
  deathDate?: string;
  nhis?: boolean;
}
