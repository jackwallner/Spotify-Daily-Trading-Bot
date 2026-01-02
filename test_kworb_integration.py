#!/usr/bin/env python3
"""
Test Kworb integration for chart scraping.
"""

import sys
from kworb_scraper import get_chart_snapshot
from spotify_daily_intelligence import playlist_delta_signal


def test_kworb_scraper():
    """Test basic Kworb scraping functionality."""
    print("\n" + "="*70)
    print("TEST: Kworb Scraper")
    print("="*70)
    
    # Test US chart
    print("\n[TEST] Scraping US chart...")
    us_chart = get_chart_snapshot("US")
    
    if not us_chart:
        print("❌ FAILED: Could not scrape US chart")
        return False
    
    if len(us_chart) < 10:
        print(f"⚠️  WARNING: Only got {len(us_chart)} tracks from US chart (expected 50)")
    else:
        print(f"✓ Successfully scraped {len(us_chart)} tracks from US chart")
    
    # Verify data structure
    first_track = us_chart[0]
    required_fields = ["rank", "artist", "title", "streams", "region", "timestamp"]
    missing_fields = [f for f in required_fields if f not in first_track]
    
    if missing_fields:
        print(f"❌ FAILED: Missing required fields: {missing_fields}")
        return False
    
    print(f"✓ Data structure validated")
    
    # Display top 5
    print(f"\n📊 Top 5 US tracks:")
    for track in us_chart[:5]:
        print(f"  {track['rank']}. {track['artist']} - {track['title']}")
        print(f"     Streams: {track.get('streams', 0):,}")
    
    # Test Global chart
    print("\n[TEST] Scraping Global chart...")
    global_chart = get_chart_snapshot("Global")
    
    if not global_chart:
        print("❌ FAILED: Could not scrape Global chart")
        return False
    
    if len(global_chart) < 10:
        print(f"⚠️  WARNING: Only got {len(global_chart)} tracks from Global chart (expected 50)")
    else:
        print(f"✓ Successfully scraped {len(global_chart)} tracks from Global chart")
    
    # Display top 5
    print(f"\n🌍 Top 5 Global tracks:")
    for track in global_chart[:5]:
        print(f"  {track['rank']}. {track['artist']} - {track['title']}")
        print(f"     Streams: {track.get('streams', 0):,}")
    
    print("\n✓ Kworb scraper test PASSED")
    return True


def test_signal_generation():
    """Test signal generation with Kworb data."""
    print("\n" + "="*70)
    print("TEST: Signal Generation")
    print("="*70)
    
    # Test US signal
    print("\n[TEST] Generating US signal...")
    us_signal = playlist_delta_signal("US")
    
    if us_signal.get("error"):
        print(f"❌ FAILED: US signal error - {us_signal['error']}")
        return False
    
    print(f"✓ US signal generated successfully")
    print(f"  Framework: {us_signal.get('framework')}")
    print(f"  Predicted #1: {us_signal['predicted']['artist']} - {us_signal['predicted']['title']}")
    print(f"  Confidence: {us_signal.get('confidence')}/10")
    print(f"  Rationale: {us_signal.get('rationale')}")
    print(f"  Top 1 streams: {us_signal.get('streams1', 0):,}")
    print(f"  Top 2 streams: {us_signal.get('streams2', 0):,}")
    print(f"  Stream delta: {us_signal.get('stream_delta_pct', 0):.1f}%")
    
    # Test Global signal
    print("\n[TEST] Generating Global signal...")
    global_signal = playlist_delta_signal("Global")
    
    if global_signal.get("error"):
        print(f"❌ FAILED: Global signal error - {global_signal['error']}")
        return False
    
    print(f"✓ Global signal generated successfully")
    print(f"  Framework: {global_signal.get('framework')}")
    print(f"  Predicted #1: {global_signal['predicted']['artist']} - {global_signal['predicted']['title']}")
    print(f"  Confidence: {global_signal.get('confidence')}/10")
    print(f"  Rationale: {global_signal.get('rationale')}")
    print(f"  Top 1 streams: {global_signal.get('streams1', 0):,}")
    print(f"  Top 2 streams: {global_signal.get('streams2', 0):,}")
    print(f"  Stream delta: {global_signal.get('stream_delta_pct', 0):.1f}%")
    
    print("\n✓ Signal generation test PASSED")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("KWORB INTEGRATION TEST SUITE")
    print("="*70)
    
    results = []
    
    # Run tests
    results.append(("Kworb Scraper", test_kworb_scraper()))
    results.append(("Signal Generation", test_signal_generation()))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n🎉 All tests PASSED!")
        return 0
    else:
        print("\n⚠️  Some tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
