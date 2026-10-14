import type { ReceptionAppointment } from "../../types";
import { formatClock, todayDateString, tomorrowDateString } from "../../utils/datetime";
import { openmrsGet } from "./client";

interface AppointmentPatient {
  uuid?: string;
  name?: string;
  identifier?: string;
}

interface AppointmentProvider {
  name?: string;
}

interface AppointmentRecord {
  uuid: string;
  startDateTime?: number | string;
  status?: string;
  patient?: AppointmentPatient;
  service?: {
    name?: string;
    speciality?: { name?: string };
  };
  providers?: AppointmentProvider[];
  provider?: { name?: string };
}

export async function fetchTodaysAppointments(): Promise<ReceptionAppointment[]> {
  const query = new URLSearchParams({
    startDate: todayDateString(),
    endDate: tomorrowDateString(),
  });
  const records = await openmrsGet<AppointmentRecord[]>(
    `/openmrs/ws/rest/v1/appointments?${query.toString()}`,
  );

  return (records ?? []).map((record) => ({
    uuid: record.uuid,
    time: formatClock(record.startDateTime),
    patientName: record.patient?.name || "Unknown patient",
    patientUuid: record.patient?.uuid || "",
    mrn: record.patient?.identifier || "—",
    doctor: record.providers?.[0]?.name || record.provider?.name || "—",
    department:
      record.service?.speciality?.name || record.service?.name || "—",
    status: record.status || "Scheduled",
  }));
}
