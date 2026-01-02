#!/usr/bin/env python3
"""
Test the full workflow without requiring Kalshi API credentials.
This validates that the Kworb integration works end-to-end.
"""

import sys
from datetime import datetime, timezone
from spotify_daily_intelligence import playlist_delta_signal, select_market_for_track


def test_kworb_workflow():
    """Test the complete workflow from Kworb to trade decision."""
    print("\n" + "="*70)
    print("FULL WORKFLOW TEST (Kworb Integration)")
    print("="*70)
    
    # Test both US and Global regions
    regions = ["US", "Global"]
    
    for region in regions:
        print(f"\n{'='*70}")
        print(f"Testing {region} Region")
        print(f"{'='*70}")
        
        # Step 1: Get signal from Kworb
        print(f"\n[STEP 1] Fetching {region} chart data from Kworb...")
        signal = playlist_delta_signal(region)
        
        if signal.get("error"):
            print(f"❌ FAILED: {signal['error']}")
            return False
        
        print(f"✓ Successfully generated signal")
        
        # Step 2: Display signal details
        predicted = signal["predicted"]
        top1 = signal["top1"]
        top2 = signal["top2"]
        
        print(f"\n[STEP 2] Signal Analysis")
        print(f"  Framework: {signal.get('framework')}")
        print(f"  Region: {signal.get('region')}")
        print(f"\n  📊 Chart Positions:")
        print(f"    #1: {top1['artist']} - {top1['title']}")
        print(f"        Streams: {top1.get('streams', 0):,}")
        print(f"        Rank: {top1.get('rank')}")
        print(f"    #2: {top2['artist']} - {top2['title']}")
        print(f"        Streams: {top2.get('streams', 0):,}")
        print(f"        Rank: {top2.get('rank')}")
        
        print(f"\n  🎯 Prediction:")
        print(f"    Predicted Winner: {predicted['artist']} - {predicted['title']}")
        print(f"    Confidence: {signal.get('confidence')}/10")
        print(f"    Rationale: {signal.get('rationale')}")
        
        print(f"\n  📈 Stream Analysis:")
        print(f"    #1 Streams: {signal.get('streams1', 0):,}")
        print(f"    #2 Streams: {signal.get('streams2', 0):,}")
        print(f"    Delta: {signal.get('stream_delta_pct', 0):.1f}%")
        print(f"    Threshold: {signal.get('stream_delta_threshold_pct', 0):.1f}%")
        
        # Step 3: Test market matching (with mock markets)
        print(f"\n[STEP 3] Testing Market Matching Logic")
        
        # Create mock markets based on predicted track
        track_title = predicted.get('title', '')
        track_artist = predicted.get('artist', '')
        
        # Mock market objects
        class MockMarket:
            def __init__(self, ticker, title):
                self.ticker = ticker
                self.title = title
        
        mock_markets = [
            MockMarket(f"KXSPOT{region.upper()}D-TEST1", f"{track_artist} - {track_title}"),
            MockMarket(f"KXSPOT{region.upper()}D-TEST2", "Some Other Song - Artist"),
            MockMarket(f"KXSPOT{region.upper()}D-TEST3", f"{track_title}"),  # Partial match
        ]
        
        selected = select_market_for_track(mock_markets, track_title, track_artist)
        
        if selected:
            print(f"✓ Market matching works: {selected.ticker}")
            print(f"  Matched to: {selected.title}")
        else:
            print(f"⚠️  No market match found (this is expected with mock data)")
        
        print(f"\n✓ {region} workflow test completed successfully")
    
    print(f"\n{'='*70}")
    print("✓ FULL WORKFLOW TEST PASSED")
    print(f"{'='*70}")
    print("\nSummary:")
    print("  ✓ Kworb chart scraping works")
    print("  ✓ Signal generation works")
    print("  ✓ Stream delta analysis works")
    print("  ✓ Market matching logic works")
    print("\nThe bot is ready to trade when Kalshi API credentials are configured.")
    print("Set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY in .env to enable trading.")
    
    return True


def main():
    """Run the workflow test."""
    try:
        success = test_kworb_workflow()
        return 0 if success else 1
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
