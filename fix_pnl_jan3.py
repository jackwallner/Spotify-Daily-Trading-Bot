#!/usr/bin/env python3
"""
Fix P/L for Jan 3 trades.
Both predicted "End of Beginning" which was #1, so both should have won.
"""

import json
from datetime import datetime

# Load trades
trades = []
with open('trades.jsonl', 'r') as f:
    for line in f:
        line = line.strip()
        if line:
            trades.append(json.loads(line))

print(f"Found {len(trades)} trades")

# Update both trades (both predicted End of Beginning, which won)
for trade in trades:
    market = trade.get('market', '')
    price = trade.get('price', 0)
    contracts = trade.get('contracts', 0)
    
    # Both bought YES at 99¢
    cost = (price * contracts) / 100.0  # $0.99
    
    # Both won (End of Beginning was #1)
    payout = contracts * 1.0  # $1.00
    pnl = payout - cost  # $1.00 - $0.99 = $0.01
    
    trade['settlement'] = {
        'pnl': pnl,
        'status': 'won',
        'market_result': 'yes',
        'updated_at': datetime.now().isoformat(),
        'note': 'End of Beginning was #1 on Jan 3'
    }
    
    print(f"{market}: ${pnl:+.2f} (won)")

# Save
with open('trades.jsonl', 'w') as f:
    for trade in trades:
        f.write(json.dumps(trade) + '\n')

total_pnl = sum(t.get('settlement', {}).get('pnl', 0) for t in trades)
print(f"\nTotal P/L: ${total_pnl:+.2f}")
print("✓ Updated trades.jsonl")
