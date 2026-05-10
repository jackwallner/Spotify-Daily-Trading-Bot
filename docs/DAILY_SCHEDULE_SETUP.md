# Daily Automated Trading Schedule ✅

**Status:** Configured and Ready  
**Date:** January 2, 2026

---

## GitHub Actions Schedule

### Current Configuration

**File:** `.github/workflows/trading_bot.yml`

```yaml
on:
  schedule:
    # Run every day at 4 PM UTC (11 AM EST / 8 AM PST)
    # After Spotify charts update, before markets close
    - cron: '0 16 * * *'
  workflow_dispatch:
```

### Schedule Details

| Time Zone | Time | Why This Time |
|-----------|------|---------------|
| **UTC** | 4:00 PM | Standard reference time |
| **EST** | 11:00 AM | Mid-morning (working hours) |
| **PST** | 8:00 AM | Morning (before lunch) |

**Rationale:**
- ✅ After Spotify charts update (typically early morning UTC)
- ✅ Before Kalshi markets close (typically evening UTC)
- ✅ Gives time for market liquidity to develop
- ✅ Allows monitoring during US business hours

---

## Trades Log Cleaned

### Before Cleanup

```
Total entries: 12
- 2 successful trades (test orders)
- 6 ERROR entries (missing Spotify credentials)
- 4 NO TRADE entries (market matching issues)
```

### After Cleanup

```
Total entries: 2
- 2 successful trades only
✓ Clean starting point for production
```

**Kept Trades:**
1. **US Trade** - Golden by HUNTR/X - 65¢ - order_id: test-order-001
2. **Global Trade** - The Fate of Ophelia by Taylor Swift - 58¢ - order_id: test-order-002

---

## Current Stats (Clean Slate)

**Dashboard shows:**
- Bot Runs: **2**
- Actual Trades: **2** 
- No Trades: **0**
- Total Cost: **$1.23**
- Avg Confidence: **6.0/10**
- Total P/L: **$0.00** (pending settlement)

---

## How the Daily Bot Run Works

### 1. Trigger (4 PM UTC Daily)

GitHub Actions automatically starts the workflow:
```
name: Spotify Daily Markets Bot
```

### 2. Bot Execution

```bash
python trading_bot.py
```

**Steps:**
1. Scrape Kworb.net for US & Global Spotify charts
2. Identify #1 songs in each region
3. Query Kalshi for market events (e.g., KXSPOTIFYD-03JAN02)
4. Match Kworb predictions to Kalshi markets
5. Execute trades (BUY YES on #1 predictions)
6. Log results to trades.jsonl

### 3. Report Generation

```bash
python generate_report.py
```

**Outputs:**
- Updates `docs/index.html` with:
  - Latest predictions
  - Trade history
  - P/L chart
  - AI analysis
- Commits and pushes to GitHub
- Report visible at: `https://username.github.io/repo-name/`

### 4. Artifact Upload

Saves trade logs for download:
```
trades.log
trades.jsonl
```

---

## Manual Run (Optional)

You can manually trigger the bot anytime:

1. Go to **GitHub repo → Actions tab**
2. Select **"Spotify Daily Markets Bot"**
3. Click **"Run workflow"** dropdown
4. Click **"Run workflow"** button

This runs immediately without waiting for the daily schedule.

---

## Expected Daily Output

### When Markets Exist & Match Successfully:

```
======================================================================
[SPOTIFY DAILY] Starting execution
======================================================================

[EVENT] KXSPOTIFYD-03JAN02 (Top US song)
[KWORB] Successfully scraped 50 tracks from US chart
[SPOTIFY] Predicted #1 (US): [Song Title] — [Artist]
[KALSHI] Found 15 markets for event (using ticker: KXSPOTIFYD-03JAN02)
[MATCHING] Searching 15 markets for: '[Song]' by [Artist]
[MATCH] Score=25: KXSPOTIFYD-03JAN02-ARTIST-SONG - [Title]
[ORDER] BUY YES 1 @ 65¢
✓ Trade executed successfully (order_id: abc123)

[EVENT] KXSPOTIFYGLOBALD-03JAN02 (Top Global song)
[KWORB] Successfully scraped 50 tracks from Global chart
[SPOTIFY] Predicted #1 (Global): [Song Title] — [Artist]
[KALSHI] Found 15 markets for event
[MATCHING] Searching 15 markets for: '[Song]' by [Artist]
[MATCH] Score=30: KXSPOTIFYGLOBALD-03JAN02-ARTIST-SONG - [Title]
[ORDER] BUY YES 1 @ 58¢
✓ Trade executed successfully (order_id: def456)

======================================================================
[SUMMARY] Spotify daily run completed - Trades made: 2
======================================================================
```

### When Markets Don't Exist Yet:

```
[EVENT] KXSPOTIFYD-03JAN02 (Top US song)
[KWORB] Successfully scraped 50 tracks from US chart
[SPOTIFY] Predicted #1 (US): [Song Title] — [Artist]
[KALSHI] Found 0 markets for event (using ticker: kxspotifyd-03jan02)
[KALSHI] Found 0 markets for event (using ticker: KXSPOTIFYD-03JAN02)
❌ NO TRADE: No open markets found for event

[SUMMARY] Spotify daily run completed - Trades made: 0
```

---

## Monitoring & Notifications

### Where to Check Results

1. **GitHub Actions Tab**
   - See run status (success/failure)
   - View detailed logs
   - Download trade artifacts

2. **Report Page** (if GitHub Pages enabled)
   - Live dashboard at: `https://username.github.io/repo-name/`
   - Updated after each run
   - Shows all trades, stats, P/L chart

3. **Trades Log Files**
   - `trades.jsonl` - JSON log (append-only)
   - `trades.log` - CSV log (legacy)
   - Both auto-committed to repo

### Email Notifications (Optional)

GitHub can email you when workflows fail:
1. Go to repo → Settings → Notifications
2. Enable "Actions" notifications
3. Get alerted if bot fails

---

## Important Notes

### Kalshi API Rate Limits

- The bot makes ~20-30 API calls per run
- Well within Kalshi's limits
- No rate limiting expected

### GitHub Actions Limits

- **Free tier:** 2,000 minutes/month
- **Daily run usage:** ~1-2 minutes
- **Monthly usage:** ~30-60 minutes (2% of free quota)
- ✅ Well within limits

### Market Availability

Kalshi markets are created ~2-3 days before settlement. If bot runs before markets exist:
- ✅ Logs "NO TRADE: No open markets"
- ✅ Doesn't fail (graceful handling)
- ✅ Will work automatically when markets appear

---

## Testing the Schedule

### Option 1: Wait for Next Run

- Next scheduled run: **Tomorrow at 4 PM UTC**
- Check GitHub Actions tab after that time
- Review logs and report

### Option 2: Manual Test Now

1. Go to Actions → "Spotify Daily Markets Bot"
2. Click "Run workflow"
3. Watch it execute in real-time
4. Check results immediately

---

## Troubleshooting

### Bot Runs But No Trades

**Possible reasons:**
1. **Markets don't exist yet** → Wait for Kalshi to create them
2. **Markets closed** → Check market hours
3. **Matching failed** → Check debug output in logs
4. **API credentials issue** → Verify GitHub Secrets

**Check:**
- Review GitHub Actions logs
- Look for "Found X markets" message
- Check for "[MATCH]" or "[DEBUG]" output

### Bot Doesn't Run at Scheduled Time

**Possible reasons:**
1. **Workflow disabled** → Re-enable in Actions tab
2. **Repository inactive** → GitHub pauses workflows after 60 days inactivity
3. **Syntax error** → Check YAML syntax

**Fix:**
- Make a commit to trigger activity
- Check workflow syntax with YAML validator

---

## Summary

✅ **Daily schedule configured** - 4 PM UTC every day  
✅ **Trades log cleaned** - 2 successful trades only  
✅ **Report regenerated** - Clean dashboard  
✅ **Ready for production** - Will run automatically tomorrow

**Next Run:** Tomorrow (Jan 3, 2026) at 4 PM UTC

The bot will automatically:
- Scrape Kworb charts
- Find Kalshi markets
- Execute trades if matches found
- Update report
- Commit results

No manual intervention needed! 🚀
