# Kalshi Trading Bot - Copilot Instructions

## Overview
Python trading bot for Kalshi's BTC hourly "Price Above" prediction markets. Uses multi-signal analysis (momentum-primary) with Gemini AI validation. Runs every 15 minutes via GitHub Actions with $1/run budget cap.

## Core Architecture

| File | Purpose |
|------|---------|
| `trading_bot.py` | Main loop: market discovery → position check → signal analysis → trade execution |
| `market_intelligence.py` | Signal engine: 5 weighted signals + Gemini AI decision. Config via `model_config.json` |
| `kalshi_auth.py` | RSA-PSS/SHA256 auth. **Use `initialize_kalshi_client()`** - custom signing logic required |
| `test_market_discovery.py` | Market helpers: `find_next_hour_markets()`, `get_next_hour_et()`, `get_brti_price()` |

## Decision Flow
1. `find_next_hour_markets()` → selects market closest to current BTC price
2. `get_market_signals()` → calculates weighted composite score (0-100)
3. `get_gemini_decision()` → AI validates with BUY_YES/BUY_NO/SKIP
4. Execute if budget allows; log to `trades.jsonl` + `trades.log`

## Signal Weights (model_config.json)
- **Momentum (55%)**: 2-min candlesticks via 1-min bars
- **Orderbook (15%)**: Bid/ask spread health
- **Trade Flow (15%)**: Recent trade direction
- **Liquidity (10%)**: Top-of-book depth
- **Volatility (5%)**: Dampening multiplier

**Thresholds**: composite > 55 → BUY_YES | < 45 → BUY_NO | 45-55 → Gemini decides

## Local Development
```bash
pip install -r requirements.txt
cp .env.example .env  # Add KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY, GEMINI_API_KEY
python trading_bot.py
cat trades.jsonl | python -m json.tool
```

## Critical Patterns

### Market Ticker Format
- **Full**: `KXBTCD-25DEC3012-T88749.99` (series-dateHHMM-Tprice)
- **Series**: `KXBTCD` (use `extract_series_ticker()`)
- Series for candlestick queries; full ticker for orders/positions

### API Timestamps
**Always SECONDS, not milliseconds**: `int(datetime.now(timezone.utc).timestamp())`

### Authentication
```python
from kalshi_auth import initialize_kalshi_client
client = initialize_kalshi_client()  # Never use SDK default auth
```

### Logging Convention
Always include `decision_log` dict with: framework, signals, confidence, Gemini reasoning
```python
log_trade(ticker, action, status, decision_log={'framework': 'momentum-primary', ...})
```

## Pitfalls
- **Timestamps**: API expects seconds - `start_ts=int(start_time.timestamp())`
- **Position conflicts**: Always call `check_existing_positions()` before trading
- **ET timezone**: Markets scheduled by ET - use `get_next_hour_et()` from `test_market_discovery.py`
- **Gemini fallback**: Wrap in try-except; uses composite thresholds if AI unavailable
- **Budget enforcement**: `MAX_TRADE_COST_CENTS = 100` - check before every order

## GitHub Actions
- Cron: `*/15 * * * *` with `cancel-in-progress: false` (sequential execution critical)
- Secrets: `KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY`, `GEMINI_API_KEY`
- Auto-commits: `docs/index.html`, `trades.log`, `trades.jsonl`
