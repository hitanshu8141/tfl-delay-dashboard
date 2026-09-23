import csv
import os
import sys
from datetime import datetime, timezone

import requests

# Configuration

BASE_URL = "https://api.tfl.gov.uk"
MODES = ["tube"]
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tfl_status_log.csv")
APP_KEY = os.environ.get("4d1ebeac541941abbfaf28eaf5d3a0a7", "")

FIELDNAMES = [
    "captured_at_utc",
    "line_id",
    "line_name",
    "mode_name",
    "status_severity",
    "status_severity_description",
    "reason",
    "disruption_category",
    "validity_period_from",
    "validity_period_to",
]


def fetch_line_status(modes: list[str]) -> list[dict]:
    """Fetch current status for all lines in the given modes."""
    modes_csv = ",".join(modes)
    url = f"{BASE_URL}/Line/Mode/{modes_csv}/Status"
    params = {"detail": "true"}
    if APP_KEY:
        params["app_key"] = APP_KEY

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def flatten_lines(lines: list[dict], captured_at: str) -> list[dict]:
    """Turn the TfL JSON response into flat row dicts ready for CSV writing.

    Each line can have multiple lineStatuses entries (e.g. different
    disruptions affecting different branches) -- one row per status entry.
    A line with no disruptions still gets one row ('Good Service').
    """
    rows = []
    for line in lines:
        line_id = line.get("id", "")
        line_name = line.get("name", "")
        mode_name = line.get("modeName", "")
        statuses = line.get("lineStatuses") or []

        if not statuses:
            rows.append({
                "captured_at_utc": captured_at,
                "line_id": line_id,
                "line_name": line_name,
                "mode_name": mode_name,
                "status_severity": "",
                "status_severity_description": "",
                "reason": "",
                "disruption_category": "",
                "validity_period_from": "",
                "validity_period_to": "",
            })
            continue

        for status in statuses:
            disruption = status.get("disruption") or {}
            validity = status.get("validityPeriods") or [{}]
            first_validity = validity[0] if validity else {}

            rows.append({
                "captured_at_utc": captured_at,
                "line_id": line_id,
                "line_name": line_name,
                "mode_name": mode_name,
                "status_severity": status.get("statusSeverity", ""),
                "status_severity_description": status.get("statusSeverityDescription", ""),
                "reason": (status.get("reason") or "").replace("\n", " ").strip(),
                "disruption_category": disruption.get("category", ""),
                "validity_period_from": first_validity.get("fromDate", ""),
                "validity_period_to": first_validity.get("toDate", ""),
            })

    return rows


def save_rows(rows: list[dict]) -> None:
    file_exists = os.path.isfile(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        lines = fetch_line_status(MODES)
    except requests.exceptions.RequestException as exc:
        print(f"[{captured_at}] ERROR fetching TfL status: {exc}", file=sys.stderr)
        return 1

    rows = flatten_lines(lines, captured_at)
    if not rows:
        print(f"[{captured_at}] No line data returned.")
        return 0

    save_rows(rows)
    print(f"[{captured_at}] Logged {len(rows)} status rows to {CSV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())