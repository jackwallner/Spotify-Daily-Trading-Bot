#!/usr/bin/env python3
"""Centralized Gemini (Generative Language) API integration.

All Gemini API calls for the trading bot and report generation.
"""
import os
import requests
import json
from datetime import datetime
import time


def print_rate_limit_status(retry_after=None):
    """Print helpful message about rate limiting."""
    print("\n⚠️  GEMINI API RATE LIMIT EXCEEDED")
    print("━" * 60)
    print("Free tier limit: 20 requests per day")
    print("Status: All available models are currently rate-limited")
    print("Solution: Wait for quota reset (approximately 24 hours from limit time)")
    print("Alternative: Upgrade to Gemini API paid tier for higher limits")
    print("━" * 60 + "\n")
    if retry_after:
        try:
            seconds = int(retry_after)
            minutes = seconds // 60
            print(f"Retry after: {minutes} minutes {seconds % 60} seconds\n")
        except:
            pass


# Global tracking for AI analysis attempts and errors
class AIAnalysisTracker:
    """Track all AI analysis attempts, successes, and detailed errors."""
    def __init__(self):
        self.attempts = []  # List of {type, model, status, error, headers}
        self.summary = {}   # Dict with status counts
    
    def add_attempt(self, analysis_type, model, status, error=None, headers=None):
        """Record an attempt."""
        self.attempts.append({
            'type': analysis_type,
            'model': model,
            'status': status,  # 'success', 'rate_limit', 'auth_error', 'model_not_found', 'other_error'
            'error': error,
            'headers': headers,
            'timestamp': datetime.now().isoformat()
        })
    
    def get_rate_limit_info(self):
        """Extract rate limit info from tracked responses."""
        for attempt in self.attempts:
            if attempt['status'] == 'rate_limit' and attempt['headers']:
                headers = attempt['headers']
                return {
                    'retry_after': headers.get('Retry-After'),
                    'rate_limit_remaining': headers.get('x-goog-ratelimit-remaining'),
                    'rate_limit_reset': headers.get('x-goog-ratelimit-reset')
                }
        return {}
    
    def to_dict(self):
        """Convert to dict for storage in HTML."""
        return {
            'attempts': self.attempts,
            'rate_limit_info': self.get_rate_limit_info()
        }


# Global tracker instance
ai_tracker = AIAnalysisTracker()


def generate_gemini_analysis(run_trades, sentiment_value):
    """
    Generate AI analysis using Gemini API explaining trading decisions.
    
    Args:
        run_trades: List of trade dicts for this run
        sentiment_value: Sentiment value (0-100) from Fear & Greed Index
    
    Returns:
        dict with 'analysis' (str) and 'confidence' (int 1-10), or None if API unavailable
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("⚠ Warning: GEMINI_API_KEY not found in environment")
        return None
    
    print(f"✓ Checking for GEMINI_API_KEY: Found ✓")
    
    # Build context from trades
    btc_trades = [t for t in run_trades if t.get('asset') == 'BTC']
    eth_trades = [t for t in run_trades if t.get('asset') == 'ETH']
    
    trades_summary = []
    if btc_trades:
        for t in btc_trades:
            decision_log = t.get('decision_log', {})
            composite = decision_log.get('composite_score', 'N/A') if isinstance(decision_log, dict) else 'N/A'
            trades_summary.append(f"BTC: {t.get('action', 'N/A')} - {t.get('status', 'N/A')} (Score: {composite})")
    if eth_trades:
        for t in eth_trades:
            decision_log = t.get('decision_log', {})
            composite = decision_log.get('composite_score', 'N/A') if isinstance(decision_log, dict) else 'N/A'
            trades_summary.append(f"ETH: {t.get('action', 'N/A')} - {t.get('status', 'N/A')} (Score: {composite})")
    
    if not trades_summary:
        trades_summary = ["No trades executed"]
    
    prompt = f"""Analyze this trading bot execution for Kalshi prediction markets:

Trades Executed:
{chr(10).join(trades_summary)}

Trading Strategy (Multi-Signal Framework):
- Uses 5 signals: Momentum (55%), Orderbook (15%), Trade Flow (15%), Liquidity (10%), Volatility (5%)
- Composite Score > 55: Buy YES (price will go above threshold)
- Composite Score < 45: Buy NO (price will not go above threshold)  
- Score 45-55 (Neutral): No trade
- Also requires positive edge vs market prices before executing

Please provide:
1. A concise explanation (2-3 sentences) of why these trades were or weren't executed based on the multi-signal analysis
2. A confidence level from 1-10 (where 10 is highest confidence) for the trading decision

Format your response as:
ANALYSIS: [your explanation]
CONFIDENCE: [number 1-10]
"""

    # Try models in order of rate limits (RPM):
    # gemini-2.5-flash-lite (7 RPM), gemini-2.5-flash (3 RPM),
    # gemma-3-27b (4 RPM), gemma-3-4b (2 RPM), gemma-3-12b (1 RPM), gemma-3-1b
    models = [
        'gemini-2.5-flash-lite',   # 7 RPM - Highest rate limit
        'gemini-2.5-flash',        # 3 RPM
        'gemma-3-27b-it',          # 4 RPM - Large Gemma (27B params)
        'gemma-3-4b-it',           # 2 RPM - Small Gemma (4B params)
        'gemma-3-12b-it',          # 1 RPM - Medium Gemma (12B params)
        'gemma-3-1b-it',           # Tiny Gemma (1B params - last resort)
    ]
    print(f"   Using available models: {models[0]} → {' → '.join(models[1:3])} + {len(models)-3} more fallbacks")
    
    for model_idx, model in enumerate(models, 1):
        try:
            print(f"   Attempting {model_idx}/{len(models)}: {model}")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                text = result['candidates'][0]['content']['parts'][0]['text']
                
                # Parse response
                analysis = text
                confidence = None
                
                # Extract confidence if mentioned
                if 'CONFIDENCE:' in text:
                    parts = text.split('CONFIDENCE:')
                    analysis = parts[0].replace('ANALYSIS:', '').strip()
                    conf_part = parts[1].strip().split('\n')[0]
                    try:
                        confidence = int(conf_part.strip())
                        if confidence < 1:
                            confidence = 1
                        if confidence > 10:
                            confidence = 10
                    except:
                        confidence = None
                
                # Extract analysis if marked
                if 'ANALYSIS:' in text:
                    parts = text.split('ANALYSIS:')
                    if len(parts) > 1:
                        analysis = parts[1].split('CONFIDENCE:')[0].strip()
                
                if model != models[0]:
                    print(f"   ✓ Fallback {model} succeeded")
                else:
                    print(f"   ✓ {model} succeeded")
                
                return {
                    'analysis': analysis.strip(),
                    'confidence': confidence if confidence else 5,  # Default to 5 if not found
                    'model': model
                }
            else:
                print(f"   ✗ {model}: No candidates in response")
        except requests.exceptions.HTTPError as e:
            # Try next model on any HTTP error
            try:
                error_body = e.response.json()
                error_msg = error_body.get('error', {}).get('message', str(e))
            except:
                error_msg = str(e)
            
            if e.response.status_code == 429:
                print(f"   ⚠ Rate limit (429) on {model}, trying next...")
                retry_after = e.response.headers.get('Retry-After')
                ai_tracker.add_attempt('gemini_analysis', model, 'rate_limit', error_msg, dict(e.response.headers))
                if model == models[-1]:
                    print_rate_limit_status(retry_after)
            elif e.response.status_code == 401:
                print(f"   ✗ Authentication failed (401): Invalid API key?")
                ai_tracker.add_attempt('gemini_analysis', model, 'auth_error', error_msg)
            elif e.response.status_code == 403:
                print(f"   ✗ Forbidden (403): {error_msg}")
                ai_tracker.add_attempt('gemini_analysis', model, 'other_error', error_msg)
            else:
                print(f"   ✗ HTTP {e.response.status_code}: {error_msg}")
                ai_tracker.add_attempt('gemini_analysis', model, 'other_error', f"HTTP {e.response.status_code}: {error_msg}")
        except requests.exceptions.Timeout:
            print(f"   ✗ Timeout on {model}")
        except requests.exceptions.ConnectionError as e:
            print(f"   ✗ Connection error on {model}: {e}")
        except Exception as e:
            print(f"   ✗ Unexpected error on {model}: {type(e).__name__}: {e}")
    
    print(f"⚠ All {len(models)} Gemini models exhausted - returning None")
    ai_tracker.add_attempt('gemini_analysis', 'all_models', 'exhausted', 'All models exceeded free tier quota')
    return None


def generate_results_analysis(gemini_api_key, previous_results, current_sentiment):
    """
    Generate AI analysis of previous trades' results.
    
    Args:
        gemini_api_key: Gemini API key
        previous_results: List of trade results from check_previous_trades_results
        current_sentiment: Current sentiment value
    
    Returns:
        dict with 'analysis' and 'summary' or None
    """
    if not gemini_api_key or not previous_results:
        return None
    
    # Calculate stats
    total_resolved = len([r for r in previous_results if r['result'] in ['win', 'loss']])
    wins = len([r for r in previous_results if r['result'] == 'win'])
    losses = len([r for r in previous_results if r['result'] == 'loss'])
    pending = len([r for r in previous_results if r['result'] == 'pending'])
    win_rate = (wins / total_resolved * 100) if total_resolved > 0 else 0
    
    # Build context
    results_summary = []
    for r in previous_results[-10:]:  # Last 10 results
        trade = r['trade']
        result = r['result']
        outcome = r['resolution'].get('outcome', 'pending')
        asset = trade.get('asset', 'UNKNOWN')
        action = trade.get('action', 'N/A')
        decision_log = trade.get('decision_log', {})
        composite = decision_log.get('composite_score', 'N/A') if isinstance(decision_log, dict) else 'N/A'
        
        result_emoji = '✅' if result == 'win' else '❌' if result == 'loss' else '⏳'
        results_summary.append(f"{result_emoji} {asset}: {action} (Score: {composite}) → {outcome.upper() if outcome else 'Pending'} ({result.upper()})")
    
    prompt = f"""Analyze the trading bot's performance based on previous trade results:

Previous Trade Results:
{chr(10).join(results_summary) if results_summary else 'No resolved trades yet'}

Performance Statistics:
- Total Resolved: {total_resolved}
- Wins: {wins}
- Losses: {losses}
- Win Rate: {win_rate:.1f}%
- Pending: {pending}

Trading Strategy:
- Multi-Signal Framework: Momentum (55%), Orderbook (15%), Trade Flow (15%), Liquidity (10%), Volatility (5%)
- Buy YES when composite score > 55, Buy NO when score < 45
- Requires positive edge vs market prices

Please provide:
1. Analysis of what's working and what's not (2-3 sentences)
2. Insights on the relationship between signal scores and trade success
3. Recommendations for improving the strategy

Format your response as:
ANALYSIS: [your analysis]
INSIGHTS: [key insights]
RECOMMENDATIONS: [recommendations]
"""

    # Try models in order of rate limits (RPM):
    # gemini-2.5-flash-lite (7 RPM), gemini-2.5-flash (3 RPM),
    # gemma-3-27b (4 RPM), gemma-3-4b (2 RPM), gemma-3-12b (1 RPM), gemma-3-1b
    models = [
        'gemini-2.5-flash-lite',   # 7 RPM - Highest rate limit
        'gemini-2.5-flash',        # 3 RPM
        'gemma-3-27b-it',          # 4 RPM - Large Gemma (27B)
        'gemma-3-4b-it',           # 2 RPM - Small Gemma (4B)
        'gemma-3-12b-it',          # 1 RPM - Medium Gemma (12B)
        'gemma-3-1b-it',           # Tiny Gemma (1B - last resort)
    ]
    
    for model_idx, model in enumerate(models, 1):
        try:
            print(f"   Attempting {model_idx}/{len(models)}: {model} (results analysis)")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_api_key}"
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=15)
            response.raise_for_status()
            
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                text = result['candidates'][0]['content']['parts'][0]['text']
                
                # Parse response
                analysis = text
                insights = ''
                recommendations = ''
                
                if 'ANALYSIS:' in text:
                    parts = text.split('ANALYSIS:')
                    if len(parts) > 1:
                        analysis_part = parts[1].split('INSIGHTS:')[0].strip()
                        analysis = analysis_part
                
                if 'INSIGHTS:' in text:
                    parts = text.split('INSIGHTS:')
                    if len(parts) > 1:
                        insights = parts[1].split('RECOMMENDATIONS:')[0].strip()
                
                if 'RECOMMENDATIONS:' in text:
                    parts = text.split('RECOMMENDATIONS:')
                    if len(parts) > 1:
                        recommendations = parts[1].strip()
                
                print(f"   ✓ Results analysis succeeded on {model}")
                ai_tracker.add_attempt('results_analysis', model, 'success')
                
                return {
                    'analysis': analysis.strip(),
                    'insights': insights.strip() if insights else None,
                    'recommendations': recommendations.strip() if recommendations else None,
                    'stats': {
                        'total_resolved': total_resolved,
                        'wins': wins,
                        'losses': losses,
                        'win_rate': win_rate,
                        'pending': pending
                    },
                    'model': model
                }
        except requests.exceptions.HTTPError as e:
            # Try next model on any HTTP error
            try:
                error_body = e.response.json()
                error_msg = error_body.get('error', {}).get('message', str(e))
            except:
                error_msg = str(e)
            
            if e.response.status_code == 429:
                print(f"   ⚠ Rate limit (429) on {model}, trying next...")
                ai_tracker.add_attempt('results_analysis', model, 'rate_limit', error_msg, dict(e.response.headers))
            elif e.response.status_code == 404:
                print(f"   ✗ Model not found (404): {error_msg}")
                ai_tracker.add_attempt('results_analysis', model, 'model_not_found', error_msg, dict(e.response.headers))
            elif e.response.status_code == 401:
                print(f"   ✗ Authentication failed (401): Invalid API key?")
                ai_tracker.add_attempt('results_analysis', model, 'auth_error', 'Invalid API key', dict(e.response.headers))
            else:
                print(f"   ✗ HTTP {e.response.status_code}: {error_msg}")
                ai_tracker.add_attempt('results_analysis', model, 'other_error', f"HTTP {e.response.status_code}: {error_msg}", dict(e.response.headers))
        except Exception as e:
            print(f"   ✗ Unexpected error on {model}: {type(e).__name__}: {e}")
            ai_tracker.add_attempt('results_analysis', model, 'other_error', f"{type(e).__name__}: {e}")
    
    print(f"⚠ All {len(models)} Gemini models exhausted for results analysis - returning None")
    ai_tracker.add_attempt('results_analysis', 'all_models', 'exhausted', 'All models tried without success')
    return None


def generate_financial_analysis(gemini_api_key, total_spent, total_gains, total_losses, net_pnl, num_trades):
    """
    Generate AI analysis of financial performance.
    
    Args:
        gemini_api_key: Gemini API key
        total_spent: Total amount spent on trades
        total_gains: Total gains from winning trades
        total_losses: Total losses from losing trades
        net_pnl: Net profit/loss
        num_trades: Number of resolved trades
    
    Returns:
        dict with 'analysis' or None
    """
    if not gemini_api_key:
        return None
    
    roi = (net_pnl / total_spent * 100) if total_spent > 0 else 0
    
    prompt = f"""Analyze the financial performance of this Kalshi trading bot:

Financial Summary:
- Total Spent: ${total_spent:.2f}
- Total Gains: ${total_gains:.2f}
- Total Losses: ${total_losses:.2f}
- Net P&L: ${net_pnl:.2f}
- Resolved Trades: {num_trades}
- ROI: {roi:.1f}%

Provide a concise 2-3 sentence analysis of:
1. Overall financial performance
2. Risk-adjusted returns assessment
3. Whether the strategy is profitable

Format as:
ANALYSIS: [your analysis]
"""

    # Try models in order of rate limits (RPM):
    # gemini-2.5-flash-lite (7 RPM), gemini-2.5-flash (3 RPM),
    # gemma-3-27b (4 RPM), gemma-3-4b (2 RPM), gemma-3-12b (1 RPM), gemma-3-1b
    models = [
        'gemini-2.5-flash-lite',   # 7 RPM - Highest rate limit
        'gemini-2.5-flash',        # 3 RPM
        'gemma-3-27b-it',          # 4 RPM - Large Gemma (27B)
        'gemma-3-4b-it',           # 2 RPM - Small Gemma (4B)
        'gemma-3-12b-it',          # 1 RPM - Medium Gemma (12B)
        'gemma-3-1b-it',           # Tiny Gemma (1B - last resort)
    ]
    
    for model_idx, model in enumerate(models, 1):
        try:
            print(f"   Attempting {model_idx}/{len(models)}: {model} (financial analysis)")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_api_key}"
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=15)
            response.raise_for_status()
            
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                text = result['candidates'][0]['content']['parts'][0]['text']
                
                # Extract analysis
                analysis = text
                if 'ANALYSIS:' in text:
                    parts = text.split('ANALYSIS:')
                    if len(parts) > 1:
                        analysis = parts[1].strip()
                
                print(f"   ✓ Financial analysis succeeded on {model}")
                ai_tracker.add_attempt('financial_analysis', model, 'success')
                
                return {
                    'analysis': analysis.strip(),
                    'model': model
                }
        except requests.exceptions.HTTPError as e:
            # Try next model on any HTTP error
            try:
                error_body = e.response.json()
                error_msg = error_body.get('error', {}).get('message', str(e))
            except:
                error_msg = str(e)
            
            if e.response.status_code == 429:
                print(f"   ⚠ Rate limit (429) on {model}, trying next...")
                ai_tracker.add_attempt('financial_analysis', model, 'rate_limit', error_msg, dict(e.response.headers))
            elif e.response.status_code == 404:
                print(f"   ✗ Model not found (404): {error_msg}")
                ai_tracker.add_attempt('financial_analysis', model, 'model_not_found', error_msg, dict(e.response.headers))
            elif e.response.status_code == 401:
                print(f"   ✗ Authentication failed (401): Invalid API key?")
                ai_tracker.add_attempt('financial_analysis', model, 'auth_error', 'Invalid API key', dict(e.response.headers))
            else:
                print(f"   ✗ HTTP {e.response.status_code}: {error_msg}")
                ai_tracker.add_attempt('financial_analysis', model, 'other_error', f"HTTP {e.response.status_code}: {error_msg}", dict(e.response.headers))
        except Exception as e:
            print(f"   ✗ Unexpected error on {model}: {type(e).__name__}: {e}")
            ai_tracker.add_attempt('financial_analysis', model, 'other_error', f"{type(e).__name__}: {e}")
    
    print(f"⚠ All {len(models)} Gemini models exhausted for financial analysis - returning None")
    ai_tracker.add_attempt('financial_analysis', 'all_models', 'exhausted', 'All models tried without success')
    return None
