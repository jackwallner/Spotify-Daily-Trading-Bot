# Correct Testing Methodology ✅

**Updated:** January 4, 2026  
**Schedule:** 4:00 PM ET daily

---

## The Right Way to Test

### ❌ WRONG: Test predictions against current snapshot
```
4 PM: Make predictions
4 PM: Check current #1 → Compare immediately
Problem: This just tests if we can read Kworb, not if we predict the winner
```

### ✅ CORRECT: Test predictions against future outcome
```
Day 1 @ 4 PM: Make predictions → Save to file
Day 2 @ 4 PM: Check actual winner from Day 1 → Validate
This tests: Can we predict what WILL win, not what IS winning
```

---

## Why This Matters

### The Real Trading Scenario

**4:00 PM ET (Prediction Time):**
- Charts are still updating
- Early trades get better prices
- We need to predict what will be #1 by end of day

**Next Day (Validation Time):**
- Chart has settled
- Actual winner is clear
- We can measure accuracy

### Example

**Friday 4 PM predictions:**
- Multi-source predicts: "Man I Need"
- Kworb-only predicts: "End of Beginning"

**Saturday check (actual Friday winner):**
- Actual #1: "End of Beginning" ✓ Kworb wins
- This proves Kworb was more accurate at prediction time

---

## Testing Protocol

### Daily Script (Automated)

```bash
# Run daily at 4 PM ET
python3 validate_at_prediction_time.py
```

**What it does:**
1. **Validates yesterday** (checks which system was correct)
2. **Makes today's predictions** (saves for tomorrow's validation)
3. **Calculates overall accuracy** (after 7+ days)

### Manual Testing

```bash
# Force predictions now (regardless of time)
python3 validate_at_prediction_time.py --predict

# Only validate previous day
python3 validate_at_prediction_time.py --validate

# Do both
python3 validate_at_prediction_time.py --force
```

---

## Data Structure

### Prediction File (`predictions_2026-01-04.json`)
```json
{
  "date": "2026-01-04",
  "prediction_time": "2026-01-04T16:00:00-05:00",
  "multi_source": {
    "top_pick": {
      "title": "Man I Need",
      "artist": "Olivia Dean",
      "score": 87.9,
      "confidence": 80
    },
    "top_20": [...]
  },
  "kworb_only": {
    "top_pick": {
      "title": "End of Beginning",
      "artist": "Djo",
      "daily_streams": 1378468
    },
    "top_20": [...]
  }
}
```

### Validation File (`validation_2026-01-04.json`)
```json
{
  "date": "2026-01-04",
  "prediction_time": "2026-01-04T16:00:00-05:00",
  "validation_time": "2026-01-05T16:00:00-05:00",
  "actual_winner": {
    "title": "End of Beginning",
    "artist": "Djo",
    "daily_streams": 1378468
  },
  "multi_source": {
    "correct": true,
    "rank": 2
  },
  "kworb_only": {
    "correct": true,
    "rank": 1
  },
  "winner": "kworb"
}
```

---

## Accuracy Calculation

### After 7+ Days

**Win Rates:**
- Multi-source: X/7 days (X%)
- Kworb-only: Y/7 days (Y%)
- Ties: Z/7 days
- Both failed: W/7 days

**Decision Criteria:**
- **Multi-source ≥ 60%** → Integrate
- **Kworb-only > Multi-source** → Keep current
- **Similar (<10% diff)** → Test longer or consider other factors

---

## GitHub Actions Schedule

### Updated Workflow

**Old schedule:**
```yaml
cron: '5 0 * * *'  # 7:05 PM ET (12:05 AM UTC next day)
```

**New schedule:**
```yaml
cron: '0 21 * * *'  # 4:00 PM ET (9:00 PM UTC during EST)
```

**Benefits:**
- 3+ hours earlier
- Better market prices
- More time for decisions

**Note:** During EDT (summer), adjust to `cron: '0 20 * * *'` for 4 PM EDT

---

## Current Status

### Day 1 Results (Today)

**Predictions made at 12:58 PM ET:**

| System | Top Pick | Score/Streams |
|--------|----------|---------------|
| **Multi-Source** | Man I Need - Olivia Dean | 87.9 score, 80% conf |
| **Kworb-Only** | End of Beginning - Djo | 1,378,468 streams |

**Validation:** Will check tomorrow at 4 PM ET

### Prediction History

Files stored in `prediction_history/`:
- `predictions_2026-01-04.json` ✓ Created
- `validation_2026-01-04.json` ⏳ Tomorrow

---

## Expected Timeline

### Week 1 Schedule

| Day | Date | Action |
|-----|------|--------|
| Sat | Jan 4 | ✓ Make predictions (done) |
| Sun | Jan 5 | Validate Jan 4 + Make Jan 5 predictions |
| Mon | Jan 6 | Validate Jan 5 + Make Jan 6 predictions |
| Tue | Jan 7 | Validate Jan 6 + Make Jan 7 predictions |
| Wed | Jan 8 | Validate Jan 7 + Make Jan 8 predictions |
| Thu | Jan 9 | Validate Jan 8 + Make Jan 9 predictions |
| Fri | Jan 10 | Validate Jan 9 + Make Jan 10 predictions |
| Sat | Jan 11 | **Validate Jan 10 + Calculate 7-day accuracy** |

### After 7 Days (Jan 11)

**Calculate:**
- Multi-source win rate
- Kworb-only win rate
- Overall accuracy

**Decide:**
- Integrate multi-source? (if ≥60% win rate)
- Keep Kworb-only? (if better)
- Test longer? (if inconclusive)

---

## Key Differences from Before

### What Changed

| Aspect | Before | Now |
|--------|--------|-----|
| **Timing** | 7:05 PM ET | 4:00 PM ET |
| **Testing** | Compare to current | Validate next day |
| **Methodology** | Snapshot comparison | Prediction → Outcome |
| **Data** | Single point | Historical tracking |
| **Decision** | Immediate | After 7 days |

### Why Better

1. **Tests actual prediction ability** (not current reading)
2. **Simulates real trading** (predict early, trade early)
3. **Builds historical data** (trends over time)
4. **Clear decision criteria** (60% threshold)
5. **Earlier trading** (3+ hours sooner)

---

## Validation Examples

### Scenario 1: Multi-source wins

```
Day 1 @ 4 PM predictions:
  Multi: "Song A" (rank #1)
  Kworb: "Song B" (rank #1)

Day 2 @ 4 PM check:
  Actual winner: "Song A" ✓ Multi wins
```

### Scenario 2: Kworb-only wins

```
Day 1 @ 4 PM predictions:
  Multi: "Song A" (rank #1)
  Kworb: "Song B" (rank #1)

Day 2 @ 4 PM check:
  Actual winner: "Song B" ✓ Kworb wins
```

### Scenario 3: Both correct, different ranks

```
Day 1 @ 4 PM predictions:
  Multi: "Song A" at rank #2
  Kworb: "Song A" at rank #1

Day 2 @ 4 PM check:
  Actual winner: "Song A" ✓ Kworb wins (ranked higher)
```

### Scenario 4: Both failed

```
Day 1 @ 4 PM predictions:
  Multi: "Song A" (rank #1)
  Kworb: "Song B" (rank #1)

Day 2 @ 4 PM check:
  Actual winner: "Song C" ✗ Both failed
```

---

## Commands Reference

### Daily Use

```bash
# Automated daily run (4 PM ET)
python3 validate_at_prediction_time.py

# Output:
# - Validates yesterday
# - Makes today's predictions
# - Shows overall stats (after 2+ days)
```

### Manual Testing

```bash
# Just make predictions
python3 validate_at_prediction_time.py --predict

# Just validate previous
python3 validate_at_prediction_time.py --validate

# Force both regardless of time
python3 validate_at_prediction_time.py --force
```

### View Results

```bash
# Today's predictions
cat prediction_history/predictions_$(date +%Y-%m-%d).json | jq '.'

# Yesterday's validation
cat prediction_history/validation_$(date -d yesterday +%Y-%m-%d).json | jq '.'

# List all results
ls prediction_history/

# Count days tested
ls prediction_history/validation_*.json | wc -l
```

---

## Success Criteria

### After 7 Days

**Integrate multi-source if:**
- ✅ Win rate ≥ 60% (4+ days out of 7)
- ✅ Consistently ranks winner higher
- ✅ No critical failures or bugs
- ✅ Data sources reliable

**Keep Kworb-only if:**
- ❌ Multi-source win rate < 60%
- ❌ Kworb-only more accurate
- ❌ Multi-source has frequent failures
- ❌ No clear improvement

**Test longer if:**
- ⚖️ Win rates within 10%
- ⚖️ Inconclusive results
- ⚖️ Need more data points

---

## Next Steps

### Immediate (Today)

- ✅ Predictions made for Jan 4
- ✅ Workflow updated to 4 PM ET
- ✅ Testing framework ready

### Tomorrow (Jan 5)

- Run script at 4 PM ET
- Validate Jan 4 predictions
- Make Jan 5 predictions
- **First validation result!**

### Week 1 (Jan 5-11)

- Run daily at 4 PM ET
- Build prediction history
- Track accuracy metrics

### Decision Point (Jan 11)

- Calculate 7-day win rates
- **Decide: Integrate or keep current**
- Document results

---

## Bottom Line

**We now have:**
1. ✅ Correct testing methodology (predict early, validate later)
2. ✅ Earlier schedule (4 PM vs 7 PM ET)
3. ✅ Automated validation script
4. ✅ Clear decision criteria (60% threshold)
5. ✅ First prediction made (Jan 4)

**Next:** Run daily for 7 days, then decide based on actual accuracy data.

**No guessing, no assumptions, just real performance metrics.** 📊
