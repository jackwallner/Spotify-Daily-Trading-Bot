#!/usr/bin/env python3
"""
Spotify Daily Market Intelligence.

Core idea (simplified):
- Use Spotify "Top 50" chart playlists as an easy-to-track signal.
- Decide whether the current #1 is safe, or if #2 is likely to flip.
- Map the predicted #1 track to the matching Kalshi market contract and buy YES.

Data sources:
- Spotify playlists (via `spotipy`) for rank + popularity proxy
  - Global Top 50: 37i9dQZEVXbMDoHDwVN2tF
  - USA Top 50:    37i9dQZEVXbLRQDuF5jeBp
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from spotify_daily_markets import get_market_close_ts


def _get_attr(obj, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


@dataclass(frozen=True)
class SpotifyDecisionThresholds:
    buy_yes: float = 60.0
    buy_no: float = 40.0
    skip_zone_low: float = 45.0
    skip_zone_high: float = 55.0


GLOBAL_TOP_50_PLAYLIST_ID = "37i9dQZEVXbMDoHDwVN2tF"
US_TOP_50_PLAYLIST_ID = "37i9dQZEVXbLRQDuF5jeBp"


def _normalize_text(s: str) -> str:
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum() or ch.isspace()).strip()


def _spotify_client() -> spotipy.Spotify:
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Missing SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET")
    auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    return spotipy.Spotify(auth_manager=auth, requests_timeout=15, retries=3)


def get_chart_snapshot(playlist_id: str, region: str) -> List[Dict[str, Any]]:
    """
    Returns list of track dicts for current playlist ordering.
    Note: Spotify API doesn't expose raw streams here; we use rank + popularity proxy.
    """
    sp = _spotify_client()
    results = sp.playlist_items(playlist_id, additional_types=("track",), limit=50)
    items = results.get("items", []) or []
    rows: List[Dict[str, Any]] = []

    for idx, item in enumerate(items):
        track = (item or {}).get("track") or {}
        if not track:
            continue
        artists = track.get("artists") or []
        artist_name = (artists[0].get("name") if artists else "") or ""
        title = track.get("name") or ""
        rows.append(
            {
                "rank": idx + 1,
                "artist": artist_name,
                "title": title,
                "popularity": int(track.get("popularity") or 0),
                "track_id": track.get("id"),
                "region": region,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    return rows


def playlist_delta_signal(region: str) -> Dict[str, Any]:
    """
    Simple signal:
    - incumbent = current #1
    - challenger = current #2
    - ALWAYS pick the incumbent (#1). We still compute popularity deltas to log
      "volatility" (how close a flip might be).
    """
    playlist_id = GLOBAL_TOP_50_PLAYLIST_ID if region.lower() == "global" else US_TOP_50_PLAYLIST_ID
    rows = get_chart_snapshot(playlist_id, region)
    if len(rows) < 2:
        return {"error": "insufficient_playlist_data", "region": region}

    top1 = rows[0]
    top2 = rows[1]

    try:
        pop_delta_threshold = int(os.getenv("SPOTIFY_POP_DELTA_THRESHOLD", "3"))
    except Exception:
        pop_delta_threshold = 3

    pop1 = int(top1.get("popularity") or 0)
    pop2 = int(top2.get("popularity") or 0)
    pop_delta = pop2 - pop1

    predicted = top1
    rationale = "Always pick current #1 (rank signal)"

    # Confidence is lower when #2 is gaining on #1 (higher popularity).
    if pop_delta >= pop_delta_threshold:
        confidence = 5
        rationale += f"; WARNING: #2 popularity momentum (+{pop_delta}) suggests possible flip"
    elif pop_delta > 0:
        confidence = 6
        rationale += f"; note: #2 popularity slightly higher (+{pop_delta})"
    else:
        confidence = 7

    return {
        "region": region,
        "playlist_id": playlist_id,
        "top1": top1,
        "top2": top2,
        "pop_delta": pop_delta,
        "pop_delta_threshold": pop_delta_threshold,
        "predicted": predicted,
        "confidence": confidence,
        "rationale": rationale,
        "framework": "spotify_playlist_delta_v1",
    }


def select_market_for_track(markets: List[Any], track_title: str, track_artist: str) -> Optional[Any]:
    """
    Best-effort matching between Spotify track and Kalshi market contract.
    We prefer matching on title, then artist.
    """
    t_title = _normalize_text(track_title)
    t_artist = _normalize_text(track_artist)
    if not t_title and not t_artist:
        return None

    best = None
    best_score = -1

    for m in markets or []:
        title = _normalize_text(str(getattr(m, "title", "") or ""))
        ticker = _normalize_text(str(getattr(m, "ticker", "") or ""))
        blob = f"{title} {ticker}".strip()
        score = 0
        if t_title and t_title in blob:
            score += 10
        if t_artist and t_artist in blob:
            score += 5
        # partial: if any word from title present
        if score == 0 and t_title:
            for w in t_title.split():
                if len(w) >= 4 and w in blob:
                    score += 1

        if score > best_score:
            best_score = score
            best = m

    if best_score <= 0:
        return None
    return best


def get_market_prices(client, ticker: str) -> Dict[str, int]:
    """
    Normalize market price fields across SDK response shapes.
    Returns cents ints: yes_bid, yes_ask, no_bid, no_ask.
    """
    resp = client.get_market(ticker)
    market = _get_attr(resp, "market", None) or resp

    yes_bid = _get_attr(market, "yes_bid", None)
    yes_ask = _get_attr(market, "yes_ask", None)
    no_bid = _get_attr(market, "no_bid", None)
    no_ask = _get_attr(market, "no_ask", None)

    def _clean(v, fallback: int) -> int:
        try:
            if v is None:
                return fallback
            return int(v)
        except Exception:
            return fallback

    yes_bid_i = _clean(yes_bid, 50)
    yes_ask_i = _clean(yes_ask, 50)
    no_bid_i = _clean(no_bid, max(0, 100 - yes_ask_i))
    no_ask_i = _clean(no_ask, max(0, 100 - yes_bid_i))

    return {"yes_bid": yes_bid_i, "yes_ask": yes_ask_i, "no_bid": no_bid_i, "no_ask": no_ask_i}


def orderbook_quality_score(prices: Dict[str, int]) -> float:
    """
    Simple orderbook quality proxy based on YES spread and mid stability.
    """
    yes_bid = prices["yes_bid"]
    yes_ask = prices["yes_ask"]
    spread = max(0, yes_ask - yes_bid)
    # Tight spread -> higher score. 0-10c is good; 20c+ is poor.
    spread_score = max(0.0, 100.0 - (spread * 6.0))
    return float(max(0.0, min(100.0, spread_score)))


def market_wisdom_signal(prices: Dict[str, int]) -> Dict[str, Any]:
    """
    Interprets market implied probability from YES bid/ask.
    """
    yes_bid = prices["yes_bid"]
    yes_ask = prices["yes_ask"]
    mid = (yes_bid + yes_ask) / 2.0
    spread = max(0, yes_ask - yes_bid)

    # Confidence decreases with spread
    spread_penalty = min(spread / 20.0, 0.5)  # max 50% penalty
    confidence = max(0.0, 100.0 - (spread_penalty * 100.0))

    if mid >= 70:
        consensus = "strong_yes"
        recommended_side = "yes"
    elif mid <= 30:
        consensus = "strong_no"
        recommended_side = "no"
    elif mid > 60:
        consensus = "lean_yes"
        recommended_side = "yes"
        confidence = min(confidence, 65.0)
    elif mid < 40:
        consensus = "lean_no"
        recommended_side = "no"
        confidence = min(confidence, 65.0)
    else:
        consensus = "neutral"
        recommended_side = "skip"
        confidence = min(confidence, 40.0)

    return {
        "consensus": consensus,
        "recommended_side": recommended_side,
        "implied_probability_yes": float(mid),
        "confidence": float(max(0.0, min(100.0, confidence))),
        "spread": int(spread),
    }


def time_to_close_signal(market) -> Dict[str, Any]:
    """
    Time-to-close signal: as markets approach close, avoid low-confidence trades.
    """
    close_ts = get_market_close_ts(market)
    if not close_ts:
        return {"minutes_remaining": None, "phase": "unknown", "should_trade": True}

    minutes = (close_ts - _now_ts()) / 60.0
    if minutes <= 5:
        return {"minutes_remaining": max(0.0, minutes), "phase": "critical", "should_trade": False}
    if minutes <= 30:
        return {"minutes_remaining": minutes, "phase": "urgent", "should_trade": True}
    if minutes <= 180:
        return {"minutes_remaining": minutes, "phase": "normal", "should_trade": True}
    return {"minutes_remaining": minutes, "phase": "early", "should_trade": True}


def trade_flow_score(client, ticker: str) -> float:
    """
    Lightweight trade-flow proxy using recent trades count.
    If trades are unavailable, returns neutral 50.
    """
    try:
        end_ts = _now_ts()
        start_ts = end_ts - (15 * 60)
        resp = client.get_trades(ticker=ticker, min_ts=start_ts, max_ts=end_ts, limit=500)
        trades = _get_attr(resp, "trades", None) or []
        n = len(trades) if trades else 0
        # More recent activity implies healthier market; cap at 100.
        return float(max(0.0, min(100.0, 30.0 + (n * 2.0))))
    except Exception:
        return 50.0


def get_spotify_daily_signals(
    client,
    market,
    thresholds: Optional[SpotifyDecisionThresholds] = None,
) -> Dict[str, Any]:
    """
    Compute a composite score + decision recommendation for a Spotify daily market.
    """
    thresholds = thresholds or SpotifyDecisionThresholds()
    ticker = _get_attr(market, "ticker", "")
    title = _get_attr(market, "title", "")

    prices = get_market_prices(client, ticker)
    ob_score = orderbook_quality_score(prices)
    flow_score = trade_flow_score(client, ticker)
    wisdom = market_wisdom_signal(prices)
    ttc = time_to_close_signal(market)

    # Composite: lean on market wisdom + execution quality + activity + time-to-close.
    # This is intentionally conservative (we don't have external Spotify fundamentals here).
    implied = wisdom["implied_probability_yes"]
    consensus_strength = wisdom["confidence"]

    # Convert implied probability into a "direction score" around 50.
    direction_score = float(implied)

    # Penalize low-quality markets
    quality_penalty = 0.0
    if wisdom["spread"] >= 20:
        quality_penalty += 10.0
    if ttc.get("phase") == "urgent":
        quality_penalty += 5.0
    if ttc.get("phase") == "critical":
        quality_penalty += 25.0

    composite = (
        (direction_score * 0.55)
        + (ob_score * 0.20)
        + (flow_score * 0.15)
        + (consensus_strength * 0.10)
    ) - quality_penalty
    composite = float(max(0.0, min(100.0, composite)))

    # Baseline decision from composite thresholds
    if not ttc.get("should_trade", True):
        decision = "SKIP"
        reason = f"Too close to close ({ttc.get('minutes_remaining'):.1f}m)"
        confidence = 2
    elif composite >= thresholds.buy_yes:
        decision = "BUY_YES"
        reason = f"Composite {composite:.1f} >= {thresholds.buy_yes} (YES-leaning market + healthy microstructure)"
        confidence = 6
    elif composite <= thresholds.buy_no:
        decision = "BUY_NO"
        reason = f"Composite {composite:.1f} <= {thresholds.buy_no} (NO-leaning market + healthy microstructure)"
        confidence = 6
    else:
        decision = "SKIP"
        reason = f"Composite {composite:.1f} in neutral zone ({thresholds.skip_zone_low}-{thresholds.skip_zone_high})"
        confidence = 4

    return {
        "ticker": ticker,
        "title": title,
        "prices": prices,
        "orderbook_score": ob_score,
        "trade_flow_score": flow_score,
        "market_wisdom": wisdom,
        "time_to_close": ttc,
        "composite_score": composite,
        "recommendation": decision,
        "reason": reason,
        "confidence": confidence,
        "framework": "spotify_microstructure_v1",
    }


def get_spotify_daily_gemini_decision(signals: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Optional AI layer: asks Gemini to approve/override a signals recommendation.
    Returns None if GEMINI_API_KEY missing or Gemini is unavailable.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    ticker = signals.get("ticker", "")
    title = signals.get("title", "")
    prices = signals.get("prices", {}) or {}
    wisdom = signals.get("market_wisdom", {}) or {}
    ttc = signals.get("time_to_close", {}) or {}
    composite = signals.get("composite_score", 50)
    rec = signals.get("recommendation", "SKIP")

    prompt = f"""You are an expert decision AI for Kalshi *Spotify daily* markets.

Market:
- Ticker: {ticker}
- Title: {title}

Current market pricing (cents):
- YES bid/ask: {prices.get('yes_bid')} / {prices.get('yes_ask')}
- NO  bid/ask: {prices.get('no_bid')} / {prices.get('no_ask')}

Market wisdom:
- Implied P(YES): {wisdom.get('implied_probability_yes', 50):.1f}%
- Consensus: {wisdom.get('consensus', 'unknown')}
- Spread: {wisdom.get('spread', 'N/A')}c

Timing:
- Minutes remaining: {ttc.get('minutes_remaining')}
- Phase: {ttc.get('phase')}

Model summary:
- Composite score: {composite:.1f}/100
- Model recommendation: {rec}

Decision rules:
1) Prefer SKIP when spread is wide (>= 20c) or time-to-close is critical.
2) Prefer trading only when the rationale is strong and execution quality is decent.
3) Keep reasoning short and focused on market microstructure + timing.

Respond in exactly this format:
DECISION: [BUY_YES | BUY_NO | SKIP]
CONFIDENCE: [1-10]
REASONING: [1-2 sentences]
"""

    models = [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemma-3-27b-it",
        "gemma-3-12b-it",
    ]

    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            data = {"contents": [{"parts": [{"text": prompt}]}]}
            resp = requests.post(url, json=data, headers=headers, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            if not payload.get("candidates"):
                continue
            text = payload["candidates"][0]["content"]["parts"][0]["text"]

            decision = rec
            confidence = 5
            reasoning = text.strip()

            if "DECISION:" in text:
                decision_part = text.split("DECISION:")[1].split("\n")[0].strip().upper()
                if "BUY_YES" in decision_part:
                    decision = "BUY_YES"
                elif "BUY_NO" in decision_part:
                    decision = "BUY_NO"
                elif "SKIP" in decision_part:
                    decision = "SKIP"

            if "CONFIDENCE:" in text:
                conf_part = text.split("CONFIDENCE:")[1].split("\n")[0].strip()
                try:
                    confidence = int("".join([c for c in conf_part if c.isdigit()]) or "5")
                except Exception:
                    confidence = 5
                confidence = max(1, min(10, confidence))

            if "REASONING:" in text:
                reasoning = text.split("REASONING:")[1].strip().split("\n")[0].strip()

            return {"decision": decision, "confidence": confidence, "reasoning": reasoning, "model": model}
        except requests.exceptions.HTTPError as e:
            if getattr(e.response, "status_code", None) == 429:
                time.sleep(0.5)
                continue
            # For non-rate-limit errors, still try next model
            continue
        except Exception:
            continue

    return None

