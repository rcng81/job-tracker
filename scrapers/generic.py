import json
import math
import re
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _first_text(soup: BeautifulSoup, selectors) -> Optional[str]:
    for sel in selectors:
        node = soup.select_one(sel)
        if node and node.get_text(strip=True):
            return node.get_text(strip=True)
    return None


def _meta_content(soup: BeautifulSoup, selector: str) -> Optional[str]:
    node = soup.select_one(selector)
    if node and node.get("content"):
        return node.get("content").strip()
    return None


def _parse_jsonld_jobposting(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for script in scripts:
        raw = script.string
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        candidates = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                candidates = data["@graph"]
            else:
                candidates = [data]

        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            if obj.get("@type") == "JobPosting":
                return obj
    return None


def _clean_title(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    title = raw.strip()
    separators = [" | ", " - ", " at "]
    for sep in separators:
        if sep in title:
            title = title.split(sep, 1)[0].strip()
    lower = title.lower()
    if " in " in lower:
        idx = lower.rfind(" in ")
        title = title[:idx].strip()
    if title.endswith(")") and "(" in title:
        title = title[: title.rfind("(")].strip()
    for term in ["internship", "intern", "contract", "temporary"]:
        lower = title.lower()
        if term in lower:
            title = title[: lower.find(term)].strip()
    return title or None


def _split_linkedin_hiring_title(raw: Optional[str]) -> Dict[str, Optional[str]]:
    if not raw:
        return {"company": None, "title": None}
    text = raw.strip()
    marker = " hiring "
    if marker in text:
        company, title = text.split(marker, 1)
        return {"company": company.strip() or None, "title": title.strip() or None}
    return {"company": None, "title": None}


def _normalize_location(job: Dict[str, Any]) -> Optional[str]:
    loc = job.get("jobLocation")
    if isinstance(loc, list) and loc:
        loc = loc[0]
    if isinstance(loc, dict):
        address = loc.get("address") or {}
        if isinstance(address, dict):
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            ]
            parts = [p for p in parts if p]
            if parts:
                return ", ".join(parts)
    return None


def _normalize_salary(job: Dict[str, Any]) -> Optional[str]:
    base = job.get("baseSalary")
    if not isinstance(base, dict):
        return None
    value = base.get("value")
    unit = None
    if isinstance(value, dict):
        min_val = value.get("minValue")
        max_val = value.get("maxValue")
        unit = value.get("unitText")
        range_text = _format_salary_range(min_val, max_val, unit)
        if range_text:
            return range_text
        min_text = _format_salary_value(min_val, unit)
        if min_text:
            return min_text
    elif value:
        return _format_salary_value(value, unit)
    return None


def _format_salary_value(raw_value: Any, unit: Optional[str]) -> Optional[str]:
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        return _normalize_salary_text(text)
    try:
        numeric = float(raw_value)
    except (TypeError, ValueError):
        return None

    unit_text = (unit or "").lower()
    if numeric >= 1000 and ("year" in unit_text or "yr" in unit_text or not unit_text):
        thousands = math.floor(numeric / 1000.0)
        return f"{int(thousands)}k"
    if numeric.is_integer():
        return str(int(numeric))
    return str(numeric)


def _format_salary_range(
    min_value: Any, max_value: Any, unit: Optional[str]
) -> Optional[str]:
    if min_value is None or max_value is None:
        return None
    try:
        min_num = float(min_value)
        max_num = float(max_value)
    except (TypeError, ValueError):
        return None

    unit_text = (unit or "").lower()
    if min_num >= 1000 and max_num >= 1000 and (
        "year" in unit_text or "yr" in unit_text or not unit_text
    ):
        min_k = math.floor(min_num / 1000.0)
        max_k = math.floor(max_num / 1000.0)
        return f"{int(min_k)}-{int(max_k)}k"
    return None


def _normalize_salary_text(text: str) -> Optional[str]:
    raw = text.strip()
    if not raw:
        return None

    lowered = raw.lower()
    if "k" in lowered:
        return raw
    if "hr" in lowered or "hour" in lowered:
        return raw

    matches = re.findall(r"\d[\d,]*(?:\.\d+)?", raw)
    if not matches:
        return raw

    numbers = []
    for match in matches:
        try:
            numbers.append(float(match.replace(",", "")))
        except ValueError:
            continue
    if not numbers:
        return raw

    def _to_k(value: float) -> str:
        thousands = math.floor(value / 1000.0)
        return f"{int(thousands)}k"

    if all(value < 1000 for value in numbers):
        if len(numbers) == 2:
            return f"{numbers[0]:g}-{numbers[1]:g}"
        return f"{numbers[0]:g}"

    if len(numbers) >= 2:
        first, second = numbers[0], numbers[1]
        if first >= 1000 and second >= 1000:
            first_k = math.floor(first / 1000.0)
            second_k = math.floor(second / 1000.0)
            return f"{int(first_k)}-{int(second_k)}k"
    if numbers and numbers[0] >= 1000:
        return _to_k(numbers[0])
        return f"{first:g}-{second:g}"

    formatted = _to_k(numbers[0])
    return formatted


def _normalize_work_mode(job: Dict[str, Any]) -> Optional[str]:
    mode = job.get("jobLocationType")
    if isinstance(mode, str):
        lowered = mode.lower()
        if "telecommute" in lowered or "remote" in lowered:
            return "Remote"
        if "hybrid" in lowered:
            return "Hybrid"
        if "on site" in lowered or "on-site" in lowered or "onsite" in lowered:
            return "On-site"
    return None


_US_STATES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
}


def _find_location_in_text(text: str) -> Optional[str]:
    pattern = re.compile(r"\b([A-Z][a-zA-Z]+(?:[ -][A-Z][a-zA-Z]+)*)\s*,\s*([A-Z]{2})\b")
    for match in pattern.finditer(text):
        state = match.group(2)
        if state in _US_STATES:
            return f"{match.group(1)}, {state}"
    lowered = text.lower()
    if "remote" in lowered:
        return "Remote"
    if "hybrid" in lowered:
        return "Hybrid"
    return None


def _find_work_mode_in_text(text: str) -> Optional[str]:
    lowered = text.lower()
    if "remote" in lowered:
        return "Remote"
    if "hybrid" in lowered:
        return "Hybrid"
    if (
        "on-site" in lowered
        or "onsite" in lowered
        or "on site" in lowered
        or "in person" in lowered
    ):
        return "On-site"
    return None


def scrape_generic(url: str) -> Dict[str, Optional[str]]:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    job = _parse_jsonld_jobposting(soup)
    if job:
        title = _clean_title(job.get("title"))
        company = None
        hiring_org = job.get("hiringOrganization")
        if isinstance(hiring_org, dict):
            company = hiring_org.get("name")
        location = _normalize_location(job)
        if not location:
            location = _find_location_in_text(soup.get_text(" ", strip=True))
        pay = _normalize_salary(job)
        posted = job.get("datePosted")
        work_mode = _normalize_work_mode(job) or _find_work_mode_in_text(
            soup.get_text(" ", strip=True)
        )
        return {
            "url": url,
            "title": title,
            "company": company,
            "location": location,
            "pay": pay,
            "posted_date": posted,
            "work_mode": work_mode,
        }

    raw_title = _meta_content(soup, "meta[property='og:title']") or _first_text(
        soup, ["h1", "title"]
    )
    split = _split_linkedin_hiring_title(raw_title)
    title = _clean_title(split.get("title") or raw_title)

    company = split.get("company") or _first_text(
        soup, ["[data-company]", ".company", ".company-name"]
    )
    location = _first_text(
        soup,
        [
            "span[dir='ltr'] span.tvm__text--low-emphasis",
            "span.tvm__text--low-emphasis",
            "[data-location]",
            ".location",
            ".job-location",
        ],
    )
    if not location:
        location = _find_location_in_text(soup.get_text(" ", strip=True))
    work_mode_hint = _first_text(
        soup,
        [
            ".job-details-fit-level-preferences button span.tvm__text--low-emphasis strong",
            "span[aria-hidden='true'] span.tvm__text--low-emphasis strong",
            "span.tvm__text--low-emphasis strong",
        ],
    )
    work_mode = _find_work_mode_in_text(work_mode_hint or "")
    if not work_mode:
        work_mode = _find_work_mode_in_text(soup.get_text(" ", strip=True))
    pay = _first_text(
        soup,
        [
            "span.tvm__text--low-emphasis strong",
            "[data-salary]",
            ".salary",
            ".compensation",
        ],
    )
    if pay:
        pay = _normalize_salary_text(pay)

    return {
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "pay": pay,
        "posted_date": None,
        "work_mode": work_mode,
    }
