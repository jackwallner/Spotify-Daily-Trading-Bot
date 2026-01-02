# How the Kalshi Trading Bot Works

## Simple Breakdown

### 1. **Data Collection**
   - Fetches **Spotify daily markets** from Kalshi (via centralized keyword/ticker filtering)
   - Pulls lightweight market data:
     - YES/NO bid/ask (orderbook snapshot)
     - recent trade activity (last ~15 minutes)
     - time-to-close (avoid last-minute noise)

### 2. **Market Selection**
   - Uses `spotify_daily_markets.py` to filter down to Spotify-themed markets
   - Prioritizes markets that:
     - match Spotify + daily framing (keywords)
     - close soon (within a configurable window)
     - have tighter spreads / better activity

### 3. **Trading Decision**
   - Computes a conservative composite score from:
     - implied probability (YES mid)
     - spread quality
     - recent trade activity
     - time-to-close
   - Optionally asks Gemini to approve/override the model recommendation.

### 4. **Trade Execution**
   - **Hard cap**: $1 per order (100 cents max cost)
   - Places a limit order slightly above the current ask (configurable buffer)
   - Prevents conflicting positions (won’t buy YES if you already hold NO, and vice versa)
   - Logs to `trades.jsonl` (preferred) + `trades.log` (legacy)

### 5. **Reporting**
   - Generates HTML report from trade logs
   - Shows stats: total trades, successful, failed, no trades
   - Commits report to `docs/index.html` in the repo

## Workflow Flow

```
Manual trigger (or scheduled run if enabled):
1. Checkout code
2. Install Python dependencies
3. Run trading_bot.py
   ├─ Discover Spotify daily markets
   ├─ Score markets (microstructure + time-to-close)
   ├─ Optional Gemini override
   └─ Place trade (if conditions met)
4. Generate HTML report
5. Commit & push report
6. Upload logs as artifact
```

## Key Files

- `trading_bot.py` - Main bot logic
- `generate_report.py` - Creates HTML report from logs
- `trades.log` - All trade history (timestamp, market, action, status)
- `.github/workflows/trading_bot.yml` - GitHub Actions automation

## Risk Controls

- ✅ $1 cap per order
- ✅ Skips low-quality markets (wide spreads / close-to-close noise)
- ✅ Prevents conflicting positions
- ✅ Handles errors gracefully
- ✅ Logs everything for review

