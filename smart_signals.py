#!/usr/bin/env python3
"""
Smart Signals Module - Advanced Trading Intelligence for Kalshi Hourly Markets

This module provides sophisticated signal generation specifically designed for 
hourly BTC "Price Above" prediction markets. Key innovations:

1. Distance-to-Strike Analysis - The #1 predictor for hourly market outcomes
2. Time-to-Expiry Decay - Critical for binary options near expiration
3. BTC Price Momentum - Uses actual BTC price movement, not market candlesticks
4. Market Wisdom Signal - Respects market consensus when it's strong
5. Edge Calculator - Only trades when expected value is positive
6. Volatility Regime Detection - Adjusts confidence based on BTC volatility

Key Insight from Trade History Analysis:
- Bot was 48.4% accurate (worse than coin flip)
- YES trades lost 75% of time  
- When market consensus is strong (yes_bid > 70 or < 30), market is usually right
- Mid-probability markets (50¢) are coin flips with no edge
- The closer BTC is to strike price, the more uncertain the outcome
"""

import os
import math
import time
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

# Price data sources (ordered by speed/reliability for US users)
# Note: Binance blocked in US (451), CoinDesk unreliable
# Coinbase/Kraken/Bitstamp all work and are used in BRTI calculation
COINBASE_API = 'https://api.coinbase.com/v2/prices/BTC-USD/spot'
KRAKEN_API = 'https://api.kraken.com/0/public/Ticker?pair=XBTUSD'
KRAKEN_OHLC_API = 'https://api.kraken.com/0/public/OHLC'
BITSTAMP_API = 'https://www.bitstamp.net/api/v2/ticker/btcusd/'
BITSTAMP_OHLC_API = 'https://www.bitstamp.net/api/v2/ohlc/btcusd/'
# Fallbacks (may not work in all regions)
BINANCE_API = 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT'
BINANCE_KLINES_API = 'https://api.binance.com/api/v3/klines'
COINDESK_API = 'https://api.coindesk.com/v1/bpi/currentprice.json'
COINGECKO_API = 'https://api.coingecko.com/api/v3'

# Default signal thresholds (can be overridden by tuned params)
STRONG_MARKET_CONSENSUS = 70  # yes_bid >= 70 means market strongly expects YES
WEAK_MARKET_CONSENSUS = 30    # yes_bid <= 30 means market strongly expects NO
NEUTRAL_ZONE_LOW = 40         # 40-60 is uncertainty zone
NEUTRAL_ZONE_HIGH = 60

# Distance thresholds (in dollars) - defaults, tunable
CRITICAL_DISTANCE = 100       # Within $100 of strike = very uncertain
MODERATE_DISTANCE = 250       # Within $250 = somewhat uncertain  
SAFE_DISTANCE = 500           # Beyond $500 = clearer direction

# Time decay thresholds (minutes to expiry)
EXPIRY_CRITICAL = 5           # Last 5 minutes = pure probability play
EXPIRY_URGENT = 15            # Last 15 minutes = weight current position heavily
EXPIRY_NORMAL = 30            # More than 30 min = momentum matters

# Volatility thresholds (hourly ATR in dollars)
LOW_VOLATILITY = 200          # BTC moving less than $200/hour
NORMAL_VOLATILITY = 500       # Normal BTC hourly range
HIGH_VOLATILITY = 1000        # High volatility regime

# Edge requirements - defaults, tunable
MIN_EDGE_REQUIREMENT = 0.05   # Require 5% expected edge to trade
HIGH_CONFIDENCE_EDGE = 0.15   # 15% edge = high confidence trade

# Velocity weight - default, tunable
VELOCITY_WEIGHT = 0.2         # How much to weight velocity in probability

# Config file for tuned parameters
MODEL_CONFIG_PATH = Path(__file__).parent / "model_config.json"


def load_tuned_params() -> Dict:
    """
    Load Gemini-tuned parameters from model_config.json.
    
    These are pre-computed during Phase 1 (model tuning) so we 
    don't need to call Gemini during fast execution.
    """
    try:
        with open(MODEL_CONFIG_PATH, 'r') as f:
            config = json.load(f)
        
        # Extract params from config.factors and top level
        factors = config.get('factors', {})
        params = {
            'min_edge_requirement': factors.get('min_edge_percent', 0.005),
            'critical_distance_dollars': factors.get('critical_distance_dollars', 50),
            'safe_distance_dollars': factors.get('safe_distance_dollars', 200),
            'strong_market_consensus': factors.get('strong_market_consensus', 60),
            'weak_market_consensus': factors.get('weak_market_consensus', 40),
            'velocity_weight': config.get('velocity_weight', 0.2),
            'contrarian_threshold': config.get('contrarian_threshold', 0.20),
        }
        return params
    except Exception as e:
        logger.debug(f"Could not load tuned params: {e}")
        return {}


# ============================================================================
# BTC PRICE DATA FUNCTIONS
# ============================================================================

def get_btc_price() -> Optional[float]:
    """
    Get current BTC price from multiple sources, ordered by update speed.
    
    Priority (fastest first):
    1. Binance (~10-50ms) – fastest ticks, may 451-block US
    2. Coinbase (~150-200ms) – BRTI component
    3. Kraken (~250-300ms) – BRTI component
    4. Bitstamp (~350-400ms) – BRTI component
    """
    # Try Binance first (fastest updates, may be blocked in US)
    try:
        response = requests.get(BINANCE_API, timeout=2)
        response.raise_for_status()
        data = response.json()
        price = float(data['price'])
        logger.debug(f"Binance price: ${price:,.2f}")
        return price
    except Exception as e:
        logger.debug(f"Binance API failed: {e}")
    
    # Try Coinbase next - fast and US-reliable
    try:
        response = requests.get(COINBASE_API, timeout=3)
        response.raise_for_status()
        data = response.json()
        price = float(data['data']['amount'])
        logger.debug(f"Coinbase price: ${price:,.2f}")
        return price
    except Exception as e:
        logger.debug(f"Coinbase API failed: {e}")
    
    # Try Kraken - also used in BRTI
    try:
        response = requests.get(KRAKEN_API, timeout=3)
        response.raise_for_status()
        data = response.json()
        price = float(data['result']['XXBTZUSD']['c'][0])
        logger.debug(f"Kraken price: ${price:,.2f}")
        return price
    except Exception as e:
        logger.debug(f"Kraken API failed: {e}")
    
    # Try Bitstamp - also used in BRTI
    try:
        response = requests.get(BITSTAMP_API, timeout=3)
        response.raise_for_status()
        data = response.json()
        price = float(data['last'])
        logger.debug(f"Bitstamp price: ${price:,.2f}")
        return price
    except Exception as e:
        logger.debug(f"Bitstamp API failed: {e}")
    
    return None


def get_btc_price_history(minutes: int = 60) -> List[Dict]:
    """
    Get BTC price history for momentum calculation.
    
    Uses Kraken OHLC (works in US, BRTI component) as primary.
    Falls back to Bitstamp OHLC, then Binance (may be blocked in US).
    
    Returns list of {timestamp, price} dicts.
    """
    # Try Kraken OHLC first - works in US, 1-minute candles
    try:
        response = requests.get(
            KRAKEN_OHLC_API,
            params={
                'pair': 'XBTUSD',
                'interval': 1,  # 1-minute candles
            },
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        
        # Kraken OHLC format: {result: {XXBTZUSD: [[time, open, high, low, close, vwap, volume, count], ...]}}
        ohlc_data = data.get('result', {}).get('XXBTZUSD', [])
        
        if ohlc_data:
            # Filter to requested time window
            cutoff = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp())
            prices = [
                {'timestamp': int(k[0]) * 1000, 'price': float(k[4])}  # k[4] is close price
                for k in ohlc_data if int(k[0]) >= cutoff
            ]
            
            if prices:
                logger.debug(f"Got {len(prices)} price points from Kraken OHLC")
                return prices
            
    except Exception as e:
        logger.debug(f"Kraken OHLC failed: {e}")
    
    # Fallback: Bitstamp OHLC
    try:
        response = requests.get(
            BITSTAMP_OHLC_API,
            params={
                'step': 60,  # 1-minute candles
                'limit': min(minutes, 1000)
            },
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        
        # Bitstamp format: {data: {ohlc: [{timestamp, open, high, low, close, volume}, ...]}}
        ohlc_data = data.get('data', {}).get('ohlc', [])
        
        if ohlc_data:
            prices = [
                {'timestamp': int(k['timestamp']) * 1000, 'price': float(k['close'])}
                for k in ohlc_data
            ]
            
            if prices:
                logger.debug(f"Got {len(prices)} price points from Bitstamp OHLC")
                return prices
            
    except Exception as e:
        logger.debug(f"Bitstamp OHLC failed: {e}")
    
    # Last fallback: Binance (blocked in US, but might work for some)
    try:
        limit = min(minutes, 1000)
        response = requests.get(
            BINANCE_KLINES_API,
            params={
                'symbol': 'BTCUSDT',
                'interval': '1m',
                'limit': limit
            },
            timeout=5
        )
        response.raise_for_status()
        klines = response.json()
        
        prices = [
            {'timestamp': k[0], 'price': float(k[4])}
            for k in klines
        ]
        
        if prices:
            logger.debug(f"Got {len(prices)} price points from Binance klines")
            return prices
            
    except Exception as e:
        logger.debug(f"Binance klines failed: {e}")
    
    logger.warning("Failed to get BTC price history from all sources")
    return []


def get_btc_velocity(seconds: int = 60) -> Dict:
    """
    Calculate BTC price VELOCITY (rate of change) over very short timeframe.
    
    This is where the EDGE comes from:
    - Fast exchanges move BEFORE BRTI updates
    - If price is accelerating toward/away from strike, we can predict direction
    
    Uses Kraken OHLC (works in US), falls back to Bitstamp then Binance.
    
    Returns:
        dict with:
        - velocity: Price change per second ($/sec)
        - acceleration: Is velocity increasing or decreasing?
        - projected_60s: Where price will be in 60 seconds at current velocity
        - confidence: How reliable is this projection?
    """
    klines = None
    source = None
    
    # Try Kraken first
    try:
        response = requests.get(
            KRAKEN_OHLC_API,
            params={
                'pair': 'XBTUSD',
                'interval': 1,  # 1-minute candles
            },
            timeout=3
        )
        response.raise_for_status()
        data = response.json()
        ohlc_data = data.get('result', {}).get('XXBTZUSD', [])
        
        if ohlc_data and len(ohlc_data) >= 5:
            # Take last 5 candles
            klines = ohlc_data[-5:]
            source = 'Kraken'
    except Exception as e:
        logger.debug(f"Kraken velocity failed: {e}")
    
    # Fallback to Bitstamp
    if klines is None:
        try:
            response = requests.get(
                BITSTAMP_OHLC_API,
                params={
                    'step': 60,
                    'limit': 5
                },
                timeout=3
            )
            response.raise_for_status()
            data = response.json()
            ohlc_data = data.get('data', {}).get('ohlc', [])
            
            if ohlc_data and len(ohlc_data) >= 2:
                klines = ohlc_data
                source = 'Bitstamp'
        except Exception as e:
            logger.debug(f"Bitstamp velocity failed: {e}")
    
    # Last fallback: Binance (may be blocked)
    if klines is None:
        try:
            response = requests.get(
                BINANCE_KLINES_API,
                params={
                    'symbol': 'BTCUSDT',
                    'interval': '1m',
                    'limit': 5
                },
                timeout=3
            )
            response.raise_for_status()
            klines = response.json()
            source = 'Binance'
        except Exception as e:
            logger.debug(f"Binance velocity failed: {e}")
    
    if not klines or len(klines) < 2:
        return {'velocity': 0, 'acceleration': 'unknown', 'projected_60s': 0, 'confidence': 0}
    
    # Extract close prices based on source format
    try:
        if source == 'Kraken':
            prices = [float(k[4]) for k in klines]  # [time, open, high, low, close, ...]
        elif source == 'Bitstamp':
            prices = [float(k['close']) for k in klines]
        else:  # Binance
            prices = [float(k[4]) for k in klines]
        
        current_price = prices[-1]
        
        # Velocity = change over last 2 minutes
        velocity_2min = (prices[-1] - prices[-3]) / 2 if len(prices) >= 3 else 0
        velocity_1min = prices[-1] - prices[-2]
        
        # Acceleration = is velocity increasing?
        if velocity_1min > velocity_2min * 1.2:
            acceleration = 'accelerating_up'
        elif velocity_1min < velocity_2min * 0.8:
            acceleration = 'accelerating_down' if velocity_1min < 0 else 'decelerating'
        else:
            acceleration = 'stable'
        
        # Project where price will be in 60 seconds
        projected_velocity = velocity_1min * 0.7 + (velocity_2min / 2) * 0.3
        projected_60s = current_price + projected_velocity
        
        # Confidence based on consistency
        if acceleration in ['accelerating_up', 'accelerating_down']:
            confidence = 70
        elif abs(velocity_1min) > 50:
            confidence = 60
        else:
            confidence = 40
        
        return {
            'velocity': velocity_1min,
            'velocity_per_sec': velocity_1min / 60,
            'acceleration': acceleration,
            'projected_60s': projected_60s,
            'current_price': current_price,
            'confidence': confidence,
            'source': source
        }
        
    except Exception as e:
        logger.debug(f"Failed to calculate velocity: {e}")
        return {'velocity': 0, 'acceleration': 'unknown', 'projected_60s': 0, 'confidence': 0}


# ============================================================================
# CORE SIGNAL FUNCTIONS
# ============================================================================

def calculate_distance_to_strike(current_price: float, strike_price: float) -> Dict:
    """
    Calculate the distance from current BTC price to strike price.
    
    This is the MOST IMPORTANT signal for hourly markets.
    
    Returns:
        dict with:
        - distance_dollars: Absolute distance in USD
        - distance_percent: Distance as percentage of current price
        - direction: 'above' if current > strike, 'below' if current < strike
        - zone: 'critical', 'moderate', 'safe' based on distance
        - score: 0-100 signal score (50 = neutral, extremes = higher confidence)
    """
    distance = current_price - strike_price
    abs_distance = abs(distance)
    distance_percent = (abs_distance / current_price) * 100
    direction = 'above' if distance > 0 else 'below'
    
    # Determine zone
    if abs_distance < CRITICAL_DISTANCE:
        zone = 'critical'  # Too close to call
    elif abs_distance < MODERATE_DISTANCE:
        zone = 'moderate'  # Slight edge possible
    elif abs_distance < SAFE_DISTANCE:
        zone = 'comfortable'  # Clear direction
    else:
        zone = 'safe'  # Very clear direction
    
    # Calculate score (0-100)
    # When above strike: higher score = more likely YES wins
    # When below strike: lower score = more likely NO wins
    # Close to strike: score near 50 = uncertain
    
    if abs_distance >= SAFE_DISTANCE:
        # Very safe distance - strong signal
        score = 85 if direction == 'above' else 15
    elif abs_distance >= MODERATE_DISTANCE:
        # Comfortable distance - moderate signal
        score = 70 if direction == 'above' else 30
    elif abs_distance >= CRITICAL_DISTANCE:
        # Moderate distance - slight signal
        score = 60 if direction == 'above' else 40
    else:
        # Critical distance - uncertain
        # Scale linearly from 50 based on how close we are
        lean = (abs_distance / CRITICAL_DISTANCE) * 10
        score = 50 + lean if direction == 'above' else 50 - lean
    
    return {
        'distance_dollars': abs_distance,
        'distance_percent': distance_percent,
        'direction': direction,
        'zone': zone,
        'score': score,
        'current_price': current_price,
        'strike_price': strike_price,
        'raw_distance': distance  # Positive = above, negative = below
    }


def calculate_time_to_expiry(market_ticker: str) -> Dict:
    """
    Calculate time remaining until market expires.
    
    Ticker format: KXBTCD-25DEC3012-T88749.99
    Date component: 25DEC3012 = 2025 Dec 30th, 12:00 ET
    
    Returns:
        dict with:
        - minutes_remaining: Minutes until expiry
        - phase: 'critical', 'urgent', 'normal', 'early'
        - weight_multiplier: How much to weight current position vs momentum
        - should_trade: Whether we should even trade this close to expiry
    """
    try:
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
    except ImportError:
        from pytz import timezone
        ET = timezone('America/New_York')
    
    # Extract date from ticker: KXBTCD-25DEC3012-T88749.99
    parts = market_ticker.split('-')
    if len(parts) < 2:
        return {'minutes_remaining': 60, 'phase': 'unknown', 'weight_multiplier': 1.0, 'should_trade': True}
    
    date_part = parts[1]  # 25DEC3012
    
    try:
        # Parse: YY + MMM + DD + HH
        year = 2000 + int(date_part[:2])
        month_str = date_part[2:5].upper()
        day = int(date_part[5:7])
        hour = int(date_part[7:9])
        
        month_map = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                     'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
        month = month_map.get(month_str, 1)
        
        # Market expires at the top of the specified hour ET
        expiry_et = datetime(year, month, day, hour, 0, 0, tzinfo=ET)
        now_et = datetime.now(ET)
        
        delta = expiry_et - now_et
        minutes_remaining = delta.total_seconds() / 60
        
        # Determine phase
        if minutes_remaining <= EXPIRY_CRITICAL:
            phase = 'critical'
            weight_multiplier = 0.1  # Almost ignore momentum, use pure probability
            should_trade = minutes_remaining > 1  # Don't trade in final minute
        elif minutes_remaining <= EXPIRY_URGENT:
            phase = 'urgent'
            weight_multiplier = 0.4  # Heavily weight current position
            should_trade = True
        elif minutes_remaining <= EXPIRY_NORMAL:
            phase = 'normal'
            weight_multiplier = 0.7  # Balance position and momentum
            should_trade = True
        else:
            phase = 'early'
            weight_multiplier = 1.0  # Full momentum weighting
            should_trade = True
        
        return {
            'minutes_remaining': max(0, minutes_remaining),
            'phase': phase,
            'weight_multiplier': weight_multiplier,
            'should_trade': should_trade,
            'expiry_time': expiry_et.isoformat()
        }
        
    except Exception as e:
        logger.warning(f"Failed to parse expiry from {market_ticker}: {e}")
        return {'minutes_remaining': 60, 'phase': 'unknown', 'weight_multiplier': 1.0, 'should_trade': True}


def calculate_btc_momentum(lookback_minutes: int = 15) -> Dict:
    """
    Calculate BTC price momentum from actual price data.
    
    Unlike market candlesticks which often return neutral data,
    this uses actual BTC price movement.
    
    Returns:
        dict with:
        - direction: 'bullish', 'bearish', 'neutral'
        - strength: 0-100 (50 = neutral)
        - price_change_dollars: Absolute change in USD
        - price_change_percent: Change as percentage
        - trend_consistency: How consistent the move is (0-1)
    """
    prices = get_btc_price_history(lookback_minutes)
    
    if len(prices) < 2:
        return {
            'direction': 'neutral',
            'strength': 50,
            'price_change_dollars': 0,
            'price_change_percent': 0,
            'trend_consistency': 0,
            'data_points': 0
        }
    
    first_price = prices[0]['price']
    last_price = prices[-1]['price']
    
    # Calculate change
    change = last_price - first_price
    change_percent = (change / first_price) * 100
    
    # Calculate trend consistency (how many moves were in same direction)
    consistent_moves = 0
    total_moves = len(prices) - 1
    
    for i in range(1, len(prices)):
        move = prices[i]['price'] - prices[i-1]['price']
        if (change > 0 and move > 0) or (change < 0 and move < 0):
            consistent_moves += 1
    
    trend_consistency = consistent_moves / total_moves if total_moves > 0 else 0
    
    # Determine direction
    if change > 50:  # More than $50 up
        direction = 'bullish'
    elif change < -50:  # More than $50 down
        direction = 'bearish'
    else:
        direction = 'neutral'
    
    # Calculate strength (0-100)
    # Larger moves = stronger signal
    # Scale: $0 = 50, +$500 = 80, -$500 = 20
    normalized_change = min(max(change / 500, -1), 1)  # Clamp to [-1, 1]
    strength = 50 + (normalized_change * 30)  # Range: 20-80
    
    # Boost strength if trend is consistent
    if trend_consistency > 0.7:
        strength = strength + (100 - strength) * 0.2 if strength > 50 else strength - strength * 0.2
    
    return {
        'direction': direction,
        'strength': strength,
        'price_change_dollars': abs(change),
        'price_change_percent': abs(change_percent),
        'trend_consistency': trend_consistency,
        'data_points': len(prices),
        'raw_change': change
    }


def calculate_market_wisdom(yes_bid: int, yes_ask: int) -> Dict:
    """
    Analyze market consensus and determine if we should respect it.
    
    Key insight from trade history:
    - When yes_bid >= 70, YES usually wins (market is right)
    - When yes_bid <= 30, NO usually wins (market is right)
    - In between, market has no strong view
    
    Returns:
        dict with:
        - consensus: 'strong_yes', 'strong_no', 'neutral'
        - confidence: How strong the market consensus is (0-100)
        - implied_probability: Market-implied probability of YES (0-100)
        - should_fade: Whether to bet against market (almost never)
        - recommended_side: 'yes', 'no', or 'skip'
    """
    # Market implied probability is approximately the mid-price
    mid_price = (yes_bid + yes_ask) / 2
    spread = yes_ask - yes_bid
    
    # Adjust for spread (wider spread = less confident market)
    spread_penalty = min(spread / 20, 0.3)  # Max 30% penalty
    
    if mid_price >= STRONG_MARKET_CONSENSUS:
        consensus = 'strong_yes'
        confidence = 100 - spread_penalty * 100
        recommended_side = 'yes'
    elif mid_price <= WEAK_MARKET_CONSENSUS:
        consensus = 'strong_no'
        confidence = 100 - spread_penalty * 100
        recommended_side = 'no'
    elif mid_price > NEUTRAL_ZONE_HIGH:
        consensus = 'lean_yes'
        confidence = 60 - spread_penalty * 100
        recommended_side = 'yes'  # Slight lean
    elif mid_price < NEUTRAL_ZONE_LOW:
        consensus = 'lean_no'
        confidence = 60 - spread_penalty * 100
        recommended_side = 'no'  # Slight lean
    else:
        consensus = 'neutral'
        confidence = 30  # Low confidence in neutral zone
        recommended_side = 'skip'
    
    # Should we fade (bet against) market? Almost never!
    # Only fade if we have VERY strong contrary evidence
    should_fade = False  # Default: respect market wisdom
    
    return {
        'consensus': consensus,
        'confidence': max(0, confidence),
        'implied_probability': mid_price,
        'should_fade': should_fade,
        'recommended_side': recommended_side,
        'yes_bid': yes_bid,
        'yes_ask': yes_ask,
        'spread': spread
    }


def calculate_volatility_regime(lookback_minutes: int = 60) -> Dict:
    """
    Determine current BTC volatility regime.
    
    High volatility = more uncertainty, need larger edge
    Low volatility = more confidence in current position
    
    Returns:
        dict with:
        - regime: 'low', 'normal', 'high', 'extreme'
        - hourly_range: Estimated hourly price range
        - adjustment_factor: Multiplier for edge requirements
    """
    prices = get_btc_price_history(lookback_minutes)
    
    if len(prices) < 5:
        return {
            'regime': 'unknown',
            'hourly_range': 500,  # Default assumption
            'adjustment_factor': 1.0
        }
    
    # Calculate min/max range in lookback window
    min_price = min(prices)
    max_price = max(prices)
    price_range = max_price - min_price
    
    # Estimate hourly range
    hours_in_lookback = lookback_minutes / 60
    estimated_hourly_range = price_range / hours_in_lookback if hours_in_lookback > 0 else price_range
    
    # Classify regime
    if estimated_hourly_range < 200:
        regime = 'low'
        adjustment = 0.9  # Lower edge requirement
    elif estimated_hourly_range < 500:
        regime = 'normal'
        adjustment = 1.0
    elif estimated_hourly_range < 1000:
        regime = 'high'
        adjustment = 1.2  # Higher edge requirement
    else:
        regime = 'extreme'
        adjustment = 1.5  # Much higher edge requirement
    
    return {
        'regime': regime,
        'hourly_range': estimated_hourly_range,
        'adjustment_factor': adjustment
    }


# ============================================================================
# CALCULATE EDGE EXPECTATION (used internally)
# ============================================================================

def calculate_edge_expectation(
    side: str,
    entry_price: int,
    distance_signal: Dict,
    time_signal: Dict,
    market_wisdom: Dict,
    volatility: Dict
) -> Dict:
    """
    This is the KEY function that determines if a trade is worth taking.

    Args:
        side: 'yes' or 'no'
        entry_price: Price in cents we'd pay
        distance_signal: Output from calculate_distance_to_strike
        time_signal: Output from calculate_time_to_expiry
        market_wisdom: Output from calculate_market_wisdom
        volatility: Output from calculate_volatility_regime

    Returns:
        dict with:
        - expected_edge: Expected value as percentage (-100 to +100)
        - win_probability: Estimated probability of winning (0-1)
        - payout: What we'd receive if we win
        - risk: What we'd lose if we lose
        - should_trade: Whether edge justifies trading
        - confidence: How confident we are in the edge estimate
    """
    # Base win probability from distance to strike
    if side == 'yes':
        base_prob = distance_signal['score'] / 100
    else:
        base_prob = 1 - (distance_signal['score'] / 100)
    
    # Adjust for market wisdom (market is often right)
    market_implied = market_wisdom['implied_probability'] / 100
    if side == 'yes':
        market_prob = market_implied
    else:
        market_prob = 1 - market_implied
    
    # Blend our estimate with market (market gets significant weight)
    # In neutral zones, trust market less; in strong consensus, trust more
    if market_wisdom['consensus'] in ['strong_yes', 'strong_no']:
        market_weight = 0.7  # Trust market heavily when it has strong view
    elif market_wisdom['consensus'] in ['lean_yes', 'lean_no']:
        market_weight = 0.5
    else:
        market_weight = 0.3  # In neutral zone, our signals matter more
    
    blended_prob = (base_prob * (1 - market_weight)) + (market_prob * market_weight)
    
    # Adjust for time decay
    # Near expiry, trust current position more
    time_weight = time_signal['weight_multiplier']
    if time_signal['phase'] in ['critical', 'urgent']:
        # Near expiry, position relative to strike matters most
        position_prob = 0.85 if distance_signal['direction'] == 'above' else 0.15
        if side == 'no':
            position_prob = 1 - position_prob
        blended_prob = (blended_prob * time_weight) + (position_prob * (1 - time_weight))
    
    # Apply volatility adjustment to confidence
    vol_adjustment = volatility['adjustment_factor']
    
    # Calculate edge
    payout = 100 - entry_price  # What we gain if we win (cents)
    risk = entry_price           # What we lose if we lose (cents)
    
    expected_value = (blended_prob * payout) - ((1 - blended_prob) * risk)
    expected_edge = expected_value / risk if risk > 0 else 0
    
    # Adjust minimum edge requirement for volatility
    min_edge = MIN_EDGE_REQUIREMENT * vol_adjustment
    should_trade = expected_edge >= min_edge
    
    # Calculate confidence in our estimate
    # Higher if: clear distance, market consensus, low volatility
    confidence_factors = [
        min(distance_signal['distance_dollars'] / SAFE_DISTANCE, 1) * 30,  # Max 30 for distance
        market_wisdom['confidence'] * 0.4,  # Max 40 for market
        (1 - min(volatility['adjustment_factor'] - 1, 0.5) / 0.5) * 30  # Max 30 for low vol
    ]
    confidence = sum(confidence_factors)
    
    return {
        'expected_edge': expected_edge * 100,  # As percentage
        'win_probability': blended_prob,
        'payout': payout,
        'risk': risk,
        'should_trade': should_trade,
        'confidence': confidence,
        'base_probability': base_prob,
        'market_probability': market_prob,
        'blended_probability': blended_prob,
        'min_edge_required': min_edge * 100,
        'entry_price': entry_price
    }


# ============================================================================
# MAIN SIGNAL AGGREGATOR
# ============================================================================

def get_smart_signals(
    market_ticker: str,
    yes_bid: int,
    yes_ask: int,
    current_btc_price: Optional[float] = None,
    tuned_params: Optional[Dict] = None
) -> Dict:
    """
    Master function that calculates all smart signals for a market.
    
    This is the FAST EXECUTION path - no external AI calls.
    Uses pre-tuned parameters from Phase 1 (model tuning).
    
    Args:
        market_ticker: Full market ticker (e.g., 'KXBTCD-25DEC3012-T88749.99')
        yes_bid: Current YES bid in cents
        yes_ask: Current YES ask in cents
        current_btc_price: Current BTC price (fetched if not provided)
        tuned_params: Pre-tuned parameters from model_tuner (optional)
    
    Returns:
        Comprehensive dict with all signals, recommendations, and trade decision
    """
    start_time = time.time()
    
    # Load tuned parameters if not provided
    if tuned_params is None:
        tuned_params = load_tuned_params()
    
    # Apply tuned thresholds (override defaults)
    min_edge = tuned_params.get('min_edge_requirement', MIN_EDGE_REQUIREMENT)
    critical_dist = tuned_params.get('critical_distance_dollars', CRITICAL_DISTANCE)
    safe_dist = tuned_params.get('safe_distance_dollars', SAFE_DISTANCE)
    strong_consensus = tuned_params.get('strong_market_consensus', STRONG_MARKET_CONSENSUS)
    weak_consensus = tuned_params.get('weak_market_consensus', WEAK_MARKET_CONSENSUS)
    velocity_weight = tuned_params.get('velocity_weight', VELOCITY_WEIGHT)
    contrarian_threshold = tuned_params.get('contrarian_threshold', 0.20)
    
    logger.info(f"\n{'='*70}")
    logger.info(f"[FAST EXECUTION] Analyzing {market_ticker}")
    logger.info(f"[TUNED PARAMS] min_edge={min_edge:.0%}, critical_dist=${critical_dist}, velocity_weight={velocity_weight}")
    logger.info(f"{'='*70}")
    
    # Get current BTC price if not provided (FAST - from Binance)
    if current_btc_price is None:
        current_btc_price = get_btc_price()
    
    if current_btc_price is None:
        logger.error("Cannot get BTC price - aborting signal calculation")
        return {
            'error': 'no_btc_price',
            'recommendation': 'SKIP',
            'reason': 'Could not fetch BTC price'
        }
    
    # Extract strike price from ticker
    try:
        strike_part = market_ticker.split('-T')[1]
        strike_price = float(strike_part)
    except (IndexError, ValueError) as e:
        logger.error(f"Cannot parse strike price from {market_ticker}: {e}")
        return {
            'error': 'invalid_ticker',
            'recommendation': 'SKIP',
            'reason': f'Could not parse strike price from ticker: {e}'
        }
    
    # Calculate all signals (all local calculations - fast)
    distance = calculate_distance_to_strike(current_btc_price, strike_price)
    time_decay = calculate_time_to_expiry(market_ticker)
    btc_momentum = calculate_btc_momentum(lookback_minutes=15)
    btc_velocity = get_btc_velocity(seconds=60)  # Short-term velocity for edge
    market_wisdom = calculate_market_wisdom(yes_bid, yes_ask)
    volatility = calculate_volatility_regime(lookback_minutes=60)
    
    # VELOCITY-BASED EDGE: If price is accelerating toward/away from strike
    # This is the predictive advantage from faster data sources
    velocity_adjustment = 0
    if btc_velocity['confidence'] >= 50:
        projected_price = btc_velocity['projected_60s']
        projected_distance = projected_price - strike_price
        current_distance_signed = distance['raw_distance']
        
        # Scale velocity adjustment by weight
        base_adjustment = 5 * (velocity_weight / 0.2)  # Normalize to default weight
        
        # If projected to move FURTHER from strike in our direction, boost confidence
        if current_distance_signed > 0 and projected_distance > current_distance_signed:
            velocity_adjustment = base_adjustment  # Boost YES confidence
        elif current_distance_signed < 0 and projected_distance < current_distance_signed:
            velocity_adjustment = -base_adjustment  # Boost NO confidence
        # If projected to cross strike, major signal
        elif current_distance_signed > 0 and projected_distance < 0:
            velocity_adjustment = -15  # Price likely to drop below strike
        elif current_distance_signed < 0 and projected_distance > 0:
            velocity_adjustment = 15  # Price likely to rise above strike
    
    # Check if we should even consider trading
    if not time_decay['should_trade']:
        return {
            'recommendation': 'SKIP',
            'reason': f"Too close to expiry ({time_decay['minutes_remaining']:.1f} min remaining)",
            'distance': distance,
            'time_decay': time_decay,
            'market_wisdom': market_wisdom,
            'volatility': volatility
        }
    
    # Calculate edge for both sides
    yes_entry = yes_ask  # What we'd pay for YES
    no_entry = 100 - yes_bid  # What we'd pay for NO
    
    try:
        yes_edge = calculate_edge_expectation('yes', yes_entry, distance, time_decay, market_wisdom, volatility)
        no_edge = calculate_edge_expectation('no', no_entry, distance, time_decay, market_wisdom, volatility)
    except Exception as e:
        logger.error(f"Error calculating edge: {e}")
        logger.debug(f"  distance type: {type(distance)}, keys: {distance.keys() if isinstance(distance, dict) else 'N/A'}")
        logger.debug(f"  market_wisdom type: {type(market_wisdom)}, keys: {market_wisdom.keys() if isinstance(market_wisdom, dict) else 'N/A'}")
        logger.debug(f"  volatility type: {type(volatility)}, keys: {volatility.keys() if isinstance(volatility, dict) else 'N/A'}")
        raise  # Re-raise so caller knows there was an error
    
    # Validate edge calculations returned numbers
    if not isinstance(yes_edge.get('expected_edge'), (int, float)):
        logger.error(f"yes_edge['expected_edge'] is {type(yes_edge.get('expected_edge'))}, not a number: {yes_edge.get('expected_edge')}")
        raise ValueError("Edge calculation returned non-numeric value")
    if not isinstance(no_edge.get('expected_edge'), (int, float)):
        logger.error(f"no_edge['expected_edge'] is {type(no_edge.get('expected_edge'))}, not a number: {no_edge.get('expected_edge')}")
        raise ValueError("Edge calculation returned non-numeric value")
    
    # FORCED DECISION: Always choose YES or NO (never SKIP)
    # Pick the side with higher expected edge
    if yes_edge['expected_edge'] >= no_edge['expected_edge']:
        recommendation = 'BUY_YES'
        selected_edge = yes_edge
        reason = f"Forced: YES edge {yes_edge['expected_edge']:.1f}% >= NO edge {no_edge['expected_edge']:.1f}%"
        entry_price = yes_entry
    else:
        recommendation = 'BUY_NO'
        selected_edge = no_edge
        reason = f"Forced: NO edge {no_edge['expected_edge']:.1f}% > YES edge {yes_edge['expected_edge']:.1f}%"
        entry_price = no_entry
    
    # Calculate execution time
    execution_time_ms = (time.time() - start_time) * 1000
    
    # Log signals
    logger.info(f"[DISTANCE] BTC ${current_btc_price:,.0f} vs Strike ${strike_price:,.0f}")
    logger.info(f"           Distance: ${distance['distance_dollars']:.0f} ({distance['direction']}) - {distance['zone']}")
    logger.info(f"[TIME] {time_decay['minutes_remaining']:.1f} min to expiry - Phase: {time_decay['phase']}")
    logger.info(f"[MOMENTUM] BTC {btc_momentum['direction']} (strength: {btc_momentum['strength']:.1f})")
    logger.info(f"[MARKET] Consensus: {market_wisdom['consensus']} (implied: {market_wisdom['implied_probability']:.0f}%)")
    logger.info(f"[VOLATILITY] {volatility['regime']} regime (${volatility['hourly_range']:.0f}/hr)")
    logger.info(f"[EDGE] YES: {yes_edge['expected_edge']:.1f}% | NO: {no_edge['expected_edge']:.1f}% (min: {min_edge*100:.0f}%)")
    logger.info(f"[VELOCITY] {btc_velocity['velocity']:+.0f}/min, {btc_velocity['acceleration']}, projected: ${btc_velocity['projected_60s']:,.0f}")
    logger.info(f"[DECISION] {recommendation} - {reason}")
    logger.info(f"[TIMING] Fast execution completed in {execution_time_ms:.0f}ms")
    
    return {
        'recommendation': recommendation,
        'reason': reason,
        'confidence': selected_edge['confidence'] if selected_edge else 0,
        'expected_edge': selected_edge['expected_edge'] if selected_edge else 0,
        
        # All signals
        'distance': distance,
        'time_decay': time_decay,
        'btc_momentum': btc_momentum,
        'btc_velocity': btc_velocity,  # Short-term velocity from Binance
        'velocity_adjustment': velocity_adjustment,  # Confidence adjustment from velocity
        'market_wisdom': market_wisdom,
        'volatility': volatility,
        'yes_edge': yes_edge,
        'no_edge': no_edge,
        
        # Tuned parameters used
        'tuned_params': {
            'min_edge': min_edge,
            'critical_distance': critical_dist,
            'safe_distance': safe_dist,
            'velocity_weight': velocity_weight,
            'contrarian_threshold': contrarian_threshold
        },
        
        # Key metrics
        'current_btc_price': current_btc_price,
        'strike_price': strike_price,
        'yes_bid': yes_bid,
        'yes_ask': yes_ask,
        'no_bid': 100 - yes_ask,
        'no_ask': 100 - yes_bid,
        
        # Execution timing
        'execution_time_ms': execution_time_ms,
        'framework': 'smart_signals_v2_fast'
    }


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Test with a sample market
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Simulate a market
    test_ticker = "KXBTCD-25DEC3012-T94500.00"
    test_yes_bid = 45
    test_yes_ask = 55
    test_btc_price = 94200
    
    print("Testing Smart Signals Module")
    print("=" * 60)
    
    signals = get_smart_signals(
        market_ticker=test_ticker,
        yes_bid=test_yes_bid,
        yes_ask=test_yes_ask,
        current_btc_price=test_btc_price
    )
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Recommendation: {signals.get('recommendation')}")
    print(f"Reason: {signals.get('reason')}")
    print(f"Confidence: {signals.get('confidence', 0):.1f}%")
    print(f"Expected Edge: {signals.get('expected_edge', 0):.1f}%")
