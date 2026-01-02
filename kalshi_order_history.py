#!/usr/bin/env python3
"""
Kalshi Order History Query Module
Fetches actual order data and market settlements from Kalshi API
"""

import json
from datetime import datetime, timezone
from kalshi_auth import initialize_kalshi_client


def get_order_history():
    """
    Fetch all orders from Kalshi API.
    
    Note: The current API key may not have permissions for order history.
    As a fallback, order data is stored in trades.jsonl decision_log with execution_price.
    
    Returns:
        list: List of order objects with actual execution details
    """
    try:
        client = initialize_kalshi_client()
        orders_response = client.get_orders()
        
        if hasattr(orders_response, 'orders'):
            orders = orders_response.orders
        elif isinstance(orders_response, list):
            orders = orders_response
        else:
            orders = []
        
        print(f"✓ Fetched {len(orders) if orders else 0} orders from Kalshi API")
        return orders if orders else []
        
    except Exception as e:
        print(f"Note: Order history not available from API ({type(e).__name__})")
        print(f"      Using execution_price from trades.jsonl decision_log instead")
        return []


def enrich_trades_with_order_data(trades_list):
    """
    Enrich trades with actual execution data from Kalshi order history.
    
    The execution_price is captured when orders are placed and stored in decision_log.
    This function ensures the top-level 'price' field reflects that.
    
    Args:
        trades_list: List of trade dicts with 'market' field
    
    Returns:
        tuple: (enriched_trades_list, enrichment_count)
    """
    if not trades_list:
        return trades_list, 0
    
    # Use execution_price from decision_log (captured at trade time)
    enrichment_count = 0
    for trade in trades_list:
        decision_log = trade.get('decision_log', {})
        if isinstance(decision_log, dict) and 'execution_price' in decision_log:
            exec_price = decision_log.get('execution_price')
            # Ensure top-level price field has the execution price
            if exec_price and (trade.get('price') != exec_price):
                trade['price'] = exec_price
                enrichment_count += 1
    
    if enrichment_count > 0:
        print(f"✓ Using execution_price from decision_log for {enrichment_count} trades")
    
    return trades_list, enrichment_count


def get_market_outcome(market_ticker):
    """
    Get the market resolution outcome from Kalshi API.
    
    Args:
        market_ticker: Market ticker string (e.g., "KXBTCD-25DEC2922-T86999.99")
    
    Returns:
        dict: {'resolved': bool, 'outcome': str, 'status': str} or None if error
    """
    try:
        client = initialize_kalshi_client()
        market = client.get_market(market_ticker)
        
        # Extract the result/outcome from market data
        outcome = None
        resolved = False
        
        if hasattr(market, 'result'):
            outcome = market.result
            resolved = outcome is not None
        elif isinstance(market, dict):
            outcome = market.get('result')
            resolved = outcome is not None
        
        return {
            'resolved': resolved,
            'outcome': outcome,
            'status': 'resolved' if resolved else 'open',
            'market': market  # Store full market data for debugging
        }
        
    except Exception as e:
        error_str = str(e)
        # Handle Pydantic validation errors for unknown market status values (e.g., 'finalized')
        if 'value_error' in error_str and 'status' in error_str and 'finalized' in error_str:
            # Market exists but has an unknown status - treat as settled/resolved
            return {'resolved': True, 'outcome': None, 'status': 'finalized', 'market': None}
        # Print but don't spam logs for placeholder markets
        if 'NOT-FOUND' not in market_ticker:
            print(f"Warning: Could not get market outcome for {market_ticker}: {e}")
        return {'resolved': False, 'outcome': None, 'status': 'error', 'market': None}


def enrich_trades_with_market_outcomes(trades_list):
    """
    Enrich trades with actual market outcomes/settlements.
    
    Args:
        trades_list: List of trade dicts
    
    Returns:
        tuple: (enriched_trades_list, enrichment_count)
    """
    if not trades_list:
        return trades_list, 0
    
    enrichment_count = 0
    for trade in trades_list:
        # Skip if already has final settlement
        existing_settlement = trade.get('settlement', {})
        if existing_settlement.get('status') in ['Won', 'Lost']:
            continue
        
        market = trade.get('market')
        if not market:
            continue
        
        # Skip placeholder/error markets that don't exist
        if 'NOT-FOUND' in market or market.startswith('BTC-') and len(market) <= 20:
            continue
        
        # Always calculate cost for tracking (needed for Amount Risked calculation)
        price = trade.get('price')
        if price is None:
            # Skip trades without execution price data
            continue
        
        contracts = trade.get('contracts', 1)
        cost_paid = (price / 100.0) * contracts
        
        outcome_data = get_market_outcome(market)
        
        if outcome_data['resolved']:
            action = trade.get('action', '').upper()
            outcome = outcome_data['outcome']
            
            # Determine win/loss
            result = None
            if 'YES' in action and outcome in ['Yes', 'yes', 1, True]:
                result = 'Won'
            elif 'NO' in action and outcome in ['No', 'no', 0, False]:
                result = 'Won'
            elif outcome is not None:
                result = 'Lost'
            
            # Calculate P&L if we have the result
            if result:
                if result == 'Won':
                    payout = 1.00 * contracts
                    pnl = payout - cost_paid
                else:
                    pnl = -cost_paid
                
                trade['settlement'] = {
                    'status': result,
                    'outcome': outcome,
                    'cost': cost_paid,
                    'pnl': pnl,
                    'details': f"Market resolved {outcome}"
                }
                enrichment_count += 1
                print(f"✓ {market}: {result} (PnL: ${pnl:.2f})")
        else:
            # Market not resolved yet - set cost for pending trades so Amount Risked is calculated
            if not existing_settlement.get('cost'):
                trade['settlement'] = existing_settlement.copy() if existing_settlement else {}
                trade['settlement']['cost'] = cost_paid
                if not trade['settlement'].get('status'):
                    trade['settlement']['status'] = 'Open'
    
    return trades_list, enrichment_count
