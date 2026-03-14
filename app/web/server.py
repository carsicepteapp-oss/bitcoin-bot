"""Flask web server — serves the dashboard and the /api/state endpoint."""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any

from flask import Flask, jsonify, render_template, request

from app.web.state import BotState

_template_dir = os.path.join(os.path.dirname(__file__), "templates")

flask_app = Flask(__name__, template_folder=_template_dir)
flask_app.logger.disabled = True

# Injected by cmd_web() before the server starts
_state: BotState = BotState()
_manual_trade_counter = 90000
_manual_counter_lock = threading.Lock()

# News cache (refresh every 5 min)
_news_cache: list = []
_news_cache_ts: float = 0.0
_NEWS_TTL = 300  # seconds


def set_state(state: BotState) -> None:
    global _state
    _state = state


def _next_trade_id() -> int:
    global _manual_trade_counter
    with _manual_counter_lock:
        _manual_trade_counter += 1
        return _manual_trade_counter


def _floor_to_5min(dt: datetime) -> datetime:
    m = (dt.minute // 5) * 5
    return dt.replace(minute=m, second=0, microsecond=0)


# ── Routes ────────────────────────────────────────────────────────────────────

@flask_app.route("/")
def index() -> Any:
    return render_template("index.html")


@flask_app.route("/api/state")
def api_state() -> Any:
    return jsonify(_state.to_dict())


@flask_app.route("/api/manual_bet", methods=["POST"])
def api_manual_bet() -> Any:
    data = request.get_json(silent=True) or {}
    direction = str(data.get("direction", "")).upper()
    try:
        stake = float(data.get("stake", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Geçersiz miktar"}), 400

    if direction not in ("UP", "DOWN"):
        return jsonify({"error": "Yön UP veya DOWN olmalı"}), 400
    if stake <= 0:
        return jsonify({"error": "Miktar 0'dan büyük olmalı"}), 400
    if _state.open_manual_bet is not None:
        return jsonify({"error": "Zaten aktif bir manuel bahis var"}), 409

    # Enforce 50% balance limit
    max_stake = round(_state.balance * 0.5, 2)
    if stake > max_stake:
        return jsonify({"error": f"Maksimum bahis bakiyenin %%50'si: ${max_stake:.2f}"}), 400

    now = datetime.now(timezone.utc)
    window_start = _floor_to_5min(now)
    window_end = window_start + timedelta(minutes=5)
    entry_price = _state.current_price or 0.0
    trade_id = _next_trade_id()

    _state.place_manual_bet(
        trade_id=trade_id,
        direction=direction,
        stake=stake,
        entry_price=entry_price,
        window_start_iso=window_start.isoformat(),
        window_end_iso=window_end.isoformat(),
    )
    return jsonify({
        "ok": True,
        "trade_id": trade_id,
        "direction": direction,
        "stake": stake,
        "entry_price": entry_price,
        "window_end": window_end.isoformat(),
    })


@flask_app.route("/api/news")
def api_news() -> Any:
    global _news_cache, _news_cache_ts
    now = time.time()
    if now - _news_cache_ts < _NEWS_TTL and _news_cache:
        return jsonify(_news_cache)
    articles = _fetch_google_news() or _fetch_reddit_news()
    if articles:
        _news_cache = articles
        _news_cache_ts = now
    return jsonify(_news_cache)


def _fetch_google_news() -> list:
    import urllib.request as _ur
    import xml.etree.ElementTree as _ET
    import logging as _log
    url = (
        "https://news.google.com/rss/search"
        "?q=bitcoin+cryptocurrency+crypto"
        "&hl=en&gl=US&ceid=US:en"
    )
    req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with _ur.urlopen(req, timeout=10) as resp:
            root = _ET.fromstring(resp.read())
    except Exception as exc:
        _log.getLogger(__name__).warning("News fetch failed: %s", exc)
        return []
    articles = []
    for item in root.findall(".//item")[:30]:
        def _g(tag):
            el = item.find(tag)
            return (el.text or "").strip() if el is not None else ""
        title = _g("title")
        source = ""
        src_el = item.find("source")
        if src_el is not None and src_el.text:
            source = src_el.text.strip()
        elif " - " in title:
            parts = title.rsplit(" - ", 1)
            title, source = parts[0].strip(), parts[1].strip()
        pub = _g("pubDate")
        ts = int(time.time())
        if pub:
            try:
                import email.utils as _eu
                ts = int(_eu.parsedate_to_datetime(pub).timestamp())
            except Exception:
                pass
        articles.append({
            "title": title,
            "source": source,
            "url": _g("link"),
            "body": "",
            "published_on": ts,
            "categories": "Bitcoin|Crypto",
            "imageurl": "",
        })
    return articles


def _fetch_reddit_news() -> list:
    import urllib.request as _ur, json as _js, logging as _log
    url = "https://www.reddit.com/r/Bitcoin/new.json?limit=25"
    req = _ur.Request(url, headers={"User-Agent": "btc-bot/1.0"})
    try:
        with _ur.urlopen(req, timeout=8) as resp:
            data = _js.loads(resp.read())
    except Exception as exc:
        _log.getLogger(__name__).warning("Reddit fetch failed: %s", exc)
        return []
    articles = []
    for post in data.get("data", {}).get("children", []):
        p = post.get("data", {})
        thumb = p.get("thumbnail", "")
        articles.append({
            "title": p.get("title", ""),
            "source": "r/Bitcoin",
            "url": "https://reddit.com" + p.get("permalink", ""),
            "body": "",
            "published_on": int(p.get("created_utc", time.time())),
            "categories": "Bitcoin|Community",
            "imageurl": thumb if thumb.startswith("http") else "",
        })
    return articles


# ── Manual bet resolver thread ────────────────────────────────────────────────

def _manual_bet_resolver() -> None:
    """Background thread: resolves manual bets when their window closes."""
    while True:
        time.sleep(1)
        bet = _state.open_manual_bet
        if bet is None:
            continue
        try:
            window_end_dt = datetime.fromisoformat(bet["window_end_iso"])
        except Exception:
            continue
        now = datetime.now(timezone.utc)
        if now < window_end_dt:
            continue
        close_price = _state.current_price
        if close_price == 0.0:
            continue
        _state.resolve_manual_bet(close_price)


def run_server(host: str = "127.0.0.1", port: int = 5000) -> None:
    """Start Flask in the calling thread (blocking)."""
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    t = threading.Thread(target=_manual_bet_resolver, daemon=True, name="ManualBetResolver")
    t.start()

    actual_port = int(os.environ.get("PORT", port))
    actual_host = os.environ.get("HOST", host)
    flask_app.run(host=actual_host, port=actual_port, debug=False, use_reloader=False)
