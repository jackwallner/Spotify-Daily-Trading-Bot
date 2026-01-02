#!/usr/bin/env python3
"""
Test script to verify market_intelligence API calls against real Kalshi market
Tests the newly corrected API method names and parameters
"""

import sys
import logging
from datetime import datetime, timezone

# Add repo root to path for local script execution
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from kalshi_auth import initialize_kalshi_client
from market_intelligence import get_market_signals

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

def test_api_calls():
    """Test market_intelligence functions with real market data"""
    
    print("\n" + "="*80)
    print("TESTING KALSHI API CALLS - market_intelligence.py")
    print("="*80 + "\n")
    
    # Market parameters
    market_ticker = "kxbtcd-25dec3017"
    asset = "BTC"
    
    # Extract series_ticker from market_ticker
    # Pattern: SERIES-IDENTIFIER
    series_parts = market_ticker.split('-')
    if len(series_parts) >= 2:
        series_ticker = '-'.join(series_parts[:-1])
    else:
        series_ticker = market_ticker
    
    print(f"[TEST PARAMS]")
    print(f"  Market Ticker: {market_ticker}")
    print(f"  Series Ticker: {series_ticker}")
    print(f"  Asset: {asset}")
    print(f"\n{'='*80}\n")
    
    try:
        # Initialize Kalshi client
        print("[STEP 1] Initializing Kalshi client...")
        kalshi_client = initialize_kalshi_client()
        print("✅ Client initialized\n")
        
        # Call get_market_signals
        print("[STEP 2] Calling get_market_signals()...")
        print(f"  Parameters: client, ticker='{market_ticker}', series_ticker='{series_ticker}', asset='{asset}'")
        
        market_signals = get_market_signals(
            kalshi_client,
            market_ticker,
            series_ticker,
            asset
        )
        
        print("\n✅ get_market_signals() completed successfully\n")
        
        # Display results
        print("[RESULTS]")
        print(f"\n  Composite Score:     {market_signals.get('final_composite_score', 'N/A'):.1f}")
        print(f"  Confidence:          {market_signals.get('confidence', 'N/A'):.1f}%")
        print(f"\n  Signal Scores:")
        print(f"    • Momentum:        {market_signals.get('momentum_score', 'N/A'):.1f}")
        print(f"    • Orderbook:       {market_signals.get('orderbook_score', 'N/A'):.1f}")
        print(f"    • Trade Flow:      {market_signals.get('trade_flow_score', 'N/A'):.1f}")
        print(f"    • Liquidity:       {market_signals.get('liquidity_score', 'N/A'):.1f}")
        print(f"    • Volatility Mult: {market_signals.get('volatility_multiplier', 'N/A'):.2f}x")
        
        print(f"\n  Market Pricing:")
        print(f"    • Best Bid (YES):  {market_signals.get('current_best_bid', 'N/A')} cents")
        print(f"    • Best Ask (NO):   {market_signals.get('current_best_ask', 'N/A')} cents")
        mid = (market_signals.get('current_best_bid', 50) + market_signals.get('current_best_ask', 50)) / 2
        print(f"    • Mid-price:       {mid:.0f} cents")
        
        print(f"\n  Decision:")
        print(f"    • Rationale: {market_signals.get('decision_rationale', 'N/A')}")
        
        print(f"\n{'='*80}")
        print("✅ ALL API CALLS SUCCESSFUL")
        print(f"{'='*80}\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print(f"\n{'='*80}")
        print("❌ API CALL FAILED")
        print(f"{'='*80}\n")
        
        import traceback
        traceback.print_exc()
        
        return False

if __name__ == "__main__":
    success = test_api_calls()
    sys.exit(0 if success else 1)
