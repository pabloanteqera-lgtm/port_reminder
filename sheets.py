"""
Google Sheets data adapter — read/write portfolio data using gspread.

Uses a service account so no login is needed.
Expects a Google Sheet with these worksheets:
  - Portfolio: Date | Broker1 | Broker2 | ... | Total
  - Benchmarks: Date | Bench1 | Bench2 | ...
  - CashFlows: Date | Broker | Amount | Type

Set these env vars (or put them in .env):
  GOOGLE_SHEET_ID=<your-sheet-id>
  GOOGLE_CREDENTIALS_JSON=<path-to-service-account-json>
    OR
  GOOGLE_CREDENTIALS=<raw JSON string> (for cloud deployment)
"""

import datetime
import json
import os
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client = None


def _get_client():
    """Get an authenticated gspread client (cached)."""
    global _client
    if _client is not None:
        return _client

    # Try raw JSON string first (for cloud deployment via env var)
    raw_json = os.environ.get("GOOGLE_CREDENTIALS")
    if raw_json:
        info = json.loads(raw_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # Fall back to file path
        creds_path = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if not creds_path:
            # Default location
            creds_path = str(Path(__file__).resolve().parent / "credentials.json")
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)

    _client = gspread.authorize(creds)
    return _client


def _get_sheet():
    """Get the Google Sheet spreadsheet object."""
    client = _get_client()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        raise ValueError(
            "GOOGLE_SHEET_ID env var not set. "
            "Set it to the ID from your Google Sheet URL: "
            "https://docs.google.com/spreadsheets/d/<THIS-PART>/edit"
        )
    return client.open_by_key(sheet_id)


# ──────────────────────────────────────────────────
#  Read operations
# ──────────────────────────────────────────────────

def load_data(broker_names, bench_labels):
    """Read portfolio and benchmark data from Google Sheets.

    Returns (broker_raw, bench_raw) matching the format of
    viewer.data.loader.load_data().
    """
    ss = _get_sheet()

    # Portfolio sheet
    ws_p = ss.worksheet("Portfolio")
    rows_p = ws_p.get_all_values()
    header_p = rows_p[0] if rows_p else []

    broker_raw = {name: {} for name in broker_names}
    for row in rows_p[1:]:
        if not row or not row[0]:
            continue
        try:
            d = datetime.date.fromisoformat(row[0])
        except ValueError:
            continue
        for i, name in enumerate(broker_names):
            col_idx = i + 1  # skip Date column
            if col_idx < len(row) and row[col_idx]:
                try:
                    broker_raw[name][d] = float(row[col_idx].replace(",", ""))
                except ValueError:
                    pass

    # Benchmarks sheet
    ws_b = ss.worksheet("Benchmarks")
    rows_b = ws_b.get_all_values()

    bench_raw = {label: {} for label in bench_labels}
    for row in rows_b[1:]:
        if not row or not row[0]:
            continue
        try:
            d = datetime.date.fromisoformat(row[0])
        except ValueError:
            continue
        for i, label in enumerate(bench_labels):
            col_idx = i + 1
            if col_idx < len(row) and row[col_idx]:
                try:
                    bench_raw[label][d] = float(row[col_idx].replace(",", ""))
                except ValueError:
                    pass

    # Forward-fill benchmarks to cover portfolio dates
    all_portfolio_dates = sorted(
        {d for br in broker_raw.values() for d in br})
    for label, raw in bench_raw.items():
        if not raw:
            continue
        bench_dates = sorted(raw.keys())
        last_val = None
        bi = 0
        for d in all_portfolio_dates:
            while bi < len(bench_dates) and bench_dates[bi] <= d:
                last_val = raw[bench_dates[bi]]
                bi += 1
            if d not in raw and last_val is not None:
                raw[d] = last_val

    return broker_raw, bench_raw


def load_cashflows():
    """Read cash flows from Google Sheets.
    Returns {broker: [(date, signed_amount), ...]}.
    """
    ss = _get_sheet()
    try:
        ws = ss.worksheet("CashFlows")
    except gspread.exceptions.WorksheetNotFound:
        return {}

    rows = ws.get_all_values()
    flows = {}
    for row in rows[1:]:
        if len(row) < 4 or not row[0] or not row[1]:
            continue
        try:
            d = datetime.date.fromisoformat(row[0])
            broker = row[1]
            amount = float(row[2].replace(",", ""))
            flow_type = row[3]
        except (ValueError, IndexError):
            continue

        signed = amount if flow_type == "deposit" else -amount
        flows.setdefault(broker, []).append((d, signed))

    return flows


# ──────────────────────────────────────────────────
#  Write operations
# ──────────────────────────────────────────────────

def save_portfolio_values(date, values_dict, broker_names):
    """Save broker values for a given date to Google Sheets."""
    ss = _get_sheet()
    ws = ss.worksheet("Portfolio")
    rows = ws.get_all_values()

    date_str = date.isoformat()
    total = sum(values_dict.values())

    # Build the new row
    new_row = [date_str]
    for name in broker_names:
        new_row.append(str(values_dict.get(name, 0)))
    new_row.append(str(total))

    # Check if date already exists — overwrite if so
    for i, row in enumerate(rows[1:], start=2):
        if row and row[0] == date_str:
            ws.update(f"A{i}", [new_row])
            return total

    # Append new row
    ws.append_row(new_row, value_input_option="RAW")
    return total


def save_cashflow(date, broker, amount, flow_type):
    """Save a deposit or withdrawal to the CashFlows sheet."""
    ss = _get_sheet()
    try:
        ws = ss.worksheet("CashFlows")
    except gspread.exceptions.WorksheetNotFound:
        ws = ss.add_worksheet("CashFlows", rows=1, cols=4)
        ws.update("A1", [["Date", "Broker", "Amount", "Type"]])

    ws.append_row(
        [date.isoformat(), broker, str(amount), flow_type],
        value_input_option="RAW",
    )


def save_benchmark_rows(rows, bench_labels):
    """Append benchmark data rows to the Benchmarks sheet.
    rows: list of (date, {label: value, ...})
    """
    ss = _get_sheet()
    ws = ss.worksheet("Benchmarks")

    new_rows = []
    for date, values in rows:
        row = [date.isoformat()]
        for label in bench_labels:
            row.append(str(values.get(label, "")))
        new_rows.append(row)

    if new_rows:
        ws.append_rows(new_rows, value_input_option="RAW")


def get_last_benchmark_date():
    """Get the last date in the Benchmarks sheet."""
    ss = _get_sheet()
    ws = ss.worksheet("Benchmarks")
    rows = ws.get_all_values()

    for row in reversed(rows[1:]):
        if row and row[0]:
            try:
                return datetime.date.fromisoformat(row[0])
            except ValueError:
                continue
    return None
