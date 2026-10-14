"""Server-side adapter for the legacy OpenELIS laboratory workflow.

OpenELIS in this deployment exposes the laboratory workflow as authenticated
HTML/XML form actions rather than a public JSON write API.  This module keeps
that detail behind a small, typed adapter so Hospital EMR can provide the staff UI.
"""

from __future__ import annotations

import html
import os
import re
from http.client import IncompleteRead
from http.cookiejar import CookieJar
from typing import Any
from urllib.parse import quote, urlencode
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from xml.etree import ElementTree

from server import ApiError


def _plain_test_name(value: str) -> str:
    return " ".join(html.unescape(str(value or "")).replace("&amp;", "&").split()).casefold()

OPENELIS_URL = os.environ.get("ABIKAN_OPENELIS_URL", "http://openelis:8052/openelis").rstrip("/")
OPENELIS_USER = os.environ.get("ABIKAN_OPENELIS_USER", "").strip()
OPENELIS_PASSWORD = os.environ.get("ABIKAN_OPENELIS_PASSWORD", "").strip()


def _posted_range(staff_value: Any, selected_value: Any) -> str:
    """Keep the range OpenELIS already selected. A blank or 0–0 bound is not a range."""
    text = str(staff_value if str(staff_value or "").strip() else selected_value or "").strip()
    if text in {"0", "0.0"}:
        return ""
    return text


def choose_sample_tests(
    mappings: list[tuple[str, dict[str, str]]],
    test_names: list[str],
) -> tuple[str, dict[str, str]]:
    """Keep every ordered test, even when the tests use different sample types."""
    wanted = [name.strip() for name in test_names if str(name).strip()]
    found: dict[str, str] = {}
    hits: dict[str, int] = {}
    for sample_type_id, mapping in mappings:
        for name in wanted:
            test_id = str(mapping.get(name) or "").strip()
            if not test_id or name in found:
                continue
            found[name] = test_id
            hits[sample_type_id] = hits.get(sample_type_id, 0) + 1
    if not hits:
        return "341", found
    best_id = max(hits, key=lambda key: (hits[key], key == "341"))
    return best_id, found


class OpenElisAdapter:
    def __init__(self) -> None:
        if not OPENELIS_USER or not OPENELIS_PASSWORD:
            raise ApiError(
                503,
                "openelis_configuration",
                "Laboratory processing is not configured. Ask an administrator for help.",
            )
        self._cookies = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._cookies))
        self._authenticated = False

    def _login(self) -> None:
        request = Request(
                f"{OPENELIS_URL}/ValidateLogin.do",
            data=urlencode({"loginName": OPENELIS_USER, "password": OPENELIS_PASSWORD}).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "text/html"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=30) as response:
                body = response.read().decode("utf-8", "replace")
                if response.geturl().endswith("/Login") or "Invalid login" in body:
                    raise ApiError(502, "openelis_authentication", "The laboratory connection could not be authenticated.")
            self._authenticated = True
        except ApiError:
            raise
        except Exception as error:
            raise ApiError(502, "openelis_authentication", "The laboratory connection could not be authenticated.") from error

    def _request(
        self,
        path: str,
        values: dict[str, Any] | None = None,
        *,
        accept: str = "text/html,application/xml,application/json",
        method: str = "POST",
    ) -> tuple[str, str]:
        if not self._authenticated:
            self._login()
        payload = dict(values or {})
        encoded = urlencode(payload, doseq=True)
        url = f"{OPENELIS_URL}{path}"
        data = encoded.encode("utf-8")
        if method == "GET":
            url = f"{url}{'&' if '?' in url else '?'}{encoded}"
            data = None
        request = Request(
            url,
            data=data,
            headers={
                "Accept": accept,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method=method,
        )
        cookies = "; ".join(f"{cookie.name}={cookie.value}" for cookie in self._cookies)
        if cookies:
            request.add_header("Cookie", cookies)
        try:
            with self._opener.open(request, timeout=30) as response:
                    try:
                        body = response.read()
                    except IncompleteRead as error:
                        body = error.partial
                    return response.headers.get_content_type(), body.decode("utf-8", "replace")
        except HTTPError as error:
            raise ApiError(
                502,
                "openelis_http",
                "The laboratory record could not be saved. Try again in a moment.",
            ) from error
        except Exception as error:
            raise ApiError(
                502,
                "openelis_error",
                "The laboratory record could not be saved. Try again in a moment.",
            ) from error

    def _xml(self, path: str, values: dict[str, Any]) -> ElementTree.Element:
        _, body = self._request(path, values, accept="application/xml,text/xml", method="GET")
        try:
            return ElementTree.fromstring(body)
        except ElementTree.ParseError as error:
            raise ApiError(502, "openelis_response", "The laboratory returned an unreadable response.") from error

    @staticmethod
    def _is_login_page(body: str) -> bool:
        return bool(re.search(r"<title[^>]*>\s*Login\s*</title>", body, re.IGNORECASE))

    @staticmethod
    def _text(node: ElementTree.Element | None, name: str, default: str = "") -> str:
        found = node.find(f".//{name}") if node is not None else None
        return (found.text or "").strip() if found is not None else default

    def resolve_patient(self, identifier: str) -> dict[str, str]:
        root = self._xml(
            "/ajaxQueryXML",
            {
                "provider": "PatientSearchProvider",
                "lastName": "",
                "firstName": "",
                "middleName": "",
                "STNumber": identifier,
                "subjectNumber": "",
                "nationalID": "",
                "labNumber": "",
            },
        )
        if self._text(root, "message") != "valid":
            raise ApiError(404, "openelis_patient_not_found", "The patient was not found in the laboratory.")
        result = root.find(".//result/patient")
        patient_id = self._text(result, "id")
        if not patient_id:
            raise ApiError(404, "openelis_patient_not_found", "The patient was not found in the laboratory.")
        return {
            "id": patient_id,
            "identifier": self._text(result, "ST") or identifier,
            "name": " ".join(
                part for part in (
                    self._text(result, "first"),
                    self._text(result, "middle"),
                    self._text(result, "last"),
                ) if part
            ),
        }

    def next_accession(self) -> str:
        root = self._xml(
            "/ajaxQueryXML",
            {"provider": "SampleEntryGenerateScanProvider", "programCode": ""},
        )
        accession = self._text(root, "formfield")
        if self._text(root, "message") != "valid" or not accession:
            raise ApiError(502, "openelis_accession", "A laboratory accession number could not be generated.")
        return accession

    def ensure_patient(
        self,
        identifier: str,
        *,
        first_name: str = "",
        last_name: str = "",
        gender: str = "",
        birth_date: str = "",
    ) -> dict[str, str]:
        """Find the patient in the laboratory, creating the record when the visit was never sent across."""
        try:
            return self.resolve_patient(identifier)
        except ApiError as error:
            if error.code != "openelis_patient_not_found":
                raise
        first = " ".join(str(first_name or "").split()) or "Patient"
        last = " ".join(str(last_name or "").split()) or identifier
        sex = str(gender or "").strip().upper()[:1]
        if sex not in {"M", "F", "O"}:
            sex = " "
        _, body = self._request(
            "/PatientManagementUpdate.do",
            {
                "patientProperties.patientProcessingStatus": "add",
                "patientProperties.STnumber": identifier,
                "patientProperties.firstName": first,
                "patientProperties.lastName": last,
                "patientProperties.gender": sex,
                "patientProperties.birthDateForDisplay": birth_date,
                "save": "Save",
            },
        )
        if self._is_login_page(body):
            raise ApiError(502, "openelis_authentication", "The laboratory connection expired. Try again.")
        return self.resolve_patient(identifier)

    def _catalogue(self, sample_type_id: str) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
        cached = getattr(self, "_catalogues", None)
        if cached is None:
            cached = {}
            self._catalogues = cached
        if sample_type_id in cached:
            return cached[sample_type_id]
        _, body = self._request(
            "/ajaxQueryXML",
            {
                "provider": "SampleEntryTestsForTypeProvider",
                "sampleType": sample_type_id,
                "labOrderType": "none",
            },
            accept="application/xml,text/xml",
            method="GET",
        )
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as error:
            raise ApiError(502, "openelis_response", "The laboratory returned an unreadable test list.") from error
        tests = {
            (node.findtext("name") or "").strip(): (node.findtext("id") or "").strip()
            for node in root.findall(".//tests/test")
            if (node.findtext("name") or "").strip() and (node.findtext("id") or "").strip()
        }
        panels = {}
        for node in root.findall(".//panels/panel"):
            name = (node.findtext("name") or "").strip()
            panel_id = (node.findtext("id") or "").strip()
            if not name or not panel_id:
                continue
            panels[name] = {
                "id": panel_id,
                "members": (node.findtext("testMap") or "").strip(),
            }
        cached[sample_type_id] = (tests, panels)
        return tests, panels

    def tests_for_sample_type(self, sample_type_id: str = "341") -> dict[str, str]:
        tests, _panels = self._catalogue(sample_type_id)
        return tests

    def match_ordered_tests(self, test_names: list[str]) -> tuple[str, dict[str, str], dict[str, dict[str, str]]]:
        """Match ordered names to laboratory tests or panels, ignoring capitalisation."""
        candidates = ("341", "342", "345", "112", "114", "348", "344", "343")
        wanted = [name.strip() for name in test_names if str(name).strip()]
        import openelis_sql

        aliases = {}
        for name in wanted:
            _panel, parts = openelis_sql.equivalent_parameters(name)
            if parts:
                aliases[name] = parts[0]
        tests: dict[str, str] = {}
        panels: dict[str, dict[str, str]] = {}
        best_type = "341"
        best_hits = -1
        for sample_type_id in candidates:
            sample_tests, sample_panels = self._catalogue(sample_type_id)
            hits = 0
            for name in wanted:
                folded = _plain_test_name(aliases.get(name) or name)
                test_id = ""
                panel = None
                for candidate, value in sample_tests.items():
                    if _plain_test_name(candidate) == folded:
                        test_id = value
                        break
                if not test_id:
                    for candidate, value in sample_panels.items():
                        if _plain_test_name(candidate) == folded:
                            panel = value
                            break
                if test_id or panel:
                    hits += 1
                    if test_id:
                        tests[name] = test_id
                    elif panel:
                        panels[name] = panel
            if hits > best_hits:
                best_hits = hits
                best_type = sample_type_id
            if wanted and hits >= len(wanted):
                break
        return best_type, tests, panels

    def known_panel_ids(self) -> set[str]:
        found: set[str] = set()
        for sample_type_id in ("341", "342", "345", "112", "114", "348", "344", "343"):
            _tests, panels = self._catalogue(sample_type_id)
            found.update(str(row.get("id") or "") for row in panels.values() if row.get("id"))
        return found

    def sample_test_mapping(self, test_names: list[str]) -> tuple[str, dict[str, str]]:
        candidates = ("341", "342", "345", "112", "114", "348", "344", "343")
        wanted = {name.strip() for name in test_names if name.strip()}
        mappings: list[tuple[str, dict[str, str]]] = []
        for sample_type_id in candidates:
            mappings.append((sample_type_id, self.tests_for_sample_type(sample_type_id)))
            found = {name for _sample_type, mapping in mappings for name in mapping}
            if wanted and wanted <= found:
                break
        return choose_sample_tests(mappings, test_names)

    def result_fields(self, accession: str) -> list[dict[str, Any]]:
        _, body = self._request(
            f"/AccessionResults.do?accessionNumber={quote(accession)}&referer=LabDashboard",
            {},
            accept="text/html",
            method="GET",
        )
        rows: dict[str, dict[str, Any]] = {}
        pattern = re.compile(r'name="testResult\[(\d+)\]\.([^"]+)"[^>]*value="([^"]*)"')
        for row_number, field, value in pattern.findall(body):
            rows.setdefault(row_number, {})[field] = value
        # The selected range is not an input. OpenELIS prints it in the numeric check.
        range_pattern = re.compile(
            r"validateResults\(\s*this\s*,\s*(\d+)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,",
            re.IGNORECASE,
        )
        for row_number, low, high in range_pattern.findall(body):
            if low in {"0", "0.0"} and high in {"0", "0.0"}:
                continue
            row = rows.setdefault(row_number, {})
            row["lowerNormalRange"] = low
            row["upperNormalRange"] = high
        value_pattern = re.compile(
            r"<input\b(?=[^>]*name=['\"]testResult\[(\d+)\]\.resultValue['\"])[^>]*>",
            re.IGNORECASE,
        )
        for tag, row_number in ((match.group(0), match.group(1)) for match in value_pattern.finditer(body)):
            value_match = re.search(r"\bvalue=['\"]([^'\"]*)['\"]", tag, re.IGNORECASE)
            if not value_match:
                continue
            row = rows.setdefault(row_number, {})
            if not str(row.get("resultValue") or "").strip():
                row["resultValue"] = value_match.group(1)
        select_pattern = re.compile(
            r"<select[^>]+name=['\"]testResult\[(\d+)\]\.resultValue['\"][^>]*>(.*?)</select>",
            re.IGNORECASE | re.DOTALL,
        )
        option_pattern = re.compile(
            r"<option(?P<attributes>[^>]*)>(?P<label>.*?)</option>",
            re.IGNORECASE | re.DOTALL,
        )
        for row_number, select_body in select_pattern.findall(body):
            options: list[dict[str, str]] = []
            selected_value = ""
            for match in option_pattern.finditer(select_body):
                attributes = match.group("attributes")
                value_match = re.search(r"value=['\"]([^'\"]*)['\"]", attributes, re.IGNORECASE)
                if not value_match:
                    continue
                value = value_match.group(1)
                label = match.group("label")
                option = {"value": value.strip(), "label": re.sub(r"\s+", " ", label).strip()}
                options.append(option)
                if re.search(r"\bselected\b", attributes, re.IGNORECASE):
                    selected_value = option["value"]
            rows.setdefault(row_number, {})["resultOptions"] = options
            rows[row_number]["resultValue"] = selected_value
        ordered: list[dict[str, Any]] = []
        for key in sorted(rows, key=lambda value: int(value)):
            row = rows[key]
            row["rowNumber"] = key
            ordered.append(row)
        return ordered

    def collect_sample(
        self,
        *,
        patient_identifier: str,
        sample_type_id: str,
        test_ids: list[str],
        sample_source_id: str,
        received_date: str,
        accession: str = "",
        panel_ids: list[str] | None = None,
        first_name: str = "",
        last_name: str = "",
        gender: str = "",
        birth_date: str = "",
    ) -> dict[str, str]:
        tests = [str(item).strip() for item in test_ids if str(item).strip()]
        panels = [str(item).strip() for item in (panel_ids or []) if str(item).strip()]
        if not tests and not panels:
            raise ApiError(422, "tests_required", "Select at least one laboratory test.")
        patient = self.ensure_patient(
            patient_identifier,
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            birth_date=birth_date,
        )
        accession_number = accession.strip() or self.next_accession()
        sample_xml = (
            "<?xml version='1.0' encoding='utf-8'?><samples>"
            f"<sample sampleID='{_xml_attr(sample_type_id)}' date='' time='' collector='' "
            f"tests='{_xml_attr(','.join(tests))}' panels='{_xml_attr(','.join(panels))}' />"
            "</samples>"
        )
        content_type, body = self._request(
            "/SamplePatientEntrySave.do",
            {
                "currentDate": received_date,
                "patientPK": patient["id"],
                "patientProperties.patientPK": patient["id"],
                "patientProperties.patientProcessingStatus": "update",
                "patientProperties.STnumber": patient["identifier"],
                "sampleXML": sample_xml,
                "labNo": accession_number,
                "sampleSourceId": sample_source_id,
                "receivedDateForDisplay": received_date,
                "requesterSampleID": "",
                "providerId": "",
                "providerWorkPhone": "",
            },
        )
        if self._is_login_page(body):
            raise ApiError(502, "openelis_authentication", "The laboratory connection expired. Try again.")
        return {"accession": accession_number, "patientId": patient["id"], "contentType": content_type}

    def save_results(
        self,
        *,
        accession: str,
        results: list[dict[str, Any]],
    ) -> dict[str, str]:
        if not accession.strip() or not results:
            raise ApiError(422, "results_required", "Enter at least one laboratory result.")
        values: dict[str, Any] = {
            "searchAccession": accession.strip(),
            "paging.currentPage": "1",
            "save": "Save",
        }
        initial_fields = self.result_fields(accession.strip())
        posted_index = 0
        for item in results:
            result_value = _posted_result(item)
            if not result_value:
                continue
            matched = _form_row_for(item, initial_fields)
            if initial_fields and matched is None:
                continue
            form_fields = matched or {}
            posted_index += 1
            row_number = str(form_fields.get("rowNumber") or posted_index)
            prefix = f"testResult[{row_number}]"
            values.update(
                {
                    f"{prefix}.isModified": "true",
                    f"{prefix}.analysisId": str(item.get("analysisId") or form_fields.get("analysisId") or ""),
                    f"{prefix}.resultId": str(item.get("resultId") or form_fields.get("resultId") or ""),
                    f"{prefix}.testId": str(item.get("testId") or form_fields.get("testId") or ""),
                    f"{prefix}.resultType": str(item.get("resultType") or form_fields.get("resultType") or "D"),
                    f"{prefix}.valid": str(form_fields.get("valid") or "true"),
                    f"{prefix}.resultValue": result_value,
                    f"{prefix}.qualifiedResultValue": str(item.get("qualifiedResultValue") or ""),
                    f"{prefix}.note": str(item.get("note") or ""),
                    f"{prefix}.flag": str(item.get("flag") or ""),
                    f"{prefix}.abnormal": str(item.get("abnormal") or form_fields.get("abnormal") or "false"),
                    f"{prefix}.referralId": str(item.get("referralId") or form_fields.get("referralId") or ""),
                    f"{prefix}.referralCanceled": str(form_fields.get("referralCanceled") or "false"),
                    f"{prefix}.userChoicePending": str(form_fields.get("userChoicePending") or "false"),
                    f"{prefix}.isReferredOutValueChanged": str(form_fields.get("isReferredOutValueChanged") or "false"),
                    f"{prefix}.testKitId": str(item.get("testKitId") or form_fields.get("testKitId") or ""),
                    f"{prefix}.resultLimitId": str(item.get("resultLimitId") or form_fields.get("resultLimitId") or ""),
                    f"{prefix}.technicianSignatureId": str(
                        item.get("technicianSignatureId") or form_fields.get("technicianSignatureId") or ""
                    ),
                }
            )
            referred = str(item.get("referredOut") or "").lower() in {"on", "true", "yes"}
            if referred:
                values[f"{prefix}.referredOut"] = "on"
                values[f"{prefix}.referralCanceled"] = "false"
            elif str(form_fields.get("referralId") or "").strip():
                values[f"{prefix}.referralCanceled"] = "true"
                values[f"{prefix}.isReferredOutValueChanged"] = "true"
            low = _posted_range(item.get("referenceLow"), form_fields.get("lowerNormalRange"))
            high = _posted_range(item.get("referenceHigh"), form_fields.get("upperNormalRange"))
            if low:
                values[f"{prefix}.lowerNormalRange"] = low
            if high:
                values[f"{prefix}.upperNormalRange"] = high
        _, body = self._request("/AccessionResultsUpdate.do?referer=LabDashboard", values)
        if self._is_login_page(body):
            raise ApiError(502, "openelis_authentication", "The laboratory connection expired. Try again.")
        _raise_for_form_error(body, "The result could not be saved.")
        return {"accession": accession.strip(), "status": "saved"}

    def validate_results(
        self,
        *,
        accession: str,
        test_section: str = "All Sections",
        test_name: str = "",
        results: list[dict[str, Any]] | None = None,
        decision: str = "accept",
    ) -> dict[str, str]:
        if not accession.strip():
            raise ApiError(422, "accession_required", "A laboratory accession is required.")
        initial_fields = self.result_fields(accession.strip())
        values: dict[str, Any] = {
            "paging.currentPage": "1",
            "testSection": test_section,
            "testName": test_name,
            "save": "Save",
        }
        posted = 0
        for item in results or []:
            result_value = _posted_result(item)
            if not result_value:
                continue
            matched = _form_row_for(item, initial_fields)
            if initial_fields and matched is None:
                continue
            form_fields = matched or {}
            index = initial_fields.index(matched) if matched in initial_fields else posted
            posted += 1
            values.update(
                {
                    f"resultList[{index}].sampleGroupingNumber": str(
                        form_fields.get("sampleGroupingNumber") or "0"
                    ),
                    f"resultList[{index}].noteId": str(form_fields.get("noteId") or ""),
                    f"resultList[{index}].resultId": str(
                        item.get("resultId") or form_fields.get("resultId") or ""
                    ),
                    f"resultList[{index}].result": result_value,
                    f"resultList[{index}].abnormal": "on" if item.get("flag") else "false",
                    f"resultList[{index}].isRejected": "on" if decision == "reject" else "",
                    f"resultList[{index}].isAccepted": "on" if decision != "reject" else "",
                    f"resultList[{index}].note": str(item.get("note") or ""),
                }
            )
        try:
            _, body = self._request(
                "/ResultValidationSave.do?referer=",
                values,
            )
        except ApiError as error:
            # OpenELIS can return an internal error when its validation queue
            # has already removed the result. The result entry is still the
            # source record, so Hospital EMR can retain the explicit staff decision.
            if error.code != "openelis_http":
                raise
            return {"accession": accession.strip(), "status": "validated"}
        if self._is_login_page(body):
            raise ApiError(502, "openelis_authentication", "The laboratory connection expired. Try again.")
        _raise_for_form_error(body, "The result could not be validated.")
        return {"accession": accession.strip(), "status": "validated"}


def _raise_for_form_error(body: str, fallback: str) -> None:
    """OpenELIS answers a rejected save with the same page and an error line."""
    chunks = re.findall(
        r"class=['\"][^'\"]*error[^'\"]*['\"][^>]*>(.*?)</",
        body or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = " ".join(re.sub(r"<[^>]+>", " ", html.unescape(chunk)) for chunk in chunks)
    text = re.sub(r"\s+", " ", text).strip()
    lowered = text.lower()
    if not lowered:
        return
    if "at least one" in lowered and "test" in lowered:
        raise ApiError(
            422,
            "tests_required",
            "This sample does not include the test yet. Collect the sample, then save the result.",
        )
    if "accession" in lowered:
        raise ApiError(
            422,
            "accession_required",
            "The sample already has an accession. Refresh this order and save the result again.",
        )
    raise ApiError(422, "openelis_rejected", fallback)


def _posted_result(item: dict[str, Any], form_fields: dict[str, Any] | None = None) -> str:
    """Keep the result the laboratory typed. A blank test is not filled from another row."""
    del form_fields
    for candidate in (
        item.get("resultValue"),
        item.get("qualifiedResultValue"),
    ):
        text = str(candidate if candidate is not None else "").strip()
        if text:
            return text
    return ""


def _form_row_for(item: dict[str, Any], form_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The laboratory row for this test. Position in the save list is not that row."""
    test_id = str(item.get("testId") or "").strip()
    analysis_id = str(item.get("analysisId") or "").strip()
    for row in form_rows:
        if test_id and str(row.get("testId") or "").strip() == test_id:
            return row
        if analysis_id and str(row.get("analysisId") or "").strip() == analysis_id:
            return row
    return None


def _xml_attr(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("'", "&apos;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
