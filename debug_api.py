#!/usr/bin/env python3
"""
Debug script to inspect actual Kalshi API responses
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from kalshi_auth import initialize_kalshi_client
import json

market_ticker = "kxbtcd-25dec3017"

print("Initializing Kalshi client...")
client = initialize_kalshi_client()

# Test 1: Get orderbook
print("\n[TEST 1] Fetching orderbook...")
try:
    orderbook = client.get_market_orderbook(ticker=market_ticker)
    print(f"Orderbook type: {type(orderbook)}")
    print(f"Orderbook: {orderbook}")
    if hasattr(orderbook, '__dict__'):
        print(f"Orderbook attrs: {orderbook.__dict__}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Get market
print("\n[TEST 2] Fetching market data...")
try:
    market = client.get_market(ticker=market_ticker)
    print(f"Market type: {type(market)}")
    print(f"Market: {market}")
    if hasattr(market, '__dict__'):
        print(f"Market attrs: {market.__dict__}")
except Exception as e:
    print(f"Error: {e}")

# Test 3: Try candlesticks with different params
print("\n[TEST 3] Fetching candlesticks (60-min only)...")
import time
from datetime import datetime, timedelta, timezone

end_time = datetime.now(timezone.utc)
start_time = end_time - timedelta(hours=1)

try:
    # Try with seconds
    candlesticks = client.get_market_candlesticks(
        series_ticker="kxbtcd",
        ticker=market_ticker,
        period_interval=60,  # 60-minute candles instead of 1-min
        start_ts=int(start_time.timestamp()),  # seconds
        end_ts=int(end_time.timestamp())  # seconds
    )
    print(f"Candlesticks type: {type(candlesticks)}")
    print(f"Candlesticks: {candlesticks}")
    if hasattr(candlesticks, '__dict__'):
        print(f"Candlesticks attrs: {candlesticks.__dict__}")
except Exception as e:
    print(f"Error: {e}")

# Test 4: Get trades
print("\n[TEST 4] Fetching trades...")
try:
    trades = client.get_trades(
        ticker=market_ticker,
        min_ts=int((end_time - timedelta(minutes=15)).timestamp()),  # seconds
        max_ts=int(end_time.timestamp()),  # seconds
        limit=50
    )
    print(f"Trades type: {type(trades)}")
    print(f"Trades: {trades}")
    if hasattr(trades, '__dict__'):
        print(f"Trades attrs: {trades.__dict__}")
except Exception as e:
    print(f"Error: {e}")
