#!/usr/bin/env python3
"""
Kalshi Trading Bot - Spotify Daily Markets

This project is repurposed to focus on discovering and trading Spotify daily
Kalshi markets. Market selection is centralized in `spotify_daily_markets.py`.
"""

import os
import json
import time
from datetime import datetime, timedelta, timezone
from kalshi_auth import initialize_kalshi_client

from spotify_daily_markets import SpotifyDailyMarketConfig, discover_spotify_daily_markets
from spotify_daily_intelligence import (
    SpotifyDecisionThresholds,
    get_spotify_daily_gemini_decision,
    get_spotify_daily_signals,
)

# Maximum cost per trade in cents ($1 = 100 cents)
MAX_TRADE_COST_CENTS = 100


def check_existing_positions(kalshi_client, market_ticker):
    """
    Check if we already have an open position in this market.
    Prevents buying YES if we already bought NO (or vice versa).
    
    Args:
        kalshi_client: Kalshi API client
        market_ticker: Market ticker to check
    
    Returns:
        dict with 'has_position' (bool), 'side' ('yes'/'no'/None), 'contracts' (int)
    """
    try:
        positions_resp = kalshi_client.get_positions()
        
        if not positions_resp or not hasattr(positions_resp, 'positions'):
            print(f"[POSITION CHECK] Could not retrieve positions")
            return {'has_position': False, 'side': None, 'contracts': 0}
        
        # Check if market_ticker is in our positions
        for position in positions_resp.positions:
            if hasattr(position, 'ticker') and position.ticker == market_ticker:
                # We have a position in this market
                yes_contracts = getattr(position, 'yes_contracts', 0) or 0
                no_contracts = getattr(position, 'no_contracts', 0) or 0
                
                print(f"[POSITION CHECK] {market_ticker}: YES={yes_contracts}, NO={no_contracts}")
                
                if yes_contracts > 0:
                    return {'has_position': True, 'side': 'yes', 'contracts': yes_contracts}
                elif no_contracts > 0:
                    return {'has_position': True, 'side': 'no', 'contracts': no_contracts}
        
        # No position found
        print(f"[POSITION CHECK] {market_ticker}: No existing position")
        return {'has_position': False, 'side': None, 'contracts': 0}
        
    except Exception as e:
        print(f"[POSITION CHECK] Error checking positions: {e}")
        return {'has_position': False, 'side': None, 'contracts': 0}


def log_trade(market_ticker, action, status, asset=None, sentiment=None, price=None, contracts=None, decision_log=None):
    """Log trade to trades.log (legacy CSV) and trades.jsonl (preferred).

    Writes one JSON object per line to `trades.jsonl` (append) and preserves
    the existing CSV-style `trades.log` for backwards compatibility.
    """
    # Auto-detect asset from ticker if not provided
    if asset is None:
        asset = 'SPOTIFY'

    timestamp = datetime.utcnow().isoformat()

    # Build JSON object for JSONL
    trade_obj = {
        'timestamp': timestamp,
        'market': market_ticker,
        'action': action,
        'status': status,
        'asset': asset,
        'sentiment': sentiment,
        'price': price,
        'contracts': contracts,
        'order_id': decision_log.get('order_id') if isinstance(decision_log, dict) else None,
        'decision_log': decision_log
    }

    # Append to trades.jsonl (machine readable)
    try:
        with open('trades.jsonl', 'a') as jf:
            jf.write(json.dumps(trade_obj, default=str) + "\n")
    except Exception as e:
        print(f"Warning: Failed to write trades.jsonl: {e}")

    # Also append to legacy trades.log (CSV-like) for compatibility
    try:
        sentiment_str = str(sentiment) if sentiment is not None else ''
        price_str = str(price) if price is not None else ''
        contracts_str = str(contracts) if contracts is not None else ''
        log_entry = f"{timestamp}, {market_ticker}, {action}, {status}, {asset}, {sentiment_str}, {price_str}, {contracts_str}\n"
        with open('trades.log', 'a') as log_file:
            log_file.write(log_entry)
    except Exception as e:
        print(f"Warning: Failed to append trades.log: {e}")

    print(f"Logged: {json.dumps(trade_obj)}")


# initialize_kalshi_client is now imported from kalshi_auth module




def fetch_spotify_daily_markets(client, cfg: SpotifyDailyMarketConfig):
    """Discover Spotify daily markets using shared selection rules."""
    try:
        return discover_spotify_daily_markets(client, cfg, status="open")
    except Exception as e:
        print(f"Error discovering Spotify daily markets: {e}")
        return []


# select_optimal_market is no longer needed - we use closest to BRTI/ERTI from find_next_hour_markets


def place_trade(kalshi_client, market, side: str, limit_price: int, contract_count: int):
    """
    Place a limit buy on YES/NO with a hard $1 cap per order.
    Returns dict with status/price/contracts/order_id.
    """
    try:
        side = (side or "").lower().strip()
        if side not in ("yes", "no"):
            return {"status": "Failed", "price": None, "contracts": None, "order_response": None, "order_id": None}

        limit_price = int(limit_price)
        contract_count = int(contract_count)
        if limit_price < 1 or limit_price > 99 or contract_count < 1:
            return {"status": "Failed", "price": None, "contracts": None, "order_response": None, "order_id": None}

        # Enforce $1 cap
        max_affordable = MAX_TRADE_COST_CENTS // limit_price
        if max_affordable <= 0:
            return {"status": "Failed", "price": None, "contracts": None, "order_response": None, "order_id": None}
        contract_count = min(contract_count, max_affordable)

        ticker = getattr(market, "ticker", None)
        if not ticker:
            return {"status": "Failed", "price": None, "contracts": None, "order_response": None, "order_id": None}

        print(f"[ORDER] BUY {side.upper()} {contract_count} @ {limit_price}¢ (cap ${MAX_TRADE_COST_CENTS/100:.2f})")

        order_response = None

        # Try multiple SDK method signatures.
        try:
            if side == "yes":
                order_response = kalshi_client.create_order(
                    ticker=ticker,
                    action="buy",
                    side="yes",
                    count=contract_count,
                    type="limit",
                    yes_price=limit_price,
                )
            else:
                order_response = kalshi_client.create_order(
                    ticker=ticker,
                    action="buy",
                    side="no",
                    count=contract_count,
                    type="limit",
                    no_price=limit_price,
                )
        except Exception:
            try:
                order_response = kalshi_client.create_order(
                    ticker=ticker,
                    action="buy",
                    side=side,
                    count=contract_count,
                    type="limit",
                    price=limit_price,
                )
            except Exception:
                order_response = kalshi_client.create_order(
                    ticker=ticker,
                    action="buy",
                    side=side,
                    count=contract_count,
                    price=limit_price,
                )

        # Best-effort order_id extraction
        order_id = None
        try:
            if hasattr(order_response, "order") and hasattr(order_response.order, "order_id"):
                order_id = order_response.order.order_id
            elif hasattr(order_response, "order_id"):
                order_id = order_response.order_id
            elif isinstance(order_response, dict):
                if isinstance(order_response.get("order"), dict):
                    order_id = order_response["order"].get("order_id")
                order_id = order_id or order_response.get("order_id")
        except Exception:
            order_id = None

        return {
            "status": "Success" if order_response else "Failed",
            "price": limit_price,
            "contracts": contract_count,
            "order_response": order_response,
            "order_id": order_id,
        }
    except Exception as e:
        print(f"Error placing trade for {getattr(market, 'ticker', 'UNKNOWN')}: {e}")
        return {"status": "Failed", "price": None, "contracts": None, "order_response": None, "order_id": None}


def main():
    """
    Main trading loop - Two-phase execution for optimal latency
    
    PHASE 1: Model Tuning (SLOW - can take 2-5s)
    - Gemini analyzes recent performance
    - Adjusts model parameters
    - Saves tuned config
    
    PHASE 2: Fast Execution (FAST - target <500ms)
    - Fetch price from Binance (10-50ms)
    - Run model with pre-tuned params (no AI calls)
    - Execute immediately if edge criteria met
    """
    print(f"Starting trading bot at {datetime.utcnow().isoformat()}")
    
    # ============= CHECK FOR FINALIZED TRADES WITH P&L DATA =============
    print("\n" + "="*70)
    print("[FINALIZED RESULTS CHECK] Checking trades for finalized p&l data")
    print("="*70)
    
    try:
        from kalshi_order_history import enrich_trades_with_market_outcomes
        import json
        
        # Load trades from trades.jsonl (dicts, not SDK objects)
        trades = []
        if os.path.exists('trades.jsonl'):
            with open('trades.jsonl', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            trades.append(json.loads(line))
                        except:
                            pass
        
        if trades:
            # Filter for executed trades (have order_id) with unknown result
            unknown_trades = [t for t in trades if t.get('order_id') and t.get('settlement', {}).get('status') not in ['Won', 'Lost']]
            
            if unknown_trades:
                print(f"\nFound {len(unknown_trades)} executed trades pending settlement. Checking for finalized data...")
                
                # Enrich with market outcomes
                enriched, count = enrich_trades_with_market_outcomes(unknown_trades)
                
                if count > 0:
                    print(f" ✓ Updated {count} trades with finalized outcomes")
                    
                    # Merge enriched trades back
                    enriched_markets = {t.get('market'): t for t in enriched if t.get('market')}
                    for i, trade in enumerate(trades):
                        market = trade.get('market')
                        if market in enriched_markets:
                            trades[i] = enriched_markets[market]
                    
                    # Save back to file
                    with open('trades.jsonl', 'w') as f:
                        for trade in trades:
                            f.write(json.dumps(trade) + '\n')
                    print(f" ✓ Saved updated trade data to trades.jsonl")
            else:
                print(" ✓ All trades have known settlement status")
        else:
            print(" No trade history found")
    except ImportError:
        print(" ⚠ Could not import order history functions")
    except Exception as e:
        print(f" ⚠ Error checking finalized results: {e}")
    
    # ============= PHASE 1: ANALYZE (No Auto-Tuning) =============
    # Gemini analyzes performance and logs insights
    # Model factors stay fixed - YOU control model_config.json manually
    model_config = None
    try:
        from model_tuner import run_analysis
        model_config = run_analysis()
        print(f"[PHASE 1 COMPLETE] Analysis logged, using fixed model config")
    except ImportError:
        print("[PHASE 1] Model analyzer not available")
    except Exception as e:
        print(f"[PHASE 1] Analysis failed: {e}")
    
    # ============= PHASE 2: FAST EXECUTION =============
    # No Gemini calls from here - pure mechanical execution
    print("\n" + "="*70)
    print("[PHASE 2: FAST EXECUTION] Starting fast execution phase")
    print("="*70)
    
    # Initialize Kalshi client
    kalshi_client = initialize_kalshi_client()
    
    cfg = SpotifyDailyMarketConfig.from_env()
    thresholds = SpotifyDecisionThresholds()

    try:
        max_markets = int(os.getenv("SPOTIFY_DAILY_MAX_MARKETS_PER_RUN", "3"))
    except Exception:
        max_markets = 3
    max_markets = max(1, max_markets)

    markets = fetch_spotify_daily_markets(kalshi_client, cfg)
    if not markets:
        print("No Spotify daily markets found (check SPOTIFY_MARKET_* env vars).")
        log_trade("SPOTIFY-DAILY-MARKET-NOT-FOUND", "NO TRADE", "Market Not Found", asset="SPOTIFY")
        print(f"Trading bot completed at {datetime.utcnow().isoformat()}")
        return

    markets = markets[:max_markets]
    trades_made = []

    for market in markets:
        ticker = getattr(market, "ticker", "")
        title = getattr(market, "title", "")
        print(f"\n[SPOTIFY DAILY] {ticker}")
        if title:
            print(f"Title: {title}")

        try:
            signals = get_spotify_daily_signals(kalshi_client, market, thresholds=thresholds)
            gemini = get_spotify_daily_gemini_decision(signals)

            decision = (gemini.get("decision") if gemini else signals.get("recommendation")) or "SKIP"
            decision = str(decision).upper()

            framework = signals.get("framework", "spotify_daily_v1")
            prices = signals.get("prices", {}) or {}
            composite = signals.get("composite_score", 50)

            print(f"[SIGNALS] Composite {composite:.1f}/100 | Model {signals.get('recommendation')} | Spread {signals.get('market_wisdom', {}).get('spread')}c")
            if gemini:
                print(f"[GEMINI] {gemini.get('model')}: {decision} ({gemini.get('confidence')}/10)")

            if decision not in ("BUY_YES", "BUY_NO"):
                log_trade(
                    ticker,
                    "NO TRADE",
                    f"Decision: {decision}",
                    asset="SPOTIFY",
                    decision_log={
                        "framework": framework,
                        "decision": decision,
                        "model_recommendation": signals.get("recommendation"),
                        "model_reason": signals.get("reason"),
                        "model_confidence": signals.get("confidence"),
                        "gemini": gemini,
                        "composite_score": composite,
                        "prices": prices,
                    },
                )
                continue

            side = "yes" if decision == "BUY_YES" else "no"
            ask = prices.get("yes_ask") if side == "yes" else prices.get("no_ask")
            try:
                buffer_cents = int(os.getenv("LIMIT_PRICE_BUFFER_CENTS", "2"))
            except Exception:
                buffer_cents = 2
            limit_price = min(99, max(1, int(ask or 50) + max(0, buffer_cents)))

            position_check = check_existing_positions(kalshi_client, ticker)
            if position_check.get("has_position"):
                existing_side = position_check.get("side")
                existing_contracts = position_check.get("contracts", 0)
                if existing_side and existing_side != side:
                    log_trade(
                        ticker,
                        "SKIPPED",
                        f"Conflict: Own {existing_contracts} {existing_side.upper()}, signal wants {side.upper()}",
                        asset="SPOTIFY",
                        decision_log={
                            "reason": "position_conflict",
                            "existing_side": existing_side,
                            "existing_contracts": existing_contracts,
                            "signal_side": side,
                        },
                    )
                    continue

            trade_result = place_trade(kalshi_client, market, side=side, limit_price=limit_price, contract_count=1)
            status = trade_result.get("status", "Failed")
            exec_price = trade_result.get("price")
            exec_contracts = trade_result.get("contracts")
            order_id = trade_result.get("order_id")

            action = f"Buy {side.upper()} ({framework})"
            log_trade(
                ticker,
                action,
                status,
                asset="SPOTIFY",
                price=exec_price,
                contracts=exec_contracts,
                decision_log={
                    "framework": framework,
                    "decision": decision,
                    "model_recommendation": signals.get("recommendation"),
                    "model_reason": signals.get("reason"),
                    "model_confidence": signals.get("confidence"),
                    "gemini": gemini,
                    "composite_score": composite,
                    "prices": prices,
                    "limit_price": limit_price,
                    "execution_price": exec_price,
                    "execution_contracts": exec_contracts,
                    "order_id": order_id,
                },
            )

            if status == "Success":
                trades_made.append({"ticker": ticker, "action": action, "price": exec_price, "contracts": exec_contracts})

        except Exception as e:
            log_trade(ticker, "ERROR", f"Signal/trade failed: {e}", asset="SPOTIFY")

    print(f"\n{'='*70}")
    print(f"[SUMMARY] Spotify daily run completed - Trades made: {len(trades_made)}")
    for t in trades_made:
        print(f"  • {t['ticker']}: {t['action']} {t.get('contracts')} @ {t.get('price')}¢")
    print(f"{'='*70}\n")
    print(f"Trading bot completed at {datetime.utcnow().isoformat()}")


if __name__ == "__main__":
    main()
