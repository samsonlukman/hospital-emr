export const RADIOLOGY_ORDER_TYPE_UUID = "d3561dc0-5e07-11ef-8f7c-0242ac120002";

export const ULTRASOUND_GROUP = "Ultrasound Scan";
export const RADIOGRAPHY_GROUP = "Radiography / Fluoroscopy";

export type RadiologyMenuGroup = typeof ULTRASOUND_GROUP | typeof RADIOGRAPHY_GROUP;

export type RadiologyMenuAvailability = "orderable" | "missing_concept" | "ambiguous";

export type RadiologyOptionPrompt = "Side" | "Area";

export interface RadiologyMenuOption {
  id: string;
  label: string;
  conceptUuid: string;
  conceptName: string;
}

export interface RadiologyMenuService {
  id: string;
  hospitalName: string;
  group: RadiologyMenuGroup;
  availability: RadiologyMenuAvailability;
  conceptUuid?: string;
  conceptName?: string;
  match?: "EXACT" | "CLOSE";
  optionPrompt?: RadiologyOptionPrompt;
  options?: RadiologyMenuOption[];
}

/** Isolated historical TEST evidence. Do not use as a hospital price. */
export const HISTORICAL_ORD_6 = {
  orderNumber: "ORD-6",
  orderUuid: "46e6031f-1fa9-4c48-a510-d32666cbc2ce",
  conceptUuid: "165152AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
  productName: "Chest x-ray, single view — TEST",
  amountUsd: 60,
} as const;

function laterality(
  right: [string, string],
  left: [string, string],
  both?: [string, string],
): RadiologyMenuOption[] {
  const options: RadiologyMenuOption[] = [
    { id: "right", label: "Right", conceptUuid: right[0], conceptName: right[1] },
    { id: "left", label: "Left", conceptUuid: left[0], conceptName: left[1] },
  ];
  if (both) {
    options.push({ id: "bilateral", label: "Bilateral", conceptUuid: both[0], conceptName: both[1] });
  }
  return options;
}

export const RADIOLOGY_MENU: RadiologyMenuService[] = [
  {
    id: "us-obstetrics",
    hospitalName: "Obstetrics (Pregnancy)",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "159618AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "Obstetric ultrasound",
    match: "EXACT",
  },
  {
    id: "us-pelvic",
    hospitalName: "Pelvic",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "161283AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "Ultrasound of pelvis",
    match: "EXACT",
  },
  {
    id: "us-breast",
    hospitalName: "Breast",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    match: "CLOSE",
    optionPrompt: "Side",
    options: laterality(
      ["161290AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "Ultrasound of right breast"],
      ["161289AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "Ultrasound of left breast"],
    ),
  },
  {
    id: "us-abdominopelvic",
    hospitalName: "Abdominopelvic",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "32f23df0-927d-4fd7-b446-d92ed6dff831",
    conceptName: "Abdominopelvic",
    match: "EXACT",
  },
  {
    id: "us-bpp",
    hospitalName: "Biophysical Profile (BPP)",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "555f0bdd-14ae-4978-9bf4-3c46bfb2f681",
    conceptName: "Biophysical Profile (BPP)",
    match: "EXACT",
  },
  {
    id: "us-thyroid",
    hospitalName: "Thyroid/Neck",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "4b374fce-4d09-41e9-b639-21c0caaead09",
    conceptName: "Thyroid/Neck",
    match: "EXACT",
  },
  {
    id: "us-anomaly",
    hospitalName: "Anomaly Scan",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "012ba652-ebad-4ebd-a680-b2de1f800df1",
    conceptName: "Anomaly Scan",
    match: "EXACT",
  },
  {
    id: "us-ocular",
    hospitalName: "Eye/Ocular",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "4497c384-d908-41dc-bab2-ec40040b1cd4",
    conceptName: "Eye/Ocular",
    match: "EXACT",
  },
  {
    id: "us-scrotal",
    hospitalName: "Scrotal/Testicular",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "161279AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "Ultrasound of scrotum and testicle",
    match: "EXACT",
  },
  {
    id: "us-msk",
    hospitalName: "Musculoskeletal",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "161277AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "Ultrasound of extremity",
    match: "CLOSE",
  },
  {
    id: "us-follicular",
    hospitalName: "Follicular Tracking",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "b83c6817-cbbc-4a3b-bfdb-4920b54c3754",
    conceptName: "Follicular Tracking",
    match: "EXACT",
  },
  {
    id: "us-prostate",
    hospitalName: "Prostate",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "ee40db9c-0fd8-462a-93a1-f5ec1de14f7a",
    conceptName: "Ultrasound of prostate",
    match: "EXACT",
  },
  {
    id: "us-transvaginal",
    hospitalName: "Transvaginal",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "161278AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "Ultrasound of pelvis, transvaginal",
    match: "EXACT",
  },
  {
    id: "us-doppler",
    hospitalName: "Doppler Studies",
    group: ULTRASOUND_GROUP,
    availability: "orderable",
    conceptUuid: "c3e07bb5-fdbc-44ca-98f7-2d9bf6a8ef73",
    conceptName: "Doppler Studies",
    match: "EXACT",
  },
  {
    id: "xr-abdomen",
    hospitalName: "Abdominal X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "101AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "X-ray, abdomen",
    match: "EXACT",
  },
  {
    id: "xr-cervical",
    hospitalName: "Cervical Neck X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "161301AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "X-ray of cervical spine, two or three views",
    match: "CLOSE",
  },
  {
    id: "xr-chest",
    hospitalName: "Chest X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "165152AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "Chest x-ray, single view",
    match: "CLOSE",
  },
  {
    id: "xr-lumbosacral",
    hospitalName: "Lumbosacral Spine",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "165126AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "X-ray of lumbosacral spine, two to three views",
    match: "EXACT",
  },
  {
    id: "xr-pns",
    hospitalName: "Paranasal Sinuses",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "161341AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "X-ray of paranasal sinuses, three views",
    match: "EXACT",
  },
  {
    id: "xr-facial",
    hospitalName: "Facial Bones/Mandible",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    match: "CLOSE",
    optionPrompt: "Area",
    options: [
      {
        id: "facial-bones",
        label: "Facial Bones",
        conceptUuid: "161305AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        conceptName: "X-ray of facial bones, three views",
      },
      {
        id: "mandible",
        label: "Mandible",
        conceptUuid: "165121AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        conceptName: "X-ray of mandible, three views",
      },
    ],
  },
  {
    id: "xr-pelvis",
    hospitalName: "Pelvic X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "392AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "X-ray, pelvis",
    match: "EXACT",
  },
  {
    id: "xr-knee",
    hospitalName: "Knee Joint",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    match: "CLOSE",
    optionPrompt: "Side",
    options: laterality(
      ["161349AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right knee, one or two views"],
      ["161350AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left knee, one or two views"],
      ["161352AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of bilateral knees, 2 views"],
    ),
  },
  {
    id: "xr-ankle",
    hospitalName: "Ankle Joint",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    match: "CLOSE",
    optionPrompt: "Side",
    options: laterality(
      ["161267AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right ankle, 2 views"],
      ["161266AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left ankle, two views"],
      ["161268AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of both ankles, 2 views"],
    ),
  },
  {
    id: "xr-paediatric",
    hospitalName: "Paediatric X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "e00d6245-e242-486f-885c-d7bf6383f829",
    conceptName: "Paediatric X-ray",
    match: "EXACT",
  },
  {
    id: "xr-hsg",
    hospitalName: "Hysterosalpingography (HSG)",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "165136AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "Hysterosalpingography (HSG), six views",
    match: "EXACT",
  },
  {
    id: "xr-ivu",
    hospitalName: "Intravenous Urography (IVU)",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "165096AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "X-ray of kidney with intravenous contrast, six to eight views",
    match: "CLOSE",
  },
  {
    id: "xr-rcug",
    hospitalName: "Retrograde Urethrography (RCUG)",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "11444779-a642-4aa0-8553-f55000724c63",
    conceptName: "Retrograde Urethrography (RCUG)",
    match: "EXACT",
  },
  {
    id: "xr-barium-enema",
    hospitalName: "Barium Enema",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "164956AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "Barium enema",
    match: "EXACT",
  },
  {
    id: "xr-skull",
    hospitalName: "Skull X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "386AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "X-ray of skull",
    match: "EXACT",
  },
  {
    id: "xr-thoracolumbar",
    hospitalName: "Thoracolumbar Spine",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "161335AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "X-ray of thoracic and lumbar spine, two views",
    match: "CLOSE",
  },
  {
    id: "xr-shoulder",
    hospitalName: "Shoulder X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "394AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "X-ray, shoulder",
    match: "EXACT",
  },
  {
    id: "xr-humeral",
    hospitalName: "Humeral X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    match: "CLOSE",
    optionPrompt: "Side",
    options: laterality(
      ["161338AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right upper arm, two views"],
      ["161337AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left upper arm, two views"],
      ["161340AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of bilateral upper arms, 2 views"],
    ),
  },
  {
    id: "xr-forearm",
    hospitalName: "Forearm X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    match: "CLOSE",
    optionPrompt: "Side",
    options: laterality(
      ["161325AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right forearm, two views"],
      ["161324AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left forearm, two views"],
      ["161326AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of bilateral forearms, 2 views"],
    ),
  },
  {
    id: "xr-tibia",
    hospitalName: "Tibia & Fibula X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    match: "CLOSE",
    optionPrompt: "Side",
    options: laterality(
      ["161327AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right lower leg, two views"],
      ["161329AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left lower leg, two views"],
    ),
  },
  {
    id: "xr-elbow",
    hospitalName: "Elbow X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    match: "CLOSE",
    optionPrompt: "Side",
    options: laterality(
      ["161303AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right elbow, two views"],
      ["161302AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left elbow, two views"],
      ["161304AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of bilateral elbows, 2 views"],
    ),
  },
  {
    id: "xr-wrist-hand-finger",
    hospitalName: "Wrist/Hand/Finger X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "7a9da21d-f687-4a61-abbc-7c9b7e925051",
    conceptName: "Wrist/Hand/Finger X-ray",
    match: "EXACT",
  },
  {
    id: "xr-femoral",
    hospitalName: "Femoral X-ray",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    match: "CLOSE",
    optionPrompt: "Side",
    options: laterality(
      ["161307AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right femur, two views"],
      ["161306AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left femur, two views"],
      ["161308AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of bilateral femurs, 2 views"],
    ),
  },
  {
    id: "xr-thoracic-inlet",
    hospitalName: "Thoracic Inlet",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "1b85a1cc-998f-4882-974b-af17ccd922e3",
    conceptName: "Thoracic Inlet",
    match: "EXACT",
  },
  {
    id: "xr-mcug",
    hospitalName: "Micturating (Voiding) Cystourethrography (MCUG)",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "164552AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "Voiding urethrocystography",
    match: "EXACT",
  },
  {
    id: "xr-tmj",
    hospitalName: "Temporomandibular Joint",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "b870eda8-f4b2-4fff-a563-d882b5cb32b3",
    conceptName: "Temporomandibular Joint",
    match: "EXACT",
  },
  {
    id: "xr-barium-meal",
    hospitalName: "Barium Meal",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "159600AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    conceptName: "x-ray, upper gastrointestinal series",
    match: "EXACT",
  },
  {
    id: "xr-barium-follow",
    hospitalName: "Barium Follow Through",
    group: RADIOGRAPHY_GROUP,
    availability: "orderable",
    conceptUuid: "00f0b2b0-1004-4eb3-81ff-6d350ba12fe6",
    conceptName: "Barium Follow Through",
    match: "EXACT",
  },
];

export const RADIOLOGY_UNAVAILABLE_MESSAGE =
  "This scan is not available to order yet. Ask the imaging desk if you need it today.";

export function radiologyMenuByGroup(group: RadiologyMenuGroup): RadiologyMenuService[] {
  return RADIOLOGY_MENU.filter((service) => service.group === group);
}

export function serviceConceptUuids(service: RadiologyMenuService): string[] {
  if (service.options?.length) {
    return service.options.map((option) => option.conceptUuid);
  }
  return service.conceptUuid ? [service.conceptUuid] : [];
}

export function orderableRadiologyServices(): RadiologyMenuService[] {
  return RADIOLOGY_MENU.filter((service) => canOrderRadiologyService(service));
}

export function findRadiologyService(id: string): RadiologyMenuService | undefined {
  return RADIOLOGY_MENU.find((service) => service.id === id);
}

export function findRadiologyServiceByConcept(
  conceptUuid: string | undefined,
): RadiologyMenuService | undefined {
  const uuid = (conceptUuid || "").trim();
  if (!uuid) {
    return undefined;
  }
  return RADIOLOGY_MENU.find((service) => serviceConceptUuids(service).includes(uuid));
}

export function findRadiologyOption(
  service: RadiologyMenuService | undefined,
  optionId: string | undefined,
): RadiologyMenuOption | undefined {
  const id = (optionId || "").trim();
  if (!service?.options?.length || !id) {
    return undefined;
  }
  return service.options.find((option) => option.id === id);
}

export function resolveRadiologyOrderConcept(
  service: RadiologyMenuService | undefined,
  optionId?: string,
): { conceptUuid: string; conceptName: string; optionLabel?: string } | undefined {
  if (!canOrderRadiologyService(service) || !service) {
    return undefined;
  }
  if (service.options?.length) {
    const option = findRadiologyOption(service, optionId);
    if (!option) {
      return undefined;
    }
    return {
      conceptUuid: option.conceptUuid,
      conceptName: option.conceptName,
      optionLabel: option.label,
    };
  }
  if (!service.conceptUuid) {
    return undefined;
  }
  return {
    conceptUuid: service.conceptUuid,
    conceptName: service.conceptName || service.hospitalName,
  };
}

export function canOrderRadiologyService(service: RadiologyMenuService | undefined): boolean {
  if (!service || service.availability !== "orderable") {
    return false;
  }
  if (service.options?.length) {
    return service.options.every((option) => Boolean(option.conceptUuid));
  }
  return Boolean(service.conceptUuid);
}

export function hospitalRadiologyLabel(
  conceptUuid: string | undefined,
  fallback: string | undefined,
): string {
  const service = findRadiologyServiceByConcept(conceptUuid);
  if (!service) {
    return fallback || "Imaging examination";
  }
  const option = service.options?.find((row) => row.conceptUuid === (conceptUuid || "").trim());
  if (option) {
    return `${service.hospitalName} — ${option.label}`;
  }
  return service.hospitalName;
}

export function doctorRadiologyOrderHasNoPrice(): true {
  return true;
}
