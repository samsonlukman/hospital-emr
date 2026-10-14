"""Hospital-approved Radiology menu.

Hospital names are authoritative. Every service is backed by an OpenMRS
Radiology/Imaging Procedure concept. Laterality or area is required only
when the dictionary has no generic concept for that hospital line.
"""

from __future__ import annotations

from typing import Any

ULTRASOUND_GROUP = "Ultrasound Scan"
RADIOGRAPHY_GROUP = "Radiography / Fluoroscopy"

HISTORICAL_ORD_6 = {
    "orderNumber": "ORD-6",
    "orderUuid": "46e6031f-1fa9-4c48-a510-d32666cbc2ce",
    "conceptUuid": "165152AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "productName": "Chest x-ray, single view — TEST",
    "amountUsd": 60.0,
}


def _side(right: tuple[str, str], left: tuple[str, str], both: tuple[str, str] | None = None) -> list[dict[str, str]]:
    options = [
        {"id": "right", "label": "Right", "conceptUuid": right[0], "conceptName": right[1]},
        {"id": "left", "label": "Left", "conceptUuid": left[0], "conceptName": left[1]},
    ]
    if both:
        options.append({"id": "bilateral", "label": "Bilateral", "conceptUuid": both[0], "conceptName": both[1]})
    return options


MENU: list[dict[str, Any]] = [
    {
        "id": "us-obstetrics",
        "hospitalName": "Obstetrics (Pregnancy)",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "159618AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "Obstetric ultrasound",
    },
    {
        "id": "us-pelvic",
        "hospitalName": "Pelvic",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "161283AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "Ultrasound of pelvis",
    },
    {
        "id": "us-breast",
        "hospitalName": "Breast",
        "group": ULTRASOUND_GROUP,
        "optionPrompt": "Side",
        "options": _side(
            ("161290AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "Ultrasound of right breast"),
            ("161289AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "Ultrasound of left breast"),
        ),
    },
    {
        "id": "us-abdominopelvic",
        "hospitalName": "Abdominopelvic",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "32f23df0-927d-4fd7-b446-d92ed6dff831",
        "conceptName": "Abdominopelvic",
    },
    {
        "id": "us-bpp",
        "hospitalName": "Biophysical Profile (BPP)",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "555f0bdd-14ae-4978-9bf4-3c46bfb2f681",
        "conceptName": "Biophysical Profile (BPP)",
    },
    {
        "id": "us-thyroid",
        "hospitalName": "Thyroid/Neck",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "4b374fce-4d09-41e9-b639-21c0caaead09",
        "conceptName": "Thyroid/Neck",
    },
    {
        "id": "us-anomaly",
        "hospitalName": "Anomaly Scan",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "012ba652-ebad-4ebd-a680-b2de1f800df1",
        "conceptName": "Anomaly Scan",
    },
    {
        "id": "us-ocular",
        "hospitalName": "Eye/Ocular",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "4497c384-d908-41dc-bab2-ec40040b1cd4",
        "conceptName": "Eye/Ocular",
    },
    {
        "id": "us-scrotal",
        "hospitalName": "Scrotal/Testicular",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "161279AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "Ultrasound of scrotum and testicle",
    },
    {
        "id": "us-msk",
        "hospitalName": "Musculoskeletal",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "161277AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "Ultrasound of extremity",
    },
    {
        "id": "us-follicular",
        "hospitalName": "Follicular Tracking",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "b83c6817-cbbc-4a3b-bfdb-4920b54c3754",
        "conceptName": "Follicular Tracking",
    },
    {
        "id": "us-prostate",
        "hospitalName": "Prostate",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "ee40db9c-0fd8-462a-93a1-f5ec1de14f7a",
        "conceptName": "Ultrasound of prostate",
    },
    {
        "id": "us-transvaginal",
        "hospitalName": "Transvaginal",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "161278AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "Ultrasound of pelvis, transvaginal",
    },
    {
        "id": "us-doppler",
        "hospitalName": "Doppler Studies",
        "group": ULTRASOUND_GROUP,
        "conceptUuid": "c3e07bb5-fdbc-44ca-98f7-2d9bf6a8ef73",
        "conceptName": "Doppler Studies",
    },
    {
        "id": "xr-abdomen",
        "hospitalName": "Abdominal X-ray",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "101AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "X-ray, abdomen",
    },
    {
        "id": "xr-cervical",
        "hospitalName": "Cervical Neck X-ray",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "161301AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "X-ray of cervical spine, two or three views",
    },
    {
        "id": "xr-chest",
        "hospitalName": "Chest X-ray",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "165152AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "Chest x-ray, single view",
    },
    {
        "id": "xr-lumbosacral",
        "hospitalName": "Lumbosacral Spine",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "165126AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "X-ray of lumbosacral spine, two to three views",
    },
    {
        "id": "xr-pns",
        "hospitalName": "Paranasal Sinuses",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "161341AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "X-ray of paranasal sinuses, three views",
    },
    {
        "id": "xr-facial",
        "hospitalName": "Facial Bones/Mandible",
        "group": RADIOGRAPHY_GROUP,
        "optionPrompt": "Area",
        "options": [
            {
                "id": "facial-bones",
                "label": "Facial Bones",
                "conceptUuid": "161305AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                "conceptName": "X-ray of facial bones, three views",
            },
            {
                "id": "mandible",
                "label": "Mandible",
                "conceptUuid": "165121AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                "conceptName": "X-ray of mandible, three views",
            },
        ],
    },
    {
        "id": "xr-pelvis",
        "hospitalName": "Pelvic X-ray",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "392AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "X-ray, pelvis",
    },
    {
        "id": "xr-knee",
        "hospitalName": "Knee Joint",
        "group": RADIOGRAPHY_GROUP,
        "optionPrompt": "Side",
        "options": _side(
            ("161349AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right knee, one or two views"),
            ("161350AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left knee, one or two views"),
            ("161352AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of bilateral knees, 2 views"),
        ),
    },
    {
        "id": "xr-ankle",
        "hospitalName": "Ankle Joint",
        "group": RADIOGRAPHY_GROUP,
        "optionPrompt": "Side",
        "options": _side(
            ("161267AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right ankle, 2 views"),
            ("161266AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left ankle, two views"),
            ("161268AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of both ankles, 2 views"),
        ),
    },
    {
        "id": "xr-paediatric",
        "hospitalName": "Paediatric X-ray",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "e00d6245-e242-486f-885c-d7bf6383f829",
        "conceptName": "Paediatric X-ray",
    },
    {
        "id": "xr-hsg",
        "hospitalName": "Hysterosalpingography (HSG)",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "165136AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "Hysterosalpingography (HSG), six views",
    },
    {
        "id": "xr-ivu",
        "hospitalName": "Intravenous Urography (IVU)",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "165096AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "X-ray of kidney with intravenous contrast, six to eight views",
    },
    {
        "id": "xr-rcug",
        "hospitalName": "Retrograde Urethrography (RCUG)",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "11444779-a642-4aa0-8553-f55000724c63",
        "conceptName": "Retrograde Urethrography (RCUG)",
    },
    {
        "id": "xr-barium-enema",
        "hospitalName": "Barium Enema",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "164956AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "Barium enema",
    },
    {
        "id": "xr-skull",
        "hospitalName": "Skull X-ray",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "386AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "X-ray of skull",
    },
    {
        "id": "xr-thoracolumbar",
        "hospitalName": "Thoracolumbar Spine",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "161335AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "X-ray of thoracic and lumbar spine, two views",
    },
    {
        "id": "xr-shoulder",
        "hospitalName": "Shoulder X-ray",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "394AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "X-ray, shoulder",
    },
    {
        "id": "xr-humeral",
        "hospitalName": "Humeral X-ray",
        "group": RADIOGRAPHY_GROUP,
        "optionPrompt": "Side",
        "options": _side(
            ("161338AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right upper arm, two views"),
            ("161337AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left upper arm, two views"),
            ("161340AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of bilateral upper arms, 2 views"),
        ),
    },
    {
        "id": "xr-forearm",
        "hospitalName": "Forearm X-ray",
        "group": RADIOGRAPHY_GROUP,
        "optionPrompt": "Side",
        "options": _side(
            ("161325AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right forearm, two views"),
            ("161324AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left forearm, two views"),
            ("161326AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of bilateral forearms, 2 views"),
        ),
    },
    {
        "id": "xr-tibia",
        "hospitalName": "Tibia & Fibula X-ray",
        "group": RADIOGRAPHY_GROUP,
        "optionPrompt": "Side",
        "options": _side(
            ("161327AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right lower leg, two views"),
            ("161329AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left lower leg, two views"),
        ),
    },
    {
        "id": "xr-elbow",
        "hospitalName": "Elbow X-ray",
        "group": RADIOGRAPHY_GROUP,
        "optionPrompt": "Side",
        "options": _side(
            ("161303AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right elbow, two views"),
            ("161302AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left elbow, two views"),
            ("161304AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of bilateral elbows, 2 views"),
        ),
    },
    {
        "id": "xr-wrist-hand-finger",
        "hospitalName": "Wrist/Hand/Finger X-ray",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "7a9da21d-f687-4a61-abbc-7c9b7e925051",
        "conceptName": "Wrist/Hand/Finger X-ray",
    },
    {
        "id": "xr-femoral",
        "hospitalName": "Femoral X-ray",
        "group": RADIOGRAPHY_GROUP,
        "optionPrompt": "Side",
        "options": _side(
            ("161307AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right femur, two views"),
            ("161306AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of left femur, two views"),
            ("161308AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of bilateral femurs, 2 views"),
        ),
    },
    {
        "id": "xr-thoracic-inlet",
        "hospitalName": "Thoracic Inlet",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "1b85a1cc-998f-4882-974b-af17ccd922e3",
        "conceptName": "Thoracic Inlet",
    },
    {
        "id": "xr-mcug",
        "hospitalName": "Micturating (Voiding) Cystourethrography (MCUG)",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "164552AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "Voiding urethrocystography",
    },
    {
        "id": "xr-tmj",
        "hospitalName": "Temporomandibular Joint",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "b870eda8-f4b2-4fff-a563-d882b5cb32b3",
        "conceptName": "Temporomandibular Joint",
    },
    {
        "id": "xr-barium-meal",
        "hospitalName": "Barium Meal",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "159600AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "conceptName": "x-ray, upper gastrointestinal series",
    },
    {
        "id": "xr-barium-follow",
        "hospitalName": "Barium Follow Through",
        "group": RADIOGRAPHY_GROUP,
        "conceptUuid": "00f0b2b0-1004-4eb3-81ff-6d350ba12fe6",
        "conceptName": "Barium Follow Through",
    },
]

BY_ID = {str(row["id"]): row for row in MENU}
BY_CONCEPT: dict[str, dict[str, Any]] = {}
for row in MENU:
    for option in row.get("options") or []:
        BY_CONCEPT[str(option["conceptUuid"])] = {**row, **option, "hospitalName": row["hospitalName"]}
    if row.get("conceptUuid"):
        BY_CONCEPT[str(row["conceptUuid"])] = row


def entry_by_id(service_id: str) -> dict[str, Any] | None:
    return BY_ID.get((service_id or "").strip())


def entry_by_concept(concept_uuid: str) -> dict[str, Any] | None:
    return BY_CONCEPT.get((concept_uuid or "").strip())


def resolve_orderable(service_id: str, concept_uuid: str) -> dict[str, Any] | None:
    service = entry_by_id(service_id)
    requested = (concept_uuid or "").strip()
    if service:
        options = service.get("options") or []
        if options:
            if requested:
                for option in options:
                    if str(option["conceptUuid"]) == requested:
                        return {
                            **service,
                            "conceptUuid": option["conceptUuid"],
                            "conceptName": option["conceptName"],
                            "optionLabel": option["label"],
                        }
                return None
            return None
        return service
    return entry_by_concept(requested)


def hospital_name(concept_uuid: str, fallback: str = "Imaging examination") -> str:
    found = entry_by_concept(concept_uuid)
    if not found:
        return fallback
    name = str(found.get("hospitalName") or fallback)
    label = found.get("optionLabel") or found.get("label")
    if label and found.get("options"):
        return f"{name} — {label}"
    return name
