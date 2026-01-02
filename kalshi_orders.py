#!/usr/bin/env python3
"""
Kalshi Orders API Module
Query orders by order_id using direct HTTP requests with proper authentication.
Since the SDK's get_order(order_id) may have permission issues, this module
uses the requests library to directly call the Kalshi API.
"""

import os
import requests
import time
import base64
from pathlib import Path
from dotenv import load_dotenv
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization


def _load_credentials():
    """Load API credentials from environment"""
    env_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=env_path)
    
    api_key_id = os.getenv('KALSHI_API_KEY_ID')
    key_path = os.getenv('KALSHI_KEY_PATH', 'kalshi_private_key.pem')
    
    if not api_key_id:
        raise ValueError("KALSHI_API_KEY_ID not set in environment")
    
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"Private key file not found: {key_path}")
    
    return api_key_id, key_path


def _sign_request(api_key_id, key_path, method, path):
    """Create Kalshi authentication headers for a request"""
    timestamp_ms = int(time.time() * 1000)
    timestamp_str = str(timestamp_ms)
    
    # Load private key
    with open(key_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None,
            backend=default_backend()
        )
    
    # Create signature on just the path (no query params)
    msg_string = timestamp_str + method.upper() + path
    message = msg_string.encode('utf-8')
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH
        ),
        hashes.SHA256()
    )
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": signature_b64,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
    }


def get_order(order_id):
    """
    Fetch a specific order by order_id from Kalshi API.
    
    Args:
        order_id: The order ID to fetch
        
    Returns:
        dict: Order details from the API, or None if failed
    """
    try:
        api_key_id, key_path = _load_credentials()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        return None
    
    # Create headers
    path = "/portfolio/orders"  # Signing path (no order_id, no query params)
    headers = _sign_request(api_key_id, key_path, "GET", path)
    
    # Full URL with order_id
    url = f"https://api.elections.kalshi.com/trade-api/v2/portfolio/orders/{order_id}"
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            error_data = response.json().get('error', {})
            print(f"Authentication error: {error_data.get('details', 'Unknown')}")
            return None
        else:
            print(f"API error ({response.status_code}): {response.text[:200]}")
            return None
            
    except Exception as e:
        print(f"Request failed: {e}")
        return None


def get_orders(limit=100):
    """
    Fetch all orders (with optional limit).
    
    Args:
        limit: Maximum number of orders to fetch
        
    Returns:
        dict: API response with orders list, or None if failed
    """
    try:
        api_key_id, key_path = _load_credentials()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        return None
    
    # Create headers - sign WITHOUT the query parameter
    path = "/portfolio/orders"
    headers = _sign_request(api_key_id, key_path, "GET", path)
    
    # Full URL with query parameter
    url = f"https://api.elections.kalshi.com/trade-api/v2/portfolio/orders?limit={limit}"
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            error_data = response.json().get('error', {})
            print(f"Authentication error: {error_data.get('details', 'Unknown')}")
            return None
        else:
            print(f"API error ({response.status_code}): {response.text[:200]}")
            return None
            
    except Exception as e:
        print(f"Request failed: {e}")
        return None


if __name__ == '__main__':
    print("Testing Kalshi Orders API...")
    
    # Test fetching orders
    print("\nFetching orders...")
    orders = get_orders(limit=5)
    if orders:
        print(f"✓ Got orders: {orders}")
    else:
        print("✗ Failed to fetch orders")
