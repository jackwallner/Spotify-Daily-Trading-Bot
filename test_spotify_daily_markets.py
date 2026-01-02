#!/usr/bin/env python3
"""
Lightweight, offline sanity checks for Spotify daily market targeting.

These tests do NOT hit the Kalshi API.
"""

from datetime import datetime, timedelta, timezone

from spotify_daily_markets import SpotifyDailyMarketConfig, is_spotify_daily_market


class DummyMarket:
    def __init__(self, ticker: str, title: str, close_time: int | None = None):
        self.ticker = ticker
        self.title = title
        self.close_time = close_time


def run():
    cfg = SpotifyDailyMarketConfig(
        required_keywords=("spotify",),
        daily_keywords=("daily",),
        exclude_keywords=(),
        daily_close_window_hours=36,
        series_tickers=(),
        event_tickers=(),
        markets_limit=200,
        markets_max_pages=2,
    )

    now = int(datetime.now(timezone.utc).timestamp())
    soon = int((datetime.now(timezone.utc) + timedelta(hours=12)).timestamp())
    later = int((datetime.now(timezone.utc) + timedelta(days=10)).timestamp())

    m1 = DummyMarket("SPOTIFY-DAILY-TEST", "Spotify daily something", close_time=soon)
    assert is_spotify_daily_market(m1, cfg, now_ts=now) is True

    m2 = DummyMarket("SPOTIFY-WEEKLY-TEST", "Spotify weekly something", close_time=later)
    assert is_spotify_daily_market(m2, cfg, now_ts=now) is False

    m3 = DummyMarket("OTHER-DAILY-TEST", "Daily something", close_time=soon)
    assert is_spotify_daily_market(m3, cfg, now_ts=now) is False

    print("✓ Spotify daily market targeting sanity checks passed")


if __name__ == "__main__":
    run()

