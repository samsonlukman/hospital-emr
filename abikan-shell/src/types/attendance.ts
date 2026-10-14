export type AttendanceStatus = "NOT_SIGNED_IN" | "SIGNED_IN" | "SIGNED_OUT";
export type AttendanceAvailableAction = "SIGN_IN" | "SIGN_OUT" | "";

export interface AttendanceStaffCard {
  personUuid: string;
  userUuid: string;
  username: string;
  displayName: string;
  workplaceId: string;
  workplaceLabel: string;
}

export interface AttendanceSession {
  id: string;
  personUuid: string;
  userUuid: string;
  username: string;
  displayName: string;
  workplaceId: string;
  workplaceLabel: string;
  localDate: string;
  status: AttendanceStatus;
  statusLabel: string;
  signInAt: string;
  signInLocalTime: string;
  signOutAt: string;
  signOutLocalTime: string;
  authenticationMethod: string;
  terminalName: string;
  createdAt: string;
  createdBy: string;
  hasPhoto: boolean;
  photoHref?: string;
}

export interface AttendanceTerminalConfig {
  status: "ok";
  title: string;
  prompt: string;
  timezone: string;
  localDate: string;
  localTime: string;
  displayDate: string;
  greeting: string;
  terminalName: string;
  developmentTerminalKey?: string;
}

export interface AttendanceLookupPayload {
  status: "ok";
  attendanceStatus: AttendanceStatus;
  statusLabel: string;
  availableAction: AttendanceAvailableAction;
  message: string;
  staff: AttendanceStaffCard;
  session: AttendanceSession | null;
  displayDate: string;
  timezone: string;
}

export interface AttendanceActionPayload {
  status: "ok";
  message: string;
  alreadyRecorded: boolean;
  attendanceStatus: AttendanceStatus;
  staff: AttendanceStaffCard;
  session: AttendanceSession;
  displayDate: string;
  timezone: string;
}

export interface AttendanceLogPayload {
  status: "ok";
  date: string;
  displayDate: string;
  today: string;
  previousDate: string;
  nextDate: string;
  timezone: string;
  total: number;
  limit: number;
  offset: number;
  sessions: AttendanceSession[];
  departments: Array<{ id: string; label: string }>;
  statuses: Array<{ id: AttendanceStatus; label: string }>;
  serverTime: string;
}

export interface StaffAttendanceCodeAudit {
  id: string;
  occurredAt: string;
  action: string;
  actionLabel: string;
  actorUsername: string;
}

export interface StaffAttendanceCodePayload {
  status: "ok";
  message?: string;
  staff: AttendanceStaffCard;
  attendanceCode: {
    hasCode: boolean;
    code: string;
    createdAt: string;
    createdBy: string;
    replacedAt: string;
    replacedBy: string;
    audit: StaffAttendanceCodeAudit[];
  };
}
