#!/usr/bin/env python3
"""
Reconcile unsettled trades in trades.jsonl by querying Kalshi API for market resolutions.
Uses the settlements API directly for accurate Win/Loss data.
Updates trades.jsonl in-place with Won/Lost status and P&L calculations.
"""

import json
import os
import sys
from datetime import datetime, timezone

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kalshi_auth import initialize_kalshi_client


def get_settlements_by_ticker():
    """
    Fetch all settlements from Kalshi API and index by market ticker.
    Returns dict: {ticker: settlement_data}
    """
    try:
        client = initialize_kalshi_client()
        settlements_resp = client.get_settlements()
        settlements = settlements_resp.settlements if hasattr(settlements_resp, 'settlements') else []
        
        settlements_by_ticker = {}
        for s in settlements:
            ticker = getattr(s, 'ticker', None)
            if ticker:
                settlements_by_ticker[ticker] = {
                    'market_result': getattr(s, 'market_result', None),  # 'yes' or 'no'
                    'yes_count': getattr(s, 'yes_count', 0),
                    'no_count': getattr(s, 'no_count', 0),
                    'yes_total_cost': getattr(s, 'yes_total_cost', 0),  # cents
                    'no_total_cost': getattr(s, 'no_total_cost', 0),    # cents
                    'revenue': getattr(s, 'revenue', 0),                # cents
                    'fee_cost': float(getattr(s, 'fee_cost', 0) or 0),  # dollars
                    'settled_time': getattr(s, 'settled_time', None),
                }
        print(f"✓ Fetched {len(settlements_by_ticker)} settlements from Kalshi API")
        return settlements_by_ticker
    except Exception as e:
        print(f"❌ Failed to fetch settlements: {e}")
        return {}


def load_trades(filepath='trades.jsonl'):
    """Load all trades from JSONL file."""
    trades = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    trades.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Warning: Skipping invalid JSON line: {e}")
    return trades


def save_trades(trades, filepath='trades.jsonl'):
    """Save trades back to JSONL file."""
    with open(filepath, 'w') as f:
        for trade in trades:
            f.write(json.dumps(trade) + '\n')


def reconcile_trades(dry_run=False, cleanup_non_trades=False):
    """
    Reconcile all unsettled trades by querying Kalshi API for market resolutions.
    
    Args:
        dry_run: If True, show what would be changed without modifying the file
        cleanup_non_trades: If True, remove entries without order_ids (SKIPs, errors)
    
    Returns:
        dict: Summary of reconciliation results
    """
    print("=" * 70)
    print("TRADE RECONCILIATION")
    print("=" * 70)
    
    # Load trades
    trades = load_trades()
    original_count = len(trades)
    print(f"Loaded {len(trades)} entries from trades.jsonl")
    
    # Count categories
    finalized = sum(1 for t in trades if t.get('settlement', {}).get('status') in ['Won', 'Lost'])
    with_order_id = sum(1 for t in trades if t.get('order_id'))
    pending_with_order = sum(1 for t in trades if t.get('order_id') and t.get('settlement', {}).get('status') not in ['Won', 'Lost'])
    non_trades = sum(1 for t in trades if not t.get('order_id'))
    
    print(f"  ✓ {finalized} finalized (Won/Lost)")
    print(f"  ⏳ {pending_with_order} with order_id pending settlement")
    print(f"  📋 {non_trades} without order_id (SKIPs/errors/NO TRADE)")
    
    # Optionally clean up non-trades
    if cleanup_non_trades:
        trades_before = len(trades)
        trades = [t for t in trades if t.get('order_id')]
        removed = trades_before - len(trades)
        if removed > 0:
            if dry_run:
                print(f"\n🔍 Would remove {removed} non-trade entries")
            else:
                print(f"\n🧹 Removed {removed} non-trade entries")
    
    # Find trades that need reconciliation
    unsettled = []
    for i, trade in enumerate(trades):
        settlement = trade.get('settlement', {})
        status = settlement.get('status', 'Unknown')
        
        # Skip already finalized trades
        if status in ['Won', 'Lost']:
            continue
            
        # Skip trades without order_id (not executed)
        order_id = trade.get('order_id')
        if not order_id:
            continue
            
        # Skip placeholder/error markets
        market = trade.get('market', '')
        if not market or 'NOT-FOUND' in market:
            continue
            
        unsettled.append((i, trade))
    
    print(f"\nFound {len(unsettled)} unsettled trades to reconcile")
    
    if not unsettled:
        print("✅ All executed trades are already reconciled!")
        return {'reconciled': 0, 'still_open': 0, 'errors': 0}
    
    # Fetch settlements from Kalshi API
    settlements = get_settlements_by_ticker()
    if not settlements:
        print("❌ Could not fetch settlements from API")
        return {'reconciled': 0, 'still_open': len(unsettled), 'errors': 1}
    
    # Match unsettled trades against settlements
    stats = {'reconciled': 0, 'still_open': 0, 'errors': 0, 'won': 0, 'lost': 0, 'total_pnl': 0.0}
    
    for idx, trade in unsettled:
        market = trade.get('market')
        action = trade.get('action', '').upper()
        price = trade.get('price')
        contracts = trade.get('contracts', 1)
        
        if price is None:
            print(f"⚠️  {market}: Missing price data, skipping")
            stats['errors'] += 1
            continue
        
        settlement = settlements.get(market)
        
        if not settlement:
            # Market not in settlements - still open
            print(f"⏳ {market}: Still open (no settlement found)")
            stats['still_open'] += 1
            continue
        
        market_result = settlement['market_result']  # 'yes' or 'no'
        cost_paid = (price / 100.0) * contracts
        
        # Determine win/loss based on our position vs market result
        result = None
        if 'YES' in action:
            result = 'Won' if market_result == 'yes' else 'Lost'
        elif 'NO' in action:
            result = 'Won' if market_result == 'no' else 'Lost'
        
        if result is None:
            print(f"⚠️  {market}: Could not determine result (action={action})")
            stats['errors'] += 1
            continue
        
        # Calculate P&L
        if result == 'Won':
            payout = 1.00 * contracts
            pnl = payout - cost_paid
            stats['won'] += 1
        else:
            pnl = -cost_paid
            stats['lost'] += 1
        
        stats['total_pnl'] += pnl
        stats['reconciled'] += 1
        
        # Update the trade
        new_settlement = {
            'status': result,
            'outcome': market_result,
            'cost': cost_paid,
            'pnl': pnl,
            'details': f"Market resolved {market_result}",
            'reconciled_at': datetime.now(timezone.utc).isoformat()
        }
        
        if dry_run:
            print(f"🔍 {market}: Would update to {result} (PnL: ${pnl:+.2f})")
        else:
            trades[idx]['settlement'] = new_settlement
            print(f"✅ {market}: {result} (PnL: ${pnl:+.2f})")
    
    print()
    print("=" * 70)
    print("RECONCILIATION SUMMARY")
    print("=" * 70)
    print(f"  Reconciled: {stats['reconciled']} trades ({stats['won']} won, {stats['lost']} lost)")
    print(f"  Still open: {stats['still_open']} trades")
    print(f"  Errors:     {stats['errors']} trades")
    print(f"  Net P&L:    ${stats['total_pnl']:+.2f}")
    print()
    
    if not dry_run and stats['reconciled'] > 0:
        save_trades(trades)
        print(f"✅ Saved updated trades to trades.jsonl")
    elif dry_run and stats['reconciled'] > 0:
        print("🔍 DRY RUN - no changes made. Run without --dry-run to apply.")
    
    return stats


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Reconcile unsettled trades')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without modifying files')
    parser.add_argument('--cleanup', action='store_true', help='Remove non-trade entries (SKIPs, errors) from trades.jsonl')
    args = parser.parse_args()
    
    reconcile_trades(dry_run=args.dry_run, cleanup_non_trades=args.cleanup)
