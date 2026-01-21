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

SHEET_COLUMNS = [
    "Company",
    "Job title",
    "Location",
    "Salary (k)",
    "URL",
    "Date applied",
    "Status",
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


def append_to_google_sheet(
    sheet_id: str, sheet_tab: str, row: Dict[str, Optional[str]], credentials_path: str
) -> None:
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing Google Sheets dependencies. Install gspread and google-auth."
        ) from exc

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    client = gspread.authorize(creds)
    worksheet = client.open_by_key(sheet_id).worksheet(sheet_tab)

    existing_ids = worksheet.col_values(1)
    if not existing_ids:
        worksheet.update("A1:G1", [SHEET_COLUMNS])
        existing_ids = ["Company"]
    values = [
        row.get("Company", ""),
        row.get("Title", ""),
        row.get("Location", ""),
        row.get("Pay", ""),
        row.get("URL", ""),
        row.get("Date Applied", ""),
        "Unknown",
    ]
    next_row = len(existing_ids) + 1
    worksheet.update(f"A{next_row}:G{next_row}", [values], value_input_option="USER_ENTERED")


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
    parser.add_argument(
        "--google-sheet-id",
        default=os.getenv("GOOGLE_SHEET_ID") or "1f-GQW4opwV8sH5XBpADxGKNvvx8Q1mv6W4JNibagXu8",
        help="Google Sheet ID (env: GOOGLE_SHEET_ID).",
    )
    parser.add_argument(
        "--google-sheet-tab",
        default=os.getenv("GOOGLE_SHEET_TAB") or "Tracker",
        help="Google Sheet tab name (env: GOOGLE_SHEET_TAB).",
    )
    parser.add_argument(
        "--google-credentials",
        default=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"),
        help="Service account JSON path (env: GOOGLE_SERVICE_ACCOUNT_JSON).",
    )
    parser.add_argument(
        "--no-sheets",
        action="store_true",
        help="Skip writing to Google Sheets.",
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
    if not args.no_sheets:
        provided = [args.google_sheet_id, args.google_sheet_tab, args.google_credentials]
        if all(provided):
            append_to_google_sheet(
                args.google_sheet_id,
                args.google_sheet_tab,
                row,
                args.google_credentials,
            )
            print("Saved job data to Google Sheets")
        elif any(provided):
            print(
                "Google Sheets not configured: provide sheet id, tab, and credentials."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
