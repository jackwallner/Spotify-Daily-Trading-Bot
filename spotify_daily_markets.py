#!/usr/bin/env python3
"""
Spotify Daily Markets targeting helpers.

This repo is being repurposed to focus on *Spotify daily* Kalshi markets.
The key principle is: **centralize market selection** so discovery, trading,
and reporting all operate on the same filtered set.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple


def _split_csv_env(name: str, default: str = "") -> List[str]:
    raw = os.getenv(name, default)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts


def _lower(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _get_attr(obj, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _coerce_ts_seconds(value) -> Optional[int]:
    """
    Coerce various SDK close_time/expiration formats to epoch seconds.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    # Some SDKs return datetime-ish objects
    if hasattr(value, "timestamp"):
        try:
            return int(value.timestamp())
        except Exception:
            return None
    # Strings might be ISO or numeric
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        try:
            return int(float(v))
        except Exception:
            pass
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except Exception:
            return None
    return None


@dataclass(frozen=True)
class SpotifyDailyMarketConfig:
    """
    Configuration for selecting Spotify daily markets.

    Environment variables (optional):
    - SPOTIFY_MARKET_REQUIRED_KEYWORDS: CSV keywords that MUST appear (default: "spotify")
    - SPOTIFY_MARKET_DAILY_KEYWORDS: CSV keywords that indicate "daily" framing (default: "daily")
    - SPOTIFY_MARKET_EXCLUDE_KEYWORDS: CSV keywords to exclude (default: "")
    - SPOTIFY_DAILY_CLOSE_WINDOW_HOURS: consider "daily" markets if closing within this many hours (default: 36)
    - SPOTIFY_SERIES_TICKERS: CSV series tickers to query directly (optional)
    - SPOTIFY_EVENT_TICKERS: CSV event tickers to query directly (optional)
    - KALSHI_MARKETS_LIMIT: page size for get_markets (default: 200)
    - KALSHI_MARKETS_MAX_PAGES: max pages to fetch when falling back to broad search (default: 10)
    """

    required_keywords: Tuple[str, ...] = ("spotify",)
    daily_keywords: Tuple[str, ...] = ("daily",)
    exclude_keywords: Tuple[str, ...] = ()
    daily_close_window_hours: int = 36
    series_tickers: Tuple[str, ...] = ()
    event_tickers: Tuple[str, ...] = ()
    markets_limit: int = 200
    markets_max_pages: int = 10

    @staticmethod
    def from_env() -> "SpotifyDailyMarketConfig":
        required = tuple(_lower(k) for k in _split_csv_env("SPOTIFY_MARKET_REQUIRED_KEYWORDS", "spotify"))
        daily = tuple(_lower(k) for k in _split_csv_env("SPOTIFY_MARKET_DAILY_KEYWORDS", "daily"))
        exclude = tuple(_lower(k) for k in _split_csv_env("SPOTIFY_MARKET_EXCLUDE_KEYWORDS", ""))
        series = tuple(_split_csv_env("SPOTIFY_SERIES_TICKERS", ""))
        events = tuple(_split_csv_env("SPOTIFY_EVENT_TICKERS", ""))

        try:
            window_h = int(os.getenv("SPOTIFY_DAILY_CLOSE_WINDOW_HOURS", "36"))
        except Exception:
            window_h = 36
        try:
            limit = int(os.getenv("KALSHI_MARKETS_LIMIT", "200"))
        except Exception:
            limit = 200
        try:
            max_pages = int(os.getenv("KALSHI_MARKETS_MAX_PAGES", "10"))
        except Exception:
            max_pages = 10

        return SpotifyDailyMarketConfig(
            required_keywords=tuple(k for k in required if k),
            daily_keywords=tuple(k for k in daily if k),
            exclude_keywords=tuple(k for k in exclude if k),
            daily_close_window_hours=max(1, window_h),
            series_tickers=series,
            event_tickers=events,
            markets_limit=max(1, limit),
            markets_max_pages=max(1, max_pages),
        )


def market_text_blob(market) -> str:
    """
    Create a single normalized text blob used for keyword filtering.
    """
    ticker = _lower(_get_attr(market, "ticker", ""))
    title = _lower(_get_attr(market, "title", ""))
    subtitle = _lower(_get_attr(market, "subtitle", ""))
    description = _lower(_get_attr(market, "description", ""))
    return " | ".join([p for p in [ticker, title, subtitle, description] if p])


def get_market_close_ts(market) -> Optional[int]:
    """
    Best-effort close timestamp. Different SDK versions expose different fields.
    """
    for field in ("close_time", "expiration_time", "expiry_time", "settlement_time"):
        ts = _coerce_ts_seconds(_get_attr(market, field, None))
        if ts:
            return ts
    return None


def is_spotify_daily_market(market, cfg: SpotifyDailyMarketConfig, now_ts: Optional[int] = None) -> bool:
    blob = market_text_blob(market)
    if not blob:
        return False

    for bad in cfg.exclude_keywords:
        if bad and bad in blob:
            return False

    # Must match all required keywords
    for req in cfg.required_keywords:
        if req and req not in blob:
            return False

    # "Daily" qualification:
    # - Prefer explicit "daily" keyword
    # - Otherwise allow markets closing within a near-term daily window (configurable)
    if cfg.daily_keywords and any(k in blob for k in cfg.daily_keywords):
        return True

    close_ts = get_market_close_ts(market)
    if close_ts is None:
        return False

    if now_ts is None:
        now_ts = int(datetime.now(timezone.utc).timestamp())

    window_seconds = cfg.daily_close_window_hours * 3600
    return now_ts <= close_ts <= (now_ts + window_seconds)


def _iter_markets_from_response(markets_response) -> Iterator:
    if not markets_response:
        return
    if hasattr(markets_response, "markets") and markets_response.markets:
        for m in markets_response.markets:
            yield m
    elif isinstance(markets_response, list):
        for m in markets_response:
            yield m


def iter_kalshi_markets(
    client,
    *,
    status: str = "open",
    limit: int = 200,
    max_pages: int = 10,
    series_ticker: Optional[str] = None,
    event_ticker: Optional[str] = None,
) -> Iterator:
    """
    Iterate markets with basic pagination support.
    Works best when series_ticker/event_ticker is provided (smaller result sets).
    """
    cursor = None
    pages = 0

    while pages < max_pages:
        pages += 1
        params = {"limit": limit}
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        if series_ticker:
            params["series_ticker"] = series_ticker
        if event_ticker:
            params["event_ticker"] = event_ticker

        resp = client.get_markets(**params)
        yielded_any = False
        for m in _iter_markets_from_response(resp):
            yielded_any = True
            yield m

        cursor = _get_attr(resp, "cursor", None)
        if not cursor:
            break
        if not yielded_any:
            break


def discover_spotify_daily_markets(
    client,
    cfg: Optional[SpotifyDailyMarketConfig] = None,
    *,
    status: str = "open",
) -> List:
    """
    Discover Spotify daily markets.

    Strategy:
    - If SPOTIFY_SERIES_TICKERS / SPOTIFY_EVENT_TICKERS are configured, query those directly.
    - Otherwise, fall back to scanning open markets (bounded by KALSHI_MARKETS_MAX_PAGES).
    """
    cfg = cfg or SpotifyDailyMarketConfig.from_env()
    now_ts = int(datetime.now(timezone.utc).timestamp())

    candidates: List = []

    # Preferred: targeted queries (fast, low volume)
    for st in cfg.series_tickers:
        for m in iter_kalshi_markets(
            client,
            status=status,
            limit=cfg.markets_limit,
            max_pages=cfg.markets_max_pages,
            series_ticker=st,
        ):
            candidates.append(m)

    for et in cfg.event_tickers:
        for m in iter_kalshi_markets(
            client,
            status=status,
            limit=cfg.markets_limit,
            max_pages=cfg.markets_max_pages,
            event_ticker=et,
        ):
            candidates.append(m)

    # Fallback: broad scan (bounded)
    if not candidates:
        for m in iter_kalshi_markets(
            client,
            status=status,
            limit=cfg.markets_limit,
            max_pages=cfg.markets_max_pages,
        ):
            candidates.append(m)

    # Filter + de-dup by ticker
    by_ticker = {}
    for m in candidates:
        t = _get_attr(m, "ticker", None)
        if not t:
            continue
        if is_spotify_daily_market(m, cfg, now_ts=now_ts):
            by_ticker[t] = m

    markets = list(by_ticker.values())

    # Sort: soonest closing first, then by liquidity-ish proxies if available.
    def _sort_key(m) -> Tuple:
        close_ts = get_market_close_ts(m) or 2**63 - 1
        volume = _get_attr(m, "volume", 0) or 0
        open_interest = _get_attr(m, "open_interest", 0) or 0
        return (close_ts, -(volume or 0), -(open_interest or 0), _lower(_get_attr(m, "ticker", "")))

    markets.sort(key=_sort_key)
    return markets

