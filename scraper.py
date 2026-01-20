import argparse
import csv
import json
import os
import re
from datetime import date
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
    separators = [" | ", " - ", " – ", " — ", " · ", " at "]
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
    if isinstance(value, dict):
        min_val = value.get("minValue")
        max_val = value.get("maxValue")
        unit = value.get("unitText")
        if min_val and max_val:
            return f"{min_val}-{max_val} {unit or ''}".strip()
        if min_val:
            return f"{min_val} {unit or ''}".strip()
    elif value:
        return str(value)
    return None


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


def scrape_job(url: str) -> Dict[str, Optional[str]]:
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

    # Fallbacks for sites without JSON-LD JobPosting
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

    return {
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "pay": pay,
        "posted_date": None,
        "work_mode": work_mode,
    }


CSV_FIELDNAMES = [
    "ID",
    "Company",
    "Title",
    "Location",
    "Work Mode",
    "Pay",
    "Date Applied",
    "URL",
]


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def write_csv(path: str, row: Dict[str, Optional[str]]) -> None:
    if not os.path.exists(path):
        row_with_id = {"ID": 1, **row}
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            writer.writerow(row_with_id)
        return

    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    has_id = "ID" in fieldnames
    if has_id:
        max_id = 0
        for existing in rows:
            parsed = _parse_int(existing.get("ID"))
            if parsed and parsed > max_id:
                max_id = parsed
    else:
        for idx, existing in enumerate(rows, start=1):
            existing["ID"] = str(idx)
        max_id = len(rows)

    row_with_id = {"ID": max_id + 1, **row}
    needs_rewrite = not has_id or fieldnames != CSV_FIELDNAMES
    if needs_rewrite:
        normalized_rows = [
            {key: existing.get(key, "") for key in CSV_FIELDNAMES} for existing in rows
        ]
        normalized_rows.append(
            {key: row_with_id.get(key, "") for key in CSV_FIELDNAMES}
        )
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            writer.writerows(normalized_rows)
    else:
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(row_with_id)


def _na(value: Optional[str]) -> str:
    if value is None or str(value).strip() == "":
        return "N/A"
    return str(value)


def print_job(row: Dict[str, Optional[str]]) -> None:
    fieldnames = [
        "Company",
        "Title",
        "Location",
        "Work Mode",
        "Pay",
        "Date Applied",
        "URL",
    ]
    print("Scraped job data:")
    for name in fieldnames:
        print(f"{name}: {_na(row.get(name))}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape a job posting into CSV.")
    parser.add_argument("url", help="Job posting URL")
    parser.add_argument("-o", "--output", default="job.csv", help="CSV output path")
    parser.add_argument(
        "--date-applied",
        default=date.today().isoformat(),
        help="Date applied (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Print to console only; skip writing CSV.",
    )
    args = parser.parse_args()

    job = scrape_job(args.url)
    row = {
        "Company": job.get("company"),
        "Title": job.get("title"),
        "Location": job.get("location"),
        "Work Mode": job.get("work_mode"),
        "Pay": job.get("pay"),
        "Date Applied": args.date_applied,
        "URL": job.get("url"),
    }
    print_job(row)
    if not args.no_csv:
        write_csv(args.output, row)
        print(f"Saved job data to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
