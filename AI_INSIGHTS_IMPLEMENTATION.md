# AI Performance Insights - Iterative Learning System

## Overview
The trading bot uses an iterative learning cycle where each run analyzes previous trading results and uses those insights to guide future trading decisions. This creates a feedback loop that improves predictions over time.

## System Architecture

### 1. **Insights Generation** (`generate_report.py`)
When the report is generated (triggered after each trading cycle):
- **Input**: Previous resolved trades from `trades.jsonl`
- **Process**: Calls `generate_results_analysis()` via Gemini API
- **Output**: Structured analysis with:
  - `analysis`: High-level performance summary
  - `key_insights`: Patterns and correlations discovered
  - `recommendations`: Strategy adjustments suggested
- **Written to**: `docs/index.html` in the "Overview" tab's "AI Performance Insights" section

### 2. **Insights Extraction** (`market_intelligence.py`)
When the trading bot runs (every 15 minutes):
- **Trigger**: `extract_ai_performance_insights()` is called
- **Source**: Reads latest `docs/index.html`
- **Process**: Parses HTML with regex to extract the three sections
- **Output**: Dictionary with cleaned insights text
- **Used by**: Passed to Gemini in the market decision prompt

### 3. **Integration into Decisions** (`market_intelligence.py`)
For each market decision:
- **Input**: Extracted AI insights (if available)
- **Context**: Added to Gemini prompt as:
  ```
  AI PERFORMANCE INSIGHTS FROM PRIOR RUNS:
  Analysis: [previous cycle analysis]
  Key Insights: [discovered patterns]
  Current Recommendations: [suggested adjustments]
  
  Use these insights to inform your decision...
  ```
- **Impact**: Gemini considers learned patterns when making new predictions

## Learning Cycle Phases

### Phase 1: Bootstrap (Cycle 1-2)
- **Cycle 1**: No insights exist yet (first run)
  - Bot makes decisions based on signals only
  - Report generated but minimal resolved trades
- **Cycle 2**: 
  - Bot still has limited context
  - Report analyzes Cycle 1 results
  - Insights begin to form

### Phase 2: Active Learning (Cycle 3+)
- **Cycle N**: 
  - Bot extracts insights from Cycle N-1 report
  - Gemini receives: signals + prior insights
  - Makes smarter predictions using learned patterns
- **Report after Cycle N**:
  - Analyzes results of N's decisions
  - Generates refined insights
  - Available for Cycle N+1

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│ CYCLE N: TRADING BOT RUNS (every 15 min)               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. Reads: docs/index.html (Cycle N-1 report)         │
│     ↓                                                   │
│  2. Extracts: AI Performance Insights (via regex)      │
│     ↓                                                   │
│  3. Queries: Kalshi API for market signals             │
│     ↓                                                   │
│  4. Calls: Gemini (with signals + insights)           │
│     ↓                                                   │
│  5. Makes: Trading decisions (BUY/SKIP)               │
│     ↓                                                   │
│  6. Writes: trades.jsonl                               │
│                                                         │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│ CYCLE N: REPORT GENERATION (after trading completes)   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. Reads: trades.jsonl                                │
│     ↓                                                   │
│  2. Queries: Kalshi API for market resolutions        │
│     ↓                                                   │
│  3. Analyzes: Trade outcomes (wins/losses)            │
│     ↓                                                   │
│  4. Calls: Gemini ("analyze these results")           │
│     ↓                                                   │
│  5. Generates: AI Performance Insights                │
│     Analysis + Key Insights + Recommendations          │
│     ↓                                                   │
│  6. Writes: docs/index.html                            │
│     (Ready for Cycle N+1 extraction)                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
                           ↓
                    (Repeats for Cycle N+1)
```

## Key Implementation Details

### Regex Extraction Pattern
```python
# Looks for HTML structure in generate_report.py output:
<strong>Analysis:</strong>{content}<div class="ai-analysis-text"...>
<strong>Key Insights:</strong>{content}<div class="ai-analysis-text"...>
<strong>Recommendations:</strong>{content}</div></div>
```

### Gemini Prompt Integration
The extracted insights are formatted as context and added to every Gemini decision call:
- Location: `market_intelligence.py` lines 576-593
- Integration point: Called BEFORE building main prompt
- Usage: Informs Gemini about what worked/didn't work previously

### API Key Requirement
- **For Insights Generation**: `GEMINI_API_KEY` must be set in environment
- **Provided by**: GitHub Actions secrets or local `.env` file
- **Fallback**: If not available, report generates without insights (graceful degradation)

## Expected Behavior Over Time

### Week 1-2 (Bootstrap):
- Win rate: ~50% (random signal match)
- Insights: Limited (few resolved trades)
- Improvements: Minimal

### Week 2-4 (Learning):
- Win rate: Gradual increase toward 55-65%
- Insights: Patterns emerge ("when X score high, I'm usually right")
- Improvements: Bot skips more bad odds, takes better trades

### Week 4+ (Optimization):
- Win rate: 60-70%+ (with good signals)
- Insights: Sophisticated ("when volatility high AND trend strong, I win")
- Improvements: Continuous refinement based on market conditions

## Troubleshooting

### Insights Not Generating
**Symptom**: "Gemini analysis skipped (API key not configured)"
- **Fix**: Set `GEMINI_API_KEY` environment variable

### Insights Not Appearing in Report
**Symptom**: "AI Performance Insights" section missing from HTML
- **Cause**: No resolved trades yet (normal on first few cycles)
- **Timeline**: Appears after ~20-30 trades resolve

### Insights Not Extracted by Bot
**Symptom**: Bot logs show "Skipped extraction"
- **Check**: Verify regex pattern matches current HTML structure
- **Debug**: Run `extract_ai_performance_insights()` manually

## Future Enhancements

1. **Persistent Learning**: Store insights in database for longer-term patterns
2. **A/B Testing**: Compare decisions with/without insights
3. **Custom Thresholds**: Adjust score thresholds based on insights
4. **Multi-Market Learning**: Cross-market pattern recognition
5. **Confidence Scoring**: Weight insights by their predictive accuracy
