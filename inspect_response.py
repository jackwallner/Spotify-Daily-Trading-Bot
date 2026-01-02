#!/usr/bin/env python3
"""
Inspect markets response structure
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from kalshi_auth import initialize_kalshi_client

client = initialize_kalshi_client()

print("Fetching active markets...")
try:
    response = client.get_markets(limit=10)
    print(f"Response type: {type(response)}")
    print(f"Response: {response}")
    if hasattr(response, '__dict__'):
        print(f"Response attrs: {response.__dict__}")
    
    # Try to iterate
    if hasattr(response, 'markets'):
        print(f"\nMarkets list (first 5):")
        for m in response.markets[:5]:
            print(f"  - {m}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
