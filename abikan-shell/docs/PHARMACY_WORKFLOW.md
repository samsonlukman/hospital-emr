# Hospital EMR pharmacy workflow

Source of truth: this Bahmni-standard deployment (OpenMRS 1.1.2, bahmnicore 1.2.0, Odoo 16 `bahmni/odoo-16:1.0.0`, odoo-connect 1.0.0), live **GET** probes, and read-only MySQL / PostgreSQL. No prescriptions, stock movements, invoices, or dispensing records were created during this investigation.

Do not invent a second pharmacy database. **OpenMRS** is the clinical chart (drug orders). **Odoo** is the inventory, sale, and billing engine. **Hospital EMR** is the product UI around both. Do not rebuild Odoo.

Related: `docs/CLINICAL_WRITE_API.md` (how a doctor prescription is saved on a consultation). Pharmacy **writes** (dispensing, stock changes, invoices) are **not** implemented in Hospital EMR.

Status labels used below:

- **CONFIRMED** — observed in this installation
- **UNKNOWN** — not established from source or live probes
- **COMING SOON** — Hospital EMR UI placeholder; no backend write

---

## Architecture (this installation)

```
Doctor consultation
  POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter
  drugOrders[]  (order type Drug Order)
        ↓
  OpenMRS orders + drug_order
  Atom feed  /openmrs/ws/atomfeed/encounter/recent
  Atom feed  /openmrs/ws/atomfeed/drug/recent     (drug catalogue)
  Atom feed  /openmrs/ws/atomfeed/patient/recent
        ↓
  odoo-connect  (consumes those feeds)
  Intended: Odoo sale order from the encounter’s drug orders
  Catalogue: Odoo product (type=product) from OpenMRS drug
        ↓
  Odoo  (stock, POS/sale, invoice)
  Home landing tile “Pharmacy & Billing” → host prefix erp-
        ↓
  Optional OpenMRS order attribute “Dispensed”
  Optional IPD medication_administration (ward MAR, not the counter)
        ↓
  Hospital EMR Pharmacy / Doctor chart  (OpenMRS reads)
```

Same principle as Laboratory and Radiology: Hospital EMR reads OpenMRS; the departmental engine (here Odoo) stays where it is.

**CONFIRMED:** there are currently **0** OpenMRS `drug_order` rows, **0** `orders` of type Drug Order, **0** `medication_administration` rows, **0** Odoo `sale_order`, **0** `stock_quant`, **0** `stock_lot`, **0** `stock_picking`, **0** `account_move`, **0** `pos_order`, **0** reorder rules (`stock_warehouse_orderpoint`).

---

## 1. Current pharmacy architecture

**CONFIRMED**

There is **no** Bahmni Pharmacy SPA on the home dashboard. Pharmacy work on this site is:

| Piece | This deployment |
|---|---|
| OpenMRS Drug Order | order type UUID `131168f4-15f5-102d-96e4-000c29c2a5d7` |
| Clinical Treatment tab | privilege `app:clinical:treatmentTab` |
| Dispense privilege | `bahmni:clinical:dispense` (order attribute **Dispensed**) |
| Odoo 16 | container `bahmni-standard-odoo-1`, DB `odoo` on `bahmni-standard-odoodb-1` |
| odoo-connect | container `bahmni-standard-odoo-connect-1`, image `bahmni/odoo-connect:1.0.0` |
| Home landing | **Pharmacy & Billing** → host prefix `erp-` (not `/odoo`) |
| Bahmni Odoo addons installed | `bahmni_account`, `bahmni_api_feed`, `bahmni_product`, `bahmni_purchase`, `bahmni_sale`, `bahmni_stock`, `bahmni_reports`, `restful_api`, plus Odoo `stock`, `sale`, `point_of_sale` |
| Login locations | Registration Desk, OPD-1, OPD-2, Emergency, General Ward, Pediatric Ward. **No Pharmacy location** |

Proxy (`bahmni-proxy.conf`): requests whose host starts with `erp-` are reverse-proxied to `odoo:8069`. There is no `/odoo` path on the clinical host.

---

## 2. Doctor prescription flow

**CONFIRMED** (write path from `CLINICAL_WRITE_API.md` and clinical JS; **no live prescriptions exist**)

Saved **inside** `POST /openmrs/ws/rest/v1/bahmnicore/bahmniencounter` as `drugOrders[]`, built by `Bahmni.Clinical.DrugOrder.createFromUIObject`.

```json
{
  "careSetting": "OUTPATIENT",
  "drug": { "uuid": "<drug-uuid>" },
  "orderType": "Drug Order",
  "dosingInstructionType": "org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions",
  "dosingInstructions": {
    "dose": 1,
    "doseUnits": "Tablet(s)",
    "route": "Oral",
    "frequency": "Twice a day",
    "asNeeded": false,
    "administrationInstructions": "{\"instructions\":\"As directed\"}",
    "quantity": 10,
    "quantityUnits": "Tablet(s)",
    "numberOfRefills": 0
  },
  "duration": 5,
  "durationUnits": "Day(s)"
}
```

Live config: `GET /openmrs/ws/rest/v1/bahmnicore/config/drugOrders` (HTTP 200).

| Config key | Count | Examples |
|---|---|---|
| doseUnits / dispensingUnits | 10 | Tablet, Capsule, ml, mg, IU, Drop, Tablespoon, Teaspoon, Unit, Puff |
| routes | 15 | Oral, IM, IV, SC, PR, SL, NG, … |
| durationUnits | 8 | Seconds … Years, Number of occurrences |
| frequencies | 23 | Once a day, Twice a day, Every 8 hours, … |
| dosingInstructions | 8 | Before meals, After meals, As directed, … |
| orderAttributes | 1 | **Dispensed** |

Drug search: `GET /openmrs/ws/rest/v1/drug?q=`. Catalogue size: **539** non-retired drugs.

Hospital EMR must **not** write `drugOrders[]` in this phase.

---

## 3. OpenMRS drug-order model

**CONFIRMED**

Stored in `orders` (order type Drug Order) plus `drug_order`:

| `drug_order` column | Role |
|---|---|
| drug_inventory_id | OpenMRS `drug` |
| dose, dose_units, route, frequency | Dosing |
| quantity, quantity_units | Dispense quantity on the **order** (intended amount) |
| duration, duration_units | Course length |
| as_needed, dosing_instructions, num_refills | Extra instructions |
| dosing_type | FlexibleDosingInstructions class |
| dispense_as_written | Substitution flag on the order |
| brand_name, drug_non_coded | Non-coded / brand |

`orders` also has `date_activated`, `auto_expire_date`, `date_stopped`, `order_action`, `order_number`, `care_setting`, `comment_to_fulfiller`, `fulfiller_status`, `urgency`.

`fulfiller_status` has **no** rows to observe. Do not treat OpenMRS fulfiller statuses as a live pharmacy queue.

Order attribute concept **Dispensed** is the confirmed Bahmni “this prescription was dispensed” flag (obs on the order), not a structured quantity-dispensed ledger.

---

## 4. Bahmni drug-order implementation

**CONFIRMED**

`BahmniDrugOrderController`:

| Method | Path | Notes |
|---|---|---|
| GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders?patientUuid=` | **Required** `patientUuid`. Live `[]` |
| GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders/active?patientUuid=` | Live `[]` |
| GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders/prescribedAndActive` | Visit-wise |
| GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders/drugOrderDetails` | Filtered details |
| GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders/{orderId}` | Missing id → HTTP **500** (empty list get(0)), not a clean 404 |
| GET | `/openmrs/ws/rest/v1/bahmnicore/config/drugOrders` | Units / routes / frequencies |
| GET | `/openmrs/ws/rest/v1/order?patient=&t=drugorder` | Live `[]` |

`GET /bahmnicore/drugOrders` without `patientUuid` → HTTP 500 missing parameter.

**There is no hospital-wide prescription queue on OpenMRS REST.** Same limitation as Laboratory and Radiology.

Contract (`BahmniDrugOrder` / `EncounterTransaction$DrugOrder`): uuid, orderNumber, drug {uuid, name, form, strength}, dosingInstructions {dose, doseUnits, route, frequency, asNeeded, administrationInstructions, quantity, quantityUnits, numberOfRefills}, duration, durationUnits, provider, dateActivated, dateStopped, autoExpireDate, careSetting, action, visit, encounterUuid, creatorName, orderAttributes, commentToFulfiller, instructions.

---

## 5. Pharmacy implementation

**CONFIRMED**

Operational pharmacy/billing UI is **Odoo**, not a Bahmni Pharmacy app.

Clinical **Treatment** tab is where doctors prescribe. Privilege `bahmni:clinical:dispense` gates the Dispensed order attribute in Clinical — that is chart documentation, not stock movement.

IPD **Medication Administration** module is started (`medication-administration.started` = true). Tables `medication_administration`, `medication_administration_performer` exist and have **0** rows. REST `GET /openmrs/ws/rest/v1/medicationadministration` is **Unknown resource**. This is ward MAR (nurse records a dose), not counter dispensing. SQL search `emrapi.sqlSearch.emergencyMedicationToAcknowledge` exists for IPD witness acknowledgement.

Do not present MAR rows as pharmacy dispensing.

---

## 6. Odoo integration

**CONFIRMED**

`odoo-connect` `erp-atomfeed.properties`:

| Feed | URI |
|---|---|
| Patients | `http://openmrs:8080/openmrs/ws/atomfeed/patient/recent` |
| Encounters (intended sale orders) | `…/atomfeed/encounter/recent` |
| Drugs (catalogue) | `…/atomfeed/drug/recent` |
| Lab catalogue | `…/atomfeed/lab/recent` |
| Saleable reference data | `…/atomfeed/saleable/recent` |
| Drug order fetch | `drugorder.uri=…/bahmnicore/drugOrders` |

Markers currently track patient, encounter, drug, lab, saleable feeds.

Odoo `product_template`: **539** rows with `type=product` (matches OpenMRS drug count), plus 1843 `service` (procedures) and 2 `consu`. Sample drug products have `list_price = 0.00` and **empty** `uuid` column; the Bahmni `drug` text column holds the drug name (e.g. Isoflurane, Ketamine).

`failed_events`: 97 rows, all **lab catalogue** NPEs (`ResponseCookie.getValue()`), not drug-order failures.

Do **not** query the Odoo database from the Hospital EMR browser. Odoo is a separate login on the `erp-` host.

---

## 7. Inventory model

**CONFIRMED**

| Odoo object | Live count | Meaning |
|---|---|---|
| product (type=product) | 539 | Drug catalogue synced from OpenMRS |
| stock_quant | 0 | No on-hand quantity |
| stock_lot | 0 | No batch / expiry lots |
| stock_warehouse | 1 | Default warehouse |
| stock_location | 16 | Standard Odoo locations |
| stock_warehouse_orderpoint | 0 | **No reorder thresholds** |
| stock_picking | 0 | No receipts/deliveries |

`product_template` has `expiration_time` / `use_time` / `alert_time` columns (Odoo expiry helpers) — unused without lots.

Hospital EMR must **not** label a drug Low Stock or Out of Stock. There is no quantity and no configured min qty.

Relationship: OpenMRS `drug` ≈ Odoo `product_template` (name/`drug` field). OpenMRS `drug_order.quantity` is the **prescribed** amount, not Odoo on-hand stock.

---

## 8. Billing relationship

**CONFIRMED**

| Odoo object | Live count |
|---|---|
| sale_order / sale_order_line | 0 |
| account_move (invoices) | 0 |
| pos_order | 0 |
| product list_price on sample drugs | **0.00** |

`sale_order` has Bahmni column `partner_uuid`. Intended path: encounter atomfeed → odoo-connect → sale order for the patient partner.

Whether billing happens before or after physical dispensing is **UNKNOWN** until a real sale exists. Do not create a Hospital EMR invoice model. Do not display prices of 0.00 as hospital tariffs.

Crater (Payment & Billing) is **disabled** on the landing page.

---

## 9. Dispensing workflow

| Step | Status |
|---|---|
| Doctor writes prescription | CONFIRMED write path; 0 live orders |
| Pharmacy queue (hospital-wide) | **Unsupported** on OpenMRS REST |
| Pharmacist review in Hospital EMR | COMING SOON |
| Stock check | Odoo stock empty; no safe browser API |
| Full dispense as OpenMRS attribute Dispensed | CONFIRMED concept exists; 0 obs |
| Partial dispense | **UNKNOWN** / not in `drug_order` |
| Unavailable / reject | **UNKNOWN** as a pharmacy state |
| Cancel / discontinue | OpenMRS `date_stopped` / `order_action` DISCONTINUE — no rows |
| Return | Odoo stock return — 0 pickings |
| Substitution | `dispense_as_written` on `drug_order` — no rows |
| Quantity actually handed over | Not a separate OpenMRS field; would be Odoo sale/POS qty |
| IPD dose administration | Separate MAR tables; 0 rows; not the pharmacy counter |

Confirmed visual statuses for Hospital EMR, when a row exists:

- **Ordered** — OpenMRS drug order present, not stopped
- **Stopped** — `dateStopped` set
- **Dispensed** — order attribute Dispensed present

Do not show Partially Dispensed / Awaiting Dispensing / New as backend truth.

---

## 10. APIs discovered

| Method | Path | Result |
|---|---|---|
| GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders?patientUuid=` | HTTP 200 `[]` |
| GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders/active?patientUuid=` | HTTP 200 `[]` |
| GET | `/openmrs/ws/rest/v1/bahmnicore/drugOrders/{orderId}` | HTTP 500 if missing |
| GET | `/openmrs/ws/rest/v1/bahmnicore/config/drugOrders` | HTTP 200 config |
| GET | `/openmrs/ws/rest/v1/order?patient=&t=drugorder` | HTTP 200 `[]` |
| GET | `/openmrs/ws/rest/v1/drug?q=` | HTTP 200 catalogue |
| GET | `/openmrs/ws/rest/v1/medicationadministration` | HTTP 404 unknown resource |
| POST | `/openmrs/ws/rest/v1/bahmnicore/bahmniencounter` `drugOrders[]` | **write** — not called |

Patient identity, visits, and allergies use the same clinical reads as Doctor and Nursing.

---

## 11. Source files inspected

| Area | Location |
|---|---|
| Drug order controller | `bahmnicore-1.2.0.omod` `BahmniDrugOrderController` |
| Contract | `bahmni-emr-api` `BahmniDrugOrder`, `EncounterTransaction$DrugOrder` / `$DosingInstructions` / `$Drug` |
| Clinical save | `docs/CLINICAL_WRITE_API.md`, clinical minified JS |
| Treatment tab | `abikan-config/openmrs/apps/clinical/extension.json` |
| Dashboard drug orders | `dashboard.json` `drugOrderDetails` |
| Order templates | `abikan-config/openmrs/ordertemplates/templates.json` |
| odoo-connect | `/opt/bahmni-erp-connect/etc/erp-atomfeed.properties.template` |
| Odoo addons | `/opt/bahmni-erp/bahmni-addons/bahmni_{sale,stock,product,api_feed,account}` |
| Proxy | `bahmni-proxy.conf` `erp-` host rewrite |
| Home landing | `abikan-config/openmrs/apps/home/whiteLabel.json` |

---

## 12. Authentication / session

**CONFIRMED**

- Hospital EMR uses the OpenMRS session cookie.
- Odoo is a **separate** application on the `erp-` host with its own users (`ODOO_ATOMFEED_USER` is only for odoo-connect).
- Do not assume OpenMRS `abikan.admin` can sign into Odoo.

---

## 13. Permissions

Use existing privileges. **Do not create new ones.**

| Privilege | Use |
|---|---|
| `bahmni:clinical:dispense` | **Hospital EMR Pharmacy workspace gate** (`PRIVILEGES.pharmacy`) |
| `app:clinical:treatmentTab` | Doctor Treatment / prescribe tab |
| `app:clinical` | Consultation save including `drugOrders[]` |

There is no `app:pharmacy`. `abikan.admin` has `bahmni:clinical:dispense` via SuperAdmin. Pharmacy is **location-independent**.

The Bahmni home **Pharmacy & Billing** (Odoo) tile must remain functional.

---

## 14. What Hospital EMR can safely read

- Per-patient drug orders via `GET /bahmnicore/drugOrders?patientUuid=`
- Active subset via `/drugOrders/active`
- Configured dose/route/frequency lists (reference only; do not invent extra units)
- Patient identity, visit, allergies
- Honest empty stock/billing (do not read Odoo from the browser)

KPIs and the hospital prescription queue have **no** REST source. Show **—** / empty states.

---

## 15. What Hospital EMR will eventually need to write

**COMING SOON — do not implement in this phase**

- Place `drugOrders[]` from Doctor consultation
- Set order attribute Dispensed
- Any Odoo sale/POS/stock move (that remains Odoo’s job unless a confirmed session-safe API appears)

---

## 16. What is unsupported

- Hospital-wide pharmacy queue on OpenMRS REST
- Live stock / batch / expiry / reorder from Hospital EMR
- Live prices (catalogue prices are 0.00; no invoices)
- Partial dispense / return / substitution as confirmed states
- `GET /medicationadministration` as a REST resource
- `#/pharmacy` inventory screens backed by Odoo SQL
- Hospital EMR writes of any kind in this phase

---

## 17. CONFIRMED vs UNKNOWN vs COMING SOON

### CONFIRMED

- Prescription write path and `drugOrders` GET
- 539 OpenMRS drugs synced as 539 Odoo products
- odoo-connect encounter + drug feeds; empty sales and stock
- Dispensed order attribute; 0 administrations
- Privilege `bahmni:clinical:dispense`
- Zero operational pharmacy data on this server

### UNKNOWN

- Exact odoo-connect sale-order payload for a new drug order (no successful event to inspect)
- Whether Odoo POS or quotation is used at the window
- Billing-before vs after handing over medication
- How Dispensed attribute is posted from Clinical JS (not called here)

### COMING SOON (Hospital EMR UI only)

- Dispense / partial dispense / return actions
- Inventory and low-stock boards
- Hospital KPI counts
- Prescribe from Doctor
- Medication / order-number hospital search
