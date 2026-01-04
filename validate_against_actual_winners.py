#!/usr/bin/env python3
"""
Validation: Test prediction accuracy against ACTUAL Spotify daily chart winners
Goal: Predict which song will be #1, not just match Kalshi markets

Test approach:
1. Run predictions at 3 PM ET
2. Check actual Spotify #1 the next day
3. Measure which system correctly predicts winners
"""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import time

from multi_source_predictor import MultiSourcePredictor


def get_actual_spotify_winner() -> Dict:
    """
    Get the actual #1 song from Spotify's daily chart.
    Uses Kworb as ground truth since it reflects actual Spotify data.
    """
    print("\n[GROUND TRUTH] Fetching actual Spotify #1...")
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        url = "https://kworb.net/spotify/country/us_daily.html"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        table = soup.find('table')
        
        if not table:
            print("✗ Could not find chart table")
            return {}
        
        # Get the first row (rank #1)
        rows = table.find_all('tr')[1:]  # Skip header
        if not rows:
            print("✗ No data rows found")
            return {}
        
        first_row = rows[0]
        cells = first_row.find_all('td')
        
        if len(cells) < 7:
            print("✗ Not enough columns in table")
            return {}
        
        # Parse the #1 song
        artist_title = cells[2].get_text(strip=True)
        daily_streams_text = cells[6].get_text(strip=True).replace(',', '')
        
        artist = "Unknown"
        title = artist_title
        
        if '-' in artist_title:
            parts = artist_title.split('-', 1)
            if len(parts) == 2:
                artist = parts[0].strip()
                title = parts[1].strip()
        
        try:
            daily_streams = int(daily_streams_text)
        except:
            daily_streams = 0
        
        winner = {
            'title': title,
            'artist': artist,
            'daily_streams': daily_streams,
            'source': 'spotify_actual'
        }
        
        print(f"✓ Actual #1: '{title}' by {artist}")
        print(f"  Streams: {daily_streams:,}")
        
        return winner
        
    except Exception as e:
        print(f"✗ Error fetching actual winner: {e}")
        return {}


def normalize_for_matching(text: str) -> str:
    """Normalize text for fuzzy matching."""
    import re
    text = text.lower().strip()
    
    # Remove features, remixes, etc.
    for pattern in ['(feat.', '(feat', '(ft.', '(ft', '(with', '(w/', '(featuring']:
        if pattern in text:
            text = text.split(pattern)[0].strip()
    
    # Remove parentheses content
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'\[[^\]]*\]', '', text)
    
    # Remove special characters
    text = re.sub(r'[^a-z0-9\s]', '', text)
    
    # Remove common words
    for word in ['the', 'a', 'an']:
        text = text.replace(f' {word} ', ' ')
    
    # Collapse spaces
    text = ' '.join(text.split())
    
    return text


def is_match(prediction: Dict, actual: Dict, strict: bool = False) -> bool:
    """
    Check if prediction matches actual winner.
    
    Args:
        prediction: Predicted song
        actual: Actual #1 song
        strict: If True, require both title and artist to match
    """
    pred_title = normalize_for_matching(prediction.get('title', ''))
    pred_artist = normalize_for_matching(prediction.get('artist', ''))
    
    actual_title = normalize_for_matching(actual.get('title', ''))
    actual_artist = normalize_for_matching(actual.get('artist', ''))
    
    # Title match
    title_match = False
    if pred_title and actual_title:
        # Exact match or substring match or significant word overlap
        if pred_title == actual_title:
            title_match = True
        elif pred_title in actual_title or actual_title in pred_title:
            title_match = True
        else:
            # Check word overlap (need 60%+ matching words)
            pred_words = set(pred_title.split())
            actual_words = set(actual_title.split())
            if pred_words and actual_words:
                overlap = len(pred_words & actual_words) / max(len(pred_words), len(actual_words))
                if overlap >= 0.6:
                    title_match = True
    
    # Artist match
    artist_match = False
    if pred_artist and actual_artist:
        if pred_artist == actual_artist:
            artist_match = True
        elif pred_artist in actual_artist or actual_artist in pred_artist:
            artist_match = True
    
    if strict:
        return title_match and artist_match
    else:
        # Lenient: just need title match (artist can be parsed differently)
        return title_match


def test_multi_source_predictions() -> List[Dict]:
    """Get top predictions from multi-source system."""
    print("\n" + "="*80)
    print("TESTING: Multi-Source Prediction System")
    print("="*80)
    
    predictor = MultiSourcePredictor()
    predictions = predictor.predict_top_songs(top_n=20)
    
    # Filter for high confidence
    high_confidence = [p for p in predictions if p['confidence'] >= 70]
    
    print(f"\n📊 Multi-Source Predictions:")
    print(f"   Total: {len(predictions)}")
    print(f"   High confidence (70%+): {len(high_confidence)}")
    print(f"   Cross-validated (2+): {sum(1 for p in predictions if p['cross_validation'] >= 2)}")
    
    if predictions:
        print(f"\n   Top 5 predictions:")
        for i, p in enumerate(predictions[:5], 1):
            cross = "✓✓" if p['cross_validation'] >= 2 else "  "
            print(f"   {i}. {cross} {p['title'][:40]} by {p['artist'][:20]} (score: {p['score']:.1f}, conf: {p['confidence']}%)")
    
    return predictions


def test_kworb_only_predictions() -> List[Dict]:
    """Get top predictions from current Kworb-only system."""
    print("\n" + "="*80)
    print("TESTING: Current Kworb-Only System")
    print("="*80)
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        url = "https://kworb.net/spotify/country/us_daily.html"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        table = soup.find('table')
        
        predictions = []
        
        if table:
            rows = table.find_all('tr')[1:21]  # Top 20
            
            for i, row in enumerate(rows, 1):
                cells = row.find_all('td')
                if len(cells) < 7:
                    continue
                
                artist_title = cells[2].get_text(strip=True)
                daily_streams_text = cells[6].get_text(strip=True).replace(',', '')
                
                artist = "Unknown"
                title = artist_title
                
                if '-' in artist_title:
                    parts = artist_title.split('-', 1)
                    if len(parts) == 2:
                        artist = parts[0].strip()
                        title = parts[1].strip()
                
                try:
                    daily_streams = int(daily_streams_text)
                except:
                    daily_streams = 0
                
                predictions.append({
                    'title': title,
                    'artist': artist,
                    'daily_streams': daily_streams,
                    'confidence': 60  # Default
                })
        
        print(f"\n📊 Kworb-Only Predictions:")
        print(f"   Total: {len(predictions)}")
        
        if predictions:
            print(f"\n   Top 5 predictions:")
            for i, p in enumerate(predictions[:5], 1):
                print(f"   {i}. {p['title'][:40]} by {p['artist'][:20]} ({p['daily_streams']:,} streams)")
        
        return predictions
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return []


def compare_systems():
    """
    Main comparison: Which system better predicts the #1 song?
    """
    print("\n" + "="*80)
    print("PREDICTION ACCURACY VALIDATION")
    print("Goal: Predict the actual #1 song on Spotify's daily chart")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %I:%M %p ET')}")
    print("="*80)
    
    # Get actual winner
    print("\n[STEP 1] Fetching actual Spotify #1 (ground truth)...")
    actual_winner = get_actual_spotify_winner()
    
    if not actual_winner or not actual_winner.get('title'):
        print("\n❌ Cannot validate without actual winner data")
        return None
    
    # Get predictions from both systems
    print("\n[STEP 2] Getting predictions from multi-source system...")
    multi_predictions = test_multi_source_predictions()
    
    print("\n[STEP 3] Getting predictions from Kworb-only system...")
    kworb_predictions = test_kworb_only_predictions()
    
    # Check if either system predicted the winner
    print("\n" + "="*80)
    print("PREDICTION ACCURACY")
    print("="*80)
    
    print(f"\n🏆 ACTUAL WINNER:")
    print(f"   '{actual_winner['title']}' by {actual_winner['artist']}")
    print(f"   Streams: {actual_winner['daily_streams']:,}")
    
    # Check multi-source
    multi_correct = False
    multi_rank = None
    for i, pred in enumerate(multi_predictions, 1):
        if is_match(pred, actual_winner):
            multi_correct = True
            multi_rank = i
            print(f"\n✅ MULTI-SOURCE: Predicted winner at rank #{i}")
            print(f"   Prediction: '{pred['title']}' by {pred['artist']}")
            print(f"   Score: {pred['score']:.1f} | Confidence: {pred['confidence']}% | Sources: {', '.join(pred['sources'])}")
            break
    
    if not multi_correct:
        print(f"\n❌ MULTI-SOURCE: Did NOT predict the winner in top 20")
    
    # Check Kworb-only
    kworb_correct = False
    kworb_rank = None
    for i, pred in enumerate(kworb_predictions, 1):
        if is_match(pred, actual_winner):
            kworb_correct = True
            kworb_rank = i
            print(f"\n✅ KWORB-ONLY: Predicted winner at rank #{i}")
            print(f"   Prediction: '{pred['title']}' by {pred['artist']}")
            print(f"   Streams: {pred['daily_streams']:,}")
            break
    
    if not kworb_correct:
        print(f"\n❌ KWORB-ONLY: Did NOT predict the winner in top 20")
    
    # Determine winner
    print("\n" + "="*80)
    print("VERDICT")
    print("="*80)
    
    if multi_correct and kworb_correct:
        if multi_rank < kworb_rank:
            print(f"\n🥇 MULTI-SOURCE WINS")
            print(f"   Ranked winner higher: #{multi_rank} vs #{kworb_rank}")
            verdict = "multi_better"
        elif kworb_rank < multi_rank:
            print(f"\n🥇 KWORB-ONLY WINS")
            print(f"   Ranked winner higher: #{kworb_rank} vs #{multi_rank}")
            verdict = "kworb_better"
        else:
            print(f"\n⚖️  TIE")
            print(f"   Both ranked winner at #{multi_rank}")
            verdict = "tie"
    elif multi_correct:
        print(f"\n🥇 MULTI-SOURCE WINS")
        print(f"   Only system to predict winner (at rank #{multi_rank})")
        verdict = "multi_better"
    elif kworb_correct:
        print(f"\n🥇 KWORB-ONLY WINS")
        print(f"   Only system to predict winner (at rank #{kworb_rank})")
        verdict = "kworb_better"
    else:
        print(f"\n❌ BOTH SYSTEMS FAILED")
        print(f"   Neither predicted the winner")
        verdict = "both_failed"
    
    # Recommendation
    print("\n" + "="*80)
    print("RECOMMENDATION")
    print("="*80)
    
    if verdict == "multi_better":
        print("\n✅ Multi-source system shows promise")
        print("\nNext steps:")
        print("1. Run this test daily for 7 days")
        print("2. Track win rate: How often does each system predict #1?")
        print("3. If multi-source wins 60%+ of tests, consider integration")
    elif verdict == "kworb_better":
        print("\n⚠️  Kworb-only system is currently better")
        print("\nNext steps:")
        print("1. Keep current system")
        print("2. Improve multi-source (adjust weights, add sources)")
        print("3. Re-test after improvements")
    elif verdict == "tie":
        print("\n⚖️  Systems are equally accurate")
        print("\nNext steps:")
        print("1. Test daily for 7 days to find consistent winner")
        print("2. Consider other factors (speed, reliability, earliness)")
    else:
        print("\n❌ Both systems need improvement")
        print("\nNext steps:")
        print("1. Analyze why winner wasn't predicted")
        print("2. Check if winner data is in sources")
        print("3. Improve prediction algorithms")
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'actual_winner': actual_winner,
        'multi_source': {
            'correct': multi_correct,
            'rank': multi_rank,
            'top_prediction': multi_predictions[0] if multi_predictions else None
        },
        'kworb_only': {
            'correct': kworb_correct,
            'rank': kworb_rank,
            'top_prediction': kworb_predictions[0] if kworb_predictions else None
        },
        'verdict': verdict
    }
    
    with open('validation_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n✓ Results saved to validation_results.json")
    
    return results


def historical_test():
    """
    Test with multiple days of data if available.
    This would require storing historical predictions and outcomes.
    """
    print("\n" + "="*80)
    print("HISTORICAL TESTING")
    print("="*80)
    print("\n💡 To run historical tests:")
    print("1. Run this script daily at 3 PM ET")
    print("2. Save predictions to dated files")
    print("3. Check actual winner the next day")
    print("4. Track success rate over time")
    print("\nFor now, running single-day test...")


if __name__ == '__main__':
    print("="*80)
    print("WINNER PREDICTION VALIDATION")
    print("Testing against actual Spotify #1 song")
    print("="*80)
    
    results = compare_systems()
    
    if results:
        print("\n" + "="*80)
        print("TESTING PROTOCOL")
        print("="*80)
        print("\n📅 Daily Testing Schedule:")
        print("   1. Run at 3 PM ET: python3 validate_against_actual_winners.py")
        print("   2. Save results with date: mv validation_results.json results_2026-01-04.json")
        print("   3. Repeat for 7 days")
        print("   4. Calculate win rates")
        print("\n📊 Success Metrics:")
        print("   • Multi-source predicts winner 60%+ of days: INTEGRATE")
        print("   • Kworb-only better: KEEP CURRENT")
        print("   • Similar (<10% diff): TEST LONGER")
        print("\n⏰ Timing:")
        print("   • Predictions run at 3 PM ET")
        print("   • Compare to current #1 (updates throughout day)")
        print("   • Earlier predictions = better for trading")
