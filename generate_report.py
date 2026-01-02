#!/usr/bin/env python3
"""
Generate HTML report from trades.log with per-workflow-run decision summaries
Includes Gemini AI analysis explaining trading decisions
Version: 2025-12-29 with Pacific Time and validation logging
"""

import os
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict
from pathlib import Path
import requests
from dotenv import load_dotenv
from kalshi_analysis import (
    generate_gemini_analysis,
    generate_results_analysis,
    generate_financial_analysis,
    ai_tracker  # Import the tracker for error/attempt logging
)

# Try to import position enrichment
try:
    from kalshi_positions import enrich_trades_with_settlement
    POSITIONS_AVAILABLE = True
except ImportError:
    print("Warning: kalshi_positions module not available, settlement data will not be shown")
    POSITIONS_AVAILABLE = False

# Try to import order history enrichment
try:
    from kalshi_order_history import enrich_trades_with_order_data, enrich_trades_with_market_outcomes
    ORDER_HISTORY_AVAILABLE = True
except ImportError:
    print("Warning: kalshi_order_history module not available, order data will not be enriched")
    ORDER_HISTORY_AVAILABLE = False

# Load environment variables for Gemini API
load_dotenv()

def to_pacific_time(utc_timestamp_str):
    """Convert UTC ISO timestamp to Pacific time string.
    
    Args:
        utc_timestamp_str: ISO format timestamp string (e.g., '2025-12-30T04:17:22.604549')
    
    Returns:
        str: Pacific time formatted as 'Dec 29, 2025 8:17 PM PST'
    """
    try:
        # Parse UTC timestamp
        if isinstance(utc_timestamp_str, str):
            # Handle both with and without timezone info
            if '+' in utc_timestamp_str or utc_timestamp_str.endswith('Z'):
                dt_utc = datetime.fromisoformat(utc_timestamp_str.replace('Z', '+00:00'))
            else:
                # Assume UTC if no timezone
                dt_utc = datetime.fromisoformat(utc_timestamp_str).replace(tzinfo=timezone.utc)
        else:
            return str(utc_timestamp_str)  # Return as-is if not a string
        
        # Convert to Pacific time
        pacific = ZoneInfo('America/Los_Angeles')
        dt_pacific = dt_utc.astimezone(pacific)
        
        # Format: "Dec 29, 2025 8:17 PM PST"
        return dt_pacific.strftime('%b %d, %Y %-I:%M %p %Z')
    except Exception as e:
        print(f"Warning: Could not convert timestamp {utc_timestamp_str} to Pacific: {e}")
        return str(utc_timestamp_str)


def calculate_trade_pnl(trade):
    """
    Calculate per-trade P&L based on settlement status and execution price.
    
    Kalshi contracts:
    - Win = contract pays out $1.00
    - Loss = contract pays out $0.00
    - P&L = (payout - cost_paid)
    
    Args:
        trade: Trade dict containing price, contracts, settlement status
    
    Returns:
        float: P&L amount in dollars, rounded to 2 decimals
    """
    settlement = trade.get('settlement', {})
    status = settlement.get('status', 'Unknown')
    
    # Get execution price and contracts
    price_cents = trade.get('price')
    if price_cents is None:
        # Try to get from decision_log as fallback
        decision_log = trade.get('decision_log')
        if decision_log:
            price_cents = decision_log.get('execution_price')
    
    contracts = trade.get('contracts')
    if contracts is None:
        decision_log = trade.get('decision_log')
        if decision_log:
            contracts = decision_log.get('execution_contracts')
    
    # Can't calculate without price and contracts
    if price_cents is None or contracts is None:
        return 0.0
    
    # Convert price from cents to dollars
    cost_paid = (price_cents / 100.0) * contracts
    
    # Calculate payout and P&L based on settlement status
    if status == 'Won':
        payout = 1.00 * contracts  # Each contract pays $1.00
        pnl = payout - cost_paid
    elif status == 'Lost':
        payout = 0.0  # Lost contracts pay nothing
        pnl = -cost_paid
    else:
        # Unknown status - can't determine P&L
        return 0.0
    
    return round(pnl, 2)


# Gemini functions now imported from kalshi_analysis module
# Placeholder to maintain line numbers for next edit
def _placeholder_gemini_analysis(run_trades, composite_score=None):
    """
    Generate AI analysis using Gemini API explaining trading decisions.
    
    Args:
        run_trades: List of trade dicts for this run
        composite_score: Composite score (0-100) from multi-signal model (optional, legacy param)
    
    Returns:
        dict with 'analysis' (str) and 'confidence' (int 1-10), or None if API unavailable
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("Warning: GEMINI_API_KEY not found in environment")
        return None
    
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

    # Try gemini-2.5-flash first, fallback to other models on rate limit
    # All models verified available via listModels API (includes gemma-3-12b-it and gemma-3-1b-it)
    models = ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.0-flash-lite', 'gemma-3-27b-it', 'gemma-3-12b-it', 'gemma-3-4b-it', 'gemma-3-1b-it']
    
    for model in models:
        try:
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
                    print(f"✓ Used fallback model {model} due to rate limit on primary model")
                else:
                    print(f"✓ Generated analysis using {model}")
                
                return {
                    'analysis': analysis.strip(),
                    'confidence': confidence if confidence else 5,  # Default to 5 if not found
                    'model': model  # Include which model was used
                }
        except requests.exceptions.HTTPError as e:
            # If rate limit (429) and not last model, try next
            if e.response.status_code == 429 and model != models[-1]:
                print(f"Rate limit hit on {model}, trying {models[models.index(model) + 1]}")
                continue
            else:
                print(f"Error generating Gemini analysis with {model}: {e}")
                if model == models[-1]:
                    return None
        except Exception as e:
            print(f"Error generating Gemini analysis with {model}: {e}")
            if model == models[-1]:
                return None
    
    return None

def check_market_resolution(client, ticker):
    """
    Check if a market has resolved and what the outcome was.
    
    Args:
        client: KalshiClient instance
        ticker: Market ticker string
    
    Returns:
        dict with 'resolved' (bool), 'outcome' ('yes', 'no', or None), 'status' (str)
    """
    try:
        # Extract base event ticker
        parts = ticker.split('-')
        if len(parts) >= 2:
            base_ticker = '-'.join(parts[:2])
        else:
            return {'resolved': False, 'outcome': None, 'status': 'unknown'}
        
        # Try to get the market - check both 'closed' and 'resolved' status
        for status in ['closed', 'resolved', 'settled']:
            try:
                markets_response = client.get_markets(
                    event_ticker=base_ticker,
                    status=status,
                    limit=200
                )
                
                if markets_response and hasattr(markets_response, 'markets'):
                    for market in markets_response.markets:
                        if market.ticker == ticker:
                            # Check if market has outcome
                            if hasattr(market, 'outcome') and market.outcome:
                                return {
                                    'resolved': True,
                                    'outcome': market.outcome.lower(),
                                    'status': status
                                }
                            elif hasattr(market, 'yes_bid') or hasattr(market, 'close_price'):
                                # Market is closed, try to determine outcome from close price
                                # If close_price exists and is 0 or 100, market resolved
                                if hasattr(market, 'close_price'):
                                    close_price = market.close_price
                                    if close_price == 100:
                                        return {'resolved': True, 'outcome': 'yes', 'status': status}
                                    elif close_price == 0:
                                        return {'resolved': True, 'outcome': 'no', 'status': status}
            except:
                continue
        
        return {'resolved': False, 'outcome': None, 'status': 'open'}
    except Exception as e:
        print(f"Error checking market resolution for {ticker}: {e}")
        return {'resolved': False, 'outcome': None, 'status': 'error'}

def get_trade_result(trade, market_resolution):
    """
    Determine if a trade was successful based on what we bought and market outcome.
    
    Args:
        trade: Trade dict with 'action' field
        market_resolution: Result from check_market_resolution()
    
    Returns:
        'win', 'loss', 'pending', or None
    """
    if not market_resolution['resolved']:
        return 'pending'
    
    action = trade.get('action', '').upper()
    outcome = market_resolution.get('outcome', '').lower()
    
    if 'BUY YES' in action:
        if outcome == 'yes':
            return 'win'
        elif outcome == 'no':
            return 'loss'
    elif 'BUY NO' in action:
        if outcome == 'no':
            return 'win'
        elif outcome == 'yes':
            return 'loss'
    
    return None

def check_previous_trades_results(client, trades):
    """
    Check results of previous successful trades that might have resolved.
    
    Args:
        client: KalshiClient instance
        trades: List of all trades from log
    
    Returns:
        List of dicts with trade info and results
    """
    results = []
    
    # Only check trades that were successful and not from current run
    # Check trades from previous runs (older than 1 hour ago)
    now = datetime.utcnow()
    cutoff_time = now - timedelta(hours=1)
    
    for trade in trades:
        # Only check successful trades
        if trade.get('status') != 'Success':
            continue
        
        # Skip trades that are too recent (likely haven't resolved yet)
        try:
            trade_time = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
            if trade_time > cutoff_time:
                continue
        except:
            continue
        
        ticker = trade.get('market')
        if not ticker:
            continue
        
        # Check if this market has resolved
        resolution = check_market_resolution(client, ticker)
        result = get_trade_result(trade, resolution)
        
        results.append({
            'trade': trade,
            'resolution': resolution,
            'result': result,
            'ticker': ticker
        })
    
    return results

# generate_results_analysis now imported from kalshi_analysis
# Removed duplicate function definition

# generate_financial_analysis now imported from kalshi_analysis
# Removed duplicate function definition

def extract_asset_from_ticker(ticker):
    """Extract asset type from market ticker (best-effort)."""
    if not ticker:
        return 'UNKNOWN'
    t = str(ticker).upper()
    if 'SPOTIFY' in t:
        return 'SPOTIFY'
    if t.startswith('KXBTCD'):
        return 'BTC'
    elif t.startswith('KXETHD'):
        return 'ETH'
    return 'UNKNOWN'

# NOTE: to_pacific_time() is defined at the top of this file (line 42)
# Do not duplicate it here

def group_trades_by_run(trades):
    """
    Each trade/action is its own run (each workflow execution is separate).
    """
    if not trades:
        return []
    
    # Each trade is its own run
    return [[trade] for trade in trades]

def generate_html_report():
    """Generate HTML report from trades.log with per-workflow-run summaries and previous trade results"""
    print("\n" + "="*60)
    print("STARTING HTML REPORT GENERATION")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("="*60 + "\n")
    
    # Initialize Kalshi client to check market resolutions
    client = None
    try:
        from kalshi_auth import initialize_kalshi_client
        client = initialize_kalshi_client()
    except Exception as e:
        print(f"Warning: Could not initialize Kalshi client for market resolution checking: {e}")
    
    # Always read trades from log files (trades.jsonl or trades.log)
    # This ensures we get all historical trades, not just what's embedded in HTML
    trades = []

    # 1) Primary: Read from trades.jsonl (newer format, one JSON object per line)
    if os.path.exists('trades.jsonl'):
        try:
            with open('trades.jsonl', 'r') as jf:
                for line in jf:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        trades.append(json.loads(line))
                    except Exception:
                        # skip malformed lines but continue
                        print(f"Warning: Skipping malformed JSONL line: {line[:80]}")
            if trades:
                print(f"Loaded {len(trades)} trades from trades.jsonl")
        except Exception as e:
            print(f"Warning: Failed to read trades.jsonl: {e}")

    # 2) Fallback: Read from legacy trades.log (CSV-like format)
    if not trades and os.path.exists('trades.log'):
        try:
            with open('trades.log', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = [p.strip() for p in line.split(',')]
                        if len(parts) >= 4:
                            asset = parts[4] if len(parts) >= 5 else extract_asset_from_ticker(parts[1])
                            try:
                                sentiment = int(parts[5]) if len(parts) >= 6 and parts[5] else None
                            except:
                                sentiment = None
                            try:
                                price = int(parts[6]) if len(parts) >= 7 and parts[6] else None
                            except:
                                price = None
                            try:
                                contracts = int(parts[7]) if len(parts) >= 8 and parts[7] else None
                            except:
                                contracts = None

                            trades.append({
                                'timestamp': parts[0],
                                'market': parts[1],
                                'action': parts[2],
                                'status': parts[3],
                                'asset': asset,
                                'sentiment': sentiment,
                                'price': price,
                                'contracts': contracts,
                                'decision_log': None
                            })
            if trades:
                print(f"Loaded {len(trades)} trades from legacy trades.log")
        except Exception as e:
            print(f"Warning: Failed to read trades.log: {e}")
    
    # Sort by timestamp (oldest first for run grouping)
    trades.sort(key=lambda x: x['timestamp'])
    
    # Track if we've updated trades with new data
    trades_updated = False
    settlement_source = 'Unknown'
    
    # Enrich trades with actual order data from Kalshi API (gets real execution prices)
    order_enrichment_count = 0
    if ORDER_HISTORY_AVAILABLE:
        try:
            trades, order_enrichment_count = enrich_trades_with_order_data(trades)
            if order_enrichment_count > 0:
                print(f"✓ Enriched {order_enrichment_count} trades with actual order data from Kalshi")
                trades_updated = True
        except Exception as e:
            print(f"Warning: Could not enrich trades with order data: {e}")
    else:
        print("Order history enrichment skipped (kalshi_order_history not available)")
    
    # Enrich trades with market outcomes from Kalshi API (gets settlement status)
    outcome_enrichment_count = 0
    if ORDER_HISTORY_AVAILABLE:
        try:
            trades, outcome_enrichment_count = enrich_trades_with_market_outcomes(trades)
            if outcome_enrichment_count > 0:
                print(f"✓ Enriched {outcome_enrichment_count} trades with market outcomes from Kalshi")
                trades_updated = True
        except Exception as e:
            print(f"Warning: Could not enrich trades with market outcomes: {e}")
    
    # Enrich trades with live position data from Kalshi (MUST happen before financial calculations)
    settlement_source = 'Unknown'  # Initialize to avoid scope issues
    if POSITIONS_AVAILABLE:
        try:
            trades, settlement_source = enrich_trades_with_settlement(trades)
            print(f"Trades enriched with settlement data (source: {settlement_source})")
            trades_updated = True
        except Exception as e:
            print(f"Warning: Could not enrich trades with settlement data: {e}")
            settlement_source = 'Error'
    else:
        print("Settlement enrichment skipped (kalshi_positions not available)")
        settlement_source = 'Unavailable'
    
    # Save updated trades back to trades.jsonl if settlement data was added
    if trades_updated and settlement_source != 'Unknown':
        try:
            with open('trades.jsonl', 'w', encoding='utf-8') as f:
                for trade in trades:
                    f.write(json.dumps(trade, ensure_ascii=False) + '\n')
            print(f"✓ Saved updated settlement data to trades.jsonl")
        except Exception as e:
            print(f"Warning: Could not save updated trades: {e}")
    
    # Check previous trades' results
    previous_results = []
    if client:
        try:
            previous_results = check_previous_trades_results(client, trades)
        except Exception as e:
            print(f"Error checking previous trades: {e}")
    
    # Get current sentiment for analysis (from most recent run)
    current_sentiment = None
    for trade in reversed(trades):
        if trade.get('sentiment') is not None:
            current_sentiment = trade.get('sentiment')
            break
    
    # === PRE-CALCULATION RECONCILIATION CHECK ===
    print("\n" + "="*60)
    print("PRE-CALCULATION RECONCILIATION")
    print("="*60)
    
    # Check for data quality issues before calculating P&L
    successful_trades = [t for t in trades if t.get('status') == 'Success']
    trades_with_missing_data = []
    
    for trade in successful_trades:
        missing = []
        if trade.get('price') is None:
            missing.append('price')
        if trade.get('contracts') is None:
            missing.append('contracts')
        if missing:
            trades_with_missing_data.append({
                'market': trade.get('market', 'UNKNOWN'),
                'missing': missing
            })
    
    if trades_with_missing_data:
        print(f"⚠️  WARNING: {len(trades_with_missing_data)} trades missing price/contracts data:")
        for item in trades_with_missing_data[:5]:
            print(f"     {item['market']}: missing {', '.join(item['missing'])}")
    else:
        print(f"✓ All {len(successful_trades)} successful trades have complete data")
    
    print("="*60 + "\n")
    
    # Calculate financial metrics
    total_spent = 0.0
    spent_on_won = 0.0
    spent_on_lost = 0.0
    spent_on_pending = 0.0
    total_gains = 0.0
    total_losses = 0.0
    open_pnl = 0.0
    
    # Calculate P&L for each trade using per-trade calculation
    print(f"Calculating P&L from {len(trades)} trades")
    for trade in trades:
        settlement = trade.get('settlement') or {}
        status = settlement.get('status', 'Unknown')
        
        # Calculate actual cost - only for executed trades (with order_id)
        if trade.get('order_id'):
            cost = settlement.get('cost', 0)
            if cost > 0:
                # Only count cost for SETTLED trades (Won/Lost), not pending
                if status in ['Won', 'Lost']:
                    total_spent += cost
                # Track cost by outcome
                if status == 'Won':
                    spent_on_won += cost
                elif status == 'Lost':
                    spent_on_lost += cost
                elif status in ['Pending', 'Open']:
                    spent_on_pending += cost
        
        # Calculate P&L for this specific trade
        pnl = calculate_trade_pnl(trade)
        
        # Categorize P&L: Won (profit), Loss, Pending (open/unknown)
        if status == 'Won' and pnl > 0:
            total_gains += pnl
        elif status == 'Lost' and pnl < 0:
            total_losses += abs(pnl)
        elif status in ['Pending', 'Open'] and pnl != 0:
            open_pnl += pnl
    
    net_pnl = total_gains - total_losses + open_pnl
    
    # Calculate net positions: spent + pnl for each outcome
    won_net = spent_on_won + total_gains
    loss_net = spent_on_lost - total_losses
    pending_net = spent_on_pending + open_pnl
    
    # === DETAILED RECONCILIATION VALIDATION ===
    print("\n" + "="*60)
    print("FINANCIAL METRICS RECONCILIATION")
    print("="*60)
    
    # Categorize all trades - order_id = executed trade
    executed_trades = [t for t in trades if t.get('order_id')]
    settled_trades = [t for t in executed_trades if t.get('settlement', {}).get('status') in ['Won', 'Lost']]
    open_trades = [t for t in executed_trades if t.get('settlement', {}).get('status') not in ['Won', 'Lost']]
    non_executed = [t for t in trades if not t.get('order_id')]
    
    print(f"\n[TRADE SUMMARY]")
    print(f"  Total entries logged:    {len(trades)}")
    print(f"  ├─ Executed trades:      {len(executed_trades)}")
    print(f"  │   ├─ Settled (Won/Lost): {len(settled_trades)}")
    print(f"  │   └─ Pending settlement: {len(open_trades)}")
    print(f"  └─ Non-executed (SKIPs): {len(non_executed)}")
    
    # Reconciliation check: all executed trades should have price and contracts
    reconciliation_issues = []
    for trade in executed_trades:
        if not trade.get('price'):
            reconciliation_issues.append(f"Trade {trade.get('market')} missing price")
        if not trade.get('contracts'):
            reconciliation_issues.append(f"Trade {trade.get('market')} missing contracts")
    
    print(f"\n[FINANCIAL METRICS]")
    print(f"  Total Spent:               ${total_spent:.2f}")
    print(f"  Won (profit):              ${total_gains:.2f}")
    print(f"  Loss:                      ${total_losses:.2f}")
    print(f"  Pending:                   ${open_pnl:.2f}")
    print(f"  Net P&L:                   ${net_pnl:.2f}")
    print(f"  Formula:                   ${total_gains:.2f} - ${total_losses:.2f} + ${open_pnl:.2f} = ${net_pnl:.2f}")
    
    # Reconciliation: settled trades cost should match total_spent
    # Use settlement.cost (same as total_spent calculation) for consistency
    settled_cost = sum(
        t.get('settlement', {}).get('cost', 0)
        for t in settled_trades
    )
    print(f"\n[RECONCILIATION CHECK]")
    print(f"  Settled trades cost:       ${settled_cost:.2f}")
    if abs(settled_cost - total_spent) > 0.01:
        print(f"  ⚠️  Mismatch with Total Spent (${total_spent:.2f})")
    print(f"  Pending settlement:        {len(open_trades)} executed trades awaiting results")
    
    # Analyze unknown trades - only those with order_ids need resolution
    unknown_trades = [t for t in trades if t.get('order_id') and t.get('settlement', {}).get('status') not in ['Won', 'Lost']]
    # Filter out placeholder/error markets
    unknown_trades_real = [t for t in unknown_trades if 'NOT-FOUND' not in t.get('market', '') and not (t.get('market', '').startswith('BTC-') and len(t.get('market', '')) <= 20)]
    unknown_trades_errors = [t for t in unknown_trades if 'NOT-FOUND' in t.get('market', '') or (t.get('market', '').startswith('BTC-') and len(t.get('market', '')) <= 20)]
    
    if unknown_trades:
        print(f"\n[UNKNOWN TRADE ANALYSIS]")
        print(f"  Total unknown trades: {len(unknown_trades)}")
        if unknown_trades_errors:
            print(f"  (Excluding {len(unknown_trades_errors)} placeholder/error markets: {', '.join(set(t.get('market') for t in unknown_trades_errors))})")
        
        # Group by market to understand patterns
        unknown_by_market = defaultdict(int)
        for t in unknown_trades_real:
            market = t.get('market', 'unknown')
            unknown_by_market[market] += 1
        
        print(f"  By market (real markets only):")
        for market, count in sorted(unknown_by_market.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"    - {market}: {count} unknown trades")
        
        # Try to enrich unknown trades with market outcomes if available
        if ORDER_HISTORY_AVAILABLE and unknown_trades_real:
            print(f"  Attempting to resolve {len(unknown_trades_real)} unknown trades via market query...")
            trades, resolved_count = enrich_trades_with_market_outcomes(trades)
            newly_resolved = len([t for t in trades if t.get('settlement', {}).get('status') != 'Unknown']) - (len(trades) - len(unknown_trades))
            if resolved_count > 0:
                print(f"  ✓ Resolved {resolved_count} unknown trades via market query")
            else:
                print(f"  ⚠ Market resolution data unavailable or markets still active")
    
    # Flag issues
    if reconciliation_issues:
        print(f"\n⚠️  DATA QUALITY ISSUES ({len(reconciliation_issues)}):")
        for issue in reconciliation_issues[:5]:  # Show first 5
            print(f"     - {issue}")
        if len(reconciliation_issues) > 5:
            print(f"     ... and {len(reconciliation_issues) - 5} more")
    
    if len(open_trades) > 5:
        print(f"\n⚠️  WARNING: {len(open_trades)} executed trades pending settlement")
        print(f"     These should resolve within the hourly cycle")
    
    if len(settled_trades) > 0 and total_gains == 0 and total_losses == 0:
        print(f"\n⚠️  WARNING: Found {len(settled_trades)} settled trades but P&L is zero!")
        print(f"     This likely means settlement data isn't being calculated correctly.")
        print(f"     Sample settled trades: {[t.get('market') for t in settled_trades[:3]]}...")
    
    if len(successful_trades) > 0 and total_spent == 0:
        print(f"\n⚠️  WARNING: Found {len(successful_trades)} successful trades but total spent is zero!")
        print(f"     Check if price/contracts data is being captured correctly.")
    
    print("="*60 + "\n")
    
    # Gemini API calls - run on every GitHub Action execution with full model fallback
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    print(f"\nChecking for GEMINI_API_KEY: {'Found ✓' if gemini_api_key else 'NOT FOUND ✗'}")
    results_analysis = None
    financial_analysis = None
    
    # Load AI insights from the append-only log (ai_insights.jsonl)
    ai_insights_log = []
    try:
        insights_path = Path('ai_insights.jsonl')
        if insights_path.exists():
            with open(insights_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            ai_insights_log.append(json.loads(line))
                        except:
                            continue
            print(f"\n✓ Loaded {len(ai_insights_log)} AI insights from log")
    except Exception as e:
        print(f"\n⚠ Could not load AI insights log: {e}")
    
    # Get latest insight for quick display
    results_analysis = None
    if ai_insights_log:
        latest = ai_insights_log[-1]
        results_analysis = {
            'analysis': latest.get('analysis', 'See insights log below'),
            'insights': latest.get('suggestion', ''),
            'recommendations': '',
            'model': latest.get('model', 'unknown')
        }
    
    if gemini_api_key:
        print("\n🤖 AI Analysis available via insights log")
        
        # Call 2: Financial analysis (always run if we have trades)
        if len(successful_trades) > 0:
            print("\n  💰 Generating financial analysis...")
            financial_analysis = generate_financial_analysis(gemini_api_key, total_spent, total_gains, total_losses, net_pnl, len(previous_results))
            if financial_analysis:
                print(f"  ✓ Financial analysis complete (model: {financial_analysis.get('model', 'unknown')})")
            else:
                print("  ✗ Financial analysis failed (exhausted all models)")
        else:
            print("\n  ℹ️  Skipping financial analysis (no successful trades yet)")
    else:
        print("  ℹ️  Gemini analysis skipped (API key not configured)")
    
    # Group by workflow runs
    runs = group_trades_by_run(trades)
    
    # Reverse to show newest runs first
    runs.reverse()
    
    # Generate HTML
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kalshi Trading Bot - Trade History</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 20px;
        }
        .header-left {
            flex: 1;
        }
        .header h1 {
            margin: 0;
            font-size: 2em;
        }
        .header p {
            margin: 10px 0 0 0;
            opacity: 0.9;
        }
        .header-quick-stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            background: rgba(255,255,255,0.15);
            padding: 12px;
            border-radius: 8px;
            min-width: 260px;
            font-size: 0.85em;
        }
        .quick-stat {
            text-align: center;
            padding: 8px 12px;
            background: rgba(255,255,255,0.1);
            border-radius: 6px;
        }
        .quick-stat .label {
            font-size: 0.7em;
            opacity: 0.9;
            text-transform: uppercase;
            margin-bottom: 2px;
        }
        .quick-stat .value {
            font-size: 1.4em;
            font-weight: bold;
        }
        .quick-stat.profit .value { color: #a7f3d0; }
        .quick-stat.loss .value { color: #fca5a5; }
        .quick-stat.pending .value { color: #fde68a; }
        .last-settled {
            grid-column: span 2;
            font-size: 0.8em;
            opacity: 0.85;
            text-align: left;
            padding: 6px 8px;
            background: rgba(0,0,0,0.1);
            border-radius: 4px;
        }
        .model-config-row {
            grid-column: span 2;
            font-size: 0.75em;
            opacity: 0.9;
            text-align: left;
            padding: 6px 8px;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            line-height: 1.4;
        }
        .model-config-row .config-label {
            font-weight: bold;
            margin-right: 5px;
        }
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
            }
            .header-quick-stats {
                min-width: 100%;
            }
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stat-card h3 {
            margin: 0 0 10px 0;
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
        }
        .stat-card .value {
            font-size: 2em;
            font-weight: bold;
            color: #333;
        }
        .stat-card.success .value { color: #10b981; }
        .stat-card.failed .value { color: #ef4444; }
        .stat-card.pending .value { color: #f59e0b; }
        table {
            width: 100%;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        thead {
            background: #667eea;
            color: white;
        }
        th {
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }
        td {
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
        }
        tbody tr:hover {
            background-color: #f9fafb;
        }
        tbody tr:last-child td {
            border-bottom: none;
        }
        .status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }
        .status.success {
            background-color: #d1fae5;
            color: #065f46;
        }
        .status.failed {
            background-color: #fee2e2;
            color: #991b1b;
        }
        .status.pending {
            background-color: #fef3c7;
            color: #92400e;
        }
        .status.not-found {
            background-color: #e5e7eb;
            color: #374151;
        }
        .status.error {
            background-color: #fee2e2;
            color: #991b1b;
        }
        .status.no-trade {
            background-color: #e5e7eb;
            color: #374151;
        }
        .action {
            font-weight: 600;
        }
        .action.buy-yes {
            color: #10b981;
        }
        .action.buy-no {
            color: #ef4444;
        }
        .footer {
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            color: #666;
            font-size: 0.9em;
        }
        .no-trades {
            background: white;
            padding: 40px;
            text-align: center;
            border-radius: 10px;
            color: #666;
        }
        .run-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .run-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 2px solid #f3f4f6;
        }
        .run-time {
            font-size: 0.9em;
            color: #666;
        }
        .run-assets {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .asset-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }
        .asset-badge.btc {
            background-color: #f59e0b;
            color: white;
        }
        .asset-badge.eth {
            background-color: #8b5cf6;
            color: white;
        }
        .asset-badge.spotify {
            background-color: #1db954;
            color: white;
        }
        .run-decisions {
            margin: 15px 0;
        }
        .decision-item {
            padding: 10px;
            margin: 5px 0;
            border-radius: 5px;
            background-color: #f9fafb;
        }
        .decision-item.bought {
            background-color: #d1fae5;
            border-left: 4px solid #10b981;
        }
        .decision-item.skipped {
            background-color: #fef3c7;
            border-left: 4px solid #f59e0b;
        }
        .decision-item.failed {
            background-color: #fee2e2;
            border-left: 4px solid #ef4444;
        }
        .run-details {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #e5e7eb;
        }
        .run-details-toggle {
            cursor: pointer;
            color: #667eea;
            font-size: 0.9em;
            user-select: none;
        }
        .run-details-toggle:hover {
            text-decoration: underline;
        }
        .run-details-content {
            display: block;
            margin-top: 10px;
        }
        .run-details table {
            width: 100%;
            font-size: 0.9em;
        }
        .ai-analysis {
            margin-top: 15px;
            padding: 15px;
            background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
            border-radius: 8px;
            border-left: 4px solid #3b82f6;
        }
        .ai-analysis h4 {
            margin: 0 0 10px 0;
            color: #1e40af;
            font-size: 1em;
        }
        .ai-analysis-text {
            color: #1e3a8a;
            line-height: 1.6;
            margin-bottom: 10px;
        }
        .confidence-level {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            background-color: #dbeafe;
            color: #1e40af;
            font-weight: 600;
            font-size: 0.9em;
        }
        .confidence-level.high {
            background-color: #d1fae5;
            color: #065f46;
        }
        .confidence-level.medium {
            background-color: #fef3c7;
            color: #92400e;
        }
        .confidence-level.low {
            background-color: #fee2e2;
            color: #991b1b;
        }
        .details-btn {
            background-color: #667eea;
            color: white;
            border: none;
            padding: 5px 12px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.85em;
            font-weight: 600;
        }
        .details-btn:hover {
            background-color: #5568d3;
        }
        .decision-details {
            background-color: #f9fafb;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
            margin-top: 10px;
        }
        .decision-details div {
            margin-bottom: 8px;
            line-height: 1.6;
        }
        .decision-details strong {
            color: #333;
            margin-right: 8px;
        }
        .decision-details-content {
            background-color: #fafafa;
            padding: 10px;
        }
        .results-section {
            background: white;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .results-section h2 {
            margin-top: 0;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        .results-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .result-stat {
            text-align: center;
            padding: 15px;
            border-radius: 8px;
            background-color: #f9fafb;
        }
        .result-stat.win {
            background-color: #d1fae5;
        }
        .result-stat.loss {
            background-color: #fee2e2;
        }
        .result-stat.pending {
            background-color: #fef3c7;
        }
        .result-stat .label {
            font-size: 0.85em;
            color: #666;
            margin-bottom: 5px;
        }
        .result-stat .value {
            font-size: 1.8em;
            font-weight: bold;
        }
        .result-stat.win .value {
            color: #065f46;
        }
        .result-stat.loss .value {
            color: #991b1b;
        }
        .previous-trades-table {
            margin-top: 20px;
        }
        .result-win {
            color: #10b981;
            font-weight: 600;
        }
        .result-loss {
            color: #ef4444;
            font-weight: 600;
        }
        .result-pending {
            color: #f59e0b;
            font-weight: 600;
        }
        /* Diagnostic sections */
        .diagnostic-section {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .diagnostic-section h3 {
            margin-top: 0;
            color: #667eea;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }
        .diagnostic-section table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        .diagnostic-section table th,
        .diagnostic-section table td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
        }
        .diagnostic-section table th {
            background-color: #f9fafb;
            font-weight: 600;
            color: #333;
        }
        .diagnostic-section table code {
            background-color: #f3f4f6;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }
        /* Tab system */
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            border-bottom: 2px solid #e5e7eb;
        }
        .tab-button {
            padding: 12px 24px;
            background: none;
            border: none;
            border-bottom: 3px solid transparent;
            cursor: pointer;
            font-size: 1em;
            font-weight: 600;
            color: #666;
            transition: all 0.3s;
        }
        .tab-button:hover {
            color: #667eea;
        }
        .tab-button.active {
            color: #667eea;
            border-bottom-color: #667eea;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .debug-section {
            background: white;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .debug-run {
            margin-bottom: 30px;
            padding: 20px;
            background: #f9fafb;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        .debug-run h3 {
            margin-top: 0;
            color: #333;
        }
        .debug-entry {
            margin: 15px 0;
            padding: 15px;
            background: white;
            border-radius: 5px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 0.85em;
        }
        .debug-entry pre {
            margin: 0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
    </style>
    <script>
        function showTab(tabName) {
            // Hide all tab contents
            const contents = document.querySelectorAll('.tab-content');
            contents.forEach(c => c.classList.remove('active'));
            
            // Deactivate all tab buttons
            const buttons = document.querySelectorAll('.tab-button');
            buttons.forEach(b => b.classList.remove('active'));
            
            // Show selected tab
            document.getElementById(tabName).classList.add('active');
            document.querySelector(`[onclick="showTab('${tabName}')"]`).classList.add('active');
        }
        
        function toggleDecisionDetails(detailsId) {
            const element = document.getElementById(detailsId);
            if (element) {
                element.style.display = element.style.display === 'none' ? 'block' : 'none';
            }
        }
        
        function toggleDetails(runId) {
            const content = document.getElementById('details-' + runId);
            const toggle = document.getElementById('toggle-' + runId);
            if (content.classList.contains('show')) {
                content.classList.remove('show');
                toggle.textContent = '▶ Show Details';
            } else {
                content.classList.add('show');
                toggle.textContent = '▼ Hide Details';
            }
        }
    </script>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <h1>🤖 Kalshi Trading Bot</h1>
            <p>Trade History & Status Report</p>
            <p style="font-size: 0.9em; margin-top: 5px;">Last updated: {update_time}</p>
        </div>
        <div class="header-quick-stats">
            <div class="quick-stat {header_pnl_class}">
                <div class="label">Net P&L</div>
                <div class="value">{header_net_pnl}</div>
            </div>
            <div class="quick-stat pending">
                <div class="label">Unsettled</div>
                <div class="value">{header_unsettled}</div>
            </div>
            <div class="last-settled">
                📊 <strong>Last:</strong> {header_last_settled}
            </div>
            <div class="model-config-row">
                ⚙️ {header_model_summary}
            </div>
        </div>
    </div>
    
    <div class="tabs">
        <button class="tab-button active" onclick="showTab('overview-tab')">📊 Overview</button>
        <button class="tab-button" onclick="showTab('how-it-works-tab')">🔬 How It Works</button>
        <button class="tab-button" onclick="showTab('trades-tab')">📈 Detailed Trades</button>
        <button class="tab-button" onclick="showTab('diagnostics-tab')">🔧 Diagnostics</button>
    </div>
    
    <div id="overview-tab" class="tab-content active">
"""
    
    # Load next market info if available
    next_market_info = None
    next_market_html = ""
    try:
        if os.path.exists('next_market.json'):
            with open('next_market.json', 'r') as f:
                next_market_info = json.load(f)
                if next_market_info:
                    status = next_market_info.get('status', 'unknown')
                    if status == 'found':
                        market_ticker = next_market_info.get('market_ticker', 'Unknown')
                        next_hour_et = next_market_info.get('next_hour_et', '')
                        try:
                            dt = datetime.fromisoformat(next_hour_et)
                            time_str = dt.strftime('%I:%M %p ET')
                        except:
                            time_str = 'Unknown'
                        next_market_html = f"""
        <div class="next-market-card" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 10px 0; color: white;">📈 Next Market Available</h3>
            <div style="font-size: 1.1em; font-weight: bold; color: white;">{market_ticker}</div>
            <div style="font-size: 0.9em; margin-top: 5px; opacity: 0.95;">Scheduled for {time_str}</div>
        </div>
"""
                    elif status == 'no_market_yet':
                        message = next_market_info.get('message', 'Market not yet available')
                        next_market_html = f"""
        <div class="next-market-card" style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 10px 0; color: white;">⏰ Market Status</h3>
            <div style="font-size: 0.95em; color: white;">{message}</div>
        </div>
"""
    except Exception as e:
        print(f"Warning: Could not load next_market.json: {e}")
    
    if next_market_html:
        html += next_market_html
    
    # Calculate stats - order_id = executed trade
    executed_trades = [t for t in trades if t.get('order_id')]
    total_trades = len(executed_trades)
    successful = len([t for t in trades if t.get('status') == 'Success'])
    failed = len([t for t in trades if t.get('status') == 'Failed'])
    no_trades = len([t for t in trades if not t.get('order_id')])
    
    # Calculate trade outcomes from settlement data
    trades_won = len([t for t in executed_trades if t.get('settlement', {}).get('status') == 'Won'])
    trades_lost = len([t for t in executed_trades if t.get('settlement', {}).get('status') == 'Lost'])
    trades_open = len([t for t in executed_trades if t.get('settlement', {}).get('status') == 'Open'])
    trades_pending = len([t for t in executed_trades if t.get('settlement', {}).get('status') == 'Pending'])
    trades_unknown = len([t for t in executed_trades if t.get('settlement', {}).get('status') == 'Unknown'])
    # Count both Open and Pending as unsettled trades
    trades_unsettled = trades_open + trades_pending
    trades_settled = trades_won + trades_lost
    success_rate = (trades_won / trades_settled * 100) if trades_settled > 0 else 0
    
    # Add stats section
    html += f"""
    <div class="stats">
        <div class="stat-card">
            <h3>Total Runs</h3>
            <div class="value">{len(runs)}</div>
            <div style="font-size: 0.75em; color: #666; margin-top: 5px;">Bot executions</div>
        </div>
        <div class="stat-card">
            <h3>Executed Trades</h3>
            <div class="value">{total_trades}</div>
            <div style="font-size: 0.75em; color: #666; margin-top: 5px;">Successfully filled orders</div>
        </div>
        <div class="stat-card success">
            <h3>Won</h3>
            <div class="value">{trades_won}</div>
            <div style="font-size: 0.75em; color: #10b981; margin-top: 5px;">Profitable trades</div>
        </div>
        <div class="stat-card failed">
            <h3>Lost</h3>
            <div class="value">{trades_lost}</div>
            <div style="font-size: 0.75em; color: #ef4444; margin-top: 5px;">Losing trades</div>
        </div>
        <div class="stat-card pending">
            <h3>Pending</h3>
            <div class="value">{trades_unsettled}</div>
            <div style="font-size: 0.75em; color: #f59e0b; margin-top: 5px;">Awaiting settlement</div>
        </div>
        <div class="stat-card" style="background-color: #f3f4f6; color: #666;">
            <h3 style="color: #666;">Unknown</h3>
            <div class="value">{trades_unknown}</div>
            <div style="font-size: 0.75em; color: #666; margin-top: 5px;">Unable to determine outcome</div>
        </div>
        <div class="stat-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">
            <h3 style="color: white;">Win Rate</h3>
            <div class="value" style="color: white;">{success_rate:.1f}%</div>
            <div style="font-size: 0.7em; margin-top: 5px; opacity: 0.9;">{trades_won}W / {trades_lost}L</div>
        </div>
    </div>
"""
    
    # Generate cumulative P&L chart data
    settled_trades = [t for t in executed_trades if t.get('settlement', {}).get('status') in ['Won', 'Lost']]
    settled_trades_sorted = sorted(settled_trades, key=lambda t: t.get('timestamp', ''))
    
    cumulative_pnl = 0
    chart_labels = []
    chart_data = []
    pacific = ZoneInfo('America/Los_Angeles')
    utc = ZoneInfo('UTC')
    for trade in settled_trades_sorted:
        try:
            ts = datetime.fromisoformat(trade.get('timestamp', '').replace('Z', '+00:00'))
            # If timestamp has no timezone info, assume it's UTC
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=utc)
            ts_pacific = ts.astimezone(pacific)
            chart_labels.append(ts_pacific.strftime('%m/%d %H:%M'))
        except:
            chart_labels.append('Unknown')
        pnl = trade.get('settlement', {}).get('pnl', 0)
        cumulative_pnl += pnl
        chart_data.append(round(cumulative_pnl, 2))
    
    # Add P&L chart if we have settled trades
    if chart_data:
        chart_json = json.dumps(chart_data)
        labels_json = json.dumps(chart_labels)
        
        html += f"""
    <div class="results-section" style="margin-top: 30px;">
        <h2>📈 Cumulative P&L Over Time</h2>
        <div style="position: relative; width: 100%; height: 300px; margin: 20px 0;">
            <canvas id="pnlChart" style="display: block;"></canvas>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.js"></script>
        <script>
            // Wait for Chart.js to load, then initialize chart
            function initializeChart() {{
                const canvas = document.getElementById('pnlChart');
                if (!canvas) return;
                
                const ctx = canvas.getContext('2d');
                const chartData = {chart_json};
                const labels = {labels_json};
                
                // Ensure canvas has proper dimensions
                canvas.parentElement.style.position = 'relative';
                canvas.parentElement.style.width = '100%';
                canvas.parentElement.style.height = '300px';
                
                new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: labels,
                        datasets: [{{
                            label: 'Cumulative P&L ($)',
                            data: chartData,
                            borderColor: chartData[chartData.length - 1] >= 0 ? '#10b981' : '#ef4444',
                            backgroundColor: chartData[chartData.length - 1] >= 0 ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                            fill: true,
                            tension: 0.3,
                            pointRadius: 4,
                            pointBackgroundColor: function(context) {{
                                const value = context.raw;
                                return value >= 0 ? '#10b981' : '#ef4444';
                            }},
                            pointBorderColor: '#fff',
                            pointBorderWidth: 2
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{
                                display: true,
                                labels: {{ color: '#374151' }}
                            }}
                        }},
                        scales: {{
                            y: {{
                                grid: {{ color: '#e5e7eb' }},
                                ticks: {{ color: '#6b7280' }},
                                title: {{ display: true, text: 'P&L ($)' }}
                            }},
                            x: {{
                                grid: {{ display: false }},
                                ticks: {{ color: '#6b7280', maxRotation: 45, minRotation: 0 }}
                            }}
                        }}
                    }}
                }});
            }}
            
            // Initialize when document is ready
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', initializeChart);
            }} else {{
                initializeChart();
            }}
        </script>
    </div>
"""
    
    # Add Financial Performance section
    if total_spent > 0 or previous_results:
        roi = (net_pnl / total_spent * 100) if total_spent > 0 else 0
        roi_color = '#10b981' if roi > 0 else '#ef4444' if roi < 0 else '#666'
        
        # Calculate net positions for trades with verified cost data
        won_net = spent_on_won + total_gains
        loss_net = spent_on_lost - total_losses
        pending_net = spent_on_pending + open_pnl
        
        # Count won and lost trades
        won_trades = [t for t in trades if t.get('settlement', {}).get('status') == 'Won']
        lost_trades = [t for t in trades if t.get('settlement', {}).get('status') == 'Lost']
        
        html += f"""
    <div class="results-section">
        <h2>💰 Financial Performance</h2>
        <div class="results-stats">
            <div class="result-stat" style="background-color: #f3f4f6;">
                <div class="label">Amount Risked</div>
                <div class="value">${total_spent:.2f}</div>
                <div style="font-size: 0.75em; opacity: 0.8;">from {len(won_trades) + len(lost_trades)} settled trade(s)</div>
            </div>
            <div class="result-stat win">
                <div class="label">Profit</div>
                <div class="value">${total_gains:.2f}</div>
                <div style="font-size: 0.75em; opacity: 0.8;">from {len(won_trades)} winning trade(s)</div>
            </div>
            <div class="result-stat loss">
                <div class="label">Loss</div>
                <div class="value">${-total_losses:.2f}</div>
                <div style="font-size: 0.75em; opacity: 0.8;">from {len(lost_trades)} losing trade(s)</div>
            </div>
            <div class="result-stat" style="background-color: {'#d1fae5' if net_pnl > 0 else '#fee2e2' if net_pnl < 0 else '#f9fafb'};">
                <div class="label">Net P&L</div>
                <div class="value" style="color: {roi_color};">${net_pnl:.2f}</div>
            </div>
            <div class="result-stat">
                <div class="label">ROI</div>
                <div class="value" style="color: {roi_color};">{roi:+.1f}%</div>
            </div>
        </div>
"""
        if financial_analysis:
            html += f"""
        <div class="ai-analysis">
            <h4>🤖 Financial Analysis (Gemini)</h4>
            <div class="ai-analysis-text">{financial_analysis.get('analysis', 'Analysis unavailable')}</div>
            <div style="font-size: 0.8em; color: #999; margin-top: 8px;">Model: {financial_analysis.get('model', 'unknown')}</div>
        </div>
"""
        elif gemini_api_key:
            # Check tracker for specific error info
            error_details = "Check 'AI Analysis Details' tab for specifics"
            if ai_tracker.attempts:
                recent_errors = [a for a in ai_tracker.attempts if a['type'] == 'financial_analysis' and a['status'] != 'success']
                if recent_errors:
                    latest_error = recent_errors[-1]
                    if latest_error['status'] == 'rate_limit':
                        error_details = "🔴 API rate limit (429) - will retry on next run"
                    elif latest_error['status'] == 'model_not_found':
                        error_details = "🔴 All models unavailable (404) - models may have been removed from API"
                    elif latest_error['status'] == 'auth_error':
                        error_details = "🔴 Authentication error (401) - check GEMINI_API_KEY"
                    elif latest_error['status'] == 'exhausted':
                        error_details = f"🔴 All attempts exhausted - {latest_error.get('error', 'unknown error')}"
                    else:
                        error_details = f"🔴 {latest_error.get('error', 'Unknown error')} - check AI Analysis Details tab"
            
            html += f"""
        <div class="ai-analysis" style="background-color: #fef3c7; border-left: 4px solid #f59e0b;">
            <h4>⚠️  Financial Analysis</h4>
            <div class="ai-analysis-text">{error_details}</div>
            <div style="font-size: 0.75em; color: #666; margin-top: 8px;">
                <strong>Troubleshooting:</strong> Review the 🤖 AI Analysis Details tab for complete error log and rate limit info.
            </div>
        </div>
"""
        html += """
    </div>
"""
    
    # Add recent trades summary to overview - only show executed trades (with order_id)
    executed_only = [t for t in trades if t.get('order_id')]
    recent_trades = sorted(executed_only, key=lambda x: x['timestamp'], reverse=True)[:10]
    all_trades = sorted(trades, key=lambda x: x['timestamp'], reverse=True)  # For settlement details
    if recent_trades:
        html += """
    <div class="results-section">
        <h2>📋 Recent Trades (Last 10 Executed)</h2>
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Asset</th>
                    <th>Market Target</th>
                    <th>Context</th>
                    <th>Action</th>
                    <th>Trade Price</th>
                    <th>AI Decision</th>
                    <th>Result</th>
                    <th>P&L</th>
                </tr>
            </thead>
            <tbody>
"""
        for trade in recent_trades:
            # Convert timestamp to Pacific time
            trade_time = to_pacific_time(trade['timestamp'])
            
            price = trade.get('price', 0)
            price_str = f"{price}¢" if price else 'N/A'
            
            # Extract decision log signals if available
            decision_log = trade.get('decision_log', {})
            if isinstance(decision_log, str):
                # Try to parse as JSON if it's stored as string
                try:
                    decision_log = json.loads(decision_log)
                except:
                    decision_log = {}
            elif decision_log is None:
                decision_log = {}
            
            # Generic "context" display (legacy field name preserved for compatibility)
            btc_price = decision_log.get('current_price')
            btc_price_display = f"${btc_price:,.0f}" if btc_price else '—'
            
            # Extract market target price from ticker (e.g., KXBTCD-25DEC3100-T88249.99)
            market_ticker = trade.get('market', '')
            market_target = 'N/A'
            if '-T' in market_ticker:
                try:
                    target_str = market_ticker.split('-T')[-1]
                    target_val = float(target_str)
                    market_target = f"${target_val:,.0f}"
                except:
                    pass
            
            # Get Gemini AI decision info
            gemini_model = decision_log.get('gemini_model', '')
            gemini_decision = decision_log.get('gemini_decision', '')
            composite_score = decision_log.get('composite_score')
            
            # Format AI decision display
            if gemini_model and gemini_model != 'MODEL_ONLY':
                ai_decision = f'<small>🤖 {gemini_decision}</small>'
            elif composite_score is not None:
                if composite_score > 55:
                    score_color = '#10b981'
                elif composite_score < 45:
                    score_color = '#ef4444'
                else:
                    score_color = '#f59e0b'
                ai_decision = f'<small style="color: {score_color};">Score: {composite_score:.0f}</small>'
            else:
                ai_decision = '<small style="color: #999;">Legacy</small>'
            
            settlement = trade.get('settlement', {})
            result_status = settlement.get('status', 'Unknown')
            pnl = calculate_trade_pnl(trade)
            
            if result_status == 'Won':
                result_display = '<span style="color: #10b981; font-weight: bold;">✓ Won</span>'
                pnl_display = f'<span style="color: #10b981; font-weight: bold;">+${pnl:.2f}</span>'
            elif result_status == 'Lost':
                result_display = '<span style="color: #ef4444; font-weight: bold;">✗ Lost</span>'
                pnl_display = f'<span style="color: #ef4444; font-weight: bold;">-${abs(pnl):.2f}</span>'
            elif result_status == 'Open':
                result_display = '<span style="color: #f59e0b; font-weight: bold;">⏳ Open</span>'
                pnl_display = '<span style="color: #666;">—</span>'
            else:
                result_display = '<span style="color: #666;">— Unknown</span>'
                pnl_display = '<span style="color: #666;">—</span>'
            
            html += f"""
                <tr>
                    <td>{trade_time}</td>
                    <td><strong>{trade.get('asset', 'N/A')}</strong></td>
                    <td>{market_target}</td>
                    <td>{btc_price_display}</td>
                    <td>{trade.get('action', 'N/A')}</td>
                    <td>{price_str}</td>
                    <td>{ai_decision}</td>
                    <td>{result_display}</td>
                    <td>{pnl_display}</td>
                </tr>
"""
        
        html += """
            </tbody>
        </table>
        <p style="text-align: center; margin-top: 15px; color: #666;">
            <small>View detailed signal breakdown in the "Detailed Trades" tab</small>
        </p>
    </div>
"""
    
    # Load model config for display
    model_config = None
    try:
        with open('model_config.json', 'r') as f:
            model_config = json.load(f)
    except:
        pass
    
    # Add Model Factors section
    if model_config:
        factors = model_config.get('factors', {})
        weights = model_config.get('weights', {})
        thresholds = model_config.get('thresholds', {})
        factor_desc = model_config.get('factor_descriptions', {})
        html += f"""
    <div class="results-section">
        <h2>⚙️ Model Configuration</h2>
        
        <!-- Signal Breakdown Table -->
        <h3 style="margin-top: 0; color: #667eea;">📊 Signal Breakdown</h3>
        <table style="margin-bottom: 20px; font-size: 0.9em;">
            <thead>
                <tr>
                    <th>Signal</th>
                    <th>Description</th>
                    <th>Weight</th>
                    <th>How It Works</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Momentum</strong></td>
                    <td>2-min candlestick trend</td>
                    <td style="text-align: center; font-weight: bold; color: #667eea;">{weights.get('momentum', 0)*100:.0f}%</td>
                    <td>Analyzes recent price movement direction. High = bullish, Low = bearish</td>
                </tr>
                <tr>
                    <td><strong>Orderbook</strong></td>
                    <td>Bid/ask balance</td>
                    <td style="text-align: center; font-weight: bold; color: #667eea;">{weights.get('orderbook', 0)*100:.0f}%</td>
                    <td>Compares buy vs sell pressure in order book</td>
                </tr>
                <tr>
                    <td><strong>Trade Flow</strong></td>
                    <td>Recent trade direction</td>
                    <td style="text-align: center; font-weight: bold; color: #667eea;">{weights.get('trade_flow', 0)*100:.0f}%</td>
                    <td>Looks at recent trades to see buyer vs seller dominance</td>
                </tr>
                <tr>
                    <td><strong>Liquidity</strong></td>
                    <td>Top-of-book depth</td>
                    <td style="text-align: center; font-weight: bold; color: #667eea;">{weights.get('liquidity', 0)*100:.0f}%</td>
                    <td>Measures market depth - more liquidity = more reliable signals</td>
                </tr>
                <tr>
                    <td><strong>Volatility</strong></td>
                    <td>Dampening multiplier</td>
                    <td style="text-align: center; font-weight: bold; color: #667eea;">{weights.get('volatility', 0)*100:.0f}%</td>
                    <td>High volatility reduces confidence, low volatility increases it</td>
                </tr>
            </tbody>
        </table>
        
        <!-- Decision Logic -->
        <h3 style="color: #667eea;">🎯 Decision Logic</h3>
        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; text-align: center;">
                <div style="background: #d1fae5; padding: 12px; border-radius: 6px;">
                    <div style="font-size: 0.8em; color: #065f46;">BUY YES when</div>
                    <div style="font-size: 1.5em; font-weight: bold; color: #10b981;">Score &gt; {thresholds.get('buy_yes', 55)}</div>
                </div>
                <div style="background: #fef3c7; padding: 12px; border-radius: 6px;">
                    <div style="font-size: 0.8em; color: #92400e;">SKIP when</div>
                    <div style="font-size: 1.5em; font-weight: bold; color: #f59e0b;">{thresholds.get('buy_no', 45)}-{thresholds.get('buy_yes', 55)}</div>
                </div>
                <div style="background: #fee2e2; padding: 12px; border-radius: 6px;">
                    <div style="font-size: 0.8em; color: #991b1b;">BUY NO when</div>
                    <div style="font-size: 1.5em; font-weight: bold; color: #ef4444;">Score &lt; {thresholds.get('buy_no', 45)}</div>
                </div>
            </div>
        </div>
        
        <!-- Edge & Distance Factors -->
        <h3 style="color: #667eea;">📐 Trading Factors</h3>
        <table style="font-size: 0.9em;">
            <thead>
                <tr>
                    <th>Factor</th>
                    <th>Value</th>
                    <th>Description</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Min Edge</strong></td>
                    <td style="font-weight: bold;">{factors.get('min_edge_percent', 0.01)*100:.1f}%</td>
                    <td>{factor_desc.get('min_edge_percent', 'Minimum expected profit to trade')}</td>
                </tr>
                <tr>
                    <td><strong>High Confidence Edge</strong></td>
                    <td style="font-weight: bold;">{factors.get('high_confidence_edge_percent', 0.15)*100:.0f}%</td>
                    <td>{factor_desc.get('high_confidence_edge_percent', 'Edge that triggers high confidence')}</td>
                </tr>
                <tr>
                    <td><strong>Critical Distance</strong></td>
                    <td style="font-weight: bold;">${factors.get('critical_distance_dollars', 100):,.0f}</td>
                    <td>{factor_desc.get('critical_distance_dollars', 'Skip if BTC within this $ of strike')}</td>
                </tr>
                <tr>
                    <td><strong>Safe Distance</strong></td>
                    <td style="font-weight: bold;">${factors.get('safe_distance_dollars', 500):,.0f}</td>
                    <td>{factor_desc.get('safe_distance_dollars', 'High confidence if BTC beyond this from strike')}</td>
                </tr>
                <tr>
                    <td><strong>Strong Consensus</strong></td>
                    <td style="font-weight: bold;">{factors.get('strong_market_consensus', 70)}</td>
                    <td>{factor_desc.get('strong_market_consensus', 'Market strongly expects YES if bid > this')}</td>
                </tr>
                <tr>
                    <td><strong>Weak Consensus</strong></td>
                    <td style="font-weight: bold;">{factors.get('weak_market_consensus', 30)}</td>
                    <td>{factor_desc.get('weak_market_consensus', 'Market strongly expects NO if bid < this')}</td>
                </tr>
            </tbody>
        </table>
        <p style="margin-top: 15px; color: #666; font-size: 0.85em;">📝 Edit <code>model_config.json</code> to adjust these factors. Gemini analyzes but does NOT auto-tune.</p>
    </div>
"""
    
    # Add AI Performance Insights section with full log
    html += """
    <div class="results-section">
        <h2>📊 AI Performance Insights</h2>
        <div class="ai-analysis">
"""
    
    # Show all insights from log (newest first)
    if ai_insights_log:
        for insight in reversed(ai_insights_log[-10:]):  # Last 10 insights
            timestamp = insight.get('timestamp', 'Unknown')
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                timestamp = dt.strftime('%Y-%m-%d %H:%M')
            except:
                pass
            
            insight_type = insight.get('type', 'unknown')
            
            if insight_type == 'run_analysis':
                perf = insight.get('performance', {})
                html += f"""
            <div class="ai-analysis-text" style="margin-bottom: 15px; padding: 10px; background: #f8f9fa; border-radius: 6px; border-left: 3px solid #667eea;">
                <strong style="color: #667eea;">📈 Run Analysis</strong> <span style="color: #999; font-size: 0.85em;">{timestamp}</span>
                <p style="margin: 8px 0 5px 0;">{insight.get('analysis', 'N/A')}</p>
                <p style="margin: 0; color: #666;"><strong>Suggestion:</strong> {insight.get('suggestion', 'N/A')}</p>
                <p style="margin: 5px 0 0 0; color: #888; font-size: 0.85em;">Performance: {perf.get('wins', 0)}W / {perf.get('losses', 0)}L ({perf.get('win_rate', 0)*100:.0f}%)</p>
            </div>
"""
            elif insight_type == 'settlement_analysis':
                outcome_color = '#10b981' if insight.get('outcome') == 'Won' else '#ef4444'
                html += f"""
            <div class="ai-analysis-text" style="margin-bottom: 15px; padding: 10px; background: #f8f9fa; border-radius: 6px; border-left: 3px solid {outcome_color};">
                <strong style="color: {outcome_color};">{'✅' if insight.get('outcome') == 'Won' else '❌'} Trade Settled: {insight.get('outcome', 'Unknown')}</strong> <span style="color: #999; font-size: 0.85em;">{timestamp}</span>
                <p style="margin: 8px 0 5px 0;"><strong>Why:</strong> {insight.get('why', 'N/A')}</p>
                <p style="margin: 0; color: #666;"><strong>Lesson:</strong> {insight.get('lesson', 'N/A')}</p>
            </div>
"""
    else:
        html += """
            <div class="ai-analysis-text">
                <p style="color: #666;">No AI insights yet. Insights will appear here after each run.</p>
            </div>
"""
    
    html += """
        </div>
    </div>
"""
    
    # Close overview tab and start How It Works tab
    html += """
    </div>
    
    <div id="how-it-works-tab" class="tab-content">
        <div style="max-width: 900px; margin: 0 auto;">
            <h2 style="color: #333; margin-bottom: 30px;">🤖 How This Works</h2>
            
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px;">
                <h3 style="margin-top: 0; font-size: 1.4em;">💡 The Simple Version</h3>
                <p style="font-size: 1.15em; line-height: 1.7; margin-bottom: 0;">
                    This is a robot that targets Spotify daily markets on Kalshi. Each run, it scans for Spotify-themed daily markets, scores market conditions (pricing/spread/timing), optionally asks an AI "should I trade?", and then either places a small trade or skips.
                </p>
            </div>
            
            <h3 style="color: #333; margin-top: 30px;">🎯 What's a Prediction Market?</h3>
            <div style="background: #e8f4f8; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #0891b2;">
                <p style="margin: 0 0 15px 0; font-size: 1.1em;">It's a place where you can make predictions about the future. If your prediction is correct, you win money. If you're wrong, you lose what you put in.</p>
                <div style="background: white; padding: 15px; border-radius: 6px;">
                    <p style="margin: 0 0 10px 0; font-weight: bold;">🪙 Example:</p>
                    <p style="margin: 0 0 5px 0;">Question: "Will a Spotify daily event happen?" (example)</p>
                    <p style="margin: 0 0 5px 0;">👉 You put <strong>20 cents</strong> on "YES"</p>
                    <p style="margin: 0 0 5px 0;">✅ If YES resolves true → You get <strong>$1.00</strong> (profit: 80 cents!)</p>
                    <p style="margin: 0;">❌ If it resolves NO → You lose your 20 cents</p>
                </div>
            </div>
            
            <h3 style="color: #333;">🔄 What Happens Every 15 Minutes</h3>
            <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #667eea;">
                <div style="display: grid; gap: 12px;">
                    <div style="background: white; padding: 15px; border-left: 4px solid #10b981; border-radius: 4px;">
                        <strong style="font-size: 1.1em;">1️⃣ Look at the market</strong><br>
                        <span style="color: #666;">Are spreads tight? Is there activity? Is the market close to closing?</span>
                    </div>
                    <div style="background: white; padding: 15px; border-left: 4px solid #3b82f6; border-radius: 4px;">
                        <strong style="font-size: 1.1em;">2️⃣ Give it a Score</strong><br>
                        <span style="color: #666;">0-100 score. High = price probably going up. Low = probably going down.</span>
                    </div>
                    <div style="background: white; padding: 15px; border-left: 4px solid #8b5cf6; border-radius: 4px;">
                        <strong style="font-size: 1.1em;">3️⃣ Ask the AI</strong><br>
                        <span style="color: #666;">"Hey Gemini, here's what I see. Should I predict or wait?"</span>
                    </div>
                    <div style="background: white; padding: 15px; border-left: 4px solid #f59e0b; border-radius: 4px;">
                        <strong style="font-size: 1.1em;">4️⃣ Predict or Skip</strong><br>
                        <span style="color: #666;">If AI says predict → spends ~20 cents. If AI says skip → waits for better chance.</span>
                    </div>
                    <div style="background: white; padding: 15px; border-left: 4px solid #ef4444; border-radius: 4px;">
                        <strong style="font-size: 1.1em;">5️⃣ Wait for Result</strong><br>
                        <span style="color: #666;">At close: Did the market resolve YES or NO? Win or lose?</span>
                    </div>
                </div>
            </div>
            
            <h3 style="color: #333;">🎬 Example: A Smart Skip</h3>
            <div style="background: #fef3c7; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #f59e0b;">
                <p style="margin: 0 0 15px 0; font-size: 1.1em;">🪙 <strong>The Question:</strong> "Will the Spotify daily market resolve YES?" (example)</p>
                
                <div style="display: grid; gap: 10px;">
                    <div style="background: white; padding: 15px; border-radius: 6px;">
                        <strong>📊 Bot checks the market:</strong>
                        <p style="margin: 8px 0 0 0;">Price is dropping ⬇️ ... Score: <strong style="color: #d97706;">38/100</strong> (low = probably going down)</p>
                    </div>
                    
                    <div style="background: white; padding: 15px; border-radius: 6px;">
                        <strong>🤖 Bot asks AI:</strong>
                        <p style="margin: 8px 0 0 0;">"Should I trade YES on this Spotify daily market?"</p>
                    </div>
                    
                    <div style="background: #fef08a; padding: 15px; border-radius: 6px;">
                        <strong>💭 AI says:</strong>
                        <p style="margin: 8px 0 0 0;">"Nope! Score is low, price is dropping. <strong>SKIP.</strong> Wait for a better chance."</p>
                    </div>
                    
                    <div style="background: #fee2e2; padding: 15px; border-radius: 6px;">
                        <strong>⏰ One hour later:</strong>
                        <p style="margin: 8px 0 0 0;">Market resolved NO ❌</p>
                        <p style="margin: 5px 0 0 0; color: #666;">Good thing it skipped! Would have lost 20 cents. 💰</p>
                    </div>
                </div>
            </div>
            
            <h3 style="color: #333;">🧠 Does It Get Smarter?</h3>
            <div style="background: #e0e7ff; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #667eea;">
                <p style="margin: 0 0 15px 0; font-size: 1.05em;">Yes! The AI looks at past wins and losses to make better decisions.</p>
                <div style="background: white; padding: 15px; border-radius: 6px;">
                    <p style="margin: 0 0 8px 0;">📅 <strong>Day 1:</strong> Makes 10 predictions. Wins 6, loses 4.</p>
                    <p style="margin: 0 0 8px 0;">🔍 <strong>Day 2:</strong> AI notices: "I lost when the market was crazy. Next time, I'll skip those."</p>
                    <p style="margin: 0;">📈 <strong>Day 3:</strong> Skips the risky ones. Wins more!</p>
                </div>
            </div>
            
            <h3 style="color: #333;">❓ Quick Questions</h3>
            <div style="display: grid; gap: 12px;">
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px;">
                    <p style="margin: 0;"><strong>🎲 Is this just luck?</strong><br>
                    <span style="color: #666;">No! This uses math and AI to find good predictions. It's data-driven, not random.</span></p>
                </div>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px;">
                    <p style="margin: 0;"><strong>💸 Can it lose money?</strong><br>
                    <span style="color: #666;">Yes, sometimes. Nobody can predict the future perfectly. The goal is to win more than you lose.</span></p>
                </div>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px;">
                    <p style="margin: 0;"><strong>⏭️ Why does it skip sometimes?</strong><br>
                    <span style="color: #666;">When it's not sure, it waits. Skipping bad predictions is just as smart as making good ones!</span></p>
                </div>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px;">
                    <p style="margin: 0;"><strong>💰 How much per prediction?</strong><br>
                    <span style="color: #666;">About 20 cents. Small amounts = small risk while it learns.</span></p>
                </div>
            </div>
        </div>
    </div>
    
    <div id="trades-tab" class="tab-content">
        <h2 style="margin: 20px 0; color: #333;">📈 Detailed Trade History</h2>
"""
    
    # Generate run cards
    if runs:
        for run_idx, run in enumerate(runs):
            # Get run timestamp (first trade in run) and convert to Pacific time
            run_time = run[0]['timestamp']
            formatted_time = to_pacific_time(run_time)
            
            # Extract assets in this run
            assets = list(set([t['asset'] for t in run]))
            
            # Generate decision summaries per asset
            decisions = []
            asset_decisions = defaultdict(list)
            for trade in run:
                asset_decisions[trade['asset']].append(trade)
            
            for asset, asset_trades in asset_decisions.items():
                # Find the main decision for this asset
                bought_trades = [t for t in asset_trades if t['status'] == 'Success']
                skipped_trades = [t for t in asset_trades if t.get('action') in ['NO TRADE', 'SKIPPED']]
                failed_trades = [t for t in asset_trades if t['status'] == 'Failed']
                
                if bought_trades:
                    for trade in bought_trades:
                        action = trade['action']
                        # Add score if available
                        decision_log = trade.get('decision_log', {})
                        score_str = ""
                        if isinstance(decision_log, dict) and 'composite_score' in decision_log:
                            score = decision_log.get('composite_score')
                            score_str = f" | Score: {score:.1f}"
                        decisions.append({
                            'asset': asset,
                            'text': f"{asset}: {action}{score_str}",
                            'class': 'bought'
                        })
                elif skipped_trades:
                    first_skipped = skipped_trades[0]
                    reason = first_skipped.get('status', 'Neutral zone')
                    # Remove limit price mention (" < our X¢" part)
                    if 'market' in reason and '<' in reason:
                        reason = reason.split('<')[0].strip()
                    score_str = ""
                    decision_log = first_skipped.get('decision_log', {})
                    if isinstance(decision_log, dict) and 'composite_score' in decision_log:
                        score = decision_log.get('composite_score')
                        score_str = f" | Score: {score:.1f}"
                    decisions.append({
                        'asset': asset,
                        'text': f"{asset}: {reason}{score_str}",
                        'class': 'skipped'
                    })
                elif failed_trades:
                    decisions.append({
                        'asset': asset,
                        'text': f"{asset}: Failed - {failed_trades[0]['status']}",
                        'class': 'failed'
                    })
                else:
                    decisions.append({
                        'asset': asset,
                        'text': f"{asset}: {asset_trades[0]['status']}",
                        'class': 'skipped'
                    })
            
            # Create asset badges
            asset_badges = ''
            for asset in sorted(assets):
                asset_lower = asset.lower()
                if asset_lower == 'spotify':
                    asset_badges += '<span class="asset-badge spotify">Spotify</span>'
                elif asset_lower == 'btc':
                    asset_badges += '<span class="asset-badge btc">₿ BTC</span>'
                elif asset_lower == 'eth':
                    asset_badges += '<span class="asset-badge eth">Ξ ETH</span>'
                else:
                    asset_badges += f'<span class="asset-badge">{asset}</span>'
            
            # Note: Gemini analysis is batched at workflow level (not per-run)
            # This saves API quota - only 2 Gemini calls per report instead of N calls per run
            gemini_analysis = None
            
            # Build decisions HTML
            decisions_html = ''
            for decision in decisions:
                decisions_html += f'<div class="decision-item {decision["class"]}">{decision["text"]}</div>'
            
            # Build AI analysis HTML (legacy sentiment display removed - now using multi-signal model)
            ai_analysis_html = ''
            if gemini_analysis:
                confidence = gemini_analysis.get('confidence', 5)
                model_used = gemini_analysis.get('model', 'gemini-2.5-flash')
                conf_class = 'high' if confidence >= 7 else 'medium' if confidence >= 4 else 'low'
                ai_analysis_html = f'''
                <div class="ai-analysis">
                    <h4>🤖 AI Analysis</h4>
                    <div style="font-size: 0.85em; color: #666; margin-bottom: 8px;">Model: {model_used}</div>
                    <div class="ai-analysis-text">{gemini_analysis.get('analysis', 'Analysis unavailable')}</div>
                    <div>Confidence Level: <span class="confidence-level {conf_class}">{confidence}/10</span></div>
                </div>'''
            
            # Build details table - last column is generic context (legacy field name preserved)
            details_table = '<table><thead><tr><th>Time</th><th>Asset</th><th>Market</th><th>Action</th><th>Price</th><th>Contracts</th><th>Result</th><th>P&L</th><th>Status</th><th>Context</th></tr></thead><tbody>'
            for trade in run:
                # Convert timestamp to Pacific time
                trade_time = to_pacific_time(trade['timestamp'])
                
                status_lower = trade['status'].lower()
                if 'success' in status_lower:
                    status_class = 'success'
                elif 'failed' in status_lower or 'error' in status_lower:
                    status_class = 'failed'
                else:
                    status_class = 'no-trade'
                
                action_lower = trade['action'].lower()
                if 'buy yes' in action_lower:
                    action_display = '🟢 Buy YES'
                elif 'buy no' in action_lower:
                    action_display = '🔴 Buy NO'
                else:
                    action_display = trade['action']
            
                sentiment_display = f"{trade.get('sentiment', 'N/A')}" if trade.get('sentiment') is not None else "N/A"
                
                # Format price and contracts - show actual execution price from decision_log
                decision_log = trade.get('decision_log', {})
                if isinstance(decision_log, dict):
                    price = decision_log.get('execution_price')
                else:
                    price = None
                
                if price:
                    price_str = f"${price/100:.2f}"
                else:
                    # Fallback to top-level price if execution_price not available
                    price = trade.get('price')
                    if price:
                        price_str = f"${price/100:.2f}"
                    else:
                        price_str = 'N/A'
                
                contracts_str = str(trade.get('contracts', 'N/A')) if trade.get('contracts') else 'N/A'
                cost_str = ''
                if price and trade.get('contracts'):
                    cost = (price / 100.0) * trade.get('contracts', 0)
                    cost_str = f"<br><small>${cost:.2f} total</small>"
                
                # Get settlement data for result and P&L
                settlement = trade.get('settlement', {})
                result_status = settlement.get('status', 'Unknown')
                pnl = calculate_trade_pnl(trade)
                
                # Format result display
                if result_status == 'Won':
                    result_display = '<span style="color: #10b981; font-weight: bold;">✓ Won</span>'
                elif result_status == 'Lost':
                    result_display = '<span style="color: #ef4444; font-weight: bold;">✗ Lost</span>'
                elif result_status == 'Open':
                    result_display = '<span style="color: #f59e0b; font-weight: bold;">⏳ Open</span>'
                else:
                    result_display = '<span style="color: #666;">— Unknown</span>'
                
                # Format P&L display
                if pnl > 0:
                    pnl_display = f'<span style="color: #10b981; font-weight: bold;">+${pnl:.2f}</span>'
                elif pnl < 0:
                    pnl_display = f'<span style="color: #ef4444; font-weight: bold;">-${abs(pnl):.2f}</span>'
                else:
                    pnl_display = '<span style="color: #666;">$0.00</span>'
                
                # Build decision log details
                decision_log = trade.get('decision_log')
                details_button = ''
                details_content = ''
                
                # Get BTC price at decision time
                btc_price_display = "—"
                if isinstance(decision_log, dict) and decision_log.get('current_price'):
                    btc_price = decision_log.get('current_price')
                    btc_price_display = f"${btc_price:,.0f}"
                elif trade["action"] in ["NO TRADE", "Market Not Found", "ERROR"]:
                    btc_price_display = "—"
                
                if decision_log and trade["action"] not in ["Market Not Found", "ERROR"]:
                    # Show details for actual trades AND skipped/no-trade (to show full Gemini reasoning)
                    if isinstance(decision_log, dict):
                        details_id = f"details-{run_idx}-{run.index(trade)}"
                        
                        decision_html = '<div class="decision-details" style="background-color: #f5f5f5; padding: 12px; border-radius: 4px; margin-top: 8px;">'
                        
                        # Show Gemini details if available (for both executed and skipped trades)
                        if 'gemini_model' in decision_log:
                            gemini_model = decision_log.get('gemini_model')
                            # Show for any actual Gemini model OR when MODEL_ONLY fallback is used
                            decision_html += f"<div style='background-color: {'#f0fdf4' if gemini_model != 'MODEL_ONLY' else '#fef3c7'}; padding: 8px; border-radius: 4px; border-left: 3px solid {'#10b981' if gemini_model != 'MODEL_ONLY' else '#f59e0b'}; margin-bottom: 10px;'>"
                            decision_html += f"<strong>🤖 Gemini AI Decision</strong><br>"
                            decision_html += f"<strong>Model:</strong> {gemini_model}<br>"
                            decision_html += f"<strong>Decision:</strong> {decision_log.get('gemini_decision')}<br>"
                            if decision_log.get('gemini_reasoning'):
                                decision_html += f"<strong>Reasoning:</strong> {decision_log.get('gemini_reasoning')}<br>"
                            if decision_log.get('gemini_confidence'):
                                decision_html += f"<strong>Confidence:</strong> {decision_log.get('gemini_confidence')}/10<br>"
                            decision_html += f"</div>"
                        
                        # Show multi-signal framework details if available
                        if 'composite_score' in decision_log:
                            composite_score = decision_log.get('composite_score')
                            confidence = decision_log.get('confidence', 0)
                            
                            score_color = '#10b981' if composite_score > 55 else '#ef4444' if composite_score < 45 else '#f59e0b'
                            decision_html += f"<div><strong>🎯 Composite Score:</strong> <span style='color: {score_color}; font-weight: bold;'>{composite_score:.1f}</span> (Confidence: {confidence:.1f}%)</div>"
                            
                            # Check for new smart_signals format with 'signals' dict
                            signals = decision_log.get('signals', {})
                            if signals:
                                # New smart_signals_v2_fast format
                                distance = signals.get('distance', {})
                                momentum = signals.get('momentum', {})
                                velocity = signals.get('velocity', {})
                                market_wisdom = signals.get('market_wisdom', {})
                                volatility = signals.get('volatility', {})
                                time_decay = signals.get('time_decay', {})
                                
                                yes_edge = decision_log.get('yes_edge', 0)
                                no_edge = decision_log.get('no_edge', 0)
                                
                                decision_html += f"<div style='margin-top: 8px; font-size: 0.9em;'><strong>📊 Signal Breakdown:</strong></div>"
                                decision_html += f"<table style='width: 100%; font-size: 0.85em; margin-top: 4px; border-collapse: collapse; border: 1px solid #e5e7eb;'>"
                                decision_html += f"<tr style='background: #e5e7eb;'><th style='padding: 6px; text-align: left;'>Signal</th><th style='padding: 6px; text-align: left;'>Value</th><th style='padding: 6px; text-align: center;'>Assessment</th></tr>"
                                
                                # Distance
                                dist_val = distance.get('value', 0)
                                dist_dir = distance.get('direction', '')
                                dist_zone = distance.get('zone', '')
                                dist_color = '#10b981' if dist_zone == 'safe' else '#ef4444' if dist_zone == 'critical' else '#f59e0b'
                                decision_html += f"<tr style='border-bottom: 1px solid #e5e7eb;'><td style='padding: 6px;'><strong>Distance</strong></td><td style='padding: 6px;'>${dist_val:,.0f} {dist_dir}</td><td style='padding: 6px; text-align: center; color: {dist_color}; font-weight: bold;'>{dist_zone.upper() if dist_zone else 'N/A'}</td></tr>"
                                
                                # Momentum
                                mom_dir = momentum.get('direction', 'neutral')
                                mom_str = momentum.get('strength', 0)
                                mom_emoji = '📈' if mom_dir == 'bullish' else '📉' if mom_dir == 'bearish' else '➖'
                                mom_color = '#10b981' if mom_dir == 'bullish' else '#ef4444' if mom_dir == 'bearish' else '#f59e0b'
                                decision_html += f"<tr style='border-bottom: 1px solid #e5e7eb;'><td style='padding: 6px;'><strong>Momentum</strong></td><td style='padding: 6px;'>Strength: {mom_str:.1f}</td><td style='padding: 6px; text-align: center; color: {mom_color}; font-weight: bold;'>{mom_emoji} {mom_dir.upper()}</td></tr>"
                                
                                # Velocity
                                vel_val = velocity.get('value', 0)
                                vel_accel = velocity.get('acceleration', 'stable')
                                vel_emoji = '🚀' if vel_accel == 'accelerating' else '🐢' if vel_accel == 'decelerating' else '➡️'
                                decision_html += f"<tr style='border-bottom: 1px solid #e5e7eb;'><td style='padding: 6px;'><strong>Velocity</strong></td><td style='padding: 6px;'>${vel_val:+,.0f}/min</td><td style='padding: 6px; text-align: center;'>{vel_emoji} {vel_accel.upper()}</td></tr>"
                                
                                # Market Wisdom
                                mw_consensus = market_wisdom.get('consensus', 'neutral')
                                mw_prob = market_wisdom.get('implied_prob', 50)
                                mw_color = '#10b981' if mw_consensus == 'bullish' else '#ef4444' if mw_consensus == 'bearish' else '#f59e0b'
                                decision_html += f"<tr style='border-bottom: 1px solid #e5e7eb;'><td style='padding: 6px;'><strong>Market Wisdom</strong></td><td style='padding: 6px;'>Implied: {mw_prob:.0f}%</td><td style='padding: 6px; text-align: center; color: {mw_color}; font-weight: bold;'>{mw_consensus.upper()}</td></tr>"
                                
                                # Volatility
                                vol_regime = volatility.get('regime', 'NORMAL')
                                vol_color = '#ef4444' if vol_regime == 'HIGH' else '#10b981' if vol_regime == 'LOW' else '#f59e0b'
                                decision_html += f"<tr style='border-bottom: 1px solid #e5e7eb;'><td style='padding: 6px;'><strong>Volatility</strong></td><td style='padding: 6px;'>{vol_regime}</td><td style='padding: 6px; text-align: center; color: {vol_color};'>{'⚠️' if vol_regime == 'HIGH' else '✓'}</td></tr>"
                                
                                # Time Decay
                                td_mins = time_decay.get('minutes_remaining', 60)
                                td_phase = time_decay.get('phase', 'normal')
                                td_color = '#ef4444' if td_phase == 'critical' else '#f59e0b' if td_phase == 'urgent' else '#10b981'
                                decision_html += f"<tr style='border-bottom: 1px solid #e5e7eb;'><td style='padding: 6px;'><strong>Time</strong></td><td style='padding: 6px;'>{td_mins:.0f} min to expiry</td><td style='padding: 6px; text-align: center; color: {td_color};'>{td_phase.upper()}</td></tr>"
                                
                                # Edge Summary
                                decision_html += f"<tr style='background: #f3f4f6; border-top: 2px solid #9ca3af;'><td style='padding: 6px;' colspan='2'><strong>Edge:</strong> YES {yes_edge:+.1f}% | NO {no_edge:+.1f}%</td><td style='padding: 6px; text-align: center;'><strong style='color: {score_color};'>Score: {composite_score:.1f}</strong></td></tr>"
                                decision_html += f"</table>"
                            else:
                                # Old format - check for individual scores
                                momentum_score = decision_log.get('momentum_score')
                                orderbook_score = decision_log.get('orderbook_score')
                                trade_flow_score = decision_log.get('trade_flow_score')
                                liquidity_score = decision_log.get('liquidity_score')
                                volatility_mult = decision_log.get('volatility_multiplier', 1.0)
                            
                                # Only show signal breakdown if we have the individual scores
                                if momentum_score is not None:
                                    # Calculate weighted contributions
                                    weighted_momentum = momentum_score * 0.55
                                    weighted_orderbook = orderbook_score * 0.15
                                    weighted_trade_flow = trade_flow_score * 0.15
                                    weighted_liquidity = liquidity_score * 0.10
                                    base_composite = weighted_momentum + weighted_orderbook + weighted_trade_flow + weighted_liquidity
                                
                                    # Interpret each signal's direction
                                    def signal_interpretation(score, signal_name):
                                        if score == 50.0:
                                            return 'neutral', '➖ Neutral'
                                        elif score > 70:
                                            return 'bullish', '📈 Strong Bullish'
                                        elif score > 55:
                                            return 'bullish', '📈 Bullish'
                                        elif score < 30:
                                            return 'bearish', '📉 Strong Bearish'
                                        elif score < 45:
                                            return 'bearish', '📉 Bearish'
                                        else:
                                            return 'neutral', '➖ Neutral'
                                    
                                    momentum_class, momentum_interp = signal_interpretation(momentum_score, 'Momentum')
                                    orderbook_class, orderbook_interp = signal_interpretation(orderbook_score, 'Orderbook')
                                    trade_flow_class, trade_flow_interp = signal_interpretation(trade_flow_score, 'Trade Flow')
                                    liquidity_class, liquidity_interp = signal_interpretation(liquidity_score, 'Liquidity')
                                    
                                    # Color coding for scores
                                    def score_color_style(score):
                                        if score > 55: return 'color: #10b981; font-weight: bold;'
                                        elif score < 45: return 'color: #ef4444; font-weight: bold;'
                                        else: return 'color: #f59e0b;'
                                    
                                    decision_html += f"<div style='margin-top: 8px; font-size: 0.9em;'><strong>📊 Signal Breakdown:</strong></div>"
                                    decision_html += f"<table style='width: 100%; font-size: 0.85em; margin-top: 4px; border-collapse: collapse; border: 1px solid #e5e7eb;'>"
                                    decision_html += f"<tr style='background: #e5e7eb;'><th style='padding: 6px; text-align: left;'>Signal</th><th style='padding: 6px; text-align: left;'>Description</th><th style='padding: 6px; text-align: center;'>Score</th><th style='padding: 6px; text-align: right;'>Weight</th><th style='padding: 6px; text-align: right;'>Contribution</th><th style='padding: 6px; text-align: center;'>Direction</th></tr>"
                                    decision_html += f"<tr style='border-bottom: 1px solid #e5e7eb;'><td style='padding: 6px;'><strong>Momentum</strong></td><td style='padding: 6px; font-size: 0.85em; color: #666;'>2-min candlestick trend</td><td style='padding: 6px; text-align: center; {score_color_style(momentum_score)}'>{momentum_score:.1f}</td><td style='padding: 6px; text-align: right;'>55%</td><td style='padding: 6px; text-align: right;'>{weighted_momentum:.1f}</td><td style='padding: 6px; text-align: center;'>{momentum_interp}</td></tr>"
                                    decision_html += f"<tr style='border-bottom: 1px solid #e5e7eb;'><td style='padding: 6px;'><strong>Orderbook</strong></td><td style='padding: 6px; font-size: 0.85em; color: #666;'>Bid/ask balance</td><td style='padding: 6px; text-align: center; {score_color_style(orderbook_score)}'>{orderbook_score:.1f}</td><td style='padding: 6px; text-align: right;'>15%</td><td style='padding: 6px; text-align: right;'>{weighted_orderbook:.1f}</td><td style='padding: 6px; text-align: center;'>{orderbook_interp}</td></tr>"
                                    decision_html += f"<tr style='border-bottom: 1px solid #e5e7eb;'><td style='padding: 6px;'><strong>Trade Flow</strong></td><td style='padding: 6px; font-size: 0.85em; color: #666;'>Recent trade direction</td><td style='padding: 6px; text-align: center; {score_color_style(trade_flow_score)}'>{trade_flow_score:.1f}</td><td style='padding: 6px; text-align: right;'>15%</td><td style='padding: 6px; text-align: right;'>{weighted_trade_flow:.1f}</td><td style='padding: 6px; text-align: center;'>{trade_flow_interp}</td></tr>"
                                    decision_html += f"<tr style='border-bottom: 1px solid #e5e7eb;'><td style='padding: 6px;'><strong>Liquidity</strong></td><td style='padding: 6px; font-size: 0.85em; color: #666;'>Top-of-book depth</td><td style='padding: 6px; text-align: center; {score_color_style(liquidity_score)}'>{liquidity_score:.1f}</td><td style='padding: 6px; text-align: right;'>10%</td><td style='padding: 6px; text-align: right;'>{weighted_liquidity:.1f}</td><td style='padding: 6px; text-align: center;'>{liquidity_interp}</td></tr>"
                                    decision_html += f"<tr style='background: #f3f4f6; border-top: 2px solid #9ca3af;'><td style='padding: 6px;' colspan='2'><strong>Base Score</strong></td><td style='padding: 6px; text-align: center;' colspan='2'></td><td style='padding: 6px; text-align: right;'><strong>{base_composite:.1f}</strong></td><td></td></tr>"
                                    volatility_label = 'Normal' if volatility_mult == 1.0 else 'High' if volatility_mult < 1.0 else 'Low'
                                    decision_html += f"<tr style='background: #f3f4f6;'><td style='padding: 6px;' colspan='2'><strong>Volatility Adj</strong> <span style='font-size: 0.85em; color: #666;'>({volatility_label})</span></td><td style='padding: 6px; text-align: center;' colspan='2'>× {volatility_mult:.2f}</td><td style='padding: 6px; text-align: right; {score_color_style(composite_score)}'><strong>{composite_score:.1f}</strong></td><td></td></tr>"
                                    decision_html += f"</table>"
                            
                            if 'decision_rationale' in decision_log:
                                decision_html += f"<div style='margin-top: 8px;'><strong>Decision Logic:</strong> {decision_log.get('decision_rationale')}</div>"
                        
                        if 'decision_reason' in decision_log:
                            decision_html += f"<div><strong>Decision Reason:</strong> {decision_log.get('decision_reason')}</div>"
                        if 'current_price' in decision_log:
                            price_label = 'BRTI' if trade.get('asset') == 'BTC' else 'ERTI' if trade.get('asset') == 'ETH' else 'Price'
                            decision_html += f"<div><strong>Current {price_label}:</strong> ${decision_log.get('current_price', 0):,.2f}</div>"
                        if 'selected_market' in decision_log:
                            decision_html += f"<div><strong>Selected Market:</strong> <code>{decision_log.get('selected_market')}</code></div>"
                        if 'execution_price' in decision_log:
                            exec_price = decision_log.get('execution_price')
                            if exec_price is not None:
                                decision_html += f"<div><strong>Execution Price:</strong> {exec_price}¢ = ${exec_price/100:.2f}</div>"
                        if 'execution_contracts' in decision_log:
                            decision_html += f"<div><strong>Contracts:</strong> {decision_log.get('execution_contracts')}</div>"
                        if 'execution_status' in decision_log:
                            decision_html += f"<div><strong>Status:</strong> {decision_log.get('execution_status')}</div>"
                        
                        # Add settlement details if available
                        settlement = trade.get('settlement', {})
                        if settlement and settlement.get('status') in ['Won', 'Lost']:
                            decision_html += f"<div style='margin-top: 8px; border-top: 1px solid #ddd; padding-top: 8px;'>"
                            decision_html += f"<strong>Settlement:</strong><br>"
                            if settlement.get('revenue'):
                                decision_html += f"  • Revenue: ${settlement.get('revenue', 0):.2f}<br>"
                            if settlement.get('cost'):
                                decision_html += f"  • Cost: ${settlement.get('cost', 0):.2f}<br>"
                            if settlement.get('fee'):
                                decision_html += f"  • Fee: ${settlement.get('fee', 0):.2f}<br>"
                            if settlement.get('pnl') is not None:
                                pnl_val = settlement.get('pnl')
                                pnl_color = '#10b981' if pnl_val > 0 else '#ef4444' if pnl_val < 0 else '#666'
                                decision_html += f"  • P&L: <span style='color: {pnl_color}; font-weight: bold;'>${pnl_val:+.2f}</span><br>"
                            decision_html += f"</div>"
                        
                        decision_html += '</div>'
                        
                        details_content = f'<div id="{details_id}" class="decision-details-content" style="display:none;">{decision_html}</div>'
                    else:
                        details_button = '<span style="color: #666;">No details</span>'
                else:
                    details_button = '<span style="color: #999;">-</span>'
                
                # Clean status display - remove limit price mention
                display_status = trade["status"]
                if 'market' in display_status and '<' in display_status:
                    display_status = display_status.split('<')[0].strip()
                
                details_table += f'''
                    <tr>
                        <td>{trade_time}</td>
                        <td><strong>{trade["asset"]}</strong></td>
                        <td><code>{trade["market"]}</code></td>
                        <td>{action_display}</td>
                        <td>{price_str}{cost_str}</td>
                        <td>{contracts_str}</td>
                        <td>{result_display}</td>
                        <td>{pnl_display}</td>
                        <td><span class="status {status_class}">{display_status}</span></td>
                        <td>{btc_price_display}</td>
                    </tr>'''
                if details_content:
                    # Remove the display:none to show details inline
                    details_inline = details_content.replace("style=\"display:none;\"", "style=\"display:block; margin-top: 10px;\"")
                    details_table += f'<tr><td colspan="10" style="padding: 10px 15px;">{details_inline}</td></tr>'
            details_table += '</tbody></table>'
            
            html += f'''
    <div class="run-card">
        <div class="run-header">
            <div>
                <strong>Run #{len(runs) - run_idx}</strong>
                <div class="run-time">{formatted_time}</div>
            </div>
            <div class="run-assets">
                {asset_badges}
            </div>
        </div>
        <div class="run-decisions">
            {decisions_html if decisions_html else '<div class="decision-item skipped">No decisions made</div>'}
        </div>
        {ai_analysis_html}
        <div class="run-details">
            <div class="run-details-content" id="details-{run_idx}">
                {details_table}
            </div>
        </div>
    </div>
'''
    else:
        html += """
    <div class="no-trades">
        <h2>No workflow runs yet</h2>
        <p>The bot hasn't executed any workflow runs yet. Check back after the next run!</p>
    </div>
"""
    
    # Close detailed trades tab
    html += """
    </div> <!-- end trades-tab -->
    
    <!-- Diagnostics Tab (includes AI Analysis, Debug Logs, and System Diagnostics) -->
    <div id="diagnostics-tab" class="tab-content">
        <div class="ai-analysis-details-section">
            <h2>🤖 AI Analysis Details & Error Tracking</h2>
            <p style="color: #666; margin-bottom: 20px;">Detailed breakdown of all AI analysis attempts, successes, and error information including rate limit details.</p>
"""
    
    # Build Gemini API Key Status section
    gemini_api_key = os.getenv('GEMINI_API_KEY', '')
    gemini_status = f"✓ PRESENT ({len(gemini_api_key)} chars)" if gemini_api_key else "✗ NOT FOUND - Using model-based decision fallback"
    gemini_decision_source = "🤖 Gemini AI" if gemini_api_key else "📊 Model-Based Fallback"
    gemini_framework = "gemini-ai-with-fallback" if gemini_api_key else "multi-signal (Gemini unavailable)"
    gemini_status_msg = "Attempting Gemini API calls with 7-model fallback chain" if gemini_api_key else "⚠️ GEMINI API KEY MISSING - All trades using model-only decisions"
    
    html += f"""
            <!-- Gemini API Key Status Section -->
            <div style="background-color: #f3f4f6; padding: 15px; border-radius: 4px; margin-bottom: 20px; border-left: 4px solid #6366f1;">
                <h3>🔑 Gemini API Key Status</h3>
                <div style="font-size: 0.95em; line-height: 1.6;">
                    <div><strong>GEMINI_API_KEY Environment Variable:</strong> <span style="font-family: monospace; background-color: white; padding: 2px 6px; border-radius: 3px;">{gemini_status}</span></div>
                    <div style="margin-top: 8px; padding: 8px; background-color: white; border-radius: 3px; font-size: 0.9em;">
                        <strong>Decision Source Used:</strong><br>
                        <div style="margin-left: 10px; margin-top: 5px;">
                            • <strong>Latest Trades:</strong> {gemini_decision_source}<br>
                            • <strong>Framework:</strong> {gemini_framework}<br>
                            • <strong>Status:</strong> {gemini_status_msg}
                        </div>
                    </div>
                </div>
            </div>
"""
    
    # Count gemini vs model-only decisions from trades
    gemini_count = 0
    model_only_count = 0
    no_decision_count = 0
    if trades:
        for trade in trades:
            decision_log = trade.get('decision_log', {})
            if isinstance(decision_log, dict):
                # Check for gemini_model field first
                gemini_model = decision_log.get('gemini_model')
                if gemini_model:
                    if gemini_model == 'MODEL_ONLY':
                        model_only_count += 1
                    else:
                        # Any other model name = Gemini AI was used
                        gemini_count += 1
                elif 'framework' in decision_log and decision_log.get('framework') == 'gemini-ai-with-fallback':
                    # If framework indicates gemini-ai-with-fallback but no gemini_model, check if it was a skip
                    if decision_log.get('action_taken') and 'SKIP' not in decision_log.get('action_taken', ''):
                        gemini_count += 1
                    else:
                        model_only_count += 1
                else:
                    no_decision_count += 1
    
    html += f"""
            <!-- Gemini Decision Summary Section -->
            <div style="background-color: #f0fdf4; padding: 15px; border-radius: 4px; margin-bottom: 20px; border-left: 4px solid #16a34a;">
                <h3>📊 Gemini Decision Summary</h3>
                <div style="font-size: 0.95em;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                        <div style="background-color: white; padding: 10px; border-radius: 3px; border-left: 3px solid #10b981;">
                            <div style="font-size: 1.2em; font-weight: bold; color: #10b981;">{gemini_count}</div>
                            <div style="color: #666; font-size: 0.9em;">Trades using Gemini AI</div>
                        </div>
                        <div style="background-color: white; padding: 10px; border-radius: 3px; border-left: 3px solid #f59e0b;">
                            <div style="font-size: 1.2em; font-weight: bold; color: #f59e0b;">{model_only_count}</div>
                            <div style="color: #666; font-size: 0.9em;">Trades using Model Fallback</div>
                        </div>
                    </div>
                    <div style="margin-top: 10px; padding: 8px; background-color: white; border-radius: 3px; font-size: 0.9em; color: #666;">
                        <strong>Expected Behavior:</strong> If GEMINI_API_KEY is present, count above should show Gemini AI usage.
                        If it shows only "Model Fallback", check that GEMINI_API_KEY is configured in GitHub Secrets.
                    </div>
                </div>
            </div>
"""
    
    # Add AI Analysis tracking data
    ai_data = ai_tracker.to_dict()
    
    if ai_data['attempts']:
        html += """
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 4px; margin-bottom: 20px;">
                <h3>📊 Analysis Attempts Summary</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background-color: #e0e0e0;">
                            <th style="padding: 8px; text-align: left; border: 1px solid #ccc;">Type</th>
                            <th style="padding: 8px; text-align: left; border: 1px solid #ccc;">Model</th>
                            <th style="padding: 8px; text-align: left; border: 1px solid #ccc;">Status</th>
                            <th style="padding: 8px; text-align: left; border: 1px solid #ccc;">Error Details</th>
                            <th style="padding: 8px; text-align: left; border: 1px solid #ccc;">Timestamp</th>
                        </tr>
                    </thead>
                    <tbody>
"""
        
        for attempt in ai_data['attempts']:
            analysis_type = attempt.get('type', 'unknown')
            model = attempt.get('model', 'N/A')
            status = attempt.get('status', 'unknown')
            error = attempt.get('error', '')
            timestamp = attempt.get('timestamp', '')
            
            # Color code status
            if status == 'success':
                status_color = '#10b981'
                status_icon = '✓'
            elif status == 'rate_limit':
                status_color = '#f59e0b'
                status_icon = '⚠'
            elif status == 'model_not_found':
                status_color = '#ef4444'
                status_icon = '✗'
            elif status == 'auth_error':
                status_color = '#ef4444'
                status_icon = '✗'
            elif status == 'exhausted':
                status_color = '#6b7280'
                status_icon = '⊘'
            else:
                status_color = '#ef4444'
                status_icon = '✗'
            
            error_display = f'<span style="color: #666; font-size: 0.9em;">{error}</span>' if error else '<span style="color: #999;">—</span>'
            
            html += f"""
                        <tr style="border-bottom: 1px solid #ddd;">
                            <td style="padding: 8px; border-right: 1px solid #ccc;">{analysis_type}</td>
                            <td style="padding: 8px; border-right: 1px solid #ccc;"><code style="background-color: #f0f0f0; padding: 2px 4px; border-radius: 2px;">{model}</code></td>
                            <td style="padding: 8px; border-right: 1px solid #ccc;">
                                <span style="color: {status_color}; font-weight: bold;">{status_icon} {status.upper()}</span>
                            </td>
                            <td style="padding: 8px; border-right: 1px solid #ccc; font-size: 0.9em;">{error_display}</td>
                            <td style="padding: 8px; font-size: 0.85em; color: #999;">{timestamp.split('T')[1].split('.')[0] if timestamp else '—'}</td>
                        </tr>
"""
        
        html += """
                    </tbody>
                </table>
            </div>
"""
    
    # Add rate limit info if available
    rate_limit_info = ai_data.get('rate_limit_info', {})
    if rate_limit_info:
        html += """
            <div style="background-color: #fef3c7; padding: 15px; border-left: 4px solid #f59e0b; margin-bottom: 20px; border-radius: 4px;">
                <h3 style="margin-top: 0;">⏱️ Rate Limit Information</h3>
"""
        if rate_limit_info.get('retry_after'):
            html += f"<div><strong>Retry After:</strong> {rate_limit_info.get('retry_after')} seconds</div>"
        if rate_limit_info.get('rate_limit_remaining'):
            html += f"<div><strong>Rate Limit Remaining:</strong> {rate_limit_info.get('rate_limit_remaining')}</div>"
        if rate_limit_info.get('rate_limit_reset'):
            html += f"<div><strong>Rate Limit Reset Time:</strong> {rate_limit_info.get('rate_limit_reset')}</div>"
        
        html += """
            </div>
"""
    
    html += """
            <div style="background-color: #f0f9ff; padding: 15px; border-left: 4px solid #3b82f6; border-radius: 4px;">
                <h3 style="margin-top: 0;">📋 Interpretation Guide</h3>
                <ul style="margin: 10px 0; padding-left: 20px;">
                    <li><strong style="color: #10b981;">✓ SUCCESS</strong> - Analysis generated successfully</li>
                    <li><strong style="color: #f59e0b;">⚠ RATE_LIMIT</strong> - API rate limit hit (429), will retry next attempt</li>
                    <li><strong style="color: #ef4444;">✗ MODEL_NOT_FOUND</strong> - Model not available (404), trying next model</li>
                    <li><strong style="color: #ef4444;">✗ AUTH_ERROR</strong> - Authentication failed (401), check API key</li>
                    <li><strong style="color: #ef4444;">✗ OTHER_ERROR</strong> - HTTP error or other issue, check error details</li>
                    <li><strong style="color: #6b7280;">⊘ EXHAUSTED</strong> - All models tried without success</li>
                </ul>
            </div>
        </div>
        
        <div class="debug-section" style="margin-top: 30px;">
            <h2>🔍 Debug Logs - Raw Decision Making</h2>
            <p style="color: #666; margin-bottom: 20px;">View raw decision logs from each bot run showing market selection, signal analysis, and execution details.</p>
"""
    # Add debug runs
    if runs:
        for run_idx, run in enumerate(runs):
            run_time = run[0].get('timestamp', 'N/A')
            formatted_time = to_pacific_time(run_time)
            
            html += f"""
            <div class="debug-run">
                <h3>Run #{len(runs) - run_idx} - {formatted_time}</h3>
"""
            
            # Add decision logs for this run
            has_logs = False
            for trade in run:
                decision_log = trade.get('decision_log')
                if decision_log:
                    has_logs = True
                    asset = trade.get('asset', 'N/A')
                    market = trade.get('market', 'N/A')
                    html += f"""
                <div class="debug-entry">
                    <strong>{asset}</strong> - {market}<br>
                    <pre>{json.dumps(decision_log, indent=2, default=str)}</pre>
                </div>
"""
            
            if not has_logs:
                html += """
                <p style="color: #999; font-style: italic;">No decision logs available for this run.</p>
"""
            
            html += """
            </div>
"""
    else:
        html += """
            <p style="color: #999; font-style: italic; text-align: center; padding: 40px;">No debug logs available yet.</p>
"""
    
    html += """
        </div>
        
        <div class="debug-section" style="margin-top: 30px;">
            <h2>🔧 System Diagnostics</h2>
            <p style="color: #666; margin-bottom: 20px;">Comprehensive debug information for troubleshooting P&L, settlement, and enrichment issues.</p>
"""
    
    # Add diagnostic sections
    html += f"""
            <div class="diagnostic-section">
                <h3>📊 Data Pipeline Status</h3>
                <table>
                    <tr><th>Component</th><th>Status</th><th>Details</th></tr>
                    <tr>
                        <td><strong>Total Trades Logged</strong></td>
                        <td>{len(trades)}</td>
                        <td>All records in trades.jsonl (includes non-executed)</td>
                    </tr>
                    <tr>
                        <td><strong>Executed Trades</strong></td>
                        <td>{len(executed_trades)}</td>
                        <td>Trades with status='Success' or 'Failed'</td>
                    </tr>
                    <tr>
                        <td><strong>Settlement Source</strong></td>
                        <td><code>{settlement_source if 'settlement_source' in locals() else 'Unknown'}</code></td>
                        <td>Where settlement data came from</td>
                    </tr>
                    <tr>
                        <td><strong>Trades with Settlement Data</strong></td>
                        <td>{len([t for t in executed_trades if t.get('settlement')])}</td>
                        <td>Executed trades that have settlement data</td>
                    </tr>
                    <tr>
                        <td><strong>Settled Trades (Won/Lost)</strong></td>
                        <td>{len(settled_trades)}</td>
                        <td>Executed trades with Won or Lost status</td>
                    </tr>
                    <tr>
                        <td><strong>Pending Settlements</strong></td>
                        <td>{len([t for t in executed_trades if t.get('settlement', {}).get('status') == 'Pending'])}</td>
                        <td>Executed trades awaiting settlement</td>
                    </tr>
                    <tr>
                        <td><strong>Unknown Settlements</strong></td>
                        <td>{len([t for t in trades if t.get('settlement', {}).get('status') == 'Unknown'])}</td>
                        <td>Trades with no settlement info</td>
                    </tr>
                </table>
            </div>
            
            <div class="diagnostic-section">
                <h3>💰 Financial Metrics Breakdown</h3>
                <table>
                    <tr><th>Metric</th><th>Value</th><th>Calculation Source</th></tr>
                    <tr>
                        <td><strong>Total Spent</strong></td>
                        <td>${total_spent:.2f}</td>
                        <td>Sum of settlement.cost (actual fill prices) from executed trades</td>
                    </tr>
                    <tr>
                        <td><strong>Profit</strong></td>
                        <td>${total_gains:.2f}</td>
                        <td>Sum of settlement.pnl where status='Won'</td>
                    </tr>
                    <tr>
                        <td><strong>Loss</strong></td>
                        <td>${total_losses:.2f}</td>
                        <td>Sum of |settlement.pnl| where status='Lost'</td>
                    </tr>
                    <tr>
                        <td><strong>Open</strong></td>
                        <td>${open_pnl:.2f}</td>
                        <td>Sum of settlement.pnl where status='Pending' or 'Open'</td>
                    </tr>
                    <tr>
                        <td><strong>Net P&L</strong></td>
                        <td style="color: {'#10b981' if net_pnl > 0 else '#ef4444' if net_pnl < 0 else '#666'};">
                            ${net_pnl:+.2f}
                        </td>
                        <td>Profit - Loss + Open</td>
                    </tr>
                    <tr>
                        <td><strong>ROI</strong></td>
                        <td style="color: {roi_color};">{roi:+.1f}%</td>
                        <td>(Net P&L / Total Spent) * 100</td>
                    </tr>
                </table>
            </div>
            
            <div class="diagnostic-section">
                <h3>🔍 Settlement Details (Executed Trades Only)</h3>
                <table>
                    <tr><th>Market</th><th>Status</th><th>P&L</th><th>Details</th></tr>
"""
    
    # Show only executed trades with settlement info (exclude NO TRADE and other non-executed)
    executed_trades = [t for t in all_trades if t.get('status') == 'Success' or t.get('status') == 'Failed']
    for trade in executed_trades:
        settlement = trade.get('settlement', {})
        status = settlement.get('status', 'None')
        pnl = calculate_trade_pnl(trade)
        details = settlement.get('details', 'No details')
        market = trade.get('market', 'Unknown')[:30]
        
        status_color = '#10b981' if status == 'Won' else '#ef4444' if status == 'Lost' else '#f59e0b' if status == 'Pending' else '#666'
        
        html += f"""
                    <tr>
                        <td><code>{market}</code></td>
                        <td style="color: {status_color}; font-weight: bold;">{status}</td>
                        <td>${pnl:+.2f}</td>
                        <td style="font-size: 0.85em; color: #666;">{details}</td>
                    </tr>
"""
    
    html += f"""
                </table>
            </div>
            
            <div class="diagnostic-section">
                <h3>🤖 AI Analysis Status</h3>
                <table>
                    <tr><th>Component</th><th>Status</th><th>Details</th></tr>
                    <tr>
                        <td><strong>Gemini API Key</strong></td>
                        <td>{'✓ Found' if gemini_api_key else '✗ Not Found'}</td>
                        <td>Required for AI analysis</td>
                    </tr>
                    <tr>
                        <td><strong>Results Analysis</strong></td>
                        <td>{'✓ Generated' if results_analysis else '✗ Failed/Skipped'}</td>
                        <td>{results_analysis.get('model', 'N/A') if results_analysis else 'No previous results or API error'}</td>
                    </tr>
                    <tr>
                        <td><strong>Financial Analysis</strong></td>
                        <td>{'✓ Generated' if financial_analysis else '✗ Failed/Skipped'}</td>
                        <td>{financial_analysis.get('model', 'N/A') if financial_analysis else 'No trades or API error'}</td>
                    </tr>
                </table>
            </div>
            
            <div class="diagnostic-section">
                <h3>⚠️ Warnings & Alerts</h3>
                <div style="padding: 15px; background: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 5px; margin-bottom: 10px;">
"""
    
    # Add warnings
    warnings = []
    if len(settled_trades) > 0 and total_gains == 0 and total_losses == 0:
        warnings.append("⚠️ Settled trades found but P&L is zero - settlement calculation may be broken")
    if len(successful_trades) > 0 and total_spent == 0:
        warnings.append("⚠️ Successful trades found but total spent is zero - price/contracts data missing")
    if len([t for t in trades if t.get('settlement', {}).get('status') == 'Unknown']) > len(trades) * 0.5:
        warnings.append("⚠️ Over 50% of trades have Unknown settlement - API permissions or enrichment issue")
    
    # Only warn about API key if it's actually needed (we have previous results or successful trades to analyze)
    if not gemini_api_key and (previous_results or len(successful_trades) > 0):
        warnings.append("⚠️ Gemini API key not found - AI analysis skipped (set GEMINI_API_KEY env var to enable)")
    
    # Only warn about failed analysis if we had API key AND expected analysis AND it failed
    # results_analysis failure only matters if we have previous_results (otherwise it's expected to be None)
    analysis_attempted = gemini_api_key and (previous_results or len(successful_trades) > 0)
    analysis_failed = analysis_attempted and previous_results and not results_analysis
    financial_analysis_failed = analysis_attempted and len(successful_trades) > 0 and not financial_analysis
    
    if analysis_failed:
        warnings.append("⚠️ Results analysis failed for all models - check API quota and logs")
    if financial_analysis_failed:
        warnings.append("⚠️ Financial analysis failed for all models - check API quota and logs")
    
    if warnings:
        for warning in warnings:
            html += f"<p style='margin: 5px 0;'>{warning}</p>"
    else:
        html += "<p style='margin: 0; color: #10b981;'>✓ No warnings - system operating normally</p>"
    
    html += f"""
                </div>
            </div>
            
            <div class="diagnostic-section">
                <h3>📝 Recent Console Logs</h3>
                <div style="background: #1f2937; color: #e5e7eb; padding: 15px; border-radius: 5px; font-family: monospace; font-size: 0.85em; max-height: 400px; overflow-y: auto;">
                    <p style="margin: 0; color: #9ca3af;">// Console output from last run (check GitHub Actions for full logs)</p>
                    <p style="margin: 5px 0;">Settlement data source: {settlement_source if 'settlement_source' in locals() else 'Unknown'}</p>
                    <p style="margin: 5px 0;">Total trades: {len(trades)}</p>
                    <p style="margin: 5px 0;">Successful trades: {len(successful_trades)}</p>
                    <p style="margin: 5px 0;">Settled trades (Won/Lost): {len(settled_trades)}</p>
                    <p style="margin: 5px 0;">Total spent: ${total_spent:.2f}</p>
                    <p style="margin: 5px 0;">Profit: ${total_gains:.2f}</p>
                    <p style="margin: 5px 0;">Loss: ${total_losses:.2f}</p>
                    <p style="margin: 5px 0;">Open: ${open_pnl:.2f}</p>
                    <p style="margin: 5px 0;">Net P&L: ${net_pnl:.2f}</p>
                </div>
            </div>
        </div>
        </div>
    </div> <!-- end diagnostics-tab -->
    
"""
    
    html += f"""
    <div class="footer">
        <p>This report is automatically generated from trades.jsonl</p>
        <p>Kalshi Trading Bot - Multi-Signal AI Strategy</p>
        <p style="font-size: 0.8em; color: #999;">{{update_time}}</p>
    </div>
</body>
</html>
"""
    
    # Write HTML file
    # Use Pacific time for consistency with rest of bot
    pt_time = to_pacific_time(datetime.utcnow().replace(tzinfo=timezone.utc).isoformat())
    update_time = pt_time
    # Replace {update_time} placeholder (need to escape other braces in CSS)
    html = html.replace('{update_time}', update_time)
    
    # Replace header quick stats placeholders
    html = html.replace('{header_total_runs}', str(len(runs)))
    html = html.replace('{header_total_trades}', str(len(executed_trades)))
    
    # P&L with color class
    header_pnl_class = 'profit' if net_pnl > 0 else 'loss' if net_pnl < 0 else ''
    header_net_pnl = f"${net_pnl:+.2f}" if net_pnl != 0 else "$0.00"
    html = html.replace('{header_pnl_class}', header_pnl_class)
    html = html.replace('{header_net_pnl}', header_net_pnl)
    
    # Unsettled money (pending trades)
    header_unsettled = f"${spent_on_pending:.2f}" if spent_on_pending > 0 else "None"
    html = html.replace('{header_unsettled}', header_unsettled)
    
    # Last settled trade info
    settled_trades_sorted = sorted(
        [t for t in executed_trades if t.get('settlement', {}).get('status') in ['Won', 'Lost']],
        key=lambda t: t.get('timestamp', ''),
        reverse=True
    )
    if settled_trades_sorted:
        last_settled = settled_trades_sorted[0]
        ls_status = last_settled.get('settlement', {}).get('status', 'Unknown')
        ls_pnl = last_settled.get('settlement', {}).get('pnl', 0)
        ls_timestamp = last_settled.get('timestamp', '')
        # Convert trade timestamp to Pacific time for display
        try:
            pacific = ZoneInfo('America/Los_Angeles')
            if isinstance(ls_timestamp, str):
                if '+' in ls_timestamp or ls_timestamp.endswith('Z'):
                    dt_utc = datetime.fromisoformat(ls_timestamp.replace('Z', '+00:00'))
                else:
                    dt_utc = datetime.fromisoformat(ls_timestamp).replace(tzinfo=timezone.utc)
                dt_pacific = dt_utc.astimezone(pacific)
                time_str = dt_pacific.strftime('%-I:%M %p PT')
            else:
                time_str = 'Unknown'
        except:
            time_str = 'Unknown'
        ls_emoji = "✅" if ls_status == 'Won' else "❌"
        header_last_settled = f"{ls_emoji} {ls_status} ${ls_pnl:+.2f} ({time_str})"
    else:
        header_last_settled = "No settled trades yet"
    html = html.replace('{header_last_settled}', header_last_settled)
    
    # Model config summary for header - show last trade details
    # Count trades by type
    trades_won = len([t for t in executed_trades if t.get('settlement', {}).get('status') == 'Won'])
    trades_lost = len([t for t in executed_trades if t.get('settlement', {}).get('status') == 'Lost'])
    trades_open = len([t for t in executed_trades if t.get('settlement', {}).get('status') in ['Open', 'Pending']])
    win_rate = (trades_won / (trades_won + trades_lost) * 100) if (trades_won + trades_lost) > 0 else 0
    header_model_summary = f"{trades_won}W / {trades_lost}L ({win_rate:.0f}%) • {trades_open} open"
    html = html.replace('{header_model_summary}', header_model_summary)
    
    # Update settlement P&L values in trades before embedding them in HTML
    # This ensures the embedded JSON has accurate per-trade P&L calculations
    for trade in trades:
        settlement = trade.get('settlement', {})
        if settlement.get('status') in ['Won', 'Lost']:
            # Recalculate per-trade P&L and update settlement
            pnl = calculate_trade_pnl(trade)
            settlement['pnl'] = pnl
    
    # Save updated trades back to trades.jsonl with corrected P&L values
    try:
        with open('trades.jsonl', 'w', encoding='utf-8') as f:
            for trade in trades:
                f.write(json.dumps(trade, ensure_ascii=False) + '\n')
        print(f"✓ Saved corrected P&L values to trades.jsonl")
    except Exception as e:
        print(f"Warning: Could not save corrected trades: {e}")
    
    # Embed machine-readable JSON into the HTML for future runs
    try:
        os.makedirs('docs', exist_ok=True)
        # Insert trades JSON and debug JSON before closing </body>
        data_script = '<script id="trades-data" type="application/json">' + json.dumps(trades, default=str) + '</script>'

        # Build debug runs (raw decision logs grouped by run)
        debug_runs = []
        for run in runs:
            run_entries = []
            for t in run:
                if t.get('decision_log') is not None:
                    run_entries.append({
                        'timestamp': t.get('timestamp'),
                        'market': t.get('market'),
                        'asset': t.get('asset'),
                        'decision_log': t.get('decision_log')
                    })
            if run_entries:
                debug_runs.append({
                    'run_time': run[0].get('timestamp') if run else None,
                    'entries': run_entries
                })

        debug_script = '<script id="debug-data" type="application/json">' + json.dumps(debug_runs, default=str) + '</script>'

        if '</body>' in html:
            html = html.replace('</body>', data_script + '\n' + debug_script + '\n</body>')
        else:
            html += '\n' + data_script + '\n' + debug_script

        # Replace update time placeholder with Pacific time
        update_time = to_pacific_time(datetime.utcnow().replace(tzinfo=timezone.utc).isoformat())
        html = html.replace('{update_time}', update_time)

        tmp_path = 'docs/index.html.tmp'
        with open(tmp_path, 'w') as f:
            f.write(html)
        os.replace(tmp_path, 'docs/index.html')
        print(f"Generated HTML report with {len(trades)} trades (atomic write)")
        print("✓ HTML REPORT GENERATION COMPLETED SUCCESSFULLY")
        print("="*60 + "\n")
    except Exception as e:
        print(f"Error writing docs/index.html: {e}")
        print("✗ HTML REPORT GENERATION FAILED")
        print("="*60 + "\n")

if __name__ == "__main__":
    generate_html_report()

