"""Compute functions for returns, drawdown, volatility, correlation, TWR."""

import datetime
import math
from collections import OrderedDict

import numpy as np


def compute_portfolio_totals(broker_raw, active_brokers):
    """Sum active brokers per date. Returns {date: total_eur}."""
    all_dates = set()
    for name in active_brokers:
        all_dates |= set(broker_raw[name].keys())
    all_dates = sorted(all_dates)

    totals = {}
    for d in all_dates:
        total = 0
        has_any = False
        for name in active_brokers:
            if d in broker_raw[name]:
                total += broker_raw[name][d]
                has_any = True
        if has_any:
            totals[d] = total
    return totals


def compute_portfolio_returns(broker_raw, active_brokers):
    """Sum active brokers per date and compute cumulative return."""
    totals = compute_portfolio_totals(broker_raw, active_brokers)
    if not totals:
        return {}

    dates = sorted(totals.keys())
    base = totals[dates[0]]
    if not base or base == 0:
        return {}
    return {d: (totals[d] - base) / base for d in dates}


def compute_bench_returns(bench_raw, start_date=None):
    """Compute cumulative returns for each benchmark, aligned to start_date."""
    series = {}
    for label, raw in bench_raw.items():
        bd = sorted(raw.keys())
        if not bd:
            continue
        base_d = bd[0]
        if start_date:
            for d in bd:
                if d >= start_date:
                    base_d = d
                    break
        base = raw[base_d]
        if not base or base == 0:
            continue
        series[label] = {
            d: (raw[d] - base) / base for d in bd if d >= base_d
        }
    return series


def compute_drawdown(totals):
    """Compute drawdown from peak. Returns {date: float} always <= 0."""
    if not totals:
        return {}
    dates = sorted(totals.keys())
    peak = totals[dates[0]]
    result = {}
    for d in dates:
        v = totals[d]
        if v > peak:
            peak = v
        result[d] = (v - peak) / peak if peak != 0 else 0
    return result


def compute_period_returns(totals, period="monthly"):
    """Compute period-over-period returns.
    Returns [(period_end_date, pct_change), ...]
    period: 'daily', 'weekly', 'monthly'
    """
    if not totals:
        return []

    dates = sorted(totals.keys())
    if len(dates) < 2:
        return []

    if period == "daily":
        results = []
        for i in range(1, len(dates)):
            prev = totals[dates[i - 1]]
            curr = totals[dates[i]]
            if prev and prev != 0:
                results.append((dates[i], (curr - prev) / prev))
        return results

    elif period == "weekly":
        # Group by ISO week
        groups = OrderedDict()
        for d in dates:
            key = d.isocalendar()[:2]  # (year, week)
            groups.setdefault(key, []).append(d)
    else:  # monthly
        groups = OrderedDict()
        for d in dates:
            key = (d.year, d.month)
            groups.setdefault(key, []).append(d)

    # Take last value per period
    period_vals = []
    for key, grp_dates in groups.items():
        last_d = max(grp_dates)
        period_vals.append((last_d, totals[last_d]))

    results = []
    for i in range(1, len(period_vals)):
        prev_d, prev_v = period_vals[i - 1]
        curr_d, curr_v = period_vals[i]
        if prev_v and prev_v != 0:
            results.append((curr_d, (curr_v - prev_v) / prev_v))

    return results


def compute_rolling_volatility(values, window=30):
    """Rolling std dev of daily returns. values: {date: float}.
    Returns {date: annualized_volatility}.
    """
    if not values:
        return {}

    dates = sorted(values.keys())
    if len(dates) < window + 1:
        return {}

    # Daily returns
    daily = []
    for i in range(1, len(dates)):
        prev = values[dates[i - 1]]
        curr = values[dates[i]]
        if prev and prev != 0:
            daily.append((dates[i], (curr - prev) / prev))
        else:
            daily.append((dates[i], 0.0))

    result = {}
    for i in range(window - 1, len(daily)):
        window_returns = [r for _, r in daily[i - window + 1:i + 1]]
        std = np.std(window_returns, ddof=1)
        annualized = std * math.sqrt(252)
        result[daily[i][0]] = annualized

    return result


def compute_correlation_matrix(broker_raw, bench_raw, active_brokers):
    """Compute correlation matrix of daily returns across brokers and benchmarks.
    Returns (labels, np.ndarray).
    """
    all_series = {}
    for name in active_brokers:
        if broker_raw.get(name):
            all_series[name] = broker_raw[name]
    for label, raw in bench_raw.items():
        if raw:
            all_series[label] = raw

    if len(all_series) < 2:
        return [], np.array([])

    labels = list(all_series.keys())

    # Find common dates
    common_dates = None
    for data in all_series.values():
        s = set(data.keys())
        common_dates = s if common_dates is None else common_dates & s
    common_dates = sorted(common_dates)

    if len(common_dates) < 3:
        return [], np.array([])

    # Compute daily returns for each series on common dates
    returns_matrix = []
    for label in labels:
        data = all_series[label]
        daily = []
        for i in range(1, len(common_dates)):
            prev = data[common_dates[i - 1]]
            curr = data[common_dates[i]]
            if prev and prev != 0:
                daily.append((curr - prev) / prev)
            else:
                daily.append(0.0)
        returns_matrix.append(daily)

    corr = np.corrcoef(returns_matrix)
    return labels, corr


def detect_missing_cashflows(totals, cashflows_list, threshold=0.10):
    """Detect dates where portfolio value jumps suspiciously without a cashflow.

    A jump > threshold (default 10%) between consecutive entries with no
    matching cashflow likely means a deposit/withdrawal was not recorded.
    Returns list of (date, change_amount, change_pct) for suspicious dates.
    """
    if not totals:
        return []

    dates = sorted(totals.keys())
    if len(dates) < 2:
        return []

    cf_dates = {d for d, _ in cashflows_list}
    warnings = []

    for i in range(1, len(dates)):
        prev_v = totals[dates[i - 1]]
        curr_v = totals[dates[i]]
        if not prev_v or prev_v == 0:
            continue
        change = curr_v - prev_v
        pct = change / prev_v
        if abs(pct) > threshold and dates[i] not in cf_dates:
            warnings.append((dates[i], change, pct))

    return warnings


def compute_twr(totals, cashflows_list):
    """Compute time-weighted return.
    totals: {date: portfolio_value}
    cashflows_list: [(date, signed_amount)] sorted by date

    Splits into sub-periods at each cashflow, chains geometric returns.
    Returns {date: cumulative_twr}.
    """
    if not totals:
        return {}

    dates = sorted(totals.keys())
    if len(dates) < 2:
        return {}

    # Build cashflow lookup
    cf_by_date = {}
    for d, amt in cashflows_list:
        cf_by_date[d] = cf_by_date.get(d, 0) + amt

    cumulative = 1.0
    result = {dates[0]: 0.0}

    for i in range(1, len(dates)):
        prev_d = dates[i - 1]
        curr_d = dates[i]
        prev_v = totals[prev_d]
        curr_v = totals[curr_d]

        # Adjust for cashflows on current date
        cf = cf_by_date.get(curr_d, 0)
        # Sub-period return: (end_value - cashflow) / start_value
        if prev_v and prev_v != 0:
            sub_return = (curr_v - cf) / prev_v
            cumulative *= sub_return
        result[curr_d] = cumulative - 1.0

    return result


def get_range_cutoff(range_key):
    """Get the cutoff date for a range key. Returns None for ALL."""
    if range_key == "ALL":
        return None
    today = datetime.date.today()
    if range_key == "YTD":
        return datetime.date(today.year, 1, 1)
    elif range_key == "1M":
        return today - datetime.timedelta(days=30)
    elif range_key == "3M":
        return today - datetime.timedelta(days=90)
    elif range_key == "6M":
        return today - datetime.timedelta(days=180)
    elif range_key == "1Y":
        return today - datetime.timedelta(days=365)
    elif range_key == "2Y":
        return today - datetime.timedelta(days=730)
    elif range_key == "3Y":
        return today - datetime.timedelta(days=1095)
    return None


def rebase_returns(data, cutoff_date):
    """Rebase cumulative returns so the value at cutoff_date = 0%.
    Keeps ALL data but shifts so the series starts at 0 from the cutoff.
    """
    if not data or cutoff_date is None:
        return data

    dates = sorted(data.keys())
    # Find the value at or just after the cutoff
    base_val = None
    for d in dates:
        if d >= cutoff_date:
            base_val = data[d]
            break

    if base_val is None:
        return data

    # Rebase: new_return = (1 + old_return) / (1 + base_return) - 1
    # Keep ALL dates so panning backwards still shows data
    result = {}
    for d in dates:
        result[d] = (1 + data[d]) / (1 + base_val) - 1
    return result


def filter_by_range(data, range_key):
    """Filter a date-keyed dict by time range.
    range_key: '1M','3M','6M','YTD','1Y','ALL'
    Returns filtered dict.
    """
    if range_key == "ALL" or not data:
        return data

    cutoff = get_range_cutoff(range_key)
    if cutoff is None:
        return data

    return {d: v for d, v in data.items() if d >= cutoff}
