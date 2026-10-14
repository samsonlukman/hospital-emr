export const HOSPITAL_ADMIN_PRIVILEGE = "abikan:admin:staff";
export const HOSPITAL_ADMIN_ANALYTICS_PRIVILEGE = "abikan:admin:analytics";
export const HOSPITAL_ADMIN_AUDIT_READ_PRIVILEGE = "abikan:admin:audit-read";

export function isTechnicalSuperAdmin(roles: string[]): boolean {
  return roles.includes("SuperAdmin") || roles.includes("System Developer");
}

export function hasHospitalAdminAccess(roles: string[], privileges: string[]): boolean {
  return (
    isTechnicalSuperAdmin(roles) ||
    privileges.includes(HOSPITAL_ADMIN_PRIVILEGE)
  );
}

export function hasAdminAnalyticsAccess(roles: string[], privileges: string[]): boolean {
  return (
    isTechnicalSuperAdmin(roles) ||
    (hasHospitalAdminAccess(roles, privileges) &&
      privileges.includes(HOSPITAL_ADMIN_ANALYTICS_PRIVILEGE))
  );
}

export function hasAdminAuditReadAccess(roles: string[], privileges: string[]): boolean {
  return (
    isTechnicalSuperAdmin(roles) ||
    (hasHospitalAdminAccess(roles, privileges) &&
      privileges.includes(HOSPITAL_ADMIN_AUDIT_READ_PRIVILEGE))
  );
}
