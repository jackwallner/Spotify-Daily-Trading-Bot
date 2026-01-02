# Kworb Integration - Quick Start Guide

## What Changed?

The bot now uses **Kworb.net** to get Spotify chart data instead of the Spotify API.

### Benefits
- ✅ **No Spotify API credentials needed**
- ✅ **Real stream counts** (not just 0-100 popularity scores)
- ✅ **No API rate limits**
- ✅ **More accurate predictions**

## Testing the Integration

Run these tests to verify everything works:

```bash
# Test 1: Kworb scraper
python3 test_kworb_integration.py

# Test 2: Full workflow
python3 test_full_workflow.py

# Test 3: Comprehensive check
python3 -c "from kworb_scraper import get_chart_snapshot; print(get_chart_snapshot('US')[:3])"
```

## Running the Bot

### Prerequisites
1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure Kalshi API credentials in `.env`:
```bash
cp .env.example .env
# Edit .env and add your KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY
```

### Run the bot:
```bash
python3 trading_bot.py
```

## How It Works

1. **Kworb Scraper** (`kworb_scraper.py`):
   - Scrapes https://kworb.net/spotify/country/us_daily.html
   - Scrapes https://kworb.net/spotify/country/global_daily.html
   - Extracts rank, artist, title, and stream counts

2. **Signal Generation** (`spotify_daily_intelligence.py`):
   - Uses Kworb data instead of Spotify API
   - Analyzes stream counts to predict winners
   - Always picks #1 song (conservative strategy)
   - Logs volatility when #2 is close

3. **Trading** (`trading_bot.py`):
   - Matches predicted song to Kalshi market
   - Places $1 max trades on YES contracts
   - Logs all decisions to `trades.jsonl`

## Data Sources

### US Chart
- URL: https://kworb.net/spotify/country/us_daily.html
- Updates: Daily
- Data: Top 50 songs with daily stream counts

### Global Chart
- URL: https://kworb.net/spotify/country/global_daily.html
- Updates: Daily
- Data: Top 50 songs with daily stream counts

## Troubleshooting

### "Could not scrape chart"
- Check internet connection
- Kworb might be temporarily down
- Try again in a few minutes

### "Insufficient chart data"
- Kworb returned less than 2 tracks
- This is rare but can happen during updates
- Retry after 5-10 minutes

### "No market match found"
- The predicted song doesn't match any Kalshi contracts
- This is expected when Kalshi hasn't created a market for that song
- Bot will skip trading and log the decision

## Configuration

### Environment Variables

```bash
# Kalshi API (required)
KALSHI_API_KEY_ID=your_key_here
KALSHI_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----...-----END PRIVATE KEY-----

# Stream delta threshold (optional, default: 5.0)
KWORB_STREAM_DELTA_THRESHOLD_PCT=5.0

# Market date override (optional, format: YYmonDD)
SPOTIFY_MARKET_DATE=26jan02
```

## Migration from Spotify API

If you were using the old Spotify API version:

1. **Remove** Spotify credentials from `.env`:
   - Delete `SPOTIFY_CLIENT_ID`
   - Delete `SPOTIFY_CLIENT_SECRET`

2. **Update** dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. **Test** the new integration:
   ```bash
   python3 test_kworb_integration.py
   ```

That's it! The bot now uses Kworb automatically.

## Performance

- **Scraping time**: ~2-3 seconds per chart
- **Data freshness**: Updated daily on Kworb
- **Reliability**: No API rate limits or authentication issues

## Support

For issues or questions:
1. Check `KWORB_MIGRATION_SUMMARY.md` for detailed changes
2. Run test suite to verify integration
3. Check logs in `trades.jsonl` for decision history

---

**Status**: ✅ Production Ready  
**Last Updated**: January 2, 2026
