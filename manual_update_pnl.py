#!/usr/bin/env python3
"""
Manually update P/L for trades based on known outcomes.
Use this when Kalshi API is not available.
"""

import json
import os
from datetime import datetime


def manual_update_trades():
    """
    Manually update trade P/L based on known market outcomes.
    """
    print("="*80)
    print("MANUAL TRADE SETTLEMENT UPDATE")
    print("="*80)
    
    # Load current trades
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
    
    print(f"\n✓ Loaded {len(trades)} trades\n")
    
    # Display trades and get user input for each
    updated_trades = []
    total_pnl = 0.0
    
    for i, trade in enumerate(trades, 1):
        market = trade.get('market', '')
        action = trade.get('action', '')
        price = trade.get('price', 0)
        contracts = trade.get('contracts', 0)
        cost = (price * contracts) / 100.0
        
        print(f"[Trade {i}] {market}")
        print(f"  Action: {action}")
        print(f"  Cost: ${cost:.2f} ({price}¢ × {contracts} contracts)")
        
        # Get outcome from user
        print(f"  Did this trade WIN? (y/n/p for pending): ", end='')
        outcome = input().strip().lower()
        
        if outcome == 'y':
            # Won: Get $1 per contract, minus cost
            payout = contracts * 1.0
            pnl = payout - cost
            status = 'won'
            print(f"  ✓ WON: ${pnl:+.2f}")
        elif outcome == 'n':
            # Lost: Lose cost
            pnl = -cost
            status = 'lost'
            print(f"  ✗ LOST: ${pnl:+.2f}")
        else:
            # Pending
            pnl = 0.0
            status = 'pending'
            print(f"  ⏳ PENDING: $0.00")
        
        # Update trade
        trade['settlement'] = {
            'pnl': pnl,
            'status': status,
            'updated_at': datetime.now().isoformat(),
            'manual_entry': True
        }
        
        total_pnl += pnl
        updated_trades.append(trade)
        print()
    
    # Save updated trades
    with open('trades.jsonl', 'w') as f:
        for trade in updated_trades:
            f.write(json.dumps(trade) + '\n')
    
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total trades: {len(updated_trades)}")
    print(f"Total P/L: ${total_pnl:+.2f}")
    print(f"\n✓ Updated trades.jsonl")
    
    # Also update trades.log
    with open('trades.log', 'w') as f:
        f.write("timestamp, market, action, status, asset, sentiment, price, contracts\n")
        for trade in updated_trades:
            ts = trade.get('timestamp', '')
            market = trade.get('market', '')
            action = trade.get('action', '')
            status = trade.get('status', '')
            asset = trade.get('asset', '')
            sentiment = trade.get('sentiment', '')
            price = trade.get('price', '')
            contracts = trade.get('contracts', '')
            f.write(f"{ts}, {market}, {action}, {status}, {asset}, {sentiment}, {price}, {contracts}\n")
    
    print("✓ Updated trades.log")
    print("\nNow regenerate the report:")
    print("  python3 generate_report.py")


if __name__ == '__main__':
    manual_update_trades()
