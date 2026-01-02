#!/usr/bin/env python3
"""
Debug script to see what markets exist and test matching logic
"""

from kalshi_auth import initialize_kalshi_client

print("\n" + "="*70)
print("DEBUGGING: Market Matching Issue")
print("="*70)

# Initialize client
client = initialize_kalshi_client()

# Check what markets exist for Jan 2
event_tickers = ["KXSPOTIFYD-26JAN02", "KXSPOTIFYGLOBALD-26JAN02"]

for event_ticker in event_tickers:
    print(f"\n[EVENT] {event_ticker}")
    print("-" * 70)
    
    try:
        resp = client.get_markets(event_ticker=event_ticker, status="open", limit=200)
        markets = getattr(resp, "markets", []) or []
        
        print(f"Found {len(markets)} markets\n")
        
        if markets:
            print("Market titles:")
            for i, m in enumerate(markets[:15], 1):
                ticker = getattr(m, "ticker", "N/A")
                title = getattr(m, "title", "N/A")
                subtitle = getattr(m, "subtitle", "N/A")
                print(f"  {i}. {ticker}")
                print(f"     Title: {title}")
                if subtitle != "N/A":
                    print(f"     Subtitle: {subtitle}")
                print()
            
            # Test Kworb predictions
            if event_ticker == "KXSPOTIFYD-26JAN02":
                kworb_title = "Golden(w/Ejae,AUDREY NUNA,REI AMI,KPop Demon Hunters Cast)"
                kworb_artist = "HUNTR/X"
            else:
                kworb_title = "The Fate of Ophelia"
                kworb_artist = "Taylor Swift"
            
            print(f"\nKworb Prediction:")
            print(f"  Title: {kworb_title}")
            print(f"  Artist: {kworb_artist}")
            
            print(f"\nTesting matching logic...")
            
            # Simple matching test
            best_match = None
            best_score = 0
            
            for m in markets:
                title = getattr(m, "title", "")
                subtitle = getattr(m, "subtitle", "")
                blob = (title + " " + subtitle).lower()
                
                score = 0
                # Check artist
                if kworb_artist.lower() in blob:
                    score += 5
                    print(f"  ✓ Found artist '{kworb_artist}' in: {title}")
                
                # Check title words
                title_words = kworb_title.lower().split()
                for word in title_words:
                    if len(word) >= 4 and word in blob:
                        score += 1
                        if score == 1:  # First match
                            print(f"  ✓ Found title word '{word}' in: {title}")
                
                if score > best_score:
                    best_score = score
                    best_match = m
            
            if best_match:
                print(f"\n✓ BEST MATCH (score={best_score}):")
                print(f"  {getattr(best_match, 'ticker', 'N/A')}")
                print(f"  {getattr(best_match, 'title', 'N/A')}")
            else:
                print(f"\n✗ NO MATCH FOUND")
                print(f"\nPossible reasons:")
                print(f"  - Artist name format different on Kalshi")
                print(f"  - Title has special characters or formatting")
                print(f"  - Need to improve matching algorithm")
        
    except Exception as e:
        print(f"Error: {e}")

print("\n" + "="*70)
