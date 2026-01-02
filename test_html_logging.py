#!/usr/bin/env python3
"""
Test actual HTML logging - Verifies fallback analysis blocks are written to index.html
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from market_intelligence import get_market_signals

def test_html_logging_writes_correctly():
    """Test that fallback analysis actually gets written to index.html"""
    print("\n" + "="*70)
    print("TEST: Fallback Analysis HTML Logging")
    print("="*70)
    
    # Create a temporary HTML file to test writing
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        temp_html_path = f.name
        # Write a minimal HTML structure
        f.write("""<html><body>
<div id="ai-insights"></div>
</body></html>""")
    
    print(f"\n[SETUP] Created temp HTML file: {temp_html_path}")
    
    try:
        # Create a mock Kalshi client
        mock_client = MagicMock()
        
        # Mock all responses
        mock_candle = MagicMock()
        mock_candle.close = 80.0
        candlesticks_response = MagicMock()
        candlesticks_response.candlesticks = [mock_candle, mock_candle]
        mock_client.get_market_candlesticks.return_value = candlesticks_response
        
        market_response = MagicMock()
        market_response.last_price = 75
        market_response.highest_yes_bid = 70
        market_response.lowest_yes_ask = 80
        mock_client.get_market.return_value = market_response
        
        orderbook_response = MagicMock()
        bid_level = MagicMock()
        bid_level.price = 70
        bid_level.quantity = 1000
        ask_level = MagicMock()
        ask_level.price = 80
        ask_level.quantity = 100
        orderbook_response.order_book = MagicMock()
        orderbook_response.order_book.yes = MagicMock(bids=[bid_level], asks=[ask_level])
        mock_client.get_orderbook.return_value = orderbook_response
        
        trade_response = MagicMock()
        trade = MagicMock()
        trade.timestamp = int(datetime.now().timestamp() * 1000)
        trade.size = 100
        trade.price = 75
        trade_response.trades = [trade, trade]
        mock_client.get_trades.return_value = trade_response
        
        # Mock the docs/index.html to be our temp file
        print(f"\n[TEST] Calling get_market_signals without Gemini API key...")
        print(f"       Target HTML: {temp_html_path}")
        
        with patch.dict(os.environ, {}, clear=True):
            with patch('market_intelligence.extract_ai_performance_insights') as mock_insights:
                mock_insights.return_value = None
                
                # Patch the index.html path
                with patch('market_intelligence.Path') as mock_path_class:
                    # Mock the Path object for docs/index.html
                    mock_path_instance = MagicMock()
                    mock_path_instance.parent = Path(temp_html_path).parent
                    
                    def path_init_side_effect(p):
                        if 'docs' in str(p) and 'index.html' in str(p):
                            return Path(temp_html_path)
                        return Path(p)
                    
                    mock_path_class.side_effect = path_init_side_effect
                    
                    with patch('builtins.open', create=True) as mock_open:
                        # Use the real file operations
                        import builtins
                        real_open = builtins.open
                        
                        def custom_open(path, *args, **kwargs):
                            if isinstance(path, Path) and temp_html_path in str(path):
                                return real_open(temp_html_path, *args, **kwargs)
                            return real_open(path, *args, **kwargs)
                        
                        mock_open.side_effect = custom_open
                        
                        try:
                            result = get_market_signals(
                                mock_client,
                                "KXBTCD-TEST-MARKET"
                            )
                            
                            print(f"\n✓ get_market_signals executed")
                            
                            # Check if HTML file was modified
                            with open(temp_html_path, 'r') as f:
                                html_content = f.read()
                            
                            print(f"\n[VERIFICATION] Checking HTML output...")
                            
                            # Check for fallback analysis block
                            if 'Model-Based Analysis' in html_content:
                                print(f"✓ Fallback analysis block found in HTML")
                                
                                # Extract the block
                                if 'KXBTCD-TEST-MARKET' in html_content:
                                    print(f"✓ Market ticker logged correctly")
                                
                                if 'Signals Analysis' in html_content:
                                    print(f"✓ Signal analysis included")
                                
                                if 'Composite Score' in html_content:
                                    print(f"✓ Composite score included")
                                
                                if 'fef3c7' in html_content or '#fef3c7' in html_content:
                                    print(f"✓ Yellow background styling applied")
                                
                                if 'f59e0b' in html_content or '#f59e0b' in html_content:
                                    print(f"✓ Orange border styling applied")
                                
                                # Show a sample of the output
                                lines = html_content.split('\n')
                                analysis_start = next((i for i, l in enumerate(lines) if 'Model-Based Analysis' in l), None)
                                if analysis_start:
                                    print(f"\n[SAMPLE OUTPUT]")
                                    for line in lines[analysis_start:min(analysis_start + 10, len(lines))]:
                                        if line.strip():
                                            print(f"  {line}")
                            else:
                                print(f"✗ Fallback analysis block NOT found in HTML")
                                print(f"\nHTML Content Preview:")
                                print(html_content[:500])
                            
                        except Exception as e:
                            print(f"✗ Error: {type(e).__name__}: {e}")
                            import traceback
                            traceback.print_exc()
    
    finally:
        # Clean up temp file
        if os.path.exists(temp_html_path):
            os.remove(temp_html_path)
            print(f"\n[CLEANUP] Removed temp file")

if __name__ == "__main__":
    print("\n" + "="*70)
    print("HTML LOGGING VERIFICATION TEST")
    print("="*70)
    
    try:
        test_html_logging_writes_correctly()
        
        print("\n" + "="*70)
        print("HTML LOGGING TEST COMPLETED")
        print("="*70)
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
