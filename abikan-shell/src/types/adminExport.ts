export type AdminExportFormat = "csv" | "xlsx" | "pdf" | "json";

export interface AdminExportOption {
  id: string;
  label: string;
}

export interface AdminExportDatasetOption extends AdminExportOption {
  kind: "clinical" | "financial" | "staff" | "analytics";
  usesDateRange: boolean;
  usesDepartment: boolean;
  departments: AdminExportOption[];
  statuses: AdminExportOption[];
  preferredFormats: AdminExportFormat[];
}

export interface AdminExportCatalog {
  status: "ok";
  datasets: AdminExportDatasetOption[];
  formats: AdminExportOption[];
  periods: AdminExportOption[];
  fileHours: number;
}

export interface AdminExportRecord {
  exportId: string;
  createdAt: string;
  adminUsername: string;
  adminDisplayName: string;
  dataset: string;
  datasetLabel: string;
  format: string;
  formatLabel: string;
  department: string;
  departmentLabel: string;
  statusFilter: string;
  statusLabel: string;
  period: string;
  periodLabel: string;
  startDate: string;
  endDate: string;
  recordCount: number;
  fileSize: number;
  filename: string;
  outcome: "success" | "failed";
  outcomeLabel: string;
  fileStatus: "available" | "expired" | "deleted" | "missing" | "none";
  fileStatusLabel: string;
  expiresAt: string;
  canDownload: boolean;
  canDelete: boolean;
  expired: boolean;
}

export interface AdminExportHistoryPayload {
  status: "ok";
  total: number;
  limit: number;
  offset: number;
  exports: AdminExportRecord[];
}

export interface AdminExportMutationPayload {
  status: "ok";
  export: AdminExportRecord;
}

export interface AdminExportRequest {
  dataset: string;
  format: AdminExportFormat;
  period: string;
  start?: string;
  end?: string;
  department?: string;
  status?: string;
}
