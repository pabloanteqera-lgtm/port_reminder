#!/usr/bin/env python3
"""
Fetch unprocessed Telegram replies and save portfolio values to Excel.
Called by the viewer on launch.
"""

import datetime, json, os, re
from pathlib import Path

import yaml
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parent

# Load .env if present
_env_file = ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
TOKEN = CFG["telegram"]["bot_token"]
CHAT_ID = CFG["telegram"]["chat_id"]
BROKERS = CFG["brokers"]

OFFSET_FILE = ROOT / ".telegram_offset"


def _get_offset():
    """Read the last processed update_id."""
    if OFFSET_FILE.exists():
        return int(OFFSET_FILE.read_text().strip())
    return 0


def _save_offset(offset):
    OFFSET_FILE.write_text(str(offset))


def get_updates():
    """Fetch new messages from Telegram."""
    offset = _get_offset()
    params = {"chat_id": CHAT_ID, "timeout": 0}
    if offset:
        params["offset"] = offset + 1

    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data)
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())

    if not result.get("ok"):
        return []

    return result.get("result", [])


def parse_values(text):
    """
    Parse broker values from a Telegram message.
    Accepts formats like:
      12500
      8300
      5200
    Or: 12500 8300 5200
    Or: 12500, 8300, 5200
    """
    # Extract all numbers (int or decimal, with optional comma as decimal sep)
    numbers = re.findall(r'[\d]+(?:[.,]\d+)?', text)
    if not numbers:
        return None

    broker_names = [b["name"] for b in BROKERS]
    if len(numbers) < len(broker_names):
        return None

    values = {}
    for i, name in enumerate(broker_names):
        val_str = numbers[i].replace(",", ".")
        values[name] = float(val_str)

    return values


def send_message(text):
    """Send a message back to the user."""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=data)
    urllib.request.urlopen(req)


def _use_sheets():
    """Check if Google Sheets backend is configured."""
    return bool(os.environ.get("GOOGLE_SHEET_ID"))


def _get_save_functions():
    """Return the appropriate save functions based on backend."""
    if _use_sheets():
        import sheets
        broker_names = [b["name"] for b in BROKERS]

        def save_pv(date, values):
            return sheets.save_portfolio_values(date, values, broker_names)

        return save_pv, sheets.save_cashflow
    else:
        from viewer.data.excel_io import save_portfolio_values, save_cashflow
        return save_portfolio_values, save_cashflow


def fetch_and_save():
    """
    Process unread Telegram messages, save portfolio values.
    Returns list of (date, values_dict) that were saved, or empty list.
    """
    save_portfolio_values, save_cashflow = _get_save_functions()

    updates = get_updates()
    saved = []
    cashflows_saved = []
    max_update_id = _get_offset()

    for update in updates:
        update_id = update["update_id"]
        max_update_id = max(max_update_id, update_id)

        msg = update.get("message")
        if not msg:
            continue

        # Only process messages from our user
        if msg.get("chat", {}).get("id") != CHAT_ID:
            continue

        text = msg.get("text", "").strip()
        if not text:
            continue

        # Skip commands
        if text.startswith("/"):
            continue

        # Check for deposit/withdrawal: "deposit DEGIRO 5000" or "withdraw XTB 1000"
        cf_match = re.match(
            r'(deposit|withdraw)\s+(\w+)\s+([\d.,]+)', text, re.IGNORECASE)
        if cf_match:
            flow_type = "deposit" if cf_match.group(1).lower() == "deposit" else "withdrawal"
            broker = cf_match.group(2)
            amount = float(cf_match.group(3).replace(",", "."))
            msg_timestamp = msg.get("date", 0)
            msg_date = datetime.datetime.fromtimestamp(msg_timestamp).date()
            save_cashflow(msg_date, broker, amount, flow_type)
            cashflows_saved.append((msg_date, broker, amount, flow_type))
            continue

        values = parse_values(text)
        if values is None:
            continue

        # Use the message date as the portfolio date
        msg_timestamp = msg.get("date", 0)
        msg_date = datetime.datetime.fromtimestamp(msg_timestamp).date()

        total = save_portfolio_values(msg_date, values)
        saved.append((msg_date, values, total))

    # Save offset so we don't reprocess these messages
    if max_update_id > _get_offset():
        _save_offset(max_update_id)

    # Send confirmations
    for date, values, total in saved:
        broker_names = [b["name"] for b in BROKERS]
        lines = [f"Saved for {date}:"]
        for name in broker_names:
            lines.append(f"  {name}: {values[name]:,.2f} EUR")
        lines.append(f"  Total: {total:,.2f} EUR")
        send_message("\n".join(lines))

    for date, broker, amount, flow_type in cashflows_saved:
        send_message(f"Saved {flow_type}: {amount:,.2f} EUR to {broker} on {date}")

    return saved


if __name__ == "__main__":
    saved = fetch_and_save()
    if saved:
        for date, values, total in saved:
            print(f"Saved {total:,.2f} EUR for {date}")
    else:
        print("No new portfolio values in Telegram.")
