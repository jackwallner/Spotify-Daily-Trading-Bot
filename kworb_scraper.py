#!/usr/bin/env python3
"""
Kworb chart scraper for Spotify daily charts.

Scrapes data from kworb.net which tracks daily Spotify chart positions and streams.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests
from bs4 import BeautifulSoup


# Kworb URLs for daily Spotify charts
KWORB_US_DAILY_URL = "https://kworb.net/spotify/country/us_daily.html"
KWORB_GLOBAL_DAILY_URL = "https://kworb.net/spotify/country/global_daily.html"


def _normalize_text(s: str) -> str:
    """Normalize text for matching."""
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum() or ch.isspace()).strip()


def _parse_streams(streams_str: str) -> int:
    """
    Parse stream count from Kworb format (e.g., "1,234,567" -> 1234567).
    Returns 0 if parsing fails.
    """
    if not streams_str:
        return 0
    try:
        # Remove commas and parse
        cleaned = streams_str.strip().replace(',', '')
        return int(cleaned)
    except (ValueError, AttributeError):
        return 0


def scrape_kworb_chart(url: str, region: str, max_retries: int = 3) -> List[Dict[str, Any]]:
    """
    Scrape a Kworb daily chart page.
    
    Args:
        url: Kworb chart URL
        region: Region name (e.g., "US", "Global")
        max_retries: Maximum number of retry attempts
    
    Returns:
        List of track dicts with rank, artist, title, streams, region, timestamp
    """
    rows: List[Dict[str, Any]] = []
    
    for attempt in range(max_retries):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Kworb uses a table with class 'sortable'
            table = soup.find('table', {'class': 'sortable'})
            if not table:
                print(f"[KWORB] Warning: Could not find chart table at {url}")
                return []
            
            tbody = table.find('tbody')
            if not tbody:
                print(f"[KWORB] Warning: Could not find tbody in table at {url}")
                return []
            
            rank = 1
            for tr in tbody.find_all('tr'):
                try:
                    cells = tr.find_all('td')
                    if len(cells) < 7:  # Need at least 7 columns for stream data
                        continue
                    
                    # Kworb table structure:
                    # Column 0: Position (rank)
                    # Column 1: Movement indicator (+/-)
                    # Column 2: Artist-Title (format: "Artist-Title")
                    # Column 3: Days on chart (NOT streams!)
                    # Column 4: Peak position
                    # Column 5: Times peaked (x?)
                    # Column 6: ACTUAL DAILY STREAMS (the number we want!)
                    # Column 7: Stream change
                    # Column 8: 7-day streams
                    # Column 9: 7-day change
                    # Column 10: Total streams
                    
                    # Get artist and title from column 2
                    artist_title_cell = cells[2]
                    artist_title_text = artist_title_cell.get_text(strip=True)
                    
                    # Split on "-" to separate artist and title
                    # Note: Some titles contain "-" so we split on first occurrence
                    if "-" in artist_title_text:
                        parts = artist_title_text.split("-", 1)
                        artist = parts[0].strip()
                        title = parts[1].strip()
                    else:
                        # Fallback: treat entire text as title
                        artist = ""
                        title = artist_title_text.strip()
                    
                    if not title:
                        continue
                    
                    # Get ACTUAL streams from column 6 (not column 3!)
                    streams_cell = cells[6]
                    streams_text = streams_cell.get_text(strip=True)
                    streams = _parse_streams(streams_text)
                    
                    rows.append({
                        "rank": rank,
                        "artist": artist,
                        "title": title,
                        "streams": streams,
                        "popularity": min(100, max(0, int(streams / 100000))) if streams > 0 else 0,  # Convert to 0-100 scale
                        "region": region,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    
                    rank += 1
                    
                    # Limit to top 50
                    if rank > 50:
                        break
                        
                except Exception as e:
                    # Skip malformed rows
                    continue
            
            if rows:
                print(f"[KWORB] Successfully scraped {len(rows)} tracks from {region} chart")
                return rows
            else:
                print(f"[KWORB] Warning: No rows parsed from {url}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"[KWORB] Request error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return []
        except Exception as e:
            print(f"[KWORB] Unexpected error scraping {url}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return []
    
    return []


def get_chart_snapshot(region: str) -> List[Dict[str, Any]]:
    """
    Get current chart snapshot from Kworb.
    
    Args:
        region: "US" or "Global"
    
    Returns:
        List of track dicts with rank, artist, title, streams, popularity, region, timestamp
    """
    region_lower = region.lower()
    
    if region_lower == "us":
        url = KWORB_US_DAILY_URL
    elif region_lower == "global":
        url = KWORB_GLOBAL_DAILY_URL
    else:
        print(f"[KWORB] Warning: Unknown region '{region}', defaulting to Global")
        url = KWORB_GLOBAL_DAILY_URL
    
    return scrape_kworb_chart(url, region)


if __name__ == "__main__":
    # Test scraping
    print("Testing Kworb scraper...")
    print("\n=== US Chart ===")
    us_chart = get_chart_snapshot("US")
    if us_chart:
        print(f"Top 5 US tracks:")
        for track in us_chart[:5]:
            print(f"  {track['rank']}. {track['artist']} - {track['title']} ({track['streams']:,} streams)")
    else:
        print("Failed to scrape US chart")
    
    print("\n=== Global Chart ===")
    global_chart = get_chart_snapshot("Global")
    if global_chart:
        print(f"Top 5 Global tracks:")
        for track in global_chart[:5]:
            print(f"  {track['rank']}. {track['artist']} - {track['title']} ({track['streams']:,} streams)")
    else:
        print("Failed to scrape Global chart")
