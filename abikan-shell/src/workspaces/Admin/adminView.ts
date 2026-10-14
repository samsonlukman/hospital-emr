import type {
  AdminAccountType,
  AdminDepartmentId,
  DepartmentAccessRow,
  StaffAccount,
  StaffCategoryId,
  StaffEmploymentType,
  StaffHrProfile,
} from "../../types/administration";

export type StaffStatusFilter = "all" | "active" | "disabled";
export type StaffEmploymentFilter = "all" | "permanent" | "external" | "na";
export type StaffCategoryFilter = "all" | StaffCategoryId | AdminDepartmentId;

export const NON_LOGIN_CATEGORIES: StaffCategoryId[] = ["security", "attendant"];

export function staffKey(staff: Pick<StaffAccount, "personUuid" | "staffId" | "userUuid">): string {
  return staff.personUuid || staff.staffId || staff.userUuid;
}

export function selectedAccessStaff(
  staff: StaffAccount[],
  selectedUuid: string,
): StaffAccount | null {
  if (!selectedUuid) {
    return null;
  }
  return staff.find((item) => item.userUuid === selectedUuid) ?? null;
}

export function matchesStaffSearch(
  staff: Pick<StaffAccount, "displayName" | "username">,
  query: string,
): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return `${staff.displayName} ${staff.username || ""}`.toLowerCase().includes(needle);
}

export function staffCategoryOf(staff: StaffAccount): string {
  if (staff.staffCategory) {
    return staff.staffCategory;
  }
  if (staff.accountType === "hospital_administrator") {
    return "hospital_admin";
  }
  return staff.departments[0]?.id || "";
}

export function hasDepartment(
  staff: StaffAccount,
  department: StaffCategoryFilter,
): boolean {
  if (department === "all") {
    return true;
  }
  if (staffCategoryOf(staff) === department) {
    return true;
  }
  return staff.departments.some((item) => item.id === department);
}

export function matchesStatus(staff: StaffAccount, status: StaffStatusFilter): boolean {
  return status === "all" || (staff.enabled ? status === "active" : status === "disabled");
}

export function matchesEmployment(staff: StaffAccount, employment: StaffEmploymentFilter): boolean {
  if (employment === "all") {
    return true;
  }
  if (employment === "na") {
    return !staff.employmentType;
  }
  return staff.employmentType === employment;
}

export function filterStaff(
  rows: StaffAccount[],
  query: string,
  department: StaffCategoryFilter,
  status: StaffStatusFilter,
  employment: StaffEmploymentFilter = "all",
): StaffAccount[] {
  return rows.filter(
    (row) =>
      matchesStaffSearch(row, query) &&
      hasDepartment(row, department) &&
      matchesStatus(row, status) &&
      matchesEmployment(row, employment),
  );
}

export function filterAccess(
  rows: DepartmentAccessRow[],
  query: string,
  department: "all" | AdminDepartmentId,
  status: StaffStatusFilter,
): DepartmentAccessRow[] {
  return rows.filter((row) => {
    const searchMatches = matchesStaffSearch(row, query);
    const departmentMatches = department === "all" || row.department.id === department;
    const statusMatches =
      status === "all" || (status === "active" ? row.enabled : !row.enabled);
    return searchMatches && departmentMatches && statusMatches;
  });
}

export function providerStatusLabel(staff: StaffAccount): string {
  if (staff.providerStatus === "missing") {
    return "Clinical profile needed";
  }
  if (staff.providerStatus === "ready") {
    return "Ready";
  }
  return "Not required";
}

export function isNonLoginCategory(category: string | undefined): boolean {
  return Boolean(category && NON_LOGIN_CATEGORIES.includes(category as StaffCategoryId));
}

export function emrAccessLabel(staff: StaffAccount): string {
  if (staff.emrAccessLabel) {
    return staff.emrAccessLabel;
  }
  if (staff.emrAccess === "none" || isNonLoginCategory(staffCategoryOf(staff)) || !staff.userUuid) {
    return "No account";
  }
  return "Has account";
}

export function employmentTypeLabel(staff: StaffAccount): string {
  if (staff.employmentTypeLabel) {
    return staff.employmentTypeLabel;
  }
  if (staff.employmentType === "permanent") {
    return "Permanent";
  }
  if (staff.employmentType === "external") {
    return "External / Sourced";
  }
  return "—";
}

export interface StaffDraft {
  fullName: string;
  username: string;
  initialPassword: string;
  accountType?: AdminAccountType;
  staffCategory: StaffCategoryId | "";
  employmentType: StaffEmploymentType | "";
  departments: AdminDepartmentId[];
  address: string;
  phone: string;
  nin: string;
  bankAccountNumber: string;
  bankName: string;
  accountName: string;
  qualification: string;
}

export function emptyHr(): StaffHrProfile {
  return {
    address: "",
    phone: "",
    nin: "",
    bankAccountNumber: "",
    bankName: "",
    accountName: "",
    qualification: "",
  };
}

export function validateStaffDraft(draft: {
  fullName: string;
  username: string;
  initialPassword: string;
  accountType?: AdminAccountType;
  staffCategory?: string;
  employmentType?: string;
  departments: AdminDepartmentId[];
}): string {
  if (draft.fullName.trim().split(/\s+/).length < 2) {
    return "Enter the staff member's full name.";
  }
  const accountType = draft.accountType ?? "staff";
  if (accountType === "hospital_administrator") {
    if (!/^[a-z0-9][a-z0-9._-]{2,49}$/.test(draft.username.trim())) {
      return "Use 3–50 lowercase letters, numbers, dots, dashes, or underscores for the username.";
    }
    return initialPasswordProblem(draft.initialPassword, draft.username);
  }
  if (isNonLoginCategory(draft.staffCategory)) {
    return "";
  }
  if (draft.staffCategory === "clinical" && !draft.employmentType) {
    return "Choose Permanent or External / Sourced.";
  }
  if (!/^[a-z0-9][a-z0-9._-]{2,49}$/.test(draft.username.trim())) {
    return "Use 3–50 lowercase letters, numbers, dots, dashes, or underscores for the username.";
  }
  const passwordProblem = initialPasswordProblem(draft.initialPassword, draft.username);
  if (passwordProblem) {
    return passwordProblem;
  }
  if (accountType === "staff" && !draft.departments.length && !draft.staffCategory) {
    return "Choose at least one department.";
  }
  return "";
}

export function initialPasswordProblem(password: string, username = ""): string {
  const problem = signInPasswordProblem(password, username);
  return problem.replace(/sign-in password/g, "initial sign-in password");
}

export function signInPasswordProblem(password: string, username = ""): string {
  if (password.length < 8) {
    return "The sign-in password must be at least 8 characters.";
  }
  if (!/[A-Z]/.test(password) || !/[a-z]/.test(password)) {
    return "The sign-in password must include both uppercase and lowercase letters.";
  }
  if (!/[0-9]/.test(password)) {
    return "The sign-in password must include at least one number.";
  }
  if (username.trim() && password.toLowerCase() === username.trim().toLowerCase()) {
    return "The sign-in password cannot match the username.";
  }
  return "";
}

export function staffDepartmentLabel(staff: StaffAccount): string {
  if (staff.staffCategoryLabel) {
    return staff.staffCategoryLabel;
  }
  if (staff.accountType === "hospital_administrator") {
    return "Administration";
  }
  if (isNonLoginCategory(staff.staffCategory)) {
    return staff.staffCategory === "security" ? "Security" : "Attendant";
  }
  return staff.departments.map((item) => item.label).join(", ") || "—";
}

export function staffRoleLabel(staff: StaffAccount): string {
  if (staff.accountType === "hospital_administrator") {
    return "Hospital Administrator";
  }
  if (staff.staffCategory === "security") {
    return "Security";
  }
  if (staff.staffCategory === "attendant") {
    return "Attendant";
  }
  return staff.departments.map((item) => item.roleLabel).join(", ") || staffDepartmentLabel(staff);
}

export function showsHrFields(category: string | undefined, employmentType: string | undefined): boolean {
  if (!category) {
    return false;
  }
  if (category === "clinical") {
    return employmentType === "permanent";
  }
  return true;
}

export function showsLoginFields(category: string | undefined, accountType?: AdminAccountType): boolean {
  if (accountType === "hospital_administrator") {
    return true;
  }
  return !isNonLoginCategory(category);
}
