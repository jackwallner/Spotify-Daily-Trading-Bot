#!/usr/bin/env python3
"""
Test script to find the correct market ticker syntax for Kalshi API
Run this locally to debug market search without waiting for GitHub Actions
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from kalshi_python_sync import Configuration, KalshiClient

load_dotenv()

KALSHI_API_KEY_ID = os.getenv('KALSHI_API_KEY_ID')
KALSHI_PRIVATE_KEY = os.getenv('KALSHI_PRIVATE_KEY')

if not KALSHI_API_KEY_ID or not KALSHI_PRIVATE_KEY:
    print("Error: KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY must be set")
    sys.exit(1)

def initialize_kalshi_client():
    """Initialize Kalshi client"""
    try:
        os.environ['KALSHI_API_KEY_ID'] = KALSHI_API_KEY_ID
        os.environ['KALSHI_PRIVATE_KEY'] = KALSHI_PRIVATE_KEY
        
        config = Configuration()
        config.api_key_id = KALSHI_API_KEY_ID
        config.private_key = KALSHI_PRIVATE_KEY
        
        client = KalshiClient(config)
        return client
    except Exception as e:
        print(f"Error initializing client: {e}")
        return None

def test_market_search():
    """Test different market search approaches"""
    client = initialize_kalshi_client()
    if not client:
        return
    
    # Calculate next hour in EST
    now = datetime.now(timezone.utc)
    est_now = now - timedelta(hours=5)
    next_hour_est = (est_now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    
    # Format: YYMMMDDHH
    year_short = f"{next_hour_est.year % 100:02d}"
    month_abbr = next_hour_est.strftime('%b').upper()
    day = f"{next_hour_est.day:02d}"
    hour = f"{next_hour_est.hour:02d}"
    
    ticker_base_btc = f"KXBTCD-{year_short}{month_abbr}{day}{hour}"
    ticker_base_eth = f"KXETHD-{year_short}{month_abbr}{day}{hour}"
    
    print("=" * 80)
    print("MARKET SEARCH TEST")
    print("=" * 80)
    print(f"Current time (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Next hour (EST): {next_hour_est.strftime('%Y-%m-%d %H:00')}")
    print(f"Looking for BTC ticker: {ticker_base_btc}")
    print(f"Looking for ETH ticker: {ticker_base_eth}")
    print()
    
    # Test 1: Search by event_ticker with status='open' (NO LIMIT - get all markets)
    print("TEST 1: event_ticker search with status='open' (NO LIMIT)")
    print("-" * 80)
    try:
        response = client.get_markets(event_ticker="KXBTCD", status="open")
        print(f"  Response received: {response is not None}")
        if response:
            print(f"  Response type: {type(response)}")
            print(f"  Has 'markets' attr: {hasattr(response, 'markets')}")
            if hasattr(response, 'markets'):
                print(f"  Markets value: {response.markets}")
                print(f"  Markets count: {len(response.markets) if response.markets else 0}")
        if response and hasattr(response, 'markets') and response.markets:
            print(f"✓ Found {len(response.markets)} markets with event_ticker='KXBTCD', status='open'")
            
            # Filter for our ticker pattern
            matching = []
            for m in response.markets:
                ticker = m.ticker.upper() if hasattr(m, 'ticker') else ''
                if ticker_base_btc.upper() in ticker and '-T' in ticker:
                    matching.append(m)
            
            print(f"  Markets matching '{ticker_base_btc}*' pattern: {len(matching)}")
            if matching:
                print("  Matching tickers:")
                for m in matching[:5]:
                    strike = m.ticker.split('-T')[-1] if '-T' in m.ticker else 'N/A'
                    print(f"    - {m.ticker} | Strike: {strike}")
            else:
                print("  No exact matches. Showing first 10 tickers found:")
                for i, m in enumerate(response.markets[:10]):
                    ticker = m.ticker if hasattr(m, 'ticker') else 'N/A'
                    status = m.status if hasattr(m, 'status') else 'N/A'
                    print(f"    {i+1}. {ticker} (status: {status})")
        else:
            print(f"✗ No markets found")
    except Exception as e:
        print(f"✗ Error: {e}")
    print()
    
    # Test 2: Search by event_ticker without status filter (NO LIMIT)
    print("TEST 2: event_ticker search (no status filter, NO LIMIT)")
    print("-" * 80)
    try:
        response = client.get_markets(event_ticker="KXBTCD")
        print(f"  Response received: {response is not None}")
        if response and hasattr(response, 'markets'):
            print(f"  Markets count: {len(response.markets) if response.markets else 0}")
            if response.markets:
                print(f"  First market status: {response.markets[0].status if hasattr(response.markets[0], 'status') else 'N/A'}")
        if response and hasattr(response, 'markets') and response.markets:
            print(f"✓ Found {len(response.markets)} total KXBTCD markets")
            
            # Filter for our ticker pattern
            matching = []
            for m in response.markets:
                ticker = m.ticker.upper() if hasattr(m, 'ticker') else ''
                if ticker.startswith(ticker_base_btc.upper()) and '-T' in ticker:
                    matching.append(m)
            
            print(f"  Markets matching '{ticker_base_btc}*-T*': {len(matching)}")
            if matching:
                print("  Matching tickers:")
                for m in matching[:5]:
                    print(f"    - {m.ticker}")
            else:
                print("  No exact matches. Showing first 10 tickers found:")
                for i, m in enumerate(response.markets[:10]):
                    ticker = m.ticker if hasattr(m, 'ticker') else 'N/A'
                    status = m.status if hasattr(m, 'status') else 'N/A'
                    print(f"    {i+1}. {ticker} (status: {status})")
        else:
            print(f"✗ No markets found")
    except Exception as e:
        print(f"✗ Error: {e}")
    print()
    
    # Test 3: Filter markets by close_time (next 60 minutes) - NO LIMIT
    print("TEST 3: Filtering by close_time (next 60 minutes) - NO LIMIT")
    print("-" * 80)
    try:
        now = datetime.now(timezone.utc)
        current_timestamp = int(now.timestamp())
        target_window_start = current_timestamp
        target_window_end = current_timestamp + 3600  # 60 minutes
        
        print(f"  Current time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  Looking for markets closing between {target_window_start} and {target_window_end}")
        
        response = client.get_markets(event_ticker="KXBTCD", status="open")
        if response and hasattr(response, 'markets') and response.markets:
            print(f"  Total markets returned: {len(response.markets)}")
            
            # Filter by close_time (next 60 minutes)
            matching = []
            for m in response.markets:
                try:
                    close_time = getattr(m, 'close_time', None)
                    if close_time is None:
                        continue
                    
                    # Convert to int
                    if isinstance(close_time, str):
                        try:
                            close_time = int(close_time)
                        except ValueError:
                            continue
                    elif hasattr(close_time, 'timestamp'):
                        close_time = int(close_time.timestamp())
                    elif not isinstance(close_time, (int, float)):
                        continue
                    
                    close_time = int(close_time)
                    
                    # Check if closes in next 60 minutes
                    if target_window_start <= close_time <= target_window_end:
                        ticker = getattr(m, 'ticker', '')
                        if '-T' in ticker:
                            matching.append(m)
                except Exception:
                    continue
            
            print(f"  Markets closing in next 60 minutes: {len(matching)}")
            if matching:
                print("  Matching markets with strike prices and close times:")
                for m in matching[:10]:
                    ticker = m.ticker if hasattr(m, 'ticker') else 'N/A'
                    close_time = getattr(m, 'close_time', None)
                    if '-T' in ticker:
                        strike = ticker.split('-T')[-1]
                        close_str = ""
                        if close_time:
                            if isinstance(close_time, (int, float)):
                                close_dt = datetime.fromtimestamp(int(close_time), tz=timezone.utc)
                                close_str = f" | Closes: {close_dt.strftime('%H:%M:%S UTC')}"
                        print(f"    - {ticker} | Strike: {strike}{close_str}")
            else:
                print("  No matches in next 60 minutes. Showing sample close_times:")
                sample_count = 0
                for m in response.markets[:10]:
                    try:
                        close_time = getattr(m, 'close_time', None)
                        ticker = m.ticker if hasattr(m, 'ticker') else 'N/A'
                        if close_time:
                            if isinstance(close_time, (int, float)):
                                close_dt = datetime.fromtimestamp(int(close_time), tz=timezone.utc)
                                print(f"    - {ticker}: closes at {close_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                                sample_count += 1
                                if sample_count >= 5:
                                    break
                    except:
                        continue
        else:
            print(f"  ✗ No markets found")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    print()
    
    # Test 4: Compare series_ticker with and without limit (we know this works)
    print("TEST 4: Comparing series_ticker results with and without limit")
    print("-" * 80)
    try:
        print("  Testing with limit=200:")
        response_limited = client.get_markets(series_ticker="KXBTCD", limit=200)
        limited_count = len(response_limited.markets) if response_limited and response_limited.markets else 0
        print(f"    Found: {limited_count} markets")
        
        print("  Testing without limit:")
        response_unlimited = client.get_markets(series_ticker="KXBTCD")
        unlimited_count = len(response_unlimited.markets) if response_unlimited and response_unlimited.markets else 0
        print(f"    Found: {unlimited_count} markets")
        
        if unlimited_count > limited_count:
            print(f"  ✓ NO LIMIT returns {unlimited_count - limited_count} more markets!")
            print(f"  Sample of additional markets (first 5):")
            if response_unlimited and response_unlimited.markets:
                for m in response_unlimited.markets[limited_count:limited_count+5]:
                    ticker = m.ticker if hasattr(m, 'ticker') else 'N/A'
                    print(f"    - {ticker}")
        elif unlimited_count == limited_count:
            print(f"  ⚠ Both return same count (may be capped at {limited_count})")
        else:
            print(f"  ⚠ Unexpected: unlimited returned fewer than limited")
        
        # Test filtering by close_time on unlimited results
        if response_unlimited and response_unlimited.markets:
            print(f"\n  Filtering unlimited results by close_time (next 60 min):")
            now = datetime.now(timezone.utc)
            current_timestamp = int(now.timestamp())
            target_window_start = current_timestamp
            target_window_end = current_timestamp + 3600
            
            matching = []
            for m in response_unlimited.markets:
                try:
                    close_time = getattr(m, 'close_time', None)
                    if close_time is None:
                        continue
                    
                    if isinstance(close_time, (int, float)):
                        close_time = int(close_time)
                    elif hasattr(close_time, 'timestamp'):
                        close_time = int(close_time.timestamp())
                    else:
                        continue
                    
                    if target_window_start <= close_time <= target_window_end:
                        ticker = getattr(m, 'ticker', '')
                        if '-T' in ticker:
                            matching.append(m)
                except:
                    continue
            
            print(f"    Markets closing in next 60 minutes: {len(matching)}")
            if matching:
                print(f"    Sample (first 5):")
                for m in matching[:5]:
                    ticker = m.ticker if hasattr(m, 'ticker') else 'N/A'
                    close_time = getattr(m, 'close_time', None)
                    strike = ticker.split('-T')[-1] if '-T' in ticker else 'N/A'
                    if close_time and isinstance(close_time, (int, float)):
                        close_dt = datetime.fromtimestamp(int(close_time), tz=timezone.utc)
                        print(f"      - {ticker} | Strike: {strike} | Closes: {close_dt.strftime('%H:%M:%S UTC')}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        if response and hasattr(response, 'markets') and response.markets:
            print("  Sample tickers (first 20):")
            for i, m in enumerate(response.markets[:20]):
                ticker = m.ticker if hasattr(m, 'ticker') else 'N/A'
                status = m.status if hasattr(m, 'status') else 'N/A'
                # Parse to show structure
                if '-T' in ticker:
                    parts = ticker.split('-T')
                    base = parts[0]
                    price = parts[1] if len(parts) > 1 else 'N/A'
                    print(f"    {i+1:2d}. {ticker:40s} | Base: {base:30s} | Price: {price:15s} | Status: {status}")
                else:
                    print(f"    {i+1:2d}. {ticker:40s} | Status: {status}")
    except Exception as e:
        print(f"✗ Error: {e}")
    print()
    
    # Test 5: Use raw API to bypass SDK validation and search for Dec 29 markets
    print("TEST 5: Raw API search for Dec 29 markets (bypassing SDK validation)")
    print("-" * 80)
    try:
        # Use client's internal API client (same as trading_bot.py)
        if hasattr(client, 'market_api') and hasattr(client.market_api, 'api_client'):
            api_client = client.market_api.api_client
            
            # Build query parameters - try without status first
            query_params = [
                ('series_ticker', 'KXBTCD'),
                ('limit', '1000')
            ]
            
            # Call the endpoint
            response = api_client.call_api(
                '/markets',
                'GET',
                query_params=query_params,
                response_type=dict
            )
            
            if isinstance(response, dict) and 'markets' in response:
                # Filter for Dec 29 markets manually
                dec29_markets = []
                all_patterns = set()
                
                for market in response['markets']:
                    ticker = market.get('ticker', '').upper()
                    status = market.get('status', '').lower()
                    
                    # Only process markets with supported statuses
                    if status not in ['initialized', 'active', 'closed', 'settled', 'determined']:
                        continue
                    
                    if '-T' in ticker:
                        base = ticker.split('-T')[0]
                        all_patterns.add(base)
                        
                        # Look for Dec 29 (25DEC29)
                        if '25DEC29' in base:
                            dec29_markets.append({
                                'ticker': market.get('ticker', ''),
                                'status': status
                            })
                
                print(f"  Found {len(dec29_markets)} Dec 29 markets (any hour)")
                if dec29_markets:
                    print("  Sample Dec 29 markets:")
                    for m in dec29_markets[:15]:
                        print(f"    - {m['ticker']} (status: {m['status']})")
                else:
                    print("  No Dec 29 markets found.")
                    print(f"  Found {len(all_patterns)} unique date/hour patterns (first 20):")
                    for p in sorted(list(all_patterns))[:20]:
                        print(f"    - {p}")
                
                # Test 6: Check if 4pm (16) markets exist
                print()
                print("TEST 6: Search for 4pm (hour 16) markets")
                print("-" * 80)
                hour16_markets = []
                for market in response['markets']:
                    ticker = market.get('ticker', '').upper()
                    status = market.get('status', '').lower()
                    
                    if status not in ['initialized', 'active', 'closed', 'settled', 'determined']:
                        continue
                    
                    if '-T' in ticker:
                        base = ticker.split('-T')[0]
                        # Check if ends with 16 (4pm) - could be ...16 or ...-16
                        if base.endswith('16') or base.endswith('-16'):
                            hour16_markets.append({
                                'ticker': market.get('ticker', ''),
                                'status': status
                            })
                
                print(f"  Found {len(hour16_markets)} markets for hour 16 (4pm)")
                if hour16_markets:
                    print("  Sample 4pm markets:")
                    for m in hour16_markets[:15]:
                        print(f"    - {m['ticker']} (status: {m['status']})")
                else:
                    print("  No 4pm markets found in current results")
            else:
                print("  No markets in response")
        else:
            print("  Client doesn't support raw API access")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    print()
    
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    test_market_search()

