#!/usr/bin/env python3
"""
Integration helper: Use multi-source predictions in the trading bot.
This script shows how to integrate the improved prediction system.
"""

from multi_source_predictor import MultiSourcePredictor
from datetime import datetime
import json


def get_enhanced_predictions(top_n=20, min_confidence=70):
    """
    Get enhanced predictions with filtering.
    
    Args:
        top_n: Number of predictions to return
        min_confidence: Minimum confidence threshold (0-100)
    
    Returns:
        List of high-confidence predictions
    """
    print("🎵 Running Multi-Source Prediction System...")
    print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %I:%M %p ET')}\n")
    
    predictor = MultiSourcePredictor()
    all_predictions = predictor.predict_top_songs(top_n=top_n * 2)  # Get extra, then filter
    
    # Filter by confidence
    filtered = [p for p in all_predictions if p['confidence'] >= min_confidence]
    
    print(f"\n📊 Filtering Results:")
    print(f"   Total predictions: {len(all_predictions)}")
    print(f"   High confidence ({min_confidence}%+): {len(filtered)}")
    print(f"   Cross-validated (2+ sources): {sum(1 for p in filtered if p['cross_validation'] >= 2)}")
    
    return filtered[:top_n]


def format_for_trading_bot(predictions):
    """
    Format predictions for trading bot consumption.
    Returns list compatible with existing bot logic.
    """
    formatted = []
    
    for pred in predictions:
        formatted.append({
            'track_name': pred['title'],
            'artist_name': pred['artist'],
            'prediction_score': pred['score'],
            'confidence': pred['confidence'],
            'data_sources': pred['sources'],
            'cross_validated': pred['cross_validation'] >= 2
        })
    
    return formatted


def example_integration():
    """
    Example of how to use this in trading_bot.py
    """
    # Get predictions
    predictions = get_enhanced_predictions(top_n=20, min_confidence=70)
    
    # Format for trading
    trading_candidates = format_for_trading_bot(predictions)
    
    print("\n" + "="*80)
    print("TOP TRADING CANDIDATES")
    print("="*80)
    
    for i, track in enumerate(trading_candidates[:10], 1):
        cross_val_mark = "✓✓" if track['cross_validated'] else "  "
        print(f"{i:2}. {cross_val_mark} {track['track_name'][:40]:<40} by {track['artist_name'][:20]:<20}")
        print(f"      Score: {track['prediction_score']:.1f} | Conf: {track['confidence']}% | Sources: {', '.join(track['data_sources'])}")
    
    # Save for bot to use
    output = {
        'timestamp': datetime.now().isoformat(),
        'tracks': trading_candidates
    }
    
    with open('trading_candidates.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✓ Trading candidates saved to trading_candidates.json")
    
    return trading_candidates


def integration_code_example():
    """
    Show code example for integration into trading_bot.py
    """
    code = '''
# In trading_bot.py, replace the Kworb section with:

from multi_source_predictor import MultiSourcePredictor

def get_trending_tracks():
    """Get trending tracks from multiple sources."""
    predictor = MultiSourcePredictor()
    predictions = predictor.predict_top_songs(top_n=20)
    
    # Filter for high confidence only
    high_confidence = [p for p in predictions if p['confidence'] >= 75]
    
    # Convert to expected format
    tracks = []
    for pred in high_confidence:
        tracks.append({
            'title': pred['title'],
            'artist': pred['artist'],
            'daily_streams': 0,  # Not needed with multi-source
            'region': 'US',
            'prediction_score': pred['score'],
            'confidence': pred['confidence']
        })
    
    return tracks

# Then use as before:
tracks = get_trending_tracks()
for track in tracks[:10]:  # Top 10 only
    # ... existing market matching and trading logic ...
'''
    
    print("\n" + "="*80)
    print("INTEGRATION CODE EXAMPLE")
    print("="*80)
    print(code)
    
    with open('INTEGRATION_EXAMPLE.txt', 'w') as f:
        f.write(code)
    
    print("\n✓ Integration example saved to INTEGRATION_EXAMPLE.txt")


if __name__ == '__main__':
    # Run example
    candidates = example_integration()
    
    # Show integration code
    integration_code_example()
    
    print("\n" + "="*80)
    print("NEXT STEPS")
    print("="*80)
    print("1. Review trading_candidates.json")
    print("2. Test accuracy by comparing to Kalshi markets")
    print("3. Run daily at 3 PM ET for 1 week")
    print("4. If accuracy >= 60%, integrate into trading_bot.py")
    print("5. Update GitHub Actions schedule to 3 PM ET")
