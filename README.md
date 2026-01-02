# Kalshi Trading Bot - Spotify Daily Markets

A Python trading bot that discovers and optionally trades **Spotify daily** markets on Kalshi.

The bot is intentionally conservative: it uses market microstructure (orderbook + recent activity + time-to-close)
and can optionally ask Gemini to approve/override decisions.

## Features

- **Spotify daily market targeting**: Centralized filtering in `spotify_daily_markets.py`
- **Market-agnostic signals**: No BTC strike parsing; uses market pricing + timing in `spotify_daily_intelligence.py`
- **Risk cap**: Per-order hard cap of **$1** (`MAX_TRADE_COST_CENTS = 100`)
- **Audit trail**: Writes `trades.jsonl` (preferred) and `trades.log` (legacy)
- **HTML report**: Generated into `docs/index.html`

## Setup

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure environment

```bash
cp .env.example .env
```

Required:

```
KALSHI_API_KEY_ID=...
KALSHI_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----
```

Optional (AI decision layer):

```
GEMINI_API_KEY=...
```

Spotify daily market targeting (optional overrides):

```
# Default behavior targets Spotify + daily-ish framing
SPOTIFY_MARKET_REQUIRED_KEYWORDS=spotify
SPOTIFY_MARKET_DAILY_KEYWORDS=daily
SPOTIFY_MARKET_EXCLUDE_KEYWORDS=

# If you know the exact Kalshi tickers, set these to avoid broad scanning:
SPOTIFY_SERIES_TICKERS=
SPOTIFY_EVENT_TICKERS=

# Safety / execution tuning
SPOTIFY_DAILY_MAX_MARKETS_PER_RUN=3
LIMIT_PRICE_BUFFER_CENTS=2
KALSHI_MARKETS_LIMIT=200
KALSHI_MARKETS_MAX_PAGES=10
```

### Run locally

```bash
python3 trading_bot.py
python3 generate_report.py
```

## GitHub Actions

The workflow in `.github/workflows/trading_bot.yml` runs the bot and regenerates the report.
You’ll need repository secrets:

- **`KALSHI_API_KEY_ID`**
- **`KALSHI_PRIVATE_KEY`**
- **`GEMINI_API_KEY`** (optional)

## Important notes

⚠️ **Real money**: Orders can execute on your Kalshi account. Test carefully.

⚠️ **Market selection**: If broad scanning is too slow/noisy, configure `SPOTIFY_SERIES_TICKERS` / `SPOTIFY_EVENT_TICKERS`.
