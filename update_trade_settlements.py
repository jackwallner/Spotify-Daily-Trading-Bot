#!/usr/bin/env python3
"""
Update trade settlements with actual P/L from Kalshi market outcomes.
"""

import json
import os
from datetime import datetime
from kalshi_auth import initialize_kalshi_client


def get_market_outcome(kalshi_client, market_ticker):
    """Get the outcome of a resolved market."""
    try:
        market = kalshi_client.get_market(market_ticker)
        
        if not market:
            print(f"  Market not found: {market_ticker}")
            return None
        
        status = getattr(market, 'status', None)
        result = getattr(market, 'result', None)
        
        print(f"  Status: {status}")
        print(f"  Result: {result}")
        
        return {
            'status': status,
            'result': result,
            'resolved': status in ['closed', 'finalized', 'settled']
        }
        
    except Exception as e:
        print(f"  Error: {e}")
        return None


def calculate_pnl(trade, outcome):
    """
    Calculate P/L for a trade given the outcome.
    
    Args:
        trade: Trade dict with price, contracts, action
        outcome: Market outcome dict with result
    
    Returns:
        P/L in dollars (positive = profit, negative = loss)
    """
    price = trade.get('price', 0)  # Price in cents
    contracts = trade.get('contracts', 0)
    action = trade.get('action', '')
    
    # Cost = (price * contracts) / 100
    cost = (price * contracts) / 100.0
    
    # Determine if we bought YES or NO
    bought_yes = 'YES' in action
    
    # Get result
    result = outcome.get('result', '') if outcome else ''
    
    # If not resolved, P/L is unknown (return -cost as placeholder)
    if not outcome or not outcome.get('resolved'):
        return -cost, 'pending'
    
    # Check if we won
    won = False
    if bought_yes and result == 'yes':
        won = True
    elif not bought_yes and result == 'no':
        won = True
    
    # Calculate P/L
    if won:
        # Win: Get $1 per contract, minus what we paid
        payout = contracts * 1.0  # $1 per contract
        pnl = payout - cost
        status = 'won'
    else:
        # Loss: Lose what we paid
        pnl = -cost
        status = 'lost'
    
    return pnl, status


def update_settlements():
    """Update all trades with settlement data from Kalshi."""
    print("="*80)
    print("UPDATING TRADE SETTLEMENTS")
    print("="*80)
    
    # Load trades
    if not os.path.exists('trades.jsonl'):
        print("\n✗ No trades.jsonl file found")
        return
    
    trades = []
    with open('trades.jsonl', 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    trades.append(json.loads(line))
                except:
                    continue
    
    print(f"\n✓ Loaded {len(trades)} trades")
    
    # Initialize Kalshi client
    try:
        kalshi_client = initialize_kalshi_client()
        print("✓ Connected to Kalshi API")
    except Exception as e:
        print(f"✗ Cannot connect to Kalshi: {e}")
        print("\nCannot update settlements without Kalshi API access")
        return
    
    # Update each trade
    updated_trades = []
    total_pnl = 0.0
    
    for i, trade in enumerate(trades, 1):
        market = trade.get('market', '')
        price = trade.get('price', 0)
        contracts = trade.get('contracts', 0)
        
        print(f"\n[{i}/{len(trades)}] {market}")
        print(f"  Bought: {price}¢ × {contracts} contracts = ${(price * contracts) / 100:.2f}")
        
        # Get market outcome
        outcome = get_market_outcome(kalshi_client, market)
        
        # Calculate P/L
        pnl, settlement_status = calculate_pnl(trade, outcome)
        
        # Update trade with settlement
        trade['settlement'] = {
            'pnl': pnl,
            'status': settlement_status,
            'market_status': outcome.get('status') if outcome else 'unknown',
            'market_result': outcome.get('result') if outcome else 'unknown',
            'updated_at': datetime.now().isoformat()
        }
        
        total_pnl += pnl
        
        # Show result
        pnl_color = '✓' if pnl > 0 else '✗'
        print(f"  {pnl_color} P/L: ${pnl:+.2f} ({settlement_status})")
        
        updated_trades.append(trade)
    
    # Save updated trades
    with open('trades.jsonl', 'w') as f:
        for trade in updated_trades:
            f.write(json.dumps(trade) + '\n')
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total trades: {len(updated_trades)}")
    print(f"Total P/L: ${total_pnl:+.2f}")
    print(f"\n✓ Updated trades.jsonl with settlement data")
    
    return updated_trades, total_pnl


if __name__ == '__main__':
    updated_trades, total_pnl = update_settlements()
    
    print("\n" + "="*80)
    print("NEXT STEP")
    print("="*80)
    print("Regenerate report:")
    print("  python3 generate_report.py")
