#!/usr/bin/env python3
"""
Model Analyzer - Gemini-Powered Analysis (NO AUTO-TUNING)

This module analyzes performance and logs insights.
It does NOT auto-tune the model - you control model_config.json manually.

Flow:
1. Analyze recent trade performance
2. Generate AI insights about what's working/not working  
3. Append insights to ai_insights.jsonl (never overwrite)
4. Display insights in index.html

The model factors stay fixed until YOU change them in model_config.json.
"""

import json
import os
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# File paths
MODEL_CONFIG_PATH = Path(__file__).parent / "model_config.json"
TRADES_LOG_PATH = Path(__file__).parent / "trades.jsonl"
AI_INSIGHTS_LOG = Path(__file__).parent / "ai_insights.jsonl"


def load_model_config() -> Dict:
    """Load the current model config (read-only, no modifications)."""
    try:
        with open(MODEL_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except:
        return {}


def load_recent_trades(hours: int = 48) -> list:
    """Load trades from the last N hours."""
    trades = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    if not TRADES_LOG_PATH.exists():
        return []
    
    try:
        with open(TRADES_LOG_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    trade = json.loads(line)
                    ts_str = trade.get('timestamp', '')
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        except:
                            ts = datetime.now(timezone.utc)
                        if ts >= cutoff:
                            trades.append(trade)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.warning(f"Error loading trades: {e}")
    
    return trades


def analyze_performance(trades: list) -> Dict:
    """Analyze recent trading performance."""
    if not trades:
        return {'total': 0, 'executed': 0, 'wins': 0, 'losses': 0, 'pending': 0, 'skips': 0}
    
    executed = [t for t in trades if t.get('order_id')]
    skips = [t for t in trades if not t.get('order_id')]
    
    wins = 0
    losses = 0
    pending = 0
    
    for t in executed:
        settlement = t.get('settlement', {})
        status = settlement.get('status', 'Unknown')
        if status == 'Won':
            wins += 1
        elif status == 'Lost':
            losses += 1
        else:
            pending += 1
    
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0
    
    return {
        'total': len(trades),
        'executed': len(executed),
        'skips': len(skips),
        'wins': wins,
        'losses': losses,
        'pending': pending,
        'win_rate': win_rate
    }


def append_insight(insight: Dict) -> None:
    """Append an insight to the log (never overwrites)."""
    insight['timestamp'] = datetime.now(timezone.utc).isoformat()
    
    try:
        with open(AI_INSIGHTS_LOG, 'a') as f:
            f.write(json.dumps(insight) + '\n')
        logger.info(f"[AI INSIGHTS] Appended insight: {insight.get('type', 'unknown')}")
    except Exception as e:
        logger.warning(f"Failed to append insight: {e}")


def load_recent_insights(count: int = 10) -> list:
    """Load the most recent N insights."""
    insights = []
    
    if not AI_INSIGHTS_LOG.exists():
        return []
    
    try:
        with open(AI_INSIGHTS_LOG, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        insights.append(json.loads(line))
                    except:
                        continue
    except:
        pass
    
    return insights[-count:]  # Return last N


def generate_run_analysis(trades: list, performance: Dict) -> Optional[Dict]:
    """Generate AI analysis for this run (called at start of each run)."""
    api_key = os.getenv('GEMINI_API_KEY')
    
    if not api_key:
        return None
    
    config = load_model_config()
    factors = config.get('factors', {})
    
    # Build trade summary
    recent_executed = [t for t in trades if t.get('order_id')][-10:]
    trade_lines = []
    for t in recent_executed:
        action = t.get('action', 'N/A')
        settlement = t.get('settlement', {})
        status = settlement.get('status', 'Pending')
        decision_log = t.get('decision_log', {})
        edge = decision_log.get('edge', {})
        edge_pct = edge.get('edge_percent', 0) if isinstance(edge, dict) else 0
        trade_lines.append(f"  {action} - {status} (edge: {edge_pct:.1%})")
    
    prompt = f"""Analyze this Kalshi BTC trading bot's recent performance.

CURRENT MODEL FACTORS (fixed, not auto-tuned):
- min_edge_percent: {factors.get('min_edge_percent', 0.01)} (trades when edge >= this)
- critical_distance: ${factors.get('critical_distance_dollars', 100)} (skips if BTC within this of strike)
- safe_distance: ${factors.get('safe_distance_dollars', 500)} (confident if beyond this)

RECENT PERFORMANCE (last 48h):
- Executed: {performance['executed']} trades
- Won: {performance['wins']} | Lost: {performance['losses']} | Pending: {performance['pending']}
- Win Rate: {performance['win_rate']*100:.1f}%
- Skipped: {performance['skips']} opportunities

RECENT TRADES:
{chr(10).join(trade_lines) if trade_lines else '  No recent executed trades'}

Provide a brief analysis (2-3 sentences) of:
1. What's working or not working
2. One specific suggestion for the human to consider adjusting

Format as JSON:
{{"analysis": "...", "suggestion": "..."}}
"""

    try:
        # Model fallback list ordered by rate limits (RPM)
        models = [
            'gemini-2.5-flash-lite',  # 7 RPM
            'gemini-2.5-flash',       # 3 RPM
            'gemma-3-27b-it',         # 4 RPM
            'gemma-3-4b-it',          # 2 RPM
            'gemma-3-12b-it',         # 1 RPM
            'gemma-3-1b-it'           # Last resort
        ]
        for model in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                response = requests.post(
                    url,
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    headers={"Content-Type": "application/json"},
                    timeout=15
                )
                response.raise_for_status()
                
                result = response.json()
                if 'candidates' in result and len(result['candidates']) > 0:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    
                    import re
                    json_match = re.search(r'\{.*\}', text, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        return {
                            'type': 'run_analysis',
                            'analysis': parsed.get('analysis', ''),
                            'suggestion': parsed.get('suggestion', ''),
                            'performance': performance,
                            'model': model
                        }
            except Exception as e:
                logger.debug(f"Model {model} failed: {e}")
                continue
    except Exception as e:
        logger.warning(f"Failed to generate analysis: {e}")
    
    return None


def generate_settlement_analysis(trade: Dict, outcome: str) -> Optional[Dict]:
    """Generate AI analysis when a trade settles (called by report generator)."""
    api_key = os.getenv('GEMINI_API_KEY')
    
    if not api_key:
        return None
    
    decision_log = trade.get('decision_log', {})
    action = trade.get('action', 'N/A')
    edge = decision_log.get('edge', {})
    edge_pct = edge.get('edge_percent', 0) if isinstance(edge, dict) else 0
    distance = decision_log.get('distance', {})
    
    prompt = f"""A Kalshi BTC trade just settled. Analyze what happened.

TRADE DETAILS:
- Action: {action}
- Outcome: {outcome}
- Edge at entry: {edge_pct:.1%}
- Distance from strike: {distance}

Why did this trade {outcome.lower()}? What can we learn?

Format as JSON (1-2 sentences each):
{{"why": "...", "lesson": "..."}}
"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={api_key}"
        response = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()
        
        result = response.json()
        if 'candidates' in result and len(result['candidates']) > 0:
            text = result['candidates'][0]['content']['parts'][0]['text']
            
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return {
                    'type': 'settlement_analysis',
                    'outcome': outcome,
                    'trade_action': action,
                    'why': parsed.get('why', ''),
                    'lesson': parsed.get('lesson', ''),
                    'market': trade.get('market', 'N/A')
                }
    except Exception as e:
        logger.debug(f"Settlement analysis failed: {e}")
    
    return None


def run_analysis() -> Dict:
    """
    Main entry point - analyze performance and log insights.
    Called at start of each trading run.
    
    Returns current model config (read-only, for reference).
    """
    print("\n" + "="*70)
    print("[MODEL ANALYZER] Analyzing performance (no auto-tuning)")
    print("="*70)
    
    # Load trades and analyze
    trades = load_recent_trades(hours=48)
    performance = analyze_performance(trades)
    
    print(f"[PERFORMANCE] Last 48h: {performance['executed']} trades, {performance['wins']}W/{performance['losses']}L, {performance['win_rate']*100:.1f}% win rate")
    
    # Generate and log AI analysis
    analysis = generate_run_analysis(trades, performance)
    if analysis:
        append_insight(analysis)
        print(f"[AI INSIGHT] {analysis.get('analysis', '')[:100]}...")
        if analysis.get('suggestion'):
            print(f"[SUGGESTION] {analysis.get('suggestion', '')}")
    else:
        print("[AI INSIGHT] Skipped (no API key or error)")
    
    # Return current config (read-only)
    config = load_model_config()
    print(f"[MODEL] Using fixed factors: min_edge={config.get('factors', {}).get('min_edge_percent', 0.01)}, critical_dist=${config.get('factors', {}).get('critical_distance_dollars', 100)}")
    print("="*70 + "\n")
    
    return config


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = run_analysis()
    print("\nCurrent model config:")
    print(json.dumps(config, indent=2))
