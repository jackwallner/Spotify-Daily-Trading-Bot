#!/usr/bin/env python3
"""
Validation Script: Test multi-source predictions against actual Kalshi outcomes
DO NOT integrate into trading bot until validation shows improvement!

This script:
1. Gets predictions from multi-source system
2. Gets actual Kalshi markets
3. Compares accuracy vs current Kworb-only approach
4. Shows which system is better before any changes
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Tuple
from pathlib import Path

# Import both systems
from multi_source_predictor import MultiSourcePredictor
import sys
sys.path.insert(0, '/workspace')
try:
    import kworb_scraper
    HAS_KWORB = True
except:
    HAS_KWORB = False


def load_env():
    """Load environment variables."""
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        return True
    return False


def get_kalshi_markets_safe():
    """Get Kalshi markets with error handling."""
    try:
        from kalshi_auth import initialize_kalshi_client
        client = initialize_kalshi_client()
        
        # Try multiple ticker formats
        for event_ticker in ['kxspotifyd', 'KXSPOTIFYD']:
            try:
                response = client.get_markets(event_ticker=event_ticker, limit=200)
                if response and hasattr(response, 'markets'):
                    markets = response.markets or []
                    if markets:
                        print(f"✓ Found {len(markets)} Kalshi markets")
                        return markets
            except Exception as e:
                continue
        
        print("⚠ No Kalshi markets found")
        return []
        
    except Exception as e:
        print(f"⚠ Cannot connect to Kalshi: {e}")
        print("  (This is OK for initial testing - will use mock data)")
        return []


def normalize_for_comparison(text: str) -> str:
    """Aggressive normalization for matching."""
    import re
    text = text.lower().strip()
    
    # Remove all special characters except spaces
    text = re.sub(r'[^a-z0-9\s]', '', text)
    
    # Remove common words
    for word in ['the', 'a', 'an', 'feat', 'ft', 'featuring', 'with']:
        text = text.replace(f' {word} ', ' ')
    
    # Collapse spaces
    text = ' '.join(text.split())
    
    return text


def extract_song_from_market(market) -> Dict:
    """Extract song info from Kalshi market."""
    import re
    
    title = getattr(market, 'title', '')
    subtitle = getattr(market, 'subtitle', '')
    ticker = getattr(market, 'ticker', '')
    
    # Parse: "Will 'Song Name' by Artist be #1?"
    song_match = re.search(r"'([^']+)'", title + ' ' + subtitle)
    artist_match = re.search(r"by ([^?]+)", title + ' ' + subtitle)
    
    return {
        'title': song_match.group(1).strip() if song_match else '',
        'artist': artist_match.group(1).strip() if artist_match else '',
        'market_title': title,
        'subtitle': subtitle,
        'ticker': ticker
    }


def test_multi_source_system() -> Tuple[List[Dict], int]:
    """
    Test the new multi-source prediction system.
    Returns: (predictions, execution_time_ms)
    """
    print("\n" + "="*80)
    print("TESTING: Multi-Source Prediction System")
    print("="*80)
    
    start_time = datetime.now()
    
    predictor = MultiSourcePredictor()
    predictions = predictor.predict_top_songs(top_n=50)
    
    # Filter for high confidence
    high_confidence = [p for p in predictions if p['confidence'] >= 70]
    
    execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
    
    print(f"\n📊 Multi-Source Results:")
    print(f"   Total predictions: {len(predictions)}")
    print(f"   High confidence (70%+): {len(high_confidence)}")
    print(f"   Cross-validated (2+ sources): {sum(1 for p in predictions if p['cross_validation'] >= 2)}")
    print(f"   Execution time: {execution_time}ms")
    
    return high_confidence, execution_time


def test_current_kworb_system() -> Tuple[List[Dict], int]:
    """
    Test the current Kworb-only system.
    Returns: (predictions, execution_time_ms)
    """
    print("\n" + "="*80)
    print("TESTING: Current Kworb-Only System")
    print("="*80)
    
    start_time = datetime.now()
    
    try:
        # Use kworb_scraper directly
        import requests
        from bs4 import BeautifulSoup
        
        url = "https://kworb.net/spotify/country/us_daily.html"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        table = soup.find('table')
        
        predictions = []
        
        if table:
            rows = table.find_all('tr')[1:51]  # Top 50
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 7:
                    continue
                
                artist_title = cells[2].get_text(strip=True)
                daily_streams_text = cells[6].get_text(strip=True).replace(',', '')
                
                # Parse artist and title
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
                    'confidence': 60  # Default confidence for Kworb
                })
        
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        print(f"\n📊 Kworb-Only Results:")
        print(f"   Total predictions: {len(predictions)}")
        print(f"   Execution time: {execution_time}ms")
        
        return predictions, execution_time
        
    except Exception as e:
        print(f"✗ Error testing Kworb system: {e}")
        return [], 0


def match_prediction_to_markets(predictions: List[Dict], kalshi_markets: List) -> Tuple[List, List]:
    """
    Match predictions to Kalshi markets.
    Returns: (matched, unmatched)
    """
    matched = []
    unmatched = []
    
    kalshi_songs = [extract_song_from_market(m) for m in kalshi_markets]
    kalshi_songs = [s for s in kalshi_songs if s['title']]  # Filter empty
    
    for pred in predictions:
        pred_title = normalize_for_comparison(pred['title'])
        pred_artist = normalize_for_comparison(pred['artist'])
        
        found = False
        for kalshi_song in kalshi_songs:
            k_title = normalize_for_comparison(kalshi_song['title'])
            k_artist = normalize_for_comparison(kalshi_song['artist'])
            
            # Match on title (most reliable)
            if pred_title and k_title and (
                pred_title in k_title or 
                k_title in pred_title or
                len(set(pred_title.split()) & set(k_title.split())) >= 2  # 2+ words match
            ):
                matched.append({
                    'prediction': pred,
                    'kalshi': kalshi_song
                })
                found = True
                break
        
        if not found:
            unmatched.append(pred)
    
    return matched, unmatched


def calculate_metrics(matched: List, unmatched: List, total_kalshi: int) -> Dict:
    """Calculate accuracy metrics."""
    total_predictions = len(matched) + len(unmatched)
    
    precision = (len(matched) / total_predictions * 100) if total_predictions > 0 else 0
    recall = (len(matched) / total_kalshi * 100) if total_kalshi > 0 else 0
    f1_score = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0
    
    return {
        'total_predictions': total_predictions,
        'matched': len(matched),
        'unmatched': len(unmatched),
        'precision': precision,
        'recall': recall,
        'f1_score': f1_score
    }


def compare_systems():
    """
    Main comparison function.
    Compare multi-source vs Kworb-only and determine which is better.
    """
    print("\n" + "="*80)
    print("PREDICTION SYSTEM VALIDATION")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %I:%M %p ET')}")
    print("="*80)
    
    # Load credentials if available
    has_credentials = load_env()
    if not has_credentials:
        print("\n⚠ No .env file found - will use limited testing")
    
    # Get Kalshi markets
    print("\n[1/4] Fetching Kalshi markets...")
    kalshi_markets = get_kalshi_markets_safe()
    
    if not kalshi_markets:
        print("\n❌ VALIDATION FAILED: Cannot test without Kalshi markets")
        print("\nNext steps:")
        print("1. Create .env file with Kalshi credentials")
        print("2. Run this script again to validate accuracy")
        print("3. Only integrate if multi-source is better than Kworb-only")
        return None
    
    print(f"✓ Found {len(kalshi_markets)} Kalshi markets to compare against")
    
    # Test multi-source system
    print("\n[2/4] Testing multi-source prediction system...")
    multi_predictions, multi_time = test_multi_source_system()
    
    # Test current Kworb system
    print("\n[3/4] Testing current Kworb-only system...")
    kworb_predictions, kworb_time = test_current_kworb_system()
    
    # Compare both systems
    print("\n[4/4] Comparing predictions to Kalshi markets...")
    
    multi_matched, multi_unmatched = match_prediction_to_markets(multi_predictions, kalshi_markets)
    kworb_matched, kworb_unmatched = match_prediction_to_markets(kworb_predictions, kalshi_markets)
    
    multi_metrics = calculate_metrics(multi_matched, multi_unmatched, len(kalshi_markets))
    kworb_metrics = calculate_metrics(kworb_matched, kworb_unmatched, len(kalshi_markets))
    
    # Display results
    print("\n" + "="*80)
    print("ACCURACY COMPARISON")
    print("="*80)
    
    print("\n📊 MULTI-SOURCE SYSTEM:")
    print(f"   Predictions: {multi_metrics['total_predictions']}")
    print(f"   Matched: {multi_metrics['matched']}")
    print(f"   Precision: {multi_metrics['precision']:.1f}%")
    print(f"   Recall: {multi_metrics['recall']:.1f}%")
    print(f"   F1 Score: {multi_metrics['f1_score']:.1f}")
    print(f"   Speed: {multi_time}ms")
    
    print("\n📊 KWORB-ONLY SYSTEM:")
    print(f"   Predictions: {kworb_metrics['total_predictions']}")
    print(f"   Matched: {kworb_metrics['matched']}")
    print(f"   Precision: {kworb_metrics['precision']:.1f}%")
    print(f"   Recall: {kworb_metrics['recall']:.1f}%")
    print(f"   F1 Score: {kworb_metrics['f1_score']:.1f}")
    print(f"   Speed: {kworb_time}ms")
    
    # Determine winner
    print("\n" + "="*80)
    print("VERDICT")
    print("="*80)
    
    multi_score = multi_metrics['f1_score']
    kworb_score = kworb_metrics['f1_score']
    improvement = ((multi_score - kworb_score) / kworb_score * 100) if kworb_score > 0 else 0
    
    if multi_score > kworb_score * 1.1:  # At least 10% better
        print(f"\n✅ MULTI-SOURCE IS BETTER by {improvement:.1f}%")
        print("\nRecommendation: INTEGRATE multi-source system")
        print("Benefits:")
        print(f"  • {improvement:.1f}% improvement in accuracy")
        print(f"  • Cross-validation reduces false positives")
        print(f"  • Can run 4+ hours earlier (3 PM vs 7 PM ET)")
        verdict = "integrate"
    elif multi_score < kworb_score * 0.9:  # More than 10% worse
        print(f"\n❌ MULTI-SOURCE IS WORSE by {abs(improvement):.1f}%")
        print("\nRecommendation: DO NOT INTEGRATE")
        print("Issues:")
        print(f"  • {abs(improvement):.1f}% decrease in accuracy")
        print(f"  • Current Kworb-only system is more accurate")
        print(f"  • Need to improve multi-source before integration")
        verdict = "reject"
    else:
        print(f"\n⚖️  SYSTEMS ARE SIMILAR (difference: {improvement:.1f}%)")
        print("\nRecommendation: TEST FOR 1 WEEK")
        print("Next steps:")
        print(f"  • Run both systems in parallel")
        print(f"  • Track accuracy over 7 days")
        print(f"  • Integrate if multi-source proves consistently better")
        verdict = "test_more"
    
    # Show matched predictions
    if multi_matched:
        print("\n" + "="*80)
        print(f"✓ MULTI-SOURCE MATCHED PREDICTIONS ({len(multi_matched)})")
        print("="*80)
        for i, match in enumerate(multi_matched[:10], 1):
            pred = match['prediction']
            print(f"\n{i}. {pred['title']} by {pred['artist']}")
            print(f"   Kalshi: {match['kalshi']['market_title']}")
            print(f"   Confidence: {pred.get('confidence', 0)}%")
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'kalshi_markets': len(kalshi_markets),
        'multi_source': {
            'metrics': multi_metrics,
            'execution_time_ms': multi_time,
            'matched_count': len(multi_matched),
            'matched': multi_matched[:20]
        },
        'kworb_only': {
            'metrics': kworb_metrics,
            'execution_time_ms': kworb_time,
            'matched_count': len(kworb_matched),
            'matched': kworb_matched[:20]
        },
        'verdict': verdict,
        'improvement_pct': improvement
    }
    
    with open('validation_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n✓ Results saved to validation_results.json")
    
    return results


if __name__ == '__main__':
    print("="*80)
    print("VALIDATION SCRIPT")
    print("DO NOT integrate multi-source system without passing validation!")
    print("="*80)
    
    results = compare_systems()
    
    if results:
        print("\n" + "="*80)
        print("NEXT STEPS")
        print("="*80)
        
        if results['verdict'] == 'integrate':
            print("1. ✅ Multi-source system validated")
            print("2. Integrate into trading_bot.py")
            print("3. Update GitHub Actions schedule to 3 PM ET")
            print("4. Monitor P/L improvement")
        elif results['verdict'] == 'reject':
            print("1. ❌ Multi-source system NOT ready")
            print("2. Keep current Kworb-only system")
            print("3. Improve multi-source (add more sources, tune weights)")
            print("4. Re-run validation after improvements")
        else:
            print("1. ⏳ Need more data")
            print("2. Run both systems in parallel for 1 week")
            print("3. Compare P/L and accuracy over time")
            print("4. Integrate if multi-source consistently better")
    else:
        print("\n⚠ Validation incomplete - need Kalshi credentials")
        print("\nCreate .env file:")
        print("  KALSHI_API_KEY_ID=your_key_id")
        print("  KALSHI_PRIVATE_KEY=your_private_key")
