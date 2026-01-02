#!/usr/bin/env python3
"""
Debug script to check what Spotify markets exist on Kalshi
"""

from kalshi_auth import initialize_kalshi_client

print("\n" + "="*70)
print("DEBUGGING: Available Kalshi Spotify Markets")
print("="*70)

try:
    client = initialize_kalshi_client()
    
    # Check what we're querying
    print("\n[1] Checking specific event tickers:")
    for event_ticker in ["kxspotifyd-26jan02", "kxspotifyglobald-26jan02"]:
        print(f"\n  Event: {event_ticker}")
        try:
            resp = client.get_markets(event_ticker=event_ticker, status="open", limit=200)
            markets = getattr(resp, "markets", []) or []
            print(f"  Markets found: {len(markets)}")
            if markets:
                for m in markets[:5]:
                    print(f"    - {m.ticker}: {m.title}")
        except Exception as e:
            print(f"  Error: {e}")
    
    # Try broader search
    print("\n[2] Searching for ANY Spotify-related markets:")
    try:
        # Search broadly
        resp = client.get_markets(status="open", limit=200)
        markets = getattr(resp, "markets", []) or []
        
        spotify_markets = [m for m in markets if 'spotify' in str(m.ticker).lower() or 'spotify' in str(getattr(m, 'title', '')).lower()]
        
        print(f"  Total open markets scanned: {len(markets)}")
        print(f"  Spotify-related markets: {len(spotify_markets)}")
        
        if spotify_markets:
            print("\n  Found Spotify markets:")
            for m in spotify_markets[:10]:
                print(f"    - {m.ticker}: {getattr(m, 'title', 'N/A')}")
                print(f"      Event: {getattr(m, 'event_ticker', 'N/A')}")
        else:
            print("  ⚠️  No Spotify markets found in open markets")
            print("\n  Sample of other markets available:")
            for m in markets[:5]:
                print(f"    - {m.ticker}: {getattr(m, 'title', 'N/A')}")
                
    except Exception as e:
        print(f"  Error: {e}")
    
    # Check series ticker
    print("\n[3] Checking series ticker format:")
    for series in ["KXSPOTIFYD", "kxspotifyd", "SPOTIFY", "spotify"]:
        print(f"\n  Series: {series}")
        try:
            resp = client.get_markets(series_ticker=series, status="open", limit=50)
            markets = getattr(resp, "markets", []) or []
            print(f"  Markets found: {len(markets)}")
            if markets:
                for m in markets[:3]:
                    print(f"    - {m.ticker}: {getattr(m, 'title', 'N/A')}")
        except Exception as e:
            print(f"  Error: {e}")
    
    print("\n" + "="*70)
    print("RECOMMENDATIONS")
    print("="*70)
    print("\nBased on results above:")
    print("1. If no markets found → Markets don't exist yet for Jan 2")
    print("2. If markets found with different event ticker → Update bot")
    print("3. If markets exist but are closed → Check market open/close times")
    
except Exception as e:
    print(f"\n❌ Error initializing Kalshi client: {e}")
    print("\nThis is expected if you don't have KALSHI_API_KEY_ID set locally.")
    print("This debug script needs to run with Kalshi credentials.")

print()
