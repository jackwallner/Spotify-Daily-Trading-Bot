#!/usr/bin/env python3
"""
Kalshi Trading Bot - Spotify Daily Markets

This bot trades Spotify daily Kalshi markets using chart data from Kworb (kworb.net).
No Spotify API credentials required - Kworb provides real-time chart positions and stream counts.

Market selection is centralized in `spotify_daily_markets.py`.
Signal generation uses Kworb data in `spotify_daily_intelligence.py`.
"""

import os
import json
import time
from datetime import datetime, timezone
from kalshi_auth import initialize_kalshi_client

from spotify_daily_intelligence import (
    get_market_prices,
    playlist_delta_signal,
    select_market_for_track,
)

# NOTE: We keep the generic discovery module in-repo for future expansion, but
# this bot run is hard-targeted to the two configured Jan 2, 2026 events.

# Maximum cost per trade in cents ($1 = 100 cents)
MAX_TRADE_COST_CENTS = 100


def _parse_iso_ts(ts: str) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        # tolerate Z suffix
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def already_traded_event_today(event_ticker: str, day_utc: str) -> bool:
    """
    Guardrail: prevent double-trading the same Kalshi event on the same UTC day.

    DISABLED: This check is bypassed to allow multiple trade attempts.
    Useful when previous "Success" logs didn't actually execute on Kalshi.
    """
    # DISABLED - always return False to allow repeated trading
    return False
    
    if not event_ticker:
        return False
    try:
        if not os.path.exists("trades.jsonl"):
            return False
        with open("trades.jsonl", "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    trade = json.loads(line)
                except Exception:
                    continue

                ts = _parse_iso_ts(trade.get("timestamp", ""))
                if not ts:
                    continue
                if ts.astimezone(timezone.utc).date().isoformat() != day_utc:
                    continue

                decision_log = trade.get("decision_log") or {}
                if isinstance(decision_log, str):
                    try:
                        decision_log = json.loads(decision_log)
                    except Exception:
                        decision_log = {}
                if not isinstance(decision_log, dict):
                    decision_log = {}

                if str(decision_log.get("event_ticker", "")).lower() == str(event_ticker).lower():
                    # DISABLED: Allow repeated trading
                    pass  # return True
        return False
    except Exception:
        # If we can't read logs, don't block trading.
        return False
    
    # NOTE: This function now always returns False (disabled duplicate trade check)
    # to allow multiple trade attempts when previous "Success" didn't execute


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

        # Only mark as Success if we got an order_id back from Kalshi
        success = bool(order_response and order_id)
        
        if not success:
            return {
                "status": "Failed",
                "price": None,
                "contracts": None,
                "order_response": order_response,
                "order_id": None,
            }
        
        # Wait for order to fill and get actual executed price
        import time
        print(f"[ORDER] Waiting 10 seconds for order to fill...")
        time.sleep(10)
        
        actual_price = limit_price
        actual_contracts = contract_count
        
        try:
            # Get order details to see actual fill price
            order_details = kalshi_client.get_order(order_id)
            
            # Extract actual fill info
            if hasattr(order_details, "order"):
                order_obj = order_details.order
            else:
                order_obj = order_details
            
            # Get yes_price or no_price depending on side
            if side == "yes":
                filled_price = getattr(order_obj, "yes_price", None)
            else:
                filled_price = getattr(order_obj, "no_price", None)
            
            # Also try getting from fills
            if not filled_price and hasattr(order_obj, "fills"):
                fills = getattr(order_obj, "fills", [])
                if fills and len(fills) > 0:
                    first_fill = fills[0]
                    filled_price = getattr(first_fill, "price", None)
            
            # Get filled count
            filled_count = getattr(order_obj, "filled_count", None) or getattr(order_obj, "count", None)
            
            if filled_price:
                actual_price = int(filled_price)
                print(f"[ORDER] ✓ Filled at {actual_price}¢ (limit was {limit_price}¢)")
            
            if filled_count:
                actual_contracts = int(filled_count)
                
        except Exception as e:
            print(f"[ORDER] Could not fetch fill details: {e}")
            print(f"[ORDER] Using limit price {limit_price}¢ as fallback")
        
        return {
            "status": "Success",
            "price": actual_price,
            "contracts": actual_contracts,
            "order_response": order_response,
            "order_id": order_id,
        }
    except Exception as e:
        print(f"Error placing trade for {getattr(market, 'ticker', 'UNKNOWN')}: {e}")
        return {"status": "Failed", "price": None, "contracts": None, "order_response": None, "order_id": None}


def main():
    """
    Main trading loop (simplified).

    Target exactly two Spotify daily Kalshi events for the current UTC date:
    - kxspotifyd-YYmonDD        (Top US song)
    - kxspotifyglobald-YYmonDD  (Top Global song)

    Override (optional):
    - SPOTIFY_MARKET_DATE=26jan02  # forces YYmonDD instead of today's UTC date

    Signal:
    - Query Kworb for Spotify daily charts (US + Global).
    - Compare #1 vs #2 stream counts.
    - Pick predicted winner (always #1), then find matching Kalshi contract and buy YES.
    """
    print(f"Starting trading bot at {datetime.utcnow().isoformat()}")

    print("\n" + "="*70)
    print("[SPOTIFY DAILY] Starting execution")
    print("="*70)
    
    # Initialize Kalshi client
    kalshi_client = initialize_kalshi_client()

    try:
        buffer_cents = int(os.getenv("LIMIT_PRICE_BUFFER_CENTS", "2"))
    except Exception:
        buffer_cents = 2
    buffer_cents = max(0, buffer_cents)

    def _date_suffix(dt: datetime) -> str:
        # Format: 26jan02
        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        yy = f"{dt.year % 100:02d}"
        mon = months[dt.month - 1]
        dd = f"{dt.day:02d}"
        return f"{yy}{mon}{dd}"

    # Use Eastern Time (ET) for determining market date, not UTC
    # Spotify charts and Kalshi markets are based on ET calendar days
    from zoneinfo import ZoneInfo
    et_tz = ZoneInfo("America/New_York")
    now_et = datetime.now(et_tz)
    
    override = os.getenv("SPOTIFY_MARKET_DATE", "").strip().lower()
    suffix = override if override else _date_suffix(now_et)
    today_et = now_et.date().isoformat()
    
    print(f"[TIME] Current ET: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"[TIME] Trading markets for: {suffix}")

    target_events = [
        {"event_ticker": f"kxspotifyd-{suffix}", "region": "US", "label": "Top US song"},
        {"event_ticker": f"kxspotifyglobald-{suffix}", "region": "Global", "label": "Top Global song"},
    ]

    trades_made: list[dict] = []

    for ev in target_events:
        event_ticker = ev["event_ticker"]
        region = ev["region"]
        label = ev["label"]

        print(f"\n[EVENT] {event_ticker} ({label})")

        try:
            if already_traded_event_today(event_ticker, today_et):
                log_trade(
                    event_ticker,
                    "SKIPPED",
                    f"Already traded this event today ({today_et})",
                    asset="SPOTIFY",
                    decision_log={"reason": "already_traded_today", "event_ticker": event_ticker, "day_et": today_et},
                )
                continue

            # 1) Spotify signal
            signal = playlist_delta_signal(region)
            if signal.get("error"):
                log_trade(event_ticker, "ERROR", f"Signal error: {signal['error']}", asset="SPOTIFY", decision_log=signal)
                continue

            predicted = signal["predicted"]
            track_title = predicted.get("title", "")
            track_artist = predicted.get("artist", "")

            print(f"[SPOTIFY] Predicted #1 ({region}): {track_title} — {track_artist}")
            print(f"[SPOTIFY] Rationale: {signal.get('rationale')} | popΔ={signal.get('pop_delta')} (thresh={signal.get('pop_delta_threshold')})")

            # 2) Fetch Kalshi markets for the event
            # Try lowercase first, then uppercase
            markets = []
            for ticker_variant in [event_ticker, event_ticker.upper()]:
                try:
                    markets_resp = kalshi_client.get_markets(event_ticker=ticker_variant, status="open", limit=200)
                    markets = getattr(markets_resp, "markets", None) or []
                    if markets:
                        print(f"[KALSHI] Found {len(markets)} markets for event (using ticker: {ticker_variant})")
                        break
                except Exception as e:
                    print(f"[KALSHI] No markets found with ticker {ticker_variant}")
                    continue
            
            if not markets:
                log_trade(event_ticker, "NO TRADE", "No open markets found for event", asset="SPOTIFY", decision_log=signal)
                continue

            # 3) Pick the contract market for the predicted track
            print(f"[MATCHING] Searching {len(markets)} markets for: '{track_title}' by {track_artist}")
            chosen_market = select_market_for_track(markets, track_title=track_title, track_artist=track_artist)
            
            if not chosen_market and len(markets) > 0:
                # Debug: Show first 5 market titles
                print(f"[DEBUG] Failed to match. First 5 market titles:")
                for i, m in enumerate(markets[:5], 1):
                    m_title = getattr(m, "title", "N/A")
                    m_ticker = getattr(m, "ticker", "N/A")
                    print(f"  {i}. {m_ticker}: {m_title}")
            
            if not chosen_market:
                # If event only has one market, fall back to it.
                if len(markets) == 1:
                    chosen_market = markets[0]
                else:
                    log_trade(event_ticker, "NO TRADE", "Could not match track to a market contract", asset="SPOTIFY", decision_log={
                        **signal,
                        "candidate_count": len(markets),
                    })
                    continue

            ticker = getattr(chosen_market, "ticker", "")
            m_title = getattr(chosen_market, "title", "")
            print(f"[KALSHI] Selected contract: {ticker}")
            if m_title:
                print(f"[KALSHI] Title: {m_title}")

            # 4) Entry price (position checks disabled - will always attempt trade)
            prices = get_market_prices(kalshi_client, ticker)
            yes_ask = prices.get("yes_ask", 50)
            limit_price = min(99, max(1, int(yes_ask) + buffer_cents))

            # Position check DISABLED - allow multiple trades per market
            # position_check = check_existing_positions(kalshi_client, ticker)
            # if position_check.get("has_position") and position_check.get("side") == "no":
            #     log_trade(ticker, "SKIPPED", "Conflict: already hold NO", asset="SPOTIFY", decision_log={"reason": "position_conflict"})
            #     continue

            # 5) Trade: BUY YES
            trade_result = place_trade(kalshi_client, chosen_market, side="yes", limit_price=limit_price, contract_count=1)
            status = trade_result.get("status", "Failed")

            action = f"Buy YES (spotify_playlist_delta_v1)"
            decision_log = {
                **signal,
                "event_ticker": event_ticker,
                "region": region,
                "selected_market": ticker,
                "selected_market_title": m_title,
                "prices": prices,
                "limit_price": limit_price,
                "order_id": trade_result.get("order_id"),
            }

            log_trade(
                ticker,
                action,
                status,
                asset="SPOTIFY",
                price=trade_result.get("price"),
                contracts=trade_result.get("contracts"),
                decision_log=decision_log,
            )

            if status == "Success":
                trades_made.append({"ticker": ticker, "action": action, "price": trade_result.get("price"), "contracts": trade_result.get("contracts")})
        except Exception as e:
            log_trade(event_ticker, "ERROR", f"Event failed: {e}", asset="SPOTIFY")

    print(f"\n{'='*70}")
    print(f"[SUMMARY] Spotify daily run completed - Trades made: {len(trades_made)}")
    for t in trades_made:
        print(f"  • {t['ticker']}: {t['action']} {t.get('contracts')} @ {t.get('price')}¢")
    print(f"{'='*70}\n")
    print(f"Trading bot completed at {datetime.utcnow().isoformat()}")


if __name__ == "__main__":
    main()
