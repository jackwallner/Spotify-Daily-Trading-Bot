#!/usr/bin/env python3
"""
Test Gemini API fallback chain - Verifies all models are called in correct order
and fallbacks work properly when models fail.
"""

import os
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import requests

# Add repo to path
sys.path.insert(0, str(Path(__file__).parent))

from market_intelligence import get_gemini_decision

# Test API key - use environment variable
TEST_API_KEY = os.getenv('GEMINI_API_KEY', '')

# Expected model fallback order
EXPECTED_MODELS = [
    'gemini-2.5-flash-lite',
    'gemini-2.5-flash',
    'gemini-2.0-flash-lite',
    'gemma-3-27b-it',
    'gemma-3-12b-it',
    'gemma-3-4b-it',
    'gemma-3-1b-it',
]

# Test thresholds
TEST_THRESHOLDS = {
    'buy_yes': 75,
    'buy_no': 25,
    'skip_zone_low': 40,
    'skip_zone_high': 60
}

def create_success_response(decision="BUY_YES", confidence=8):
    """Create a valid Gemini API response"""
    return {
        'candidates': [{
            'content': {
                'parts': [{
                    'text': f"""DECISION: {decision}
CONFIDENCE: {confidence}
REASONING: This is a test response showing all signals aligned for {decision.lower()}."""
                }]
            }
        }]
    }

def test_successful_first_model():
    """Test that first model (gemini-2.5-flash-lite) succeeds"""
    print("\n" + "="*70)
    print("TEST 1: First Model Succeeds (gemini-2.5-flash-lite)")
    print("="*70)
    
    with patch.dict(os.environ, {'GEMINI_API_KEY': TEST_API_KEY}):
        with patch('requests.post') as mock_post:
            mock_post.return_value.json.return_value = create_success_response("BUY_YES", 9)
            mock_post.return_value.raise_for_status = MagicMock()
            
            result = get_gemini_decision(
                momentum_score=80,
                orderbook_score=75,
                trade_flow_score=70,
                liquidity_score=65,
                final_composite_score=75,
                best_bid=5000,
                best_ask=5010,
                market_ticker="KXBTCD-TEST",
                thresholds=TEST_THRESHOLDS
            )
            
            # Check that only 1 call was made (to first model)
            assert mock_post.call_count == 1, f"Expected 1 call, got {mock_post.call_count}"
            
            # Verify it called the first model
            call_url = mock_post.call_args[0][0]
            assert 'gemini-2.5-flash-lite' in call_url, f"Expected first model in URL: {call_url}"
            
            # Verify result
            assert result is not None, "Result should not be None"
            assert result['decision'] == 'BUY_YES', f"Expected BUY_YES, got {result['decision']}"
            assert result['confidence'] == 9, f"Expected confidence 9, got {result['confidence']}"
            assert result['model'] == 'gemini-2.5-flash-lite', f"Expected first model, got {result['model']}"
            
            print(f"✓ First model succeeded on first attempt")
            print(f"✓ Decision: {result['decision']}")
            print(f"✓ Confidence: {result['confidence']}/10")
            print(f"✓ Model: {result['model']}")
            print(f"✓ Total API calls: {mock_post.call_count}")

def test_first_model_fails_second_succeeds():
    """Test that second model is called after first fails (429 rate limit)"""
    print("\n" + "="*70)
    print("TEST 2: First Model Rate Limited (429), Second Succeeds")
    print("="*70)
    
    with patch.dict(os.environ, {'GEMINI_API_KEY': TEST_API_KEY}):
        with patch('requests.post') as mock_post:
            # First call fails with 429 (rate limit)
            rate_limit_response = MagicMock()
            rate_limit_response.status_code = 429
            rate_limit_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=rate_limit_response)
            
            # Second call succeeds
            success_response = MagicMock()
            success_response.json.return_value = create_success_response("BUY_NO", 7)
            success_response.raise_for_status = MagicMock()
            
            mock_post.side_effect = [rate_limit_response, success_response]
            
            result = get_gemini_decision(
                momentum_score=20,
                orderbook_score=25,
                trade_flow_score=30,
                liquidity_score=35,
                final_composite_score=25,
                best_bid=5000,
                best_ask=5010,
                market_ticker="KXBTCD-TEST",
                thresholds=TEST_THRESHOLDS
            )
            
            # Check that 2 calls were made
            assert mock_post.call_count == 2, f"Expected 2 calls, got {mock_post.call_count}"
            
            # Verify it tried first, then second model
            first_url = mock_post.call_args_list[0][0][0]
            second_url = mock_post.call_args_list[1][0][0]
            assert 'gemini-2.5-flash-lite' in first_url, f"First attempt should be first model"
            assert 'gemini-2.5-flash' in second_url, f"Second attempt should be second model"
            
            # Verify result
            assert result is not None, "Result should not be None"
            assert result['decision'] == 'BUY_NO', f"Expected BUY_NO, got {result['decision']}"
            assert result['model'] == 'gemini-2.5-flash', f"Expected second model, got {result['model']}"
            
            print(f"✓ First model failed with 429 (rate limit)")
            print(f"✓ Second model succeeded on fallback")
            print(f"✓ Decision: {result['decision']}")
            print(f"✓ Model: {result['model']}")
            print(f"✓ Total API calls: {mock_post.call_count}")

def test_multiple_fallbacks():
    """Test that multiple models are tried before one succeeds"""
    print("\n" + "="*70)
    print("TEST 3: First 3 Models Fail (429), Fourth Succeeds")
    print("="*70)
    
    with patch.dict(os.environ, {'GEMINI_API_KEY': TEST_API_KEY}):
        with patch('requests.post') as mock_post:
            # First 3 calls fail with 429
            rate_limit_response = MagicMock()
            rate_limit_response.status_code = 429
            rate_limit_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=rate_limit_response)
            
            # 4th call succeeds
            success_response = MagicMock()
            success_response.json.return_value = create_success_response("SKIP", 6)
            success_response.raise_for_status = MagicMock()
            
            mock_post.side_effect = [rate_limit_response, rate_limit_response, rate_limit_response, success_response]
            
            result = get_gemini_decision(
                momentum_score=50,
                orderbook_score=50,
                trade_flow_score=50,
                liquidity_score=50,
                final_composite_score=50,
                best_bid=5000,
                best_ask=5010,
                market_ticker="KXBTCD-TEST",
                thresholds=TEST_THRESHOLDS
            )
            
            # Check that 4 calls were made
            assert mock_post.call_count == 4, f"Expected 4 calls, got {mock_post.call_count}"
            
            # Verify fallback order
            urls = [call[0][0] for call in mock_post.call_args_list]
            assert 'gemini-2.5-flash-lite' in urls[0], "1st attempt failed"
            assert 'gemini-2.5-flash' in urls[1], "2nd attempt failed"
            assert 'gemini-2.0-flash-lite' in urls[2], "3rd attempt failed"
            assert 'gemma-3-27b-it' in urls[3], "4th attempt succeeded"
            
            # Verify result
            assert result is not None, "Result should not be None"
            assert result['decision'] == 'SKIP', f"Expected SKIP, got {result['decision']}"
            assert result['model'] == 'gemma-3-27b-it', f"Expected gemma-3-27b-it, got {result['model']}"
            
            print(f"✓ Models 1-3 failed with 429 (rate limit)")
            print(f"✓ Model 4 (gemma-3-27b-it) succeeded on fallback")
            print(f"✓ Decision: {result['decision']}")
            print(f"✓ Model: {result['model']}")
            print(f"✓ Total API calls: {mock_post.call_count}")
            print(f"✓ Fallback chain: {' → '.join([m.split('/')[-1] for m in urls])}")

def test_all_models_fail():
    """Test that None is returned when all models fail"""
    print("\n" + "="*70)
    print("TEST 4: All Models Fail (All 7 Models Exhausted)")
    print("="*70)
    
    with patch.dict(os.environ, {'GEMINI_API_KEY': TEST_API_KEY}):
        with patch('requests.post') as mock_post:
            # All calls fail with 429
            rate_limit_response = MagicMock()
            rate_limit_response.status_code = 429
            rate_limit_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=rate_limit_response)
            
            mock_post.side_effect = rate_limit_response
            
            result = get_gemini_decision(
                momentum_score=80,
                orderbook_score=75,
                trade_flow_score=70,
                liquidity_score=65,
                final_composite_score=75,
                best_bid=5000,
                best_ask=5010,
                market_ticker="KXBTCD-TEST",
                thresholds=TEST_THRESHOLDS
            )
            
            # Check that all 7 models were tried
            assert mock_post.call_count == 7, f"Expected 7 calls, got {mock_post.call_count}"
            
            # Verify result is None (triggers model-based fallback)
            assert result is None, f"Result should be None when all models fail, got {result}"
            
            print(f"✓ All 7 models failed with 429")
            print(f"✓ Returned None (triggers model-based fallback)")
            print(f"✓ Total API calls: {mock_post.call_count}")
            print(f"✓ Models tried: {', '.join(EXPECTED_MODELS)}")

def test_no_api_key():
    """Test that None is returned when API key is missing"""
    print("\n" + "="*70)
    print("TEST 5: No API Key Present")
    print("="*70)
    
    with patch.dict(os.environ, {}, clear=True):
        result = get_gemini_decision(
            momentum_score=80,
            orderbook_score=75,
            trade_flow_score=70,
            liquidity_score=65,
            final_composite_score=75,
            best_bid=5000,
            best_ask=5010,
            market_ticker="KXBTCD-TEST",
            thresholds=TEST_THRESHOLDS
        )
        
        # Verify result is None
        assert result is None, f"Result should be None when API key missing, got {result}"
        print(f"✓ No API key provided")
        print(f"✓ Returned None (triggers model-based fallback)")

def test_with_real_api():
    """Test with actual Gemini API (if key is valid)"""
    print("\n" + "="*70)
    print("TEST 6: Real API Test (Using AIzaSyAJt... key)")
    print("="*70)
    
    # Set environment variable for real test
    os.environ['GEMINI_API_KEY'] = TEST_API_KEY
    
    try:
        result = get_gemini_decision(
            momentum_score=80,
            orderbook_score=75,
            trade_flow_score=70,
            liquidity_score=65,
            final_composite_score=75,
            best_bid=5000,
            best_ask=5010,
            market_ticker="KXBTCD-TEST",
            thresholds=TEST_THRESHOLDS
        )
        
        if result:
            print(f"✓ Real API call succeeded!")
            print(f"✓ Decision: {result['decision']}")
            print(f"✓ Confidence: {result['confidence']}/10")
            print(f"✓ Model: {result['model']}")
            print(f"✓ Reasoning: {result['reasoning'][:100]}...")
        else:
            print(f"⚠ Real API call returned None (all models failed)")
            print(f"  This might indicate API issues or exhausted rate limits")
            
    except Exception as e:
        print(f"✗ Real API call failed: {type(e).__name__}: {e}")

if __name__ == "__main__":
    print("\n" + "="*70)
    print("GEMINI FALLBACK CHAIN TEST SUITE")
    print("="*70)
    print(f"Testing {len(EXPECTED_MODELS)} model fallback chain:")
    for i, model in enumerate(EXPECTED_MODELS, 1):
        print(f"  {i}. {model}")
    
    try:
        # Run unit tests
        test_successful_first_model()
        test_first_model_fails_second_succeeds()
        test_multiple_fallbacks()
        test_all_models_fail()
        test_no_api_key()
        
        # Run real API test
        test_with_real_api()
        
        print("\n" + "="*70)
        print("ALL TESTS COMPLETED")
        print("="*70)
        print("\n✓ Fallback chain is working correctly!")
        print("✓ All models will be tried in proper order")
        print("✓ Returns None when all models exhausted (triggers model-based decision)")
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
