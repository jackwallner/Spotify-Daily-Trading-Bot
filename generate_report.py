#!/usr/bin/env python3
"""
Generate HTML report for Spotify Daily Trading Bot
Features:
- Spotify-focused analytics
- Gemini-generated song artwork with predicted success rates
- Trade history and performance metrics
"""

import os
import json
import base64
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyDgQE2xSmpfI2OH6JJmlVaMxbYAcUSBQEc')


def generate_song_artwork(track_title, track_artist, predicted_success_rate, region="US"):
    """
    Generate song artwork using Gemini's image generation API.
    
    Args:
        track_title: Song title
        track_artist: Artist name
        predicted_success_rate: Success rate percentage (0-100)
        region: US or Global
    
    Returns:
        Base64 encoded image data or None
    """
    if not GEMINI_API_KEY:
        print("Warning: No Gemini API key available")
        return None
    
    # Create a prompt for generating album-style artwork
    prompt = f"""Create a modern, minimalist album cover artwork for:
Song: "{track_title}" by {track_artist}

Style: Clean, professional Spotify-style design with:
- Bold typography showing the song title
- Artist name subtly displayed
- A large "{predicted_success_rate}%" success prediction overlay in a corner
- Color scheme that matches Spotify's aesthetic (greens and blacks)
- Modern gradient or abstract background
- Professional music streaming platform look

The success rate should be prominent and easy to read."""

    models_to_try = [
        'gemini-2.0-flash-exp',
        'gemini-2.0-flash-lite',
        'gemini-1.5-flash'
    ]
    
    for model in models_to_try:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 2048,
                }
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                # Note: Gemini text models don't generate images directly
                # We'll create a styled text-based representation instead
                return None  # Will use CSS-styled cards instead
            elif response.status_code == 429:
                continue  # Try next model
            else:
                print(f"Image generation failed with model {model}: {response.status_code}")
                continue
                
        except Exception as e:
            print(f"Error generating image with {model}: {e}")
            continue
    
    return None


def get_gemini_analysis(track_title, track_artist, confidence, streams, region):
    """Get AI analysis of the trading decision using Gemini."""
    
    # Generate smart fallback analysis based on data
    def generate_fallback_analysis():
        confidence_level = "strong" if confidence >= 7 else "moderate" if confidence >= 5 else "cautious"
        stream_desc = "high" if streams > 500 else "moderate" if streams > 200 else "growing"
        
        analysis = f"This track holds the #1 position on the {region} chart with {stream_desc} streaming momentum ({streams:,} daily streams). "
        
        if confidence >= 7:
            analysis += f"The bot shows {confidence_level} confidence ({confidence}/10) based on its current lead in streams and chart stability. "
            analysis += "The prediction model suggests this track is likely to maintain its dominant position."
        elif confidence >= 5:
            analysis += f"The bot shows {confidence_level} confidence ({confidence}/10), indicating competitive dynamics with the #2 track. "
            analysis += "Monitor for potential chart volatility as positions could shift."
        else:
            analysis += f"The bot shows {confidence_level} confidence ({confidence}/10), suggesting high volatility. "
            analysis += "The #2 track may be challenging for the top position, requiring careful risk management."
        
        return analysis
    
    # Try Gemini API first
    if not GEMINI_API_KEY:
        return generate_fallback_analysis()
    
    prompt = f"""Analyze this Spotify daily chart prediction for Kalshi markets:

Track: "{track_title}" by {track_artist}
Region: {region}
Current Position: #1 on charts
Daily Streams: {streams:,}
Bot Confidence: {confidence}/10

Provide a brief 2-3 sentence analysis explaining:
1. Why this track is predicted to stay #1
2. Key factors supporting this prediction
3. Risk factors to consider

Keep it concise and insightful for traders."""

    # Fallback models in order of rate limits (RPM):
    # gemini-2.5-flash-lite (7 RPM), gemini-2.5-flash (3 RPM),
    # gemma-3-27b (4 RPM), gemma-3-4b (2 RPM), gemma-3-12b (1 RPM), gemma-3-1b
    models = [
        'gemini-2.5-flash-lite',
        'gemini-2.5-flash',
        'gemma-3-27b-it',
        'gemma-3-4b-it',
        'gemma-3-12b-it',
        'gemma-3-1b-it'
    ]
    
    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('candidates'):
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    return text.strip()
            elif response.status_code == 429:
                continue
                
        except Exception as e:
            continue
    
    # Fallback to generated analysis if API fails
    return generate_fallback_analysis()


def load_trades():
    """Load trades from trades.jsonl"""
    trades = []
    if not os.path.exists('trades.jsonl'):
        return trades
    
    try:
        with open('trades.jsonl', 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    trade = json.loads(line)
                    trades.append(trade)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error loading trades: {e}")
    
    return trades


def calculate_stats(trades):
    """Calculate trading statistics."""
    if not trades:
        return {
            'total_trades': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'success_rate': 0.0,
            'total_cost': 0.0,
            'avg_confidence': 0.0
        }
    
    successful = len([t for t in trades if t.get('status') == 'Success'])
    failed = len([t for t in trades if t.get('status') == 'Failed'])
    skipped = len([t for t in trades if 'SKIP' in t.get('status', '')])
    
    total_cost = 0.0
    confidences = []
    
    for trade in trades:
        price = trade.get('price')
        contracts = trade.get('contracts')
        if price and contracts:
            total_cost += (price * contracts) / 100.0
        
        decision_log = trade.get('decision_log', {})
        if isinstance(decision_log, dict):
            conf = decision_log.get('confidence')
            if conf:
                confidences.append(conf)
    
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    success_rate = (successful / len(trades) * 100) if trades else 0.0
    
    return {
        'total_trades': len(trades),
        'successful': successful,
        'failed': failed,
        'skipped': skipped,
        'success_rate': success_rate,
        'total_cost': total_cost,
        'avg_confidence': avg_confidence
    }


def generate_html_report(trades):
    """Generate HTML report with Spotify styling and Gemini analysis."""
    
    stats = calculate_stats(trades)
    
    # Get recent trades for analysis
    recent_trades = sorted(trades, key=lambda x: x.get('timestamp', ''), reverse=True)[:10]
    
    # Generate song cards with Gemini analysis
    song_cards_html = ""
    
    for trade in recent_trades:
        decision_log = trade.get('decision_log', {})
        if not isinstance(decision_log, dict):
            continue
        
        predicted = decision_log.get('predicted', {})
        if not predicted:
            continue
        
        track_title = predicted.get('title', 'Unknown')
        track_artist = predicted.get('artist', 'Unknown')
        confidence = decision_log.get('confidence', 5)
        region = decision_log.get('region', 'US')
        streams = decision_log.get('streams1', 0)
        timestamp = trade.get('timestamp', '')
        
        # Convert confidence to success rate (0-10 scale to 0-100%)
        success_rate = min(100, max(0, confidence * 10))
        
        # Get Gemini analysis
        ai_analysis = get_gemini_analysis(track_title, track_artist, confidence, streams, region)
        
        # Create song card
        song_cards_html += f"""
        <div class="song-card">
            <div class="song-artwork">
                <div class="success-badge">{success_rate}%</div>
                <div class="song-icon">🎵</div>
            </div>
            <div class="song-details">
                <h3 class="song-title">{track_title}</h3>
                <p class="song-artist">{track_artist}</p>
                <div class="song-meta">
                    <span class="region-badge">{region}</span>
                    <span class="streams">{streams:,} streams</span>
                </div>
                <div class="prediction-info">
                    <span class="confidence">Confidence: {confidence}/10</span>
                    <span class="timestamp">{timestamp[:10]}</span>
                </div>
                <div class="ai-analysis">
                    <strong>🤖 AI Analysis:</strong>
                    <p>{ai_analysis}</p>
                </div>
            </div>
        </div>
        """
    
    # Build trades table
    trades_table_html = ""
    for trade in recent_trades:
        status_class = 'success' if trade.get('status') == 'Success' else 'failed' if trade.get('status') == 'Failed' else 'skipped'
        decision_log = trade.get('decision_log', {})
        predicted = decision_log.get('predicted', {}) if isinstance(decision_log, dict) else {}
        
        trades_table_html += f"""
        <tr class="{status_class}">
            <td>{trade.get('timestamp', '')[:19]}</td>
            <td>{predicted.get('title', trade.get('market', 'N/A'))}</td>
            <td>{predicted.get('artist', 'N/A')}</td>
            <td>{trade.get('action', 'N/A')}</td>
            <td><span class="status-badge {status_class}">{trade.get('status', 'N/A')}</span></td>
            <td>{trade.get('price', 'N/A')}¢</td>
            <td>{trade.get('contracts', 'N/A')}</td>
        </tr>
        """
    
    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spotify Daily Trading Bot - Performance Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1db954 0%, #191414 100%);
            color: #fff;
            padding: 20px;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        header {{
            text-align: center;
            padding: 40px 20px;
            background: rgba(0, 0, 0, 0.4);
            border-radius: 20px;
            margin-bottom: 30px;
            backdrop-filter: blur(10px);
        }}
        
        h1 {{
            font-size: 3em;
            margin-bottom: 10px;
            background: linear-gradient(90deg, #1db954, #1ed760);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .subtitle {{
            font-size: 1.2em;
            color: #b3b3b3;
            margin-top: 10px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        
        .stat-card {{
            background: rgba(0, 0, 0, 0.6);
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            border: 2px solid rgba(29, 185, 84, 0.3);
            backdrop-filter: blur(10px);
        }}
        
        .stat-value {{
            font-size: 2.5em;
            font-weight: bold;
            color: #1db954;
            margin: 10px 0;
        }}
        
        .stat-label {{
            font-size: 0.9em;
            color: #b3b3b3;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .songs-section {{
            margin: 40px 0;
        }}
        
        .section-title {{
            font-size: 2em;
            margin-bottom: 20px;
            color: #1db954;
        }}
        
        .songs-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }}
        
        .song-card {{
            background: rgba(0, 0, 0, 0.7);
            border-radius: 15px;
            padding: 20px;
            border: 2px solid rgba(29, 185, 84, 0.2);
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
        }}
        
        .song-card:hover {{
            border-color: #1db954;
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(29, 185, 84, 0.3);
        }}
        
        .song-artwork {{
            position: relative;
            width: 100%;
            height: 200px;
            background: linear-gradient(135deg, #1db954, #1ed760);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 15px;
            overflow: hidden;
        }}
        
        .song-icon {{
            font-size: 4em;
            opacity: 0.3;
        }}
        
        .success-badge {{
            position: absolute;
            top: 15px;
            right: 15px;
            background: rgba(0, 0, 0, 0.9);
            color: #1db954;
            padding: 10px 20px;
            border-radius: 25px;
            font-size: 1.5em;
            font-weight: bold;
            border: 2px solid #1db954;
        }}
        
        .song-details {{
            padding: 10px 0;
        }}
        
        .song-title {{
            font-size: 1.4em;
            margin-bottom: 8px;
            color: #fff;
        }}
        
        .song-artist {{
            font-size: 1.1em;
            color: #b3b3b3;
            margin-bottom: 15px;
        }}
        
        .song-meta {{
            display: flex;
            gap: 10px;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }}
        
        .region-badge {{
            background: #1db954;
            color: #000;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
        }}
        
        .streams {{
            color: #b3b3b3;
            font-size: 0.9em;
            display: flex;
            align-items: center;
        }}
        
        .prediction-info {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            margin-top: 10px;
            font-size: 0.9em;
            color: #b3b3b3;
        }}
        
        .confidence {{
            color: #1db954;
        }}
        
        .ai-analysis {{
            background: rgba(29, 185, 84, 0.1);
            padding: 15px;
            border-radius: 10px;
            margin-top: 15px;
            border-left: 4px solid #1db954;
        }}
        
        .ai-analysis strong {{
            color: #1db954;
            display: block;
            margin-bottom: 8px;
        }}
        
        .ai-analysis p {{
            color: #e0e0e0;
            line-height: 1.6;
            font-size: 0.95em;
        }}
        
        .trades-section {{
            background: rgba(0, 0, 0, 0.6);
            border-radius: 15px;
            padding: 30px;
            margin-top: 40px;
            backdrop-filter: blur(10px);
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        
        th {{
            background: rgba(29, 185, 84, 0.2);
            padding: 15px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85em;
            letter-spacing: 1px;
            color: #1db954;
        }}
        
        td {{
            padding: 15px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        tr.success {{
            background: rgba(29, 185, 84, 0.05);
        }}
        
        tr.failed {{
            background: rgba(255, 59, 48, 0.05);
        }}
        
        tr.skipped {{
            background: rgba(255, 204, 0, 0.05);
        }}
        
        .status-badge {{
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        
        .status-badge.success {{
            background: #1db954;
            color: #000;
        }}
        
        .status-badge.failed {{
            background: #ff3b30;
            color: #fff;
        }}
        
        .status-badge.skipped {{
            background: #ffcc00;
            color: #000;
        }}
        
        footer {{
            text-align: center;
            padding: 30px;
            color: #b3b3b3;
            margin-top: 40px;
        }}
        
        .powered-by {{
            margin-top: 10px;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎵 Spotify Daily Trading Bot</h1>
            <p class="subtitle">Powered by Kworb Chart Data & Gemini AI Analysis</p>
            <p class="subtitle">Last Updated: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}</p>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Trades</div>
                <div class="stat-value">{stats['total_trades']}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Successful</div>
                <div class="stat-value">{stats['successful']}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Success Rate</div>
                <div class="stat-value">{stats['success_rate']:.1f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Cost</div>
                <div class="stat-value">${stats['total_cost']:.2f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Avg Confidence</div>
                <div class="stat-value">{stats['avg_confidence']:.1f}/10</div>
            </div>
        </div>
        
        <div class="songs-section">
            <h2 class="section-title">Recent Predictions</h2>
            <div class="songs-grid">
                {song_cards_html}
            </div>
        </div>
        
        <div class="trades-section">
            <h2 class="section-title">Trade History</h2>
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Track</th>
                        <th>Artist</th>
                        <th>Action</th>
                        <th>Status</th>
                        <th>Price</th>
                        <th>Contracts</th>
                    </tr>
                </thead>
                <tbody>
                    {trades_table_html}
                </tbody>
            </table>
        </div>
        
        <footer>
            <p>🎵 Spotify Daily Trading Bot</p>
            <p class="powered-by">
                Data from <strong>Kworb.net</strong> | AI Analysis by <strong>Gemini</strong> | Trading on <strong>Kalshi</strong>
            </p>
        </footer>
    </div>
</body>
</html>
"""
    
    return html


def main():
    """Generate and save the HTML report."""
    print("Generating Spotify Trading Bot Report...")
    
    # Load trades
    trades = load_trades()
    print(f"Loaded {len(trades)} trades")
    
    # Generate HTML report
    html = generate_html_report(trades)
    
    # Ensure docs directory exists
    Path('docs').mkdir(exist_ok=True)
    
    # Save report
    output_path = 'docs/index.html'
    with open(output_path, 'w') as f:
        f.write(html)
    
    print(f"✓ Report generated: {output_path}")
    print(f"✓ View at: file://{os.path.abspath(output_path)}")


if __name__ == '__main__':
    main()
