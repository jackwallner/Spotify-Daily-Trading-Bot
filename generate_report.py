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

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'REDACTED_GEMINI_KEY')
HUGGING_FACE_API_KEY = os.getenv('HUGGING_FACE_API_KEY', 'REDACTED_HF_KEY')


def generate_song_artwork(track_title, track_artist, predicted_success_rate, region="US"):
    """
    Generate song artwork using Hugging Face's FLUX.1-dev model.
    
    Args:
        track_title: Song title
        track_artist: Artist name
        predicted_success_rate: Success rate percentage (0-100)
        region: US or Global
    
    Returns:
        Base64 encoded image data or None (fallback to styled icon)
    """
    if not HUGGING_FACE_API_KEY:
        print("Warning: No Hugging Face API key available")
        return None
    
    # Create a prompt for album-style artwork
    prompt = f"Professional album cover artwork for '{track_title}' by {track_artist}, modern minimalist design, bold typography, spotify aesthetic, high quality, 4k"
    
    # Use FLUX.1-dev as main model
    model_id = "black-forest-labs/FLUX.1-dev"
    api_url = f"https://api-inference.huggingface.co/models/{model_id}"
    headers = {"Authorization": f"Bearer {HUGGING_FACE_API_KEY}"}
    
    try:
        response = requests.post(api_url, headers=headers, json={"inputs": prompt}, timeout=60)
        
        if response.status_code == 200:
            image_bytes = response.content
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            print(f"✓ Generated artwork for: {track_title}")
            return image_b64
        elif response.status_code == 503:
            print(f"Model loading for: {track_title}")
            return None
        else:
            print(f"Image generation failed ({response.status_code}): {response.text[:100]}")
            return None
            
    except Exception as e:
        print(f"Error generating image: {e}")
        return None


def generate_additional_artworks(track_title, track_artist, predicted_success_rate, region="US"):
    """
    Generate additional artwork variations using different models.
    
    Returns:
        List of dicts with {'model_name': str, 'image_b64': str}
    """
    if not HUGGING_FACE_API_KEY:
        return []
    
    prompt = f"album cover for '{track_title}' by {track_artist}, professional music artwork"
    
    # Additional models to try
    models = [
        {"id": "prompthero/openjourney", "name": "Midjourney Style"},
        {"id": "wavymulder/Analog-Diffusion", "name": "Film Photography"},
        {"id": "Lykon/DreamShaper", "name": "Artistic Style"}
    ]
    
    artworks = []
    headers = {"Authorization": f"Bearer {HUGGING_FACE_API_KEY}"}
    
    for model in models:
        try:
            api_url = f"https://api-inference.huggingface.co/models/{model['id']}"
            response = requests.post(api_url, headers=headers, json={"inputs": prompt}, timeout=30)
            
            if response.status_code == 200:
                image_bytes = response.content
                image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                artworks.append({
                    'model_name': model['name'],
                    'image_b64': image_b64
                })
                print(f"  ✓ Generated {model['name']} variation")
            elif response.status_code == 503:
                print(f"  Model loading: {model['name']}")
            else:
                print(f"  Failed: {model['name']} ({response.status_code})")
        except Exception as e:
            print(f"  Error with {model['name']}: {e}")
            continue
    
    return artworks


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
    """
    Load trades from trades.jsonl file.
    
    Returns:
        dict with 'trades' (actual executed trades) and 'runs' (all bot runs including NO TRADE)
    """
    all_runs = []
    actual_trades = []
    
    if not os.path.exists('trades.jsonl'):
        print("No trades.jsonl file found")
        return {'trades': actual_trades, 'runs': all_runs}
    
    try:
        with open('trades.jsonl', 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    all_runs.append(entry)
                    
                    # Only count as actual trade if status is Success and we have an order_id
                    status = entry.get('status', '')
                    action = entry.get('action', '')
                    order_id = entry.get('order_id')
                    
                    if status == 'Success' and order_id and 'Buy' in action:
                        actual_trades.append(entry)
                        
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error loading trades: {e}")
    
    return {'trades': actual_trades, 'runs': all_runs}


def calculate_stats(trades, runs):
    """
    Calculate trading statistics.
    
    Args:
        trades: List of actual executed trades (Success with order_id)
        runs: List of all bot runs (including NO TRADE, errors, etc.)
    """
    if not runs:
        return {
            'total_runs': 0,
            'total_trades': 0,
            'successful_trades': 0,
            'failed_attempts': 0,
            'no_trade_runs': 0,
            'errors': 0,
            'success_rate': 0.0,
            'total_cost': 0.0,
            'avg_confidence': 0.0,
            'total_pnl': 0.0,
            'pnl_history': []
        }
    
    # Count from all runs
    successful_trades = len(trades)  # trades already filtered to Success with order_id
    failed_attempts = len([r for r in runs if r.get('status') == 'Failed'])
    no_trade = len([r for r in runs if 'NO TRADE' in r.get('action', '')])
    errors = len([r for r in runs if r.get('action') == 'ERROR'])
    
    total_cost = 0.0
    total_pnl = 0.0
    confidences = []
    pnl_history = []
    running_pnl = 0.0
    
    for trade in trades:
        price = trade.get('price')
        contracts = trade.get('contracts')
        
        # Calculate cost
        if price and contracts:
            cost = (price * contracts) / 100.0
            total_cost += cost
            
            # Check settlement status for P/L
            settlement = trade.get('settlement', {})
            if isinstance(settlement, dict):
                pnl = settlement.get('pnl', 0)
                if pnl:
                    total_pnl += pnl
                    running_pnl += pnl
            else:
                # Assume pending/unknown settlements are -cost for now
                running_pnl -= cost
            
            pnl_history.append({
                'timestamp': trade.get('timestamp', ''),
                'pnl': running_pnl
            })
        
        decision_log = trade.get('decision_log', {})
        if isinstance(decision_log, dict):
            conf = decision_log.get('confidence')
            if conf:
                confidences.append(conf)
    
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    success_rate = (successful_trades / len(runs) * 100) if runs else 0.0
    
    return {
        'total_runs': len(runs),
        'total_trades': len(trades),
        'successful_trades': successful_trades,
        'failed_attempts': failed_attempts,
        'no_trade_runs': no_trade,
        'errors': errors,
        'success_rate': success_rate,
        'total_cost': total_cost,
        'avg_confidence': avg_confidence,
        'total_pnl': total_pnl,
        'pnl_history': pnl_history
    }


def generate_html_report(data):
    """Generate HTML report with Spotify styling and Gemini analysis."""
    
    trades = data['trades']
    runs = data['runs']
    stats = calculate_stats(trades, runs)
    
    # Get recent ACTUAL trades for analysis (not NO TRADE runs)
    recent_trades = sorted(trades, key=lambda x: x.get('timestamp', ''), reverse=True)[:10]
    
    # Get recent runs for history table (includes NO TRADE)
    recent_runs = sorted(runs, key=lambda x: x.get('timestamp', ''), reverse=True)[:20]
    
    # Generate song cards with Gemini analysis
    song_cards_html = ""
    
    # Import timezone for conversions
    from zoneinfo import ZoneInfo
    et_tz = ZoneInfo("America/New_York")
    
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
        
        # Convert timestamp to ET
        try:
            ts_utc = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            ts_et = ts_utc.astimezone(et_tz)
        except:
            ts_et = None
        
        # Convert confidence to success rate (0-10 scale to 0-100%)
        success_rate = min(100, max(0, confidence * 10))
        
        # Generate main artwork with FLUX.1-dev
        artwork_b64 = generate_song_artwork(track_title, track_artist, success_rate, region)
        
        # Generate additional artwork variations
        additional_artworks = generate_additional_artworks(track_title, track_artist, success_rate, region)
        
        # Get Gemini analysis
        ai_analysis = get_gemini_analysis(track_title, track_artist, confidence, streams, region)
        
        # Create main artwork HTML (image or fallback icon)
        if artwork_b64:
            artwork_html = f'<img src="data:image/png;base64,{artwork_b64}" alt="{track_title}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 10px;">'
        else:
            artwork_html = '<div class="song-icon">🎵</div>'
        
        # Create additional artworks HTML
        additional_artworks_html = ""
        if additional_artworks:
            additional_artworks_html = '<div class="additional-artworks"><h4>Alternative Styles</h4><div class="artwork-grid">'
            for artwork in additional_artworks:
                additional_artworks_html += f'''
                <div class="artwork-variant">
                    <img src="data:image/png;base64,{artwork['image_b64']}" alt="{artwork['model_name']}">
                    <span class="model-label">{artwork['model_name']}</span>
                </div>
                '''
            additional_artworks_html += '</div></div>'
        
        # Create song card
        song_cards_html += f"""
        <div class="song-card">
            <div class="song-artwork">
                <div class="success-badge">{success_rate}%</div>
                {artwork_html}
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
                    <span class="timestamp">{ts_et.strftime('%m/%d/%y %I:%M%p ET') if timestamp else 'N/A'}</span>
                </div>
                <div class="ai-analysis">
                    <strong>🤖 AI Analysis:</strong>
                    <p>{ai_analysis}</p>
                </div>
                {additional_artworks_html}
            </div>
        </div>
        """
    
    # Build history table (showing all runs, not just trades)
    history_table_html = ""
    for run in recent_runs:
        status = run.get('status', 'N/A')
        action = run.get('action', 'N/A')
        
        # Determine status class
        if status == 'Success' and run.get('order_id'):
            status_class = 'success'
        elif 'NO TRADE' in action or 'Could not match' in status:
            status_class = 'skipped'
        elif action == 'ERROR' or status == 'Failed':
            status_class = 'failed'
        else:
            status_class = 'skipped'
        
        decision_log = run.get('decision_log', {})
        predicted = decision_log.get('predicted', {}) if isinstance(decision_log, dict) else {}
        
        track_title = predicted.get('title', run.get('market', 'N/A'))
        track_artist = predicted.get('artist', 'N/A')
        
        # Convert timestamp to ET
        timestamp_str = run.get('timestamp', '')
        try:
            ts_utc = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            ts_et = ts_utc.astimezone(et_tz)
            timestamp_display = ts_et.strftime('%Y-%m-%d %I:%M %p ET')
        except:
            timestamp_display = timestamp_str[:19]
        
        history_table_html += f"""
        <tr class="{status_class}">
            <td>{timestamp_display}</td>
            <td>{track_title}</td>
            <td>{track_artist}</td>
            <td>{action}</td>
            <td><span class="status-badge {status_class}">{status[:50]}</span></td>
            <td>{run.get('price', 'N/A')}¢</td>
            <td>{run.get('contracts', 'N/A')}</td>
        </tr>
        """
    
    # Generate HTML
    # Prepare P/L chart data - convert timestamps to ET
    from zoneinfo import ZoneInfo
    et_tz = ZoneInfo("America/New_York")
    
    pnl_labels = []
    for p in stats['pnl_history']:
        ts_str = p['timestamp']
        try:
            # Parse ISO timestamp and convert to ET
            ts_utc = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            ts_et = ts_utc.astimezone(et_tz)
            pnl_labels.append(ts_et.strftime('%m/%d %I:%M%p ET'))
        except:
            # Fallback to just the date
            pnl_labels.append(ts_str[:10])
    
    pnl_data = [p['pnl'] for p in stats['pnl_history']]
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spotify Daily Trading Bot - Performance Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #121212;
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
            color: #fff;
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
        
        .stat-sublabel {{
            font-size: 0.75em;
            color: #888;
            margin-top: 5px;
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
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(29, 185, 84, 0.2);
        }}
        
        .song-artwork {{
            position: relative;
            width: 100%;
            height: 200px;
            background: linear-gradient(135deg, #282828, #181818);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 15px;
            overflow: hidden;
            border: 2px solid #333;
        }}
        
        .song-icon {{
            font-size: 4em;
            opacity: 0.5;
            color: #1db954;
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
            background: rgba(29, 185, 84, 0.2);
            color: #1db954;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
            border: 1px solid #1db954;
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
        
        .additional-artworks {{
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        .additional-artworks h4 {{
            color: #b3b3b3;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
        }}
        
        .artwork-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }}
        
        .artwork-variant {{
            position: relative;
            border-radius: 8px;
            overflow: hidden;
            border: 2px solid rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
        }}
        
        .artwork-variant:hover {{
            border-color: #1db954;
            transform: scale(1.05);
        }}
        
        .artwork-variant img {{
            width: 100%;
            height: 120px;
            object-fit: cover;
            display: block;
        }}
        
        .model-label {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: rgba(0, 0, 0, 0.8);
            color: #fff;
            padding: 5px;
            font-size: 0.7em;
            text-align: center;
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
        
        .pnl-chart-section {{
            margin: 40px 0;
        }}
        
        .chart-container {{
            background: rgba(0, 0, 0, 0.6);
            padding: 30px;
            border-radius: 15px;
            border: 2px solid rgba(29, 185, 84, 0.2);
            max-width: 900px;
            margin: 0 auto;
        }}
        
        #pnlChart {{
            max-width: 100%;
            height: 300px;
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
            <p class="subtitle">Last Updated: {datetime.now(ZoneInfo("America/New_York")).strftime('%B %d, %Y at %I:%M %p ET')}</p>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Bot Runs</div>
                <div class="stat-value">{stats['total_runs']}</div>
                <div class="stat-sublabel">Total executions</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Actual Trades</div>
                <div class="stat-value">{stats['total_trades']}</div>
                <div class="stat-sublabel">Executed orders</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">No Trades</div>
                <div class="stat-value">{stats['no_trade_runs']}</div>
                <div class="stat-sublabel">No match/markets</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Cost</div>
                <div class="stat-value">${stats['total_cost']:.2f}</div>
                <div class="stat-sublabel">Contracts purchased</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Avg Confidence</div>
                <div class="stat-value">{stats['avg_confidence']:.1f}/10</div>
                <div class="stat-sublabel">Prediction strength</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total P/L</div>
                <div class="stat-value" style="color: {'#1db954' if stats['total_pnl'] >= 0 else '#ff4444'}">${stats['total_pnl']:.2f}</div>
                <div class="stat-sublabel">Profit & Loss</div>
            </div>
        </div>
        
        <div class="pnl-chart-section">
            <h2 class="section-title">Profit & Loss Chart</h2>
            <div class="chart-container">
                <canvas id="pnlChart"></canvas>
            </div>
        </div>
        
        <div class="songs-section">
            <h2 class="section-title">Recent Predictions</h2>
            <div class="songs-grid">
                {song_cards_html}
            </div>
        </div>
        
        <div class="trades-section">
            <h2 class="section-title">Bot Run History</h2>
            <p style="color: #b3b3b3; margin-bottom: 20px;">Shows all bot executions including successful trades, failed attempts, and no-trade runs</p>
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
                    {history_table_html}
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
    
    <script>
        // P/L Chart
        const ctx = document.getElementById('pnlChart');
        if (ctx) {{
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: {pnl_labels},
                    datasets: [{{
                        label: 'Profit & Loss ($)',
                        data: {pnl_data},
                        borderColor: '#1db954',
                        backgroundColor: 'rgba(29, 185, 84, 0.1)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        pointBackgroundColor: '#1db954',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            display: true,
                            labels: {{
                                color: '#fff',
                                font: {{
                                    size: 14
                                }}
                            }}
                        }},
                        tooltip: {{
                            backgroundColor: 'rgba(0, 0, 0, 0.9)',
                            titleColor: '#1db954',
                            bodyColor: '#fff',
                            borderColor: '#1db954',
                            borderWidth: 1
                        }}
                    }},
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            grid: {{
                                color: 'rgba(255, 255, 255, 0.1)'
                            }},
                            ticks: {{
                                color: '#b3b3b3',
                                callback: function(value) {{
                                    return '$' + value.toFixed(2);
                                }}
                            }}
                        }},
                        x: {{
                            grid: {{
                                color: 'rgba(255, 255, 255, 0.1)'
                            }},
                            ticks: {{
                                color: '#b3b3b3',
                                maxRotation: 45,
                                minRotation: 45
                            }}
                        }}
                    }}
                }}
            }});
        }}
    </script>
</body>
</html>
"""
    
    return html


def main():
    """Generate and save the HTML report."""
    print("\nGenerating Spotify Trading Bot Report...")
    
    # Load trades and runs
    data = load_trades()
    print(f"Loaded {len(data['trades'])} actual trades from {len(data['runs'])} total runs")
    
    # Generate HTML report
    html = generate_html_report(data)
    
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
