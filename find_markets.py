#!/usr/bin/env python3
"""
Find Spotify daily markets to test with
"""

import sys
from pathlib import Path

# Ensure repo root is importable when run as a script
sys.path.insert(0, str(Path(__file__).parent))

from kalshi_auth import initialize_kalshi_client
from spotify_daily_markets import SpotifyDailyMarketConfig, discover_spotify_daily_markets

client = initialize_kalshi_client()

print("Fetching Spotify daily markets...")
try:
    cfg = SpotifyDailyMarketConfig.from_env()
    markets = discover_spotify_daily_markets(client, cfg, status="open")
    print(f"Found {len(markets)} Spotify daily market(s)")
    for i, m in enumerate(markets[:10]):
        ticker = m.ticker if hasattr(m, 'ticker') else str(m)
        status = m.status if hasattr(m, 'status') else 'unknown'
        title = getattr(m, "title", "")
        print(f"  {i+1}. {ticker} (status: {status})")
        if title:
            print(f"      {title}")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
