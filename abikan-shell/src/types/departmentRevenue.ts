import type { AdminMetric, AdminAnalyticsPeriod } from "./administration";

export interface DepartmentRevenueRow extends AdminMetric {
  department: string;
  share: number;
}

export interface DepartmentRevenuePayload {
  status: "ok";
  period: AdminAnalyticsPeriod;
  scope: "hospital" | "department";
  departmentsAllowed: string[];
  revenue: AdminMetric;
  departments: DepartmentRevenueRow[];
}
