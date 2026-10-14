export type AdminDepartmentId =
  | "clinical"
  | "nursing"
  | "reception"
  | "laboratory"
  | "radiology"
  | "pharmacy"
  | "accountant";

export type AdminAccountType = "staff" | "hospital_administrator";

export type StaffCategoryId =
  | AdminDepartmentId
  | "hospital_admin"
  | "security"
  | "attendant";

export type StaffEmploymentType = "permanent" | "external";

export type StaffEmrAccess = "account" | "none";

export interface StaffCategory {
  id: StaffCategoryId;
  label: string;
  roleLabel: string;
  emrAccess: StaffEmrAccess;
  requiresEmploymentType: boolean;
  requiresLogin: boolean;
}

export interface StaffHrProfile {
  address: string;
  phone: string;
  nin: string;
  bankAccountNumber: string;
  bankName: string;
  accountName: string;
  qualification: string;
}

export interface AdminDepartment {
  id: AdminDepartmentId;
  label: string;
  roleLabel: string;
  providerRequired: boolean;
}

export interface StaffDepartment {
  id: AdminDepartmentId;
  label: string;
  roleLabel: string;
}

export interface StaffAccount {
  userUuid: string;
  username: string;
  displayName: string;
  enabled: boolean;
  accountType?: AdminAccountType;
  personUuid?: string;
  staffId?: string;
  staffCategory?: StaffCategoryId | string;
  staffCategoryLabel?: string;
  employmentType?: StaffEmploymentType | string | null;
  employmentTypeLabel?: string;
  emrAccess?: StaffEmrAccess;
  emrAccessLabel?: string;
  departments: StaffDepartment[];
  preferredDepartment: Pick<AdminDepartment, "id" | "label"> | null;
  providerStatus: "ready" | "missing" | "not_required";
  providerRequired: boolean;
  hasProfilePicture?: boolean;
  hasAppointmentLetter?: boolean;
  profilePictureHref?: string;
  hr?: StaffHrProfile;
}

export interface StaffDirectoryCapabilities {
  canCreateHospitalAdministrator: boolean;
}

export interface StaffDirectoryPayload {
  status: "ok";
  staff: StaffAccount[];
  departments: AdminDepartment[];
  staffCategories?: StaffCategory[];
  capabilities?: StaffDirectoryCapabilities;
}

export interface DepartmentAccessRow {
  userUuid: string;
  displayName: string;
  username: string;
  enabled: boolean;
  department: StaffDepartment;
}

export interface DepartmentAccessPayload {
  status: "ok";
  access: DepartmentAccessRow[];
  departments: AdminDepartment[];
}

export interface CreateStaffRequest {
  fullName: string;
  username: string;
  initialPassword: string;
  accountType?: AdminAccountType;
  staffCategory?: StaffCategoryId | string;
  employmentType?: StaffEmploymentType | "";
  departments: AdminDepartmentId[];
  enabled: boolean;
  requestId: string;
  address?: string;
  phone?: string;
  nin?: string;
  bankAccountNumber?: string;
  bankName?: string;
  accountName?: string;
  qualification?: string;
}

export interface AdminMutationPayload {
  status: "ok" | "partial";
  message: string;
  staff?: StaffAccount;
  enabled?: boolean;
}

export type AdminPeriodId =
  | "today"
  | "yesterday"
  | "this_week"
  | "last_week"
  | "this_month"
  | "last_month"
  | "custom";

export interface AdminMetric {
  status: "ok" | "unavailable";
  value: number | null;
  message?: string;
  occupied?: number | null;
  total?: number | null;
  available?: number | null;
  rate?: number | null;
  asOf?: "current";
  label?: string;
  amount?: number;
  formatted?: string;
  currencyCode?: string;
  currencySymbol?: string;
  movements?: number | null;
}

export interface AdminAnalyticsPeriod {
  period: AdminPeriodId;
  label: string;
  timezone: string;
  startDate: string;
  endDate: string;
  weekStartsOn?: string;
}

export interface AdminAnalyticsOverview {
  status: "ok";
  period: AdminAnalyticsPeriod;
  patientsRegistered: AdminMetric;
  opdVisits: AdminMetric;
  consultations: AdminMetric;
  admissions: AdminMetric;
  discharges: AdminMetric;
  occupancy: AdminMetric;
  labOrders: AdminMetric;
  prescriptions: AdminMetric;
  dispensed: AdminMetric;
  billed: AdminMetric;
  collected: AdminMetric;
  outstanding: AdminMetric;
  revenueByDepartment?: {
    status: "ok" | "unavailable";
    message?: string;
    departments: Array<AdminMetric & { department: string; share?: number }>;
    total?: AdminMetric;
  };
}

export interface AdminStaffAuditEvent {
  eventId: string;
  occurredAt: string;
  actorUsername: string;
  targetUsername: string;
  action: string;
  actionLabel: string;
  outcome: string;
  errorCode: string;
  requestId: string;
  previous: {
    enabled?: boolean;
    departments?: string[];
    accountType?: string;
    alive?: boolean;
    deathDate?: string;
  };
  current: {
    enabled?: boolean;
    departments?: string[];
    accountType?: string;
    alive?: boolean;
    deathDate?: string;
  };
}

export interface AdminStaffAuditPayload {
  status: "ok";
  total: number;
  limit: number;
  offset: number;
  events: AdminStaffAuditEvent[];
}
