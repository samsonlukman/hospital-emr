import type { NavGroup } from "../types";
import { ACCOUNTANT_NAV } from "./accountantNav";
import { ADMIN_NAV } from "./adminNav";
import { DOCTOR_NAV } from "./doctorNav";
import { LABORATORY_NAV } from "./laboratoryNav";
import { NURSING_NAV } from "./nursingNav";
import { PHARMACY_NAV } from "./pharmacyNav";
import { RADIOLOGY_NAV } from "./radiologyNav";
import { RECEPTION_NAV } from "./receptionNav";
import { MESSAGES_NAV } from "./messagesNav";
import { SYSTEM_NAV } from "./systemNav";
import type { WorkplaceId } from "./workplaces";

export function navGroupsForWorkplace(workplaceId: WorkplaceId): NavGroup[] {
  let groups: NavGroup[] = [];
  switch (workplaceId) {
    case "administration":
      groups = ADMIN_NAV;
      break;
    case "registration":
      groups = RECEPTION_NAV;
      break;
    case "clinical":
      groups = DOCTOR_NAV;
      break;
    case "nursing":
      groups = NURSING_NAV;
      break;
    case "pharmacy":
      groups = PHARMACY_NAV;
      break;
    case "laboratory":
      groups = LABORATORY_NAV;
      break;
    case "radiology":
      groups = RADIOLOGY_NAV;
      break;
    case "accountant":
      groups = ACCOUNTANT_NAV;
      break;
  }
  return [...groups, MESSAGES_NAV, SYSTEM_NAV];
}
