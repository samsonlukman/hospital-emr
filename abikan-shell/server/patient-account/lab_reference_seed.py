"""Proposed reference limits from published sources.

Every numeric interval below was read from the cited page on 12 October 2026.
Nothing here is approved for reporting. A laboratory scientist has to review
the method, the units, and this hospital's population before a row can be used.

Mayo Clinic Laboratories states that its catalog values are valid only on the
day of printing, and that the intervals are Mayo-derived unless the page says
otherwise. They are not this hospital's analyser ranges.

The WHO rows are anaemia cutoffs, not reference intervals. They are stored so
the difference is visible, and result entry does not use them.
"""

from __future__ import annotations

import re
from typing import Any

ACCESSED = "2026-10-12"

MAYO_LIMIT = (
    "Published for the method and specimen on the Mayo Clinic Laboratories page. "
    "It has not been verified for this hospital's population or analyser. "
    "The catalog says the values are valid only on the day of printing; this copy was read on 12 October 2026. "
    "Do not approve it until the laboratory has checked it for the local method. "
    "CLSI EP28-A3c is the guideline for that check; it is not the source of these numbers."
)

ADULT_LIMIT = (
    " The catalog prints this row as Adults after a 15–17 year row and does not give a numeric lower age. "
    "It is stored as 18 years and older so it does not overlap 15–17 years. Confirm that cutoff before approval."
)

WHO_LIMIT = (
    "This is a sea-level cutoff for defining anaemia, from the WHO 2024 guideline, Table 2. "
    "It is not a reference interval and result entry does not use it. "
    "The cutoffs came from 5th percentiles in higher-income settings; lower-income data were not in the pooled analysis. "
    "No altitude or smoking adjustment is applied. "
    "Pregnancy is not read from the hospital record, so a pregnancy cutoff is never chosen automatically."
)

CBC_METHOD = (
    "Sysmex XN-9000: hydrodynamic focusing, semiconductor-laser flow cytometry, "
    "and sodium lauryl sulfate haemoglobin. Instruction manual cited by Mayo Clinic Laboratories, November 2015."
)
CBC_SOURCE = {
    "source_title": "Complete Blood Cell Count (CBC) with Differential, Blood",
    "source_publisher": "Mayo Clinic Laboratories",
    "source_version": "Test catalog CBC, test 9109, read 12 October 2026",
    "source_url": "https://www.mayocliniclabs.com/test-catalog/overview/9109",
    "source_accessed": ACCESSED,
    "method": CBC_METHOD,
    "specimen": "Whole blood EDTA",
}


def _bounds(
    min_value: int | None,
    min_unit: str,
    min_inclusive: bool,
    max_value: int | None,
    max_unit: str,
    max_inclusive: bool,
    text: str,
) -> dict[str, Any]:
    return {
        "age_min_value": min_value,
        "age_min_unit": min_unit,
        "age_min_inclusive": min_inclusive,
        "age_max_value": max_value,
        "age_max_unit": max_unit,
        "age_max_inclusive": max_inclusive,
        "age_text": text,
    }


def parse_age(phrase: str) -> dict[str, Any]:
    """Turn a catalog age phrase into inclusive completed-age bounds.

    "4 weeks" as an upper bound means completed weeks of 4, which runs through
    the day before 5 weeks. A following "5 weeks" row starts the next day.
    "Adults" after a 15–17 year row is stored as 18 years and older.
    """
    text = " ".join(phrase.split())
    folded = text.casefold()
    if folded == "adults":
        return _bounds(18, "years", True, None, "", False, text)
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)\s+(day|days|week|weeks|month|months|year|years)", folded)
    if match:
        unit = _plural(match.group(3))
        return _bounds(int(match.group(1)), unit, True, int(match.group(2)), unit, True, text)
    match = re.fullmatch(
        r"(\d+)\s+(day|days|week|weeks|month|months|year|years)\s*-\s*(\d+)\s+(day|days|week|weeks|month|months|year|years)",
        folded,
    )
    if match:
        return _bounds(
            int(match.group(1)),
            _plural(match.group(2)),
            True,
            int(match.group(3)),
            _plural(match.group(4)),
            True,
            text,
        )
    match = re.fullmatch(r"(\d+)\s+(day|days|week|weeks|month|months|year|years)", folded)
    if match:
        unit = _plural(match.group(2))
        value = int(match.group(1))
        return _bounds(value, unit, True, value, unit, True, text)
    raise ValueError(f"unparsed age phrase: {phrase}")


def _plural(unit: str) -> str:
    word = unit.casefold()
    if word.endswith("s"):
        return word
    return f"{word}s"


def _slug(*parts: str) -> str:
    text = "-".join(parts)
    return "seed:" + re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")


def _row(
    *,
    test_name: str,
    aliases: list[str],
    sex: str,
    low: str,
    high: str,
    unit: str,
    age: dict[str, Any] | None,
    specimen: str,
    method: str,
    source: dict[str, str],
    limitations: str,
    purpose: str = "reference_interval",
    result_type: str = "numeric",
    condition: str = "",
    low_inclusive: bool = True,
    high_inclusive: bool = True,
    descriptive: str = "",
    conflict_note: str = "",
) -> dict[str, Any]:
    age = age or _bounds(None, "", False, None, "", False, "")
    return {
        "id": _slug(test_name, sex or "any", condition or "none", age.get("age_text") or "any-age", purpose),
        "test_name": test_name,
        "aliases": aliases,
        "specimen": specimen,
        "result_type": result_type,
        "purpose": purpose,
        "low": low,
        "high": high,
        "low_inclusive": low_inclusive,
        "high_inclusive": high_inclusive,
        "unit": unit,
        **age,
        "sex": sex or "any",
        "condition": condition,
        "method": method,
        "expected_values": [],
        "descriptive_text": descriptive,
        "source_title": source.get("source_title", ""),
        "source_publisher": source.get("source_publisher", ""),
        "source_version": source.get("source_version", ""),
        "source_url": source.get("source_url", ""),
        "source_accessed": source.get("source_accessed", ""),
        "limitations": limitations,
        "conflict_group": "",
        "conflict_note": conflict_note,
    }


def _cbc(test_name: str, aliases: list[str], unit: str, sex: str, lines: str) -> list[dict[str, Any]]:
    rows = []
    for raw in lines.strip().splitlines():
        phrase, low, high = [part.strip() for part in raw.split("|")]
        age = parse_age(phrase)
        limit = MAYO_LIMIT + (ADULT_LIMIT if phrase.strip().casefold() == "adults" else "")
        rows.append(
            _row(
                test_name=test_name,
                aliases=aliases,
                sex=sex,
                low=low,
                high=high,
                unit=unit,
                age=age,
                specimen=CBC_SOURCE["specimen"],
                method=CBC_SOURCE["method"],
                source=CBC_SOURCE,
                limitations=limit,
            )
        )
    return rows


def _chemistry_rows() -> list[dict[str, Any]]:
    electrolyte = {
        "source_title": "Electrolyte Panel, Serum",
        "source_publisher": "Mayo Clinic Laboratories",
        "source_version": "Test catalog ELPSR, test 113632, read 12 October 2026",
        "source_url": "https://www.mayocliniclabs.com/test-catalog/overview/113632",
        "source_accessed": ACCESSED,
    }
    electrolyte_method = {
        "sodium": "Indirect potentiometry. Roche ISE indirect Na-K-Cl for Gen 2, package insert 05/2024, as cited by Mayo Clinic Laboratories.",
        "potassium": "Indirect potentiometry. Roche ISE indirect Na-K-Cl for Gen 2, package insert 05/2024, as cited by Mayo Clinic Laboratories.",
        "chloride": "Indirect potentiometry. Roche ISE indirect Na-K-Cl for Gen 2, package insert 05/2024, as cited by Mayo Clinic Laboratories.",
        "bicarbonate": "Photometric. Roche bicarbonate reagent, package insert 02/2023, as cited by Mayo Clinic Laboratories.",
    }
    at_least_one_year = _bounds(1, "years", True, None, "", False, ">=1 year")
    rows = [
        _row(
            test_name="Sodium",
            aliases=["Serum sodium", "Na"],
            sex="any",
            low="135",
            high="145",
            unit="mmol/L",
            age=at_least_one_year,
            specimen="Serum",
            method=electrolyte_method["sodium"],
            source=electrolyte,
            limitations=MAYO_LIMIT + " No interval is published for patients younger than 1 year, so none is stored.",
        ),
        _row(
            test_name="Potassium",
            aliases=["Serum potassium", "Serum Potassium", "K"],
            sex="any",
            low="3.6",
            high="5.2",
            unit="mmol/L",
            age=at_least_one_year,
            specimen="Serum",
            method=electrolyte_method["potassium"],
            source=electrolyte,
            limitations=MAYO_LIMIT + " No interval is published for patients younger than 1 year, so none is stored.",
        ),
        _row(
            test_name="Chloride",
            aliases=["Serum chloride", "Cl"],
            sex="any",
            low="102",
            high="112",
            unit="mmol/L",
            age=_bounds(1, "years", True, 17, "years", True, "1-17 years"),
            specimen="Serum",
            method=electrolyte_method["chloride"],
            source=electrolyte,
            limitations=MAYO_LIMIT + " No interval is published for patients younger than 1 year, so none is stored.",
        ),
        _row(
            test_name="Chloride",
            aliases=["Serum chloride", "Cl"],
            sex="any",
            low="98",
            high="107",
            unit="mmol/L",
            age=_bounds(18, "years", True, None, "", False, ">=18 years"),
            specimen="Serum",
            method=electrolyte_method["chloride"],
            source=electrolyte,
            limitations=MAYO_LIMIT,
        ),
    ]
    bicarbonate_source_note = (
        MAYO_LIMIT
        + " The order name Serum carbon dioxide is matched to this bicarbonate interval. "
        + "Confirm that the local method is serum bicarbonate before approval. "
        + "No interval is published for patients younger than 1 year."
    )
    male_bicarbonate = [
        ("1-2 years", _bounds(1, "years", True, 2, "years", True, "1-2 years"), "17", "25"),
        ("3 years", _bounds(3, "years", True, 3, "years", True, "3 years"), "18", "26"),
        ("4-5 years", _bounds(4, "years", True, 5, "years", True, "4-5 years"), "19", "27"),
        ("6-7 years", _bounds(6, "years", True, 7, "years", True, "6-7 years"), "20", "28"),
        ("8-17 years", _bounds(8, "years", True, 17, "years", True, "8-17 years"), "21", "29"),
        (">=18 years", _bounds(18, "years", True, None, "", False, ">=18 years"), "22", "29"),
    ]
    female_bicarbonate = [
        ("1-3 years", _bounds(1, "years", True, 3, "years", True, "1-3 years"), "18", "25"),
        ("4-5 years", _bounds(4, "years", True, 5, "years", True, "4-5 years"), "19", "26"),
        ("6-7 years", _bounds(6, "years", True, 7, "years", True, "6-7 years"), "20", "27"),
        ("8-9 years", _bounds(8, "years", True, 9, "years", True, "8-9 years"), "21", "28"),
        (">=10 years", _bounds(10, "years", True, None, "", False, ">=10 years"), "22", "29"),
    ]
    for _label, age, low, high in male_bicarbonate:
        rows.append(
            _row(
                test_name="Bicarbonate",
                aliases=["Serum carbon dioxide", "HCO3", "Total CO2"],
                sex="male",
                low=low,
                high=high,
                unit="mmol/L",
                age=age,
                specimen="Serum",
                method=electrolyte_method["bicarbonate"],
                source=electrolyte,
                limitations=bicarbonate_source_note,
            )
        )
    for _label, age, low, high in female_bicarbonate:
        rows.append(
            _row(
                test_name="Bicarbonate",
                aliases=["Serum carbon dioxide", "HCO3", "Total CO2"],
                sex="female",
                low=low,
                high=high,
                unit="mmol/L",
                age=age,
                specimen="Serum",
                method=electrolyte_method["bicarbonate"],
                source=electrolyte,
                limitations=bicarbonate_source_note,
            )
        )

    alt = {
        "source_title": "Alanine Aminotransferase (ALT) (GPT), Serum",
        "source_publisher": "Mayo Clinic Laboratories",
        "source_version": "Test catalog ALT, test 8362, read 12 October 2026",
        "source_url": "https://www.mayocliniclabs.com/test-catalog/Overview/8362",
        "source_accessed": ACCESSED,
    }
    alt_method = (
        "Photometric rate with pyridoxal phosphate. Roche Diagnostics ALT reagent, package insert 04/2024, "
        "as cited by Mayo Clinic Laboratories. The page says the interval is Mayo-derived."
    )
    rows.append(
        _row(
            test_name="ALT",
            aliases=["Alanine aminotransferase", "SGPT", "Alanine Aminotransferase (ALT), S"],
            sex="male",
            low="7",
            high="55",
            unit="U/L",
            age=at_least_one_year,
            specimen="Serum",
            method=alt_method,
            source=alt,
            limitations=MAYO_LIMIT + " No interval is published below 12 months of age.",
        )
    )
    rows.append(
        _row(
            test_name="ALT",
            aliases=["Alanine aminotransferase", "SGPT", "Alanine Aminotransferase (ALT), S"],
            sex="female",
            low="7",
            high="45",
            unit="U/L",
            age=at_least_one_year,
            specimen="Serum",
            method=alt_method,
            source=alt,
            limitations=MAYO_LIMIT + " No interval is published below 12 months of age.",
        )
    )

    ast = {
        "source_title": "Aspartate Aminotransferase (AST) (GOT), Serum",
        "source_publisher": "Mayo Clinic Laboratories",
        "source_version": "Test catalog AST, test 8360, read 12 October 2026",
        "source_url": "https://www.mayocliniclabs.com/test-catalog/overview/8360",
        "source_accessed": ACCESSED,
    }
    ast_method = (
        "Photometric rate with pyridoxal phosphate. Roche Diagnostics aspartate aminotransferase reagent, "
        "package insert 01/2024, as cited by Mayo Clinic Laboratories. The page says the interval is Mayo-derived."
    )
    ast_bands = [
        ("male", "1-13 years", _bounds(1, "years", True, 13, "years", True, "1-13 years"), "8", "60"),
        ("male", ">=14 years", _bounds(14, "years", True, None, "", False, ">=14 years"), "8", "48"),
        ("female", "1-13 years", _bounds(1, "years", True, 13, "years", True, "1-13 years"), "8", "50"),
        ("female", ">=14 years", _bounds(14, "years", True, None, "", False, ">=14 years"), "8", "43"),
    ]
    for sex, _label, age, low, high in ast_bands:
        rows.append(
            _row(
                test_name="AST",
                aliases=["Aspartate aminotransferase", "SGOT", "Aspartate Aminotransferase (AST), S"],
                sex=sex,
                low=low,
                high=high,
                unit="U/L",
                age=age,
                specimen="Serum",
                method=ast_method,
                source=ast,
                limitations=MAYO_LIMIT + " No interval is published below 12 months of age.",
            )
        )

    alp = {
        "source_title": "Alkaline Phosphatase, Serum",
        "source_publisher": "Mayo Clinic Laboratories",
        "source_version": "Test catalog ALP, test 8340, read 12 October 2026",
        "source_url": "https://www.mayocliniclabs.com/test-catalog/overview/8340",
        "source_accessed": ACCESSED,
    }
    alp_method = (
        "Colorimetric, p-nitrophenyl phosphate. Roche Diagnostics alkaline phosphatase reagent, "
        "package insert 09/2022, as cited by Mayo Clinic Laboratories. The page says pediatric intervals must be used for children."
    )
    alp_bands = [
        ("male", "0-14 days", _bounds(0, "days", True, 14, "days", True, "0-14 days"), "83", "248"),
        ("male", "15 days-<1 year", _bounds(15, "days", True, 1, "years", False, "15 days-<1 year"), "122", "469"),
        ("male", "1-<10 years", _bounds(1, "years", True, 10, "years", False, "1-<10 years"), "142", "335"),
        ("male", "10-<13 years", _bounds(10, "years", True, 13, "years", False, "10-<13 years"), "129", "417"),
        ("male", "13-<15 years", _bounds(13, "years", True, 15, "years", False, "13-<15 years"), "116", "468"),
        ("male", "15-<17 years", _bounds(15, "years", True, 17, "years", False, "15-<17 years"), "82", "331"),
        ("male", "17-<19 years", _bounds(17, "years", True, 19, "years", False, "17-<19 years"), "55", "149"),
        ("male", ">=19 years", _bounds(19, "years", True, None, "", False, ">=19 years"), "40", "129"),
        ("female", "0-14 days", _bounds(0, "days", True, 14, "days", True, "0-14 days"), "83", "248"),
        ("female", "15 days-<1 year", _bounds(15, "days", True, 1, "years", False, "15 days-<1 year"), "122", "469"),
        ("female", "1-<10 years", _bounds(1, "years", True, 10, "years", False, "1-<10 years"), "142", "335"),
        ("female", "10-<13 years", _bounds(10, "years", True, 13, "years", False, "10-<13 years"), "129", "417"),
        ("female", "13-<15 years", _bounds(13, "years", True, 15, "years", False, "13-<15 years"), "57", "254"),
        ("female", "15-<17 years", _bounds(15, "years", True, 17, "years", False, "15-<17 years"), "50", "117"),
        ("female", ">=17 years", _bounds(17, "years", True, None, "", False, ">=17 years"), "35", "104"),
    ]
    for sex, _label, age, low, high in alp_bands:
        rows.append(
            _row(
                test_name="Alkaline phosphatase",
                aliases=["ALP", "Alkaline Phosphatase, S"],
                sex=sex,
                low=low,
                high=high,
                unit="U/L",
                age=age,
                specimen="Serum",
                method=alp_method,
                source=alp,
                limitations=MAYO_LIMIT,
            )
        )

    glucose = {
        "source_title": "Glucose, Random, Serum",
        "source_publisher": "Mayo Clinic Laboratories",
        "source_version": "Test catalog GLURA, test 89115, read 12 October 2026",
        "source_url": "https://www.mayocliniclabs.com/test-catalog/overview/89115",
        "source_accessed": ACCESSED,
    }
    glucose_method = (
        "Hexokinase. Roche Diagnostics Glucose HK Gen.3, package insert 07/2024, as cited by Mayo Clinic Laboratories."
    )
    rows.append(
        _row(
            test_name="Random blood sugar",
            aliases=["Random Blood Sugar (RBS)", "RBS", "Glucose, Random", "Random glucose"],
            sex="any",
            low="70",
            high="140",
            unit="mg/dL",
            age=at_least_one_year,
            specimen="Serum",
            method=glucose_method,
            source=glucose,
            limitations=(
                MAYO_LIMIT
                + " This is the random serum glucose interval for age 1 year and older. "
                + "It is not a fasting interval. No interval is published below 12 months."
            ),
        )
    )
    rows.append(
        _row(
            test_name="Fasting blood sugar",
            aliases=["Fasting Blood Sugar (FBS)", "FBS", "Fasting glucose"],
            sex="any",
            low="126",
            high="",
            unit="mg/dL",
            age=None,
            specimen="Serum or plasma",
            method=glucose_method,
            source=glucose,
            limitations=(
                "The random-glucose page quotes this as a diagnostic criterion for diabetes: "
                "fasting plasma or serum glucose at or above 126 mg/dL after an 8-hour fast, confirmed on a subsequent day. "
                "It is not a reference interval and result entry does not use it. "
                "No fasting reference interval was loaded."
            ),
            purpose="diagnostic_threshold",
            low_inclusive=True,
            descriptive="Diabetes diagnostic criterion when fasting for at least 8 hours, not a reference range.",
        )
    )
    return rows


def _who_rows() -> list[dict[str, Any]]:
    source = {
        "source_title": "Guideline on haemoglobin cutoffs to define anaemia in individuals and populations",
        "source_publisher": "World Health Organization",
        "source_version": "Geneva, 2024. Table 2.",
        "source_url": "https://iris.who.int/items/80a8b7b3-b3e9-4673-8a47-90eeee11ccaa",
        "source_accessed": ACCESSED,
    }
    bands = [
        ("6-23 months", _bounds(6, "months", True, 23, "months", True, "6-23 months"), "any", "", "105"),
        ("24-59 months", _bounds(24, "months", True, 59, "months", True, "24-59 months"), "any", "", "110"),
        ("5-11 years", _bounds(5, "years", True, 11, "years", True, "5-11 years"), "any", "", "115"),
        ("12-14 years", _bounds(12, "years", True, 14, "years", True, "12-14 years"), "any", "", "120"),
        (
            "15-65 years, nonpregnant women",
            _bounds(15, "years", True, 65, "years", True, "15-65 years, nonpregnant women"),
            "female",
            "nonpregnant",
            "120",
        ),
        ("15-65 years, men", _bounds(15, "years", True, 65, "years", True, "15-65 years, men"), "male", "", "130"),
        (
            "Pregnancy, first trimester",
            _bounds(None, "", False, None, "", False, "Pregnancy, first trimester"),
            "female",
            "pregnant_first_trimester",
            "110",
        ),
        (
            "Pregnancy, second trimester",
            _bounds(None, "", False, None, "", False, "Pregnancy, second trimester"),
            "female",
            "pregnant_second_trimester",
            "105",
        ),
        (
            "Pregnancy, third trimester",
            _bounds(None, "", False, None, "", False, "Pregnancy, third trimester"),
            "female",
            "pregnant_third_trimester",
            "110",
        ),
    ]
    rows = []
    for _label, age, sex, condition, cutoff in bands:
        rows.append(
            _row(
                test_name="Haemoglobin",
                aliases=["Hemoglobin", "Hb", "HGB"],
                sex=sex,
                low="",
                high=cutoff,
                unit="g/L",
                age=age,
                specimen="Blood",
                method="The guideline recommends venous blood and an automated haematology analyser. It does not name this hospital's method.",
                source=source,
                limitations=WHO_LIMIT,
                purpose="diagnostic_threshold",
                condition=condition,
                high_inclusive=False,
                descriptive=f"Anaemia is defined as haemoglobin below {cutoff} g/L at sea level.",
                conflict_note=(
                    "This WHO cutoff is not a competing reference interval. "
                    "The Mayo Clinic Laboratories haemoglobin rows are reference intervals in g/dL and are stored separately."
                ),
            )
        )
    return rows


def _review_rows() -> list[dict[str, Any]]:
    """Tests already on the hospital list for which no numeric interval was established."""
    empty_source = {
        "source_title": "",
        "source_publisher": "",
        "source_version": "",
        "source_url": "",
        "source_accessed": "",
    }
    gaps = [
        (
            "Creatinine",
            ["Serum creatinine (umol/L)", "Serum creatinine"],
            "Serum",
            "numeric",
            "No reference interval was loaded. The laboratory order is named in µmol/L. A mg/dL interval was not copied onto it, and no conversion was applied.",
        ),
        (
            "Urea",
            ["Blood urea nitrogen", "BUN", "Serum urea"],
            "Serum",
            "numeric",
            "No reference interval was loaded. Urea and blood urea nitrogen use different units. Neither an unsourced conversion nor an analyser range was used.",
        ),
        ("Albumin", ["Serum albumin"], "Serum", "numeric", "No method-specific reference interval was established."),
        (
            "Bilirubin total",
            ["Total bilirubin", "Bilirubin, total"],
            "Serum",
            "numeric",
            "No method-specific reference interval was established. Direct and total bilirubin were not given the same range.",
        ),
        (
            "Bilirubin direct",
            ["Direct bilirubin", "Conjugated bilirubin"],
            "Serum",
            "numeric",
            "No method-specific reference interval was established.",
        ),
        ("Uric acid", ["Serum uric acid"], "Serum", "numeric", "No method-specific reference interval was established."),
        ("Calcium", ["Calcium, total", "Serum calcium"], "Serum", "numeric", "No method-specific reference interval was established."),
        (
            "Total cholesterol",
            ["Cholesterol"],
            "Serum",
            "numeric",
            "No reference interval was loaded. A treatment target was not stored as a reference interval.",
        ),
        ("HDL cholesterol", ["HDL"], "Serum", "numeric", "No reference interval was loaded."),
        ("LDL cholesterol", ["LDL"], "Serum", "numeric", "No reference interval was loaded."),
        ("Triglycerides", ["Triglyceride"], "Serum", "numeric", "No reference interval was loaded."),
        (
            "Fasting blood sugar",
            ["Fasting Blood Sugar (FBS)", "FBS", "Fasting glucose"],
            "Serum",
            "numeric",
            "No fasting reference interval was established. The separate diabetes cutoff is not a reference range.",
        ),
        ("ESR", ["Erythrocyte sedimentation rate"], "Whole blood", "numeric", "No reference interval was established."),
        (
            "Blood group",
            ["Blood grouping test", "ABO"],
            "Whole blood EDTA",
            "categorical",
            "No expected-result list was taken from a cited source.",
        ),
        (
            "Malaria rapid test",
            ["Rapid test for malaria", "Malaria Parasite (RDT)", "Malaria RDT"],
            "Whole blood",
            "categorical",
            "No expected-result list was taken from a cited source.",
        ),
        (
            "Serum pregnancy test",
            ["Pregnancy test, serum"],
            "Serum",
            "categorical",
            "No expected-result list was taken from a cited source.",
        ),
        (
            "Urine pregnancy test",
            ["Pregnancy test, urine"],
            "Urine",
            "categorical",
            "No expected-result list was taken from a cited source.",
        ),
    ]
    rows = []
    for name, aliases, specimen, result_type, limitations in gaps:
        rows.append(
            _row(
                test_name=name,
                aliases=aliases,
                sex="any",
                low="",
                high="",
                unit="",
                age=None,
                specimen=specimen,
                method="",
                source=empty_source,
                limitations=limitations,
                result_type=result_type,
                descriptive=limitations if result_type != "numeric" else "",
            )
        )
    return rows


def proposed_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(
        _cbc(
            "Haemoglobin",
            ["Hemoglobin", "Hb", "HGB"],
            "g/dL",
            "male",
            """
0-14 days | 13.9 | 19.1
15 days-4 weeks | 10.0 | 15.3
5 weeks-7 weeks | 8.9 | 12.7
8 weeks-5 months | 9.6 | 12.4
6 months-23 months | 10.1 | 12.5
24 months-35 months | 10.2 | 12.7
3-5 years | 11.4 | 14.3
6-8 years | 11.5 | 14.3
9-10 years | 11.8 | 14.7
11-14 years | 12.4 | 15.7
15-17 years | 13.3 | 16.9
Adults | 13.2 | 16.6
""",
        )
    )
    rows.extend(
        _cbc(
            "Haemoglobin",
            ["Hemoglobin", "Hb", "HGB"],
            "g/dL",
            "female",
            """
0-14 days | 13.4 | 20.0
15 days-4 weeks | 10.8 | 14.6
5 weeks-7 weeks | 9.2 | 11.4
8 weeks-5 months | 9.9 | 12.4
6 months-35 months | 10.2 | 12.7
3-5 years | 11.4 | 14.3
6-8 years | 11.5 | 14.3
9-10 years | 11.8 | 14.7
11-17 years | 11.9 | 14.8
Adults | 11.6 | 15.0
""",
        )
    )
    rows.extend(
        _cbc(
            "Haematocrit",
            ["Hematocrit", "PCV", "Packed cell volume", "Packed Cell Volume", "HCT"],
            "%",
            "male",
            """
0-14 days | 39.8 | 53.6
15 days-4 weeks | 30.5 | 45.0
5 weeks-7 weeks | 26.8 | 37.5
8 weeks-5 months | 28.6 | 37.2
6 months-23 months | 30.8 | 37.8
24 months-35 months | 31.0 | 37.7
3-7 years | 34 | 42
8-11 years | 35 | 43
12-15 years | 38 | 47
16-17 years | 40 | 50
Adults | 38.3 | 48.6
""",
        )
    )
    rows.extend(
        _cbc(
            "Haematocrit",
            ["Hematocrit", "PCV", "Packed cell volume", "Packed Cell Volume", "HCT"],
            "%",
            "female",
            """
0-14 days | 39.6 | 57.2
15 days-4 weeks | 32.0 | 44.5
5 weeks-7 weeks | 27.7 | 35.1
8 weeks-5 months | 29.5 | 37.1
6 months-23 months | 30.9 | 37.9
24 months-35 months | 31.2 | 37.8
3-7 years | 34 | 42
8-17 years | 35 | 43
Adults | 35.5 | 44.9
""",
        )
    )
    rows.extend(
        _cbc(
            "Red blood cell count",
            ["Erythrocytes", "RBC", "Red blood cells"],
            "x10(12)/L",
            "male",
            """
0-14 days | 4.10 | 5.55
15 days-4 weeks | 3.16 | 4.63
5 weeks-7 weeks | 3.02 | 4.22
8 weeks-5 months | 3.43 | 4.80
6 months-23 months | 4.03 | 5.07
24 months-35 months | 3.89 | 4.97
3-5 years | 4.00 | 5.10
6-10 years | 4.10 | 5.20
11-14 years | 4.20 | 5.30
15-17 years | 4.30 | 5.70
Adults | 4.35 | 5.65
""",
        )
    )
    rows.extend(
        _cbc(
            "Red blood cell count",
            ["Erythrocytes", "RBC", "Red blood cells"],
            "x10(12)/L",
            "female",
            """
0-14 days | 4.12 | 5.74
15 days-4 weeks | 3.32 | 4.80
5 weeks-7 weeks | 2.93 | 3.87
8 weeks-5 months | 3.45 | 4.75
6 months-23 months | 3.97 | 5.01
24 months-35 months | 3.84 | 4.92
3-5 years | 4.00 | 5.10
6-10 years | 4.10 | 5.20
11-14 years | 4.10 | 5.10
15-17 years | 3.80 | 5.00
Adults | 3.92 | 5.13
""",
        )
    )
    rows.extend(
        _cbc(
            "White blood cell count",
            ["Leukocytes", "WBC", "White blood cells", "White cell count"],
            "x10(9)/L",
            "male",
            """
0-14 days | 8.0 | 15.4
15 days-4 weeks | 7.8 | 15.9
5 weeks-7 weeks | 8.1 | 15.0
8 weeks-5 months | 6.5 | 13.3
6 months-23 months | 6.0 | 13.5
24 months-35 months | 5.1 | 13.4
3-5 years | 4.4 | 12.9
6-17 years | 3.8 | 10.4
Adults | 3.4 | 9.6
""",
        )
    )
    rows.extend(
        _cbc(
            "White blood cell count",
            ["Leukocytes", "WBC", "White blood cells", "White cell count"],
            "x10(9)/L",
            "female",
            """
0-14 days | 8.2 | 14.6
15 days-4 weeks | 8.4 | 14.4
5 weeks-7 weeks | 7.1 | 14.7
8 weeks-5 months | 6.0 | 13.3
6 months-23 months | 6.5 | 13.0
24 months-35 months | 4.9 | 13.2
3-5 years | 4.4 | 12.9
6-17 years | 3.8 | 10.4
Adults | 3.4 | 9.6
""",
        )
    )
    rows.extend(
        _cbc(
            "Platelet count",
            ["Platelets", "PLT"],
            "x10(9)/L",
            "male",
            """
0-14 days | 218 | 419
15 days-4 weeks | 248 | 586
5 weeks-7 weeks | 229 | 562
8 weeks-5 months | 244 | 529
6 months-23 months | 206 | 445
24 months-35 months | 202 | 403
3-5 years | 187 | 445
6-9 years | 187 | 400
10-13 years | 177 | 381
14-17 years | 139 | 320
Adults | 135 | 317
""",
        )
    )
    rows.extend(
        _cbc(
            "Platelet count",
            ["Platelets", "PLT"],
            "x10(9)/L",
            "female",
            """
0-14 days | 144 | 449
15 days-4 weeks | 279 | 571
5 weeks-7 weeks | 331 | 597
8 weeks-5 months | 247 | 580
6 months-23 months | 214 | 459
24 months-35 months | 189 | 394
3-5 years | 187 | 445
6-9 years | 187 | 400
10-13 years | 177 | 381
14-17 years | 158 | 362
Adults | 157 | 371
""",
        )
    )
    rows.extend(
        _cbc(
            "Neutrophils",
            ["Neutrophils, absolute", "Absolute neutrophil count", "ANC"],
            "x10(9)/L",
            "male",
            """
0-14 days | 1.60 | 6.06
15 days-4 weeks | 1.18 | 5.45
5 weeks-7 weeks | 0.83 | 4.23
8 weeks-5 months | 0.97 | 5.45
6 months-23 months | 1.19 | 7.21
24 months-35 months | 1.54 | 7.92
3-5 years | 1.60 | 7.80
6-16 years | 1.40 | 6.10
17 years | 1.80 | 7.20
Adults | 1.56 | 6.45
""",
        )
    )
    rows.extend(
        _cbc(
            "Neutrophils",
            ["Neutrophils, absolute", "Absolute neutrophil count", "ANC"],
            "x10(9)/L",
            "female",
            """
0-14 days | 1.73 | 6.75
15 days-4 weeks | 1.23 | 4.80
5 weeks-7 weeks | 1.00 | 4.68
8 weeks-5 months | 1.04 | 7.20
6 months-23 months | 1.27 | 7.18
24 months-35 months | 1.60 | 8.29
3-5 years | 1.60 | 7.80
6-14 years | 1.50 | 6.50
15-17 years | 2.00 | 7.40
Adults | 1.56 | 6.45
""",
        )
    )
    rows.extend(
        _cbc(
            "Lymphocytes",
            ["Lymphocytes, absolute", "Absolute lymphocyte count"],
            "x10(9)/L",
            "male",
            """
0-14 days | 2.07 | 7.53
15 days-4 weeks | 2.11 | 8.38
5 weeks-7 weeks | 2.47 | 7.95
8 weeks-5 months | 2.45 | 8.89
6 months-23 months | 1.56 | 7.83
24 months-35 months | 1.13 | 5.52
3-5 years | 1.60 | 5.30
6-11 years | 1.40 | 3.90
12-17 years | 1.00 | 3.20
Adults | 0.95 | 3.07
""",
        )
    )
    rows.extend(
        _cbc(
            "Lymphocytes",
            ["Lymphocytes, absolute", "Absolute lymphocyte count"],
            "x10(9)/L",
            "female",
            """
0-14 days | 1.75 | 8.00
15 days-4 weeks | 2.42 | 8.20
5 weeks-7 weeks | 2.29 | 9.14
8 weeks-5 months | 2.14 | 8.99
6 months-23 months | 1.52 | 8.09
24 months-35 months | 1.25 | 5.77
3-5 years | 1.60 | 5.30
6-11 years | 1.40 | 3.90
12-17 years | 1.00 | 3.20
Adults | 0.95 | 3.07
""",
        )
    )
    rows.extend(
        _cbc(
            "Monocytes",
            ["Monocytes, absolute", "Absolute monocyte count"],
            "x10(9)/L",
            "male",
            """
0-14 days | 0.52 | 1.77
15 days-4 weeks | 0.28 | 1.38
5 weeks-7 weeks | 0.28 | 1.05
8 weeks-5 months | 0.28 | 1.07
6 months-23 months | 0.25 | 1.15
24 months-35 months | 0.19 | 0.94
3-5 years | 0.30 | 0.90
6-17 years | 0.20 | 0.80
Adults | 0.26 | 0.81
""",
        )
    )
    rows.extend(
        _cbc(
            "Monocytes",
            ["Monocytes, absolute", "Absolute monocyte count"],
            "x10(9)/L",
            "female",
            """
0-14 days | 0.57 | 1.72
15 days-4 weeks | 0.42 | 1.21
5 weeks-7 weeks | 0.28 | 1.21
8 weeks-5 months | 0.24 | 1.17
6 months-23 months | 0.26 | 1.08
24 months-35 months | 0.24 | 0.92
3-5 years | 0.30 | 0.90
6-17 years | 0.20 | 0.80
Adults | 0.26 | 0.81
""",
        )
    )
    rows.extend(
        _cbc(
            "Eosinophils",
            ["Eosinophils, absolute", "Absolute eosinophil count"],
            "x10(9)/L",
            "male",
            """
0-14 days | 0.12 | 0.66
15 days-4 weeks | 0.08 | 0.80
5 weeks-7 weeks | 0.05 | 0.57
8 weeks-5 months | 0.03 | 0.61
6 months-23 months | 0.02 | 0.82
24 months-35 months | 0.03 | 0.53
3-11 years | 0.00 | 0.50
12-17 years | 0.10 | 0.20
Adults | 0.03 | 0.48
""",
        )
    )
    rows.extend(
        _cbc(
            "Eosinophils",
            ["Eosinophils, absolute", "Absolute eosinophil count"],
            "x10(9)/L",
            "female",
            """
0-14 days | 0.09 | 0.64
15 days-4 weeks | 0.06 | 0.75
5 weeks-7 weeks | 0.04 | 0.63
8 weeks-5 months | 0.02 | 0.74
6 months-23 months | 0.02 | 0.58
24 months-35 months | 0.03 | 0.46
3-11 years | 0.00 | 0.50
12-17 years | 0.10 | 0.20
Adults | 0.03 | 0.48
""",
        )
    )
    rows.extend(
        _cbc(
            "Basophils",
            ["Basophils, absolute", "Absolute basophil count"],
            "x10(9)/L",
            "male",
            """
0-14 days | 0.02 | 0.11
15 days-7 weeks | 0.01 | 0.07
8 weeks-35 months | 0.01 | 0.06
3-17 years | 0.00 | 0.10
Adults | 0.01 | 0.08
""",
        )
    )
    rows.extend(
        _cbc(
            "Basophils",
            ["Basophils, absolute", "Absolute basophil count"],
            "x10(9)/L",
            "female",
            """
0-14 days | 0.02 | 0.07
15 days-4 weeks | 0.01 | 0.06
5 weeks-7 weeks | 0.01 | 0.05
8 weeks-5 months | 0.01 | 0.07
6 months-35 months | 0.01 | 0.06
3-17 years | 0.00 | 0.10
Adults | 0.01 | 0.08
""",
        )
    )
    rows.extend(
        _cbc(
            "Mean cell volume",
            ["MCV", "Mean corpuscular volume"],
            "fL",
            "male",
            """
0-14 days | 91.3 | 103.1
15 days-4 weeks | 89.4 | 99.7
5 weeks-7 weeks | 84.3 | 94.2
8 weeks-5 months | 74.1 | 87.5
6 months-23 months | 69.5 | 81.7
24 months-35 months | 71.3 | 84.0
3-5 years | 77.2 | 89.5
6-11 years | 77.8 | 91.1
12-14 years | 79.9 | 93.0
15-17 years | 82.5 | 98.0
Adults | 78.2 | 97.9
""",
        )
    )
    rows.extend(
        _cbc(
            "Mean cell volume",
            ["MCV", "Mean corpuscular volume"],
            "fL",
            "female",
            """
0-14 days | 92.7 | 106.4
15 days-4 weeks | 90.1 | 103.0
5 weeks-7 weeks | 83.4 | 96.4
8 weeks-5 months | 74.8 | 88.3
6 months-23 months | 71.3 | 82.6
24 months-35 months | 72.3 | 85.0
3-5 years | 77.2 | 89.5
6-11 years | 77.8 | 91.1
12-14 years | 79.9 | 93.0
15-17 years | 82.5 | 98.0
Adults | 78.2 | 97.93
""",
        )
    )
    rows.extend(
        _cbc(
            "Red cell distribution width",
            ["RDW"],
            "%",
            "male",
            """
0-14 days | 14.8 | 17.0
15 days-4 weeks | 14.3 | 16.8
5 weeks-7 weeks | 13.8 | 16.1
8 weeks-5 months | 12.4 | 15.3
6 months-23 months | 12.9 | 15.6
24 months-35 months | 12.5 | 14.9
3-5 years | 11.3 | 13.4
6-17 years | 11.4 | 13.5
Adults | 11.8 | 14.5
""",
        )
    )
    rows.extend(
        _cbc(
            "Red cell distribution width",
            ["RDW"],
            "%",
            "female",
            """
0-14 days | 14.6 | 17.3
15 days-4 weeks | 14.4 | 16.2
5 weeks-7 weeks | 13.6 | 15.8
8 weeks-5 months | 12.2 | 14.3
6 months-23 months | 12.7 | 15.1
24 months-35 months | 12.4 | 14.9
3-5 years | 11.3 | 13.4
6-17 years | 11.4 | 13.5
Adults | 12.2 | 16.1
""",
        )
    )
    rows.extend(_chemistry_rows())
    rows.extend(_who_rows())
    rows.extend(_review_rows())
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("reference-range seed ids are not unique")
    return rows
