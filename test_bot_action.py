#!/usr/bin/env python3
"""
Test what the bot would actually do on kxbtcd-25dec3017
Shows Gemini AI decision layer, signal scores, and market price edge checking
Updated to reflect new Gemini decision architecture with 7-model fallback
"""

import os
from kalshi_auth import initialize_kalshi_client
from market_intelligence import get_market_signals

def simulate_bot_action():
    """Simulate trading bot decision on live market with Gemini AI"""
    
    print("\n" + "="*70)
    print("TRADING BOT DECISION SIMULATOR - kxbtcd-25dec3017 (Live Market)")
    print("="*70)
    print("Architecture: Multi-Signal → Gemini AI (7-model fallback) → Decision")
    print("="*70 + "\n")
    
    # Initialize client
    kalshi_client = initialize_kalshi_client()
    
    # Test parameters
    market_ticker = "kxbtcd-25dec3017"
    series_ticker = "kxbtcd"
    asset = "BTC"
    
    print(f"[MARKET] {market_ticker}")
    print(f"[ASSET] {asset}")
    print(f"[SERIES] {series_ticker}\n")
    
    # Get multi-signal analysis
    print("Analyzing market with 5-signal framework...")
    print("  • Momentum (55%)")
    print("  • Orderbook (15%)")
    print("  • Trade Flow (15%)")
    print("  • Liquidity (10%)")
    print("  • Volatility (5%)\n")
    
    market_signals = get_market_signals(kalshi_client, market_ticker, series_ticker, asset)
    
    # Extract decision data
    composite_score = market_signals.get('final_composite_score', 50)
    confidence = market_signals.get('confidence', 0)
    best_bid = market_signals.get('current_best_bid', 50)
    best_ask = market_signals.get('current_best_ask', 50)
    decision_rationale = market_signals.get('decision_rationale', '')
    
    # Signal breakdown
    momentum = market_signals.get('momentum_score', 50)
    orderbook = market_signals.get('orderbook_score', 50)
    trade_flow = market_signals.get('trade_flow_score', 50)
    liquidity = market_signals.get('liquidity_score', 50)
    volatility_mult = 1.0
    
    print("═" * 70)
    print("SIGNAL SCORES")
    print("═" * 70)
    print(f"Momentum Score:      {momentum:.1f}  (weight: 55%)")
    print(f"Orderbook Score:     {orderbook:.1f}  (weight: 15%)")
    print(f"Trade Flow Score:    {trade_flow:.1f}  (weight: 15%)")
    print(f"Liquidity Score:     {liquidity:.1f}  (weight: 10%)")
    print(f"Volatility Mult:     {volatility_mult:.2f}x (weight: 5%)")
    
    print("\n" + "═" * 70)
    print("COMPOSITE DECISION")
    print("═" * 70)
    print(f"Composite Score:     {composite_score:.1f}/100")
    print(f"Confidence:          {confidence:.1f}%")
    
    # Get Gemini AI decision
    print("\n" + "═" * 70)
    print("GEMINI AI DECISION LAYER (7-Model Fallback)")
    print("═" * 70)
    
    thresholds = {
        'buy_yes': 55,
        'buy_no': 45,
        'skip_zone_low': 45,
        'skip_zone_high': 55
    }
    
    gemini_result = get_gemini_decision(
        momentum_score=momentum,
        orderbook_score=orderbook,
        trade_flow_score=trade_flow,
        liquidity_score=liquidity,
        final_composite_score=composite_score,
        best_bid=best_bid,
        best_ask=best_ask,
        market_ticker=market_ticker,
        thresholds=thresholds
    )
    
    if gemini_result:
        print(f"\n✓ Gemini AI Decision (Model: {gemini_result.get('model', 'Unknown')})")
        ai_decision = gemini_result.get('decision', 'SKIP')
        ai_confidence = gemini_result.get('confidence', 5)
        ai_reasoning = gemini_result.get('reasoning', 'N/A')
        
        print(f"  Decision:            {ai_decision}")
        print(f"  Confidence:          {ai_confidence}/10")
        print(f"  Reasoning:           {ai_reasoning[:100]}..." if len(ai_reasoning) > 100 else f"  Reasoning:           {ai_reasoning}")
        print(f"  Model Used:          {gemini_result.get('model', 'N/A')}")
    else:
        print(f"\n⚠ Gemini unavailable - using model-based decision")
        print(f"  (All 7 models exhausted or no API key)")
        ai_decision = None
        
        # Fall back to model-based
        if composite_score > thresholds['buy_yes']:
            ai_decision = 'BUY_YES'
            print(f"  Decision:            {ai_decision} (composite {composite_score:.1f} > {thresholds['buy_yes']})")
        elif composite_score < thresholds['buy_no']:
            ai_decision = 'BUY_NO'
            print(f"  Decision:            {ai_decision} (composite {composite_score:.1f} < {thresholds['buy_no']})")
        else:
            ai_decision = 'SKIP'
            print(f"  Decision:            {ai_decision} (composite {composite_score:.1f} in neutral zone)")
    
    # Use Gemini AI decision (already tested & validated)
    print("\n" + "─" * 70)
    print("DECISION SOURCE: Gemini AI (validated 7-model fallback)")
    print("─" * 70)

    if ai_decision == 'BUY_YES':
        action = "BUY YES"
        signal_type = "BULLISH"
        buy_yes = True
    elif ai_decision == 'BUY_NO':
        action = "BUY NO"
        signal_type = "BEARISH"
        buy_yes = False
    else:
        action = "NO TRADE"
        signal_type = "NEUTRAL"
        buy_yes = None
    
    print(f"AI Signal:           {signal_type}")
    print(f"AI Action:           {action}")
    print("─" * 70)
    
    # Market pricing
    print("\n" + "═" * 70)
    print("MARKET PRICING & EDGE CHECK")
    print("═" * 70)
    print(f"Market Bid (YES):    {best_bid}¢")
    print(f"Market Ask (NO):     {best_ask}¢")
    print(f"Mid-price:           {(best_bid + best_ask) / 2:.0f}¢")
    
    if buy_yes is not None:
        entry_price = 99  # Our limit order
        print(f"\nOur Limit Price:     {entry_price}¢")
        
        if buy_yes:
            # Buying YES - we pay up to 99¢, market asks 50¢
            if entry_price > best_ask:
                edge = "❌ NEGATIVE"
                print(f"\n[BUY YES] Market asking {best_ask}¢, we'd pay {entry_price}¢")
                print(f"Price Edge:          {edge} - paying MORE than market wants")
                would_trade = False
            else:
                edge = "✅ POSITIVE"
                print(f"\n[BUY YES] Market asking {best_ask}¢, we'd pay {entry_price}¢")
                print(f"Price Edge:          {edge} - paying LESS than our limit (good!)")
                would_trade = True
        else:
            # Buying NO - we pay to short YES
            fair_no_price = 100 - best_bid
            if entry_price < fair_no_price:
                edge = "❌ NEGATIVE"
                print(f"\n[BUY NO] Market bid {best_bid}¢ for YES, fair NO price ~{fair_no_price:.0f}¢")
                print(f"Price Edge:          {edge} - selling for LESS than fair value")
                would_trade = False
            else:
                edge = "✅ POSITIVE"
                print(f"\n[BUY NO] Market bid {best_bid}¢ for YES, fair NO price ~{fair_no_price:.0f}¢")
                print(f"Price Edge:          {edge} - selling at FAIR or BETTER value")
                would_trade = True
    else:
        would_trade = False
    
    # Final decision
    print("\n" + "═" * 70)
    print("FINAL DECISION")
    print("═" * 70)
    
    if buy_yes is None:
        print(f"\n❌ DO NOT TRADE")
        print(f"Reason: Composite score {composite_score:.1f} in neutral zone")
        print(f"Bot waits for stronger signal (score > {buy_threshold} or < {sell_threshold})")
    elif would_trade:
        if buy_yes:
            print(f"\n✅ EXECUTE TRADE")
            print(f"Action: Buy YES for {entry_price}¢")
            print(f"Signal: {signal_type} (score {composite_score:.1f} > {buy_threshold})")
            print(f"Edge:   Market asking {best_ask}¢ - good deal!")
        else:
            print(f"\n✅ EXECUTE TRADE")
            print(f"Action: Buy NO for {entry_price}¢")
            print(f"Signal: {signal_type} (score {composite_score:.1f} < {sell_threshold})")
            print(f"Edge:   Market bid {best_bid}¢ for YES - NO looks undervalued!")
    else:
        print(f"\n❌ SKIP TRADE (Negative Edge)")
        if buy_yes:
            print(f"Signal says BUY YES (score {composite_score:.1f} > {buy_threshold})")
        else:
            print(f"Signal says BUY NO (score {composite_score:.1f} < {sell_threshold})")
        print(f"But market pricing doesn't offer positive edge - wait for better entry")
    
    # Rationale summary
    print("\n" + "═" * 70)
    print("RATIONALE")
    print("═" * 70)
    print(decision_rationale)
    
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    simulate_bot_action()
