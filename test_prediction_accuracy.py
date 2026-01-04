#!/usr/bin/env python3
"""
Test prediction accuracy against actual Kalshi market outcomes.
This helps validate which data sources and weighting strategies work best.
"""

import json
from datetime import datetime
from multi_source_predictor import MultiSourcePredictor
from kalshi_auth import initialize_kalshi_client


def get_kalshi_spotify_markets():
    """Get actual Spotify daily markets from Kalshi."""
    print("\n[KALSHI] Fetching actual Spotify markets...")
    try:
        client = initialize_kalshi_client()
        
        # Try different event ticker formats
        for event_ticker in ['kxspotifyd', 'KXSPOTIFYD']:
            try:
                response = client.get_markets(event_ticker=event_ticker, limit=200)
                if response and hasattr(response, 'markets'):
                    markets = response.markets or []
                    if markets:
                        print(f"[KALSHI] ✓ Found {len(markets)} markets using ticker: {event_ticker}")
                        return markets
            except:
                continue
        
        print("[KALSHI] ⚠ No markets found")
        return []
        
    except Exception as e:
        print(f"[KALSHI] ✗ Error: {e}")
        return []


def extract_song_from_market(market) -> dict:
    """Extract song info from Kalshi market."""
    title = getattr(market, 'title', '')
    subtitle = getattr(market, 'subtitle', '')
    ticker = getattr(market, 'ticker', '')
    
    # Parse song info from title/subtitle
    # Example: "Will 'Song Name' by Artist be #1?"
    import re
    
    song_match = re.search(r"'([^']+)'", title)
    artist_match = re.search(r"by ([^?]+)", title)
    
    if not song_match and subtitle:
        song_match = re.search(r"'([^']+)'", subtitle)
        artist_match = re.search(r"by ([^?]+)", subtitle)
    
    return {
        'title': song_match.group(1) if song_match else '',
        'artist': artist_match.group(1).strip() if artist_match else '',
        'market_title': title,
        'subtitle': subtitle,
        'ticker': ticker
    }


def compare_predictions_to_kalshi():
    """Compare our predictions to actual Kalshi markets."""
    print("=" * 80)
    print("PREDICTION ACCURACY TEST")
    print("=" * 80)
    
    # Get predictions
    predictor = MultiSourcePredictor()
    predictions = predictor.predict_top_songs(top_n=50)
    
    # Get actual Kalshi markets
    markets = get_kalshi_spotify_markets()
    
    if not markets:
        print("\n⚠ Could not fetch Kalshi markets for comparison")
        return
    
    # Extract songs from markets
    kalshi_songs = []
    for market in markets:
        song = extract_song_from_market(market)
        if song['title']:
            kalshi_songs.append(song)
    
    print(f"\n[COMPARISON] Found {len(kalshi_songs)} Kalshi market songs")
    
    # Normalize and match
    print("\n" + "=" * 80)
    print("MATCHING PREDICTIONS TO KALSHI MARKETS")
    print("=" * 80)
    
    matched = []
    unmatched_predictions = []
    
    for pred in predictions:
        pred_title_norm = predictor.normalize_title(pred['title'])
        pred_artist_norm = predictor.normalize_artist(pred['artist'])
        
        found = False
        for kalshi_song in kalshi_songs:
            kalshi_title_norm = predictor.normalize_title(kalshi_song['title'])
            kalshi_artist_norm = predictor.normalize_artist(kalshi_song['artist'])
            
            # Check for match
            if (pred_title_norm and kalshi_title_norm and pred_title_norm in kalshi_title_norm) or \
               (kalshi_title_norm and pred_title_norm and kalshi_title_norm in pred_title_norm):
                
                matched.append({
                    'prediction': pred,
                    'kalshi': kalshi_song,
                    'match_type': 'title'
                })
                found = True
                break
        
        if not found:
            unmatched_predictions.append(pred)
    
    # Calculate accuracy metrics
    precision = len(matched) / len(predictions) * 100 if predictions else 0
    recall = len(matched) / len(kalshi_songs) * 100 if kalshi_songs else 0
    
    print(f"\n{'='*80}")
    print("ACCURACY METRICS")
    print("=" * 80)
    print(f"Total Predictions: {len(predictions)}")
    print(f"Total Kalshi Markets: {len(kalshi_songs)}")
    print(f"Matched: {len(matched)}")
    print(f"Precision: {precision:.1f}% (predictions that match Kalshi markets)")
    print(f"Recall: {recall:.1f}% (Kalshi markets we predicted)")
    
    # Show matched predictions
    if matched:
        print(f"\n{'='*80}")
        print(f"✓ SUCCESSFULLY MATCHED PREDICTIONS ({len(matched)})")
        print("=" * 80)
        
        for i, match in enumerate(matched[:20], 1):
            pred = match['prediction']
            kalshi = match['kalshi']
            print(f"\n{i}. Predicted: '{pred['title']}' by {pred['artist']}")
            print(f"   Kalshi: {kalshi['market_title']}")
            print(f"   Score: {pred['score']:.1f} | Sources: {', '.join(pred['sources'])} | Conf: {pred['confidence']}%")
    
    # Show top unmatched (false positives)
    if unmatched_predictions:
        print(f"\n{'='*80}")
        print(f"✗ UNMATCHED PREDICTIONS - Not in Kalshi ({len(unmatched_predictions)})")
        print("=" * 80)
        
        for i, pred in enumerate(unmatched_predictions[:10], 1):
            print(f"{i}. '{pred['title']}' by {pred['artist']}")
            print(f"   Score: {pred['score']:.1f} | Sources: {', '.join(pred['sources'])}")
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'metrics': {
            'total_predictions': len(predictions),
            'total_kalshi_markets': len(kalshi_songs),
            'matched': len(matched),
            'precision': precision,
            'recall': recall
        },
        'matched': matched,
        'unmatched_predictions': unmatched_predictions[:20]
    }
    
    with open('prediction_accuracy.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n✓ Results saved to prediction_accuracy.json")
    
    return results


if __name__ == '__main__':
    compare_predictions_to_kalshi()
