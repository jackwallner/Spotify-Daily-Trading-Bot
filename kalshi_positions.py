#!/usr/bin/env python3
"""
Kalshi Position Query and Settlement Enrichment Module
Queries current open positions and enriches trade history with settlement status.
"""

import json
import os
import requests
from datetime import datetime, timezone

from kalshi_auth import initialize_kalshi_client

# Cache settings
POSITIONS_CACHE_FILE = 'positions_cache.json'
CACHE_TTL_SECONDS = 900  # 15 minutes


def create_auth_headers(url: str, method: str = "GET") -> dict:
    """Convenience wrapper to sign raw HTTP requests."""
    client = initialize_kalshi_client()
    return client.kalshi_auth.create_auth_headers(method, url)


def get_market_raw(ticker: str) -> dict:
    """Get market data via raw API call (needed for statuses the SDK may not accept)."""
    url = f"https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}"
    headers = create_auth_headers(url, method="GET")
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    return data.get('market', {})


def query_kalshi_positions():
    """Query Kalshi API for current positions, with simple JSON cache fallback."""
    try:
        client = initialize_kalshi_client()
        positions_resp = client.get_positions()

        # Custom JSON encoder to handle datetime objects from SDK
        def json_serializer(obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            elif hasattr(obj, '__dict__'):
                return obj.__dict__
            return str(obj)

        cache_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'positions': positions_resp.to_dict() if hasattr(positions_resp, 'to_dict') else str(positions_resp),
            'source': 'live'
        }
        try:
            with open(POSITIONS_CACHE_FILE, 'w') as f:
                json.dump(cache_data, f, default=json_serializer)
        except Exception as cache_err:
            print(f"Warning: Could not save positions cache: {cache_err}")

        return positions_resp
    except Exception as e:
        print(f"Warning: Failed to query Kalshi positions: {e}")
        # Try cache
        try:
            if os.path.exists(POSITIONS_CACHE_FILE):
                with open(POSITIONS_CACHE_FILE, 'r') as f:
                    cache_data = json.load(f)
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(cache_data['timestamp'].replace('Z', '+00:00'))).total_seconds()
                    if age < CACHE_TTL_SECONDS * 2:
                        print(f"Using cached positions (age: {int(age)}s)")
                        return cache_data.get('positions')
        except Exception as cache_err:
            print(f"Warning: Could not load positions cache: {cache_err}")
        return None


def enrich_trades_with_settlement(trades_list):
    """
    Enrich trade list with settlement status using fills/settlements first, then positions, then raw market.
    Returns (enriched_trades_list, source_indicator).
    """
    if not trades_list:
        return trades_list, 'Unknown'

    client = None
    fills_by_order_id = {}
    settlements_by_order_id = {}
    position_map = {}
    source_indicator = 'Unknown'

    # Try exact fills/settlements
    try:
        client = initialize_kalshi_client()
        print("Querying order fills...")
        fills_resp = client.get_fills()
        fills = fills_resp.fills if hasattr(fills_resp, 'fills') else []

        print("Querying settlements...")
        settlements_resp = client.get_settlements()
        settlements = settlements_resp.settlements if hasattr(settlements_resp, 'settlements') else []

        for fill in fills:
            order_id = getattr(fill, 'order_id', None) or (fill.get('order_id') if isinstance(fill, dict) else None)
            if not order_id:
                continue
            fills_by_order_id.setdefault(order_id, []).append(fill)

        for settlement in settlements:
            order_id = getattr(settlement, 'order_id', None) or (settlement.get('order_id') if isinstance(settlement, dict) else None)
            if order_id:
                settlements_by_order_id[order_id] = settlement

        if fills or settlements:
            source_indicator = 'Fills+Settlements'
            print(f"Settlement data source: {source_indicator}")
    except Exception as e:
        print(f"Warning: Failed to query fills/settlements: {e}")

    # Fallback to positions when we have no settlements
    if not settlements_by_order_id:
        print("Querying Kalshi positions...")
        positions_data = query_kalshi_positions()
        if positions_data is None:
            print("Settlement data source: Unknown")
            for trade in trades_list:
                trade['settlement'] = {
                    'status': 'Unknown',
                    'pnl': 0,
                    'details': 'Position query failed'
                }
            return trades_list, 'Unknown'

        try:
            positions_list = []
            if isinstance(positions_data, dict) and 'positions' in positions_data:
                positions_list = positions_data['positions']
            elif isinstance(positions_data, list):
                positions_list = positions_data

            for pos in positions_list:
                ticker = getattr(pos, 'ticker', None) or (pos.get('ticker') if isinstance(pos, dict) else None)
                if ticker:
                    position_map[ticker] = pos
            source_indicator = 'Positions'
        except Exception as e:
            print(f"Warning: Error parsing positions: {e}")
            source_indicator = 'Unknown'
        print(f"Settlement data source: {source_indicator}")

    # Enrich each trade
    for trade in trades_list:
        existing_settlement = trade.get('settlement', {})
        # Preserve Won/Lost (final outcomes), but always refresh Pending to check if settled
        if existing_settlement.get('status') in ['Won', 'Lost']:
            continue
        
        # Skip trades that were never executed (no order_id)
        order_id = trade.get('order_id')
        if not order_id:
            # For non-executed trades, only set settlement if not already set
            if not existing_settlement.get('status'):
                trade['settlement'] = {
                    'status': 'Unknown',
                    'pnl': 0,
                    'details': 'Trade not executed'
                }
            continue

        market = trade.get('market')
        action = trade.get('action', '').upper()

        if order_id and order_id in settlements_by_order_id:
            settlement = settlements_by_order_id[order_id]
            revenue_cents = getattr(settlement, 'revenue', None) or (settlement.get('revenue') if isinstance(settlement, dict) else 0)
            fee_raw = getattr(settlement, 'fee_cost', None) or (settlement.get('fee_cost') if isinstance(settlement, dict) else 0)

            # fee_cost from API is already dollars; if an unexpected large value shows up, fall back to cents → dollars
            fee_cost = float(fee_raw or 0)
            if fee_cost > 100:  # defensive: treat as cents if something looks off
                fee_cost = fee_cost / 100.0

            cost_paid = 0.0
            if order_id in fills_by_order_id:
                for fill in fills_by_order_id[order_id]:
                    count = getattr(fill, 'count', None) or (fill.get('count') if isinstance(fill, dict) else 0)
                    yes_price = getattr(fill, 'yes_price', None) or (fill.get('yes_price') if isinstance(fill, dict) else 0)
                    no_price = getattr(fill, 'no_price', None) or (fill.get('no_price') if isinstance(fill, dict) else 0)
                    price_cents = yes_price or no_price or 0
                    cost_paid += (price_cents / 100.0) * count

            revenue = (revenue_cents or 0) / 100.0
            pnl = revenue - cost_paid - fee_cost
            # Use a tiny epsilon to avoid rounding classifying ~0 as Lost/Won
            if pnl > 0.0001:
                status = 'Won'
            elif pnl < -0.0001:
                status = 'Lost'
            else:
                status = 'Break-even'

            trade['settlement'] = {
                'status': status,
                'pnl': round(pnl, 2),
                'revenue': round(revenue, 2),
                'cost': round(cost_paid, 2),
                'fee': round(fee_cost, 2),
                'details': f'Settled via settlements API: revenue=${revenue:.2f}, cost=${cost_paid:.2f}, fee=${fee_cost:.2f}'
            }
        elif market in position_map:
            pos = position_map[market]
            exposure = getattr(pos, 'market_exposure_dollars', None) or getattr(pos, 'market_exposure', None)
            # Preserve existing cost if already calculated
            existing_cost = existing_settlement.get('cost', 0)
            if not existing_cost and trade.get('price'):
                existing_cost = (trade.get('price', 0) / 100.0) * trade.get('contracts', 1)
            trade['settlement'] = {
                'status': 'Open',
                'pnl': 0,
                'cost': existing_cost,
                'details': f'Position open; exposure={exposure}'
            }
        else:
            try:
                client = client or initialize_kalshi_client()
                try:
                    market_data = client.get_market(ticker=market)
                    market_dict = market_data.market.to_dict() if hasattr(market_data.market, 'to_dict') else market_data.market
                except Exception as sdk_error:
                    if 'validation error' in str(sdk_error).lower() or 'finalized' in str(sdk_error).lower():
                        market_dict = get_market_raw(market)
                    else:
                        raise

                market_status = market_dict.get('status')
                result = market_dict.get('result')

                if market_status in ['finalized', 'settled', 'closed'] and result:
                    trade_price = trade.get('price', 99) or trade.get('decision_log', {}).get('execution_price', 99)
                    trade_contracts = trade.get('contracts', 1)
                    cost_paid = (trade_price / 100.0) * trade_contracts

                    if result.lower() == 'yes':
                        if 'YES' in action:
                            payout = 1.00 * trade_contracts
                            pnl = payout - cost_paid
                            status = 'Won'
                        else:
                            pnl = -cost_paid
                            status = 'Lost'
                    elif result.lower() == 'no':
                        if 'NO' in action:
                            payout = 1.00 * trade_contracts
                            pnl = payout - cost_paid
                            status = 'Won'
                        else:
                            pnl = -cost_paid
                            status = 'Lost'
                    else:
                        status = 'Unknown'
                        pnl = 0

                    trade['settlement'] = {
                        'status': status,
                        'pnl': round(pnl, 2),
                        'details': f'Market result: {result}'
                    }
                else:
                    # Preserve existing cost if already calculated
                    existing_cost = existing_settlement.get('cost', 0)
                    if not existing_cost and trade.get('price'):
                        existing_cost = (trade.get('price', 0) / 100.0) * trade.get('contracts', 1)
                    trade['settlement'] = {
                        'status': 'Open',
                        'pnl': 0,
                        'cost': existing_cost,
                        'details': f'Market status: {market_status}'
                    }
            except Exception as e:
                print(f"Warning: Error fetching market data: {e}")
                trade['settlement'] = {
                    'status': 'Unknown',
                    'pnl': 0,
                    'details': 'Error fetching market data'
                }

    return trades_list, source_indicator
