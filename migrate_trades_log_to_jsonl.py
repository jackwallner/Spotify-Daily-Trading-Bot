#!/usr/bin/env python3
"""Migrate legacy trades.log (CSV-like) to trades.jsonl

Usage:
    python migrate_trades_log_to_jsonl.py

This will read trades.log and append converted JSON objects to trades.jsonl.
It will not delete trades.log.
"""

import os
import json


def migrate(log_path='trades.log', out_path='trades.jsonl'):
    if not os.path.exists(log_path):
        print(f"No {log_path} found; nothing to migrate.")
        return

    count = 0
    with open(log_path, 'r') as f, open(out_path, 'a') as out:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 4:
                continue
            try:
                asset = parts[4] if len(parts) >= 5 else 'UNKNOWN'
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

                trade_obj = {
                    'timestamp': parts[0],
                    'market': parts[1],
                    'action': parts[2],
                    'status': parts[3],
                    'asset': asset,
                    'sentiment': sentiment,
                    'price': price,
                    'contracts': contracts,
                    'decision_log': None
                }
                out.write(json.dumps(trade_obj, default=str) + '\n')
                count += 1
            except Exception as e:
                print(f"Skipping line due to error: {e}")

    print(f"Migrated {count} trades from {log_path} to {out_path}")


if __name__ == '__main__':
    migrate()
