#!/usr/bin/env python3
"""Send a daily Telegram reminder to enter portfolio values. Run via Task Scheduler."""

from pathlib import Path
import yaml
import urllib.request
import urllib.parse
import json

ROOT = Path(__file__).resolve().parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
TOKEN = CFG["telegram"]["bot_token"]
CHAT_ID = CFG["telegram"]["chat_id"]
BROKERS = CFG["brokers"]

broker_names = [b["name"] for b in BROKERS]
lines = ["US market closed. Time to log your portfolio values!",
         "",
         "Reply with one message, one value per line:"]
for name in broker_names:
    currency = next((b["currency"] for b in BROKERS if b["name"] == name), "EUR")
    lines.append(f"  {name} ({currency}): ???")
lines.append("")
lines.append("Example:")
for name in broker_names:
    lines.append(f"  12500")

text = "\n".join(lines)

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
req = urllib.request.Request(url, data=data)
resp = urllib.request.urlopen(req)
result = json.loads(resp.read())

if result.get("ok"):
    print("Reminder sent.")
else:
    print(f"Failed: {result}")
