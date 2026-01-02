#!/usr/bin/env python3
"""
Test script for brute force market discovery for Kalshi BTC and ETH hourly markets
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from kalshi_auth import initialize_kalshi_client
import requests
import time


def get_all_open_markets(client, asset):
    """
    Get ALL open markets for BTC or ETH to analyze format.
    
    Args:
        client: KalshiClient instance
        asset: 'BTC' or 'ETH'
    
    Returns:
        List of all open market objects
    """
    series_ticker = 'KXBTCD' if asset.upper() == 'BTC' else 'KXETHD'
    all_markets = []
    cursor = None
    limit = 200  # Max per request
    
    print(f"\n{'='*60}")
    print(f"Fetching ALL open {asset} markets...")
    print(f"{'='*60}")
    
    while True:
        try:
            params = {
                'series_ticker': series_ticker,
                'limit': limit,
                'status': 'open'
            }
            
            if cursor:
                params['cursor'] = cursor
            
            markets_response = client.get_markets(**params)
            
            if not markets_response or not hasattr(markets_response, 'markets'):
                break
                
            markets = markets_response.markets
            if not markets:
                break
            
            all_markets.extend(markets)
            print(f"  Fetched {len(markets)} markets (total: {len(all_markets)})...")
            
            # Check if there are more pages
            if hasattr(markets_response, 'cursor') and markets_response.cursor:
                cursor = markets_response.cursor
            else:
                break
                
        except Exception as e:
            print(f"Error fetching markets: {e}")
            break
    
    print(f"\n✓ Total open {asset} markets found: {len(all_markets)}")
    return all_markets


def analyze_market_format(markets, asset):
    """
    Analyze and print format details of all markets.
    
    Args:
        markets: List of market objects
        asset: 'BTC' or 'ETH'
    """
    if not markets:
        print(f"\nNo {asset} markets to analyze.")
        return
    
    print(f"\n{'='*60}")
    print(f"Market Format Analysis for {asset}")
    print(f"{'='*60}\n")
    
    # Group by ticker pattern
    ticker_patterns = {}
    unique_dates = set()
    price_values = []
    
    for market in markets:
        ticker = market.ticker
        parts = ticker.split('-')
        
        # Store pattern
        if len(parts) not in ticker_patterns:
            ticker_patterns[len(parts)] = []
        ticker_patterns[len(parts)].append(ticker)
        
        # Extract date patterns (usually second part)
        if len(parts) >= 2:
            unique_dates.add(parts[1])
        
        # Extract price patterns (usually last part or third part)
        if len(parts) >= 3:
            price_part = parts[-1]
            if price_part.startswith('T'):
                try:
                    price_value = float(price_part[1:])
                    price_values.append(price_value)
                except:
                    pass
    
    print(f"Ticker Structure Analysis:")
    for num_parts, tickers in sorted(ticker_patterns.items()):
        print(f"  {num_parts} parts: {len(tickers)} markets")
        # Show first 3 examples
        for ticker in tickers[:3]:
            print(f"    Example: {ticker}")
    
    print(f"\nDate Patterns Found: {len(unique_dates)} unique")
    sample_dates = sorted(list(unique_dates))[:10]
    for date in sample_dates:
        print(f"  {date}")
    
    if price_values:
        print(f"\nPrice Range Analysis:")
        print(f"  Min price: ${min(price_values):,.2f}")
        print(f"  Max price: ${max(price_values):,.2f}")
        print(f"  Avg price: ${sum(price_values)/len(price_values):,.2f}")
        print(f"  Total price points: {len(set(price_values))}")
    
    print(f"\n{'='*60}")
    print(f"All {asset} Markets (Total: {len(markets)})")
    print(f"{'='*60}\n")
    
    # Sort by ticker for consistent output
    sorted_markets = sorted(markets, key=lambda m: m.ticker)
    
    for i, market in enumerate(sorted_markets, 1):
        title = getattr(market, 'title', 'N/A')
        status = getattr(market, 'status', 'N/A')
        print(f"{i:4d}. {market.ticker}")
        print(f"     Title: {title}")
        print(f"     Status: {status}")
        if hasattr(market, 'expiration_time'):
            print(f"     Expiration: {market.expiration_time}")
        print()


def examine_existing_markets(client, series_ticker):
    """
    Fetch and analyze existing market tickers to understand the format
    Returns a dict with sample tickers and format analysis
    """
    print(f"\n=== Examining existing markets for series: {series_ticker} ===")
    
    try:
        # Try to get markets using series_ticker
        markets_response = client.get_markets(
            series_ticker=series_ticker,
            limit=200
        )
        
        if not markets_response or not hasattr(markets_response, 'markets'):
            print(f"No markets found for series {series_ticker}")
            return {'samples': [], 'format_info': None}
        
        print(f"Found {len(markets_response.markets)} markets")
        
        # Collect sample tickers and analyze format
        sample_tickers = []
        ticker_parts = []
        
        for market in markets_response.markets[:50]:  # Examine first 50
            ticker = market.ticker
            title = market.title if hasattr(market, 'title') else 'N/A'
            sample_tickers.append({
                'ticker': ticker,
                'title': title
            })
            
            # Parse ticker to understand structure
            parts = ticker.split('-')
            ticker_parts.append(parts)
            
            if len(sample_tickers) <= 10:  # Print first 10
                print(f"  Ticker: {ticker}")
                print(f"  Title: {title}")
                print(f"  Parts: {parts}")
                print()
        
        # Analyze format
        format_info = {}
        if ticker_parts:
            # Find common prefix
            all_prefixes = [parts[0] for parts in ticker_parts if len(parts) > 0]
            if all_prefixes:
                format_info['prefix'] = all_prefixes[0] if len(set(all_prefixes)) == 1 else 'varies'
            
            # Analyze structure (number of parts)
            part_counts = [len(parts) for parts in ticker_parts]
            format_info['num_parts'] = max(set(part_counts), key=part_counts.count) if part_counts else 0
            
            print(f"\nFormat Analysis:")
            print(f"  Prefix: {format_info.get('prefix', 'unknown')}")
            print(f"  Typical number of parts: {format_info.get('num_parts', 'unknown')}")
            print(f"  Sample structures (first 10):")
            for i, parts in enumerate(ticker_parts[:10]):
                print(f"    {i+1}. {parts} (total: {len(parts)} parts)")
        
        return {'samples': sample_tickers, 'format_info': format_info}
        
    except Exception as e:
        print(f"Error examining markets for {series_ticker}: {e}")
        import traceback
        traceback.print_exc()
        return {'samples': [], 'format_info': None}


def format_target_datetime_et(dt_et):
    """
    Convert ET datetime to Kalshi ticker format.
    Markets use ET time, so the hour in the ticker is ET hour.
    
    Format: YYMMMDDHH where:
    - YY = 2-digit year
    - MMM = 3-letter month abbreviation (uppercase)
    - DD = 2-digit day
    - HH = 2-digit hour in ET (24-hour format, with leading zero)
    
    Args:
        dt_et: datetime object in ET timezone
    
    Example: Dec 29, 2025, 7pm ET -> 25DEC2919
    """
    month_abbr = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
                   'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    
    year_2digit = dt_et.year % 100
    month_str = month_abbr[dt_et.month - 1]
    day_str = f"{dt_et.day:02d}"
    hour_str = f"{dt_et.hour:02d}"  # ET hour
    
    return f"{year_2digit:02d}{month_str}{day_str}{hour_str}"


def get_next_hour_et():
    """
    Get the next hour in ET timezone.
    Markets are scheduled by ET hour, so we need the next ET hour.
    
    Returns:
        datetime object representing the next hour in ET timezone
    """
    try:
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")  # Handles EST/EDT automatically
    except ImportError:
        # Fallback for older Python versions
        from pytz import timezone
        ET = timezone('America/New_York')
    
    # Get current time in ET
    now_et = datetime.now(ET)
    
    # Calculate next hour in ET
    next_hour_et = now_et.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    
    return next_hour_et


def extract_price_points(markets):
    """
    Extract all unique price points (the T####.## part) from existing markets.
    
    Args:
        markets: List of market objects with ticker attribute
        
    Returns:
        List of price point strings (e.g., ['T80499.99', 'T80749.99', ...])
    """
    price_points = set()
    
    for market in markets:
        ticker = market.ticker
        parts = ticker.split('-')
        if len(parts) >= 3:
            price_part = parts[-1]  # Last part is the price
            if price_part.startswith('T'):
                price_points.add(price_part)
    
    return sorted(list(price_points))


def price_point_to_value(price_point):
    """
    Convert price point string to float value.
    
    Args:
        price_point: Price point string (e.g., 'T80499.99')
        
    Returns:
        float: Price value (e.g., 80499.99)
    """
    if price_point.startswith('T'):
        return float(price_point[1:])
    return float(price_point)


def find_closest_market(current_price, market_tickers):
    """
    Find the market ticker with price point closest to the current price.
    
    Args:
        current_price: Current BTC/ETH price (float)
        market_tickers: List of market ticker strings
        
    Returns:
        str: Ticker string of the closest market, or None if no markets
    """
    if not market_tickers or current_price is None:
        return None
    
    closest_ticker = None
    min_diff = float('inf')
    
    for ticker in market_tickers:
        # Extract price point from ticker (last part after -)
        parts = ticker.split('-')
        if len(parts) >= 3:
            price_point = parts[-1]
            try:
                price_value = price_point_to_value(price_point)
                diff = abs(price_value - current_price)
                if diff < min_diff:
                    min_diff = diff
                    closest_ticker = ticker
            except ValueError:
                continue
    
    return closest_ticker


def construct_market_ticker(asset, date_str, price_point=None):
    """
    Build market ticker string in correct Kalshi format.
    
    Args:
        asset: 'BTC' or 'ETH'
        date_str: Date/time string in format from format_target_datetime() (e.g., '25DEC2919')
        price_point: Optional price point string (e.g., 'T80499.99'). If None, returns base ticker.
    
    Returns:
        Market ticker string (e.g., 'KXBTCD-25DEC2919-T80499.99')
    """
    # Series prefixes (uppercase)
    series_prefixes = {
        'BTC': 'KXBTCD',
        'ETH': 'KXETHD'
    }
    
    if asset.upper() not in series_prefixes:
        raise ValueError(f"Unknown asset: {asset}. Must be 'BTC' or 'ETH'")
    
    prefix = series_prefixes[asset.upper()]
    
    # Base ticker format: SERIES-DATE
    base_ticker = f"{prefix}-{date_str}"
    
    # If price point provided, append it: SERIES-DATE-PRICE
    if price_point:
        return f"{base_ticker}-{price_point}"
    
    return base_ticker


def get_brti_price():
    """
    Get current Bitcoin price from BRTI (Bitcoin Reference Rate Index).
    CoinDesk BPI API provides the reference rate.
    Returns price as float or None if error
    """
    try:
        # CoinDesk Bitcoin Price Index API (free, no key required)
        # This provides the BPI which is similar to BRTI reference rate
        response = requests.get(
            'https://api.coindesk.com/v1/bpi/currentprice.json',
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        # Extract USD price
        return float(data.get('bpi', {}).get('USD', {}).get('rate_float'))
    except Exception as e:
        print(f"Error fetching BRTI price: {e}")
        # Fallback to CoinGecko if CoinDesk fails
        try:
            response = requests.get(
                'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd',
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('bitcoin', {}).get('usd')
        except Exception as e2:
            print(f"Error fetching fallback price: {e2}")
            return None


def get_erti_price():
    """
    Get current Ethereum price from ERTI (Ethereum Reference Rate Index).
    CoinGecko provides Ethereum price data.
    Returns price as float or None if error
    
    Note: ETH trading is currently disabled in trading_bot.py (assets = ['BTC']).
    This function is available for future ETH support.
    """
    try:
        # Use CoinGecko for ETH price (CoinDesk BPI only supports BTC)
        response = requests.get(
            'https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd',
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        return data.get('ethereum', {}).get('usd')
    except Exception as e:
        print(f"Error fetching ERTI price: {e}")
        return None


def get_current_crypto_price(asset):
    """
    Get current BTC/ETH spot price from reference rate APIs.
    - BTC uses BRTI (Bitcoin Reference Rate Index)
    - ETH uses ERTI (Ethereum Reference Rate Index)
    Returns price as float or None if error
    """
    try:
        if asset.upper() == 'BTC':
            # Use BRTI for BTC
            return get_brti_price()
        elif asset.upper() == 'ETH':
            # Use ERTI for ETH
            return get_erti_price()
        else:
            return None
    except Exception as e:
        print(f"Error fetching {asset} price: {e}")
        return None


def check_market_exists(client, ticker):
    """
    Check if a market exists by querying via event_ticker and checking if ticker is in results.
    Returns True if market exists, False otherwise
    """
    try:
        # Extract base event ticker (SERIES-DATE part, without price)
        parts = ticker.split('-')
        if len(parts) >= 2:
            base_ticker = '-'.join(parts[:2])  # SERIES-DATE
        else:
            return False
        
        # Get all markets for this event
        markets_response = client.get_markets(
            event_ticker=base_ticker,
            status='open',  # or 'active'
            limit=200
        )
        
        if markets_response and hasattr(markets_response, 'markets'):
            # Check if our specific ticker is in the results
            for market in markets_response.markets:
                if market.ticker == ticker:
                    return True
        
        return False
    except Exception as e:
        # Market doesn't exist or other error
        return False


def discover_markets_brute_force(client, asset, target_datetime, price_range=None, step=None):
    """
    Try different price values to find existing markets
    
    Strategy:
    1. First examine existing markets to understand format
    2. Try using event_ticker to get all markets for the event
    3. If that doesn't work, try brute forcing different price values
    
    Args:
        client: KalshiClient instance
        asset: 'BTC' or 'ETH'
        target_datetime: datetime object for target hour
        price_range: tuple (min_price, max_price) or None to auto-detect
        step: price step size or None to auto-detect
    
    Returns:
        List of found market objects/dicts
    """
    print(f"\n=== Brute Force Discovery for {asset} ===")
    print(f"Target datetime: {target_datetime}")
    
    # Format the date/time portion
    date_str = format_target_datetime_et(target_datetime)
    print(f"Date string: {date_str}")
    
    # First, examine existing markets to understand the format
    series_ticker = 'KXBTCD' if asset.upper() == 'BTC' else 'KXETHD'
    market_analysis = examine_existing_markets(client, series_ticker)
    format_info = market_analysis.get('format_info', {})
    
    found_markets = []
    
    # Strategy 1: Try using event_ticker (if the base ticker is an event)
    base_ticker = construct_market_ticker(asset, date_str)
    print(f"\n=== Strategy 1: Trying event_ticker approach ===")
    print(f"Base ticker: {base_ticker}")
    
    try:
        # Try to get markets using event_ticker
        markets_response = client.get_markets(
            event_ticker=base_ticker,
            limit=100
        )
        if markets_response and hasattr(markets_response, 'markets') and markets_response.markets:
            print(f"✓ Found {len(markets_response.markets)} markets using event_ticker")
            for market in markets_response.markets:
                found_markets.append(market)
                print(f"  - {market.ticker}: {getattr(market, 'title', 'N/A')}")
            return found_markets
        else:
            print(f"✗ No markets found using event_ticker")
    except Exception as e:
        print(f"✗ Error using event_ticker: {e}")
    
    # Strategy 2: Search by series and filter by date string
    print(f"\n=== Strategy 2: Searching by series and filtering ===")
    try:
        markets_response = client.get_markets(
            series_ticker=series_ticker,
            limit=500
        )
        
        if markets_response and hasattr(markets_response, 'markets'):
            # Filter markets that match our date string
            matching_markets = []
            for market in markets_response.markets:
                if date_str in market.ticker:
                    matching_markets.append(market)
                    print(f"  Found: {market.ticker} - {getattr(market, 'title', 'N/A')}")
            
            if matching_markets:
                found_markets.extend(matching_markets)
                found_markets = list({m.ticker: m for m in found_markets}.values())  # Remove duplicates by ticker
                return found_markets
            else:
                print(f"  No markets found matching date string {date_str}")
    except Exception as e:
        print(f"Error in series search: {e}")
    
    # Strategy 3: Brute force different price values
    print(f"\n=== Strategy 3: Brute force price values ===")
    
    # Get current price to center our search
    current_price = get_current_crypto_price(asset)
    if current_price:
        print(f"Current {asset} price: ${current_price:,.2f}")
    
    # Determine price range and step
    if price_range is None:
        if current_price:
            # Default: ±20% from current price
            if asset.upper() == 'BTC':
                price_range = (current_price * 0.8, current_price * 1.2)
                step = 500 if step is None else step  # $500 steps for BTC
            else:  # ETH
                price_range = (current_price * 0.8, current_price * 1.2)
                step = 50 if step is None else step  # $50 steps for ETH
        else:
            # Fallback ranges
            if asset.upper() == 'BTC':
                price_range = (40000, 100000)
                step = 1000
            else:  # ETH
                price_range = (2000, 5000)
                step = 100
    
    print(f"Brute force range: ${price_range[0]:,.2f} - ${price_range[1]:,.2f} (step: ${step:,.2f})")
    
    # Try different prices
    min_price, max_price = price_range
    prices_to_try = []
    
    # Generate price list
    price = min_price
    while price <= max_price:
        prices_to_try.append(price)
        price += step
    
    # Also try some round numbers
    if asset.upper() == 'BTC':
        round_numbers = [40000, 45000, 50000, 55000, 60000, 65000, 70000, 75000, 80000, 90000, 100000]
    else:
        round_numbers = [2000, 2500, 3000, 3500, 4000, 4500, 5000]
    
    prices_to_try.extend([p for p in round_numbers if min_price <= p <= max_price])
    prices_to_try = sorted(list(set(prices_to_try)))  # Remove duplicates and sort
    
    print(f"Trying {len(prices_to_try)} price points...")
    
    # Limit brute force attempts to avoid too many API calls
    max_attempts = 50
    attempts = 0
    
    for price in prices_to_try[:max_attempts]:
        attempts += 1
        # Note: price needs to be formatted as price_point string (e.g., 'T80499.99')
        price_point = f"T{price:.2f}" if isinstance(price, (int, float)) else price
        ticker = construct_market_ticker(asset, date_str, price_point)
        
        if attempts % 10 == 0:
            print(f"  Attempted {attempts}/{min(len(prices_to_try), max_attempts)} prices...")
        
        if check_market_exists(client, ticker):
            print(f"  ✓ Found market at ${price:,.2f}: {ticker}")
            try:
                # Try to get market details
                markets_response = client.get_markets(event_ticker=ticker, limit=1)
                if markets_response and hasattr(markets_response, 'markets') and markets_response.markets:
                    found_markets.append(markets_response.markets[0])
            except:
                pass
        
        # Small delay to avoid rate limiting
        time.sleep(0.1)
    
    print(f"\nBrute force completed. Found {len(found_markets)} markets.")
    
    return found_markets


def find_next_hour_markets(client, asset, target_datetime_et=None):
    """
    Find all markets for the next hour by extracting price points from existing markets
    and applying them to the target ET datetime.
    
    Args:
        client: KalshiClient instance
        asset: 'BTC' or 'ETH'
        target_datetime_et: datetime object for target hour in ET (optional, defaults to next ET hour)
    
    Returns:
        tuple: (list of found tickers, closest_ticker)
    """
    # If no target datetime provided, use next ET hour
    if target_datetime_et is None:
        target_datetime_et = get_next_hour_et()
    
    print(f"\n{'='*60}")
    print(f"Finding {asset} markets for: {target_datetime_et} (ET)")
    print(f"{'='*60}")
    
    # Format the target date/hour using ET time
    date_str = format_target_datetime_et(target_datetime_et)
    print(f"Target date string (ET hour): {date_str}")
    
    # Get all open markets to extract price points
    print(f"\nFetching existing {asset} markets to extract price points...")
    existing_markets = get_all_open_markets(client, asset)
    
    if not existing_markets:
        print(f"No existing {asset} markets found to extract price points from.")
        return []
    
    # Extract all unique price points
    price_points = extract_price_points(existing_markets)
    print(f"\n✓ Extracted {len(price_points)} unique price points")
    print(f"  Sample: {price_points[:5]} ... {price_points[-5:]}")
    
    # Construct tickers for all price points with target date
    print(f"\nChecking which markets exist for {date_str}...")
    print(f"Checking ALL {len(price_points)} price points...")
    found_markets = []
    
    # Check in batches to avoid rate limiting
    batch_size = 50
    total_batches = (len(price_points) + batch_size - 1) // batch_size
    
    for i in range(0, len(price_points), batch_size):
        batch = price_points[i:i+batch_size]
        batch_num = i // batch_size + 1
        print(f"  Checking batch {batch_num}/{total_batches} ({len(batch)} tickers)...")
        
        batch_found = 0
        for price_point in batch:
            ticker = construct_market_ticker(asset, date_str, price_point)
            if check_market_exists(client, ticker):
                found_markets.append(ticker)
                batch_found += 1
                if batch_found <= 5 or batch_found == len(batch):  # Show first 5 or if all found
                    print(f"    ✓ Found: {ticker}")
        
        if batch_found > 5:
            print(f"    ... and {batch_found - 5} more in this batch")
        
        # Small delay between batches
        if i + batch_size < len(price_points):
            time.sleep(0.3)
    
    print(f"\n✓ Found {len(found_markets)} markets for {date_str}")
    
    # Get current price (BRTI for BTC, ERTI for ETH) if not already fetched
    if asset.upper() == 'BTC':
        current_price = get_brti_price()
        if current_price:
            print(f"\nCurrent BTC price (BRTI): ${current_price:,.2f}")
        else:
            print("\n⚠ Could not fetch BRTI price")
            current_price = None
    elif asset.upper() == 'ETH':
        current_price = get_erti_price()
        if current_price:
            print(f"\nCurrent ETH price (ERTI): ${current_price:,.2f}")
        else:
            print("\n⚠ Could not fetch ERTI price")
            current_price = None
    else:
        current_price = None
    
    # Find the market closest to current price
    closest_ticker = None
    if current_price and found_markets:
        print(f"\nFinding market closest to current price (${current_price:,.2f})...")
        closest_ticker = find_closest_market(current_price, found_markets)
        if closest_ticker:
            # Extract the price from the ticker
            parts = closest_ticker.split('-')
            closest_price = price_point_to_value(parts[-1])
            diff = abs(closest_price - current_price)
            print(f"✓ Closest market: {closest_ticker}")
            print(f"  Market price: ${closest_price:,.2f}")
            print(f"  Difference: ${diff:,.2f}")
        else:
            print("✗ Could not find closest market")
    else:
        if not current_price:
            print("\n⚠ Skipping closest market selection (no current price available)")
        if not found_markets:
            print("\n⚠ No markets found to select from")
    
    # Return both the list and the closest ticker
    return found_markets, closest_ticker


def main():
    """Main function to find markets for next hour using discovered price points"""
    print("=" * 60)
    print("Kalshi Next Hour Market Discovery")
    print("=" * 60)
    
    # Initialize client
    print("\nInitializing Kalshi client...")
    client = initialize_kalshi_client()
    print("✓ Client initialized")
    
    # Calculate target hour: Use next ET hour (markets are scheduled by ET)
    target_hour_et = get_next_hour_et()
    
    try:
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        now_et = datetime.now(ET)
    except ImportError:
        from pytz import timezone
        ET = timezone('America/New_York')
        now_et = datetime.now(ET)
    
    print(f"\nCurrent ET time: {now_et}")
    print(f"Target hour (ET): {target_hour_et}")
    
    # Find BTC markets for next hour
    btc_markets, btc_closest = find_next_hour_markets(client, 'BTC', target_hour_et)
    print(f"\n{'='*60}")
    print(f"BTC Markets Summary")
    print(f"{'='*60}")
    print(f"Total markets found: {len(btc_markets)}")
    if btc_closest:
        print(f"✓ Selected market (closest to BRTI): {btc_closest}")
    print(f"\nAll BTC markets (showing first 20):")
    for ticker in btc_markets[:20]:
        print(f"  {ticker}")
    if len(btc_markets) > 20:
        print(f"  ... and {len(btc_markets) - 20} more")
    
    # Find ETH markets for next hour
    eth_markets, eth_closest = find_next_hour_markets(client, 'ETH', target_hour_et)
    print(f"\n{'='*60}")
    print(f"ETH Markets Summary")
    print(f"{'='*60}")
    print(f"Total markets found: {len(eth_markets)}")
    if eth_closest:
        print(f"✓ Selected market (closest to ERTI): {eth_closest}")
    print(f"\nAll ETH markets (showing first 20):")
    for ticker in eth_markets[:20]:
        print(f"  {ticker}")
    if len(eth_markets) > 20:
        print(f"  ... and {len(eth_markets) - 20} more")
    
    print("\n" + "=" * 60)
    print("Discovery Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

