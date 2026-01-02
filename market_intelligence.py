#!/usr/bin/env python3
"""
Market Intelligence Module - Multi-Signal Trading Framework

UPGRADED VERSION - Now integrates Smart Signals for superior decision making:
1. Distance-to-Strike Analysis (most important for hourly markets)
2. Time-to-Expiry Decay (critical for binary options)
3. BTC Price Momentum (actual BTC movement, not market candlesticks)
4. Market Wisdom (respects market consensus when strong)
5. Edge Calculator (only trades positive expected value)
6. Volatility Regime Detection

Previous version had 48.4% accuracy (worse than coin flip).
This version implements proven edge-based trading.
"""

import json
import os
import math
import time
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
import re

# Import smart signals module
try:
    from smart_signals import (
        get_smart_signals,
        get_btc_price,
        calculate_distance_to_strike,
        calculate_time_to_expiry,
        calculate_btc_momentum,
        calculate_market_wisdom,
        calculate_volatility_regime,
        calculate_expected_edge
    )
    SMART_SIGNALS_AVAILABLE = True
except ImportError as e:
    SMART_SIGNALS_AVAILABLE = False
    print(f"Warning: smart_signals module not available: {e}")

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Default model weights and thresholds
DEFAULT_WEIGHTS = {
    "momentum": 0.55,
    "orderbook": 0.15,
    "trade_flow": 0.15,
    "liquidity": 0.10,
    "volatility": 0.05
}

DEFAULT_THRESHOLDS = {
    "buy_yes": 55,
    "buy_no": 45,
    "skip_zone_low": 45,
    "skip_zone_high": 55
}


def extract_ai_performance_insights():
    """
    Read the latest AI Performance Insights from cache.
    These are generated fresh at the start of each run by model_tuner.py.
    
    Returns:
        dict with 'analysis', 'key_insights', 'recommendations' or None if not found
    """
    try:
        cache_path = Path(__file__).parent / "ai_insights_cache.json"
        
        if not cache_path.exists():
            logger.debug("AI insights cache not found - may be first run")
            return None
        
        with open(cache_path, 'r') as f:
            insights = json.load(f)
        
        # Validate it has the expected fields
        if insights.get('analysis') or insights.get('key_insights') or insights.get('recommendations'):
            logger.info("[AI INSIGHTS] Loaded fresh insights from cache")
            return {
                'analysis': insights.get('analysis'),
                'key_insights': insights.get('key_insights'),
                'recommendations': insights.get('recommendations'),
                'generated_at': insights.get('generated_at')
            }
        
        return None
        
    except Exception as e:
        logger.warning(f"Error reading AI insights cache: {e}")
        return None


def extract_series_ticker(market_ticker):
    """
    Extract series_ticker from market_ticker
    Market format: KXBTCD-25DEC3012-T88749.99
    Series format: KXBTCD (everything before first date component)
    
    Args:
        market_ticker (str): Full market ticker
        
    Returns:
        str: Series ticker (e.g., 'KXBTCD' from 'KXBTCD-25DEC3012-T88749.99')
    """
    if not market_ticker:
        return 'KXBTCD'  # Default to BTC
    
    # Split by hyphen and take first part
    # Example: 'KXBTCD-25DEC3012-T88749.99' → 'KXBTCD'
    parts = market_ticker.split('-')
    if parts:
        return parts[0].upper()
    return market_ticker.upper()


def load_model_config():
    """
    Load model configuration from model_config.json
    Returns dict with weights and thresholds
    Falls back to hardcoded defaults if file doesn't exist
    """
    config_path = Path(__file__).parent / "model_config.json"
    
    try:
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                logger.debug(f"Loaded model config from {config_path}")
                return config
        else:
            logger.warning(f"model_config.json not found at {config_path}, using defaults")
            return {
                "version": 1,
                "weights": DEFAULT_WEIGHTS,
                "thresholds": DEFAULT_THRESHOLDS
            }
    except Exception as e:
        logger.error(f"Error loading model_config.json: {e}, using defaults")
        return {
            "version": 1,
            "weights": DEFAULT_WEIGHTS,
            "thresholds": DEFAULT_THRESHOLDS
        }


def get_candlestick_momentum(client, market_ticker, series_ticker=None, asset='BTC'):
    """
    Fetch 1-minute candlesticks for last 30 minutes and calculate momentum score
    API Spec: GET /series/{series_ticker}/markets/{ticker}/candlesticks
    
    Args:
        client: Kalshi client
        market_ticker: Market identifier (e.g., 'KXBTCD-25DEC3012-T88749.99')
        series_ticker: Optional series identifier. If not provided, extracted from market_ticker
        asset: Asset type for logging
    
    Returns:
        tuple: (momentum_score, data_quality) where data_quality is 0-100% confidence
               momentum_score (0-100, where 50=neutral, >50=bullish, <50=bearish)
    """
    try:
        # Auto-extract series_ticker if not provided
        if not series_ticker:
            series_ticker = extract_series_ticker(market_ticker)
        # Fetch candlesticks - use tight lookback for real-time momentum
        # 2 minutes of fastest available interval = fresh data
        # API requires timestamps in SECONDS not milliseconds
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=2)  # 2 minutes for real-time momentum
        
        print(f"[MOMENTUM] Fetching candlesticks for {market_ticker} (last 2 minutes)")
        
        # Call GetMarketCandlesticks endpoint - requires series_ticker + market_ticker
        try:
            candlesticks_response = client.get_market_candlesticks(
                series_ticker=series_ticker,
                ticker=market_ticker,
                start_ts=int(start_time.timestamp()),  # SECONDS not milliseconds
                end_ts=int(end_time.timestamp()),
                period_interval=1  # 1-minute candlesticks for fresh momentum
            )
        except (TimeoutError, ConnectionError) as e:
            logger.warning(f"⚠️ [MOMENTUM] API timeout or connection error for {market_ticker}: {e}")
            return 50.0, 0
        
        if not candlesticks_response or not hasattr(candlesticks_response, 'candlesticks'):
            logger.warning(f"⚠️ [MOMENTUM] No candlestick data for {market_ticker} - API call failed or returned None")
            return 50.0, 0  # Default to neutral with 0% confidence
        
        candles = candlesticks_response.candlesticks
        if not candles or len(candles) < 1:
            logger.warning(f"⚠️ [MOMENTUM] Insufficient candlestick data for {market_ticker} - empty response")
            return 50.0, 0  # 0% confidence - no data
        
        # With 60-min candles we may only have 1-2 candles, use what we have
        try:
            oldest_close = candles[0].close if hasattr(candles[0], 'close') else 50
            latest_close = candles[-1].close if hasattr(candles[-1], 'close') else 50
        except (AttributeError, KeyError):
            # If candle object doesn't have expected structure, default to neutral
            logger.warning(f"⚠️ [MOMENTUM] Candle structure invalid for {market_ticker}")
            return 50.0, 0
        
        if oldest_close == 0:
            logger.warning("⚠️ [MOMENTUM] Cannot calculate slope: oldest_close is 0")
            return 50.0, 0  # 0% confidence
        
        simple_slope = ((latest_close - oldest_close) / oldest_close) * 100
        slope_score = 50 + (simple_slope * 5)  # Scale slope to 0-100 range
        slope_score = max(0, min(100, slope_score))  # Clamp to 0-100
        
        # Calculate 15-candle momentum (rate of change)
        momentum_roc = 0
        if len(candles) >= 15:
            try:
                momentum_window_close = candles[-15].close if hasattr(candles[-15], 'close') else 50
                momentum_change = ((latest_close - momentum_window_close) / momentum_window_close) * 100
                momentum_roc = 50 + (momentum_change * 3)
                momentum_roc = max(0, min(100, momentum_roc))
            except (AttributeError, ZeroDivisionError):
                momentum_roc = 0
        
        # Count bullish vs bearish candles
        bullish_count = 0
        bearish_count = 0
        for candle in candles:
            try:
                open_price = candle.open if hasattr(candle, 'open') else 50
                close_price = candle.close if hasattr(candle, 'close') else 50
                
                if close_price > open_price:
                    bullish_count += 1
                else:
                    bearish_count += 1
            except (AttributeError, TypeError):
                # Skip candles with missing data
                pass
        total_candles = bullish_count + bearish_count
        if total_candles > 0:
            bullish_ratio = bullish_count / total_candles
            candle_strength_score = 50 + (bullish_ratio * 100) - 50  # Map to 0-100
        else:
            candle_strength_score = 50.0
        
        # Composite momentum score (weighted average)
        momentum_score = (slope_score * 0.4) + (momentum_roc * 0.35) + (candle_strength_score * 0.25)
        momentum_score = max(0, min(100, momentum_score))
        
        # Data quality: higher confidence with more recent data
        # 1-min data (60 candles) = 100% confidence
        # 60-min data (3+ candles) = 70% confidence
        # Less than 3 candles = 40% confidence
        data_quality = 100 if len(candles) >= 60 else (70 if len(candles) >= 3 else 40)
        
        logger.info(f"[MOMENTUM] {market_ticker}: slope={slope_score:.1f}, roc={momentum_roc:.1f}, candles={candle_strength_score:.1f} → {momentum_score:.1f}, quality={data_quality}%")
        
        return momentum_score, data_quality
        
    except Exception as e:
        logger.warning(f"Error calculating momentum for {market_ticker}: {e}")
        return 50.0, 0  # Default to neutral with 0% confidence on error


def get_orderbook_score(client, market_ticker):
    """
    Analyze orderbook health and depth
    Returns tuple of (score, best_bid, best_ask) in cents
    """
    try:
        print(f"[ORDERBOOK] Fetching orderbook for {market_ticker}")
        # get_market() returns GetMarketResponse with .market attribute
        response = client.get_market(market_ticker)
        
        if not response or not hasattr(response, 'market'):
            logger.warning(f"No market data for {market_ticker}")
            return 50.0, 50, 50
        
        market = response.market
        
        # Market object has yes_bid, yes_ask, no_bid, no_ask (in cents, integers)
        yes_bid = market.yes_bid if hasattr(market, 'yes_bid') and market.yes_bid is not None else 50
        yes_ask = market.yes_ask if hasattr(market, 'yes_ask') and market.yes_ask is not None else 50
        no_bid = market.no_bid if hasattr(market, 'no_bid') and market.no_bid is not None else 50
        no_ask = market.no_ask if hasattr(market, 'no_ask') and market.no_ask is not None else 50
        
        logger.debug(f"[ORDERBOOK] Market prices: yes_bid={yes_bid}¢, yes_ask={yes_ask}¢, no_bid={no_bid}¢, no_ask={no_ask}¢")
        
        # For market analysis use the same contract (YES):
        # best_bid = highest price someone will pay for YES
        # best_ask = lowest price someone will accept for YES
        best_bid = yes_bid
        best_ask = yes_ask
        
        # Calculate spread width
        spread_cents = abs(yes_ask - yes_bid) if yes_ask and yes_bid else 0
        spread_score = max(0, 100 - (spread_cents * 10))  # Tighter spread = higher score
        
        # Balance score (bid-ask balance)
        mid = (yes_bid + yes_ask) / 2 if yes_bid and yes_ask else 50
        bid_imbalance = abs(yes_bid - mid) / 50 if yes_bid else 0
        ask_imbalance = abs(yes_ask - mid) / 50 if yes_ask else 0
        balance_score = max(0, 100 - ((bid_imbalance + ask_imbalance) * 50))
        
        # Simple orderbook score
        orderbook_score = (spread_score * 0.6) + (balance_score * 0.4)
        orderbook_score = max(0, min(100, orderbook_score))
        
        logger.info(f"[ORDERBOOK] {market_ticker}: yes_bid={yes_bid}¢, yes_ask={yes_ask}¢, spread={spread_cents}¢, score={orderbook_score:.1f}")
        
        return orderbook_score, best_bid, best_ask
        
    except Exception as e:
        logger.warning(f"Error calculating orderbook score for {market_ticker}: {e}")
        return 50.0, 50, 50  # Return neutral score + mid-price as fallback


def get_trade_flow_score(client, market_ticker):
    """
    Fetch recent trades and calculate directionality bias
    API Spec: GET /markets/trades (with ticker query param)
    
    Returns:
        float: trade_flow_score (0-100, >50=bullish, <50=bearish)
    """
    try:
        print(f"[TRADE_FLOW] Fetching recent trades for {market_ticker}")
        
        # Fetch recent trades (last 15 minutes)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=15)
        
        trades_response = client.get_trades(
            ticker=market_ticker,
            min_ts=int(start_time.timestamp()),  # SECONDS not milliseconds
            max_ts=int(end_time.timestamp()),    # SECONDS not milliseconds
            limit=500
        )
        
        if not trades_response or not hasattr(trades_response, 'trades'):
            logger.warning(f"No trade data for {market_ticker}")
            return 50.0
        
        trades = trades_response.trades
        if not trades or len(trades) < 1:
            logger.warning(f"Insufficient trade data for {market_ticker}")
            return 50.0
        
        # Count YES vs NO trades and volumes
        yes_trades = 0
        no_trades = 0
        yes_volume = 0
        no_volume = 0
        
        for trade in trades:
            try:
                side = str(trade.side).lower() if hasattr(trade, 'side') else 'unknown'
                size = int(trade.size) if hasattr(trade, 'size') else 0
                
                if 'yes' in side or 'buy' in side or 'long' in side:
                    yes_trades += 1
                    yes_volume += size
                elif 'no' in side or 'sell' in side or 'short' in side:
                    no_trades += 1
                    no_volume += size
            except (AttributeError, ValueError):
                # Skip malformed trades
                continue
        
        total_trades = yes_trades + no_trades
        total_volume = yes_volume + no_volume
        
        if total_trades == 0:
            logger.warning(f"No valid trades found for {market_ticker}")
            return 50.0
        
        # Calculate trade flow bias
        trade_count_bias = (yes_trades / total_trades) * 100 if total_trades > 0 else 50
        
        if total_volume > 0:
            volume_bias = (yes_volume / total_volume) * 100
        else:
            volume_bias = 50.0
        
        # Composite trade flow score (favor volume over count)
        trade_flow_score = (volume_bias * 0.6) + (trade_count_bias * 0.4)
        trade_flow_score = max(0, min(100, trade_flow_score))
        
        logger.info(f"[TRADE_FLOW] {market_ticker}: trades={trade_count_bias:.1f}, volume={volume_bias:.1f} → {trade_flow_score:.1f}")
        
        return trade_flow_score
        
    except Exception as e:
        logger.warning(f"Error calculating trade flow score for {market_ticker}: {e}")
        return 50.0


def get_liquidity_score(client, market_ticker):
    """
    Calculate liquidity score from orderbook data
    API Spec: GET /markets/{ticker}/orderbook
    
    Returns:
        float: liquidity_score (0-100, higher = better liquidity)
    """
    try:
        print(f"[LIQUIDITY] Calculating liquidity for {market_ticker}")
        # Use get_market() which returns GetMarketResponse with .market attribute
        response = client.get_market(market_ticker)
        
        if not response or not hasattr(response, 'market'):
            logger.warning(f"No market data for liquidity calculation")
            return 50.0
        
        market = response.market
        
        # Market has yes_bid, yes_ask (and no_bid, no_ask but we use YES side)
        yes_bid = market.yes_bid if hasattr(market, 'yes_bid') and market.yes_bid else 50
        yes_ask = market.yes_ask if hasattr(market, 'yes_ask') and market.yes_ask else 50
        
        # Spread width (tighter = better)
        spread = abs(yes_ask - yes_bid) if yes_ask and yes_bid else 0
        spread_score = max(0, 100 - (spread * 5))  # Smaller spread = higher liquidity
        
        # For simple liquidity, we use bid-ask spread as proxy
        # In real market, we'd have order depth, but SDK doesn't expose that
        # So we estimate: narrow spread = good liquidity
        liquidity_score = max(50, spread_score)  # At least 50 for any response
        
        logger.info(f"[LIQUIDITY] {market_ticker}: spread={spread}¢, score={liquidity_score:.1f}")
        
        return liquidity_score
        
    except Exception as e:
        logger.warning(f"Error calculating liquidity score for {market_ticker}: {e}")
        return 50.0


def get_volatility_adjustment(client, market_ticker, series_ticker=None):
    """
    Calculate volatility adjustment multiplier from candlestick data
    Uses Average True Range (ATR) for volatility measurement
    API Spec: GET /series/{series_ticker}/markets/{ticker}/candlesticks
    
    Args:
        client: Kalshi client
        market_ticker: Market identifier
        series_ticker: Optional series identifier. If not provided, extracted from market_ticker
    
    Returns:
        float: volatility_multiplier (0.7 if extreme, 1.0 if normal)
    """
    try:
        # Auto-extract series_ticker if not provided
        if not series_ticker:
            series_ticker = extract_series_ticker(market_ticker)
        print(f"[VOLATILITY] Calculating volatility adjustment for {market_ticker}")
        
        # Fetch candlesticks for volatility - tight lookback for active markets
        # 1 hour of 1-min data = 60 candles (enough for volatility measurement)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)
        
        candlesticks_response = client.get_market_candlesticks(
            series_ticker=series_ticker,
            ticker=market_ticker,
            start_ts=int(start_time.timestamp()),  # SECONDS
            end_ts=int(end_time.timestamp()),
            period_interval=60  # 1-minute for volatility precision
        )
        
        if not candlesticks_response or not hasattr(candlesticks_response, 'candlesticks'):
            logger.warning(f"No candlestick data for volatility calculation")
            return 1.0
        
        candles = candlesticks_response.candlesticks
        if len(candles) < 5:
            logger.warning(f"Insufficient candles for volatility calculation")
            return 1.0
        
        # Calculate True Range for each candle
        true_ranges = []
        for i, candle in enumerate(candles):
            try:
                high = candle.high if hasattr(candle, 'high') else 50
                low = candle.low if hasattr(candle, 'low') else 50
                close = candle.close if hasattr(candle, 'close') else 50
                
                if i > 0:
                    prev_close = candles[i-1].close if hasattr(candles[i-1], 'close') else 50
                else:
                    prev_close = close
                
                # True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)
            except (AttributeError, TypeError):
                continue
        
        if not true_ranges:
            return 1.0
        
        # Calculate ATR (Average True Range)
        atr = sum(true_ranges) / len(true_ranges)
        
        # Calculate volatility percentile (simplified: compare to average)
        avg_range = sum(true_ranges) / len(true_ranges)
        volatility_level = (atr / avg_range) * 100 if avg_range > 0 else 100
        
        # If volatility is extreme (>120% average), apply dampening
        if volatility_level > 120:
            volatility_multiplier = 0.8  # Dampening factor
            logger.info(f"[VOLATILITY] {market_ticker}: ATR={atr:.2f}, Level={volatility_level:.1f}% → HIGH, multiplier=0.8")
        else:
            volatility_multiplier = 1.0  # Normal
            logger.info(f"[VOLATILITY] {market_ticker}: ATR={atr:.2f}, Level={volatility_level:.1f}% → NORMAL, multiplier=1.0")
        
        return volatility_multiplier
        
    except Exception as e:
        logger.warning(f"Error calculating volatility adjustment for {market_ticker}: {e}")
        return 1.0  # Default to normal on error


def get_smart_gemini_decision(smart_signals: dict, market_ticker: str, thresholds: dict):
    """
    UPGRADED Gemini decision function using smart signals.
    
    This version provides Gemini with:
    1. Distance to strike (most important factor)
    2. Time to expiry (critical for binary options)
    3. BTC price momentum (actual price movement)
    4. Market wisdom (consensus strength)
    5. Calculated edge for both sides
    6. Volatility regime
    
    Args:
        smart_signals: Output from get_smart_signals()
        market_ticker: Market identifier
        thresholds: Decision thresholds
    
    Returns:
        dict with 'decision', 'reasoning', 'confidence', 'model'
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.debug("GEMINI_API_KEY not found - using smart signals recommendation directly")
        return {
            'decision': smart_signals.get('recommendation', 'SKIP'),
            'reasoning': smart_signals.get('reason', 'No API key - using edge calculation'),
            'confidence': int(smart_signals.get('confidence', 50) / 10),
            'model': 'SMART_SIGNALS_ONLY'
        }
    
    try:
        print(f"[GEMINI] Consulting AI with smart signals for {market_ticker}")
        
        # Extract key data from smart signals
        distance = smart_signals.get('distance', {})
        time_decay = smart_signals.get('time_decay', {})
        btc_momentum = smart_signals.get('btc_momentum', {})
        btc_velocity = smart_signals.get('btc_velocity', {})  # NEW: Short-term velocity
        velocity_adjustment = smart_signals.get('velocity_adjustment', 0)
        market_wisdom = smart_signals.get('market_wisdom', {})
        volatility = smart_signals.get('volatility', {})
        yes_edge = smart_signals.get('yes_edge', {})
        no_edge = smart_signals.get('no_edge', {})
        
        # Build comprehensive prompt
        prompt = f"""You are an expert quantitative trading AI for Kalshi hourly BTC prediction markets.

CRITICAL CONTEXT: This is a binary options market. At expiry, if BTC price is ABOVE the strike price, YES wins $1. If BELOW, NO wins $1.

=== MARKET STATE ===
Market: {market_ticker}
Strike Price: ${distance.get('strike_price', 0):,.2f}
Current BTC: ${distance.get('current_price', 0):,.2f}

=== DISTANCE TO STRIKE (Most Important Signal) ===
Distance: ${distance.get('distance_dollars', 0):,.0f} ({distance.get('direction', 'unknown')})
Zone: {distance.get('zone', 'unknown')} 
- critical (<$100): Too close to call, avoid trading
- moderate ($100-250): Slight edge possible
- comfortable ($250-500): Clear direction
- safe (>$500): Very clear direction

=== TIME TO EXPIRY ===
Minutes Remaining: {time_decay.get('minutes_remaining', 60):.1f}
Phase: {time_decay.get('phase', 'unknown')}
- critical (<5 min): Trust current position only
- urgent (5-15 min): Weight current position heavily
- normal (15-30 min): Balance position and momentum
- early (>30 min): Momentum matters more

=== BTC PRICE MOMENTUM (Last 15 min) ===
Direction: {btc_momentum.get('direction', 'neutral')}
Strength: {btc_momentum.get('strength', 50):.1f}/100
Price Change: ${btc_momentum.get('raw_change', 0):+,.0f}
Trend Consistency: {btc_momentum.get('trend_consistency', 0)*100:.0f}%

=== BTC VELOCITY (PREDICTIVE EDGE - Binance data, faster than BRTI) ===
Current Rate: ${btc_velocity.get('velocity', 0):+,.0f}/minute
Acceleration: {btc_velocity.get('acceleration', 'stable')}
Projected Price (60s): ${btc_velocity.get('projected_60s', 0):,.0f}
Confidence Adjustment: {velocity_adjustment:+}%
NOTE: Binance leads BRTI by 200-500ms. If price is accelerating toward strike, outcome may flip!

=== MARKET WISDOM (What the market thinks) ===
Consensus: {market_wisdom.get('consensus', 'neutral')}
Implied Probability (YES): {market_wisdom.get('implied_probability', 50):.0f}%
Yes Bid: {market_wisdom.get('yes_bid', 50)}¢ | Yes Ask: {market_wisdom.get('yes_ask', 50)}¢
CRITICAL: When market has strong consensus (>70% or <30%), it's usually RIGHT. Don't bet against it.

=== VOLATILITY REGIME ===
Regime: {volatility.get('regime', 'normal')}
Hourly Range: ${volatility.get('hourly_range', 500):,.0f}
- Low vol: Can trade with less edge
- High vol: Need more edge, outcomes more uncertain

=== CALCULATED EDGE ===
YES Edge: {yes_edge.get('expected_edge', 0):+.1f}% (Win Prob: {yes_edge.get('win_probability', 0.5)*100:.0f}%, Entry: {yes_edge.get('entry_price', 50)}¢)
NO Edge: {no_edge.get('expected_edge', 0):+.1f}% (Win Prob: {no_edge.get('win_probability', 0.5)*100:.0f}%, Entry: {no_edge.get('entry_price', 50)}¢)
Minimum Edge Required: {max(yes_edge.get('min_edge_required', 5), no_edge.get('min_edge_required', 5)):.1f}%

=== PRE-COMPUTED RECOMMENDATION ===
Smart Signals Says: {smart_signals.get('recommendation', 'SKIP')}
Reason: {smart_signals.get('reason', 'No reason given')}
Confidence: {smart_signals.get('confidence', 0):.0f}%

=== YOUR DECISION RULES ===
1. ONLY trade when expected edge > minimum required edge
2. NEVER bet against strong market consensus (>70% or <30% implied prob)
3. PAY ATTENTION TO VELOCITY - if price is accelerating toward strike, be cautious
3. SKIP when distance is critical (<$100) AND market is neutral
4. In last 5 minutes, only trust current BTC position vs strike
5. Higher volatility = need higher edge to trade

=== YOUR TASK ===
Evaluate the smart signals recommendation. You may:
- AGREE with it (most likely if edge calculation is positive)
- OVERRIDE to SKIP if you see risks the calculation missed
- OVERRIDE to trade if you see an edge the calculation missed

DECISION FORMAT:
DECISION: [BUY_YES | BUY_NO | SKIP]
CONFIDENCE: [1-10] (10 = extremely confident)
REASONING: [1-2 sentences explaining your decision]
"""
        
        # Model fallback list ordered by rate limits (RPM):
        # gemini-2.5-flash-lite (7 RPM), gemini-2.5-flash (3 RPM),
        # gemma-3-27b (4 RPM), gemma-3-4b (2 RPM), gemma-3-12b (1 RPM), gemma-3-1b
        models = [
            'gemini-2.5-flash-lite',  # 7 RPM
            'gemini-2.5-flash',       # 3 RPM
            'gemma-3-27b-it',         # 4 RPM
            'gemma-3-4b-it',          # 2 RPM
            'gemma-3-12b-it',         # 1 RPM
            'gemma-3-1b-it',          # Last resort
        ]
        
        for model_idx, model in enumerate(models, 1):
            try:
                print(f"   Attempting {model_idx}/{len(models)}: {model}")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                data = {
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }]
                }
                
                response = requests.post(url, json=data, headers=headers, timeout=15)
                response.raise_for_status()
                
                result = response.json()
                if 'candidates' in result and len(result['candidates']) > 0:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    
                    # Parse response
                    decision = smart_signals.get('recommendation', 'SKIP')  # Default to smart signals
                    confidence = 5
                    reasoning = text.strip()
                    
                    # Extract decision
                    if 'DECISION:' in text:
                        decision_part = text.split('DECISION:')[1].split('\n')[0].strip().upper()
                        if 'BUY_YES' in decision_part or ('YES' in decision_part and 'NO' not in decision_part):
                            decision = 'BUY_YES'
                        elif 'BUY_NO' in decision_part:
                            decision = 'BUY_NO'
                        elif 'SKIP' in decision_part:
                            decision = 'SKIP'
                    
                    # Extract confidence
                    if 'CONFIDENCE:' in text:
                        conf_part = text.split('CONFIDENCE:')[1].split('\n')[0].strip()
                        try:
                            # Extract just the number
                            import re
                            conf_match = re.search(r'(\d+)', conf_part)
                            if conf_match:
                                conf_val = int(conf_match.group(1))
                                confidence = max(1, min(10, conf_val))
                        except:
                            confidence = 5
                    
                    # Extract reasoning
                    if 'REASONING:' in text:
                        reasoning = text.split('REASONING:')[1].strip()
                        # Take only first paragraph
                        reasoning = reasoning.split('\n')[0].strip()
                    
                    print(f"   ✓ {model} succeeded: {decision} (confidence: {confidence})")
                    
                    return {
                        'decision': decision,
                        'reasoning': reasoning[:500],  # Limit length
                        'confidence': confidence,
                        'model': model,
                        'smart_signals_rec': smart_signals.get('recommendation'),
                        'agreed_with_signals': decision == smart_signals.get('recommendation')
                    }
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logger.debug(f"Rate limit (429) on {model}, trying next...")
                    time.sleep(0.5)
                elif e.response.status_code == 401:
                    logger.warning(f"Authentication failed (401)")
                    break
                else:
                    logger.debug(f"HTTP {e.response.status_code} on {model}")
            except requests.exceptions.Timeout:
                logger.debug(f"Timeout on {model}")
            except Exception as e:
                logger.debug(f"Error on {model}: {e}")
        
        # Fallback: use smart signals recommendation directly
        logger.warning("All Gemini models failed - using smart signals directly")
        return {
            'decision': smart_signals.get('recommendation', 'SKIP'),
            'reasoning': smart_signals.get('reason', 'Gemini unavailable, using edge calculation'),
            'confidence': int(smart_signals.get('confidence', 50) / 10),
            'model': 'SMART_SIGNALS_FALLBACK'
        }
        
    except Exception as e:
        logger.error(f"Error in get_smart_gemini_decision: {e}")
        return {
            'decision': smart_signals.get('recommendation', 'SKIP'),
            'reasoning': f'Error: {e}',
            'confidence': 3,
            'model': 'ERROR_FALLBACK'
        }


def get_gemini_decision(momentum_score, orderbook_score, trade_flow_score, liquidity_score, 
                       final_composite_score, best_bid, best_ask, market_ticker, thresholds):
    """
    Consult Gemini AI to make final buy/skip decision based on signal analysis.
    Uses model-fallback pattern: try 7 models in order of preference.
    On complete failure, returns None to trigger model-based fallback decision.
    
    Args:
        momentum_score: 0-100 momentum signal
        orderbook_score: 0-100 orderbook signal
        trade_flow_score: 0-100 trade flow signal
        liquidity_score: 0-100 liquidity signal
        final_composite_score: 0-100 weighted composite (after volatility adjustment)
        best_bid: Current YES best bid in cents
        best_ask: Current YES best ask in cents
        market_ticker: Market identifier for logging
        thresholds: Dict with buy_yes, buy_no, skip_zone_low, skip_zone_high
    
    Returns:
        dict with 'decision' (BUY_YES/BUY_NO/SKIP), 'reasoning', 'confidence' (1-10), 'model'
        OR None if Gemini unavailable or all models fail (triggers model-based fallback)
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print(f"[GEMINI] DEBUG: GEMINI_API_KEY not found in environment. os.getenv('GEMINI_API_KEY') = {api_key}")
        print(f"[GEMINI] DEBUG: All env vars with 'GEMINI': {[k for k in os.environ.keys() if 'GEMINI' in k.upper()]}")
        logger.debug("GEMINI_API_KEY not found - will use model decision")
        return None
    
    try:
        print(f"[GEMINI] Consulting Gemini for {market_ticker}")
        
        # Extract AI Performance Insights from index.html
        ai_insights = extract_ai_performance_insights()
        insights_context = ""
        if ai_insights:
            print(f"[GEMINI] Incorporating prior performance insights into decision")
            insights_context = f"""
AI PERFORMANCE INSIGHTS FROM PRIOR RUNS:
Analysis: {ai_insights.get('analysis', 'N/A')[:300]}...

Key Insights: {ai_insights.get('key_insights', 'N/A')[:300]}...

Current Recommendations: {ai_insights.get('recommendations', 'N/A')[:300]}...

Use these insights to inform your decision, especially regarding:
- Whether the current score aligns with historical patterns
- Any suggested adjustments to thresholds or signal weighting
- How to handle conservative vs aggressive trading strategies
"""
        
        # Build context from signal analysis
        prompt = f"""You are a trading decision AI for Kalshi prediction markets. Analyze this market signal analysis and recommend whether to execute a trade.

MARKET: {market_ticker}
CURRENT PRICES: Best Bid (YES) = {best_bid}¢, Best Ask (YES) = {best_ask}¢

PRICE ATTRACTIVENESS ANALYSIS:
- YES at {best_ask}¢ (ask) is {"VERY CHEAP" if best_ask <= 30 else "CHEAP" if best_ask <= 40 else "FAIR" if best_ask <= 60 else "EXPENSIVE" if best_ask <= 70 else "VERY EXPENSIVE"}
- NO at {100-best_bid}¢ (implied) is {"VERY CHEAP" if 100-best_bid <= 30 else "CHEAP" if 100-best_bid <= 40 else "FAIR" if 100-best_bid <= 60 else "EXPENSIVE" if 100-best_bid <= 70 else "VERY EXPENSIVE"}

SIGNAL ANALYSIS (0-100 scale, 50=neutral, >50=bullish, <50=bearish):
- Momentum Score: {momentum_score:.1f}
- Orderbook Score: {orderbook_score:.1f}
- Trade Flow Score: {trade_flow_score:.1f}
- Liquidity Score: {liquidity_score:.1f}
- COMPOSITE SCORE: {final_composite_score:.1f}

DECISION FRAMEWORK:
- Buy YES if Composite > {thresholds['buy_yes']} (confident bullish outlook) OR if signals are strong AND prices are very attractive
- Buy NO if Composite < {thresholds['buy_no']} (confident bearish outlook) OR if signals are weak AND NO prices are very attractive
- Skip if Composite in {thresholds['skip_zone_low']}-{thresholds['skip_zone_high']} (uncertain) - UNLESS prices are extremely attractive for your conviction
{insights_context}

DECISION REQUESTED:
Consider the combination of:
1. Signal strength (momentum, orderbook, trade flow, liquidity)
2. Price attractiveness (is this a good deal right now?)
3. Risk/reward (do the prices offer good entry points?)

Based on ALL factors, should we:
1. BUY YES (bullish conviction, signal or price driven)
2. BUY NO (bearish conviction, signal or price driven)
3. SKIP (hold cash, wait for better opportunity)

What is your confidence (1-10) in this decision?
Briefly explain your reasoning (1-2 sentences), referencing the key factors.

Format your response as:
DECISION: [BUY_YES | BUY_NO | SKIP]
CONFIDENCE: [1-10]
REASONING: [Your explanation]
"""
        
        # Model fallback list ordered by rate limits (RPM):
        # gemini-2.5-flash-lite (7 RPM), gemini-2.5-flash (3 RPM),
        # gemma-3-27b (4 RPM), gemma-3-4b (2 RPM), gemma-3-12b (1 RPM), gemma-3-1b
        models = [
            'gemini-2.5-flash-lite',  # 7 RPM
            'gemini-2.5-flash',       # 3 RPM
            'gemma-3-27b-it',         # 4 RPM
            'gemma-3-4b-it',          # 2 RPM
            'gemma-3-12b-it',         # 1 RPM
            'gemma-3-1b-it',          # Last resort
        ]
        
        for model_idx, model in enumerate(models, 1):
            try:
                print(f"   Attempting {model_idx}/{len(models)}: {model}")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                data = {
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }]
                }
                
                response = requests.post(url, json=data, headers=headers, timeout=10)
                response.raise_for_status()
                
                result = response.json()
                if 'candidates' in result and len(result['candidates']) > 0:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    
                    # Parse response
                    decision = 'SKIP'
                    confidence = 5
                    reasoning = text.strip()
                    
                    # Extract decision
                    if 'DECISION:' in text:
                        decision_part = text.split('DECISION:')[1].split('\n')[0].strip().upper()
                        if 'BUY_YES' in decision_part or 'YES' in decision_part:
                            decision = 'BUY_YES'
                        elif 'BUY_NO' in decision_part or 'NO' in decision_part:
                            decision = 'BUY_NO'
                        else:
                            decision = 'SKIP'
                    
                    # Extract confidence
                    if 'CONFIDENCE:' in text:
                        conf_part = text.split('CONFIDENCE:')[1].split('\n')[0].strip()
                        try:
                            conf_val = int(conf_part)
                            confidence = max(1, min(10, conf_val))
                        except:
                            confidence = 5
                    
                    # Extract reasoning
                    if 'REASONING:' in text:
                        reasoning = text.split('REASONING:')[1].strip()
                    
                    if model != models[0]:
                        print(f"   ✓ Fallback {model} succeeded")
                    else:
                        print(f"   ✓ {model} succeeded")
                    
                    logger.info(f"[GEMINI] {market_ticker}: Decision={decision}, Confidence={confidence}/10, Model={model}")
                    
                    return {
                        'decision': decision,
                        'reasoning': reasoning,
                        'confidence': confidence,
                        'model': model
                    }
                else:
                    logger.debug(f"No candidates in {model} response")
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logger.debug(f"Rate limit (429) on {model}, trying next...")
                elif e.response.status_code == 401:
                    logger.warning(f"Authentication failed (401): Invalid API key?")
                    return None  # Stop trying if auth fails
                elif e.response.status_code == 404:
                    logger.debug(f"Model not found (404): {model}, trying next...")
                else:
                    logger.debug(f"HTTP {e.response.status_code} on {model}")
                    
            except requests.exceptions.Timeout:
                logger.debug(f"Timeout on {model}")
            except requests.exceptions.ConnectionError as e:
                logger.debug(f"Connection error on {model}")
            except Exception as e:
                logger.debug(f"Error on {model}: {type(e).__name__}: {e}")
        
        logger.warning(f"All {len(models)} Gemini models exhausted for {market_ticker} - using model decision")
        return None  # Fallback to model-based decision
        
    except Exception as e:
        logger.warning(f"Error in get_gemini_decision: {e}")
        return None  # Fallback to model-based decision


def get_market_signals(client, market_ticker, series_ticker=None, asset='BTC'):
    """
    MAIN FUNCTION - Calculate all market signals and composite score
    
    Auto-extracts series_ticker from market_ticker if not provided.
    Example: KXBTCD-25DEC3012-T88749.99 → series_ticker='KXBTCD'
    
    Returns:
        dict with: momentum_score, orderbook_score, trade_flow_score, liquidity_score,
                   volatility_multiplier, final_composite_score, confidence, decision_rationale,
                   current_best_bid, current_best_ask, market_price_context
    """
    try:
        # Auto-extract series_ticker if not provided
        if not series_ticker:
            series_ticker = extract_series_ticker(market_ticker)
        
        print(f"\n{'='*70}")
        print(f"[MULTI-SIGNAL ANALYSIS] Starting analysis for {market_ticker} ({asset})")
        print(f"{'='*70}")
        
        # Load configuration
        config = load_model_config()
        weights = config.get('weights', DEFAULT_WEIGHTS)
        thresholds = config.get('thresholds', DEFAULT_THRESHOLDS)
        
        # Get all signal scores (some return tuples with data quality, extract score only)
        momentum_result = get_candlestick_momentum(client, market_ticker, series_ticker, asset)
        momentum_score = momentum_result[0] if isinstance(momentum_result, tuple) else momentum_result
        
        orderbook_score, best_bid, best_ask = get_orderbook_score(client, market_ticker)
        trade_flow_score = get_trade_flow_score(client, market_ticker)
        liquidity_score = get_liquidity_score(client, market_ticker)
        volatility_multiplier = get_volatility_adjustment(client, market_ticker, series_ticker)
        
        # Calculate weighted composite score
        weighted_momentum = momentum_score * weights['momentum']
        weighted_orderbook = orderbook_score * weights['orderbook']
        weighted_trade_flow = trade_flow_score * weights['trade_flow']
        weighted_liquidity = liquidity_score * weights['liquidity']
        
        # Base composite score before volatility adjustment
        base_composite = (weighted_momentum + weighted_orderbook + 
                         weighted_trade_flow + weighted_liquidity)
        
        # Apply volatility adjustment
        final_composite_score = base_composite * volatility_multiplier
        final_composite_score = max(0, min(100, final_composite_score))
        
        # Calculate confidence (0-100) based on signal alignment
        # Higher confidence when signals agree
        scores = [momentum_score, orderbook_score, trade_flow_score, liquidity_score]
        score_mean = sum(scores) / len(scores)
        score_variance = sum([(s - score_mean) ** 2 for s in scores]) / len(scores)
        score_stdev = math.sqrt(score_variance)
        
        # Lower stdev = higher alignment = higher confidence
        alignment_factor = max(0, 100 - (score_stdev * 2))  # Scale stdev to 0-100
        confidence = alignment_factor
        
        # CHECK: Warn if signals are clustered at neutral 50 (indicates poor data quality)
        all_near_neutral = all(45 <= s <= 55 for s in scores)
        if all_near_neutral:
            print(f"⚠️ [DATA QUALITY] All signals near neutral (45-55): {scores}")
            print(f"   This suggests API calls may be failing silently or returning empty data")
            print(f"   Composite score {final_composite_score:.1f} may not be reliable")
            confidence = min(confidence, 20)  # Cap confidence when data quality is poor
        
        # CONSULT GEMINI for final decision
        print(f"\n[GEMINI DECISION]")
        gemini_result = get_gemini_decision(momentum_score, orderbook_score, trade_flow_score,
                                           liquidity_score, final_composite_score, best_bid, 
                                           best_ask, market_ticker, thresholds)
        
        # Pre-calculate signal strengths for fallback logging
        signal_strengths = {
            'momentum': momentum_score,
            'orderbook': orderbook_score,
            'trade_flow': trade_flow_score,
            'liquidity': liquidity_score
        }
        bullish_signals = sum(1 for s in signal_strengths.values() if s > 55)
        bearish_signals = sum(1 for s in signal_strengths.values() if s < 45)
        
        if bullish_signals >= 2:
            direction = "BULLISH"
        elif bearish_signals >= 2:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"
        
        if gemini_result:
            # Use Gemini decision
            gemini_decision = gemini_result['decision']
            gemini_reasoning = gemini_result['reasoning']
            gemini_confidence = gemini_result['confidence']
            gemini_model = gemini_result['model']
            print(f"  Decision: {gemini_decision}")
            print(f"  Reasoning: {gemini_reasoning}")
            print(f"  Confidence: {gemini_confidence}/10")
            print(f"  Model: {gemini_model}")
        else:
            # Fallback to model-based decision
            print(f"  Gemini unavailable - using model-based decision")
            if final_composite_score > thresholds['buy_yes']:
                gemini_decision = 'BUY_YES'
            elif final_composite_score < thresholds['buy_no']:
                gemini_decision = 'BUY_NO'
            else:
                gemini_decision = 'SKIP'
            gemini_reasoning = f"Model decision: Composite score {final_composite_score:.1f}"
            gemini_confidence = int(confidence / 10)  # Convert model confidence (0-100) to 1-10 scale
            gemini_model = 'MODEL_ONLY'
            
            # Log fallback analysis to index.html using same structure as Gemini reports
            try:
                index_path = Path(__file__).parent / "docs" / "index.html"
                if index_path.exists():
                    with open(index_path, 'r') as f:
                        html_content = f.read()
                    
                    # Create fallback analysis block in same format as Gemini results
                    fallback_analysis_html = f'''
                <div class="ai-analysis" style="background-color: #fef3c7; border-left: 4px solid #f59e0b;">
                    <h4>📊 Model-Based Analysis (Gemini Unavailable)</h4>
                    <div style="font-size: 0.85em; color: #666; margin-bottom: 8px;">Fallback to Statistical Model</div>
                    <div class="ai-analysis-text">
                        <strong>Market:</strong> {market_ticker}<br>
                        <strong>Signals Analysis:</strong> {direction} ({bullish_signals} bullish, {bearish_signals} bearish)<br>
                        <strong>Composite Score:</strong> {final_composite_score:.1f} / 100<br>
                        <strong>Decision:</strong> {gemini_decision} (threshold: YES > {thresholds['buy_yes']}, NO < {thresholds['buy_no']})<br>
                        <strong>Reasoning:</strong> {gemini_reasoning}<br>
                        <strong>Confidence:</strong> {int(confidence)}/100 (model alignment)
                    </div>
                </div>'''
                    
                    # Append to AI Performance Insights section (after analysis)
                    insights_marker = "<!-- GEMINI_DECISIONS_LOG -->"
                    if insights_marker not in html_content:
                        insights_marker = "</div>\n    </div>\n\n    </div>"
                    
                    html_content = html_content.replace(insights_marker, 
                                                       f"{fallback_analysis_html}\n    {insights_marker}", 
                                                       1)
                    
                    with open(index_path, 'w') as f:
                        f.write(html_content)
                    
                    logger.debug(f"[AI ANALYSIS LOG] Fallback analysis logged to index.html")
            except Exception as log_error:
                logger.debug(f"[AI ANALYSIS LOG] Could not log to index.html: {log_error}")
        
        # Calculate strongest signal for rationale
        strongest_signal = max(signal_strengths, key=signal_strengths.get)
        strongest_value = signal_strengths[strongest_signal]
        
        decision_rationale = (
            f"{direction} ({bullish_signals} bullish, {bearish_signals} bearish signals). "
            f"Strongest: {strongest_signal}={strongest_value:.1f}. "
            f"Composite={final_composite_score:.1f}, Alignment={alignment_factor:.1f}%, "
            f"Volatility={'DAMPENED' if volatility_multiplier < 1.0 else 'NORMAL'}"
        )
        
        # Print summary
        print(f"\n[SIGNAL SUMMARY]")
        print(f"  Momentum:     {momentum_score:6.1f} (weight: {weights['momentum']*100:.0f}%)")
        print(f"  Orderbook:    {orderbook_score:6.1f} (weight: {weights['orderbook']*100:.0f}%)")
        print(f"  Trade Flow:   {trade_flow_score:6.1f} (weight: {weights['trade_flow']*100:.0f}%)")
        print(f"  Liquidity:    {liquidity_score:6.1f} (weight: {weights['liquidity']*100:.0f}%)")
        print(f"  Volatility:   {volatility_multiplier:.2f}x multiplier")
        print(f"\n[MARKET PRICING]")
        print(f"  Best Bid (YES): {best_bid:.0f} cents")
        print(f"  Best Ask (NO):  {best_ask:.0f} cents")
        print(f"  Mid-price:      {(best_bid + best_ask) / 2:.0f} cents")
        print(f"\n[FINAL SCORE]")
        print(f"  Composite:    {final_composite_score:6.1f}")
        print(f"  Confidence:   {confidence:6.1f}%")
        print(f"  Threshold Buy YES:  {thresholds['buy_yes']}")
        print(f"  Threshold Buy NO:   {thresholds['buy_no']}")
        print(f"\n[RATIONALE] {decision_rationale}")
        print(f"{'='*70}\n")
        
        return {
            'momentum_score': momentum_score,
            'orderbook_score': orderbook_score,
            'trade_flow_score': trade_flow_score,
            'liquidity_score': liquidity_score,
            'volatility_multiplier': volatility_multiplier,
            'final_composite_score': final_composite_score,
            'confidence': confidence,
            'decision_rationale': decision_rationale,
            'current_best_bid': best_bid,
            'current_best_ask': best_ask,
            'market_price_context': f"Bid-Ask: {best_bid}-{best_ask} cents",
            'gemini_decision': gemini_decision,
            'gemini_reasoning': gemini_reasoning,
            'gemini_confidence': gemini_confidence,
            'gemini_model': gemini_model
        }
        
    except Exception as e:
        logger.error(f"Error in get_market_signals: {e}")
        import traceback
        traceback.print_exc()
        
        # Return neutral signals on error
        return {
            'momentum_score': 50.0,
            'orderbook_score': 50.0,
            'trade_flow_score': 50.0,
            'liquidity_score': 50.0,
            'volatility_multiplier': 1.0,
            'final_composite_score': 50.0,
            'confidence': 0.0,
            'decision_rationale': f'ERROR: {str(e)} - Using neutral signals',
            'current_best_bid': 50,
            'current_best_ask': 50,
            'market_price_context': 'Error fetching market data',
            'gemini_decision': 'SKIP',
            'gemini_reasoning': f'Error occurred: {str(e)}',
            'gemini_confidence': 0,
            'gemini_model': 'ERROR_FALLBACK'
        }


def get_smart_market_signals(client, market_ticker, series_ticker=None, asset='BTC'):
    """
    UPGRADED MAIN FUNCTION - Uses Smart Signals for superior decision making.
    
    This version calculates:
    1. Distance to strike (most important for hourly markets)
    2. Time to expiry (critical for binary options)
    3. BTC price momentum (actual BTC movement)
    4. Market wisdom (respects strong consensus)
    5. Expected edge for both sides
    6. Volatility regime
    
    Falls back to legacy signals if smart_signals module unavailable.
    
    Returns:
        dict with smart signals, legacy signals, and combined decision
    """
    try:
        # Auto-extract series_ticker if not provided
        if not series_ticker:
            series_ticker = extract_series_ticker(market_ticker)
        
        print(f"\n{'='*70}")
        print(f"[SMART SIGNAL ANALYSIS] Starting analysis for {market_ticker} ({asset})")
        print(f"{'='*70}")
        
        # Load configuration
        config = load_model_config()
        thresholds = config.get('thresholds', DEFAULT_THRESHOLDS)
        
        # First get basic market data (orderbook)
        orderbook_score, best_bid, best_ask = get_orderbook_score(client, market_ticker)
        
        # Check if smart signals available
        if SMART_SIGNALS_AVAILABLE:
            print("[SMART SIGNALS] Module available - using advanced analysis")
            
            # Get smart signals (this does the heavy lifting)
            smart_signals_result = get_smart_signals(
                market_ticker=market_ticker,
                yes_bid=best_bid,
                yes_ask=best_ask,
                current_btc_price=None  # Will fetch automatically
            )
            
            # Check for errors
            if 'error' in smart_signals_result:
                print(f"[SMART SIGNALS] Error: {smart_signals_result.get('reason')}")
                print("[SMART SIGNALS] Falling back to legacy signals")
                return get_market_signals(client, market_ticker, series_ticker, asset)
            
            # Get Gemini decision using smart signals
            print(f"\n[GEMINI DECISION]")
            gemini_result = get_smart_gemini_decision(smart_signals_result, market_ticker, thresholds)
            
            # Extract key metrics from smart signals
            distance = smart_signals_result.get('distance', {})
            time_decay = smart_signals_result.get('time_decay', {})
            btc_momentum = smart_signals_result.get('btc_momentum', {})
            market_wisdom = smart_signals_result.get('market_wisdom', {})
            volatility = smart_signals_result.get('volatility', {})
            yes_edge = smart_signals_result.get('yes_edge', {})
            no_edge = smart_signals_result.get('no_edge', {})
            
            # Print comprehensive summary
            print(f"\n[SMART SIGNALS SUMMARY]")
            print(f"  === DISTANCE TO STRIKE ===")
            print(f"  Current BTC:  ${distance.get('current_price', 0):,.0f}")
            print(f"  Strike Price: ${distance.get('strike_price', 0):,.0f}")
            print(f"  Distance:     ${distance.get('distance_dollars', 0):,.0f} ({distance.get('direction', 'unknown')})")
            print(f"  Zone:         {distance.get('zone', 'unknown')}")
            
            print(f"\n  === TIME TO EXPIRY ===")
            print(f"  Minutes:      {time_decay.get('minutes_remaining', 0):.1f}")
            print(f"  Phase:        {time_decay.get('phase', 'unknown')}")
            
            print(f"\n  === BTC MOMENTUM ===")
            print(f"  Direction:    {btc_momentum.get('direction', 'neutral')}")
            print(f"  Strength:     {btc_momentum.get('strength', 50):.1f}/100")
            print(f"  15min Change: ${btc_momentum.get('raw_change', 0):+,.0f}")
            
            # NEW: Display velocity (short-term prediction from faster data)
            btc_velocity = smart_signals_result.get('btc_velocity', {})
            velocity_adj = smart_signals_result.get('velocity_adjustment', 0)
            print(f"\n  === BTC VELOCITY (Binance - faster than BRTI) ===")
            print(f"  Rate:         ${btc_velocity.get('velocity', 0):+,.0f}/min")
            print(f"  Acceleration: {btc_velocity.get('acceleration', 'unknown')}")
            print(f"  Projected 60s: ${btc_velocity.get('projected_60s', 0):,.0f}")
            print(f"  Edge Adjust:  {velocity_adj:+}% confidence")
            
            print(f"\n  === MARKET WISDOM ===")
            print(f"  Consensus:    {market_wisdom.get('consensus', 'neutral')}")
            print(f"  Implied Prob: {market_wisdom.get('implied_probability', 50):.0f}%")
            print(f"  Yes Bid/Ask:  {best_bid}/{best_ask}¢")
            
            print(f"\n  === VOLATILITY ===")
            print(f"  Regime:       {volatility.get('regime', 'normal')}")
            print(f"  Hourly Range: ${volatility.get('hourly_range', 500):,.0f}")
            
            print(f"\n  === EDGE CALCULATION ===")
            print(f"  YES Edge:     {yes_edge.get('expected_edge', 0):+.1f}% (prob: {yes_edge.get('win_probability', 0.5)*100:.0f}%)")
            print(f"  NO Edge:      {no_edge.get('expected_edge', 0):+.1f}% (prob: {no_edge.get('win_probability', 0.5)*100:.0f}%)")
            print(f"  Min Required: {max(yes_edge.get('min_edge_required', 5), no_edge.get('min_edge_required', 5)):.1f}%")
            
            print(f"\n  === DECISION ===")
            print(f"  Smart Rec:    {smart_signals_result.get('recommendation')}")
            print(f"  Gemini:       {gemini_result.get('decision')} (confidence: {gemini_result.get('confidence')}/10)")
            print(f"  Model:        {gemini_result.get('model')}")
            print(f"  Reasoning:    {gemini_result.get('reasoning', '')[:150]}...")
            
            print(f"{'='*70}\n")
            
            # Build decision rationale
            decision_rationale = (
                f"Distance: ${distance.get('distance_dollars', 0):.0f} {distance.get('direction', '')} ({distance.get('zone', '')}). "
                f"Velocity: ${btc_velocity.get('velocity', 0):+,.0f}/min ({btc_velocity.get('acceleration', 'stable')}). "
                f"Market: {market_wisdom.get('consensus', 'neutral')} ({market_wisdom.get('implied_probability', 50):.0f}%). "
                f"Edge: YES {yes_edge.get('expected_edge', 0):+.1f}% / NO {no_edge.get('expected_edge', 0):+.1f}%"
            )
            
            # Return combined results
            return {
                # Smart signals data
                'smart_signals': smart_signals_result,
                'distance_to_strike': distance,
                'time_to_expiry': time_decay,
                'btc_momentum': btc_momentum,
                'market_wisdom_signal': market_wisdom,
                'volatility_regime': volatility,
                'yes_edge': yes_edge,
                'no_edge': no_edge,
                
                # Decision
                'gemini_decision': gemini_result.get('decision', 'SKIP'),
                'gemini_reasoning': gemini_result.get('reasoning', ''),
                'gemini_confidence': gemini_result.get('confidence', 0),
                'gemini_model': gemini_result.get('model', 'UNKNOWN'),
                
                # Smart signals recommendation (before Gemini)
                'smart_recommendation': smart_signals_result.get('recommendation', 'SKIP'),
                'smart_reason': smart_signals_result.get('reason', ''),
                'smart_confidence': smart_signals_result.get('confidence', 0),
                
                # Legacy compatibility fields
                'momentum_score': btc_momentum.get('strength', 50),
                'orderbook_score': orderbook_score,
                'trade_flow_score': 50,  # Not used in smart signals
                'liquidity_score': 80,  # Derived from spread
                'volatility_multiplier': volatility.get('adjustment_factor', 1.0),
                'final_composite_score': 50 + (yes_edge.get('expected_edge', 0) - no_edge.get('expected_edge', 0)),
                'confidence': smart_signals_result.get('confidence', 0),
                'decision_rationale': decision_rationale,
                'current_best_bid': best_bid,
                'current_best_ask': best_ask,
                'market_price_context': f"Bid-Ask: {best_bid}-{best_ask}¢",
                
                # Framework indicator
                'framework': 'smart_signals_v2',
                'agreed_with_signals': gemini_result.get('agreed_with_signals', True)
            }
            
        else:
            print("[SMART SIGNALS] Module not available - using legacy analysis")
            return get_market_signals(client, market_ticker, series_ticker, asset)
            
    except Exception as e:
        logger.error(f"Error in get_smart_market_signals: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback to legacy
        print("[SMART SIGNALS] Error occurred - falling back to legacy signals")
        try:
            return get_market_signals(client, market_ticker, series_ticker, asset)
        except:
            return {
                'gemini_decision': 'SKIP',
                'gemini_reasoning': f'Error: {str(e)}',
                'gemini_confidence': 0,
                'gemini_model': 'ERROR_FALLBACK',
                'confidence': 0,
                'current_best_bid': 50,
                'current_best_ask': 50,
                'framework': 'error_fallback'
            }

