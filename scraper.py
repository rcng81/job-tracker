import argparse
import csv
import os
from datetime import date
from typing import Dict, Optional

from scrapers import scrape_job

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
