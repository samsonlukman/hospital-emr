"""Pharmacy adds a medicine to a doctor's prescription, or changes one."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pharmacy as dispensary
import pharmacy_rx_links as rx_links
import server as core
from server import ApiError

CONSULTATION_ENCOUNTER = "d34fe3ab-5e07-11ef-8f7c-0242ac120002"
DRUG_OTHER = "d726baf8-5e07-11ef-8f7c-0242ac120002"
FLEXIBLE = "org.openmrs.module.bahmniemrapi.drugorder.dosinginstructions.FlexibleDosingInstructions"

execute = dispensary.execute
as_float = dispensary.as_float
many2one_id = dispensary.many2one_id


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number <= 0:
        return fallback
    return number


def duration_units(value: Any) -> str:
    text = _text(value) or "Days"
    aliases = {
        "day": "Days",
        "days": "Days",
        "day(s)": "Days",
        "week": "Weeks",
        "weeks": "Weeks",
        "week(s)": "Weeks",
        "month": "Months",
        "months": "Months",
        "month(s)": "Months",
        "hour": "Hours",
        "hours": "Hours",
        "minute": "Minutes",
        "minutes": "Minutes",
        "year": "Years",
        "years": "Years",
    }
    return aliases.get(text.lower(), text)


def medicine_fields(body: dict[str, Any]) -> dict[str, Any]:
    drug_uuid = _text(body.get("drugUuid"))
    drug_name = _text(body.get("drugName"))
    if not drug_uuid:
        raise ApiError(422, "medicine_required", "Choose a medicine from the hospital list.")
    quantity = _number(body.get("quantity"), 0)
    if quantity <= 0:
        raise ApiError(422, "quantity_required", "Enter the quantity.")
    dose_units = _text(body.get("doseUnits")) or _text(body.get("form")) or "Unit"
    return {
        "drugUuid": drug_uuid,
        "conceptUuid": _text(body.get("conceptUuid")),
        "drugName": drug_name or "Medication",
        "dose": _number(body.get("dose"), 1),
        "doseUnits": dose_units,
        "route": _text(body.get("route")) or "Oral",
        "frequency": _text(body.get("frequency")) or "Twice a day",
        "duration": _number(body.get("duration"), 5),
        "durationUnits": duration_units(body.get("durationUnits")),
        "quantity": quantity,
        "quantityUnits": _text(body.get("quantityUnits")) or dose_units,
        "instructions": _text(body.get("instructions")),
    }


def drug_order_payload(fields: dict[str, Any], *, care_setting: str, previous_uuid: str = "") -> dict[str, Any]:
    coded = bool(fields.get("drugUuid"))
    instructions = _text(fields.get("instructions"))
    payload: dict[str, Any] = {
        "careSetting": "INPATIENT" if "inpatient" in care_setting.lower() or care_setting == "ipd" else "OUTPATIENT",
        "orderType": "Drug Order",
        "dosingInstructionType": FLEXIBLE,
        "dosingInstructions": {
            "dose": fields["dose"],
            "doseUnits": fields["doseUnits"],
            "route": fields["route"],
            "frequency": fields["frequency"],
            "asNeeded": False,
            "administrationInstructions": json.dumps(
                {"instructions": instructions, "administrationMode": "HOME"}
            )
            if instructions
            else "",
            "quantity": fields["quantity"],
            "quantityUnits": fields["quantityUnits"],
            "numberOfRefills": 0,
        },
        "duration": fields["duration"],
        "durationUnits": fields["durationUnits"],
    }
    if coded:
        payload["drug"] = {"uuid": fields["drugUuid"]}
        if fields.get("conceptUuid"):
            payload["concept"] = {"uuid": fields["conceptUuid"]}
    else:
        payload["drugNonCoded"] = fields.get("drugName") or "Medication"
        payload["concept"] = {"uuid": DRUG_OTHER}
    if previous_uuid:
        payload["action"] = "REVISE"
        payload["previousOrderUuid"] = previous_uuid
        payload["previousOrder"] = {"uuid": previous_uuid}
    return payload


def _interpret_save_failure(detail: str) -> ApiError | None:
    lowered = detail.lower()
    if "duration" in lowered and "unit" in lowered:
        return ApiError(
            409,
            "duration_units",
            "Choose how long the medicine is taken from the list, then save again.",
        )
    if "more than one" in lowered or "order.cannot.have.more.than.one" in lowered:
        return ApiError(
            409,
            "already_prescribed",
            "This medicine is already on the prescription. Change that line instead.",
        )
    return None


def _read_http_error(error: HTTPError) -> str:
    try:
        return error.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _post_with_cookie(cookie: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        f"{core.OPENMRS_URL}/openmrs/ws/rest/v1/bahmnicore/bahmniencounter",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cookie": cookie,
        },
        method="POST",
    )
    with urlopen(request, timeout=40) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def _post_encounter(cookie: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Pharmacists cannot look up dose units, so the hospital identity writes the prescription."""
    try:
        return core.openmrs_service_post(
            "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter",
            payload,
        )
    except ApiError as service_error:
        try:
            return _post_with_cookie(cookie, payload)
        except HTTPError as error:
            detail = _read_http_error(error)
            understood = _interpret_save_failure(detail) or _interpret_save_failure(service_error.message)
            if understood:
                raise understood from error
            if "dose unit" in detail.lower() or "quantity unit" in detail.lower():
                raise ApiError(
                    409,
                    "dose_units",
                    "Choose the dose unit from the list, then save again.",
                ) from error
            raise ApiError(
                502,
                "prescription_save_failed",
                "The medicine could not be added to this prescription. Try again.",
            ) from service_error
    except HTTPError as error:
        detail = _read_http_error(error)
        print(f"prescription save failed: {detail[:500]}", flush=True)
        understood = _interpret_save_failure(detail)
        if understood and error.code not in {401, 403, 500}:
            raise understood from error
        if error.code == 401:
            raise ApiError(401, "unauthenticated", "Sign in required.") from error
        try:
            return core.openmrs_service_post(
                "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter",
                payload,
            )
        except ApiError as service_error:
            if understood:
                raise understood from service_error
            text = f"{service_error.message} {detail}".lower()
            mapped = _interpret_save_failure(text)
            if mapped:
                raise mapped from service_error
            raise ApiError(
                502,
                "prescription_save_failed",
                "The medicine could not be added to this prescription. Try again.",
            ) from service_error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        try:
            return core.openmrs_service_post(
                "/openmrs/ws/rest/v1/bahmnicore/bahmniencounter",
                payload,
            )
        except ApiError as service_error:
            raise ApiError(
                502,
                "prescription_save_failed",
                "The medicine could not be added to this prescription. Try again.",
            ) from service_error


def _as_utc(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = _text(value).replace("Z", "+00:00")
    if text.endswith("+0000"):
        text = text[:-5] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_openmrs(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def encounter_moment(
    now: datetime,
    started: datetime | None,
    stopped: datetime | None,
    original: datetime | None,
) -> datetime:
    """Keep a pharmacy addition inside the visit, including after the visit has ended."""
    chosen = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    chosen = chosen.astimezone(timezone.utc)
    if started and chosen < started:
        chosen = started
    if stopped and chosen > stopped:
        if original and (started is None or original >= started) and original <= stopped:
            chosen = original
        else:
            chosen = stopped - timedelta(seconds=1)
    if stopped and chosen >= stopped:
        chosen = stopped - timedelta(seconds=1)
    if started and chosen < started:
        chosen = started
    return chosen


def _visit_context(encounter_uuid: str) -> dict[str, Any]:
    import openmrs_sql

    try:
        rows = openmrs_sql.fetch_all(
            """
            SELECT v.uuid, IFNULL(vt.name, 'OPD'), IFNULL(l.uuid, ''),
                   e.encounter_datetime, v.date_started, v.date_stopped
            FROM encounter e
            JOIN visit v ON v.visit_id = e.visit_id
            LEFT JOIN visit_type vt ON vt.visit_type_id = v.visit_type_id
            LEFT JOIN location l ON l.location_id = e.location_id
            WHERE e.uuid = %s
            LIMIT 1
            """,
            (encounter_uuid,),
        )
    except openmrs_sql.OpenmrsSqlError as error:
        raise ApiError(
            502,
            "prescription_save_failed",
            "The medicine could not be added to this prescription. Try again.",
        ) from error
    if not rows:
        raise ApiError(409, "visit_required", "This prescription is not on a visit.")
    return {
        "visitUuid": str(rows[0][0] or ""),
        "visitType": str(rows[0][1] or "OPD"),
        "locationUuid": str(rows[0][2] or ""),
        "encounterDatetime": _as_utc(rows[0][3]),
        "started": _as_utc(rows[0][4]),
        "stopped": _as_utc(rows[0][5]),
    }


def _orderer_uuid(order_uuid: str) -> str:
    import openmrs_sql

    try:
        rows = openmrs_sql.fetch_all(
            """
            SELECT pr.uuid
            FROM orders o
            JOIN provider pr ON pr.provider_id = o.orderer
            WHERE o.uuid = %s
            LIMIT 1
            """,
            (order_uuid,),
        )
    except openmrs_sql.OpenmrsSqlError:
        return ""
    return str(rows[0][0] or "") if rows else ""


def _provider_uuid(cookie: str, fallback_order_uuid: str) -> str:
    try:
        user = dispensary.load_openmrs_user(cookie)
        user_uuid = _text(user.get("uuid"))
        if user_uuid:
            payload = dispensary._openmrs_json(
                f"/openmrs/ws/rest/v1/provider?user={user_uuid}&v=custom:(uuid,retired)",
                cookie,
            )
            for row in (payload or {}).get("results") or []:
                if isinstance(row, dict) and row.get("uuid") and not row.get("retired"):
                    return str(row["uuid"])
    except Exception:
        pass
    provider = _orderer_uuid(fallback_order_uuid)
    if not provider:
        raise ApiError(409, "provider_missing", "This prescription could not be saved. Try again.")
    return provider


def _known_order_uuids(patient_uuid: str) -> list[str]:
    import openmrs_sql

    rows = openmrs_sql.fetch_all(
        """
        SELECT o.uuid
        FROM orders o
        JOIN person per ON per.person_id = o.patient_id
        JOIN order_type ot ON ot.order_type_id = o.order_type_id
        WHERE per.uuid = %s AND ot.name = %s AND o.voided = 0
        ORDER BY o.order_id DESC
        """,
        (patient_uuid, "Drug Order"),
    )
    return [str(row[0]) for row in rows if row and row[0]]


_DOSING_CONFIG: dict[str, Any] = {"loaded": 0.0, "payload": {}}


def _option_names(rows: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(rows, list):
        return names
    for row in rows:
        if isinstance(row, dict):
            name = _text(row.get("name") or row.get("display"))
        else:
            name = _text(row)
        if name and name not in names:
            names.append(name)
    return names


def _match_dosing_name(value: str, options: list[str]) -> str:
    """Use the hospital's exact dosing name, including Tablet(s) and Day(s)."""
    text = _text(value)
    if not text or not options:
        return text
    if text in options:
        return text
    folded = text.casefold()
    for name in options:
        if name.casefold() == folded:
            return name
    stem = folded.replace("(s)", "").rstrip("s").strip()
    if len(stem) >= 2:
        for name in options:
            other = name.casefold().replace("(s)", "").rstrip("s").strip()
            if other == stem:
                return name
    return text


def _dosing_config(cookie: str) -> dict[str, Any]:
    now = time.time()
    cached = _DOSING_CONFIG.get("payload")
    if isinstance(cached, dict) and cached and now - float(_DOSING_CONFIG.get("loaded") or 0) < 300:
        return cached
    path = "/openmrs/ws/rest/v1/bahmnicore/config/drugOrders"
    payload: dict[str, Any] = {}
    try:
        loaded = dispensary._openmrs_json(path, cookie)
        if isinstance(loaded, dict):
            payload = loaded
    except Exception:
        payload = {}
    if not payload:
        try:
            loaded = core.openmrs_service_get(path)
            if isinstance(loaded, dict):
                payload = loaded
        except ApiError:
            payload = {}
    if payload:
        _DOSING_CONFIG["payload"] = payload
        _DOSING_CONFIG["loaded"] = now
    return payload


def _known_option(value: str, options: list[str], fallbacks: tuple[str, ...]) -> str:
    """Keep a dosing name the hospital recognises. A dosage form such as Consumables is not a dose unit."""
    matched = _match_dosing_name(value, options)
    if matched in options:
        return matched
    for fallback in fallbacks:
        alt = _match_dosing_name(fallback, options)
        if alt in options:
            return alt
    return options[0] if options else value


def _align_dosing(cookie: str, fields: dict[str, Any]) -> None:
    config = _dosing_config(cookie)
    pairs = (
        ("doseUnits", ("doseUnits",), ("Unit", "Tablet", "ml")),
        ("route", ("route", "routes"), ("Oral",)),
        ("frequency", ("frequency", "frequencies"), ("Once a day", "Twice a day")),
        ("durationUnits", ("durationUnits",), ("Days",)),
        ("quantityUnits", ("dispensingUnits", "quantityUnits", "doseUnits"), ("Unit", "Tablet", "ml")),
    )
    for field, keys, fallbacks in pairs:
        options: list[str] = []
        for key in keys:
            options = _option_names(config.get(key))
            if options:
                break
        if options:
            fields[field] = _known_option(_text(fields.get(field)), options, fallbacks)


def _prescription_batch(clinical: dict[str, Any]) -> str:
    linked = rx_links.group_for(_text(clinical.get("uuid")))
    if "|" in linked:
        return linked
    return dispensary.prescription_batch_key(
        _text(clinical.get("encounterUuid")),
        _text(clinical.get("ordered")),
    ) or _text(clinical.get("encounterUuid")) or _text(clinical.get("uuid"))


def _save_order(
    cookie: str,
    clinical: dict[str, Any],
    fields: dict[str, Any],
    *,
    previous_uuid: str = "",
) -> str:
    patient_uuid = _text(clinical.get("patientUuid"))
    encounter_uuid = _text(clinical.get("encounterUuid"))
    anchor = rx_links.group_for(_text(clinical.get("uuid"))) or encounter_uuid
    context = _visit_context(anchor or encounter_uuid)
    if not context["locationUuid"]:
        import openmrs_sql

        fallback = openmrs_sql.fetch_all(
            "SELECT uuid FROM location WHERE retired = 0 ORDER BY location_id LIMIT 1"
        )
        if fallback and fallback[0] and fallback[0][0]:
            context["locationUuid"] = str(fallback[0][0])
    if not context["visitUuid"] or not context["locationUuid"]:
        raise ApiError(409, "visit_required", "This prescription could not be saved. Try again.")
    _align_dosing(cookie, fields)
    _fill_concept(fields)
    before = set(_known_order_uuids(patient_uuid))
    care = _text(clinical.get("careSetting"))
    encounter = {
        "patientUuid": patient_uuid,
        "visitUuid": context["visitUuid"],
        "visitType": context["visitType"] or "OPD",
        "encounterTypeUuid": CONSULTATION_ENCOUNTER,
        "encounterDateTime": _format_openmrs(
            encounter_moment(
                datetime.now(timezone.utc),
                context.get("started"),
                context.get("stopped"),
                context.get("encounterDatetime"),
            )
        ),
        "locationUuid": context["locationUuid"],
        "providers": [{"uuid": _provider_uuid(cookie, _text(clinical.get("uuid")))}],
        "observations": [],
        "bahmniDiagnoses": [],
        "orders": [],
        "drugOrders": [drug_order_payload(fields, care_setting=care, previous_uuid=previous_uuid)],
    }
    if anchor:
        encounter["encounterUuid"] = anchor
    encounter["drugOrders"][0]["scheduledDate"] = encounter["encounterDateTime"]
    saved = _post_encounter(cookie, encounter)
    found = _order_uuid_from_save(saved)
    if not found or found in before:
        created = [uuid for uuid in _known_order_uuids(patient_uuid) if uuid not in before]
        if not created:
            raise ApiError(502, "prescription_save_failed", "The prescription could not be saved. Try again.")
        found = created[0]
    _keep_order_on_visit(found, context["visitUuid"])
    return found


def _keep_order_on_visit(order_uuid: str, visit_uuid: str) -> None:
    """Keep a saved medicine on the visit that was already open."""
    import openmrs_sql

    wanted = _text(visit_uuid)
    order = _text(order_uuid)
    if not wanted or not order:
        return
    try:
        placed = openmrs_sql.fetch_one(
            """
            SELECT e.encounter_id, v.visit_id, v.uuid
            FROM orders o
            JOIN encounter e ON e.encounter_id = o.encounter_id
            JOIN visit v ON v.visit_id = e.visit_id
            WHERE o.uuid = %s
            """,
            (order,),
        )
        intended = openmrs_sql.fetch_one(
            "SELECT visit_id FROM visit WHERE uuid = %s AND voided = 0",
            (wanted,),
        )
    except openmrs_sql.OpenmrsSqlError:
        return
    if not placed or not intended or str(placed[2]) == wanted:
        return
    stray_visit_id = int(placed[1])
    openmrs_sql.execute(
        "UPDATE encounter SET visit_id = %s WHERE encounter_id = %s",
        (int(intended[0]), int(placed[0])),
    )
    if openmrs_sql.fetch_int(
        "SELECT COUNT(*) FROM encounter WHERE visit_id = %s AND voided = 0",
        (stray_visit_id,),
    ):
        return
    actor = openmrs_sql.fetch_int(
        "SELECT user_id FROM users WHERE username = 'abikan_openmrs' LIMIT 1"
    ) or openmrs_sql.fetch_int("SELECT MIN(user_id) FROM users")
    openmrs_sql.execute(
        """
        UPDATE visit
        SET voided = 1,
            date_voided = UTC_TIMESTAMP(),
            voided_by = %s,
            void_reason = %s
        WHERE visit_id = %s AND voided = 0
        """,
        (actor, "Extra visit opened when a medicine was saved.", stray_visit_id),
    )


def _fill_concept(fields: dict[str, Any]) -> None:
    if fields.get("conceptUuid"):
        return
    if not fields.get("drugUuid"):
        raise ApiError(422, "medicine_required", "Choose a medicine from the hospital list.")
    import openmrs_sql

    rows: list[Any] = []
    try:
        rows = openmrs_sql.fetch_all(
            """
            SELECT c.uuid
            FROM drug d
            JOIN concept c ON c.concept_id = d.concept_id
            WHERE d.uuid = %s
            LIMIT 1
            """,
            (fields["drugUuid"],),
        )
    except Exception:
        rows = []
    if rows and rows[0] and rows[0][0]:
        fields["conceptUuid"] = str(rows[0][0])
        return
    try:
        drug = core.openmrs_service_get(
            f"/openmrs/ws/rest/v1/drug/{quote(str(fields['drugUuid']))}?v=custom:(uuid,concept:(uuid))"
        )
    except ApiError:
        drug = {}
    concept = drug.get("concept") if isinstance(drug, dict) else None
    if isinstance(concept, dict) and concept.get("uuid"):
        fields["conceptUuid"] = str(concept["uuid"])
        return
    raise ApiError(409, "medicine_required", "Choose a medicine from the hospital list.")


def _order_uuid_from_save(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("drugOrders", "orders"):
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and _text(row.get("uuid")):
                return _text(row.get("uuid"))
    return ""


def _line_values(odoo: dispensary.OdooReader, clinical: dict[str, Any], fields: dict[str, Any], patient_uuid: str) -> dict[str, Any]:
    product = dispensary.find_pharmacy_products(odoo, [fields["drugUuid"]]).get(fields["drugUuid"])
    if not product or not product.get("id"):
        raise ApiError(409, "medicine_required", "Choose a medicine from the hospital list.")
    price = as_float(product.get("list_price"))
    if price <= 0:
        raise ApiError(409, "missing_price", "This medicine has no selling price yet.")
    discount = 0
    name_parts = [str(product.get("name") or fields["drugName"])]
    for part in (fields["dose"], fields["doseUnits"], fields["frequency"], f"{fields['duration']} {fields['durationUnits']}"):
        text = _text(part)
        if text:
            name_parts.append(text)
    return {
        "product_id": int(product["id"]),
        "name": " · ".join(name_parts),
        "product_uom_qty": fields["quantity"],
        "price_unit": price,
        "discount": discount,
        "tax_id": [(6, 0, [])],
        "external_order_id": _text(clinical.get("uuid")),
        "external_id": patient_uuid,
    }


def _sale_for_group(
    odoo: dispensary.OdooReader,
    anchor: str,
    extras: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    wanted: list[str] = []
    for order_uuid in (anchor, *rx_links.members(anchor), *extras):
        text = _text(order_uuid)
        if text and text not in wanted:
            wanted.append(text)
    fallback: dict[str, Any] | None = None
    for order_uuid in wanted:
        matched = dispensary.sale_line_for_order(odoo, order_uuid)
        if not matched:
            continue
        state = str(matched[1].get("state") or "")
        if state in {"cancel", "cancelled"}:
            continue
        if state == "draft":
            return matched[1]
        fallback = matched[1]
    return fallback


def _create_sale(
    odoo: dispensary.OdooReader,
    cookie: str,
    patient_uuid: str,
    clinical: dict[str, Any],
    fields: dict[str, Any],
    anchor: str,
) -> None:
    import pharmacy_sale

    patient = core.load_openmrs_patient(patient_uuid, cookie)
    partner = dispensary.billing_partner(odoo, patient)
    if not partner:
        raise ApiError(409, "account_not_found", "This patient has no bill account yet.")
    shop = pharmacy_sale.find_pharmacy_shop(odoo)
    line = _line_values(odoo, clinical, fields, patient_uuid)
    care = "ipd" if "inpatient" in _text(clinical.get("careSetting")).lower() else "opd"
    sale_id = int(
        execute(
            odoo,
            "sale.order",
            "create",
            [
                {
                    "partner_id": int(partner["id"]),
                    "shop_id": int(shop["id"]),
                    "warehouse_id": many2one_id(shop.get("warehouse_id")) or 1,
                    "pricelist_id": many2one_id(shop.get("pricelist_id")) or 1,
                    "payment_term_id": many2one_id(shop.get("payment_default_id")) or 1,
                    "origin": anchor or patient_uuid,
                    "care_setting": care,
                    "order_line": [(0, 0, line)],
                }
            ],
        )
    )
    sale_rows = odoo.read(
        "sale.order",
        [sale_id],
        ["name", "state", "partner_id", "invoice_ids", "origin", "shop_id"],
    )
    if not sale_rows:
        raise ApiError(502, "odoo_charge_failed", "The pharmacy bill could not be created. Refresh and try again.")
    dispensary.ensure_pharmacy_invoice(odoo, sale_rows[0])


def _require_billable(
    odoo: dispensary.OdooReader,
    cookie: str,
    patient_uuid: str,
    fields: dict[str, Any],
) -> None:
    product = dispensary.find_pharmacy_products(odoo, [fields["drugUuid"]]).get(fields["drugUuid"])
    if not product or not product.get("id"):
        raise ApiError(409, "medicine_required", "Choose a medicine from the hospital list.")
    if as_float(product.get("list_price")) <= 0:
        raise ApiError(409, "missing_price", "This medicine has no selling price yet.")
    patient = core.load_openmrs_patient(patient_uuid, cookie)
    if not dispensary.billing_partner(odoo, patient):
        raise ApiError(409, "account_not_found", "This patient has no bill account yet.")


def _attach_bill(
    odoo: dispensary.OdooReader,
    cookie: str,
    clinical: dict[str, Any],
    fields: dict[str, Any],
    anchor: str,
    extras: tuple[str, ...] = (),
) -> None:
    patient_uuid = _text(clinical.get("patientUuid"))
    line = _line_values(odoo, clinical, fields, patient_uuid)
    sale = _sale_for_group(odoo, anchor, extras)
    if sale and str(sale.get("state") or "") == "draft":
        execute(odoo, "sale.order", "write", [[int(sale["id"])], {"order_line": [(0, 0, line)]}])
        return
    _create_sale(odoo, cookie, patient_uuid, clinical, fields, anchor)


def _assert_changeable(odoo: dispensary.OdooReader, order_uuid: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    matched = dispensary.sale_line_for_order(odoo, order_uuid)
    if not matched:
        return None
    line, sale = matched
    if as_float(line.get("qty_delivered")) > 0.0001:
        raise ApiError(409, "already_dispensed", "This medicine has already been handed over and cannot be changed.")
    invoice = dispensary.related_invoice(odoo, sale)
    payment = _text((invoice or {}).get("payment_state")).lower()
    residual = as_float((invoice or {}).get("amount_residual"))
    total = as_float((invoice or {}).get("amount_total"))
    paid = payment in {"paid", "in_payment", "partial"} or (
        invoice is not None and total > residual + 0.009 and payment not in {"", "not_paid"}
    )
    if paid:
        raise ApiError(409, "already_paid", "This medicine has been paid and cannot be changed.")
    return matched


def _rewrite_draft_line(
    odoo: dispensary.OdooReader,
    matched: tuple[dict[str, Any], dict[str, Any]] | None,
    clinical: dict[str, Any],
    fields: dict[str, Any],
) -> bool:
    if not matched:
        return False
    line, sale = matched
    if str(sale.get("state") or "") != "draft":
        return False
    values = _line_values(odoo, clinical, fields, _text(clinical.get("patientUuid")))
    values.pop("tax_id", None)
    execute(odoo, "sale.order.line", "write", [[int(line["id"])], values])
    return True


def add_medicine(order_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    import sqlite3
    import xmlrpc.client

    dispensary.require_pharmacist(cookie)
    fields = medicine_fields(body if isinstance(body, dict) else {})
    clinical = dispensary.load_openmrs_order(order_uuid, cookie)
    if clinical.get("stopped"):
        raise ApiError(409, "prescription_stopped", "This prescription has been stopped.")
    anchor = rx_links.group_for(order_uuid) or _text(clinical.get("encounterUuid")) or order_uuid
    batch = _prescription_batch(clinical)
    odoo = dispensary.odoo_reader()
    _require_billable(odoo, cookie, _text(clinical.get("patientUuid")), fields)
    try:
        new_uuid = _save_order(cookie, clinical, fields)
        saved = dispensary.load_openmrs_order(new_uuid, cookie)
        saved["uuid"] = saved.get("uuid") or new_uuid
        rx_links.remember(new_uuid, batch)
        _attach_bill(odoo, cookie, saved, fields, anchor, (order_uuid,))
        return dispensary.assemble_prescription_group(order_uuid, cookie)
    except xmlrpc.client.Fault as error:
        raise ApiError(
            502,
            "bill_not_created",
            "The medicine could not be added to the bill. Try again.",
        ) from error
    except sqlite3.Error as error:
        raise ApiError(
            502,
            "prescription_save_failed",
            "The medicine could not be added to this prescription. Try again.",
        ) from error


def change_medicine(order_uuid: str, body: dict[str, Any], cookie: str) -> dict[str, Any]:
    dispensary.require_pharmacist(cookie)
    fields = medicine_fields(body if isinstance(body, dict) else {})
    requested = order_uuid
    order_uuid = rx_links.resolve(order_uuid) or order_uuid
    clinical = dispensary.load_openmrs_order(order_uuid, cookie)
    if clinical.get("stopped"):
        raise ApiError(409, "prescription_stopped", "This medicine has been stopped and cannot be changed.")
    import pharmacy_unlisted as unlisted

    if unlisted.not_in_pharmacy_order(clinical):
        raise ApiError(409, "not_in_pharmacy", "This medicine is not in the hospital list and cannot be changed here.")
    odoo = dispensary.odoo_reader()
    matched = _assert_changeable(odoo, order_uuid)
    anchor = rx_links.group_for(order_uuid) or _text(clinical.get("encounterUuid")) or order_uuid
    batch = _prescription_batch(clinical)
    _require_billable(odoo, cookie, _text(clinical.get("patientUuid")), fields)
    new_uuid = _save_order(cookie, clinical, fields, previous_uuid=order_uuid)
    saved = dispensary.load_openmrs_order(new_uuid, cookie)
    saved["uuid"] = saved.get("uuid") or new_uuid
    rx_links.replace(order_uuid, new_uuid, batch)
    if not _rewrite_draft_line(odoo, matched, saved, fields):
        _attach_bill(odoo, cookie, saved, fields, anchor, (order_uuid,))
        if matched:
            import pharmacy_prescription_ops as rx_ops

            try:
                rx_ops._cancel_odoo_sale_for_order(odoo, order_uuid)
            except ApiError as error:
                raise ApiError(
                    409,
                    "bill_not_updated",
                    "The medicine was changed, but the previous charge is still on the bill. Ask accounts to remove the old charge.",
                ) from error
    return dispensary.assemble_prescription_group(requested, cookie)
