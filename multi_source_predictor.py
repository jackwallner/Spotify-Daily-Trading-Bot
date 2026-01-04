#!/usr/bin/env python3
"""
Multi-Source Music Trend Predictor
Combines multiple data sources to predict top songs earlier and more accurately.

Data Sources:
1. Kworb (Spotify daily streams - updated throughout day)
2. YouTube Music Trending (reflects real-time popularity)
3. Shazam Discovery (real-time song identification)
4. TikTok trending sounds (strong correlation with song success)
5. Apple Music charts (alternative streaming platform)

Strategy: Aggregate signals from multiple sources, weight them, and predict
which songs will be in Spotify's daily top charts before the official update.
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from typing import List, Dict, Optional
import time


class MultiSourcePredictor:
    """Aggregates music trend signals from multiple sources."""
    
    def __init__(self):
        self.sources = {
            'kworb': {'weight': 0.30, 'enabled': True},
            'apple_music': {'weight': 0.25, 'enabled': True},
            'billboard': {'weight': 0.20, 'enabled': True},
            'genius': {'weight': 0.15, 'enabled': True},
            'last_fm': {'weight': 0.10, 'enabled': True},
            # Disabled: harder to scrape reliably
            'youtube_music': {'weight': 0.0, 'enabled': False},
            'shazam': {'weight': 0.0, 'enabled': False},
            'tiktok': {'weight': 0.0, 'enabled': False},
        }
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_kworb_trends(self, limit=50) -> List[Dict]:
        """
        Scrape Kworb for current Spotify streaming trends.
        Returns early data with trajectory analysis.
        """
        print("\n[KWORB] Fetching Spotify streaming data...")
        try:
            url = "https://kworb.net/spotify/country/us_daily.html"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            table = soup.find('table')
            
            if not table:
                print("[KWORB] ⚠ No table found")
                return []
            
            songs = []
            rows = table.find_all('tr')[1:]  # Skip header
            
            for i, row in enumerate(rows[:limit], 1):
                cells = row.find_all('td')
                if len(cells) < 7:
                    continue
                
                # Extract data
                artist_title = cells[2].get_text(strip=True)
                daily_streams_text = cells[6].get_text(strip=True).replace(',', '')
                
                # Parse artist and title
                if ' - ' in artist_title:
                    artist, title = artist_title.split(' - ', 1)
                else:
                    artist = "Unknown"
                    title = artist_title
                
                # Parse streams
                try:
                    daily_streams = int(daily_streams_text)
                except:
                    daily_streams = 0
                
                songs.append({
                    'rank': i,
                    'title': title.strip(),
                    'artist': artist.strip(),
                    'daily_streams': daily_streams,
                    'source': 'kworb',
                    'confidence': min(100, 50 + (daily_streams / 1000000) * 5)  # Higher streams = higher confidence
                })
            
            print(f"[KWORB] ✓ Found {len(songs)} songs")
            return songs
            
        except Exception as e:
            print(f"[KWORB] ✗ Error: {e}")
            return []
    
    def get_youtube_music_trends(self, limit=50) -> List[Dict]:
        """
        Scrape YouTube Music trending charts.
        YouTube trends often predict Spotify trends.
        """
        print("\n[YOUTUBE] Fetching YouTube Music trends...")
        try:
            # YouTube Music trending page
            url = "https://charts.youtube.com/charts/TrendingVideos/us"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # YouTube Music embeds data in JSON-LD
            scripts = soup.find_all('script', type='application/ld+json')
            
            songs = []
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        for item in data[:limit]:
                            if item.get('@type') == 'MusicRecording':
                                songs.append({
                                    'title': item.get('name', ''),
                                    'artist': item.get('byArtist', {}).get('name', ''),
                                    'source': 'youtube_music',
                                    'confidence': 70
                                })
                except:
                    continue
            
            # Fallback: Try parsing HTML if JSON-LD fails
            if not songs:
                print("[YOUTUBE] Trying HTML parsing fallback...")
                # Look for trending music videos
                items = soup.select('.chart-table-row, .chart-item, .ytm-item')
                for i, item in enumerate(items[:limit], 1):
                    title_elem = item.select_one('.title, .chart-title, h3')
                    artist_elem = item.select_one('.artist, .chart-artist, .subtitle')
                    
                    if title_elem:
                        songs.append({
                            'rank': i,
                            'title': title_elem.get_text(strip=True),
                            'artist': artist_elem.get_text(strip=True) if artist_elem else 'Unknown',
                            'source': 'youtube_music',
                            'confidence': 70
                        })
            
            print(f"[YOUTUBE] ✓ Found {len(songs)} songs")
            return songs
            
        except Exception as e:
            print(f"[YOUTUBE] ✗ Error: {e}")
            return []
    
    def get_shazam_trends(self, limit=50) -> List[Dict]:
        """
        Get Shazam discovery charts via unofficial API.
        Shazam data is highly predictive of streaming trends.
        """
        print("\n[SHAZAM] Fetching Shazam discovery charts...")
        try:
            # Use Shazam's unofficial chart API (used by their web app)
            url = "https://www.shazam.com/charts/top-200/united-states"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            songs = []
            
            # Parse chart items from HTML
            chart_items = soup.select('[class*="chart"], .track-item, .song-item')
            
            for i, item in enumerate(chart_items[:limit], 1):
                # Try multiple selectors
                title_elem = item.select_one('.track-name, .song-name, h3, h4')
                artist_elem = item.select_one('.artist-name, .subtitle, .secondary')
                
                if title_elem:
                    songs.append({
                        'rank': i,
                        'title': title_elem.get_text(strip=True),
                        'artist': artist_elem.get_text(strip=True) if artist_elem else 'Unknown',
                        'source': 'shazam',
                        'confidence': 80
                    })
            
            print(f"[SHAZAM] ✓ Found {len(songs)} songs")
            return songs
            
        except Exception as e:
            print(f"[SHAZAM] ✗ Error: {e}")
            return []
    
    def get_tiktok_trends(self, limit=50) -> List[Dict]:
        """
        Get TikTok trending sounds.
        TikTok is one of the strongest predictors of song popularity.
        """
        print("\n[TIKTOK] Fetching TikTok trending sounds...")
        try:
            # TikTok Discover page has trending sounds
            url = "https://www.tiktok.com/music"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            songs = []
            # TikTok embeds data in JSON within script tags
            scripts = soup.find_all('script', id='__UNIVERSAL_DATA_FOR_REHYDRATION__')
            
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    # Navigate through TikTok's data structure
                    music_list = data.get('__DEFAULT_SCOPE__', {}).get('webapp.music-trending', {}).get('musicList', [])
                    
                    for i, music in enumerate(music_list[:limit], 1):
                        songs.append({
                            'rank': i,
                            'title': music.get('title', ''),
                            'artist': music.get('authorName', ''),
                            'use_count': music.get('useCount', 0),
                            'source': 'tiktok',
                            'confidence': 85  # TikTok is very predictive
                        })
                except:
                    continue
            
            print(f"[TIKTOK] ✓ Found {len(songs)} songs")
            return songs
            
        except Exception as e:
            print(f"[TIKTOK] ✗ Error: {e}")
            return []
    
    def get_apple_music_trends(self, limit=50) -> List[Dict]:
        """
        Get Apple Music top charts.
        Apple Music charts as a cross-platform validation.
        """
        print("\n[APPLE] Fetching Apple Music charts...")
        try:
            # Apple Music has RSS feeds for charts
            url = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/50/songs.json"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            songs = []
            
            results = data.get('feed', {}).get('results', [])
            for i, track in enumerate(results[:limit], 1):
                songs.append({
                    'rank': i,
                    'title': track.get('name', ''),
                    'artist': track.get('artistName', ''),
                    'source': 'apple_music',
                    'confidence': 75
                })
            
            print(f"[APPLE] ✓ Found {len(songs)} songs")
            return songs
            
        except Exception as e:
            print(f"[APPLE] ✗ Error: {e}")
            return []
    
    def normalize_title(self, title: str) -> str:
        """Normalize song title for matching across sources."""
        if not title:
            return ""
        
        title = title.lower().strip()
        
        # Remove special characters and extra whitespace
        for char in ['|', ':', ';', '"', "'", '`']:
            title = title.replace(char, '')
        
        # Remove features and collaborations
        for pattern in ['(feat.', '(feat', '(with', '(ft.', '(ft', '(featuring']:
            if pattern in title:
                title = title.split(pattern)[0].strip()
        
        # Remove brackets
        title = title.replace('[', '(').replace(']', ')')
        
        # Keep only the base title (before parentheses)
        if '(' in title:
            title = title.split('(')[0].strip()
        
        # Remove common suffixes
        for suffix in [' remaster', ' remix', ' version', ' edit', ' radio edit']:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()
        
        # Remove years like "2004 Remaster"
        import re
        title = re.sub(r'\b\d{4}\s+(remaster|remix|version)\b', '', title).strip()
        
        # Collapse multiple spaces
        title = ' '.join(title.split())
        
        return title
    
    def normalize_artist(self, artist: str) -> str:
        """Normalize artist name for matching across sources."""
        if not artist or artist.lower() == 'unknown':
            return ""
        
        artist = artist.lower().strip()
        
        # Remove "featuring" and collaborations
        for sep in [' feat.', ' feat', ' ft.', ' ft', ' featuring', ' with', ' x ', ' & ']:
            if sep in artist:
                artist = artist.split(sep)[0].strip()
        
        # Remove "the" prefix/suffix
        artist = artist.replace(', the', '').replace(' the', '').strip()
        
        # Remove special characters
        for char in ['|', ':', ';', '"', "'", '`']:
            artist = artist.replace(char, '')
        
        # Collapse multiple spaces
        artist = ' '.join(artist.split())
        
        return artist
    
    def aggregate_predictions(self, all_sources: Dict[str, List[Dict]]) -> List[Dict]:
        """
        Aggregate signals from all sources into unified predictions.
        Uses weighted scoring based on source reliability and cross-validation.
        """
        print("\n[AGGREGATOR] Combining signals from all sources...")
        
        # Create a unified song database with normalized keys
        song_db = {}
        
        for source_name, songs in all_sources.items():
            if not songs:
                continue
            
            weight = self.sources.get(source_name, {}).get('weight', 0)
            
            for song in songs:
                title = song.get('title', '')
                artist = song.get('artist', '')
                
                if not title:
                    continue
                
                # Create normalized key for matching
                key = f"{self.normalize_title(title)}|{self.normalize_artist(artist)}"
                
                if key not in song_db:
                    song_db[key] = {
                        'title': title,
                        'artist': artist,
                        'sources': [],
                        'total_score': 0,
                        'confidence': 0,
                        'cross_validation': 0
                    }
                
                # Add source data
                song_db[key]['sources'].append(source_name)
                song_db[key]['cross_validation'] = len(song_db[key]['sources'])
                
                # Calculate weighted score
                rank = song.get('rank', 100)
                rank_score = max(0, 100 - rank)  # Higher rank = higher score
                confidence = song.get('confidence', 50)
                
                source_score = (rank_score * 0.7 + confidence * 0.3) * weight
                song_db[key]['total_score'] += source_score
        
        # Convert to list and sort by score
        predictions = []
        for key, data in song_db.items():
            # Boost score for cross-validation (song appears in multiple sources)
            cross_val_boost = data['cross_validation'] * 20
            final_score = data['total_score'] + cross_val_boost
            
            predictions.append({
                'title': data['title'],
                'artist': data['artist'],
                'score': final_score,
                'sources': data['sources'],
                'cross_validation': data['cross_validation'],
                'confidence': min(100, 50 + (data['cross_validation'] * 15))
            })
        
        # Sort by score (descending)
        predictions.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"[AGGREGATOR] ✓ Generated {len(predictions)} unique predictions")
        print(f"[AGGREGATOR] Top songs validated by multiple sources: {sum(1 for p in predictions if p['cross_validation'] >= 2)}")
        
        return predictions
    
    def get_billboard_trends(self, limit=50) -> List[Dict]:
        """
        Get Billboard Hot 100 (updates frequently, strong predictor).
        """
        print("\n[BILLBOARD] Fetching Billboard Hot 100...")
        try:
            url = "https://www.billboard.com/charts/hot-100/"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            songs = []
            
            # Billboard chart structure
            chart_items = soup.select('.o-chart-results-list-row')
            
            for i, item in enumerate(chart_items[:limit], 1):
                title_elem = item.select_one('#title-of-a-story, .c-title, h3')
                artist_elem = item.select_one('.c-label, .a-no-trucate')
                
                if title_elem:
                    songs.append({
                        'rank': i,
                        'title': title_elem.get_text(strip=True),
                        'artist': artist_elem.get_text(strip=True) if artist_elem else 'Unknown',
                        'source': 'billboard',
                        'confidence': 85  # Billboard is very reliable
                    })
            
            print(f"[BILLBOARD] ✓ Found {len(songs)} songs")
            return songs
            
        except Exception as e:
            print(f"[BILLBOARD] ✗ Error: {e}")
            return []
    
    def get_genius_trends(self, limit=50) -> List[Dict]:
        """
        Get Genius trending songs (people looking up lyrics = current interest).
        """
        print("\n[GENIUS] Fetching Genius trending songs...")
        try:
            url = "https://genius.com/"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            songs = []
            
            # Genius chart items
            chart_items = soup.select('.chart_row, .song_list-item, .ChartSongItem')
            
            for i, item in enumerate(chart_items[:limit], 1):
                title_elem = item.select_one('.chart_row-content-title, h3, .song-title')
                artist_elem = item.select_one('.chart_row-content-subtitle, .artist-name')
                
                if title_elem:
                    songs.append({
                        'rank': i,
                        'title': title_elem.get_text(strip=True),
                        'artist': artist_elem.get_text(strip=True) if artist_elem else 'Unknown',
                        'source': 'genius',
                        'confidence': 70
                    })
            
            print(f"[GENIUS] ✓ Found {len(songs)} songs")
            return songs
            
        except Exception as e:
            print(f"[GENIUS] ✗ Error: {e}")
            return []
    
    def get_last_fm_trends(self, limit=50) -> List[Dict]:
        """
        Get Last.fm trending tracks (real-time scrobbling data).
        """
        print("\n[LAST.FM] Fetching Last.fm trending tracks...")
        try:
            # Last.fm public API (no key required for chart data)
            url = "https://www.last.fm/music/+trending"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            songs = []
            
            # Last.fm chart structure
            chart_items = soup.select('.chartlist-row, .track-item')
            
            for i, item in enumerate(chart_items[:limit], 1):
                title_elem = item.select_one('.chartlist-name, .track-name')
                artist_elem = item.select_one('.chartlist-artist, .artist-name')
                
                if title_elem:
                    songs.append({
                        'rank': i,
                        'title': title_elem.get_text(strip=True),
                        'artist': artist_elem.get_text(strip=True) if artist_elem else 'Unknown',
                        'source': 'last_fm',
                        'confidence': 65
                    })
            
            print(f"[LAST.FM] ✓ Found {len(songs)} songs")
            return songs
            
        except Exception as e:
            print(f"[LAST.FM] ✗ Error: {e}")
            return []
    
    def predict_top_songs(self, top_n=50) -> List[Dict]:
        """
        Main prediction method: Aggregate all sources and return top predictions.
        """
        print("=" * 70)
        print("MULTI-SOURCE MUSIC TREND PREDICTOR")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")
        print("=" * 70)
        
        all_sources = {}
        
        # Fetch from all enabled sources
        for source_name, config in self.sources.items():
            if not config['enabled']:
                continue
            
            try:
                if source_name == 'kworb':
                    all_sources[source_name] = self.get_kworb_trends()
                elif source_name == 'youtube_music':
                    all_sources[source_name] = self.get_youtube_music_trends()
                elif source_name == 'shazam':
                    all_sources[source_name] = self.get_shazam_trends()
                elif source_name == 'tiktok':
                    all_sources[source_name] = self.get_tiktok_trends()
                elif source_name == 'apple_music':
                    all_sources[source_name] = self.get_apple_music_trends()
                elif source_name == 'billboard':
                    all_sources[source_name] = self.get_billboard_trends()
                elif source_name == 'genius':
                    all_sources[source_name] = self.get_genius_trends()
                elif source_name == 'last_fm':
                    all_sources[source_name] = self.get_last_fm_trends()
                
                # Rate limiting
                time.sleep(2)
            except Exception as e:
                print(f"[ERROR] Failed to fetch {source_name}: {e}")
        
        # Aggregate predictions
        predictions = self.aggregate_predictions(all_sources)
        
        return predictions[:top_n]


def test_predictor():
    """Test the multi-source predictor locally."""
    predictor = MultiSourcePredictor()
    
    print("\n🎵 Starting Multi-Source Prediction Test...\n")
    
    predictions = predictor.predict_top_songs(top_n=20)
    
    print("\n" + "=" * 70)
    print("TOP 20 PREDICTED SONGS")
    print("=" * 70)
    print(f"{'Rank':<6} {'Song':<30} {'Artist':<25} {'Score':<8} {'Sources':<15} {'Conf%':<6}")
    print("-" * 110)
    
    for i, pred in enumerate(predictions, 1):
        title = pred['title'][:28] + '..' if len(pred['title']) > 30 else pred['title']
        artist = pred['artist'][:23] + '..' if len(pred['artist']) > 25 else pred['artist']
        sources_str = f"{pred['cross_validation']}/{len(predictor.sources)}"
        
        print(f"{i:<6} {title:<30} {artist:<25} {pred['score']:<8.1f} {sources_str:<15} {pred['confidence']:<6}%")
    
    print("\n" + "=" * 70)
    print("CROSS-VALIDATION ANALYSIS")
    print("=" * 70)
    
    for threshold in [5, 4, 3, 2]:
        count = sum(1 for p in predictions if p['cross_validation'] >= threshold)
        if count > 0:
            print(f"Songs validated by {threshold}+ sources: {count}")
            for p in predictions:
                if p['cross_validation'] >= threshold:
                    print(f"  • {p['title']} - {p['artist']} ({', '.join(p['sources'])})")
    
    # Save predictions to file
    output_file = 'predictions.json'
    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'predictions': predictions
        }, f, indent=2)
    
    print(f"\n✓ Predictions saved to {output_file}")
    
    return predictions


if __name__ == '__main__':
    test_predictor()
