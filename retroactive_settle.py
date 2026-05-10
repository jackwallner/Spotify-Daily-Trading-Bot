#!/usr/bin/env python3
"""
Retroactively add theoretical $1/day settlement data to trades.jsonl.
Determines if each prediction was correct based on next-day Kworb data,
and calculates what the P&L would have been at $1/day.
"""

import json
import os
from datetime import datetime


def load_trades(path='trades.jsonl'):
    entries = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def get_prediction_key(entry):
    """Get a unique key for the prediction: (date, region)."""
    dl = entry.get('decision_log', {})
    if not isinstance(dl, dict):
        return None
    predicted = dl.get('predicted', {})
    artist = predicted.get('artist', '')
    title = predicted.get('title', '')
    region = dl.get('region', '')
    ts = entry.get('timestamp', '')[:10]
    return (ts, region, f"{artist} - {title}")


def determine_correctness(entries):
    """
    Determine if each prediction was correct by comparing with
    the NEXT day's scraped data for the same region.
    
    Key insight: each entry's decision_log.top1 is what the bot saw
    at prediction time. If the NEXT day's entry for the same region
    still has the same song at #1, the prediction was correct
    (because the prediction was "this song will still be #1 tomorrow").
    
    But we can also detect when #1 changed: if the next day's top1
    is different from today's predicted song.
    """
    results = {}
    
    for i, entry in enumerate(entries):
        dl = entry.get('decision_log', {})
        if not isinstance(dl, dict):
            results[i] = {'correct': None, 'reason': 'no decision_log'}
            continue
        
        predicted = dl.get('predicted', {})
        pred_artist = predicted.get('artist', '')
        pred_title = predicted.get('title', '')
        region = dl.get('region', '')
        
        if not pred_title:
            results[i] = {'correct': None, 'reason': 'no prediction'}
            continue
        
        # Find the next entry for the same region
        next_entry = None
        for j in range(i + 1, len(entries)):
            ndl = entries[j].get('decision_log', {})
            if isinstance(ndl, dict) and ndl.get('region') == region:
                next_entry = entries[j]
                break
        
        if not next_entry:
            # Last entry for this region - can't determine
            results[i] = {'correct': None, 'reason': 'last entry for region'}
            continue
        
        # Check if the predicted song is still #1 on the next scrape
        ndl = next_entry.get('decision_log', {})
        next_top1 = ndl.get('top1', {}) if isinstance(ndl, dict) else {}
        next_artist = next_top1.get('artist', '')
        next_title = next_top1.get('title', '')
        
        # Normalize for comparison
        pred_key = f"{pred_artist.lower().strip()}||{pred_title.lower().strip()}"
        next_key = f"{next_artist.lower().strip()}||{next_title.lower().strip()}"
        
        if pred_key == next_key:
            results[i] = {'correct': True, 'reason': f'{pred_title} stayed #1'}
        else:
            results[i] = {'correct': False, 'reason': f'{pred_title} was overtaken by {next_title}'}
    
    return results


def calculate_theoretical_pnl(correct, price_cents=99):
    """Calculate theoretical P&L for a $1/day bet."""
    if correct is None:
        return 0.0, "unknown"
    
    cost = price_cents / 100.0  # $0.99
    if correct:
        pnl = 1.00 - cost  # $0.01 profit
        status = "theoretical_win"
    else:
        pnl = -cost  # -$0.99 loss
        status = "theoretical_loss"
    
    return round(pnl, 2), status


def main():
    entries = load_trades()
    print(f"Loaded {len(entries)} entries")
    
    correctness = determine_correctness(entries)
    
    # Print summary
    correct_count = sum(1 for v in correctness.values() if v['correct'] is True)
    incorrect_count = sum(1 for v in correctness.values() if v['correct'] is False)
    unknown_count = sum(1 for v in correctness.values() if v['correct'] is None)
    
    print(f"\nCorrect: {correct_count}")
    print(f"Incorrect: {incorrect_count}")
    print(f"Unknown: {unknown_count}")
    
    total_pnl = 0.0
    wins = 0
    losses = 0
    
    for i, entry in enumerate(entries):
        result = correctness.get(i, {'correct': None, 'reason': 'unknown'})
        correct = result['correct']
        reason = result['reason']
        
        pnl, status = calculate_theoretical_pnl(correct)
        total_pnl += pnl
        
        if correct is True:
            wins += 1
        elif correct is False:
            losses += 1
        
        # Add or update settlement
        existing_settlement = entry.get('settlement', {})
        
        if isinstance(existing_settlement, dict) and existing_settlement.get('pnl') is not None and 'theoretical' not in existing_settlement.get('note', ''):
            # Has actual settlement data, add theoretical as a separate note
            entry['theoretical_settlement'] = {
                'pnl': pnl,
                'status': status,
                'note': f'${1.00:.2f} bet at {99}¢. {reason}',
                'correct': correct
            }
        else:
            # No actual settlement, add theoretical
            entry['settlement'] = {
                'pnl': pnl,
                'status': status,
                'note': f'THEORETICAL: ${1.00:.2f} bet at {99}¢. {reason}',
                'correct': correct
            }
    
    print(f"\nWins: {wins}, Losses: {losses}")
    print(f"Total theoretical P&L: ${total_pnl:.2f}")
    print(f"Net result: {'PROFITABLE' if total_pnl > 0 else 'UNSUCCESSFUL'}")
    
    # Write back
    with open('trades.jsonl', 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry) + '\n')
    
    print(f"\nUpdated trades.jsonl with theoretical settlements")
    print(f"Run: python3 generate_report.py to refresh the dashboard")


if __name__ == '__main__':
    main()
