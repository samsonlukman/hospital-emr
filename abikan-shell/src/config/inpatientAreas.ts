/** Hospital inpatient areas staff should see. Demo/test wards stay hidden. */
export const HOSPITAL_INPATIENT_AREAS = [
  "Hawawu Maternity Ward",
  "Aisha Children Ward",
  "Emergency Room",
  "Gold Room 203",
  "Gold Room 202",
  "Gold Room 204",
  "Silver 207",
  "Bronze 208",
  "Gold Room 210",
  "Gold Room 211",
  "Platinum Room 209",
  "Diamond 214",
  "Pre Labour Room",
  "Gold Room 212",
  "Gold Room 213",
  "Silver 206",
  "ICPU",
] as const;

export const HOSPITAL_INPATIENT_AREA_SET = new Set(
  HOSPITAL_INPATIENT_AREAS.map((name) => name.trim().toLowerCase()),
);
