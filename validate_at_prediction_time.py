#!/usr/bin/env python3
"""
CORRECT Validation: Test predictions at 4 PM ET against actual outcomes later

Testing methodology:
1. Run predictions at 4 PM ET (when we'd make trading decisions)
2. Save predictions with timestamp
3. Check actual winner at 8 PM ET (after markets settle)
4. Measure which system correctly predicted the eventual winner

This simulates real trading: predict early, validate against outcome.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

from multi_source_predictor import MultiSourcePredictor


ET_TZ = ZoneInfo("America/New_York")
PREDICTIONS_DIR = Path("prediction_history")


def get_current_et_time():
    """Get current time in ET."""
    return datetime.now(ET_TZ)


def should_make_predictions():
    """Check if it's time to make predictions (4 PM ET)."""
    now = get_current_et_time()
    hour = now.hour
    
    # Run between 4:00 PM and 4:30 PM ET
    return 16 <= hour < 17


def get_current_snapshot() -> Dict:
    """Get current Spotify chart snapshot (what's #1 right now)."""
    print(f"\n[SNAPSHOT] Getting current chart state...")
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        url = "https://kworb.net/spotify/country/us_daily.html"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        table = soup.find('table')
        
        songs = []
        
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
                
                songs.append({
                    'rank': i,
                    'title': title,
                    'artist': artist,
                    'daily_streams': daily_streams
                })
        
        if songs:
            print(f"✓ Current #1: '{songs[0]['title']}' by {songs[0]['artist']}")
            print(f"  Streams: {songs[0]['daily_streams']:,}")
        
        return {
            'timestamp': datetime.now(ET_TZ).isoformat(),
            'top_20': songs
        }
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return {'timestamp': datetime.now(ET_TZ).isoformat(), 'top_20': []}


def make_predictions():
    """Make predictions using both systems and save them."""
    now = get_current_et_time()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%I:%M %p')
    
    print("="*80)
    print(f"MAKING PREDICTIONS FOR {date_str} at {time_str} ET")
    print("="*80)
    
    # Get current snapshot (what's winning right now)
    current_snapshot = get_current_snapshot()
    
    # Multi-source predictions
    print("\n[MULTI-SOURCE] Getting predictions...")
    predictor = MultiSourcePredictor()
    multi_predictions = predictor.predict_top_songs(top_n=20)
    
    # Kworb-only predictions (current system)
    print("\n[KWORB-ONLY] Getting predictions...")
    kworb_predictions = current_snapshot['top_20']
    
    # Save predictions
    PREDICTIONS_DIR.mkdir(exist_ok=True)
    
    prediction_data = {
        'date': date_str,
        'prediction_time': now.isoformat(),
        'prediction_time_str': time_str,
        'current_snapshot': current_snapshot,
        'multi_source': {
            'top_20': multi_predictions,
            'top_pick': multi_predictions[0] if multi_predictions else None
        },
        'kworb_only': {
            'top_20': kworb_predictions,
            'top_pick': kworb_predictions[0] if kworb_predictions else None
        }
    }
    
    filename = PREDICTIONS_DIR / f"predictions_{date_str}.json"
    with open(filename, 'w') as f:
        json.dump(prediction_data, f, indent=2, default=str)
    
    print(f"\n✓ Predictions saved to {filename}")
    
    # Display predictions
    print("\n" + "="*80)
    print("PREDICTIONS SUMMARY")
    print("="*80)
    
    if multi_predictions:
        top_multi = multi_predictions[0]
        print(f"\n🤖 MULTI-SOURCE predicts:")
        print(f"   #{1}: '{top_multi['title']}' by {top_multi['artist']}")
        print(f"   Score: {top_multi['score']:.1f} | Confidence: {top_multi['confidence']}%")
        print(f"   Sources: {', '.join(top_multi['sources'])}")
        print(f"\n   Top 5:")
        for i, p in enumerate(multi_predictions[:5], 1):
            print(f"   {i}. {p['title'][:35]} by {p['artist'][:20]}")
    
    if kworb_predictions:
        top_kworb = kworb_predictions[0]
        print(f"\n📊 KWORB-ONLY predicts:")
        print(f"   #{1}: '{top_kworb['title']}' by {top_kworb['artist']}")
        print(f"   Streams: {top_kworb['daily_streams']:,}")
        print(f"\n   Top 5:")
        for i, p in enumerate(kworb_predictions[:5], 1):
            print(f"   {i}. {p['title'][:35]} by {p['artist'][:20]}")
    
    print("\n" + "="*80)
    print("Next step: Run validation tomorrow to check which was correct!")
    print("="*80)
    
    return prediction_data


def normalize_for_matching(text: str) -> str:
    """Normalize text for fuzzy matching."""
    import re
    text = text.lower().strip()
    
    # Remove features
    for pattern in ['(feat.', '(feat', '(ft.', '(ft', '(with', '(w/', '(featuring']:
        if pattern in text:
            text = text.split(pattern)[0].strip()
    
    # Remove parentheses/brackets
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


def is_match(pred: Dict, actual: Dict) -> bool:
    """Check if prediction matches actual song."""
    pred_title = normalize_for_matching(pred.get('title', ''))
    actual_title = normalize_for_matching(actual.get('title', ''))
    
    if not pred_title or not actual_title:
        return False
    
    # Exact or substring match
    if pred_title == actual_title:
        return True
    if pred_title in actual_title or actual_title in pred_title:
        return True
    
    # Word overlap (60%+)
    pred_words = set(pred_title.split())
    actual_words = set(actual_title.split())
    if pred_words and actual_words:
        overlap = len(pred_words & actual_words) / max(len(pred_words), len(actual_words))
        if overlap >= 0.6:
            return True
    
    return False


def validate_previous_predictions():
    """Validate yesterday's predictions against today's actual outcome."""
    now = get_current_et_time()
    yesterday = now - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    
    print("="*80)
    print(f"VALIDATING PREDICTIONS FROM {yesterday_str}")
    print("="*80)
    
    # Load yesterday's predictions
    pred_file = PREDICTIONS_DIR / f"predictions_{yesterday_str}.json"
    
    if not pred_file.exists():
        print(f"\n⚠ No predictions found for {yesterday_str}")
        print("Run this script daily at 4 PM ET to build prediction history")
        return None
    
    with open(pred_file, 'r') as f:
        pred_data = json.load(f)
    
    print(f"\n✓ Loaded predictions from {pred_data['prediction_time_str']} ET")
    
    # Get today's actual winner (what won yesterday)
    print(f"\n[ACTUAL] Checking actual winner for {yesterday_str}...")
    actual = get_current_snapshot()
    
    if not actual['top_20']:
        print("✗ Cannot get actual results")
        return None
    
    actual_winner = actual['top_20'][0]
    print(f"✓ Actual winner: '{actual_winner['title']}' by {actual_winner['artist']}")
    
    # Check both systems
    multi_top = pred_data['multi_source']['top_pick']
    kworb_top = pred_data['kworb_only']['top_pick']
    
    print("\n" + "="*80)
    print("ACCURACY CHECK")
    print("="*80)
    
    # Check multi-source
    multi_correct = False
    multi_rank = None
    
    for i, pred in enumerate(pred_data['multi_source']['top_20'], 1):
        if is_match(pred, actual_winner):
            multi_correct = True
            multi_rank = i
            break
    
    if multi_correct:
        print(f"\n✅ MULTI-SOURCE: Predicted winner at rank #{multi_rank}")
        print(f"   Predicted: '{multi_top['title']}' by {multi_top['artist']}")
        print(f"   Actual: '{actual_winner['title']}' by {actual_winner['artist']}")
    else:
        print(f"\n❌ MULTI-SOURCE: Did NOT predict the winner")
        print(f"   Predicted #1: '{multi_top['title']}' by {multi_top['artist']}")
        print(f"   Actual winner: '{actual_winner['title']}' by {actual_winner['artist']}")
    
    # Check kworb-only
    kworb_correct = False
    kworb_rank = None
    
    for i, pred in enumerate(pred_data['kworb_only']['top_20'], 1):
        if is_match(pred, actual_winner):
            kworb_correct = True
            kworb_rank = i
            break
    
    if kworb_correct:
        print(f"\n✅ KWORB-ONLY: Predicted winner at rank #{kworb_rank}")
        print(f"   Predicted: '{kworb_top['title']}' by {kworb_top['artist']}")
        print(f"   Actual: '{actual_winner['title']}' by {actual_winner['artist']}")
    else:
        print(f"\n❌ KWORB-ONLY: Did NOT predict the winner")
        print(f"   Predicted #1: '{kworb_top['title']}' by {kworb_top['artist']}")
        print(f"   Actual winner: '{actual_winner['title']}' by {actual_winner['artist']}")
    
    # Determine winner
    print("\n" + "="*80)
    print("VERDICT")
    print("="*80)
    
    if multi_correct and kworb_correct:
        if multi_rank < kworb_rank:
            print(f"\n🥇 MULTI-SOURCE WINS (ranked #{multi_rank} vs #{kworb_rank})")
            winner = "multi"
        elif kworb_rank < multi_rank:
            print(f"\n🥇 KWORB-ONLY WINS (ranked #{kworb_rank} vs #{multi_rank})")
            winner = "kworb"
        else:
            print(f"\n⚖️  TIE (both ranked #{multi_rank})")
            winner = "tie"
    elif multi_correct:
        print(f"\n🥇 MULTI-SOURCE WINS (only system to predict winner)")
        winner = "multi"
    elif kworb_correct:
        print(f"\n🥇 KWORB-ONLY WINS (only system to predict winner)")
        winner = "kworb"
    else:
        print(f"\n❌ BOTH FAILED (neither predicted the winner)")
        winner = "both_failed"
    
    # Save validation result
    validation_result = {
        'date': yesterday_str,
        'prediction_time': pred_data['prediction_time'],
        'validation_time': now.isoformat(),
        'actual_winner': actual_winner,
        'multi_source': {
            'correct': multi_correct,
            'rank': multi_rank,
            'prediction': multi_top
        },
        'kworb_only': {
            'correct': kworb_correct,
            'rank': kworb_rank,
            'prediction': kworb_top
        },
        'winner': winner
    }
    
    result_file = PREDICTIONS_DIR / f"validation_{yesterday_str}.json"
    with open(result_file, 'w') as f:
        json.dump(validation_result, f, indent=2, default=str)
    
    print(f"\n✓ Validation saved to {result_file}")
    
    return validation_result


def calculate_overall_accuracy():
    """Calculate win rates across all validation days."""
    validation_files = sorted(PREDICTIONS_DIR.glob("validation_*.json"))
    
    if not validation_files:
        print("\n⚠ No validation results yet")
        print("Run daily at 4 PM ET for at least 2 days to get accuracy stats")
        return
    
    print("\n" + "="*80)
    print(f"OVERALL ACCURACY ({len(validation_files)} days)")
    print("="*80)
    
    multi_wins = 0
    kworb_wins = 0
    ties = 0
    both_failed = 0
    
    for vfile in validation_files:
        with open(vfile, 'r') as f:
            result = json.load(f)
        
        winner = result.get('winner', 'unknown')
        if winner == 'multi':
            multi_wins += 1
        elif winner == 'kworb':
            kworb_wins += 1
        elif winner == 'tie':
            ties += 1
        elif winner == 'both_failed':
            both_failed += 1
    
    total = len(validation_files)
    
    print(f"\n📊 Win Rates:")
    print(f"   Multi-source: {multi_wins}/{total} ({multi_wins/total*100:.1f}%)")
    print(f"   Kworb-only: {kworb_wins}/{total} ({kworb_wins/total*100:.1f}%)")
    print(f"   Ties: {ties}/{total} ({ties/total*100:.1f}%)")
    print(f"   Both failed: {both_failed}/{total} ({both_failed/total*100:.1f}%)")
    
    print("\n" + "="*80)
    print("RECOMMENDATION")
    print("="*80)
    
    multi_win_rate = multi_wins / total if total > 0 else 0
    kworb_win_rate = kworb_wins / total if total > 0 else 0
    
    if total < 7:
        print(f"\n⏳ Need more data ({total}/7 days)")
        print("Continue testing until 7 days of data")
    elif multi_win_rate >= 0.6:
        print(f"\n✅ INTEGRATE MULTI-SOURCE SYSTEM")
        print(f"Multi-source wins {multi_win_rate*100:.0f}% of the time")
    elif kworb_win_rate > multi_win_rate:
        print(f"\n🚫 KEEP CURRENT SYSTEM")
        print(f"Kworb-only is more accurate ({kworb_win_rate*100:.0f}% vs {multi_win_rate*100:.0f}%)")
    else:
        print(f"\n⚖️  SYSTEMS ARE SIMILAR")
        print(f"Multi: {multi_win_rate*100:.0f}%, Kworb: {kworb_win_rate*100:.0f}%")
        print("Consider other factors (earliness, reliability)")


if __name__ == '__main__':
    import sys
    
    print("="*80)
    print("PREDICTION VALIDATION AT DECISION TIME")
    print("="*80)
    
    now = get_current_et_time()
    print(f"\nCurrent time: {now.strftime('%Y-%m-%d %I:%M %p %Z')}")
    
    # Check if we have any previous predictions to validate
    validation_files = list(PREDICTIONS_DIR.glob("validation_*.json"))
    prediction_files = list(PREDICTIONS_DIR.glob("predictions_*.json"))
    
    if prediction_files:
        print(f"Found {len(prediction_files)} prediction day(s)")
        print(f"Found {len(validation_files)} validation day(s)")
    
    # Allow force mode
    force_predict = '--predict' in sys.argv or '--force' in sys.argv
    force_validate = '--validate' in sys.argv or '--force' in sys.argv
    
    # Always validate previous day's predictions first
    if not force_predict:
        print("\n[STEP 1] Validating previous predictions...")
        validate_previous_predictions()
    
    # Make new predictions if it's 4 PM ET (or forced)
    if force_predict or should_make_predictions():
        print("\n[STEP 2] Making new predictions...")
        make_predictions()
    else:
        print(f"\n[STEP 2] Skipping predictions (run between 4-5 PM ET)")
        print("To force predictions: python3 validate_at_prediction_time.py --predict")
    
    # Show overall stats
    calculate_overall_accuracy()
    
    print("\n" + "="*80)
    print("USAGE")
    print("="*80)
    print("\n📅 Daily workflow:")
    print("   python3 validate_at_prediction_time.py")
    print("   • Run daily at 4 PM ET")
    print("   • Validates yesterday's predictions")
    print("   • Makes new predictions for today")
    print("\n🔧 Manual commands:")
    print("   --predict : Force make predictions now")
    print("   --validate : Only validate previous day")
    print("   --force : Do both regardless of time")
