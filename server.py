#!/usr/bin/env python3
"""
Portfolio Tracker — Web Server

Serves the portfolio dashboard as a live web app.
Reads data from Google Sheets (cloud) or Excel (local).

Usage:
    python server.py              # start on port 5000
    python server.py --port 8080  # custom port

Set GOOGLE_SHEET_ID env var to use Google Sheets backend.
Without it, falls back to local Excel file.
"""

import argparse
import datetime
import json
import os
import socket
from pathlib import Path

import yaml
from flask import Flask, Response

# Import compute functions directly to avoid pulling in desktop GUI dependencies
# (viewer/__init__.py imports customtkinter/matplotlib which aren't on the server)
import importlib.util
_compute_path = Path(__file__).resolve().parent / "viewer" / "data" / "compute.py"
_spec = importlib.util.spec_from_file_location("compute", _compute_path)
_compute = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_compute)
compute_portfolio_totals = _compute.compute_portfolio_totals
compute_portfolio_returns = _compute.compute_portfolio_returns
compute_bench_returns = _compute.compute_bench_returns

# Load .env if present
_root = Path(__file__).resolve().parent
_env_file = _root / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

# Load config — try config.yaml first, then config.cloud.yaml (safe for git)
_config_path = _root / "config.yaml"
_cloud_config_path = _root / "config.cloud.yaml"
if _config_path.exists():
    CFG = yaml.safe_load(_config_path.read_text())
elif _cloud_config_path.exists():
    CFG = yaml.safe_load(_cloud_config_path.read_text())
else:
    raise RuntimeError("No config.yaml or config.cloud.yaml found")
BROKERS = CFG["brokers"]
BENCHMARKS = CFG["benchmarks"]

# Choose backend
USE_SHEETS = bool(os.environ.get("GOOGLE_SHEET_ID"))

app = Flask(__name__)


def _load_data():
    """Load data from Google Sheets or local Excel."""
    broker_names = [b["name"] for b in BROKERS]
    bench_labels = [b["label"] for b in BENCHMARKS]

    if USE_SHEETS:
        import sheets
        return sheets.load_data(broker_names, bench_labels)
    else:
        from viewer.data.loader import load_data
        return load_data()


def _get_dashboard_data():
    """Read data and compute all values needed for the dashboard."""
    broker_raw, bench_raw = _load_data()
    broker_names = [b["name"] for b in BROKERS]
    bench_labels = [b["label"] for b in BENCHMARKS]

    # Portfolio totals per date
    totals = compute_portfolio_totals(broker_raw, broker_names)
    port_returns = compute_portfolio_returns(broker_raw, broker_names)
    port_dates = sorted(port_returns.keys()) if port_returns else []
    start_date = port_dates[0] if port_dates else None
    bench_returns = compute_bench_returns(bench_raw, start_date)

    # Build portfolio rows (date + per-broker + total)
    port_rows = []
    all_dates = sorted(totals.keys())
    for d in all_dates:
        entry = {"date": str(d)}
        for name in broker_names:
            entry[name] = broker_raw[name].get(d, 0)
        entry["Total"] = totals[d]
        port_rows.append(entry)

    # Build returns rows
    returns_rows = []
    all_return_dates = sorted(
        set(port_returns.keys())
        | {d for series in bench_returns.values() for d in series}
    )
    for d in all_return_dates:
        entry = {"date": str(d)}
        if d in port_returns:
            entry["Portfolio"] = round(port_returns[d] * 100, 4)
        for label in bench_labels:
            if label in bench_returns and d in bench_returns[label]:
                entry[label] = round(bench_returns[label][d] * 100, 4)
        returns_rows.append(entry)

    # Summary values
    latest = port_rows[-1] if port_rows else {}
    first = port_rows[0] if port_rows else {}
    latest_total = latest.get("Total", 0)
    first_total = first.get("Total", 0)
    total_return = (
        (latest_total - first_total) / first_total * 100 if first_total else 0
    )
    latest_ret = returns_rows[-1] if returns_rows else {}

    # Weekly change per broker and total
    week_change = {}
    total_week_change = 0
    if len(port_rows) >= 2:
        # Find the row ~5 trading days ago (or the earliest available)
        week_idx = max(0, len(port_rows) - 6)
        week_ago = port_rows[week_idx]
        for name in broker_names:
            curr = latest.get(name, 0)
            prev = week_ago.get(name, 0)
            week_change[name] = ((curr - prev) / prev * 100) if prev else 0
        curr_total = latest.get("Total", 0)
        prev_total = week_ago.get("Total", 0)
        total_week_change = ((curr_total - prev_total) / prev_total * 100) if prev_total else 0

    return {
        "returns_json": json.dumps(returns_rows),
        "portfolio_json": json.dumps(port_rows),
        "benchmarks_json": json.dumps(bench_labels),
        "brokers_json": json.dumps(broker_names),
        "latest_total": latest_total,
        "total_return": total_return,
        "total_week_change": total_week_change,
        "week_change": week_change,
        "latest_ret": latest_ret,
        "bench_labels": bench_labels,
        "broker_names": broker_names,
        "latest": latest,
    }


def _render_dashboard(ctx):
    """Generate the full dashboard HTML from data context."""
    bench_cards = ""
    for label in ctx["bench_labels"]:
        v = ctx["latest_ret"].get(label, 0)
        sign = "+" if v >= 0 else ""
        color = "#48BB78" if v >= 0 else "#F56565"
        bench_cards += f"""
        <div class="card">
            <div class="card-label">{label}</div>
            <div class="card-value" style="color:{color}">{sign}{v:.2f}%</div>
        </div>"""

    broker_cards = ""
    for name in ctx["broker_names"]:
        v = ctx["latest"].get(name, 0)
        wk = ctx["week_change"].get(name, 0)
        wk_sign = "+" if wk >= 0 else ""
        wk_color = "#48BB78" if wk >= 0 else "#F56565"
        broker_cards += f"""
        <div class="card">
            <div class="card-label">{name}</div>
            <div class="card-value">\u20ac{v:,.0f} <span class="card-week" style="color:{wk_color}">{wk_sign}{wk:.1f}%</span></div>
        </div>"""

    port_sign = "+" if ctx["total_return"] >= 0 else ""
    port_color = "#48BB78" if ctx["total_return"] >= 0 else "#F56565"
    wk_total = ctx["total_week_change"]
    wk_total_sign = "+" if wk_total >= 0 else ""
    wk_total_color = "#48BB78" if wk_total >= 0 else "#F56565"
    today = datetime.date.today().isoformat()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#0B0F19">
<title>Portfolio Tracker</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family:'DM Sans',sans-serif;
    background:#0B0F19;
    color:#E2E8F0;
    min-height:100vh;
    -webkit-text-size-adjust:100%;
}}
.container {{ max-width:1280px; margin:0 auto; padding:32px 24px; }}

/* Header */
header {{
    display:flex; justify-content:space-between; align-items:flex-end;
    margin-bottom:40px; padding-bottom:24px;
    border-bottom:1px solid rgba(255,255,255,0.06);
}}
h1 {{
    font-size:28px; font-weight:700; letter-spacing:-0.5px;
    background:linear-gradient(135deg,#63B3ED,#B794F4);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
}}
.subtitle {{ color:#718096; font-size:13px; margin-top:4px; }}
.header-right {{ text-align:right; }}
.total-value {{ font-size:36px; font-weight:700; letter-spacing:-1px;
    font-family:'JetBrains Mono',monospace; }}
.total-return {{ font-size:16px; font-weight:600;
    font-family:'JetBrains Mono',monospace; color:{port_color}; }}

/* Cards */
.cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr));
    gap:12px; margin-bottom:32px; }}
.card {{
    background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06);
    border-radius:12px; padding:16px 18px;
}}
.card-label {{ font-size:11px; text-transform:uppercase; letter-spacing:1px;
    color:#718096; margin-bottom:6px; }}
.card-value {{ font-size:20px; font-weight:600;
    font-family:'JetBrains Mono',monospace; }}
.card-week {{ font-size:12px; font-weight:500; }}
.week-badge {{ font-size:13px; font-weight:500; }}

/* Sections */
.section {{ margin-bottom:40px; }}
.section-title {{
    font-size:14px; text-transform:uppercase; letter-spacing:1.5px;
    color:#718096; margin-bottom:16px; font-weight:600;
}}
.chart-box {{
    background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06);
    border-radius:16px; padding:24px; position:relative;
}}
canvas {{ width:100%!important; }}

/* Controls */
.controls {{
    display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap;
}}
.btn {{
    background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1);
    color:#CBD5E0; padding:8px 18px; border-radius:8px; font-size:13px;
    font-family:'DM Sans',sans-serif; cursor:pointer; transition:all .2s;
    font-weight:500; -webkit-tap-highlight-color:transparent;
}}
.btn:hover {{ background:rgba(255,255,255,0.12); color:#fff; }}
.btn.active {{ background:rgba(99,179,237,0.15); border-color:#63B3ED;
    color:#63B3ED; }}

/* Table */
.table-wrap {{ overflow-x:auto; border-radius:12px;
    border:1px solid rgba(255,255,255,0.06);
    -webkit-overflow-scrolling:touch; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ background:rgba(255,255,255,0.04); padding:12px 16px; text-align:left;
    font-size:11px; text-transform:uppercase; letter-spacing:1px;
    color:#718096; font-weight:600; white-space:nowrap; }}
td {{ padding:10px 16px; border-top:1px solid rgba(255,255,255,0.04);
    font-family:'JetBrains Mono',monospace; font-size:12px; white-space:nowrap; }}
tr:hover td {{ background:rgba(255,255,255,0.02); }}
.pos {{ color:#48BB78; }} .neg {{ color:#F56565; }}

/* Footer */
footer {{ text-align:center; color:#4A5568; font-size:11px; margin-top:40px; padding-top:20px;
    border-top:1px solid rgba(255,255,255,0.04); }}

/* ── Mobile responsive ── */
@media (max-width: 640px) {{
    .desktop-only {{ display:none; }}
    .container {{ padding:16px 12px; }}

    header {{
        flex-direction:column; align-items:flex-start; gap:12px;
        margin-bottom:24px; padding-bottom:16px;
    }}
    .header-right {{ text-align:left; }}
    .total-value {{ font-size:28px; }}
    .total-return {{ font-size:14px; }}
    h1 {{ font-size:22px; }}

    .cards {{ grid-template-columns:repeat(2, 1fr); gap:8px; margin-bottom:24px; }}
    .card {{ padding:12px 14px; }}
    .card-value {{ font-size:16px; }}
    .card-label {{ font-size:10px; }}

    .section {{ margin-bottom:28px; }}
    .section-title {{ font-size:12px; margin-bottom:12px; }}
    .chart-box {{ padding:12px; border-radius:12px; }}

    .btn {{ padding:10px 14px; font-size:14px; min-height:40px;
            display:flex; align-items:center; justify-content:center; }}
    .controls {{ gap:6px; }}

    table {{ font-size:11px; }}
    th {{ padding:8px 10px; font-size:10px; }}
    td {{ padding:8px 10px; font-size:11px; }}
}}

@media (max-width: 380px) {{
    .cards {{ grid-template-columns:1fr; }}
    .total-value {{ font-size:24px; }}
}}
</style>
</head>
<body>
<div class="container">

<header>
  <div>
    <h1>Portfolio Tracker</h1>
    <div class="subtitle">Performance vs. Benchmarks</div>
  </div>
  <div class="header-right">
    <div class="total-value">\u20ac{ctx["latest_total"]:,.0f}</div>
    <div class="total-return">{port_sign}{ctx["total_return"]:.2f}% cumulative <span class="week-badge" style="color:{wk_total_color}">({wk_total_sign}{wk_total:.1f}% this week)</span></div>
  </div>
</header>

<!-- Summary cards -->
<div class="cards">
  {broker_cards}
  {bench_cards}
</div>

<!-- Cumulative Returns Chart -->
<div class="section">
  <div class="section-title">Cumulative Returns (%)</div>
  <div class="controls" id="period-controls">
    <button class="btn" data-period="30">1M</button>
    <button class="btn" data-period="90">3M</button>
    <button class="btn" data-period="180">6M</button>
    <button class="btn active" data-period="0">ALL</button>
  </div>
  <div class="chart-box">
    <canvas id="returnsChart" height="340"></canvas>
  </div>
</div>

<!-- Portfolio Value Chart -->
<div class="section">
  <div class="section-title">Portfolio Value (\u20ac)</div>
  <div class="chart-box">
    <canvas id="valueChart" height="280"></canvas>
  </div>
</div>

<!-- Broker Allocation Chart (hidden on mobile) -->
<div class="section desktop-only">
  <div class="section-title">Broker Allocation</div>
  <div class="chart-box" style="max-width:420px">
    <canvas id="allocationChart" height="280"></canvas>
  </div>
</div>

<!-- Data Table (hidden on mobile) -->
<div class="section desktop-only">
  <div class="section-title">Daily Returns Log</div>
  <div class="table-wrap">
    <table id="returnsTable">
      <thead><tr><th>Date</th><th>Portfolio</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<footer>Updated {today} \u00b7 Portfolio Tracker</footer>
</div>

<script>
const returnsData = {ctx["returns_json"]};
const portfolioData = {ctx["portfolio_json"]};
const benchLabels = {ctx["benchmarks_json"]};
const brokerNames = {ctx["brokers_json"]};

const COLORS = {{
    Portfolio: '#63B3ED',
    'S&P 500':  '#F6AD55',
    'NASDAQ':   '#FC8181',
    'MSCI World':'#B794F4',
}};
const FALLBACK = ['#68D391','#F6E05E','#FEB2B2','#C4B5FD','#76E4F7'];

function getColor(label, i) {{
    return COLORS[label] || FALLBACK[i % FALLBACK.length];
}}

// ── Returns chart ──────────────────────
function rebaseSeries(filtered, key) {{
    // Rebase so the first non-null value in the visible range = 0%
    const raw = filtered.map(r => r[key] ?? null);
    let baseVal = null;
    for (const v of raw) {{
        if (v !== null) {{ baseVal = v; break; }}
    }}
    if (baseVal === null) return raw;
    // rebase: (1 + current) / (1 + base) - 1, then back to percentage
    return raw.map(v => v === null ? null :
        ((1 + v/100) / (1 + baseVal/100) - 1) * 100);
}}

function buildReturnsChart(days) {{
    const filtered = days > 0 ? returnsData.slice(-days) : returnsData;
    const labels = filtered.map(r => r.date);
    const datasets = [];
    datasets.push({{
        label: 'Portfolio',
        data: rebaseSeries(filtered, 'Portfolio'),
        borderColor: getColor('Portfolio', 0),
        backgroundColor: 'transparent',
        borderWidth: 2.5, pointRadius: 0, tension: 0.3, spanGaps: true,
    }});
    benchLabels.forEach((l, i) => {{
        datasets.push({{
            label: l,
            data: rebaseSeries(filtered, l),
            borderColor: getColor(l, i+1),
            backgroundColor: 'transparent',
            borderWidth: 1.8, pointRadius: 0, tension: 0.3, spanGaps: true,
            borderDash: [6, 3],
        }});
    }});

    if (window._returnsChart) window._returnsChart.destroy();
    window._returnsChart = new Chart(document.getElementById('returnsChart'), {{
        type: 'line',
        data: {{ labels, datasets }},
        options: {{
            responsive: true,
            interaction: {{ intersect: false, mode: 'index' }},
            plugins: {{
                legend: {{ labels: {{ color:'#A0AEC0', font:{{ family:'DM Sans', size:12 }} }} }},
                tooltip: {{
                    backgroundColor:'rgba(26,32,44,0.95)', titleColor:'#E2E8F0',
                    bodyColor:'#CBD5E0', borderColor:'rgba(255,255,255,0.1)', borderWidth:1,
                    padding:12, titleFont:{{ family:'DM Sans' }}, bodyFont:{{ family:'JetBrains Mono', size:12 }},
                    callbacks: {{ label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y != null ? ctx.parsed.y.toFixed(2)+'%' : '\u2014') }}
                }}
            }},
            scales: {{
                x: {{ ticks:{{ color:'#4A5568', font:{{ size:10 }}, maxTicksLimit:8 }},
                       grid:{{ color:'rgba(255,255,255,0.03)' }} }},
                y: {{ ticks:{{ color:'#4A5568', font:{{ family:'JetBrains Mono', size:11 }},
                             callback: v => v.toFixed(1)+'%' }},
                       grid:{{ color:'rgba(255,255,255,0.04)' }} }}
            }}
        }}
    }});
}}
buildReturnsChart(0);

document.querySelectorAll('#period-controls .btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('#period-controls .btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        buildReturnsChart(+btn.dataset.period);
    }});
}});

// ── Portfolio value chart ──────────────
(() => {{
    const labels = portfolioData.map(r => r.date);
    const datasets = brokerNames.map((name, i) => ({{
        label: name,
        data: portfolioData.map(r => r[name] || 0),
        backgroundColor: getColor(name, i+2) + '99',
        borderColor: getColor(name, i+2),
        borderWidth: 1, fill: true, pointRadius: 0, tension: 0.3,
    }}));
    new Chart(document.getElementById('valueChart'), {{
        type: 'line',
        data: {{ labels, datasets }},
        options: {{
            responsive: true, interaction: {{ intersect:false, mode:'index' }},
            plugins: {{
                legend: {{ labels:{{ color:'#A0AEC0', font:{{ family:'DM Sans', size:12 }} }} }},
                tooltip: {{
                    backgroundColor:'rgba(26,32,44,0.95)', titleColor:'#E2E8F0',
                    bodyColor:'#CBD5E0', borderColor:'rgba(255,255,255,0.1)', borderWidth:1,
                    padding:12, bodyFont:{{ family:'JetBrains Mono', size:12 }},
                    callbacks: {{ label: ctx => {{
                        const val = ctx.parsed.y || 0;
                        const first = ctx.dataset.data[0] || 1;
                        const ret = ((val - first) / first * 100);
                        const sign = ret >= 0 ? '+' : '';
                        return ctx.dataset.label + ': \u20ac' + val.toLocaleString() + '  (' + sign + ret.toFixed(2) + '%)';
                    }} }}
                }}
            }},
            scales: {{
                x: {{ ticks:{{ color:'#4A5568', font:{{ size:10 }}, maxTicksLimit:8 }},
                       grid:{{ color:'rgba(255,255,255,0.03)' }} }},
                y: {{ stacked:false,
                       ticks:{{ color:'#4A5568', font:{{ family:'JetBrains Mono', size:11 }},
                               callback: v => '\u20ac'+v.toLocaleString() }},
                       grid:{{ color:'rgba(255,255,255,0.04)' }} }}
            }}
        }}
    }});
}})();

// ── Allocation doughnut ────────────────
(() => {{
    const latest = portfolioData[portfolioData.length - 1] || {{}};
    const vals = brokerNames.map(n => latest[n] || 0);
    new Chart(document.getElementById('allocationChart'), {{
        type: 'doughnut',
        data: {{
            labels: brokerNames,
            datasets: [{{ data: vals,
                backgroundColor: brokerNames.map((n,i) => getColor(n,i+2)),
                borderColor: '#0B0F19', borderWidth: 3 }}]
        }},
        options: {{
            responsive: true, cutout: '65%',
            plugins: {{
                legend: {{ position:'right', labels:{{ color:'#A0AEC0', font:{{ family:'DM Sans', size:12 }},
                    padding:16 }} }},
                tooltip: {{
                    backgroundColor:'rgba(26,32,44,0.95)', titleColor:'#E2E8F0',
                    bodyColor:'#CBD5E0', bodyFont:{{ family:'JetBrains Mono', size:12 }},
                    callbacks: {{ label: ctx => ctx.label + ': \u20ac' + ctx.parsed.toLocaleString() }}
                }}
            }}
        }}
    }});
}})();

// ── Data table ─────────────────────────
(() => {{
    const table = document.getElementById('returnsTable');
    const thead = table.querySelector('thead tr');
    benchLabels.forEach(l => {{
        const th = document.createElement('th');
        th.textContent = l;
        thead.appendChild(th);
    }});
    const tbody = table.querySelector('tbody');
    [...returnsData].reverse().slice(0, 60).forEach(r => {{
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${{r.date}}</td>`;
        ['Portfolio', ...benchLabels].forEach(key => {{
            const v = r[key];
            const cls = v > 0 ? 'pos' : v < 0 ? 'neg' : '';
            const txt = v != null ? (v > 0 ? '+' : '') + v.toFixed(2) + '%' : '\u2014';
            tr.innerHTML += `<td class="${{cls}}">${{txt}}</td>`;
        }});
        tbody.appendChild(tr);
    }});
}})();
</script>
</body>
</html>"""


@app.route("/")
def dashboard():
    ctx = _get_dashboard_data()
    html = _render_dashboard(ctx)
    return Response(html, mimetype="text/html")


@app.route("/api/data")
def api_data():
    ctx = _get_dashboard_data()
    return Response(
        json.dumps(
            {
                "portfolio": json.loads(ctx["portfolio_json"]),
                "returns": json.loads(ctx["returns_json"]),
                "benchmarks": ctx["bench_labels"],
                "brokers": ctx["broker_names"],
                "latest_total": ctx["latest_total"],
                "total_return": ctx["total_return"],
            }
        ),
        mimetype="application/json",
    )


def _get_local_ip():
    """Get the machine's local network IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Portfolio Tracker Web Server")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    local_ip = _get_local_ip()
    print(f"\n  Portfolio Tracker Web Server")
    print(f"  {'=' * 40}")
    print(f"  Local:   http://localhost:{args.port}")
    print(f"  Network: http://{local_ip}:{args.port}")
    print(f"\n  Open the Network URL on your phone!")
    print(f"  (both devices must be on the same Wi-Fi)\n")

    app.run(host="0.0.0.0", port=args.port, debug=False)
