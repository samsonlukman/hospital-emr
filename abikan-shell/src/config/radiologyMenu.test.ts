import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  HISTORICAL_ORD_6,
  RADIOGRAPHY_GROUP,
  RADIOLOGY_MENU,
  ULTRASOUND_GROUP,
  canOrderRadiologyService,
  doctorRadiologyOrderHasNoPrice,
  findRadiologyService,
  findRadiologyServiceByConcept,
  hospitalRadiologyLabel,
  orderableRadiologyServices,
  radiologyMenuByGroup,
  resolveRadiologyOrderConcept,
  serviceConceptUuids,
} from "./radiologyMenu.ts";

const ULTRASOUND_NAMES = [
  "Obstetrics (Pregnancy)",
  "Pelvic",
  "Breast",
  "Abdominopelvic",
  "Biophysical Profile (BPP)",
  "Thyroid/Neck",
  "Anomaly Scan",
  "Eye/Ocular",
  "Scrotal/Testicular",
  "Musculoskeletal",
  "Follicular Tracking",
  "Prostate",
  "Transvaginal",
  "Doppler Studies",
] as const;

const RADIOGRAPHY_NAMES = [
  "Abdominal X-ray",
  "Cervical Neck X-ray",
  "Chest X-ray",
  "Lumbosacral Spine",
  "Paranasal Sinuses",
  "Facial Bones/Mandible",
  "Pelvic X-ray",
  "Knee Joint",
  "Ankle Joint",
  "Paediatric X-ray",
  "Hysterosalpingography (HSG)",
  "Intravenous Urography (IVU)",
  "Retrograde Urethrography (RCUG)",
  "Barium Enema",
  "Skull X-ray",
  "Thoracolumbar Spine",
  "Shoulder X-ray",
  "Humeral X-ray",
  "Forearm X-ray",
  "Tibia & Fibula X-ray",
  "Elbow X-ray",
  "Wrist/Hand/Finger X-ray",
  "Femoral X-ray",
  "Thoracic Inlet",
  "Micturating (Voiding) Cystourethrography (MCUG)",
  "Temporomandibular Joint",
  "Barium Meal",
  "Barium Follow Through",
] as const;

const CREATED_CONCEPTS: Record<string, string> = {
  "Abdominopelvic": "32f23df0-927d-4fd7-b446-d92ed6dff831",
  "Biophysical Profile (BPP)": "555f0bdd-14ae-4978-9bf4-3c46bfb2f681",
  "Anomaly Scan": "012ba652-ebad-4ebd-a680-b2de1f800df1",
  "Eye/Ocular": "4497c384-d908-41dc-bab2-ec40040b1cd4",
  "Follicular Tracking": "b83c6817-cbbc-4a3b-bfdb-4920b54c3754",
  "Doppler Studies": "c3e07bb5-fdbc-44ca-98f7-2d9bf6a8ef73",
  "Thyroid/Neck": "4b374fce-4d09-41e9-b639-21c0caaead09",
  "Paediatric X-ray": "e00d6245-e242-486f-885c-d7bf6383f829",
  "Retrograde Urethrography (RCUG)": "11444779-a642-4aa0-8553-f55000724c63",
  "Thoracic Inlet": "1b85a1cc-998f-4882-974b-af17ccd922e3",
  "Temporomandibular Joint": "b870eda8-f4b2-4fff-a563-d882b5cb32b3",
  "Barium Follow Through": "00f0b2b0-1004-4eb3-81ff-6d350ba12fe6",
  "Wrist/Hand/Finger X-ray": "7a9da21d-f687-4a61-abbc-7c9b7e925051",
};

describe("hospital radiology menu", () => {
  it("uses the hospital scan names exactly and groups Ultrasound then Radiography", () => {
    assert.equal(RADIOLOGY_MENU.length, 42);
    assert.deepEqual(
      radiologyMenuByGroup(ULTRASOUND_GROUP).map((row) => row.hospitalName),
      [...ULTRASOUND_NAMES],
    );
    assert.deepEqual(
      radiologyMenuByGroup(RADIOGRAPHY_GROUP).map((row) => row.hospitalName),
      [...RADIOGRAPHY_NAMES],
    );
    assert.equal(radiologyMenuByGroup(ULTRASOUND_GROUP).length, 14);
    assert.equal(radiologyMenuByGroup(RADIOGRAPHY_GROUP).length, 28);
  });

  it("does not add laterality, views, or invented clinical names to the hospital labels", () => {
    const names = RADIOLOGY_MENU.map((row) => row.hospitalName).join(" ");
    assert.equal(/Left|Right|Bilateral|TRUS|transabdominal|PA \/|single view/i.test(names), false);
    assert.equal(RADIOLOGY_MENU.some((row) => row.hospitalName === "OPD"), false);
  });

  it("makes all 42 hospital services orderable with no unavailable placeholder", () => {
    const orderable = orderableRadiologyServices();
    assert.equal(orderable.length, 42);
    assert.equal(
      RADIOLOGY_MENU.every((service) => canOrderRadiologyService(service)),
      true,
    );
    assert.equal(
      RADIOLOGY_MENU.some((service) => service.availability !== "orderable"),
      false,
    );
    assert.equal(
      RADIOLOGY_MENU.every((service) => serviceConceptUuids(service).length > 0),
      true,
    );
    assert.equal(canOrderRadiologyService(findRadiologyService("us-obstetrics")), true);
    assert.equal(canOrderRadiologyService(findRadiologyService("us-breast")), true);
    assert.equal(canOrderRadiologyService(findRadiologyService("us-abdominopelvic")), true);
    assert.equal(canOrderRadiologyService(findRadiologyService("xr-knee")), true);
    assert.equal(canOrderRadiologyService(findRadiologyService("xr-chest")), true);
  });

  it("maps each hospital service to the configured OpenMRS concept", () => {
    assert.equal(
      findRadiologyService("us-obstetrics")?.conceptUuid,
      "159618AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    );
    assert.equal(
      findRadiologyService("us-prostate")?.conceptUuid,
      "ee40db9c-0fd8-462a-93a1-f5ec1de14f7a",
    );
    assert.equal(findRadiologyService("us-abdominopelvic")?.conceptUuid, CREATED_CONCEPTS.Abdominopelvic);
    assert.equal(findRadiologyService("us-doppler")?.conceptUuid, CREATED_CONCEPTS["Doppler Studies"]);
    assert.equal(findRadiologyService("xr-rcug")?.conceptUuid, CREATED_CONCEPTS["Retrograde Urethrography (RCUG)"]);
    assert.equal(
      findRadiologyService("xr-wrist-hand-finger")?.conceptUuid,
      CREATED_CONCEPTS["Wrist/Hand/Finger X-ray"],
    );
    const knee = resolveRadiologyOrderConcept(findRadiologyService("xr-knee"), "right");
    assert.equal(knee?.conceptUuid, "161349AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    const breast = resolveRadiologyOrderConcept(findRadiologyService("us-breast"), "left");
    assert.equal(breast?.conceptUuid, "161289AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    assert.equal(resolveRadiologyOrderConcept(findRadiologyService("xr-knee")), undefined);
    assert.equal(
      hospitalRadiologyLabel("161349AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "X-ray of right knee"),
      "Knee Joint — Right",
    );
  });

  it("does not silently map combined or laterality services to an unrelated concept", () => {
    assert.notEqual(findRadiologyService("us-abdominopelvic")?.conceptUuid, "845AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    assert.notEqual(findRadiologyService("us-abdominopelvic")?.conceptUuid, "161283AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    assert.notEqual(findRadiologyService("us-anomaly")?.conceptUuid, "159618AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    assert.notEqual(findRadiologyService("us-bpp")?.conceptUuid, "159618AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    assert.notEqual(findRadiologyService("us-doppler")?.conceptUuid, "6092cbe6-c02d-4c59-a268-f4c421d6e994");
    assert.notEqual(findRadiologyService("xr-rcug")?.conceptUuid, "165146AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    assert.notEqual(findRadiologyService("xr-barium-follow")?.conceptUuid, "159600AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    assert.notEqual(findRadiologyService("xr-wrist-hand-finger")?.conceptUuid, "382AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    assert.notEqual(findRadiologyService("us-thyroid")?.conceptUuid, "65b41d2f-6c02-4cdc-8cee-967666723ee3");
    assert.notEqual(findRadiologyService("us-thyroid")?.conceptUuid, "161285AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
  });

  it("maps Chest X-ray to the existing concept and does not treat ORD-6 $60 as the menu price", () => {
    const chest = findRadiologyService("xr-chest");
    assert.equal(chest?.conceptUuid, HISTORICAL_ORD_6.conceptUuid);
    assert.equal(hospitalRadiologyLabel(chest?.conceptUuid, "Chest x-ray, single view"), "Chest X-ray");
    assert.equal(doctorRadiologyOrderHasNoPrice(), true);
    assert.equal(HISTORICAL_ORD_6.orderNumber, "ORD-6");
    assert.equal(HISTORICAL_ORD_6.amountUsd, 60);
    assert.equal(Object.prototype.hasOwnProperty.call(chest, "price"), false);
  });

  it("looks up a hospital name from the stored concept", () => {
    assert.equal(
      findRadiologyServiceByConcept("159618AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")?.hospitalName,
      "Obstetrics (Pregnancy)",
    );
    assert.equal(
      findRadiologyServiceByConcept("161349AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")?.hospitalName,
      "Knee Joint",
    );
  });
});
