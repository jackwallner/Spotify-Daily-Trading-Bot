# Data Quality & Inconsistency Debug Guide

## Problem Identified
The bot was showing inconsistent trading behavior with scores clustering around the neutral zone (45-55):
- Run #49: 45.7 → NO TRADE
- Run #48: 48.7 → NO TRADE
- Run #47: 47.2 → NO TRADE
- Run #46: <45 → Buy NO (execution)
- Run #45: 45.3 → NO TRADE

This pattern suggests **API calls failing silently** and defaulting to neutral scores.

## Root Cause
When individual signal calculations fail (API timeouts, empty responses, network errors), they return **50.0 (neutral)** as a fallback:

```
get_candlestick_momentum()  → Returns 50.0 on error
get_orderbook_score()       → Returns 50.0 on error
get_trade_flow_score()      → Returns 50.0 on error
get_liquidity_score()       → Returns 50.0 on error
```

**When ALL 5 return 50.0:**
- Weighted composite = ~50.0
- Small deviations → 45-55 neutral zone
- Result = NO TRADE (by design)

**When 1-2 get real data:**
- Composite shifts based on those signals
- Can cross into 55+ (BUY YES) or <45 (BUY NO)
- Result = EXECUTION

This makes the bot appear inconsistent, but it's actually **working correctly given the poor data quality**.

## Solution Implemented

### 1. Data Quality Detection
Added warning when all signals cluster near neutral:
```python
all_near_neutral = all(45 <= s <= 55 for s in scores)
if all_near_neutral:
    print(f"⚠️ [DATA QUALITY] All signals near neutral (45-55): {scores}")
    confidence = min(confidence, 20)  # Cap confidence at 20%
```

### 2. Better Error Logging
Each signal function now logs specifically when data is missing:
```
⚠️ [MOMENTUM] No candlestick data for {ticker} - API call failed or returned None
⚠️ [ORDERBOOK] Market prices: yes_bid=N/A, yes_ask=N/A - empty response
⚠️ [TRADE_FLOW] No trade data for {ticker} - insufficient data
```

### 3. Timeout Protection
Added timeouts to prevent hanging on unresponsive APIs:
```python
candlesticks_response = client.get_market_candlesticks(
    series_ticker=series_ticker,
    ticker=market_ticker,
    start_ts=...,
    end_ts=...,
    period_interval=1,
    timeout=5  # 5 second timeout
)
```

### 4. Confidence Cap
When data quality is poor, confidence is capped at 20% instead of false confidence in unreliable scores.

## How to Debug Live

### Check Logs
```bash
# Look for these warning patterns:
tail -f logs/*.log | grep "DATA QUALITY"
tail -f logs/*.log | grep "⚠️"
tail -f logs/*.log | grep "API timeout"
```

### Identify Problem Areas
1. **If MOMENTUM warnings dominate:** Candlestick API or market data issues
2. **If ORDERBOOK warnings dominate:** Market snapshot API issues
3. **If TRADE_FLOW warnings dominate:** Recent trades API or rate limiting
4. **If ALL warnings:** Kalshi API is having widespread issues

### Expected Behavior

**Good Data Quality:**
- Individual signals range from 30-70 (not all 50)
- Composite scores vary widely (not 45-55)
- Confidence > 50%
- Consistent trading decisions

**Poor Data Quality:**
```
⚠️ [DATA QUALITY] All signals near neutral (45-55): [50.0, 50.0, 50.0, 50.0]
⚠️ Composite score 50.2 may not be reliable
⚠️ Confidence capped at 20%
```

## Potential Root Causes

### 1. Market Data Availability
- Market may not have opened yet
- Market may have closed
- No recent trades in 15-minute window
- Not enough candlestick data

### 2. API Issues
- **Rate limiting** on specific endpoints
- **Slow responses** (>5 seconds)
- **Network timeouts**
- **Kalshi API maintenance**

### 3. Configuration Issues
- Wrong market ticker format
- Series ticker extraction failing
- model_config.json missing or invalid

## Action Items to Improve Consistency

### Option 1: Verify Kalshi API Connectivity
```bash
python3 test_market_discovery.py
python3 test_api_calls.py
```

Check if individual API endpoints are responding.

### Option 2: Add Retry Logic
Wrap API calls with exponential backoff:
```python
def api_call_with_retry(func, *args, max_retries=3, timeout=5):
    for attempt in range(max_retries):
        try:
            return func(*args, timeout=timeout)
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(f"Attempt {attempt+1} failed, retrying in {wait_time}s...")
                time.sleep(wait_time)
    return None  # Return neutral after all retries exhausted
```

### Option 3: Use Cached Data
Store previous signal calculations and use if fresh data unavailable:
```python
# If API fails, use signal from 1 minute ago rather than 50.0
# Provides continuity in scoring
```

### Option 4: Market-Specific Thresholds
Some markets may be less active. Adjust neutral zone per market:
```python
# Active markets: 45-55 neutral
# Slow markets: 40-60 neutral (larger range)
```

## Monitoring Checklist

- [ ] Check logs for `⚠️ [DATA QUALITY]` warnings
- [ ] Verify Kalshi API is responsive
- [ ] Check confidence levels (should be >50% for good trades)
- [ ] Monitor signal distribution (should vary 20-80, not 45-55)
- [ ] Track trade outcomes (if all NO TRADE, data quality is poor)

## Next Steps

1. Run bot with improved logging for 1-2 hours
2. Collect all warning messages
3. Identify which API endpoints are consistently failing
4. Implement endpoint-specific retry logic
5. Re-test consistency with fixes in place

---
Last Updated: Dec 30, 2025
Issue: Inconsistent composite scores clustering at 45-55 (neutral zone)
Status: Root cause identified, data quality warnings added
