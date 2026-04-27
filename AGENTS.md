# QuantLab Screener — Agent Instructions

## Project Purpose

A proof-of-concept stock screener for the Korean market (KOSPI + KOSDAQ combined top-100 by market cap). Scores each stock on four axes: Growth, Value, Quality (Fundamentals), and Trend. **Analysis only — no order/trade execution code.**

## Hard Rules (Non-Negotiable)

1. **No trade execution code.** Never add buy/sell order logic.
2. **No hardcoded API keys.** Load from `.env` only via `python-dotenv`.
3. **45-day disclosure lag rule.** At analysis time `t`, only use disclosures filed before `t - 45 days`. Any function that touches disclosure dates must have a comment explaining why.
4. **Sector-relative percentile normalization required.** Never compare absolute values across sectors.
5. **No ML or optimization libraries.** Use only `pandas` for scoring logic.
6. **No new web frameworks.** This PoC is CLI + Streamlit only.
7. **[Constitution] No fabricated values.** If data is unavailable, set the field to `NaN` or `0 points`. Never `fillna` with median/arbitrary values before scaling. Apply `fillna(0)` only **after** scaling so missing data does not affect peer rankings.

## Architecture

```
src/
  main.py          # CLI entry point (argparse)
  universe.py      # Build top-100 universe from KOSPI+KOSDAQ
  data_loader.py   # Fetch prices, financials, disclosures
  scorers/
    growth.py      # Revenue YoY, Op.profit YoY, EPS CAGR, acceleration
    value.py       # PER/PBR sector percentile, PEG, dividend yield
    quality.py     # ROE, op.margin, debt ratio inverse, interest coverage
    trend.py       # MA alignment, 52w high proximity, volume trend, RSI
  normalizer.py    # Sector-relative percentile normalization (0–100)
  aggregator.py    # Weighted sum: 25% × each axis
  analyst.py       # Per-stock metric detail
  explainer.py     # Human-readable score explanation
  backtest.py      # (optional) historical score validation

dashboard/
  app.py           # Streamlit dashboard

config/            # YAML config files
output/            # CSV results (gitignored)
data/              # Temp data cache (gitignored)
tests/             # pytest test suite
```

## Scoring Formula

```
TotalScore = 0.25 × Growth + 0.25 × Value + 0.25 × Quality + 0.25 × Trend
```

Each axis is 0–100. Sub-scores are sector-percentile-normalized before aggregation.

## Tech Stack

- Python 3.11 + venv
- `FinanceDataReader` — price/market data
- `OpenDartReader` — DART disclosure API
- `pykrx` — KRX market data
- `pandas` — all data wrangling and scoring
- `Streamlit` + `Plotly` — dashboard only
- `pytest` — tests
- Environment: `.env` file with `DART_API_KEY`, `OUTPUT_DIR`, `DATA_DIR`, `LOG_LEVEL`

## Code Style

- Small, single-purpose functions with type hints
- Log business logic decisions in `NOTES.md`
- Add comments on any function that touches the 45-day disclosure lag rule
- No multi-paragraph docstrings — one short line max

## Key Workflow Commands

```bash
# Setup
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run screener
python -m src.main

# Refresh universe (re-fetch top-100 list)
python -m src.main --refresh-universe

# Point-in-time analysis
python -m src.main --as-of-date 2026-01-15

# Dashboard
streamlit run dashboard/app.py

# Tests
pytest
```

## Output

- `output/stocks_top100.csv` — full scoring results for top-100 stocks

## What NOT to Do

- Do not add trade/order execution logic under any circumstances
- Do not use `sklearn`, `scipy`, or any optimization library
- Do not `fillna` before normalization/scaling
- Do not compare raw financial values across sectors (always percentile-normalize within sector)
- Do not hardcode ticker lists — universe is built dynamically at runtime
- Do not add new dependencies outside of `requirements.txt` without explicit approval
