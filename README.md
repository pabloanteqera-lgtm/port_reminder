# Portfolio Tracker

Track your investment portfolio daily across multiple brokers and compare
your performance against market benchmarks (S&P 500, NASDAQ, MSCI World).

## Quick Start

```bash
# 1. Install dependencies
pip install yfinance openpyxl pyyaml pandas

# 2. Run the demo to see it in action
python tracker.py demo

# 3. Open dashboard.html in your browser
```

## Daily Usage

```bash
# Enter today's broker values (interactive prompt)
python tracker.py add

# Fetch latest benchmark data from Yahoo Finance
python tracker.py fetch

# Regenerate the dashboard
python tracker.py dash

# Or do all three at once
python tracker.py update
```

## Configuration

Edit **config.yaml** to set your brokers, benchmarks, and currency:

```yaml
brokers:
  - name: DEGIRO
    type: manual
    currency: EUR
  - name: XTB
    type: manual
    currency: EUR

benchmarks:
  - ticker: "^GSPC"
    label: "S&P 500"
  - ticker: "^IXIC"
    label: "NASDAQ"
  - ticker: "URTH"
    label: "MSCI World"
```

## Automating with Cron (Linux/Mac)

Run daily at 23:00:

```bash
crontab -e
# Add this line:
0 23 * * 1-5 cd /path/to/portfolio-tracker && python tracker.py fetch && python tracker.py dash
```

For the portfolio values (which require manual entry or scraping), you can:
1. **Manual**: Run `python tracker.py add` each evening
2. **CSV import**: Export from your broker and run `python tracker.py import-csv data.csv`
3. **Selenium automation**: Extend the tracker with browser automation (see below)

## Bulk Import from CSV

Prepare a CSV with columns `date`, `broker_name`, `value`:

```csv
date,broker_name,value
2025-01-02,DEGIRO,15230.50
2025-01-02,XTB,8120.00
2025-01-02,Renta4,5045.30
2025-01-03,DEGIRO,15310.20
...
```

Then run:
```bash
python tracker.py import-csv my_data.csv
```

## Automating Broker Scraping (Advanced)

For automated daily collection from broker websites, you'd need Selenium
or Playwright. Here's a skeleton to extend in `tracker.py`:

```python
from selenium import webdriver
from selenium.webdriver.common.by import By

def scrape_degiro(username, password):
    driver = webdriver.Chrome()
    driver.get("https://trader.degiro.nl/login")
    # Login
    driver.find_element(By.ID, "username").send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "button[type=submit]").click()
    # Wait and extract portfolio value
    # ... (site-specific selectors)
    value = driver.find_element(By.CSS_SELECTOR, ".portfolio-total").text
    driver.quit()
    return float(value.replace(",", "").replace("€", ""))
```

> **Note**: Broker websites change frequently and may block automated access.
> Using the official API (DEGIRO has an unofficial Python API: `degiro-connector`)
> is more reliable than scraping.

## Files

| File | Description |
|------|-------------|
| `tracker.py` | Main application |
| `config.yaml` | Configuration (brokers, benchmarks, currency) |
| `portfolio_data.xlsx` | Excel data store (auto-created) |
| `dashboard.html` | Interactive dashboard (auto-generated) |
