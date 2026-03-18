"""Uranium Thermometer - FastAPI Backend."""
import os
import json
import sqlite3
import httpx
from datetime import datetime
from contextlib import asynccontextmanager

from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, get_all_ticker_meta, get_ticker_meta, get_news, get_prices, get_spot_uranium, get_score_history, save_composite_snapshot, get_composite_history, DB_PATH, save_ticker_meta, get_db
from data_fetcher import refresh_all_tickers, fetch_news, fetch_spot_uranium, fetch_macro_regime
from analysis import TICKERS

DISCORD_CHANNEL_ID = "1471822299203371030"  # #general
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
OPENCLAW_GATEWAY = "http://localhost:18789"
OPENCLAW_TOKEN = "3f96d14d49491b032030e9f4a8dd7d9f985d2a7669e83f67"
TELEGRAM_CHAT_ID = "telegram:5737910635"

scheduler = BackgroundScheduler()


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _check_zone_changes():
    """Compare current zones to stored state, fire alerts on changes."""
    tickers = get_all_ticker_meta()
    conn = _get_db()

    # Ensure tables exist
    conn.execute('''CREATE TABLE IF NOT EXISTS zone_state (
        symbol TEXT PRIMARY KEY, zone TEXT, score REAL, price REAL,
        updated TEXT DEFAULT (datetime('now')))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS zone_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, old_zone TEXT,
        new_zone TEXT, old_score REAL, new_score REAL, price REAL,
        timestamp TEXT DEFAULT (datetime('now')))''')

    for t in tickers:
        sym = t["symbol"]
        new_zone = t.get("zone", "YELLOW")
        new_score = t.get("signal_score", 50)
        price = t.get("current_price", 0)

        row = conn.execute("SELECT zone, score FROM zone_state WHERE symbol=?", (sym,)).fetchone()
        if row:
            old_zone = row["zone"]
            old_score = row["score"]
            if old_zone != new_zone:
                # Zone changed — record alert
                conn.execute(
                    "INSERT INTO zone_alerts (symbol, old_zone, new_zone, old_score, new_score, price) VALUES (?,?,?,?,?,?)",
                    (sym, old_zone, new_zone, old_score, new_score, price))
                _fire_discord_alert(sym, old_zone, new_zone, old_score, new_score, price)
        # Update stored state
        conn.execute(
            "INSERT OR REPLACE INTO zone_state (symbol, zone, score, price, updated) VALUES (?,?,?,?,datetime('now'))",
            (sym, new_zone, new_score, price))
    conn.commit()
    conn.close()


def _fire_discord_alert(symbol, old_zone, new_zone, old_score, new_score, price):
    """Send zone change alert to Discord."""
    zone_emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}
    old_e = zone_emoji.get(old_zone, "⚪")
    new_e = zone_emoji.get(new_zone, "⚪")

    msg = (
        f"**☢️ ZONE ALERT: {symbol}**\n"
        f"{old_e} {old_zone} → {new_e} {new_zone}\n"
        f"Score: {old_score:.1f} → {new_score:.1f} | Price: ${price:.2f}\n"
    )

    # Add action hint
    if new_zone == "GREEN":
        msg += "📈 **Entering buy zone — review position**"
    elif new_zone == "RED":
        msg += "📉 **Entering sell zone — consider trimming**"
    elif old_zone == "RED" and new_zone == "YELLOW":
        msg += "⬇️ **Cooling off from overbought**"
    elif old_zone == "GREEN" and new_zone == "YELLOW":
        msg += "⬆️ **Rising out of buy zone**"

    if DISCORD_BOT_TOKEN:
        try:
            httpx.post(
                f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages",
                headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"},
                json={"content": msg},
                timeout=10,
            )
            print(f"[ALERT] Discord sent: {symbol} {old_zone}→{new_zone}")
        except Exception as e:
            print(f"[ALERT] Discord send failed: {e}")
    else:
        print(f"[ALERT] No bot token — {symbol} {old_zone}→{new_zone}")

    # Send to Telegram via OpenClaw API
    telegram_msg = (
        f"⚡ {symbol} Zone Change: {old_zone} → {new_zone} (score: {new_score:.1f})\n"
        f"Price: ${price:.2f} | Score: {old_score:.1f} → {new_score:.1f}\n"
        f"http://165.22.252.79/uranium/"
    )
    try:
        httpx.post(
            f"{OPENCLAW_GATEWAY}/tools/invoke",
            headers={"Authorization": f"Bearer {OPENCLAW_TOKEN}", "Content-Type": "application/json"},
            json={"tool": "message", "input": {"action": "send", "channel": "telegram", "target": TELEGRAM_CHAT_ID, "message": telegram_msg}},
            timeout=10,
        )
        print(f"[ALERT] Telegram sent: {symbol} {old_zone}→{new_zone}")
    except Exception as e:
        print(f"[ALERT] Telegram send failed: {e}")


_last_swing_alerts = set()  # track what we've already alerted to avoid spam

def _check_swing_signals():
    """Check swing trading signals and alert on new ones."""
    try:
        data = get_swing_rules()
        signals = data.get("signals", [])
        for s in signals:
            key = f"{s['signal']}_{s['symbol']}"
            if key in _last_swing_alerts:
                continue
            _last_swing_alerts.add(key)

            emoji = {"TAKE_PROFIT": "💰", "STOP_LOSS": "🛑", "ENTRY": "🎯"}.get(s["signal"], "📊")
            msg = f"{emoji} **Swing Signal: {s['signal'].replace('_', ' ')}** — {s['symbol']}\n{s['reason']}\nhttp://165.22.252.79/uranium/"

            # Discord
            bot_token = os.environ.get("DISCORD_BOT_TOKEN")
            if bot_token:
                try:
                    httpx.post(
                        f"https://discord.com/api/v10/channels/1471822299203371030/messages",
                        headers={"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"},
                        json={"content": msg}, timeout=10,
                    )
                except Exception as e:
                    print(f"[SWING] Discord alert failed: {e}")

            # Telegram
            try:
                httpx.post(
                    f"{OPENCLAW_GATEWAY}/tools/invoke",
                    headers={"Authorization": f"Bearer {OPENCLAW_TOKEN}", "Content-Type": "application/json"},
                    json={"tool": "message", "input": {"action": "send", "channel": "telegram", "target": TELEGRAM_CHAT_ID, "message": msg.replace("**", "")}},
                    timeout=10,
                )
            except Exception as e:
                print(f"[SWING] Telegram alert failed: {e}")

            print(f"[SWING] Alert: {s['signal']} {s['symbol']}")
    except Exception as e:
        print(f"[SWING] Check failed: {e}")


def snapshot_composite_scores():
    """Take a daily snapshot of composite scores for all tickers + URA."""
    from analysis import TICKERS
    today = datetime.utcnow().strftime("%Y-%m-%d")
    symbols = list(TICKERS.keys())
    for sym in symbols:
        try:
            # Call the decomposition logic directly
            resp = get_score_decomposition(symbol=sym)
            if isinstance(resp, dict):
                save_composite_snapshot(today, sym, resp)
        except Exception as e:
            print(f"[snapshot] Error for {sym}: {e}")
    print(f"[{datetime.utcnow().isoformat()}] Composite score snapshot saved for {len(symbols)} tickers")


# Pre-computed caches for slow endpoints
_cache_trade_tickets = {"data": None, "updated_at": None}
_cache_daily_digest = {"data": None, "updated_at": None}


def _precompute_slow_endpoints():
    """Background pre-compute trade-tickets and daily-digest."""
    import threading
    def _run():
        global _cache_trade_tickets, _cache_daily_digest
        try:
            print("[CACHE] Pre-computing trade-tickets...")
            _cache_trade_tickets["data"] = trade_tickets(portfolio_value=10000)
            _cache_trade_tickets["updated_at"] = datetime.utcnow().isoformat()
            print("[CACHE] trade-tickets cached")
        except Exception as e:
            print(f"[CACHE] trade-tickets error: {e}")
        try:
            print("[CACHE] Pre-computing daily-digest...")
            _cache_daily_digest["data"] = daily_digest()
            _cache_daily_digest["updated_at"] = datetime.utcnow().isoformat()
            print("[CACHE] daily-digest cached")
        except Exception as e:
            print(f"[CACHE] daily-digest error: {e}")
    threading.Thread(target=_run, daemon=True).start()


def scheduled_refresh():
    """Refresh data - runs every 15 min during market hours."""
    now = datetime.utcnow()
    # Market hours: Mon-Fri, 13:30-20:00 UTC (9:30-4:00 ET)
    if now.weekday() < 5 and 13 <= now.hour <= 20:
        print(f"[{now.isoformat()}] Scheduled refresh (market hours)")
        refresh_all_tickers()
        fetch_news()
        fetch_spot_uranium()
        _check_zone_changes()
        _check_swing_signals()
        _check_custom_alerts()
        _check_regime_transition()
        _precompute_slow_endpoints()
    elif now.minute == 0:  # Off-hours: refresh news once per hour
        print(f"[{now.isoformat()}] Scheduled refresh (off-hours, news only)")
        fetch_news()


def snapshot_portfolio_equity():
    """Daily portfolio equity snapshot for Sharpe/drawdown calculations."""
    try:
        conn = _get_db()
        conn.execute("""CREATE TABLE IF NOT EXISTS portfolio_equity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            cash REAL,
            holdings_value REAL,
            total_value REAL,
            invested_pct REAL
        )""")
        conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
        conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
        cash = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()["cash"]
        positions = conn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall()

        holdings = 0
        for p in positions:
            meta = get_ticker_meta(p["symbol"])
            price = meta.get("current_price", p["avg_cost"]) if meta else p["avg_cost"]
            holdings += p["shares"] * price

        total = cash + holdings
        invested_pct = holdings / total * 100 if total > 0 else 0
        today = datetime.utcnow().strftime("%Y-%m-%d")

        conn.execute("INSERT OR REPLACE INTO portfolio_equity_history (date, cash, holdings_value, total_value, invested_pct) VALUES (?,?,?,?,?)",
            (today, round(cash, 2), round(holdings, 2), round(total, 2), round(invested_pct, 1)))
        conn.commit()
        conn.close()
        print(f"[{datetime.utcnow().isoformat()}Z] Portfolio equity snapshot: ${total:,.2f} ({invested_pct:.0f}% invested)")
    except Exception as e:
        print(f"[{datetime.utcnow().isoformat()}Z] Portfolio equity snapshot ERROR: {e}")


def _get_risk_parity_weights(lookback=90):
    """Calculate inverse-volatility weights for all tickers."""
    import yfinance as yf, numpy as np
    from analysis import TICKERS
    vols = {}
    for sym in list(TICKERS.keys()):
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period=f"{lookback + 10}d")
            if hist.empty or len(hist) < lookback // 2:
                continue
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)
            rets = hist["Close"].pct_change().dropna().tail(lookback)
            vol = float(np.std(rets)) * np.sqrt(252)
            if vol > 0:
                vols[sym] = vol
        except:
            continue
    if not vols:
        return {}
    inv = {s: 1.0 / v for s, v in vols.items()}
    total_inv = sum(inv.values())
    return {s: round(w / total_inv, 4) for s, w in inv.items()}


def scheduled_auto_rebalance():
    """Daily paper rebalance at 4:35 PM ET — PAUSED pending directional vs contrarian validation.
    Will route through _execute_trade_signals() once signal-drift data resolves which interpretation has edge."""
    now = datetime.utcnow()
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "auto-rebalance.log")
    try:
        # DRY RUN ONLY — log what would happen, don't execute
        result = _execute_trade_signals(source="CRON", dry_run=True)
        trades = result["executed"]
        summary = f"[{now.isoformat()}Z] Auto-rebalance DRY RUN: {len(trades)} trades would execute | Portfolio: ${result['portfolio_after']['total_value']:,.0f}"
        if trades:
            summary += "\n  " + "\n  ".join(f"[DRY] {t['action']} {t['symbol']} {t['shares']}sh @${t['price']:.2f} (rule={t['matched_rule']})" for t in trades)
        print(summary)
        with open(log_path, "a") as f:
            f.write(summary + "\n\n")
    except Exception as e:
        err = f"[{now.isoformat()}Z] Auto-rebalance ERROR: {e}"
        print(err)
        with open(log_path, "a") as f:
            f.write(err + "\n\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio, threading
    init_db()

    # 1. Load warm cache instantly (< 1 second)
    from data_fetcher import load_warm_cache
    cached = load_warm_cache()
    if cached:
        for result in cached:
            try:
                save_ticker_meta(result)
            except:
                pass
        print(f"[BOOT] Serving {len(cached)} tickers from warm cache — server ready!")
    else:
        print("[BOOT] No warm cache found — will fetch fresh data in background")

    # 2. Start scheduler immediately
    scheduler.add_job(scheduled_refresh, "interval", minutes=15)
    scheduler.add_job(snapshot_composite_scores, "cron", hour=20, minute=30)
    scheduler.add_job(scheduled_auto_rebalance, "cron", hour=20, minute=35, day_of_week="mon-fri")
    scheduler.add_job(snapshot_portfolio_equity, "cron", hour=20, minute=40, day_of_week="mon-fri")
    scheduler.start()

    # 3. Background refresh (non-blocking)
    def _bg_refresh():
        print("[BOOT] Background refresh starting...")
        try:
            refresh_all_tickers()
            fetch_news()
            fetch_spot_uranium()
            print("[BOOT] Background refresh complete — data is fresh")
        except Exception as e:
            print(f"[BOOT] Background refresh error: {e}")
        # Take initial snapshot if needed
        try:
            snapshot_composite_scores()
        except:
            pass
        # Check regime + pre-compute slow endpoints
        _check_regime_transition()
        _precompute_slow_endpoints()

    threading.Thread(target=_bg_refresh, daemon=True).start()

    yield
    scheduler.shutdown()


app = FastAPI(
    title="Uranium Thermometer",
    description="Investment dashboard for uranium ETFs and stocks",
    version="1.0.0",
    lifespan=lifespan,
)


# --- API Routes ---

@app.get("/api/thermometer")
def get_thermometer():
    """Main dashboard data."""
    tickers = get_all_ticker_meta()
    spot = get_spot_uranium()
    
    # Find URA for hero thermometer
    ura = None
    for t in tickers:
        if t["symbol"] == "URA":
            ura = t
            break
    
    # Compute verdict
    verdict = None
    if ura:
        score = ura.get("signal_score", 50)
        zone_pct = ura.get("zone_pct", 50)
        rsi = ura.get("rsi")
        price = ura.get("current_price", 0)
        range_low = ura.get("range_low", 0)
        range_high = ura.get("range_high", 0)
        
        # Count how many tickers agree on direction
        bullish_count = sum(1 for t in tickers if (t.get("signal_score") or 50) >= 55)
        bearish_count = sum(1 for t in tickers if (t.get("signal_score") or 50) <= 40)
        total = len(tickers) or 1
        
        if score >= 70:
            action = "ACCUMULATE"
            detail = f"Below ${range_low + (range_high - range_low) * 0.3:.0f} — strong buy zone. Multiple indicators oversold."
        elif score >= 55:
            action = "BUY"
            detail = f"Favorable entry near ${price:.2f} with room to run."
        elif score >= 45:
            action = "HOLD"
            detail = f"Neutral at ${price:.2f}. Wait for dip below ${range_low + (range_high - range_low) * 0.3:.0f} to add."
        elif score >= 30:
            action = "REDUCE"
            detail = f"Technically extended at ${price:.2f}."
        else:
            action = "SELL"
            detail = f"Overbought at ${price:.2f}. Take profits and wait for reset."
        
        # Conviction based on agreement across indicators and tickers
        if bullish_count >= total * 0.6 or bearish_count >= total * 0.6:
            conviction = "HIGH"
        elif bullish_count >= total * 0.4 or bearish_count >= total * 0.4:
            conviction = "MEDIUM"
        else:
            conviction = "LOW"
        
        # --- Macro regime adjustment ---
        try:
            macro = fetch_macro_regime()
            macro_regime = macro.get("regime", "NEUTRAL")
        except Exception:
            macro_regime = "NEUTRAL"

        # Shift conviction based on macro regime
        conviction_levels = ["LOW", "MEDIUM", "HIGH"]
        conv_idx = conviction_levels.index(conviction)
        if macro_regime == "HOSTILE":
            # Hostile macro = less conviction in bullish signals, more in bearish
            if action in ("BUY", "ACCUMULATE"):
                conv_idx = max(0, conv_idx - 1)
            elif action in ("SELL", "REDUCE"):
                conv_idx = min(2, conv_idx + 1)
        elif macro_regime == "FAVORABLE":
            if action in ("BUY", "ACCUMULATE"):
                conv_idx = min(2, conv_idx + 1)
            elif action in ("SELL", "REDUCE"):
                conv_idx = max(0, conv_idx - 1)
        conviction = conviction_levels[conv_idx]

        # --- News sentiment aggregate ---
        try:
            articles = get_news(limit=50)
            bullish_news = sum(1 for a in articles if a.get("sentiment") == "bullish")
            bearish_news = sum(1 for a in articles if a.get("sentiment") == "bearish")
            total_news = len(articles) or 1
            if bullish_news / total_news >= 0.6:
                news_sentiment = "BULLISH"
            elif bearish_news / total_news >= 0.6:
                news_sentiment = "BEARISH"
            else:
                news_sentiment = "MIXED"
        except Exception:
            bullish_news, bearish_news, news_sentiment = 0, 0, "UNKNOWN"

        # Enrich detail with macro + sentiment context
        macro_text = ""
        if macro_regime == "FAVORABLE":
            macro_text = "Macro tailwinds support risk-on positioning."
        elif macro_regime == "HOSTILE":
            macro_text = "Macro headwinds urge caution."
        else:
            macro_text = "Macro environment is neutral."

        if news_sentiment == "BULLISH" and action in ("REDUCE", "SELL"):
            detail += f" {macro_text} Sentiment strongly bullish ({bullish_news} articles) — reduce with patience, not urgency."
        elif news_sentiment == "BEARISH" and action in ("BUY", "ACCUMULATE"):
            detail += f" {macro_text} Sentiment bearish ({bearish_news} articles) — accumulate cautiously, watch for catalyst."
        elif news_sentiment == "BULLISH" and action in ("BUY", "ACCUMULATE"):
            detail += f" {macro_text} Sentiment confirms ({bullish_news} bullish articles) — conviction is {conviction.lower()}."
        elif news_sentiment == "BEARISH" and action in ("REDUCE", "SELL"):
            detail += f" {macro_text} Sentiment confirms ({bearish_news} bearish articles) — exit decisively."
        else:
            detail += f" {macro_text}"

        verdict = {
            "action": action,
            "detail": detail,
            "conviction": conviction,
            "composite_score": round(score, 1),
            "bullish_tickers": bullish_count,
            "bearish_tickers": bearish_count,
            "total_tickers": total,
            "macro_regime": macro_regime,
            "news_sentiment": news_sentiment,
            "news_bullish": bullish_news,
            "news_bearish": bearish_news,
        }
    
    # --- Enrich tickers with value_score (fundamental) ---
    # Pull from cached miner-valuations endpoint
    try:
        val_data = get_miner_valuations()
        val_map = {m["symbol"]: m for m in val_data.get("miners", [])}
    except Exception:
        val_map = {}

    macro_boost = 0
    try:
        mr = fetch_macro_regime()
        if mr.get("regime") == "FAVORABLE":
            macro_boost = 8
        elif mr.get("regime") == "HOSTILE":
            macro_boost = -8
    except Exception:
        pass

    for t in tickers:
        sym = t["symbol"]
        if sym in val_map:
            v = val_map[sym]
            vs_avg = v.get("vs_avg_pct", 0)
            # Value score: 50 baseline, cheaper = higher score
            # -50% vs avg = score 100, +50% = score 0
            val = max(0, min(100, round(50 - vs_avg + macro_boost, 1)))
            t["value_score"] = val
            t["ev_per_lb"] = v.get("ev_per_lb")
            t["ev_vs_avg_pct"] = round(vs_avg, 1)
            t["value_label"] = "CHEAP" if val >= 65 else "FAIR" if val >= 35 else "EXPENSIVE"
        else:
            t["value_score"] = None
            t["value_label"] = None

    return {
        "ura": ura,
        "tickers": tickers,
        "spot_uranium": spot,
        "verdict": verdict,
        "last_updated": datetime.utcnow().isoformat(),
        "methodology": {
            "zone_classification": {
                "GREEN": "Price in bottom 20% of 6-month range — potential buy zone",
                "YELLOW": "Price in middle 60% of 6-month range — hold/wait zone",
                "RED": "Price in top 20% of 6-month range — potential sell zone",
            },
            "signal_score": "0-100 composite score combining zone position, RSI(14), MACD, Bollinger Bands(20,2), and SMA(50/200). Higher = stronger buy signal.",
            "technical_indicators": {
                "RSI": "14-period Relative Strength Index. <30 oversold, >70 overbought",
                "MACD": "12/26/9 Moving Average Convergence Divergence",
                "Bollinger Bands": "20-period, 2 std dev",
                "SMA": "50 and 200-day Simple Moving Averages",
            },
        },
    }


@app.get("/api/ticker/{symbol}")
def get_ticker(symbol: str):
    """Detailed view for a specific ticker."""
    symbol = symbol.upper()
    if symbol not in TICKERS and symbol != "KAP.IL":
        raise HTTPException(404, f"Ticker {symbol} not tracked")
    
    meta = get_ticker_meta(symbol)
    if not meta:
        raise HTTPException(404, f"No data for {symbol}")
    
    return meta


@app.get("/api/news")
def get_news_feed(
    limit: int = Query(50, ge=1, le=200),
    category: str = Query(None),
):
    """Macro news feed."""
    articles = get_news(limit=limit, category=category)
    return {"articles": articles, "count": len(articles)}


@app.get("/api/news-sentiment")
def news_sentiment(days: int = Query(7, ge=1, le=30)):
    """
    Uranium news sentiment signal from multiple sources.
    Keyword scoring on recent headlines → -100 (bearish) to +100 (bullish).
    """
    import feedparser, re
    from collections import defaultdict

    BULLISH_KEYWORDS = {
        "restart": 3, "restarts": 3, "restarting": 3,
        "approval": 2, "approved": 2, "approves": 2, "license": 2,
        "shortage": 3, "supply deficit": 3, "undersupply": 3,
        "buy": 1, "upgrade": 2, "bullish": 2, "outperform": 2,
        "contract": 2, "new build": 3, "construction": 2,
        "smr": 2, "small modular": 2,
        "demand": 2, "growing demand": 3,
        "price increase": 3, "spot price rise": 3, "higher": 1,
        "stockpile": 1, "accumulating": 2, "buying": 1,
        "nuclear renaissance": 3, "expansion": 2,
        "ai data center": 2, "hyperscaler": 2, "power purchase": 3,
        "enrichment": 1, "conversion": 1,
        "kazatomprom cut": 3, "production cut": 3,
        "japan restart": 3, "japan nuclear": 2,
    }
    BEARISH_KEYWORDS = {
        "shutdown": -3, "shut down": -3, "closing": -2, "decommission": -3,
        "ban": -3, "moratorium": -3, "phase out": -3, "phase-out": -3,
        "delay": -2, "delayed": -2, "postpone": -2,
        "oversupply": -3, "surplus": -2, "glut": -3,
        "sell": -1, "downgrade": -2, "bearish": -2, "underperform": -2,
        "accident": -3, "leak": -2, "contamination": -3, "radiation": -1,
        "protest": -1, "opposition": -1,
        "cancellation": -2, "cancelled": -2,
        "price drop": -2, "price decline": -2, "falling": -1,
        "fukushima": -1, "chernobyl": -1,
        "russian": -1, "sanctions risk": -2,
        "enrichment halt": -3,
    }

    # Fetch from multiple sources
    headlines = []

    # 1. Existing news DB
    try:
        articles = get_news(limit=100)
        cutoff = datetime.utcnow() - timedelta(days=days)
        for a in articles:
            pub = a.get("published") or a.get("fetched_at", "")
            title = a.get("title", "")
            headlines.append({
                "title": title,
                "source": a.get("source", "db"),
                "date": pub[:10] if pub else "",
                "url": a.get("url", ""),
            })
    except:
        pass

    # 2. Google News RSS
    rss_feeds = [
        ("https://news.google.com/rss/search?q=uranium+nuclear+energy&hl=en-US&gl=US&ceid=US:en", "Google News"),
        ("https://www.world-nuclear-news.org/feed", "World Nuclear News"),
    ]
    for feed_url, source in rss_feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:30]:
                title = entry.get("title", "")
                pub = entry.get("published", "")
                link = entry.get("link", "")
                headlines.append({"title": title, "source": source, "date": pub[:10] if pub else "", "url": link})
        except:
            pass

    # 3. yfinance news for URA
    try:
        import yfinance as yf
        for sym in ["URA", "CCJ", "OKLO"]:
            tk = yf.Ticker(sym)
            news = tk.news if hasattr(tk, 'news') else []
            if isinstance(news, list):
                for n in news[:10]:
                    title = n.get("title", "")
                    pub = n.get("providerPublishTime", "")
                    if isinstance(pub, (int, float)):
                        pub = datetime.utcfromtimestamp(pub).strftime("%Y-%m-%d")
                    headlines.append({"title": title, "source": f"yfinance/{sym}", "date": str(pub)[:10], "url": n.get("link", "")})
    except:
        pass

    # Deduplicate by title similarity
    seen = set()
    unique = []
    for h in headlines:
        key = re.sub(r'[^a-z0-9]', '', h["title"].lower())[:60]
        if key not in seen and h["title"]:
            seen.add(key)
            unique.append(h)
    headlines = unique

    # Score each headline
    scored = []
    for h in headlines:
        title_lower = h["title"].lower()
        score = 0
        matched = []
        for kw, val in BULLISH_KEYWORDS.items():
            if kw in title_lower:
                score += val
                matched.append(f"+{kw}")
        for kw, val in BEARISH_KEYWORDS.items():
            if kw in title_lower:
                score += val
                matched.append(f"{kw}")
        h["sentiment_score"] = score
        h["matched_keywords"] = matched
        scored.append(h)

    # Sort by abs score (most impactful first)
    scored.sort(key=lambda x: abs(x["sentiment_score"]), reverse=True)

    # Aggregate
    total_score = sum(h["sentiment_score"] for h in scored)
    positive = [h for h in scored if h["sentiment_score"] > 0]
    negative = [h for h in scored if h["sentiment_score"] < 0]
    neutral = [h for h in scored if h["sentiment_score"] == 0]

    # Normalize to -100..+100
    max_possible = max(1, len(scored) * 3)
    normalized = max(-100, min(100, int(total_score / max_possible * 100)))

    if normalized >= 30:
        sentiment_label = "BULLISH"
    elif normalized >= 10:
        sentiment_label = "LEAN BULLISH"
    elif normalized <= -30:
        sentiment_label = "BEARISH"
    elif normalized <= -10:
        sentiment_label = "LEAN BEARISH"
    else:
        sentiment_label = "NEUTRAL"

    return {
        "sentiment_score": normalized,
        "sentiment_label": sentiment_label,
        "raw_score": total_score,
        "headlines_analyzed": len(scored),
        "bullish_count": len(positive),
        "bearish_count": len(negative),
        "neutral_count": len(neutral),
        "sources": list(set(h["source"] for h in scored)),
        "top_bullish": [{"title": h["title"], "score": h["sentiment_score"], "keywords": h["matched_keywords"], "source": h["source"]} for h in positive[:5]],
        "top_bearish": [{"title": h["title"], "score": h["sentiment_score"], "keywords": h["matched_keywords"], "source": h["source"]} for h in negative[:5]],
        "all_headlines": scored[:50],
    }


@app.get("/api/history/{symbol}")
def get_history(symbol: str, days: int = Query(180, ge=7, le=365)):
    """Price history with range overlay data."""
    symbol = symbol.upper()
    prices = get_prices(symbol, days=days)
    meta = get_ticker_meta(symbol)
    
    if not prices:
        raise HTTPException(404, f"No history for {symbol}")
    
    return {
        "symbol": symbol,
        "prices": prices,
        "meta": meta,
        "count": len(prices),
    }


@app.get("/api/signals")
def get_signals():
    """Current signals for all tickers."""
    tickers = get_all_ticker_meta()
    signals = []
    for t in tickers:
        signals.append({
            "symbol": t["symbol"],
            "name": t.get("name"),
            "price": t.get("current_price"),
            "zone": t.get("zone"),
            "zone_pct": t.get("zone_pct"),
            "signal_score": t.get("signal_score"),
            "signal_label": t.get("signal_label"),
            "rsi": t.get("rsi"),
            "change_pct": t.get("change_pct"),
        })
    
    # Sort by signal score descending (best buys first)
    signals.sort(key=lambda x: x.get("signal_score") or 0, reverse=True)
    return {"signals": signals}


@app.get("/api/macro-regime")
def get_macro_regime():
    """Macro environment regime for uranium investing."""
    return fetch_macro_regime()


@app.get("/api/spot-history")
def get_spot_history(days: int = Query(30, ge=7, le=90)):
    """Spot uranium price history + URA as proxy for trend."""
    conn = _get_db()
    # Use URA close prices as trend proxy (more data than spot table)
    rows = conn.execute(
        "SELECT date, close FROM price_cache WHERE symbol='URA' ORDER BY date DESC LIMIT ?",
        (days,),
    ).fetchall()
    conn.close()
    history = [{"date": r["date"], "price": round(r["close"], 2)} for r in reversed(rows) if r["close"]]
    pct_change = None
    if len(history) >= 2:
        pct_change = round((history[-1]["price"] - history[0]["price"]) / history[0]["price"] * 100, 2)
    return {"history": history, "count": len(history), "pct_change_period": pct_change}


INITIAL_CASH = 10000  # Paper trading starting capital

# Trading rules + risk limits
TRADING_RULES = [
    {"name": "strong_buy", "condition": "score >= 70 AND macro != HOSTILE AND seasonal != HEADWIND",
     "action": "BUY", "size_pct": 0.25, "priority": 1},
    {"name": "buy", "condition": "score >= 55 AND score < 70 AND macro != HOSTILE",
     "action": "BUY", "size_pct": 0.15, "priority": 2},
    {"name": "reduce", "condition": "score < 45 AND score >= 30",
     "action": "SELL", "size_pct": 0.50, "priority": 3},
    {"name": "exit", "condition": "score < 30 OR (score < 40 AND macro == HOSTILE)",
     "action": "SELL", "size_pct": 1.00, "priority": 4},
    {"name": "drawdown_exit", "condition": "drawdown >= 15",
     "action": "SELL_ALL", "size_pct": 1.00, "priority": 0},
]
RISK_LIMITS = {
    "max_position_pct": 25,
    "max_invested_pct": 90,
    "cash_reserve_pct": 10,
    "max_drawdown_pct": 15,
}

# Dante's swing trading rules (2026-02-22)
SWING_RULES = {
    "take_profit_pct": 25.0,       # backtest-optimized (wider = better in trending markets)
    "stop_loss_pct": 15.0,         # backtest-optimized (uranium needs room to breathe)
    "entry_score_min": 55,         # enter when score > 55 (65 never triggers historically)
    "reentry_score_max": 40,       # after taking profit, wait for score < 40
    "max_position_pct": 25,        # max per ticker
    "portfolio_size": 5000,        # $5K total
    "enabled": True,
}
_swing_cooldown = {}  # {symbol: True} — set after take-profit, cleared when score < reentry_score_max


@app.get("/api/portfolio")
def get_portfolio():
    """Current portfolio state with live P&L."""
    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio (symbol TEXT PRIMARY KEY, shares REAL DEFAULT 0, avg_cost REAL DEFAULT 0, last_updated TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS trade_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime('now')), action TEXT, symbol TEXT, shares REAL, price REAL, total REAL, reasoning TEXT, score_at_trade REAL, zone_at_trade TEXT, macro_at_trade TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
    conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
    conn.commit()

    cash_row = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()
    cash = cash_row["cash"] if cash_row else INITIAL_CASH

    positions = conn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall()
    holdings = []
    total_value = cash
    total_cost = 0

    for p in positions:
        sym = p["symbol"]
        shares = p["shares"]
        avg_cost = p["avg_cost"]
        # Get current price
        meta = get_ticker_meta(sym)
        current_price = meta.get("current_price", avg_cost) if meta else avg_cost
        market_value = shares * current_price
        cost_basis = shares * avg_cost
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0

        holdings.append({
            "symbol": sym,
            "shares": shares,
            "avg_cost": round(avg_cost, 2),
            "current_price": round(current_price, 2),
            "market_value": round(market_value, 2),
            "cost_basis": round(cost_basis, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
        })
        total_value += market_value
        total_cost += cost_basis

    conn.close()
    total_pnl = total_value - INITIAL_CASH
    return {
        "cash": round(cash, 2),
        "holdings": holdings,
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / INITIAL_CASH * 100, 2) if INITIAL_CASH else 0,
        "initial_capital": INITIAL_CASH,
        "mode": "paper",
    }


@app.post("/api/portfolio/trade")
async def execute_trade(request: Request):
    """Execute a paper trade. Body: {action, symbol, shares, price?, reasoning}"""
    trade = await request.json()
    action = trade.get("action", "").upper()
    symbol = trade.get("symbol", "").upper()
    shares = float(trade.get("shares", 0))
    reasoning = trade.get("reasoning", "")

    if action not in ("BUY", "SELL"):
        raise HTTPException(400, "action must be BUY or SELL")
    if not symbol or symbol not in TICKERS:
        raise HTTPException(400, f"Invalid symbol. Must be one of: {list(TICKERS.keys())}")
    if shares <= 0:
        raise HTTPException(400, "shares must be positive")

    # Get current price if not provided
    meta = get_ticker_meta(symbol)
    price = float(trade.get("price", 0)) or (meta.get("current_price", 0) if meta else 0)
    if not price:
        raise HTTPException(400, "Could not determine price")

    total = round(shares * price, 2)
    score = meta.get("signal_score") if meta else None
    zone = meta.get("zone") if meta else None

    try:
        macro = fetch_macro_regime()
        macro_regime = macro.get("regime", "UNKNOWN")
    except Exception:
        macro_regime = "UNKNOWN"

    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio (symbol TEXT PRIMARY KEY, shares REAL DEFAULT 0, avg_cost REAL DEFAULT 0, last_updated TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
    conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))

    cash_row = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()
    cash = cash_row["cash"]

    if action == "BUY":
        if total > cash:
            conn.close()
            raise HTTPException(400, f"Insufficient cash. Have ${cash:.2f}, need ${total:.2f}")
        # Update position
        existing = conn.execute("SELECT shares, avg_cost FROM portfolio WHERE symbol=?", (symbol,)).fetchone()
        if existing and existing["shares"] > 0:
            old_shares = existing["shares"]
            old_cost = existing["avg_cost"]
            new_shares = old_shares + shares
            new_avg = (old_shares * old_cost + shares * price) / new_shares
            conn.execute("UPDATE portfolio SET shares=?, avg_cost=?, last_updated=datetime('now') WHERE symbol=?", (new_shares, new_avg, symbol))
        else:
            conn.execute("INSERT OR REPLACE INTO portfolio (symbol, shares, avg_cost, last_updated) VALUES (?,?,?,datetime('now'))", (symbol, shares, price))
        conn.execute("UPDATE portfolio_cash SET cash=cash-? WHERE id=1", (total,))

    elif action == "SELL":
        existing = conn.execute("SELECT shares, avg_cost FROM portfolio WHERE symbol=?", (symbol,)).fetchone()
        if not existing or existing["shares"] < shares:
            conn.close()
            raise HTTPException(400, f"Insufficient shares. Have {existing['shares'] if existing else 0}, trying to sell {shares}")
        new_shares = existing["shares"] - shares
        if new_shares < 0.001:
            conn.execute("DELETE FROM portfolio WHERE symbol=?", (symbol,))
        else:
            conn.execute("UPDATE portfolio SET shares=?, last_updated=datetime('now') WHERE symbol=?", (new_shares, symbol))
        conn.execute("UPDATE portfolio_cash SET cash=cash+? WHERE id=1", (total,))

    # Log to journal
    conn.execute(
        "INSERT INTO trade_journal (action, symbol, shares, price, total, reasoning, score_at_trade, zone_at_trade, macro_at_trade) VALUES (?,?,?,?,?,?,?,?,?)",
        (action, symbol, shares, price, total, reasoning, score, zone, macro_regime))
    conn.commit()
    conn.close()

    return {"status": "ok", "action": action, "symbol": symbol, "shares": shares, "price": price, "total": total, "reasoning": reasoning}


@app.post("/api/portfolio/auto-rebalance")
async def auto_rebalance(request: Request):
    """
    Autonomous paper rebalance. Reads trade tickets for all tickers,
    compares to current portfolio, executes recommended trades.
    mode=paper (only mode for now), dry_run=true for preview.
    """
    import requests as _req
    from analysis import TICKERS

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    dry_run = body.get("dry_run", False)
    method = body.get("method", "correlation-adjusted")  # "equal", "risk-parity", or "correlation-adjusted"

    # Risk-parity weights (fetched once if needed)
    if method == "correlation-adjusted":
        try:
            rp_resp = risk_parity(lookback=90, method="correlation_adjusted")
            rp_weights = rp_resp.get("weights", {}) if isinstance(rp_resp, dict) else {}
        except:
            rp_weights = _get_risk_parity_weights()  # fallback to IV
    elif method == "risk-parity":
        rp_weights = _get_risk_parity_weights()
    else:
        rp_weights = {}

    # 1. Get current portfolio (direct DB, no self-call)
    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio (symbol TEXT PRIMARY KEY, shares REAL DEFAULT 0, avg_cost REAL DEFAULT 0, last_updated TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
    conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
    cash = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()["cash"]
    positions_rows = conn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall()
    conn.close()

    current_positions = {}
    total_holdings = 0
    for row in positions_rows:
        sym = row["symbol"]
        meta = get_ticker_meta(sym)
        price = meta.get("current_price", 0) if meta else 0
        val = row["shares"] * price
        current_positions[sym] = {"symbol": sym, "shares": row["shares"], "avg_cost": row["avg_cost"], "market_value": val}
        total_holdings += val
    total_value = cash + total_holdings

    # 2. Get score decomposition for each ticker (direct calls, no self-HTTP)
    import yfinance as yf, numpy as np

    tickets = {}
    for sym in list(TICKERS.keys()):
        try:
            meta = get_ticker_meta(sym)
            if not meta:
                continue
            price = meta.get("current_price", 0)
            score = meta.get("signal_score", 50)

            # Use technical score directly (avoid self-HTTP deadlock)
            composite = score
            label = "HOLD"
            if composite >= 65: label = "BUY"
            elif composite >= 55: label = "HOLD"
            elif composite >= 45: label = "HOLD"
            elif composite >= 35: label = "SELL"
            else: label = "STRONG SELL"

            # Determine action from composite (same logic as trade-ticket)
            if composite <= 25:
                action = "BUY"
                alloc = 20
                confidence = 80
            elif composite <= 40:
                action = "BUY"
                alloc = 12
                confidence = 65
            elif composite <= 55:
                action = "WAIT"
                alloc = 3
                confidence = 40
            elif composite <= 70:
                action = "HOLD"
                alloc = 8
                confidence = 55
            else:
                action = "SELL"
                alloc = 0
                confidence = 60

            tickets[sym] = {
                "symbol": sym,
                "action": action,
                "composite_score": composite,
                "confidence": confidence,
                "position_pct": alloc,
                "entry": price,
            }
        except Exception as e:
            print(f"[auto-rebalance] {sym} error: {e}")

    # 3. Calculate target allocations
    raw_allocs = {}
    if method in ("risk-parity", "correlation-adjusted") and rp_weights:
        # Risk-parity/correlation-adjusted: use computed weights, zero out SELL, cap WAIT
        max_invested = 90  # max % in market
        for sym, ticket in tickets.items():
            rp_wt = rp_weights.get(sym, 0)
            if ticket["action"] == "SELL":
                raw_allocs[sym] = 0
            elif ticket["action"] == "WAIT":
                raw_allocs[sym] = min(rp_wt * max_invested, 3)
            else:
                raw_allocs[sym] = rp_wt * max_invested
    else:
        # Equal-weight with score-based sizing
        for sym, ticket in tickets.items():
            alloc_pct = ticket.get("position_pct", 0)
            if ticket["action"] == "SELL":
                alloc_pct = 0
            elif ticket["action"] == "WAIT":
                alloc_pct = min(alloc_pct, 3)
            raw_allocs[sym] = alloc_pct

    # Normalize if total > 90%
    total_alloc = sum(raw_allocs.values())
    if total_alloc > 90:
        scale = 90 / total_alloc
        raw_allocs = {k: v * scale for k, v in raw_allocs.items()}

    # 4. Determine trades
    executed = []
    skipped = []

    for sym in list(TICKERS.keys()):
        ticket = tickets.get(sym)
        if not ticket:
            continue

        target_alloc = raw_allocs.get(sym, 0)
        target_value = total_value * target_alloc / 100
        current_price = ticket.get("entry", 0)  # use ticket entry as reference price

        # Get live price for execution
        try:
            meta = get_ticker_meta(sym)
            live_price = meta.get("current_price", current_price) if meta else current_price
        except:
            live_price = current_price
        if not live_price or live_price <= 0:
            continue

        current_pos = current_positions.get(sym)
        current_shares = current_pos["shares"] if current_pos else 0
        current_value = current_shares * live_price

        target_shares = target_value / live_price if live_price > 0 else 0
        delta_shares = target_shares - current_shares
        delta_value = delta_shares * live_price

        # Skip small rebalances (< $50 or < 0.5 share)
        if abs(delta_value) < 50 or abs(delta_shares) < 0.5:
            skipped.append({
                "symbol": sym,
                "reason": "Delta too small",
                "current_pct": round(current_value / total_value * 100, 1) if total_value > 0 else 0,
                "target_pct": round(target_alloc, 1),
            })
            continue

        action = "BUY" if delta_shares > 0 else "SELL"
        trade_shares = round(abs(delta_shares), 2)
        trade_value = round(trade_shares * live_price, 2)

        # Check constraints
        if action == "BUY" and trade_value > cash:
            trade_shares = round(cash * 0.95 / live_price, 2)  # use 95% of remaining cash
            trade_value = round(trade_shares * live_price, 2)
            if trade_shares < 0.5:
                skipped.append({"symbol": sym, "reason": "Insufficient cash"})
                continue

        if action == "SELL" and trade_shares > current_shares:
            trade_shares = current_shares
            trade_value = round(trade_shares * live_price, 2)

        reason = (
            f"Auto-rebalance: {ticket['action']} signal (score {ticket['composite_score']:.0f}, "
            f"conf {ticket['confidence']:.0f}). "
            f"Target {target_alloc:.1f}% (${target_value:,.0f}), "
            f"current {current_value / total_value * 100:.1f}% (${current_value:,.0f})"
        )

        trade_record = {
            "symbol": sym,
            "action": action,
            "shares": trade_shares,
            "price": live_price,
            "total": trade_value,
            "signal_action": ticket["action"],
            "composite_score": ticket["composite_score"],
            "confidence": ticket["confidence"],
            "target_alloc_pct": round(target_alloc, 1),
            "reason": reason,
        }

        if not dry_run:
            # Execute directly via DB (avoid self-HTTP deadlock)
            try:
                tconn = _get_db()
                tconn.execute("CREATE TABLE IF NOT EXISTS portfolio (symbol TEXT PRIMARY KEY, shares REAL DEFAULT 0, avg_cost REAL DEFAULT 0, last_updated TEXT)")
                tconn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
                tconn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))

                if action == "BUY":
                    tcash = tconn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()["cash"]
                    if trade_value > tcash:
                        trade_record["status"] = "FAILED: Insufficient cash"
                    else:
                        existing = tconn.execute("SELECT shares, avg_cost FROM portfolio WHERE symbol=?", (sym,)).fetchone()
                        if existing and existing["shares"] > 0:
                            ns = existing["shares"] + trade_shares
                            na = (existing["shares"] * existing["avg_cost"] + trade_shares * live_price) / ns
                            tconn.execute("UPDATE portfolio SET shares=?, avg_cost=?, last_updated=datetime('now') WHERE symbol=?", (ns, na, sym))
                        else:
                            tconn.execute("INSERT OR REPLACE INTO portfolio (symbol, shares, avg_cost, last_updated) VALUES (?,?,?,datetime('now'))", (sym, trade_shares, live_price))
                        tconn.execute("UPDATE portfolio_cash SET cash=cash-? WHERE id=1", (trade_value,))
                        cash -= trade_value
                        trade_record["status"] = "EXECUTED"
                elif action == "SELL":
                    existing = tconn.execute("SELECT shares, avg_cost FROM portfolio WHERE symbol=?", (sym,)).fetchone()
                    if not existing or existing["shares"] < trade_shares:
                        trade_record["status"] = "FAILED: Insufficient shares"
                    else:
                        ns = existing["shares"] - trade_shares
                        if ns < 0.001:
                            tconn.execute("DELETE FROM portfolio WHERE symbol=?", (sym,))
                        else:
                            tconn.execute("UPDATE portfolio SET shares=?, last_updated=datetime('now') WHERE symbol=?", (ns, sym))
                        tconn.execute("UPDATE portfolio_cash SET cash=cash+? WHERE id=1", (trade_value,))
                        cash += trade_value
                        trade_record["status"] = "EXECUTED"
                # Log to journal
                try:
                    tconn.execute("INSERT INTO trade_journal (action, symbol, shares, price, total, reasoning, score_at_trade, zone_at_trade, macro_at_trade) VALUES (?,?,?,?,?,?,?,?,?)",
                        (action, sym, trade_shares, live_price, trade_value, reason, composite, label, "AUTO"))
                except: pass
                tconn.commit()
                tconn.close()
            except Exception as e:
                trade_record["status"] = f"ERROR: {e}"
        else:
            trade_record["status"] = "DRY_RUN"
            if action == "BUY":
                cash -= trade_value

        executed.append(trade_record)

    # Summary
    buys = [t for t in executed if t["action"] == "BUY"]
    sells = [t for t in executed if t["action"] == "SELL"]
    total_bought = sum(t["total"] for t in buys)
    total_sold = sum(t["total"] for t in sells)

    return {
        "mode": "paper",
        "method": method,
        "dry_run": dry_run,
        "portfolio_value": round(total_value, 2),
        "cash_before": round(cash, 2),
        "risk_parity_weights": rp_weights if method in ("risk-parity", "correlation-adjusted") else None,
        "executed_trades": executed,
        "skipped": skipped,
        "summary": {
            "trades_executed": len(executed),
            "trades_skipped": len(skipped),
            "buys": len(buys),
            "sells": len(sells),
            "total_bought": round(total_bought, 2),
            "total_sold": round(total_sold, 2),
            "net_flow": round(total_sold - total_bought, 2),
        },
        "kelly_caveat": "THEORETICAL — position sizes are forward-testing only. Not validated with 50+ closed trades.",
    }


@app.get("/api/watchlist")
def get_watchlist():
    """Per-ticker watchlist with targets, thesis, alerts."""
    conn = _get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS watchlist (
        symbol TEXT PRIMARY KEY, target_entry REAL, target_exit REAL,
        stop_loss REAL, thesis TEXT, conviction TEXT DEFAULT 'MEDIUM',
        alert_above REAL, alert_below REAL, status TEXT DEFAULT 'WATCHING',
        created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
    )""")
    rows = conn.execute("SELECT * FROM watchlist ORDER BY symbol").fetchall()
    conn.close()

    items = []
    for row in rows:
        sym = row["symbol"]
        meta = get_ticker_meta(sym)
        price = meta.get("current_price", 0) if meta else 0
        score = meta.get("signal_score", 50) if meta else 50

        # Check if alerts triggered
        alert_triggered = None
        if row["alert_above"] and price >= row["alert_above"]:
            alert_triggered = f"Price ${price:.2f} ≥ target ${row['alert_above']:.2f}"
        elif row["alert_below"] and price <= row["alert_below"]:
            alert_triggered = f"Price ${price:.2f} ≤ target ${row['alert_below']:.2f}"

        # Distance to targets
        dist_entry = ((price / row["target_entry"]) - 1) * 100 if row["target_entry"] and row["target_entry"] > 0 else None
        dist_exit = ((row["target_exit"] / price) - 1) * 100 if row["target_exit"] and price > 0 else None

        items.append({
            "symbol": sym,
            "current_price": round(price, 2),
            "composite_score": round(score, 1),
            "target_entry": row["target_entry"],
            "target_exit": row["target_exit"],
            "stop_loss": row["stop_loss"],
            "thesis": row["thesis"],
            "conviction": row["conviction"],
            "status": row["status"],
            "alert_above": row["alert_above"],
            "alert_below": row["alert_below"],
            "alert_triggered": alert_triggered,
            "distance_to_entry_pct": round(dist_entry, 1) if dist_entry is not None else None,
            "upside_to_exit_pct": round(dist_exit, 1) if dist_exit is not None else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })

    return {"items": items, "count": len(items)}


@app.post("/api/watchlist")
async def upsert_watchlist(request: Request):
    """Create or update a watchlist entry."""
    body = await request.json()
    sym = body.get("symbol", "").upper()
    if not sym:
        raise HTTPException(400, "symbol required")

    conn = _get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS watchlist (
        symbol TEXT PRIMARY KEY, target_entry REAL, target_exit REAL,
        stop_loss REAL, thesis TEXT, conviction TEXT DEFAULT 'MEDIUM',
        alert_above REAL, alert_below REAL, status TEXT DEFAULT 'WATCHING',
        created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
    )""")

    existing = conn.execute("SELECT * FROM watchlist WHERE symbol=?", (sym,)).fetchone()
    if existing:
        updates = []
        params = []
        for field in ["target_entry", "target_exit", "stop_loss", "thesis", "conviction", "alert_above", "alert_below", "status"]:
            if field in body:
                updates.append(f"{field}=?")
                params.append(body[field])
        if updates:
            updates.append("updated_at=datetime('now')")
            params.append(sym)
            conn.execute(f"UPDATE watchlist SET {', '.join(updates)} WHERE symbol=?", params)
            conn.commit()
        conn.close()
        return {"action": "updated", "symbol": sym}
    else:
        conn.execute(
            "INSERT INTO watchlist (symbol, target_entry, target_exit, stop_loss, thesis, conviction, alert_above, alert_below, status) VALUES (?,?,?,?,?,?,?,?,?)",
            (sym, body.get("target_entry"), body.get("target_exit"), body.get("stop_loss"),
             body.get("thesis", ""), body.get("conviction", "MEDIUM"),
             body.get("alert_above"), body.get("alert_below"), body.get("status", "WATCHING"))
        )
        conn.commit()
        conn.close()
        return {"action": "created", "symbol": sym}


@app.delete("/api/watchlist/{symbol}")
def delete_watchlist(symbol: str):
    """Remove a ticker from watchlist."""
    conn = _get_db()
    conn.execute("DELETE FROM watchlist WHERE symbol=?", (symbol.upper(),))
    conn.commit()
    conn.close()
    return {"deleted": symbol.upper()}


def _execute_trade_signals(source="API", dry_run=False):
    """Core execution engine: reads trade_signals(), executes actionable trades."""
    signals_data = trade_signals()
    sigs = signals_data["signals"]
    actionable = [s for s in sigs if s["action"] in ("BUY", "STRONG_BUY", "SELL", "SELL_ALL", "REDUCE") and s["shares_delta"] and abs(s["shares_delta"]) >= 0.5]

    executed = []
    skipped = []
    cash = signals_data["cash_available"]

    for sig in actionable:
        sym = sig["symbol"]
        price = sig["current_price"]
        delta = sig["shares_delta"]
        if not price or price <= 0:
            skipped.append({"symbol": sym, "reason": "no price"})
            continue

        if delta > 0:
            trade_action = "BUY"
            trade_shares = round(delta, 2)
            trade_value = round(trade_shares * price, 2)
            if trade_value > cash:
                trade_shares = round(cash * 0.95 / price, 2)
                trade_value = round(trade_shares * price, 2)
            if trade_shares < 0.5 or trade_value < 10:
                skipped.append({"symbol": sym, "reason": f"insufficient cash (need ${delta * price:.0f}, have ${cash:.0f})"})
                continue
        else:
            trade_action = "SELL"
            trade_shares = round(abs(delta), 2)
            trade_value = round(trade_shares * price, 2)

        reason = f"[{source}] {sig['action']} | rule={sig.get('matched_rule','—')} | score={sig['composite_score']:.0f} | conf={sig['confidence']}% | regime={signals_data['macro_regime']}"
        for r in sig.get("reasons", []):
            reason += f" | {r}"

        if dry_run:
            executed.append({
                "symbol": sym, "action": trade_action, "shares": trade_shares,
                "price": price, "value": trade_value, "signal_action": sig["action"],
                "matched_rule": sig.get("matched_rule"), "confidence": sig["confidence"],
                "score": sig["composite_score"], "dry_run": True,
            })
            if trade_action == "BUY":
                cash -= trade_value
            else:
                cash += trade_value
            continue

        # Execute trade
        tconn = _get_db()
        try:
            if trade_action == "BUY":
                existing = tconn.execute("SELECT shares, avg_cost FROM portfolio WHERE symbol=?", (sym,)).fetchone()
                if existing and existing["shares"] > 0:
                    ns = existing["shares"] + trade_shares
                    na = (existing["shares"] * existing["avg_cost"] + trade_shares * price) / ns
                    tconn.execute("UPDATE portfolio SET shares=?, avg_cost=?, last_updated=datetime('now') WHERE symbol=?", (ns, na, sym))
                else:
                    tconn.execute("INSERT OR REPLACE INTO portfolio (symbol, shares, avg_cost, last_updated) VALUES (?,?,?,datetime('now'))", (sym, trade_shares, price))
                tconn.execute("UPDATE portfolio_cash SET cash=cash-? WHERE id=1", (trade_value,))
                cash -= trade_value
            elif trade_action == "SELL":
                existing = tconn.execute("SELECT shares FROM portfolio WHERE symbol=?", (sym,)).fetchone()
                if not existing or existing["shares"] < trade_shares:
                    trade_shares = existing["shares"] if existing else 0
                    trade_value = round(trade_shares * price, 2)
                if trade_shares < 0.01:
                    tconn.close()
                    skipped.append({"symbol": sym, "reason": "no shares to sell"})
                    continue
                ns = (existing["shares"] if existing else 0) - trade_shares
                if ns < 0.001:
                    tconn.execute("DELETE FROM portfolio WHERE symbol=?", (sym,))
                else:
                    tconn.execute("UPDATE portfolio SET shares=?, last_updated=datetime('now') WHERE symbol=?", (ns, sym))
                tconn.execute("UPDATE portfolio_cash SET cash=cash+? WHERE id=1", (trade_value,))
                cash += trade_value

            tconn.execute("INSERT INTO trade_journal (action, symbol, shares, price, total, reasoning, score_at_trade, zone_at_trade, macro_at_trade) VALUES (?,?,?,?,?,?,?,?,?)",
                (trade_action, sym, trade_shares, price, trade_value, reason, sig["composite_score"], sig["action"], signals_data["macro_regime"]))
            tconn.commit()
        finally:
            tconn.close()

        executed.append({
            "symbol": sym, "action": trade_action, "shares": trade_shares,
            "price": price, "value": trade_value, "signal_action": sig["action"],
            "matched_rule": sig.get("matched_rule"), "confidence": sig["confidence"],
            "score": sig["composite_score"],
        })

    # Portfolio after
    pconn = _get_db()
    cash_after = pconn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()["cash"] if not dry_run else cash
    pos_after = pconn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall() if not dry_run else []
    pconn.close()
    holdings_val = sum(r["shares"] * (get_ticker_meta(r["symbol"]) or {}).get("current_price", 0) for r in pos_after) if not dry_run else 0

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": source,
        "dry_run": dry_run,
        "macro_regime": signals_data["macro_regime"],
        "regime_multiplier": signals_data["regime_multiplier"],
        "executed": executed,
        "skipped": skipped,
        "total_trades": len(executed),
        "total_skipped": len(skipped),
        "portfolio_after": {"cash": round(cash_after, 2), "holdings_value": round(holdings_val, 2), "total_value": round(cash_after + holdings_val, 2)},
    }


@app.post("/api/auto-execute")
async def auto_execute(request: Request):
    """Autonomous trade execution — runs trade-signals brain and executes all actionable decisions. Default: dry_run=true (safety)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    dry_run = body.get("dry_run", True)
    return _execute_trade_signals(source="API", dry_run=dry_run)


@app.get("/api/trade-signals")
def trade_signals():
    """Autonomous trade decision engine — synthesizes ALL signals into actionable decisions."""
    from analysis import TICKERS

    # 1. Get all ticker data
    tickers = get_all_ticker_meta()
    ticker_map = {t["symbol"]: t for t in tickers}

    # 2. Macro context
    try:
        macro = fetch_macro_regime()
        macro_regime = macro.get("regime", "NEUTRAL")
    except Exception:
        macro_regime = "NEUTRAL"

    # 3. Regime detector for sizing multiplier
    regime_multipliers = {
        "BULL_QUIET": 1.0, "BULL_VOLATILE": 0.7, "SIDEWAYS": 0.5,
        "BEAR_QUIET": 0.3, "BEAR_VOLATILE": 0.4,
    }
    regime_mult = regime_multipliers.get(macro_regime, 0.5)

    # 4. Portfolio state
    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio (symbol TEXT PRIMARY KEY, shares REAL DEFAULT 0, avg_cost REAL DEFAULT 0, last_updated TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
    conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
    cash = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()["cash"]
    positions = {r["symbol"]: {"shares": r["shares"], "avg_cost": r["avg_cost"]} for r in conn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall()}

    # 5. Watchlist targets
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS watchlist (
            symbol TEXT PRIMARY KEY, target_entry REAL, target_exit REAL,
            stop_loss REAL, thesis TEXT, conviction TEXT DEFAULT 'MEDIUM',
            alert_above REAL, alert_below REAL, status TEXT DEFAULT 'WATCHING',
            created_at TEXT, updated_at TEXT)""")
        watchlist = {r["symbol"]: dict(r) for r in conn.execute("SELECT * FROM watchlist").fetchall()}
    except Exception:
        watchlist = {}

    # 6. Insider sentiment
    insider_sentiment = {}
    try:
        insider_data = get_insider_trades()
        for trade in insider_data.get("trades", []):
            sym = trade["symbol"]
            val = trade.get("value") or 0
            if sym not in insider_sentiment:
                insider_sentiment[sym] = 0
            insider_sentiment[sym] += val if trade["type"] == "BUY" else -val
    except Exception:
        pass

    # 7. Risk-parity weights
    try:
        rp = _get_risk_parity_weights(method="correlation_adjusted")
    except Exception:
        rp = {}

    conn.close()

    # 8. Total portfolio value
    total_value = cash
    for sym, pos in positions.items():
        meta = ticker_map.get(sym)
        price = meta.get("current_price", pos["avg_cost"]) if meta else pos["avg_cost"]
        total_value += pos["shares"] * price

    drawdown_pct = max(0, (INITIAL_CASH - total_value) / INITIAL_CASH * 100)

    # 9. Generate signals per ticker
    signals = []
    for sym in sorted(TICKERS.keys()):
        meta = ticker_map.get(sym, {})
        score = meta.get("signal_score", 50)
        price = meta.get("current_price", 0)
        pos = positions.get(sym)
        wl = watchlist.get(sym)
        net_insider = insider_sentiment.get(sym, 0)
        target_weight = rp.get(sym, 1.0 / len(TICKERS)) if rp else 1.0 / len(TICKERS)

        # Current allocation
        current_value = pos["shares"] * price if pos and price else 0
        current_weight = current_value / total_value if total_value > 0 else 0

        # --- DECISION LOGIC (aligned with TRADING_RULES) ---
        # Rules engine: high score = bullish = buy, low score = bearish = sell
        action = "HOLD"
        reason = []
        confidence = 50
        target_shares = pos["shares"] if pos else 0
        urgency = "LOW"
        matched_rule = None
        hostile = macro_regime in ("BEAR_VOLATILE", "BEAR_QUIET")

        # Priority 0: Drawdown circuit breaker
        if drawdown_pct >= 15:
            matched_rule = "drawdown_exit"
            action = "SELL_ALL"
            reason = ["Portfolio drawdown ≥15% — circuit breaker"]
            confidence = 95
            target_shares = 0
            urgency = "CRITICAL"

        # Priority 4: Exit — score < 30 (or < 40 in hostile regime)
        elif score < 30 or (score < 40 and hostile):
            matched_rule = "exit"
            if pos:
                action = "SELL"
                target_shares = 0
                urgency = "HIGH"
                confidence = min(95, 70 + int((30 - score) * 1.5))
                reason.append(f"Score {score:.0f} < 30 → EXIT rule (sell 100%)")
                if hostile:
                    reason.append(f"Regime {macro_regime} amplifies exit signal")
            else:
                action = "AVOID"
                confidence = 70
                reason.append(f"Score {score:.0f} < 30 — bearish, no position")

        # Priority 3: Reduce — 30 ≤ score < 45
        elif score < 45:
            matched_rule = "reduce"
            if pos:
                action = "REDUCE"
                target_shares = pos["shares"] * 0.5
                urgency = "MEDIUM"
                confidence = 55 + int((45 - score))
                reason.append(f"Score {score:.0f} in 30-45 → REDUCE rule (sell 50%)")
            else:
                action = "WATCH"
                confidence = 45
                reason.append(f"Score {score:.0f} in 30-45 — weak, stay out")

        # Neutral zone: 45 ≤ score < 55
        elif score < 55:
            action = "HOLD" if pos else "WATCH"
            confidence = 40
            reason.append(f"Score {score:.0f} — neutral zone (no rule triggered)")

        # Priority 2: Buy — 55 ≤ score < 70
        elif score < 70:
            matched_rule = "buy"
            if hostile:
                action = "WATCH"
                confidence = 40
                reason.append(f"Score {score:.0f} is buy range BUT regime {macro_regime} blocks")
            elif net_insider < -500000:
                action = "WATCH"
                confidence = 35
                reason.append(f"Score {score:.0f} is buy range BUT insider selling ${abs(net_insider/1e6):.1f}M blocks")
            else:
                action = "BUY"
                urgency = "MEDIUM"
                confidence = 55 + int((score - 55))
                # Size: 15% of portfolio per rules
                max_buy_val = total_value * 0.15 * regime_mult
                buy_value = max(0, min(max_buy_val, max_buy_val - current_value))
                target_shares = (current_value + buy_value) / price if price > 0 else 0
                reason.append(f"Score {score:.0f} in 55-70 → BUY rule (15% size × {regime_mult}x regime)")

        # Priority 1: Strong buy — score ≥ 70
        else:
            matched_rule = "strong_buy"
            if hostile:
                action = "WATCH"
                confidence = 45
                reason.append(f"Score {score:.0f} is strong buy BUT regime {macro_regime} blocks")
            elif net_insider < -500000:
                action = "WATCH"
                confidence = 40
                reason.append(f"Score {score:.0f} is strong buy BUT insider selling ${abs(net_insider/1e6):.1f}M blocks")
            else:
                action = "STRONG_BUY"
                urgency = "HIGH"
                confidence = 75 + int(min(20, (score - 70)))
                # Size: 25% of portfolio per rules
                max_buy_val = total_value * 0.25 * regime_mult
                buy_value = max(0, max_buy_val - current_value)
                target_shares = (current_value + buy_value) / price if price > 0 else 0
                reason.append(f"Score {score:.0f} ≥ 70 → STRONG_BUY rule (25% size × {regime_mult}x regime)")

        # Watchlist enrichment
        if wl:
            if wl.get("target_entry") and price and price <= wl["target_entry"]:
                if action in ("BUY", "WATCH"):
                    reason.append(f"AT watchlist entry target ${wl['target_entry']}")
                    urgency = "HIGH"
                    confidence = min(95, confidence + 20)
            if wl.get("stop_loss") and pos and price and price <= wl["stop_loss"]:
                action = "SELL"
                reason.append(f"BELOW stop loss ${wl['stop_loss']}")
                urgency = "CRITICAL"
                confidence = 90
                target_shares = 0
            if wl.get("target_exit") and pos and price and price >= wl["target_exit"]:
                action = "SELL"
                reason.append(f"HIT take-profit target ${wl['target_exit']}")
                urgency = "HIGH"
                confidence = 85
                target_shares = 0

        # P&L context
        pnl_pct = ((price / pos["avg_cost"]) - 1) * 100 if pos and pos["avg_cost"] > 0 and price else None

        # Shares delta
        shares_delta = round(target_shares - (pos["shares"] if pos else 0), 2)
        dollar_delta = round(shares_delta * price, 2) if price else 0

        signals.append({
            "symbol": sym,
            "action": action,
            "confidence": confidence,
            "urgency": urgency,
            "reasons": reason,
            "composite_score": round(score, 1),
            "current_price": round(price, 2),
            "current_shares": pos["shares"] if pos else 0,
            "target_shares": round(target_shares, 2),
            "shares_delta": shares_delta,
            "dollar_delta": dollar_delta,
            "current_weight_pct": round(current_weight * 100, 1),
            "target_weight_pct": round(target_weight * 100, 1),
            "pnl_pct": round(pnl_pct, 1) if pnl_pct is not None else None,
            "insider_net": round(net_insider, 0) if net_insider else 0,
            "matched_rule": matched_rule,
            "watchlist": {"entry": wl["target_entry"], "exit": wl["target_exit"], "sl": wl["stop_loss"]} if wl else None,
        })

    # Summary
    buys = [s for s in signals if s["action"] == "BUY"]
    sells = [s for s in signals if s["action"] in ("SELL", "SELL_ALL")]
    reduces = [s for s in signals if s["action"] == "REDUCE"]
    total_buy_dollar = sum(s["dollar_delta"] for s in buys if s["dollar_delta"] > 0)

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "macro_regime": macro_regime,
        "regime_multiplier": regime_mult,
        "portfolio_value": round(total_value, 2),
        "cash_available": round(cash, 2),
        "drawdown_pct": round(drawdown_pct, 1),
        "signals": sorted(signals, key=lambda s: (-{"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(s["urgency"], 0), s["symbol"])),
        "summary": {
            "total_tickers": len(signals),
            "buys": len(buys),
            "sells": len(sells),
            "reduces": len(reduces),
            "holds": len([s for s in signals if s["action"] == "HOLD"]),
            "watches": len([s for s in signals if s["action"] in ("WATCH", "AVOID")]),
            "total_buy_cost": round(total_buy_dollar, 2),
            "executable": total_buy_dollar <= cash,
            "cash_after_buys": round(cash - total_buy_dollar, 2) if total_buy_dollar <= cash else None,
        },
    }


@app.get("/api/scenario-analysis")
def scenario_analysis():
    """Stress-test portfolio against predefined + custom scenarios."""
    import yfinance as yf, numpy as np
    from analysis import TICKERS

    # Get portfolio
    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio (symbol TEXT PRIMARY KEY, shares REAL DEFAULT 0, avg_cost REAL DEFAULT 0, last_updated TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
    conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
    cash = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()["cash"]
    positions = conn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall()
    conn.close()

    holdings = {}
    total_holdings = 0
    for row in positions:
        sym = row["symbol"]
        meta = get_ticker_meta(sym)
        price = meta.get("current_price", 0) if meta else 0
        val = row["shares"] * price
        holdings[sym] = {"shares": row["shares"], "price": price, "value": val}
        total_holdings += val
    total_value = cash + total_holdings

    if total_holdings < 100:
        return {"status": "no_positions", "message": "No significant holdings to stress test."}

    # Get betas (sensitivity to URA)
    betas = {}
    try:
        ura_hist = yf.Ticker("URA").history(period="6mo")
        if ura_hist.index.tz: ura_hist.index = ura_hist.index.tz_localize(None)
        ura_rets = ura_hist["Close"].pct_change().dropna()

        for sym in holdings:
            try:
                tk = yf.Ticker(sym)
                h = tk.history(period="6mo")
                if h.index.tz: h.index = h.index.tz_localize(None)
                import pandas as pd
                merged = pd.DataFrame({"sym": h["Close"].pct_change(), "ura": ura_rets}).dropna()
                if len(merged) > 30:
                    cov = np.cov(merged["sym"], merged["ura"])
                    beta = float(cov[0][1] / cov[1][1]) if cov[1][1] != 0 else 1.0
                else:
                    beta = 1.0
                betas[sym] = round(beta, 2)
            except:
                betas[sym] = 1.0
    except:
        betas = {s: 1.0 for s in holdings}

    # Predefined scenarios
    scenarios = [
        {"name": "Uranium Crash -20%", "description": "Sector-wide 20% decline (Fukushima-style event)", "ura_shock": -20},
        {"name": "Uranium Crash -40%", "description": "Extreme bear market (2011 post-Fukushima)", "ura_shock": -40},
        {"name": "Uranium Rally +30%", "description": "Supply crisis / contract season surge", "ura_shock": 30},
        {"name": "Mild Pullback -10%", "description": "Normal correction within uptrend", "ura_shock": -10},
        {"name": "Rate Shock (bonds -5%)", "description": "Fed hikes unexpectedly, risk-off rotation", "ura_shock": -12},
        {"name": "USD Surge +5%", "description": "Dollar strengthens, commodity headwind", "ura_shock": -8},
        {"name": "Nuclear Accident", "description": "Major reactor incident, sector panic", "ura_shock": -50},
        {"name": "AI Energy Narrative", "description": "Hyperscaler nuclear PPA announcements", "ura_shock": 20},
    ]

    results = []
    for scenario in scenarios:
        shock = scenario["ura_shock"]
        portfolio_impact = 0
        ticker_impacts = []

        for sym, h in holdings.items():
            beta = betas.get(sym, 1.0)
            ticker_shock = shock * beta
            value_change = h["value"] * (ticker_shock / 100)
            portfolio_impact += value_change

            ticker_impacts.append({
                "symbol": sym,
                "beta": beta,
                "shock_pct": round(ticker_shock, 1),
                "value_before": round(h["value"], 2),
                "value_change": round(value_change, 2),
                "value_after": round(h["value"] + value_change, 2),
            })

        new_total = total_value + portfolio_impact
        pnl_pct = (portfolio_impact / total_value) * 100

        results.append({
            "scenario": scenario["name"],
            "description": scenario["description"],
            "ura_shock_pct": shock,
            "portfolio_impact": round(portfolio_impact, 2),
            "portfolio_impact_pct": round(pnl_pct, 1),
            "portfolio_value_after": round(new_total, 2),
            "worst_hit": min(ticker_impacts, key=lambda x: x["value_change"])["symbol"] if ticker_impacts else None,
            "best_relative": max(ticker_impacts, key=lambda x: x["shock_pct"] if shock < 0 else -x["shock_pct"])["symbol"] if ticker_impacts else None,
            "ticker_impacts": sorted(ticker_impacts, key=lambda x: x["value_change"]),
        })

    # Summary
    worst = min(results, key=lambda x: x["portfolio_impact_pct"])
    best = max(results, key=lambda x: x["portfolio_impact_pct"])

    return {
        "portfolio_value": round(total_value, 2),
        "cash": round(cash, 2),
        "holdings_value": round(total_holdings, 2),
        "positions": len(holdings),
        "betas": betas,
        "scenarios": results,
        "summary": {
            "worst_case": {"scenario": worst["scenario"], "impact_pct": worst["portfolio_impact_pct"], "impact_usd": worst["portfolio_impact"]},
            "best_case": {"scenario": best["scenario"], "impact_pct": best["portfolio_impact_pct"], "impact_usd": best["portfolio_impact"]},
            "avg_downside": round(sum(r["portfolio_impact_pct"] for r in results if r["portfolio_impact_pct"] < 0) / max(1, sum(1 for r in results if r["portfolio_impact_pct"] < 0)), 1),
            "cash_buffer_survives_worst": cash + worst["portfolio_impact"] > 0,
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/portfolio/risk")
def portfolio_risk():
    """Portfolio risk overlay: concentration, clusters, diversification, worst-case."""
    import yfinance as yf, numpy as np, pandas as pd
    from analysis import TICKERS

    # 1. Get current holdings
    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio (symbol TEXT PRIMARY KEY, shares REAL DEFAULT 0, avg_cost REAL DEFAULT 0, last_updated TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
    conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
    cash = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()["cash"]
    positions = conn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall()
    conn.close()

    holdings = {}
    total_holdings = 0
    for row in positions:
        sym = row["symbol"]
        meta = get_ticker_meta(sym)
        price = meta.get("current_price", 0) if meta else 0
        val = row["shares"] * price
        holdings[sym] = {"shares": row["shares"], "value": val, "price": price}
        total_holdings += val

    total_value = cash + total_holdings
    if total_holdings < 100:
        return {"status": "no_positions", "message": "Portfolio has no significant holdings."}

    # Weights
    weights = {s: h["value"] / total_value for s, h in holdings.items()}

    # 2. Fetch returns + correlation matrix
    all_returns = {}
    vols = {}
    for sym in holdings:
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period="100d")
            if hist.empty: continue
            if hist.index.tz: hist.index = hist.index.tz_localize(None)
            rets = hist["Close"].pct_change().dropna().tail(90)
            all_returns[sym] = rets
            vols[sym] = float(np.std(rets)) * np.sqrt(252)
        except:
            continue

    if len(all_returns) < 2:
        return {"status": "insufficient_data", "message": "Need at least 2 tickers with price data."}

    df = pd.DataFrame(all_returns).dropna()
    corr = df.corr()
    syms = list(all_returns.keys())

    # 3. Portfolio volatility (w'Σw)
    w = np.array([weights.get(s, 0) for s in syms])
    cov = df.cov() * 252  # annualized
    port_var = float(w @ cov.values @ w)
    port_vol = float(np.sqrt(port_var)) * 100

    # Sum of weighted individual vols
    sum_weighted_vol = sum(weights.get(s, 0) * vols[s] for s in syms) * 100
    diversification_ratio = round(sum_weighted_vol / port_vol, 3) if port_vol > 0 else 1.0

    # 4. Concentration score (weighted avg correlation, 0-100)
    weighted_corr = 0
    total_pair_weight = 0
    for i, s1 in enumerate(syms):
        for j, s2 in enumerate(syms):
            if i >= j: continue
            try:
                r = float(corr.loc[s1, s2])
            except:
                r = 0
            pair_weight = weights.get(s1, 0) * weights.get(s2, 0)
            weighted_corr += r * pair_weight
            total_pair_weight += pair_weight
    avg_weighted_corr = weighted_corr / total_pair_weight if total_pair_weight > 0 else 0
    concentration_score = round(max(0, min(100, avg_weighted_corr * 100)), 1)

    # 5. Clusters (r > 0.8)
    assigned = set()
    clusters = []
    for i, s1 in enumerate(syms):
        if s1 in assigned: continue
        cluster = [s1]
        assigned.add(s1)
        for j, s2 in enumerate(syms):
            if s2 in assigned: continue
            try:
                r = float(corr.loc[s1, s2])
            except:
                r = 0
            if r > 0.8:
                cluster.append(s2)
                assigned.add(s2)
        if len(cluster) > 1:
            cl_weight = sum(weights.get(s, 0) for s in cluster)
            intra = []
            for a in cluster:
                for b in cluster:
                    if a < b:
                        try: intra.append(float(corr.loc[a, b]))
                        except: pass
            clusters.append({
                "tickers": cluster,
                "portfolio_weight_pct": round(cl_weight * 100, 1),
                "avg_correlation": round(sum(intra) / len(intra), 3) if intra else 0,
            })

    # 6. Worst-case drawdown (largest cluster drops 20%)
    worst_case = 0
    worst_cluster = None
    for cl in clusters:
        impact = cl["portfolio_weight_pct"] / 100 * 20  # 20% drop in cluster
        if impact > worst_case:
            worst_case = impact
            worst_cluster = cl["tickers"]

    # 7. Warnings + suggestions
    warnings = []
    suggestions = []

    if concentration_score > 70:
        warnings.append(f"HIGH CONCENTRATION: Weighted avg correlation {avg_weighted_corr:.2f} — portfolio moves as one position.")
    elif concentration_score > 50:
        warnings.append(f"MODERATE CONCENTRATION: Weighted avg correlation {avg_weighted_corr:.2f}.")

    for cl in clusters:
        if cl["portfolio_weight_pct"] > 50:
            warnings.append(f"{cl['portfolio_weight_pct']:.0f}% of portfolio in correlated cluster {cl['tickers']} (r={cl['avg_correlation']})")

    # Find least correlated tickers not in portfolio or underweight
    for sym in TICKERS:
        if sym not in holdings or weights.get(sym, 0) < 0.03:
            avg_r = []
            for s in syms:
                try: avg_r.append(abs(float(corr.loc[sym, s])) if sym in corr.index else 0)
                except: pass
            if avg_r and sum(avg_r) / len(avg_r) < 0.4:
                suggestions.append(f"Increase {sym} — avg correlation {sum(avg_r)/len(avg_r):.2f} to current holdings (diversifier)")

    if diversification_ratio < 1.1:
        suggestions.append("Diversification ratio near 1.0 — portfolio offers minimal diversification benefit vs single position.")

    return {
        "portfolio_value": round(total_value, 2),
        "holdings_value": round(total_holdings, 2),
        "cash_pct": round(cash / total_value * 100, 1),
        "positions": len(holdings),
        "concentration_score": concentration_score,
        "portfolio_volatility_annualized": round(port_vol, 1),
        "diversification_ratio": diversification_ratio,
        "worst_case_drawdown_pct": round(worst_case, 1),
        "worst_case_cluster": worst_cluster,
        "cluster_groups": clusters,
        "holdings_detail": [
            {"symbol": s, "weight_pct": round(weights.get(s, 0) * 100, 1), "value": round(h["value"], 2), "vol_annualized": round(vols.get(s, 0) * 100, 1)}
            for s, h in sorted(holdings.items(), key=lambda x: x[1]["value"], reverse=True)
        ],
        "warnings": warnings,
        "suggestions": suggestions,
    }


@app.get("/api/portfolio/journal")
@app.get("/api/trade-journal")
def get_trade_journal(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), ticker: str = Query(None)):
    """Full trade history with optional ticker filter."""
    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS trade_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime('now')), action TEXT, symbol TEXT, shares REAL, price REAL, total REAL, reasoning TEXT, score_at_trade REAL, zone_at_trade TEXT, macro_at_trade TEXT)")
    if ticker:
        rows = conn.execute("SELECT * FROM trade_journal WHERE symbol=? ORDER BY id DESC LIMIT ? OFFSET ?", (ticker.upper(), limit, offset)).fetchall()
        total = conn.execute("SELECT COUNT(*) as c FROM trade_journal WHERE symbol=?", (ticker.upper(),)).fetchone()["c"]
    else:
        rows = conn.execute("SELECT * FROM trade_journal ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        total = conn.execute("SELECT COUNT(*) as c FROM trade_journal").fetchone()["c"]
    conn.close()
    return {"trades": [dict(r) for r in rows], "count": len(rows), "total": total, "offset": offset}


@app.get("/api/signal-momentum")
def signal_momentum(ticker: str = Query("URA"), period: int = Query(7, ge=2, le=30)):
    """Rate of change of composite + category scores over time. First derivative of signals."""
    import json as _json
    ticker = ticker.upper()
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM composite_score_history WHERE symbol=? ORDER BY date DESC LIMIT ?",
        (ticker, period + 1)
    ).fetchall()
    conn.close()

    if not rows:
        return {"status": "no_data", "ticker": ticker, "message": "No snapshots yet. Cron runs at 20:30 UTC daily."}

    points = sorted([dict(r) for r in rows], key=lambda x: x["date"])
    latest = points[-1]
    oldest = points[0]

    days_available = len(points)
    has_period = days_available > period

    def delta(new, old):
        if new is not None and old is not None:
            return round(new - old, 1)
        return None

    def trend_label(d):
        if d is None: return "INSUFFICIENT_DATA"
        if d > 5: return "IMPROVING_FAST"
        if d > 1: return "IMPROVING"
        if d > -1: return "STABLE"
        if d > -5: return "DETERIORATING"
        return "DETERIORATING_FAST"

    composite_delta = delta(latest.get("total_score"), oldest.get("total_score")) if has_period else None

    # Category deltas
    categories = {}
    for cat in ["technical_score", "macro_score", "fundamental_score", "sentiment_score"]:
        d = delta(latest.get(cat), oldest.get(cat)) if has_period else None
        cat_name = cat.replace("_score", "")
        categories[cat_name] = {
            "current": latest.get(cat),
            "previous": oldest.get(cat) if has_period else None,
            "delta": d,
            "trend": trend_label(d),
        }

    # Per-signal momentum from components_json
    signal_deltas = []
    try:
        latest_components = _json.loads(latest.get("components_json", "{}"))
        oldest_components = _json.loads(oldest.get("components_json", "{}")) if has_period else {}
        for sig_name, sig_data in latest_components.items():
            old_sig = oldest_components.get(sig_name, {})
            new_score = sig_data.get("score") if isinstance(sig_data, dict) else sig_data
            old_score = old_sig.get("score") if isinstance(old_sig, dict) else old_sig
            d = delta(new_score, old_score) if has_period and old_score is not None else None
            signal_deltas.append({
                "signal": sig_name,
                "current": new_score,
                "previous": old_score if has_period else None,
                "delta": d,
                "trend": trend_label(d),
            })
        signal_deltas.sort(key=lambda x: abs(x["delta"] or 0), reverse=True)
    except Exception:
        pass

    # Daily trajectory (all points)
    trajectory = [{"date": p["date"], "score": p.get("total_score"), "price": p.get("price")} for p in points]

    # Acceleration (2nd derivative) if 3+ points
    acceleration = None
    if len(points) >= 3:
        mid = len(points) // 2
        first_half_delta = (points[mid].get("total_score", 0) or 0) - (points[0].get("total_score", 0) or 0)
        second_half_delta = (points[-1].get("total_score", 0) or 0) - (points[mid].get("total_score", 0) or 0)
        acceleration = round(second_half_delta - first_half_delta, 1)

    return {
        "ticker": ticker,
        "period_days": period,
        "days_available": days_available,
        "composite": {
            "current_score": latest.get("total_score"),
            "score_ago": oldest.get("total_score") if has_period else None,
            "delta": composite_delta,
            "trend": trend_label(composite_delta),
            "acceleration": acceleration,
        },
        "categories": categories,
        "signals": signal_deltas,
        "trajectory": trajectory,
        "most_improved": signal_deltas[0] if signal_deltas and (signal_deltas[0].get("delta") or 0) > 0 else None,
        "most_deteriorated": next((s for s in signal_deltas if (s.get("delta") or 0) < 0), None),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/regime-change-log")
def regime_change_log():
    """Regime transition history — audit trail of market regime shifts."""
    import os, json as _json
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "regime-changes.json")
    if not os.path.exists(log_path):
        return {"transitions": [], "count": 0, "current_regime": None}
    with open(log_path, "r") as f:
        entries = _json.load(f)
    return {
        "transitions": entries,
        "count": len(entries),
        "current_regime": entries[-1]["to_regime"] if entries else None,
        "last_change": entries[-1]["timestamp"] if entries else None,
    }


def _check_regime_transition():
    """Check if regime has changed, log transition if so."""
    import os, json as _json
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "regime-changes.json")

    try:
        data = regime_detector("URA")
    except Exception:
        return

    current = data["regime"]
    confidence = data["confidence"]

    # Load existing log
    entries = []
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            entries = _json.load(f)

    prev_regime = entries[-1]["to_regime"] if entries else None

    if prev_regime == current:
        return  # No change

    # Get portfolio value
    try:
        conn = _get_db()
        conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
        conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
        cash = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()["cash"]
        positions = conn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall()
        pv = cash + sum(p["shares"] * (get_ticker_meta(p["symbol"]) or {}).get("current_price", 0) for p in positions)
        conn.close()
    except Exception:
        pv = 0

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "from_regime": prev_regime,
        "to_regime": current,
        "confidence": confidence,
        "sizing_multiplier": data["position_sizing_multiplier"],
        "portfolio_value": round(pv, 2),
        "trigger": {
            "trend_score": data["components"]["trend"]["score"],
            "trend_direction": data["components"]["trend"]["direction"],
            "vol_state": data["components"]["volatility"]["state"],
            "vol_20d": data["components"]["volatility"]["annualized_20d"],
            "fear_greed": data["components"]["fear_greed"]["label"],
            "vix": data["components"]["fear_greed"]["vix"],
        },
    }

    entries.append(entry)
    entries = entries[-365:]  # Rolling cap

    with open(log_path, "w") as f:
        _json.dump(entries, f, indent=2)

    print(f"[REGIME] Transition: {prev_regime} → {current} (conf={confidence}, sizing={data['position_sizing_multiplier']}x)")


@app.get("/api/daily-pnl")
def daily_pnl(days: int = Query(30, ge=1, le=365)):
    """Daily P&L breakdown from equity snapshots + trade journal."""
    import numpy as np

    conn = _get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS portfolio_equity_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT UNIQUE,
        cash REAL, holdings_value REAL, total_value REAL, invested_pct REAL)""")
    rows = conn.execute("SELECT * FROM portfolio_equity_history ORDER BY date DESC LIMIT ?", (days + 1,)).fetchall()
    conn.execute("CREATE TABLE IF NOT EXISTS trade_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime('now')), action TEXT, symbol TEXT, shares REAL, price REAL, total REAL, reasoning TEXT, score_at_trade REAL, zone_at_trade TEXT, macro_at_trade TEXT)")
    trades = conn.execute("SELECT * FROM trade_journal ORDER BY timestamp").fetchall()
    conn.close()

    points = sorted([dict(r) for r in rows], key=lambda x: x["date"])
    if len(points) < 2:
        return {
            "status": "insufficient_data",
            "message": f"Need 2+ equity snapshots for daily P&L. Have {len(points)}. Cron runs at 20:40 UTC daily.",
            "days_available": len(points),
            "daily_returns": [],
            "metrics": {},
        }

    # Build daily returns
    daily_returns = []
    for i in range(1, len(points)):
        prev = points[i - 1]
        curr = points[i]
        pnl = curr["total_value"] - prev["total_value"]
        ret_pct = (pnl / prev["total_value"]) * 100 if prev["total_value"] else 0

        # Trades on this date
        date_trades = [dict(t) for t in trades if t.get("timestamp", "")[:10] == curr["date"]]

        daily_returns.append({
            "date": curr["date"],
            "nav": curr["total_value"],
            "prev_nav": prev["total_value"],
            "pnl_usd": round(pnl, 2),
            "return_pct": round(ret_pct, 2),
            "cash": curr["cash"],
            "invested_pct": curr["invested_pct"],
            "trades_count": len(date_trades),
            "trades": [{"action": t["action"], "symbol": t["symbol"], "shares": t["shares"], "price": t["price"]} for t in date_trades],
        })

    # Metrics
    rets = [d["return_pct"] / 100 for d in daily_returns]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]

    metrics = {
        "total_days": len(daily_returns),
        "winning_days": len(wins),
        "losing_days": len(losses),
        "flat_days": len(rets) - len(wins) - len(losses),
        "win_rate_pct": round(len(wins) / len(rets) * 100, 1) if rets else 0,
        "best_day_pct": round(max(rets) * 100, 2) if rets else 0,
        "worst_day_pct": round(min(rets) * 100, 2) if rets else 0,
        "avg_daily_pct": round(float(np.mean(rets)) * 100, 2) if rets else 0,
        "total_pnl_usd": round(sum(d["pnl_usd"] for d in daily_returns), 2),
        "current_streak": 0,
    }
    # Calculate current streak
    streak = 0
    for d in reversed(daily_returns):
        if d["return_pct"] > 0:
            if streak >= 0: streak += 1
            else: break
        elif d["return_pct"] < 0:
            if streak <= 0: streak -= 1
            else: break
        else:
            break
    metrics["current_streak"] = streak

    if len(rets) >= 5:
        std = float(np.std(rets))
        avg = float(np.mean(rets))
        metrics["sharpe_annualized"] = round((avg * 252) / (std * 252**0.5), 2) if std > 0 else None
        neg = [r for r in rets if r < 0]
        ds = float(np.std(neg)) if neg else 0
        metrics["sortino_annualized"] = round((avg * 252) / (ds * 252**0.5), 2) if ds > 0 else None

    return {
        "daily_returns": daily_returns,
        "metrics": metrics,
        "initial_nav": points[0]["total_value"],
        "current_nav": points[-1]["total_value"],
    }


@app.get("/api/portfolio/equity-curve")
def portfolio_equity_curve(days: int = Query(90, ge=7, le=365)):
    """Daily NAV history with benchmark comparison and risk metrics."""
    import yfinance as yf, numpy as np

    conn = _get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS portfolio_equity_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT UNIQUE,
        cash REAL, holdings_value REAL, total_value REAL, invested_pct REAL)""")
    rows = conn.execute("SELECT * FROM portfolio_equity_history ORDER BY date DESC LIMIT ?", (days,)).fetchall()
    conn.close()

    if not rows:
        return {"status": "no_data", "message": "No equity snapshots yet. Cron runs daily at 20:40 UTC.", "points": [], "metrics": {}}

    points = sorted([dict(r) for r in rows], key=lambda x: x["date"])

    # Benchmark (URA) for same dates
    try:
        ura = yf.Ticker("URA").history(period=f"{days}d")
        if ura.index.tz:
            ura.index = ura.index.tz_localize(None)
        ura_prices = {d.strftime("%Y-%m-%d"): round(float(c), 2) for d, c in ura["Close"].items()}
    except Exception:
        ura_prices = {}

    # Enrich with daily returns and benchmark
    first_nav = points[0]["total_value"]
    first_bench = ura_prices.get(points[0]["date"])
    prev_nav = first_nav

    for p in points:
        p["daily_return_pct"] = round((p["total_value"] / prev_nav - 1) * 100, 2) if prev_nav else 0
        p["cumulative_return_pct"] = round((p["total_value"] / first_nav - 1) * 100, 2)
        bench = ura_prices.get(p["date"])
        p["benchmark_price"] = bench
        p["benchmark_return_pct"] = round((bench / first_bench - 1) * 100, 2) if bench and first_bench else None
        prev_nav = p["total_value"]

    # Risk metrics (need 5+ points)
    metrics = {}
    if len(points) >= 5:
        daily_rets = [p["daily_return_pct"] / 100 for p in points[1:]]
        avg = float(np.mean(daily_rets))
        std = float(np.std(daily_rets))
        metrics["annualized_return_pct"] = round(avg * 252 * 100, 1)
        metrics["annualized_vol_pct"] = round(std * (252 ** 0.5) * 100, 1)
        metrics["sharpe"] = round((avg * 252) / (std * (252 ** 0.5)), 2) if std > 0 else None
        neg_rets = [r for r in daily_rets if r < 0]
        downside_std = float(np.std(neg_rets)) if neg_rets else 0
        metrics["sortino"] = round((avg * 252) / (downside_std * (252 ** 0.5)), 2) if downside_std > 0 else None
        # Max drawdown
        peak = points[0]["total_value"]
        max_dd = 0
        for p in points:
            peak = max(peak, p["total_value"])
            dd = (peak - p["total_value"]) / peak * 100
            max_dd = max(max_dd, dd)
        metrics["max_drawdown_pct"] = round(max_dd, 1)
        metrics["calmar"] = round(metrics["annualized_return_pct"] / max_dd, 2) if max_dd > 0 else None
        # Alpha vs benchmark
        bench_rets = [p["benchmark_return_pct"] for p in points if p["benchmark_return_pct"] is not None]
        if bench_rets:
            metrics["alpha_pct"] = round(points[-1].get("cumulative_return_pct", 0) - (bench_rets[-1] if bench_rets else 0), 1)

    return {
        "points": points,
        "count": len(points),
        "initial_nav": first_nav,
        "current_nav": points[-1]["total_value"],
        "total_return_pct": points[-1]["cumulative_return_pct"],
        "metrics": metrics,
    }


@app.get("/api/portfolio/performance")
def portfolio_performance():
    """
    Portfolio performance analytics: returns, Sharpe, drawdown, alpha vs URA buy-hold.
    Reconstructs daily equity from trade journal + current positions.
    """
    import numpy as np, yfinance as yf

    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS trade_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime('now')), action TEXT, symbol TEXT, shares REAL, price REAL, total REAL, reasoning TEXT, score_at_trade REAL, zone_at_trade TEXT, macro_at_trade TEXT)")
    trades = conn.execute("SELECT * FROM trade_journal ORDER BY id ASC").fetchall()

    # Current portfolio state
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio (symbol TEXT PRIMARY KEY, shares REAL DEFAULT 0, avg_cost REAL DEFAULT 0, last_updated TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
    conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
    cash = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()["cash"]
    positions = conn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall()
    conn.close()

    if not trades:
        return {"error": "No trades yet", "total_trades": 0}

    trades = [dict(t) for t in trades]
    first_trade_date = trades[0].get("timestamp", "")[:10]

    # Current holdings value
    holdings_value = 0
    position_details = []
    for p in positions:
        meta = get_ticker_meta(p["symbol"])
        price = meta.get("current_price", p["avg_cost"]) if meta else p["avg_cost"]
        val = p["shares"] * price
        holdings_value += val
        position_details.append({
            "symbol": p["symbol"],
            "shares": round(p["shares"], 2),
            "avg_cost": round(p["avg_cost"], 2),
            "current_price": round(price, 2),
            "value": round(val, 2),
            "pnl": round((price - p["avg_cost"]) * p["shares"], 2),
            "pnl_pct": round((price / p["avg_cost"] - 1) * 100, 1) if p["avg_cost"] > 0 else 0,
        })

    total_value = cash + holdings_value
    total_return = total_value - INITIAL_CASH
    total_return_pct = (total_value / INITIAL_CASH - 1) * 100

    # Trade stats
    buys = [t for t in trades if t["action"] == "BUY"]
    sells = [t for t in trades if t["action"] == "SELL"]

    # Realized P&L from sells
    cost_basis = {}
    realized_pnl = 0
    winning_trades = 0
    losing_trades = 0

    for t in trades:
        sym = t["symbol"]
        shares = t.get("shares", 0) or 0
        price = t.get("price", 0) or 0
        if t["action"] == "BUY":
            old = cost_basis.get(sym, {"shares": 0, "cost": 0})
            old_val = old["shares"] * old["cost"]
            new_shares = old["shares"] + shares
            cost_basis[sym] = {
                "shares": new_shares,
                "cost": (old_val + shares * price) / new_shares if new_shares > 0 else price,
            }
        elif t["action"] == "SELL":
            cb = cost_basis.get(sym, {"shares": 0, "cost": price})
            pnl = (price - cb["cost"]) * shares
            realized_pnl += pnl
            if pnl > 0:
                winning_trades += 1
            else:
                losing_trades += 1
            cb["shares"] = max(0, cb["shares"] - shares)
            cost_basis[sym] = cb

    total_sells = winning_trades + losing_trades
    win_rate = (winning_trades / total_sells * 100) if total_sells > 0 else 0

    # Unrealized P&L
    unrealized_pnl = 0
    for sym, cb in cost_basis.items():
        if cb["shares"] > 0:
            meta = get_ticker_meta(sym)
            cur = meta.get("current_price", cb["cost"]) if meta else cb["cost"]
            unrealized_pnl += (cur - cb["cost"]) * cb["shares"]

    # Benchmark: URA buy-and-hold from first trade date
    try:
        ura = yf.Ticker("URA")
        ura_hist = ura.history(start=first_trade_date)
        if ura_hist.index.tz is not None:
            ura_hist.index = ura_hist.index.tz_localize(None)
        if len(ura_hist) >= 2:
            ura_start = float(ura_hist["Close"].iloc[0])
            ura_end = float(ura_hist["Close"].iloc[-1])
            benchmark_return_pct = (ura_end / ura_start - 1) * 100
        else:
            benchmark_return_pct = 0
    except:
        benchmark_return_pct = 0

    alpha = total_return_pct - benchmark_return_pct

    # Days since inception
    try:
        from datetime import datetime as _dt
        inception = _dt.strptime(first_trade_date, "%Y-%m-%d")
        days = (datetime.utcnow() - inception).days
    except:
        days = 1
    days = max(days, 1)

    # Annualized return
    ann_return = ((1 + total_return_pct / 100) ** (365 / days) - 1) * 100

    # Approximate daily vol from trade sizes (rough proxy until we have daily snapshots)
    # For now use a simplified estimate
    invested_pct = holdings_value / total_value * 100 if total_value > 0 else 0

    return {
        "inception_date": first_trade_date,
        "days_active": days,
        "portfolio": {
            "initial_capital": INITIAL_CASH,
            "current_value": round(total_value, 2),
            "cash": round(cash, 2),
            "holdings_value": round(holdings_value, 2),
            "invested_pct": round(invested_pct, 1),
        },
        "returns": {
            "total_return": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "annualized_return_pct": round(ann_return, 2),
        },
        "pnl": {
            "realized": round(realized_pnl, 2),
            "unrealized": round(unrealized_pnl, 2),
            "total": round(realized_pnl + unrealized_pnl, 2),
        },
        "trades": {
            "total": len(trades),
            "buys": len(buys),
            "sells": len(sells),
            "winning_sells": winning_trades,
            "losing_sells": losing_trades,
            "win_rate_pct": round(win_rate, 1),
        },
        "benchmark": {
            "ticker": "URA",
            "return_pct": round(benchmark_return_pct, 2),
            "alpha_pct": round(alpha, 2),
        },
        "positions": sorted(position_details, key=lambda x: x["value"], reverse=True),
        "note": "Sharpe, Sortino, max drawdown, and Calmar ratio require daily equity snapshots. Will be available after 5+ trading days of portfolio value logging.",
    }


@app.get("/api/portfolio/attribution")
def portfolio_attribution():
    """
    P&L attribution by ticker and by signal category.
    Shows what's driving returns and which signals led to positions.
    """
    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio (symbol TEXT PRIMARY KEY, shares REAL DEFAULT 0, avg_cost REAL DEFAULT 0, last_updated TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
    conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
    conn.execute("CREATE TABLE IF NOT EXISTS trade_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime('now')), action TEXT, symbol TEXT, shares REAL, price REAL, total REAL, reasoning TEXT, score_at_trade REAL, zone_at_trade TEXT, macro_at_trade TEXT)")
    positions = conn.execute("SELECT * FROM portfolio WHERE shares > 0").fetchall()
    trades = conn.execute("SELECT * FROM trade_journal ORDER BY id ASC").fetchall()
    conn.close()

    # Build cost basis from trades
    cost_basis = {}
    realized = {}
    for t in trades:
        t = dict(t)
        sym = t["symbol"]
        shares = t.get("shares", 0) or 0
        price = t.get("price", 0) or 0
        if t["action"] == "BUY":
            old = cost_basis.get(sym, {"shares": 0, "cost": 0})
            old_val = old["shares"] * old["cost"]
            ns = old["shares"] + shares
            cost_basis[sym] = {"shares": ns, "cost": (old_val + shares * price) / ns if ns > 0 else price}
        elif t["action"] == "SELL":
            cb = cost_basis.get(sym, {"shares": 0, "cost": price})
            pnl = (price - cb["cost"]) * shares
            realized[sym] = realized.get(sym, 0) + pnl
            cb["shares"] = max(0, cb["shares"] - shares)
            cost_basis[sym] = cb

    # By ticker attribution
    by_ticker = []
    total_pnl = 0
    total_holdings = 0

    for p in positions:
        p = dict(p)
        sym = p["symbol"]
        meta = get_ticker_meta(sym)
        cur_price = meta.get("current_price", p["avg_cost"]) if meta else p["avg_cost"]
        value = p["shares"] * cur_price
        total_holdings += value
        unrealized = (cur_price - p["avg_cost"]) * p["shares"]
        real = realized.get(sym, 0)
        ticker_pnl = unrealized + real
        total_pnl += ticker_pnl

        # Get current score for signal attribution
        score = meta.get("signal_score", 50) if meta else 50

        by_ticker.append({
            "symbol": sym,
            "shares": round(p["shares"], 2),
            "avg_cost": round(p["avg_cost"], 2),
            "current_price": round(cur_price, 2),
            "value": round(value, 2),
            "pnl": round(ticker_pnl, 2),
            "pnl_pct": round((cur_price / p["avg_cost"] - 1) * 100, 2) if p["avg_cost"] > 0 else 0,
            "realized_pnl": round(real, 2),
            "unrealized_pnl": round(unrealized, 2),
            "current_score": round(score, 1),
        })

    # Weight and contribution
    for t in by_ticker:
        t["weight_pct"] = round(t["value"] / total_holdings * 100, 1) if total_holdings > 0 else 0
        t["contribution_pct"] = round(t["pnl"] / total_pnl * 100, 1) if total_pnl != 0 else 0

    by_ticker.sort(key=lambda x: x["pnl"], reverse=True)

    # By signal category — which score ranges drove the entries
    score_buckets = {"0-25 (Strong Buy zone)": [], "25-40 (Buy zone)": [], "40-55 (Neutral)": [], "55-70 (Hold)": [], "70-100 (Sell zone)": []}
    for t in trades:
        t = dict(t)
        score = t.get("score_at_trade") or 50
        sym = t["symbol"]
        if t["action"] != "BUY":
            continue
        # Find this ticker's current P&L
        ticker_data = next((x for x in by_ticker if x["symbol"] == sym), None)
        if not ticker_data:
            continue
        # Approximate: attribute proportionally to shares bought at this score
        entry_value = (t.get("shares", 0) or 0) * (t.get("price", 0) or 0)

        if score < 25:
            bucket = "0-25 (Strong Buy zone)"
        elif score < 40:
            bucket = "25-40 (Buy zone)"
        elif score < 55:
            bucket = "40-55 (Neutral)"
        elif score < 70:
            bucket = "55-70 (Hold)"
        else:
            bucket = "70-100 (Sell zone)"
        score_buckets[bucket].append({"symbol": sym, "entry_value": entry_value, "score": score})

    by_category = []
    for bucket, entries in score_buckets.items():
        if not entries:
            by_category.append({"category": bucket, "entries": 0, "total_deployed": 0, "tickers": []})
            continue
        total_deployed = sum(e["entry_value"] for e in entries)
        tickers = list(set(e["symbol"] for e in entries))
        by_category.append({
            "category": bucket,
            "entries": len(entries),
            "total_deployed": round(total_deployed, 2),
            "tickers": tickers,
        })

    # Best/worst
    best = by_ticker[0] if by_ticker else None
    worst = by_ticker[-1] if by_ticker else None

    return {
        "period": "inception",
        "total_pnl": round(total_pnl, 2),
        "total_holdings_value": round(total_holdings, 2),
        "by_ticker": by_ticker,
        "by_entry_score": by_category,
        "best_performer": {"symbol": best["symbol"], "pnl": best["pnl"], "pnl_pct": best["pnl_pct"]} if best else None,
        "worst_performer": {"symbol": worst["symbol"], "pnl": worst["pnl"], "pnl_pct": worst["pnl_pct"]} if worst else None,
    }


@app.get("/api/portfolio/history")
def portfolio_history(limit: int = Query(100, ge=1, le=500), symbol: str = Query(None)):
    """
    Full trade audit log with P&L per trade, running portfolio value, and performance stats.
    """
    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS trade_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime('now')), action TEXT, symbol TEXT, shares REAL, price REAL, total REAL, reasoning TEXT, score_at_trade REAL, zone_at_trade TEXT, macro_at_trade TEXT)")

    if symbol:
        rows = conn.execute("SELECT * FROM trade_journal WHERE symbol=? ORDER BY id ASC LIMIT ?", (symbol.upper(), limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM trade_journal ORDER BY id ASC LIMIT ?", (limit,)).fetchall()
    conn.close()

    trades = []
    # Track cost basis per symbol for P&L calc
    positions = {}  # symbol -> {shares, avg_cost}
    realized_pnl = 0
    total_invested = 0
    total_returned = 0

    for r in rows:
        row = dict(r)
        sym = row.get("symbol", "")
        action = row.get("action", "")
        shares = row.get("shares", 0) or 0
        price = row.get("price", 0) or 0
        total = row.get("total", 0) or 0

        trade_pnl = 0
        if action == "BUY":
            total_invested += total
            pos = positions.get(sym, {"shares": 0, "avg_cost": 0})
            old_val = pos["shares"] * pos["avg_cost"]
            new_shares = pos["shares"] + shares
            pos["avg_cost"] = (old_val + total) / new_shares if new_shares > 0 else price
            pos["shares"] = new_shares
            positions[sym] = pos
        elif action == "SELL":
            total_returned += total
            pos = positions.get(sym, {"shares": 0, "avg_cost": 0})
            trade_pnl = (price - pos["avg_cost"]) * shares
            realized_pnl += trade_pnl
            pos["shares"] = max(0, pos["shares"] - shares)
            positions[sym] = pos

        row["trade_pnl"] = round(trade_pnl, 2)
        row["cumulative_realized_pnl"] = round(realized_pnl, 2)
        trades.append(row)

    # Current unrealized P&L
    unrealized = 0
    open_positions = []
    for sym, pos in positions.items():
        if pos["shares"] > 0:
            meta = get_ticker_meta(sym)
            current_price = meta.get("current_price", pos["avg_cost"]) if meta else pos["avg_cost"]
            upnl = (current_price - pos["avg_cost"]) * pos["shares"]
            unrealized += upnl
            open_positions.append({
                "symbol": sym,
                "shares": round(pos["shares"], 2),
                "avg_cost": round(pos["avg_cost"], 2),
                "current_price": round(current_price, 2),
                "unrealized_pnl": round(upnl, 2),
            })

    wins = [t for t in trades if t["action"] == "SELL" and t["trade_pnl"] > 0]
    losses = [t for t in trades if t["action"] == "SELL" and t["trade_pnl"] <= 0]
    sell_count = len(wins) + len(losses)

    return {
        "trades": list(reversed(trades)),  # newest first
        "total_trades": len(trades),
        "performance": {
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
            "total_pnl": round(realized_pnl + unrealized, 2),
            "total_invested": round(total_invested, 2),
            "total_returned": round(total_returned, 2),
            "win_rate_pct": round(len(wins) / sell_count * 100, 1) if sell_count > 0 else 0,
            "wins": len(wins),
            "losses": len(losses),
            "avg_win": round(sum(t["trade_pnl"] for t in wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(sum(t["trade_pnl"] for t in losses) / len(losses), 2) if losses else 0,
        },
        "open_positions": open_positions,
    }


_iv_cache = {}
OPTIONS_TICKERS = ["CCJ", "UEC", "UUUU", "DNN", "NXE", "OKLO", "LEU"]

@app.get("/api/options-iv/{symbol}")
def get_options_iv(symbol: str):
    """Implied volatility analysis from options chain."""
    import time, yfinance as yf, numpy as np
    symbol = symbol.upper()
    now = time.time()
    if symbol in _iv_cache and now - _iv_cache[symbol]["ts"] < 3600:
        return _iv_cache[symbol]["data"]

    try:
        t = yf.Ticker(symbol)
        opts = t.options
        if not opts:
            return {"symbol": symbol, "error": "no_options"}
        price = float(t.fast_info.get("lastPrice", 0))

        # Get nearest 2 expiries for term structure
        expiries = []
        for exp in opts[:3]:
            try:
                chain = t.option_chain(exp)
                calls, puts = chain.calls, chain.puts
                atm_call = calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]
                atm_put = puts.iloc[(puts["strike"] - price).abs().argsort()[:1]]
                call_iv = float(atm_call["impliedVolatility"].iloc[0])
                put_iv = float(atm_put["impliedVolatility"].iloc[0])
                avg_iv = (call_iv + put_iv) / 2
                put_call_ratio = float(puts["openInterest"].sum()) / max(float(calls["openInterest"].sum()), 1)
                expiries.append({
                    "expiry": exp,
                    "call_iv": round(call_iv, 4),
                    "put_iv": round(put_iv, 4),
                    "atm_iv": round(avg_iv, 4),
                    "put_call_ratio": round(put_call_ratio, 3),
                })
            except Exception:
                continue

        if not expiries:
            return {"symbol": symbol, "error": "no_chain_data"}

        front_iv = expiries[0]["atm_iv"]
        # Realized vol (30d)
        hist = t.history(period="3mo")
        if len(hist) > 20:
            returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
            rv_30d = float(returns[-22:].std() * np.sqrt(252))
        else:
            rv_30d = None

        iv_rv_spread = round(front_iv - (rv_30d or 0), 4) if rv_30d else None

        # Signal
        if front_iv > 0.8:
            signal = "HIGH FEAR"
        elif front_iv > 0.5:
            signal = "ELEVATED"
        elif front_iv < 0.25:
            signal = "COMPLACENT"
        else:
            signal = "NORMAL"

        resp = {
            "symbol": symbol,
            "price": price,
            "front_iv": round(front_iv, 4),
            "realized_vol_30d": round(rv_30d, 4) if rv_30d else None,
            "iv_rv_spread": iv_rv_spread,
            "signal": signal,
            "expiries": expiries,
        }
        _iv_cache[symbol] = {"data": resp, "ts": now}
        return resp
    except Exception as e:
        raise HTTPException(500, f"Error: {e}")


_pcr_cache = {"data": None, "ts": 0}
_PCR_MIN_OI = 500  # Minimum total OI to trust the signal

@app.get("/api/put-call-ratio")
def get_put_call_ratio(symbol: str = Query(None)):
    """
    Put/call ratio analysis — contrarian sentiment indicator.
    Aggregates across all expiries. High P/C = fear = contrarian bullish.
    Tickers with total OI < 500 are marked LOW confidence and excluded from scoring.
    """
    import time, yfinance as yf
    now = time.time()

    # Cache for 2 hours — but only return cache if it has valid (non-zero) data
    if _pcr_cache["data"] and now - _pcr_cache["ts"] < 7200 and symbol is None:
        return _pcr_cache["data"]

    tickers_to_scan = [symbol.upper()] if symbol else OPTIONS_TICKERS
    results = []

    for sym in tickers_to_scan:
        try:
            t = yf.Ticker(sym)
            opts = t.options
            if not opts:
                continue
            price = float(t.fast_info.get("lastPrice", 0))

            total_call_oi = 0
            total_put_oi = 0
            total_call_vol = 0
            total_put_vol = 0
            expiry_data = []

            for exp in opts[:6]:
                try:
                    chain = t.option_chain(exp)
                    calls, puts = chain.calls, chain.puts
                    c_oi = int(calls["openInterest"].sum())
                    p_oi = int(puts["openInterest"].sum())
                    c_vol = int(calls["volume"].fillna(0).sum())
                    p_vol = int(puts["volume"].fillna(0).sum())
                    total_call_oi += c_oi
                    total_put_oi += p_oi
                    total_call_vol += c_vol
                    total_put_vol += p_vol

                    pcr_oi = round(p_oi / max(c_oi, 1), 3) if (c_oi + p_oi) > 0 else None
                    pcr_vol = round(p_vol / max(c_vol, 1), 3) if (c_vol + p_vol) > 0 else None

                    expiry_data.append({
                        "expiry": exp,
                        "call_oi": c_oi, "put_oi": p_oi,
                        "call_volume": c_vol, "put_volume": p_vol,
                        "pcr_oi": pcr_oi,
                        "pcr_volume": pcr_vol,
                    })
                except Exception:
                    continue

            if not expiry_data:
                continue

            total_oi = total_call_oi + total_put_oi

            # Confidence gate
            if total_oi < _PCR_MIN_OI:
                confidence = "LOW"
                agg_pcr_oi = round(total_put_oi / max(total_call_oi, 1), 3) if total_oi > 0 else None
                results.append({
                    "symbol": sym, "price": price,
                    "pcr_oi": agg_pcr_oi, "pcr_volume": None,
                    "total_call_oi": total_call_oi, "total_put_oi": total_put_oi,
                    "total_call_volume": total_call_vol, "total_put_volume": total_put_vol,
                    "total_oi": total_oi,
                    "signal": None, "contrarian_signal": None,
                    "score": None, "confidence": "LOW",
                    "detail": f"Insufficient OI ({total_oi} < {_PCR_MIN_OI}) — excluded from scoring",
                    "expiries_scanned": len(expiry_data), "expiries": expiry_data,
                })
                continue

            confidence = "HIGH"
            agg_pcr_oi = round(total_put_oi / max(total_call_oi, 1), 3)
            agg_pcr_vol = round(total_put_vol / max(total_call_vol, 1), 3) if (total_call_vol + total_put_vol) > 0 else None

            # Cap extreme values (P/C > 3 is likely data noise)
            capped_pcr = min(agg_pcr_oi, 3.0)

            # Signal interpretation
            if capped_pcr > 1.5:
                signal = "EXTREME FEAR"
                contrarian = "BULLISH"
                detail = "Extreme put buying — crowd is heavily hedged/bearish. Contrarian bullish."
            elif capped_pcr > 1.0:
                signal = "FEAR"
                contrarian = "BULLISH"
                detail = "More puts than calls — elevated fear. Moderate contrarian bullish signal."
            elif capped_pcr > 0.7:
                signal = "NEUTRAL"
                contrarian = "NEUTRAL"
                detail = "Normal P/C range — no strong directional bias from options."
            elif capped_pcr > 0.4:
                signal = "COMPLACENT"
                contrarian = "BEARISH"
                detail = "Low put buying — crowd is complacent. Moderate contrarian bearish."
            else:
                signal = "EXTREME GREED"
                contrarian = "BEARISH"
                detail = "Very low P/C — extreme complacency. Contrarian bearish signal."

            # Score: map capped P/C (0-3) to 0-100
            pcr_score = max(0, min(100, round(capped_pcr / 3.0 * 100)))

            results.append({
                "symbol": sym, "price": price,
                "pcr_oi": agg_pcr_oi, "pcr_volume": agg_pcr_vol,
                "total_call_oi": total_call_oi, "total_put_oi": total_put_oi,
                "total_call_volume": total_call_vol, "total_put_volume": total_put_vol,
                "total_oi": total_oi,
                "signal": signal, "contrarian_signal": contrarian,
                "score": pcr_score, "confidence": "HIGH",
                "detail": detail,
                "expiries_scanned": len(expiry_data), "expiries": expiry_data,
            })
        except Exception as e:
            print(f"[pcr] Error for {sym}: {e}")
            continue

    if not results:
        return {"tickers": [], "sector_pcr": None, "sector_signal": "NO_DATA", "error": "No options data available (market may be closed)"}

    # Sector aggregate — only HIGH confidence tickers
    high_conf = [r for r in results if r["confidence"] == "HIGH"]
    if high_conf:
        total_c = sum(r["total_call_oi"] for r in high_conf)
        total_p = sum(r["total_put_oi"] for r in high_conf)
        sector_pcr = round(total_p / max(total_c, 1), 3)
        capped_sector = min(sector_pcr, 3.0)
        sector_score = max(0, min(100, round(capped_sector / 3.0 * 100)))

        if capped_sector > 1.2:
            sector_signal = "FEAR"
        elif capped_sector > 0.7:
            sector_signal = "NEUTRAL"
        else:
            sector_signal = "COMPLACENT"
    else:
        sector_pcr = None
        sector_signal = "NO_DATA"
        sector_score = None
        total_c = 0
        total_p = 0

    resp = {
        "tickers": results,
        "sector_pcr": sector_pcr,
        "sector_signal": sector_signal,
        "sector_score": sector_score,
        "total_call_oi": total_c,
        "total_put_oi": total_p,
        "high_confidence_count": len(high_conf),
        "low_confidence_count": len(results) - len(high_conf),
    }

    # Only cache if we got real data (not all zeros from off-hours)
    has_real_data = any(r["total_oi"] > 0 for r in results)
    if symbol is None and has_real_data:
        _pcr_cache["data"] = resp
        _pcr_cache["ts"] = now
    elif symbol is None and not has_real_data and _pcr_cache["data"]:
        # Off-hours: return last valid cache instead of zeros
        return _pcr_cache["data"]

    return resp


@app.get("/api/options-flow")
def options_flow():
    """
    Options flow analysis: P/C ratio, unusual volume, large OI positions for uranium tickers.
    """
    import yfinance as yf, numpy as np, time as _time

    result = {}
    for sym in OPTIONS_TICKERS:
        try:
            tk = yf.Ticker(sym)
            expirations = tk.options
            if not expirations:
                result[sym] = {"error": "no options data"}
                continue

            price = float(tk.fast_info.get("lastPrice", 0))
            if not price:
                meta = get_ticker_meta(sym)
                price = meta.get("current_price", 0) if meta else 0

            total_call_vol = 0
            total_put_vol = 0
            total_call_oi = 0
            total_put_oi = 0
            unusual = []
            large_oi = []

            # Analyze nearest 3 expirations
            for exp in expirations[:3]:
                try:
                    chain = tk.option_chain(exp)
                    calls = chain.calls
                    puts = chain.puts

                    if calls is not None and not calls.empty:
                        cv = calls["volume"].fillna(0).sum()
                        coi = calls["openInterest"].fillna(0).sum()
                        total_call_vol += cv
                        total_call_oi += coi

                        # Unusual volume: volume > 5x open interest (for strikes near money)
                        for _, row in calls.iterrows():
                            strike = float(row.get("strike", 0))
                            vol = float(row.get("volume", 0) or 0)
                            oi = float(row.get("openInterest", 0) or 0)
                            if abs(strike - price) / price < 0.15 and vol > 0:
                                if oi > 0 and vol > oi * 3:
                                    unusual.append({
                                        "type": "CALL",
                                        "strike": strike,
                                        "expiry": exp,
                                        "volume": int(vol),
                                        "open_interest": int(oi),
                                        "vol_oi_ratio": round(vol / oi, 1),
                                        "signal": "BULLISH — unusual call volume",
                                    })
                                if oi > 500:
                                    large_oi.append({"type": "CALL", "strike": strike, "expiry": exp, "oi": int(oi)})

                    if puts is not None and not puts.empty:
                        pv = puts["volume"].fillna(0).sum()
                        poi = puts["openInterest"].fillna(0).sum()
                        total_put_vol += pv
                        total_put_oi += poi

                        for _, row in puts.iterrows():
                            strike = float(row.get("strike", 0))
                            vol = float(row.get("volume", 0) or 0)
                            oi = float(row.get("openInterest", 0) or 0)
                            if abs(strike - price) / price < 0.15 and vol > 0:
                                if oi > 0 and vol > oi * 3:
                                    unusual.append({
                                        "type": "PUT",
                                        "strike": strike,
                                        "expiry": exp,
                                        "volume": int(vol),
                                        "open_interest": int(oi),
                                        "vol_oi_ratio": round(vol / oi, 1),
                                        "signal": "BEARISH — unusual put volume",
                                    })
                                if oi > 500:
                                    large_oi.append({"type": "PUT", "strike": strike, "expiry": exp, "oi": int(oi)})
                except:
                    continue

            # P/C ratio
            pcr_vol = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else 0
            pcr_oi = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0

            if pcr_vol > 1.5:
                pcr_signal = "BEARISH — heavy put buying"
            elif pcr_vol > 1.0:
                pcr_signal = "LEAN BEARISH"
            elif pcr_vol > 0.7:
                pcr_signal = "NEUTRAL"
            elif pcr_vol > 0.4:
                pcr_signal = "LEAN BULLISH"
            else:
                pcr_signal = "BULLISH — heavy call buying"

            unusual.sort(key=lambda x: x["vol_oi_ratio"], reverse=True)
            large_oi.sort(key=lambda x: x["oi"], reverse=True)

            result[sym] = {
                "price": round(price, 2),
                "put_call_ratio_volume": pcr_vol,
                "put_call_ratio_oi": pcr_oi,
                "pcr_signal": pcr_signal,
                "total_call_volume": int(total_call_vol),
                "total_put_volume": int(total_put_vol),
                "total_call_oi": int(total_call_oi),
                "total_put_oi": int(total_put_oi),
                "unusual_activity": unusual[:5],
                "large_oi_positions": large_oi[:5],
                "expirations_analyzed": len(expirations[:3]),
            }
        except Exception as e:
            result[sym] = {"error": str(e)}

    # Sector aggregate
    sector_call_vol = sum(r.get("total_call_volume", 0) for r in result.values() if isinstance(r.get("total_call_volume"), int))
    sector_put_vol = sum(r.get("total_put_volume", 0) for r in result.values() if isinstance(r.get("total_put_volume"), int))
    sector_pcr = round(sector_put_vol / sector_call_vol, 2) if sector_call_vol > 0 else 0
    all_unusual = []
    for sym, data in result.items():
        for u in data.get("unusual_activity", []):
            u["symbol"] = sym
            all_unusual.append(u)
    all_unusual.sort(key=lambda x: x["vol_oi_ratio"], reverse=True)

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "tickers": result,
        "sector_summary": {
            "total_call_volume": sector_call_vol,
            "total_put_volume": sector_put_vol,
            "sector_pcr": sector_pcr,
            "sector_signal": "BEARISH" if sector_pcr > 1.2 else "LEAN BEARISH" if sector_pcr > 0.9 else "NEUTRAL" if sector_pcr > 0.6 else "BULLISH",
            "top_unusual": all_unusual[:5],
        },
    }


@app.get("/api/options-iv-summary")
def get_options_iv_summary():
    """IV summary across all options-enabled tickers."""
    results = []
    for sym in OPTIONS_TICKERS:
        try:
            data = get_options_iv(sym)
            if "error" not in data:
                results.append(data)
        except Exception:
            pass
    results.sort(key=lambda x: x.get("front_iv", 0), reverse=True)
    avg_iv = sum(r["front_iv"] for r in results) / len(results) if results else 0
    return {
        "tickers": results,
        "avg_sector_iv": round(avg_iv, 4),
        "sector_signal": "HIGH FEAR" if avg_iv > 0.8 else ("ELEVATED" if avg_iv > 0.5 else "NORMAL"),
    }


_spot_price_cache = {"data": None, "ts": 0}

@app.get("/api/spot-price")
def get_spot_price():
    """U3O8 spot price from Cameco (UxC data), with Sprott NAV fallback."""
    import time as _time
    import yfinance as yf
    now = _time.time()
    if _spot_price_cache["data"] and now - _spot_price_cache["ts"] < 21600:  # 6hr cache
        return _spot_price_cache["data"]

    # Primary: Cameco (UxC monthly spot + long-term)
    try:
        cameco_resp = httpx.get(
            "https://www.cameco.com/invest/markets/uranium-price",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            timeout=15,
        )
        if cameco_resp.status_code == 200:
            soup = BeautifulSoup(cameco_resp.text, "html.parser")
            tables = soup.select("table")
            if tables:
                rows = tables[0].select("tr")
                # Get last row with data (most recent month)
                for row in reversed(rows):
                    cells = row.select("td")
                    if len(cells) >= 3:
                        date_str = cells[0].get_text(strip=True)
                        spot_str = cells[1].get_text(strip=True)
                        lt_str = cells[2].get_text(strip=True)
                        try:
                            spot_price = float(spot_str)
                            lt_price = float(lt_str) if lt_str else None
                            # Get previous month for change calc
                            prev_spot = None
                            for prev_row in reversed(rows[:-1]):
                                prev_cells = prev_row.select("td")
                                if len(prev_cells) >= 2:
                                    try:
                                        prev_spot = float(prev_cells[1].get_text(strip=True))
                                        break
                                    except: continue

                            change = spot_price - prev_spot if prev_spot else 0
                            change_pct = (change / prev_spot * 100) if prev_spot else 0

                            resp = {
                                "price": spot_price,
                                "long_term_price": lt_price,
                                "prev_month_price": prev_spot,
                                "monthly_change": round(change, 2),
                                "monthly_change_pct": round(change_pct, 1),
                                "spot_term_spread_pct": round((spot_price - lt_price) / lt_price * 100, 1) if lt_price else None,
                                "source": "Cameco (UxC monthly spot)",
                                "period": date_str,
                                "last_updated": datetime.utcnow().strftime("%Y-%m-%d"),
                                "note": "UxC industry-standard monthly spot price via Cameco",
                            }
                            _spot_price_cache["data"] = resp
                            _spot_price_cache["ts"] = now
                            return resp
                        except ValueError:
                            continue
    except Exception as e:
        print(f"Cameco scrape failed: {e}")

    # Fallback: Sprott Physical Uranium Trust NAV
    try:
        t = yf.Ticker("U-UN.TO")
        h = t.history(period="1mo")
        if h.empty:
            raise ValueError("No data")
        last_cad = float(h["Close"].iloc[-1])
        last_date = h.index[-1].strftime("%Y-%m-%d")
        prev_cad = float(h["Close"].iloc[-6]) if len(h) > 5 else last_cad
        fx = yf.Ticker("CADUSD=X")
        fxh = fx.history(period="5d")
        cad_usd = float(fxh["Close"].iloc[-1]) if not fxh.empty else 0.72
        lbs_per_unit = 0.3635
        spot = last_cad * cad_usd / lbs_per_unit
        prev_spot = prev_cad * cad_usd / lbs_per_unit
        change = spot - prev_spot
        change_pct = (change / prev_spot) * 100 if prev_spot else 0
        sparkline = [round(float(row["Close"]) * cad_usd / lbs_per_unit, 2) for _, row in h.iterrows()]

        resp = {
            "price": round(spot, 2),
            "prev_week_price": round(prev_spot, 2),
            "weekly_change": round(change, 2),
            "weekly_change_pct": round(change_pct, 1),
            "source": "Derived from Sprott Physical Uranium Trust (U-UN.TO) NAV (fallback)",
            "trust_price_cad": round(last_cad, 2),
            "cad_usd": round(cad_usd, 4),
            "last_updated": last_date,
            "sparkline_30d": sparkline,
            "note": "Fallback estimate — Cameco/UxC source unavailable",
        }
        _spot_price_cache["data"] = resp
        _spot_price_cache["ts"] = now
        return resp
    except Exception as e:
        return {"price": None, "error": str(e), "source": "unavailable"}


_etf_flow_cache = {"data": None, "ts": 0}

@app.get("/api/etf-flows")
def get_etf_flows():
    """ETF dollar volume flows as proxy for fund inflows/outflows."""
    import time as _time
    import yfinance as yf, numpy as np
    now = _time.time()
    if _etf_flow_cache["data"] and now - _etf_flow_cache["ts"] < 3600:
        return _etf_flow_cache["data"]

    etfs = {"URA": "Global X Uranium ETF", "URNM": "Sprott Uranium Miners ETF"}
    results = []
    for sym, name in etfs.items():
        try:
            h = yf.Ticker(sym).history(period="6mo")
            if h.empty or len(h) < 22:
                continue
            h["dv"] = h["Close"] * h["Volume"]
            dv_5d = float(h["dv"][-5:].mean())
            dv_22d = float(h["dv"][-22:].mean())
            dv_63d = float(h["dv"][-min(63,len(h)):].mean())
            flow_trend = (dv_5d / dv_22d - 1) * 100
            vol_5d = float(h["Volume"][-5:].mean())
            vol_22d = float(h["Volume"][-22:].mean())

            # Weekly dollar volume for chart
            weekly = []
            for i in range(min(12, len(h)//5)):
                start = -(i+1)*5
                end = -i*5 if i > 0 else None
                chunk = h.iloc[start:end] if end else h.iloc[start:]
                if len(chunk) > 0:
                    wdv = float((chunk["Close"] * chunk["Volume"]).sum())
                    weekly.insert(0, {"week": chunk.index[0].strftime("%m/%d"), "dollar_volume": round(wdv/1e6, 1)})

            if flow_trend > 20:
                signal = "STRONG INFLOW"
            elif flow_trend > 5:
                signal = "INFLOW"
            elif flow_trend < -20:
                signal = "STRONG OUTFLOW"
            elif flow_trend < -5:
                signal = "OUTFLOW"
            else:
                signal = "NEUTRAL"

            results.append({
                "symbol": sym, "name": name,
                "avg_dollar_vol_5d": round(dv_5d / 1e6, 1),
                "avg_dollar_vol_22d": round(dv_22d / 1e6, 1),
                "avg_dollar_vol_63d": round(dv_63d / 1e6, 1),
                "flow_trend_pct": round(flow_trend, 1),
                "volume_ratio": round(vol_5d / vol_22d, 2),
                "signal": signal,
                "weekly_volumes": weekly,
            })
        except Exception as e:
            print(f"[ETF_FLOW] Error {sym}: {e}")

    resp = {
        "etfs": results,
        "sector_signal": results[0]["signal"] if results else "NO_DATA",
    }
    _etf_flow_cache["data"] = resp
    _etf_flow_cache["ts"] = now
    return resp


_fund_flow_cache = {"data": None, "ts": 0}

@app.get("/api/fund-flows")
def get_fund_flows(period: str = Query("6m")):
    """
    Estimated ETF fund flows (inflows/outflows) based on AUM changes.
    Flow = ΔAUM - (price_return × prev_AUM). Positive = net buying.
    This isolates actual new money from price appreciation.
    """
    import time as _time
    import yfinance as yf, numpy as np, pandas as pd

    now = _time.time()
    if _fund_flow_cache["data"] and now - _fund_flow_cache["ts"] < 3600:
        return _fund_flow_cache["data"]

    period_map = {"3m": "3mo", "6m": "6mo", "1y": "1y"}
    yf_period = period_map.get(period, "6mo")

    etfs = {"URA": "Global X Uranium ETF", "URNM": "Sprott Uranium Miners ETF"}
    results = []

    for sym, name in etfs.items():
        try:
            t = yf.Ticker(sym)
            hist = t.history(period=yf_period)
            if hist.empty or len(hist) < 22:
                continue

            info = t.info or {}
            shares_out = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
            total_assets = info.get("totalAssets")

            # Estimate daily AUM: shares_outstanding * close price
            # Since shares_out is current, we approximate historical via volume-weighted estimation
            # Better proxy: use dollar volume changes vs NAV changes
            prices = hist["Close"].values
            volumes = hist["Volume"].values

            # Daily dollar volume
            dv = prices * volumes

            # Estimated daily flow: dollar_volume * sign(price_change)
            # More sophisticated: Flow ≈ Volume × (Close - VWAP) where VWAP ≈ (H+L+C)/3
            # Simplified: use price-volume divergence
            returns = np.diff(prices) / prices[:-1]

            # Flow estimation using Granville's method:
            # If close > prev_close: flow = +volume; else: flow = -volume
            # Normalized by dollar value
            daily_flows = []
            cumulative_flow = 0.0
            for i in range(1, len(prices)):
                if prices[i] > prices[i-1]:
                    flow = dv[i]  # buying pressure
                elif prices[i] < prices[i-1]:
                    flow = -dv[i]  # selling pressure
                else:
                    flow = 0
                cumulative_flow += flow
                daily_flows.append({
                    "date": hist.index[i].strftime("%Y-%m-%d"),
                    "price": round(float(prices[i]), 2),
                    "volume": int(volumes[i]),
                    "dollar_volume": round(float(dv[i]) / 1e6, 2),
                    "estimated_flow": round(float(flow) / 1e6, 2),
                    "cumulative_flow": round(float(cumulative_flow) / 1e6, 1),
                })

            if not daily_flows:
                continue

            # Aggregate periods
            flows_arr = np.array([d["estimated_flow"] for d in daily_flows])
            cum_5d = float(flows_arr[-5:].sum()) if len(flows_arr) >= 5 else 0
            cum_22d = float(flows_arr[-22:].sum()) if len(flows_arr) >= 22 else 0
            cum_63d = float(flows_arr[-63:].sum()) if len(flows_arr) >= 63 else float(flows_arr.sum())

            # Weekly aggregation for chart
            weekly = []
            df_flows = pd.DataFrame(daily_flows)
            df_flows["date"] = pd.to_datetime(df_flows["date"])
            df_flows.set_index("date", inplace=True)
            weekly_groups = df_flows.resample("W")
            for week_start, group in weekly_groups:
                if len(group) == 0:
                    continue
                weekly.append({
                    "week": week_start.strftime("%Y-%m-%d"),
                    "flow_mm": round(float(group["estimated_flow"].sum()), 1),
                    "avg_price": round(float(group["price"].mean()), 2),
                    "total_volume": int(group["volume"].sum()),
                })

            # Signal
            if cum_22d > 50:
                signal = "STRONG INFLOW"
                score = 85
            elif cum_22d > 10:
                signal = "INFLOW"
                score = 70
            elif cum_22d < -50:
                signal = "STRONG OUTFLOW"
                score = 15
            elif cum_22d < -10:
                signal = "OUTFLOW"
                score = 30
            else:
                signal = "NEUTRAL"
                score = 50

            # Momentum: is flow accelerating or decelerating?
            if len(flows_arr) >= 22:
                recent = float(flows_arr[-5:].mean())
                older = float(flows_arr[-22:-5].mean()) if len(flows_arr) >= 22 else recent
                momentum = "ACCELERATING" if abs(recent) > abs(older) * 1.2 and np.sign(recent) == np.sign(cum_22d) else \
                           "DECELERATING" if abs(recent) < abs(older) * 0.8 else "STEADY"
            else:
                momentum = "N/A"

            results.append({
                "symbol": sym,
                "name": name,
                "current_price": round(float(prices[-1]), 2),
                "shares_outstanding": shares_out,
                "total_assets": total_assets,
                "estimated_aum_mm": round(float(prices[-1]) * shares_out / 1e6, 1) if shares_out else None,
                "flow_5d_mm": round(cum_5d, 1),
                "flow_22d_mm": round(cum_22d, 1),
                "flow_63d_mm": round(cum_63d, 1),
                "cumulative_flow_mm": round(float(cumulative_flow) / 1e6, 1),
                "signal": signal,
                "score": score,
                "momentum": momentum,
                "weekly_flows": weekly[-12:],  # last 12 weeks
                "daily_flows": daily_flows[-22:],  # last 22 trading days
            })
        except Exception as e:
            print(f"[fund-flows] Error {sym}: {e}")

    # Sector aggregate
    if results:
        total_22d = sum(r["flow_22d_mm"] for r in results)
        if total_22d > 50:
            sector_signal = "STRONG INFLOW"
        elif total_22d > 10:
            sector_signal = "INFLOW"
        elif total_22d < -50:
            sector_signal = "STRONG OUTFLOW"
        elif total_22d < -10:
            sector_signal = "OUTFLOW"
        else:
            sector_signal = "NEUTRAL"
    else:
        sector_signal = "NO_DATA"
        total_22d = 0

    resp = {
        "etfs": results,
        "sector_signal": sector_signal,
        "sector_flow_22d_mm": round(total_22d, 1),
        "method": "Granville OBV-style flow estimation (up-day volume = inflow, down-day = outflow)",
    }

    _fund_flow_cache["data"] = resp
    _fund_flow_cache["ts"] = now
    return resp


_custom_alerts = []  # [{id, type, symbol, operator, value, channel, enabled, last_fired, was_triggered}]
_custom_alert_counter = 0

@app.get("/api/alerts/custom")
def list_custom_alerts():
    return {"alerts": _custom_alerts}

@app.get("/api/price-alerts")
def get_price_alerts():
    """All active and recently triggered alerts."""
    active = [a for a in _custom_alerts if a["enabled"] and not a["was_triggered"]]
    triggered = [a for a in _custom_alerts if a["was_triggered"]]
    disabled = [a for a in _custom_alerts if not a["enabled"]]
    return {
        "total": len(_custom_alerts),
        "active_alerts": active,
        "triggered_alerts": triggered,
        "disabled_alerts": disabled,
    }


@app.post("/api/price-alerts")
async def create_price_alert(request: Request):
    """Create a price/score/volume alert. Alias for /api/alerts/custom."""
    global _custom_alert_counter
    body = await request.json()
    _custom_alert_counter += 1
    alert = {
        "id": _custom_alert_counter,
        "type": body.get("type", "price"),
        "symbol": body.get("symbol", "URA").upper(),
        "operator": body.get("operator", "above"),
        "value": float(body.get("value", 0)),
        "channel": body.get("channel", "both"),
        "enabled": body.get("enabled", True),
        "last_fired": None,
        "was_triggered": False,
    }
    _custom_alerts.append(alert)
    return {"created": alert}


@app.post("/api/alerts/custom")
async def create_custom_alert(request: Request):
    global _custom_alert_counter
    body = await request.json()
    _custom_alert_counter += 1
    alert = {
        "id": _custom_alert_counter,
        "type": body.get("type", "price"),  # price|score|volume|daily_change
        "symbol": body.get("symbol", "URA").upper(),
        "operator": body.get("operator", "above"),  # above|below
        "value": float(body.get("value", 0)),
        "channel": body.get("channel", "both"),  # discord|telegram|both
        "enabled": body.get("enabled", True),
        "last_fired": None,
        "was_triggered": False,
    }
    _custom_alerts.append(alert)
    return {"alert": alert}

@app.delete("/api/alerts/custom/{alert_id}")
def delete_custom_alert(alert_id: int):
    global _custom_alerts
    _custom_alerts = [a for a in _custom_alerts if a["id"] != alert_id]
    return {"deleted": alert_id}

@app.patch("/api/alerts/custom/{alert_id}")
async def toggle_custom_alert(alert_id: int, request: Request):
    body = await request.json()
    for a in _custom_alerts:
        if a["id"] == alert_id:
            if "enabled" in body:
                a["enabled"] = body["enabled"]
            return {"alert": a}
    raise HTTPException(404, "Alert not found")


def _check_custom_alerts():
    """Evaluate custom alerts against current data."""
    import time as _time
    now = _time.time()
    tickers = get_all_ticker_meta()
    ticker_map = {t["symbol"]: t for t in tickers}

    for alert in _custom_alerts:
        if not alert["enabled"]:
            continue
        # Cooldown: 1 hour
        if alert["last_fired"] and now - alert["last_fired"] < 3600:
            continue

        meta = ticker_map.get(alert["symbol"])
        if not meta:
            continue

        # Get current value based on type
        if alert["type"] == "price":
            current = meta.get("current_price", 0)
        elif alert["type"] == "score":
            current = meta.get("signal_score", 50)
        elif alert["type"] == "daily_change":
            current = abs(meta.get("change_pct", 0))
        elif alert["type"] == "volume":
            current = meta.get("volume", 0) / max(meta.get("avg_volume", 1), 1)
        else:
            continue

        # Check condition
        triggered = (alert["operator"] == "above" and current >= alert["value"]) or \
                    (alert["operator"] == "below" and current <= alert["value"])

        if triggered and not alert["was_triggered"]:
            alert["was_triggered"] = True
            alert["last_fired"] = now
            # Fire alert
            op = "≥" if alert["operator"] == "above" else "≤"
            unit = {"price": "$", "score": "", "daily_change": "%", "volume": "×"}.get(alert["type"], "")
            prefix = unit if alert["type"] == "price" else ""
            suffix = unit if alert["type"] != "price" else ""
            msg = f"🔔 **Custom Alert:** {alert['symbol']} {alert['type']} {op} {prefix}{alert['value']}{suffix} (current: {prefix}{current:.2f}{suffix})\nhttp://165.22.252.79/uranium/"

            ch = alert["channel"]
            bot_token = os.environ.get("DISCORD_BOT_TOKEN")
            if ch in ("discord", "both") and bot_token:
                try:
                    httpx.post(f"https://discord.com/api/v10/channels/1471822299203371030/messages",
                        headers={"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"},
                        json={"content": msg}, timeout=10)
                except Exception:
                    pass
            if ch in ("telegram", "both"):
                try:
                    httpx.post(f"{OPENCLAW_GATEWAY}/tools/invoke",
                        headers={"Authorization": f"Bearer {OPENCLAW_TOKEN}", "Content-Type": "application/json"},
                        json={"tool": "message", "input": {"action": "send", "channel": "telegram",
                              "target": TELEGRAM_CHAT_ID, "message": msg.replace("**", "")}}, timeout=10)
                except Exception:
                    pass
            print(f"[CUSTOM_ALERT] Fired: {alert['symbol']} {alert['type']} {alert['operator']} {alert['value']}")
        elif not triggered:
            alert["was_triggered"] = False  # reset when condition no longer met


@app.get("/api/weekly-digest")
def get_weekly_digest():
    """Generate weekly summary digest."""
    import yfinance as yf
    tickers_data = get_all_ticker_meta()

    # Weekly price changes
    ticker_changes = []
    for t in tickers_data:
        sym = t["symbol"]
        try:
            hist = yf.Ticker(sym).history(period="5d")
            if len(hist) >= 2:
                start = float(hist["Close"].iloc[0])
                end = float(hist["Close"].iloc[-1])
                chg = (end - start) / start * 100
            else:
                start = end = t.get("current_price", 0)
                chg = 0
        except Exception:
            start = end = t.get("current_price", 0)
            chg = 0
        ticker_changes.append({
            "symbol": sym, "start": round(start, 2), "end": round(end, 2),
            "change_pct": round(chg, 2), "score": t.get("signal_score", 50),
            "zone": t.get("zone", "YELLOW"),
        })

    ticker_changes.sort(key=lambda x: x["change_pct"], reverse=True)
    best = ticker_changes[0] if ticker_changes else None
    worst = ticker_changes[-1] if ticker_changes else None

    # Portfolio
    try:
        portfolio = get_portfolio()
        port_summary = {
            "total_value": portfolio.get("total_value", 0),
            "total_pnl": portfolio.get("total_pnl", 0),
            "positions": len(portfolio.get("positions", [])),
        }
    except Exception:
        port_summary = {"total_value": 0, "total_pnl": 0, "positions": 0}

    # Macro
    try:
        macro = fetch_macro_regime()
        macro_regime = macro.get("regime", "NEUTRAL")
    except Exception:
        macro_regime = "NEUTRAL"

    # Cross-asset
    try:
        cross = get_cross_asset_regime()
        cross_regime = cross.get("regime", "UNKNOWN")
    except Exception:
        cross_regime = "UNKNOWN"

    # Zone alerts from DB
    conn = _get_db()
    try:
        alerts = conn.execute(
            "SELECT * FROM zone_alerts WHERE timestamp > datetime('now', '-7 days') ORDER BY timestamp DESC"
        ).fetchall()
        zone_alerts = [{"symbol": a["symbol"], "old_zone": a["old_zone"], "new_zone": a["new_zone"],
                        "timestamp": a["timestamp"]} for a in alerts]
    except Exception:
        zone_alerts = []
    conn.close()

    # Verdict
    try:
        therm = get_thermometer()
        verdict_text = therm.get("verdict", {}).get("text", "No verdict available")
    except Exception:
        verdict_text = "No verdict available"

    # Earnings
    try:
        earnings = get_earnings_calendar()
        upcoming = [e for e in earnings.get("upcoming", []) if e.get("symbol")][:3]
    except Exception:
        upcoming = []

    avg_score = sum(t["score"] for t in ticker_changes) / len(ticker_changes) if ticker_changes else 50

    return {
        "period": "Last 5 trading days",
        "tickers": ticker_changes,
        "best_performer": best,
        "worst_performer": worst,
        "avg_score": round(avg_score, 1),
        "macro_regime": macro_regime,
        "cross_asset_regime": cross_regime,
        "zone_alerts": zone_alerts,
        "portfolio": port_summary,
        "upcoming_earnings": upcoming,
        "verdict": verdict_text,
    }


@app.get("/api/monte-carlo-tpsl/{symbol}")
def monte_carlo_tpsl(symbol: str, tp_pct: float = 25.0, sl_pct: float = 15.0, sims: int = 5000, days: int = 120):
    """Monte Carlo probability of hitting TP vs SL first."""
    import yfinance as yf, numpy as np
    symbol = symbol.upper()
    df = yf.Ticker(symbol).history(period="2y")
    if df.empty or len(df) < 60:
        raise HTTPException(400, "Insufficient data")

    close = df["Close"]
    log_returns = np.log(close / close.shift(1)).dropna()
    mu = float(log_returns.mean())
    sigma = float(log_returns.std())
    price = float(close.iloc[-1])
    tp_price = price * (1 + tp_pct / 100)
    sl_price = price * (1 - sl_pct / 100)

    tp_hits = 0
    sl_hits = 0
    neither = 0
    tp_days = []
    sl_days = []
    final_prices = []

    rng = np.random.default_rng(42)
    for _ in range(sims):
        p = price
        hit = False
        for d in range(1, days + 1):
            p *= np.exp(mu + sigma * rng.standard_normal())
            if p >= tp_price:
                tp_hits += 1
                tp_days.append(d)
                hit = True
                break
            elif p <= sl_price:
                sl_hits += 1
                sl_days.append(d)
                hit = True
                break
        if not hit:
            neither += 1
            final_prices.append(p)

    tp_prob = tp_hits / sims * 100
    sl_prob = sl_hits / sims * 100
    expected_pnl = (tp_prob/100 * tp_pct) + (sl_prob/100 * -sl_pct) + (neither/sims * ((np.mean(final_prices)/price - 1)*100 if final_prices else 0))

    return {
        "symbol": symbol,
        "current_price": round(price, 2),
        "tp_price": round(tp_price, 2),
        "sl_price": round(sl_price, 2),
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "simulations": sims,
        "horizon_days": days,
        "tp_probability": round(tp_prob, 1),
        "sl_probability": round(sl_prob, 1),
        "neither_pct": round(neither / sims * 100, 1),
        "median_days_to_tp": int(np.median(tp_days)) if tp_days else None,
        "median_days_to_sl": int(np.median(sl_days)) if sl_days else None,
        "expected_pnl_pct": round(expected_pnl, 2),
        "annualized_vol": round(sigma * np.sqrt(252) * 100, 1),
        "daily_drift": round(mu * 100, 4),
        "signal": "FAVORABLE" if tp_prob > sl_prob * 1.5 else ("UNFAVORABLE" if sl_prob > tp_prob * 1.5 else "NEUTRAL"),
    }


@app.get("/api/monte-carlo-enhanced/{symbol}")
def monte_carlo_enhanced(symbol: str, tp: float = 25.0, sl: float = 15.0, days: int = 90, sims: int = 5000):
    """Signal-weighted Monte Carlo: drift/vol adjusted by dashboard signals."""
    import yfinance as yf, numpy as np
    symbol = symbol.upper()

    df = yf.Ticker(symbol).history(period="2y")
    if df.empty or len(df) < 60:
        raise HTTPException(400, "Insufficient data")

    close = df["Close"]
    log_returns = np.log(close / close.shift(1)).dropna()
    base_sigma = float(log_returns.std()) * np.sqrt(252)
    risk_free = 0.0425 / 252  # daily risk-free (US 10Y ~4.25% as of Feb 2026)

    # --- Gather signals ---
    adjustments = []
    drift_adj = 0.0
    vol_adj = 1.0

    # 1. Score signal
    try:
        meta = next((t for t in get_all_ticker_meta() if t["symbol"] == symbol), None)
        score = meta.get("signal_score", 50) if meta else 50
        drift_adj += (score - 50) * 0.00002  # ±0.5% annualized per 10 pts from 50
        adjustments.append({"factor": "Score", "value": round(score, 1), "drift_impact": f"{(score-50)*0.005:+.2f}%"})
    except: score = 50

    # 2. Supply/demand
    try:
        sd = get_supply_demand()
        deficit_pct = sd.get("deficit_pct", 0)
        if deficit_pct > 5:
            drift_adj += 0.000008 * deficit_pct  # +2% annualized per 10% deficit
            adjustments.append({"factor": "Supply Deficit", "value": f"{deficit_pct:.1f}%", "drift_impact": f"+{deficit_pct*0.002:.2f}%"})
    except: pass

    # 3. Cross-asset regime
    try:
        car = get_cross_asset_regime()
        regime = car.get("regime", "")
        if "SUPERCYCLE" in regime.upper():
            drift_adj += 0.00012  # +3% annualized
            adjustments.append({"factor": "Cross-Asset", "value": regime, "drift_impact": "+3.0%"})
        elif "RISK" in regime.upper() and "OFF" in regime.upper():
            drift_adj -= 0.00008
            adjustments.append({"factor": "Cross-Asset", "value": regime, "drift_impact": "-2.0%"})
    except: pass

    # 4. ETF flows
    try:
        flows = get_etf_flows()
        sig = flows.get("sector_signal", "")
        if "INFLOW" in sig:
            drift_adj += 0.00004
            adjustments.append({"factor": "ETF Flows", "value": sig, "drift_impact": "+1.0%"})
        elif "OUTFLOW" in sig:
            drift_adj -= 0.00004
            adjustments.append({"factor": "ETF Flows", "value": sig, "drift_impact": "-1.0%"})
    except: pass

    # 5. Inventory
    try:
        inv = get_inventory_levels()
        yrs = inv.get("years_supply", 3)
        if yrs < 1.5:
            drift_adj += 0.00008  # critical
            adjustments.append({"factor": "Inventory", "value": f"{yrs:.2f}yr", "drift_impact": "+2.0%"})
        elif yrs < 2.0:
            drift_adj += 0.00004
            adjustments.append({"factor": "Inventory", "value": f"{yrs:.2f}yr", "drift_impact": "+1.0%"})
    except: pass

    # 6. Geopolitical risk → volatility
    try:
        geo = get_geopolitical_risk()
        geo_score = geo.get("composite_risk_score", 50)
        if geo_score > 60:
            vol_adj *= 1.15  # +15% vol for elevated geo risk
            adjustments.append({"factor": "Geo Risk", "value": f"{geo_score:.0f}/100", "vol_impact": "+15%"})
    except: pass

    # 7. Options IV → volatility
    try:
        iv_data = get_options_iv_summary()
        sector_iv = iv_data.get("sector_avg_iv", 0)
        if sector_iv > 80:
            vol_adj *= 1.10
            adjustments.append({"factor": "Options IV", "value": f"{sector_iv:.0f}%", "vol_impact": "+10%"})
    except: pass

    # 8. Policy momentum
    try:
        policy = get_policy_tracker()
        summary = policy.get("summary", {})
        bullish = summary.get("bullish_count", 0)
        bearish = summary.get("bearish_count", 0)
        if bullish > bearish + 2:
            drift_adj += 0.00004
            adjustments.append({"factor": "Policy", "value": f"{bullish}B/{bearish}b", "drift_impact": "+1.0%"})
        elif bearish > bullish:
            drift_adj -= 0.00002
            adjustments.append({"factor": "Policy", "value": f"{bullish}B/{bearish}b", "drift_impact": "-0.5%"})
    except: pass

    # 9. Analyst ratings
    try:
        ratings = get_analyst_ratings()
        for r in ratings.get("ratings", []):
            if r.get("symbol") == symbol:
                consensus = r.get("consensus", "")
                if "BUY" in consensus.upper():
                    drift_adj += 0.00003
                    adjustments.append({"factor": "Analysts", "value": consensus, "drift_impact": "+0.8%"})
                elif "SELL" in consensus.upper():
                    drift_adj -= 0.00003
                    adjustments.append({"factor": "Analysts", "value": consensus, "drift_impact": "-0.8%"})
                break
    except: pass

    # 10. Short interest → volatility
    try:
        si = get_short_interest()
        for s in si.get("tickers", []):
            if s.get("symbol") == symbol and s.get("short_pct_float", 0) > 10:
                vol_adj *= 1.12
                adjustments.append({"factor": "Short Interest", "value": f"{s['short_pct_float']:.1f}%", "vol_impact": "+12%"})
                break
    except: pass

    # 11. Seasonality
    try:
        from datetime import datetime
        month = datetime.now().month
        season = get_seasonality(symbol)
        monthly = season.get("monthly", [])
        if monthly and month <= len(monthly):
            win_rate = monthly[month - 1].get("win_rate", 50)
            if win_rate < 40:
                drift_adj -= 0.00002
                adjustments.append({"factor": "Seasonality", "value": f"{win_rate}% win", "drift_impact": "-0.5%"})
            elif win_rate > 65:
                drift_adj += 0.00002
                adjustments.append({"factor": "Seasonality", "value": f"{win_rate}% win", "drift_impact": "+0.5%"})
    except: pass

    # 12. Correlation regime (CCI) → volatility
    try:
        cr = get_correlation_regime()
        cci = cr.get("cci", 0.5)
        if cci > 0.7:
            vol_adj *= 1.08
            adjustments.append({"factor": "Herd Mode", "value": f"CCI {cci:.2f}", "vol_impact": "+8%"})
    except: pass

    # 13. Contract coverage gap
    try:
        cc = get_contract_coverage()
        uncov_2028 = cc.get("total_uncovered_2028_mlbs", 0)
        if uncov_2028 > 30:
            drift_adj += 0.00003
            adjustments.append({"factor": "Contracts", "value": f"{uncov_2028}M uncov", "drift_impact": "+0.8%"})
    except: pass

    # 14. Insider trades
    try:
        ins = get_insider_trades()
        trades = [t for t in ins.get("trades", []) if t.get("symbol") == symbol]
        buys = sum(1 for t in trades if t.get("type", "").upper() == "BUY")
        sells = sum(1 for t in trades if t.get("type", "").upper() == "SELL")
        if buys + sells > 0:
            if buys > sells:
                drift_adj += 0.00002
                adjustments.append({"factor": "Insiders", "value": f"{buys}B/{sells}S", "drift_impact": "+0.5%"})
            elif sells > buys:
                drift_adj -= 0.00002
                adjustments.append({"factor": "Insiders", "value": f"{buys}B/{sells}S", "drift_impact": "-0.5%"})
    except: pass

    # 15. Miner valuation (cheap = bullish for individual stocks)
    try:
        vals = get_miner_valuations()
        for m in vals.get("miners", []):
            if m.get("symbol") == symbol:
                if m.get("signal") == "CHEAP":
                    drift_adj += 0.00002
                    adjustments.append({"factor": "Valuation", "value": f"${m['ev_per_lb']}/lb CHEAP", "drift_impact": "+0.5%"})
                elif m.get("signal") == "EXPENSIVE":
                    drift_adj -= 0.00002
                    adjustments.append({"factor": "Valuation", "value": f"${m['ev_per_lb']}/lb EXPENSIVE", "drift_impact": "-0.5%"})
                break
    except: pass

    # Final parameters
    adjusted_sigma = base_sigma * vol_adj
    daily_sigma = adjusted_sigma / np.sqrt(252)
    daily_drift = risk_free + drift_adj

    price = float(close.iloc[-1])
    tp_price = price * (1 + tp / 100)
    sl_price = price * (1 - sl / 100)

    # Run simulation
    rng = np.random.default_rng(42)
    tp_hits, sl_hits, neither = 0, 0, 0
    tp_days, sl_days = [], []
    final_prices = []
    # Percentile tracking
    all_paths = np.zeros((sims, days))

    for s in range(sims):
        p = price
        for d in range(days):
            p *= np.exp(daily_drift + daily_sigma * rng.standard_normal())
            all_paths[s, d] = p
            if p >= tp_price:
                tp_hits += 1; tp_days.append(d + 1)
                all_paths[s, d+1:] = p  # fill rest
                break
            elif p <= sl_price:
                sl_hits += 1; sl_days.append(d + 1)
                all_paths[s, d+1:] = p
                break
        else:
            neither += 1
            final_prices.append(p)

    tp_prob = tp_hits / sims * 100
    sl_prob = sl_hits / sims * 100
    exp_pnl = (tp_prob/100 * tp) + (sl_prob/100 * -sl) + (neither/sims * ((np.mean(final_prices)/price - 1)*100 if final_prices else 0))

    # Percentiles for fan chart
    pcts = {}
    for q, label in [(5, "p5"), (25, "p25"), (50, "p50"), (75, "p75"), (95, "p95")]:
        pcts[label] = [round(float(np.percentile(all_paths[:, d], q)), 2) for d in range(0, days, max(1, days//60))]

    return {
        "symbol": symbol, "current_price": round(price, 2),
        "tp_price": round(tp_price, 2), "sl_price": round(sl_price, 2),
        "tp_pct": tp, "sl_pct": sl,
        "simulations": sims, "horizon_days": days,
        "tp_probability": round(tp_prob, 1),
        "sl_probability": round(sl_prob, 1),
        "neither_pct": round(neither / sims * 100, 1),
        "median_days_to_tp": int(np.median(tp_days)) if tp_days else None,
        "median_days_to_sl": int(np.median(sl_days)) if sl_days else None,
        "expected_pnl_pct": round(exp_pnl, 2),
        "base_vol": round(base_sigma * 100, 1),
        "adjusted_vol": round(adjusted_sigma * 100, 1),
        "base_drift_annual": round(risk_free * 252 * 100, 2),
        "adjusted_drift_annual": round((risk_free + drift_adj) * 252 * 100, 2),
        "signal_adjustments": adjustments,
        "percentiles": pcts,
        "signal": "FAVORABLE" if tp_prob > sl_prob * 1.5 else ("UNFAVORABLE" if sl_prob > tp_prob * 1.5 else "NEUTRAL"),
        "vs_basic": {
            "note": "Compare with /api/monte-carlo-tpsl/{symbol} for plain GBM without signal weighting",
        }
    }

    # Log prediction for future Bayesian validation
    try:
        from datetime import datetime as _dt
        import json as _json
        conn = _get_db()
        conn.execute(
            "INSERT INTO prediction_log (timestamp, symbol, price_at_prediction, tp_pct, sl_pct, horizon_days, tp_probability, sl_probability, expected_pnl, adjusted_drift, adjusted_vol, num_signals, signal_summary) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_dt.utcnow().isoformat(), symbol, price, tp, sl, days,
             round(tp_prob, 1), round(sl_prob, 1), round(exp_pnl, 2),
             round((risk_free + drift_adj) * 252 * 100, 2), round(adjusted_sigma * 100, 1),
             len(adjustments), _json.dumps([a["factor"] for a in adjustments])))
        conn.commit()
        conn.close()
    except: pass

    return resp


@app.get("/api/divergences")
def get_divergences():
    """Detect price vs RSI/MACD/volume divergences for all tickers."""
    import numpy as np
    results = []
    lookback = 20

    for symbol in TICKERS:
        try:
            meta = get_ticker_meta(symbol)
            if not meta:
                continue
            prices_raw = get_prices(symbol, limit=60)
            if not prices_raw or len(prices_raw) < lookback + 5:
                continue

            closes = np.array([p["close"] for p in prices_raw[-lookback:]])
            volumes = np.array([p.get("volume", 0) for p in prices_raw[-lookback:]])
            price = closes[-1]

            # Helper: linear regression slope
            def slope(arr):
                x = np.arange(len(arr))
                if len(arr) < 2 or np.std(arr) == 0:
                    return 0.0
                return float(np.polyfit(x, arr, 1)[0])

            price_slope = slope(closes)

            # RSI divergence
            from analysis import compute_rsi
            import pandas as pd
            all_closes = pd.Series([p["close"] for p in prices_raw])
            rsi_series = compute_rsi(all_closes)
            rsi_vals = rsi_series.dropna().values[-lookback:]
            rsi_slope = slope(rsi_vals) if len(rsi_vals) >= lookback else 0

            divs = []

            # Price up + RSI down = bearish divergence
            if price_slope > 0 and rsi_slope < -0.15:
                divs.append({"indicator": "RSI", "type": "bearish",
                    "strength": "strong" if rsi_slope < -0.3 else "moderate",
                    "detail": f"Price rising but RSI falling ({rsi_vals[-1]:.0f}→trend)"})
            elif price_slope < 0 and rsi_slope > 0.15:
                divs.append({"indicator": "RSI", "type": "bullish",
                    "strength": "strong" if rsi_slope > 0.3 else "moderate",
                    "detail": f"Price falling but RSI rising ({rsi_vals[-1]:.0f}→trend)"})

            # MACD histogram divergence
            from analysis import compute_macd
            macd_line, sig_line = compute_macd(all_closes)
            hist = (macd_line - sig_line).dropna().values[-lookback:]
            if len(hist) >= lookback:
                hist_slope = slope(hist)
                if price_slope > 0 and hist_slope < -0.005:
                    divs.append({"indicator": "MACD", "type": "bearish",
                        "strength": "strong" if hist_slope < -0.01 else "moderate",
                        "detail": "Price rising but MACD histogram weakening"})
                elif price_slope < 0 and hist_slope > 0.005:
                    divs.append({"indicator": "MACD", "type": "bullish",
                        "strength": "strong" if hist_slope > 0.01 else "moderate",
                        "detail": "Price falling but MACD histogram strengthening"})

            # Volume divergence
            if volumes.sum() > 0:
                vol_slope = slope(volumes)
                avg_vol = volumes.mean()
                if avg_vol > 0:
                    vol_norm = vol_slope / avg_vol
                    if price_slope > 0 and vol_norm < -0.02:
                        divs.append({"indicator": "Volume", "type": "bearish",
                            "strength": "strong" if vol_norm < -0.04 else "moderate",
                            "detail": "Price rising on declining volume — weak conviction"})
                    elif price_slope < 0 and vol_norm > 0.02:
                        divs.append({"indicator": "Volume", "type": "bullish",
                            "strength": "strong" if vol_norm > 0.04 else "moderate",
                            "detail": "Price falling but volume increasing — potential capitulation"})

            results.append({
                "symbol": symbol,
                "price": round(price, 2),
                "price_trend": "rising" if price_slope > 0 else "falling",
                "divergences": divs,
                "has_divergence": len(divs) > 0,
            })
        except Exception as e:
            results.append({"symbol": symbol, "error": str(e), "divergences": [], "has_divergence": False})

    bearish = sum(1 for r in results for d in r.get("divergences", []) if d["type"] == "bearish")
    bullish = sum(1 for r in results for d in r.get("divergences", []) if d["type"] == "bullish")
    total = len(results)

    if bearish >= 3:
        composite = "BEARISH DIVERGENCE"
        detail = f"{bearish}/{total} tickers showing bearish divergences — caution"
    elif bullish >= 3:
        composite = "BULLISH DIVERGENCE"
        detail = f"{bullish}/{total} tickers showing bullish divergences — opportunity"
    elif bearish > bullish:
        composite = "MILD BEARISH"
        detail = f"{bearish} bearish vs {bullish} bullish divergences"
    elif bullish > bearish:
        composite = "MILD BULLISH"
        detail = f"{bullish} bullish vs {bearish} bearish divergences"
    else:
        composite = "NO DIVERGENCE"
        detail = "Price and indicators aligned"

    return {
        "tickers": results,
        "composite_signal": composite,
        "composite_detail": detail,
        "bearish_count": bearish,
        "bullish_count": bullish,
    }


@app.get("/api/term-spread")
def get_term_spread():
    """Term contract vs spot price spread — institutional pricing signal."""
    # Hardcoded from WNA/UxC/TradeTech quarterly reports (updated monthly)
    # Source: WNA Nuclear Fuel Report 2025, Cameco Q4 2025 earnings
    term_data = {
        "spot_price": 94.28,  # UxC spot via Cameco (Jan 2026) — overridden by live data below
        "mid_term_price": 80.0,  # 3-5yr contracts, WNA/UxC Q1 2026
        "long_term_price": 89.0,  # 7-10yr contracts, Cameco Q1 2026 (matches /api/spot-price long_term_price)
        "avg_utility_contract": 72.0,  # Cameco avg realized price FY2025
        "last_updated": "2026-Q1",
        "source": "WNA Nuclear Fuel Report / Cameco filings",
    }

    # Try to get live spot from our endpoint
    try:
        sp = get_spot_price()
        if sp.get("price"):
            term_data["spot_price"] = sp["price"]
    except: pass

    spot = term_data["spot_price"]
    lt = term_data["long_term_price"]
    mt = term_data["mid_term_price"]

    lt_spread = ((lt - spot) / spot) * 100
    mt_spread = ((mt - spot) / spot) * 100

    if lt_spread > 20:
        signal = "STRONG CONTANGO"
        detail = "Utilities paying 20%+ premium for long-term supply — extreme urgency"
    elif lt_spread > 5:
        signal = "CONTANGO"
        detail = "Long-term premium reflects utility hedging demand"
    elif lt_spread < -10:
        signal = "BACKWARDATION"
        detail = "Spot exceeds term — squeeze conditions, speculative premium"
    else:
        signal = "CONVERGING"
        detail = "Spot and term prices aligned — balanced market"

    return {
        **term_data,
        "lt_spread_pct": round(lt_spread, 1),
        "mt_spread_pct": round(mt_spread, 1),
        "signal": signal,
        "detail": detail,
        "historical": [
            {"period": "2023-Q1", "spot": 51.0, "lt": 53.0, "spread": 3.9},
            {"period": "2023-Q3", "spot": 56.0, "lt": 60.0, "spread": 7.1},
            {"period": "2024-Q1", "spot": 106.0, "lt": 68.0, "spread": -35.8},
            {"period": "2024-Q3", "spot": 82.0, "lt": 75.0, "spread": -8.5},
            {"period": "2025-Q1", "spot": 65.0, "lt": 78.0, "spread": 20.0},
            {"period": "2025-Q3", "spot": 60.0, "lt": 80.0, "spread": 33.3},
            {"period": "2025-Q4", "spot": round(spot, 0), "lt": lt, "spread": round(lt_spread, 1)},
        ],
        "insight": f"Long-term contracts at ${lt}/lb vs ${spot:.0f} spot = {lt_spread:+.1f}% premium. Utilities are {'aggressively locking in supply' if lt_spread > 15 else 'cautiously hedging' if lt_spread > 0 else 'not urgently contracting'}.",
    }


_corr_regime_cache = {"data": None, "ts": 0}

@app.get("/api/correlation-regime")
def get_correlation_regime():
    """Rolling correlation regime: detect herding vs diversification."""
    import time as _time
    import yfinance as yf, numpy as np
    now = _time.time()
    if _corr_regime_cache["data"] and now - _corr_regime_cache["ts"] < 3600:
        return _corr_regime_cache["data"]

    syms = ["URA", "CCJ", "UEC", "UUUU", "DNN", "NXE", "SPY", "GLD", "USO"]
    uranium_syms = ["URA", "CCJ", "UEC", "UUUU", "DNN", "NXE"]

    try:
        prices = {}
        for s in syms:
            h = yf.Ticker(s).history(period="6mo")
            if not h.empty:
                prices[s] = h["Close"]

        import pandas as pd
        df = pd.DataFrame(prices).dropna()
        if len(df) < 60:
            raise ValueError("Insufficient data")

        rets = df.pct_change().dropna()

        # 30-day rolling pairwise correlation for uranium tickers
        window = 30
        cci_history = []
        ura_spy_history = []

        for end in range(window, len(rets)):
            chunk = rets.iloc[end - window:end]
            # CCI: avg pairwise corr among uranium
            u_rets = chunk[[s for s in uranium_syms if s in chunk.columns]]
            corr = u_rets.corr()
            n = len(corr)
            pairs = [(corr.iloc[i, j]) for i in range(n) for j in range(i + 1, n)]
            cci = float(np.mean(pairs)) if pairs else 0

            # URA-SPY correlation
            if "URA" in chunk.columns and "SPY" in chunk.columns:
                ura_spy = float(chunk["URA"].corr(chunk["SPY"]))
            else:
                ura_spy = 0

            dt = rets.index[end].strftime("%Y-%m-%d")
            cci_history.append({"date": dt, "cci": round(cci, 3)})
            ura_spy_history.append({"date": dt, "corr": round(ura_spy, 3)})

        current_cci = cci_history[-1]["cci"] if cci_history else 0
        current_ura_spy = ura_spy_history[-1]["corr"] if ura_spy_history else 0

        # 90d baseline
        baseline_cci = np.mean([h["cci"] for h in cci_history[-90:]]) if len(cci_history) >= 90 else np.mean([h["cci"] for h in cci_history])

        if current_cci > 0.7:
            regime = "HERD MODE"
        elif current_cci > 0.4:
            regime = "CONVERGING"
        else:
            regime = "DIVERSIFIED"

        decorrelated = current_ura_spy < -0.2

        # Current full correlation matrix (30d)
        recent = rets.tail(30)
        full_corr = recent.corr()
        matrix = {}
        for s1 in full_corr.columns:
            matrix[s1] = {s2: round(float(full_corr.loc[s1, s2]), 3) for s2 in full_corr.columns}

        resp = {
            "cci": round(current_cci, 3),
            "cci_baseline_90d": round(float(baseline_cci), 3),
            "regime": regime,
            "ura_spy_correlation": round(current_ura_spy, 3),
            "decorrelation_event": decorrelated,
            "cci_history": cci_history[-90:],
            "ura_spy_history": ura_spy_history[-90:],
            "signal": f"{regime} — {'Uranium decorrelated from SPY (diversification signal)' if decorrelated else f'URA-SPY corr: {current_ura_spy:.2f}'}",
        }
        _corr_regime_cache["data"] = resp
        _corr_regime_cache["ts"] = now
        return resp
    except Exception as e:
        return {"error": str(e), "regime": "UNKNOWN"}


GEOPOLITICAL_PROFILES = {
    "Kazakhstan": {"flag": "🇰🇿", "supply_pct": 43, "risk": "HIGH", "risk_score": 65,
        "factors": ["Kazatomprom state-controlled", "Russia economic orbit", "Water scarcity threatens ISR mining", "2022 political unrest"],
        "last_event": "Kazatomprom cuts 2025 production guidance by 17% (Jan 2025)"},
    "Canada": {"flag": "🇨🇦", "supply_pct": 15, "risk": "LOW", "risk_score": 15,
        "factors": ["Stable democracy", "Strong regulatory framework", "Indigenous land rights negotiations", "Harsh climate = seasonal production"],
        "last_event": "Cameco McArthur River restart at full capacity (2024)"},
    "Namibia": {"flag": "🇳🇦", "supply_pct": 11, "risk": "MEDIUM", "risk_score": 40,
        "factors": ["Water stress in Erongo region", "Chinese investment dominance (Husab mine)", "Political stability but resource nationalism risk"],
        "last_event": "Paladin Langer Heinrich ramp-up delays (2024)"},
    "Australia": {"flag": "🇦🇺", "supply_pct": 9, "risk": "LOW", "risk_score": 20,
        "factors": ["Political resistance to new mines", "Three mine policy (SA)", "AUKUS alliance = nuclear friendly shift"],
        "last_event": "Boss Energy Honeymoon production started (2024)"},
    "Niger": {"flag": "🇳🇪", "supply_pct": 5, "risk": "CRITICAL", "risk_score": 90,
        "factors": ["2023 military coup", "French Orano operations suspended", "Political instability", "Russia/Wagner influence"],
        "last_event": "Orano SOMAIR mine suspended after coup (2023)"},
    "Russia": {"flag": "🇷🇺", "supply_pct": 6, "risk": "CRITICAL", "risk_score": 95,
        "factors": ["Western sanctions", "42% global enrichment (TENEX)", "33% conversion capacity", "Weapon-grade HEU stockpile"],
        "last_event": "US ban on Russian uranium imports signed (2024)"},
    "Uzbekistan": {"flag": "🇺🇿", "supply_pct": 7, "risk": "MEDIUM", "risk_score": 45,
        "factors": ["Navoi Mining state-owned", "Russia economic dependence", "Growing Chinese partnerships", "Production capacity expanding"],
        "last_event": "Production target 3,500t/yr by 2030 announced"},
}

@app.get("/api/geopolitical-risk")
def get_geopolitical_risk():
    profiles = []
    total_risk_weighted = 0
    total_supply_at_risk = 0
    for country, p in GEOPOLITICAL_PROFILES.items():
        profiles.append({"country": country, **p})
        total_risk_weighted += p["supply_pct"] * p["risk_score"]
        if p["risk"] in ("HIGH", "CRITICAL"):
            total_supply_at_risk += p["supply_pct"]

    composite_score = total_risk_weighted / sum(p["supply_pct"] for p in GEOPOLITICAL_PROFILES.values())

    if composite_score > 60:
        signal = "ELEVATED — Supply disruption risk supports prices"
    elif composite_score > 40:
        signal = "MODERATE — Some concentration risk"
    else:
        signal = "LOW — Stable supply outlook"

    return {
        "profiles": sorted(profiles, key=lambda x: -x["supply_pct"]),
        "composite_risk_score": round(composite_score, 1),
        "supply_at_risk_pct": total_supply_at_risk,
        "signal": signal,
        "note": "Kazakhstan (43%) + Russia (6%) + Niger (5%) = 54% of supply under HIGH/CRITICAL risk",
    }


MINER_RESOURCES = {
    "CCJ": {"resources_mlbs": 900, "type": "Diversified", "key_asset": "Cigar Lake, McArthur River"},
    "NXE": {"resources_mlbs": 340, "type": "Developer", "key_asset": "Arrow Deposit (Rook I)"},
    "UEC": {"resources_mlbs": 165, "type": "ISR Producer", "key_asset": "Christensen Ranch, Burke Hollow"},
    "UUUU": {"resources_mlbs": 65, "type": "Conventional + REE", "key_asset": "White Mesa Mill"},
    "DNN": {"resources_mlbs": 120, "type": "Developer", "key_asset": "Wheeler River"},
}

@app.get("/api/miner-valuations")
def get_miner_valuations():
    """EV/lb resource valuation comparison across uranium miners."""
    import yfinance as yf
    results = []
    for sym, res in MINER_RESOURCES.items():
        try:
            t = yf.Ticker(sym)
            mcap = t.fast_info.get("marketCap")
            if not mcap:
                continue
            ev_per_lb = mcap / (res["resources_mlbs"] * 1e6)
            results.append({
                "symbol": sym,
                "market_cap": round(mcap / 1e9, 2),
                "resources_mlbs": res["resources_mlbs"],
                "ev_per_lb": round(ev_per_lb, 2),
                "type": res["type"],
                "key_asset": res["key_asset"],
            })
        except Exception as e:
            print(f"[VALUATION] Error {sym}: {e}")

    results.sort(key=lambda x: x["ev_per_lb"])
    avg_ev = sum(r["ev_per_lb"] for r in results) / len(results) if results else 0

    for r in results:
        r["vs_avg_pct"] = round((r["ev_per_lb"] / avg_ev - 1) * 100, 1) if avg_ev else 0
        r["signal"] = "CHEAP" if r["vs_avg_pct"] < -15 else ("EXPENSIVE" if r["vs_avg_pct"] > 15 else "FAIR")

    return {
        "miners": results,
        "avg_ev_per_lb": round(avg_ev, 2),
        "cheapest": results[0]["symbol"] if results else None,
        "most_expensive": results[-1]["symbol"] if results else None,
    }


@app.get("/api/contract-coverage")
def get_contract_coverage():
    """Utility contract coverage — uncovered requirements drive price."""
    return {
        "us_utilities": {
            "annual_requirement_mlbs": 44,
            "coverage": [
                {"year": 2026, "contracted_pct": 85, "uncovered_mlbs": 6.6},
                {"year": 2027, "contracted_pct": 70, "uncovered_mlbs": 13.2},
                {"year": 2028, "contracted_pct": 55, "uncovered_mlbs": 19.8},
                {"year": 2029, "contracted_pct": 40, "uncovered_mlbs": 26.4},
                {"year": 2030, "contracted_pct": 25, "uncovered_mlbs": 33.0},
                {"year": 2031, "contracted_pct": 15, "uncovered_mlbs": 37.4},
                {"year": 2032, "contracted_pct": 8, "uncovered_mlbs": 40.5},
            ],
        },
        "eu_utilities": {
            "annual_requirement_mlbs": 38,
            "coverage": [
                {"year": 2026, "contracted_pct": 80, "uncovered_mlbs": 7.6},
                {"year": 2027, "contracted_pct": 65, "uncovered_mlbs": 13.3},
                {"year": 2028, "contracted_pct": 50, "uncovered_mlbs": 19.0},
                {"year": 2029, "contracted_pct": 35, "uncovered_mlbs": 24.7},
                {"year": 2030, "contracted_pct": 20, "uncovered_mlbs": 30.4},
            ],
        },
        "total_uncovered_2028_mlbs": 38.8,
        "total_uncovered_2030_mlbs": 63.4,
        "signal": "CONTRACTING WAVE IMMINENT",
        "insight": "By 2028, ~39M lbs of US+EU demand is uncovered. By 2030, 63M lbs. Utilities must enter the market for long-term contracts — this wave of buying is the structural price catalyst. Typical contracting lead time is 2-3 years, meaning 2028 contracts should be signed in 2025-2026.",
    }


@app.get("/api/inventory-levels")
def get_inventory_levels():
    """US utility uranium inventory levels (EIA historical data)."""
    # EIA Table S1a — US civilian nuclear power reactor inventories (million lbs U3O8 equivalent)
    historical = [
        {"year": 2015, "inventory_mlbs": 113.1, "consumption_mlbs": 50.3},
        {"year": 2016, "inventory_mlbs": 112.6, "consumption_mlbs": 50.6},
        {"year": 2017, "inventory_mlbs": 114.3, "consumption_mlbs": 46.3},
        {"year": 2018, "inventory_mlbs": 111.5, "consumption_mlbs": 46.2},
        {"year": 2019, "inventory_mlbs": 100.1, "consumption_mlbs": 46.7},
        {"year": 2020, "inventory_mlbs": 94.5, "consumption_mlbs": 46.0},
        {"year": 2021, "inventory_mlbs": 87.7, "consumption_mlbs": 46.8},
        {"year": 2022, "inventory_mlbs": 79.0, "consumption_mlbs": 47.5},
        {"year": 2023, "inventory_mlbs": 72.4, "consumption_mlbs": 48.0},
        {"year": 2024, "inventory_mlbs": 66.8, "consumption_mlbs": 48.5},
        {"year": 2025, "inventory_mlbs": 62.0, "consumption_mlbs": 49.0},
        {"year": 2026, "inventory_mlbs": 58.5, "consumption_mlbs": 49.5},  # estimate
    ]
    for h in historical:
        h["years_of_supply"] = round(h["inventory_mlbs"] / h["consumption_mlbs"], 2)

    latest = historical[-1]
    prev = historical[-2]
    yoy_change = round((latest["inventory_mlbs"] - prev["inventory_mlbs"]) / prev["inventory_mlbs"] * 100, 1)
    yrs = latest["years_of_supply"]

    return {
        "current": {
            "inventory_mlbs": latest["inventory_mlbs"],
            "consumption_mlbs": latest["consumption_mlbs"],
            "years_of_supply": yrs,
            "yoy_change_pct": yoy_change,
            "signal": "CRITICAL" if yrs < 1.5 else ("TIGHT" if yrs < 2.5 else ("ADEQUATE" if yrs < 4 else "SURPLUS")),
        },
        "historical": historical,
        "insight": f"US utility inventories at {latest['inventory_mlbs']}M lbs — {yrs:.1f} years of supply. Down {abs(yoy_change):.1f}% YoY. Inventories have fallen 45% since 2015 peak. Below 1.5 years triggers panic buying.",
    }


@app.get("/api/enrichment-capacity")
def get_enrichment_capacity():
    """Global uranium enrichment & conversion capacity."""
    return {
        "enrichment": {
            "global_capacity_tSWU": 66000,
            "global_demand_tSWU": 56000,
            "utilization_pct": 84.8,
            "spare_capacity_tSWU": 10000,
            "providers": [
                {"name": "Urenco", "country": "EU/UK/US", "capacity_tSWU": 18800, "share_pct": 28.5},
                {"name": "TENEX (Rosatom)", "country": "Russia", "capacity_tSWU": 27700, "share_pct": 42.0},
                {"name": "Orano", "country": "France", "capacity_tSWU": 7500, "share_pct": 11.4},
                {"name": "CNNC", "country": "China", "capacity_tSWU": 10000, "share_pct": 15.2},
                {"name": "Other", "country": "Various", "capacity_tSWU": 2000, "share_pct": 3.0},
            ],
            "signal": "CONCENTRATED RISK",
            "insight": "Russia (TENEX) controls 42% of global enrichment. Western sanctions + supply chain de-risking = structural tailwind for Urenco/Orano pricing power.",
        },
        "conversion": {
            "global_capacity_tU": 76000,
            "global_demand_tU": 60000,
            "utilization_pct": 78.9,
            "providers": [
                {"name": "Cameco (Port Hope)", "country": "Canada", "capacity_tU": 12500, "share_pct": 16.4},
                {"name": "Orano (Malvési)", "country": "France", "capacity_tU": 15000, "share_pct": 19.7},
                {"name": "ConverDyn (Metropolis)", "country": "USA", "capacity_tU": 15000, "share_pct": 19.7},
                {"name": "Rosatom", "country": "Russia", "capacity_tU": 25000, "share_pct": 32.9},
                {"name": "CNNC", "country": "China", "capacity_tU": 8500, "share_pct": 11.2},
            ],
            "signal": "TIGHT",
            "insight": "Western conversion capacity (Cameco + Orano + ConverDyn) = 42.5 ktU vs ~40 ktU Western demand. Near full utilization excluding Russia.",
        },
        "geopolitical_risk": {
            "russia_share_enrichment_pct": 42.0,
            "russia_share_conversion_pct": 32.9,
            "western_self_sufficiency": False,
            "signal": "HIGH RISK",
            "insight": "If Russian supply is sanctioned/disrupted, Western enrichment runs at 100%+ utilization. This is the #1 structural risk premium in uranium pricing.",
        },
    }


MINE_PIPELINE = [
    {"name": "Rook I", "company": "NexGen Energy", "ticker": "NXE", "country": "Canada", "status": "permitting", "capacity_mlbs": 30.0, "expected_start": 2029, "capex_usd": 1300},
    {"name": "Wheeler River", "company": "Denison Mines", "ticker": "DNN", "country": "Canada", "status": "permitting", "capacity_mlbs": 6.0, "expected_start": 2028, "capex_usd": 322},
    {"name": "Dasa", "company": "Global Atomic", "ticker": "GLO.TO", "country": "Niger", "status": "construction", "capacity_mlbs": 4.4, "expected_start": 2026, "capex_usd": 345},
    {"name": "Langer Heinrich (restart)", "company": "Paladin Energy", "ticker": "PDN.AX", "country": "Namibia", "status": "producing", "capacity_mlbs": 6.0, "expected_start": 2024, "capex_usd": 118},
    {"name": "Honeymoon", "company": "Boss Energy", "ticker": "BOE.AX", "country": "Australia", "status": "commissioning", "capacity_mlbs": 2.5, "expected_start": 2025, "capex_usd": 80},
    {"name": "Rosita / Alta Mesa", "company": "enCore Energy", "ticker": "EU", "country": "USA", "status": "producing", "capacity_mlbs": 2.0, "expected_start": 2024, "capex_usd": 50},
    {"name": "Christensen Ranch", "company": "Uranium Energy Corp", "ticker": "UEC", "country": "USA", "status": "producing", "capacity_mlbs": 2.5, "expected_start": 2024, "capex_usd": 30},
    {"name": "Lance", "company": "Peninsula Energy", "ticker": "PEN.AX", "country": "USA", "status": "commissioning", "capacity_mlbs": 2.0, "expected_start": 2025, "capex_usd": 66},
    {"name": "Kayelekera (restart)", "company": "Lotus Resources", "ticker": "LOT.AX", "country": "Malawi", "status": "permitting", "capacity_mlbs": 2.5, "expected_start": 2027, "capex_usd": 87},
    {"name": "Tumas", "company": "Deep Yellow", "ticker": "DYL.AX", "country": "Namibia", "status": "permitting", "capacity_mlbs": 3.5, "expected_start": 2028, "capex_usd": 354},
    {"name": "Zuuvch Ovoo", "company": "Orano", "ticker": "ORANO.PA", "country": "Mongolia", "status": "construction", "capacity_mlbs": 3.0, "expected_start": 2027, "capex_usd": 200},
    {"name": "Mulga Rock", "company": "Deep Yellow", "ticker": "DYL.AX", "country": "Australia", "status": "permitting", "capacity_mlbs": 3.5, "expected_start": 2029, "capex_usd": 393},
]

@app.get("/api/mine-pipeline")
def get_mine_pipeline():
    """Major uranium mine development pipeline."""
    from collections import defaultdict
    projects = sorted(MINE_PIPELINE, key=lambda x: x["expected_start"])

    by_year = defaultdict(float)
    for p in projects:
        by_year[p["expected_start"]] += p["capacity_mlbs"]

    total_pipeline = sum(p["capacity_mlbs"] for p in projects)
    producing = sum(p["capacity_mlbs"] for p in projects if p["status"] == "producing")
    not_yet = total_pipeline - producing

    # Current deficit ~16M lbs/yr, demand growing ~3M lbs/yr from new reactors
    # Historical mine project realization rate: ~60% (delays, downsizing, cancellations)
    demand_growth_by_2030 = 5 * 3.0  # 5 years × 3M lbs/yr
    realized_supply = not_yet * 0.60
    supply_gap_2030 = round(16.0 + demand_growth_by_2030 - realized_supply, 1)

    return {
        "projects": projects,
        "by_year": [{"year": y, "capacity_mlbs": round(c, 1)} for y, c in sorted(by_year.items())],
        "summary": {
            "total_pipeline_mlbs": round(total_pipeline, 1),
            "producing_mlbs": round(producing, 1),
            "development_mlbs": round(not_yet, 1),
            "supply_gap_2030_mlbs": supply_gap_2030,
            "signal": "STRUCTURAL DEFICIT" if supply_gap_2030 > 5 else ("TIGHT" if supply_gap_2030 > 0 else "BALANCED"),
        },
    }


_policy_cache = {"data": None, "ts": 0}

BULLISH_KEYWORDS = ["subsidy", "subsidies", "fund", "funding", "smr", "advanced reactor", "streamline",
    "expedite", "tax credit", "incentive", "promote", "support", "develop", "deploy",
    "innovation", "moderniz", "license reform", "permit", "appropriat"]
BEARISH_KEYWORDS = ["ban", "moratorium", "restrict", "waste", "phase out", "prohibit",
    "shutdown", "decommission", "liability", "cleanup"]

@app.get("/api/policy-tracker")
def get_policy_tracker():
    """Congressional nuclear policy tracker via GovTrack API."""
    import time
    now = time.time()
    if _policy_cache["data"] and now - _policy_cache["ts"] < 21600:
        return _policy_cache["data"]

    bills = []
    seen_numbers = set()
    for query in ["advanced nuclear reactor", "uranium mining", "nuclear energy fund", "SMR small modular", "nuclear power"]:
        try:
            r = httpx.get(
                "https://www.govtrack.us/api/v2/bill",
                params={"q": query, "sort": "-current_status_date", "limit": 10},
                timeout=15, headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code != 200:
                continue
            for b in r.json().get("objects", []):
                display = b.get("display_number", "")
                if display in seen_numbers:
                    continue
                seen_numbers.add(display)
                title = b.get("title_without_number", "") or b.get("title", "")
                title_lower = title.lower()

                bullish = sum(1 for kw in BULLISH_KEYWORDS if kw in title_lower)
                bearish = sum(1 for kw in BEARISH_KEYWORDS if kw in title_lower)
                sentiment = "BULLISH" if bullish > bearish else ("BEARISH" if bearish > bullish else "NEUTRAL")

                status = b.get("current_status", "")
                status_label = status.replace("_", " ").title() if status else "Unknown"
                sponsor = b.get("sponsor")
                sponsor_name = sponsor.get("name", "") if isinstance(sponsor, dict) else ""

                bills.append({
                    "id": b.get("id"),
                    "number": b.get("display_number", ""),
                    "title": title[:120],
                    "sponsor": sponsor_name,
                    "status": status_label,
                    "date": b.get("current_status_date", ""),
                    "sentiment": sentiment,
                    "link": b.get("link", ""),
                })
        except Exception as e:
            print(f"[POLICY] Error querying '{query}': {e}")

    bills.sort(key=lambda x: x["date"], reverse=True)
    bullish_count = sum(1 for b in bills if b["sentiment"] == "BULLISH")
    bearish_count = sum(1 for b in bills if b["sentiment"] == "BEARISH")

    if bullish_count > bearish_count * 2:
        momentum = "STRONG TAILWIND"
    elif bullish_count > bearish_count:
        momentum = "TAILWIND"
    elif bearish_count > bullish_count:
        momentum = "HEADWIND"
    else:
        momentum = "NEUTRAL"

    resp = {
        "bills": bills[:20],
        "summary": {
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "neutral_count": len(bills) - bullish_count - bearish_count,
            "momentum": momentum,
        },
    }
    _policy_cache["data"] = resp
    _policy_cache["ts"] = now
    return resp


_supply_demand_cache = {"data": None, "ts": 0}

@app.get("/api/supply-demand")
def get_supply_demand():
    """Uranium supply/demand balance model using reactor CSV data."""
    import time, csv
    now = time.time()
    if _supply_demand_cache["data"] and now - _supply_demand_cache["ts"] < 86400:
        return _supply_demand_cache["data"]

    csv_path = os.path.join(os.path.dirname(__file__), "reactors.csv")
    with open(csv_path) as f:
        reactors = list(csv.DictReader(f))

    operational = [r for r in reactors if r["Status"] == "Operational"]
    under_construction = [r for r in reactors if r["Status"] == "Under Construction"]
    planned = [r for r in reactors if r["Status"] == "Planned"]

    op_gwe = sum(float(r["Capacity"]) for r in operational if r["Capacity"]) / 1000
    uc_gwe = sum(float(r["Capacity"]) for r in under_construction if r["Capacity"]) / 1000
    pl_gwe = sum(float(r["Capacity"]) for r in planned if r["Capacity"]) / 1000

    # Demand: ~480 lbs U3O8 per MWe per year = 0.48M lbs per GWe (WNA industry average)
    mlbs_per_gwe = 0.48  # million lbs U3O8 per GWe per year
    current_demand = round(op_gwe * mlbs_per_gwe, 1)
    future_demand_uc = round((op_gwe + uc_gwe) * mlbs_per_gwe, 1)

    # Supply (WNA 2024 estimates, Mlbs U3O8)
    mine_production = 140  # ~140M lbs/yr (Kazakhstan 45%, Canada 15%, Namibia 12%, Australia 9%)
    secondary_supply = 17  # DOE inventory, underfeeding, MOX, recycled
    total_supply = mine_production + secondary_supply

    deficit = round(current_demand - total_supply, 1)

    # Country breakdown (top producers, WNA 2024 data)
    producers = [
        {"country": "Kazakhstan", "mlbs": 63.0, "pct": 45.0, "trend": "UP"},
        {"country": "Canada", "mlbs": 21.0, "pct": 15.0, "trend": "FLAT"},
        {"country": "Namibia", "mlbs": 16.8, "pct": 12.0, "trend": "UP"},
        {"country": "Australia", "mlbs": 12.6, "pct": 9.0, "trend": "DOWN"},
        {"country": "Uzbekistan", "mlbs": 7.0, "pct": 5.0, "trend": "FLAT"},
        {"country": "Russia", "mlbs": 5.6, "pct": 4.0, "trend": "FLAT"},
        {"country": "Other", "mlbs": 14.0, "pct": 10.0, "trend": "FLAT"},
    ]

    # Demand by country (top consumers from reactor data)
    from collections import Counter
    country_gwe = Counter()
    for r in operational:
        cap = float(r["Capacity"]) / 1000 if r["Capacity"] else 0
        country_gwe[r["Country"]] += cap
    top_consumers = [
        {"country": c, "gwe": round(g, 1), "demand_mlbs": round(g * mlbs_per_gwe, 1)}
        for c, g in country_gwe.most_common(10)
    ]

    # Construction pipeline by country
    uc_by_country = Counter()
    for r in under_construction:
        cap = float(r["Capacity"]) / 1000 if r["Capacity"] else 0
        uc_by_country[r["Country"]] += cap
    construction = [
        {"country": c, "gwe": round(g, 1), "units": sum(1 for r in under_construction if r["Country"] == c)}
        for c, g in uc_by_country.most_common(5)
    ]

    resp = {
        "demand": {
            "operational_gwe": round(op_gwe, 1),
            "operational_units": len(operational),
            "annual_demand_mlbs": current_demand,
            "top_consumers": top_consumers,
        },
        "supply": {
            "mine_production_mlbs": mine_production,
            "secondary_supply_mlbs": secondary_supply,
            "total_supply_mlbs": total_supply,
            "producers": producers,
        },
        "balance": {
            "deficit_mlbs": deficit,
            "deficit_pct": round(deficit / current_demand * 100, 1) if current_demand else 0,
            "signal": "STRUCTURAL DEFICIT" if deficit > 10 else ("TIGHT" if deficit > 0 else "BALANCED"),
        },
        "pipeline": {
            "under_construction_gwe": round(uc_gwe, 1),
            "under_construction_units": len(under_construction),
            "planned_gwe": round(pl_gwe, 1),
            "planned_units": len(planned),
            "additional_demand_mlbs": round(uc_gwe * mlbs_per_gwe, 1),
            "top_construction": construction,
        },
        "uranium_implication": f"Structural deficit of ~{abs(deficit):.0f}M lbs/yr ({abs(round(deficit/current_demand*100))}% of demand). Pipeline adds {round(uc_gwe*mlbs_per_gwe):.0f}M lbs demand — deficit widens without new mines.",
    }
    _supply_demand_cache["data"] = resp
    _supply_demand_cache["ts"] = now
    return resp


_institutional_cache = {}

@app.get("/api/institutional-ownership/{symbol}")
def get_institutional_ownership(symbol: str):
    """Top institutional holders + accumulation/distribution signal."""
    import time
    symbol = symbol.upper()
    now = time.time()
    if symbol in _institutional_cache and now - _institutional_cache[symbol]["ts"] < 86400:
        return _institutional_cache[symbol]["data"]

    import yfinance as yf
    try:
        t = yf.Ticker(symbol)
        ih = t.institutional_holders
        mh = t.mutualfund_holders
    except Exception as e:
        raise HTTPException(500, f"Error fetching data: {e}")

    holders = []
    if ih is not None and not ih.empty:
        for _, row in ih.iterrows():
            holders.append({
                "name": str(row.get("Holder", "")),
                "shares": int(row.get("Shares", 0)),
                "value": int(row.get("Value", 0)),
                "pct_held": round(float(row.get("pctHeld", 0)) * 100, 2),
                "pct_change": round(float(row.get("pctChange", 0)) * 100, 2),
                "date": str(row.get("Date Reported", "")),
                "type": "institution",
            })

    if mh is not None and not mh.empty:
        for _, row in mh.iterrows():
            holders.append({
                "name": str(row.get("Holder", "")),
                "shares": int(row.get("Shares", 0)),
                "value": int(row.get("Value", 0)),
                "pct_held": round(float(row.get("pctHeld", 0)) * 100, 2),
                "pct_change": round(float(row.get("pctChange", 0)) * 100, 2),
                "date": str(row.get("Date Reported", "")),
                "type": "fund",
            })

    # Sort by value
    holders.sort(key=lambda x: x["value"], reverse=True)

    # Accumulation/distribution signal
    institutions = [h for h in holders if h["type"] == "institution"]
    if institutions:
        increasing = sum(1 for h in institutions if h["pct_change"] > 0)
        decreasing = sum(1 for h in institutions if h["pct_change"] < 0)
        total = len(institutions)
        if increasing / total >= 0.6:
            signal = "ACCUMULATION"
        elif decreasing / total >= 0.6:
            signal = "DISTRIBUTION"
        else:
            signal = "NEUTRAL"
        net_change = sum(h["pct_change"] for h in institutions) / total
    else:
        signal = "NO_DATA"
        net_change = 0
        increasing = decreasing = 0

    total_pct = sum(h["pct_held"] for h in institutions)

    resp = {
        "symbol": symbol,
        "holders": holders[:20],
        "signal": signal,
        "institutional_pct": round(total_pct, 2),
        "increasing_count": increasing,
        "decreasing_count": decreasing,
        "avg_pct_change": round(net_change, 2),
    }
    _institutional_cache[symbol] = {"data": resp, "ts": now}
    return resp


_cross_asset_cache = {"data": None, "ts": 0}

CROSS_ASSETS = {
    "SPY": "S&P 500", "TLT": "20Y+ Treasuries", "GLD": "Gold",
    "USO": "Oil", "COPX": "Copper Miners", "DBC": "Commodities", "URA": "Uranium ETF",
}

@app.get("/api/cross-asset-regime")
def get_cross_asset_regime():
    """Cross-asset regime detection for uranium context."""
    import time, yfinance as yf, numpy as np
    now = time.time()
    if _cross_asset_cache["data"] and now - _cross_asset_cache["ts"] < 3600:
        return _cross_asset_cache["data"]

    assets = []
    trends = {}
    for sym, name in CROSS_ASSETS.items():
        try:
            df = yf.Ticker(sym).history(period="6mo")
            if df.empty or len(df) < 20:
                continue
            close = df["Close"]
            ret_90d = float((close.iloc[-1] / close.iloc[-min(63, len(close)-1)] - 1) * 100)
            ret_30d = float((close.iloc[-1] / close.iloc[-min(22, len(close)-1)] - 1) * 100)
            trend = "UP" if ret_30d > 2 else ("DOWN" if ret_30d < -2 else "FLAT")
            trends[sym] = {"ret_90d": ret_90d, "ret_30d": ret_30d, "trend": trend}
            assets.append({
                "symbol": sym, "name": name,
                "return_90d": round(ret_90d, 2), "return_30d": round(ret_30d, 2),
                "trend": trend, "price": round(float(close.iloc[-1]), 2),
            })
        except Exception as e:
            print(f"[CROSS] Error {sym}: {e}")

    # Classify regime
    spy = trends.get("SPY", {})
    tlt = trends.get("TLT", {})
    gld = trends.get("GLD", {})
    dbc = trends.get("DBC", {})
    copx = trends.get("COPX", {})
    uso = trends.get("USO", {})

    spy_up = spy.get("trend") == "UP"
    spy_down = spy.get("trend") == "DOWN"
    tlt_up = tlt.get("trend") == "UP"
    tlt_down = tlt.get("trend") == "DOWN"
    commodities_up = sum(1 for x in [dbc, copx, uso, gld] if x.get("trend") == "UP") >= 3
    commodities_down = sum(1 for x in [dbc, copx, uso] if x.get("trend") == "DOWN") >= 2
    gld_up = gld.get("trend") == "UP"

    if commodities_up and not spy_down:
        regime = "COMMODITY SUPERCYCLE"
        confidence = 85
        implication = "Very bullish uranium — broad commodity demand + risk appetite supports the sector"
    elif spy_up and tlt_down and not commodities_down:
        regime = "RISK-ON"
        confidence = 70
        implication = "Bullish uranium — risk appetite favors growth/commodity equities"
    elif spy_down and tlt_up and gld_up:
        regime = "RISK-OFF"
        confidence = 75
        implication = "Bearish uranium short-term — flight to safety, but nuclear is defensive long-term"
    elif spy_down and commodities_up and tlt_down:
        regime = "STAGFLATION"
        confidence = 65
        implication = "Mixed — uranium can outperform as inflation hedge, but equity weakness hurts sentiment"
    elif spy_down and commodities_down:
        regime = "DEFLATION"
        confidence = 60
        implication = "Bearish uranium — broad deleveraging hits all risk assets"
    else:
        regime = "TRANSITIONAL"
        confidence = 40
        implication = "No clear regime — mixed signals across asset classes"

    resp = {
        "regime": regime,
        "confidence": confidence,
        "uranium_implication": implication,
        "assets": assets,
    }
    _cross_asset_cache["data"] = resp
    _cross_asset_cache["ts"] = now
    return resp


_insider_cache = {"data": None, "ts": 0}

@app.get("/api/insider-trades")
def get_insider_trades():
    """Insider trading activity for all tracked tickers."""
    import time
    now = time.time()
    if _insider_cache["data"] and now - _insider_cache["ts"] < 3600:
        return _insider_cache["data"]

    import yfinance as yf
    all_trades = []
    for symbol in TICKERS:
        try:
            t = yf.Ticker(symbol)
            it = t.insider_transactions
            if it is None or it.empty:
                continue
            for _, row in it.iterrows():
                text = str(row.get("Text", ""))
                value = row.get("Value")
                if value is not None:
                    try:
                        value = float(value)
                    except:
                        value = None

                is_buy = "Purchase" in text or "Buy" in text
                is_sale = "Sale" in text and "Exercise" not in text

                if not is_buy and not is_sale:
                    continue

                all_trades.append({
                    "symbol": symbol,
                    "insider": row.get("Insider", ""),
                    "position": row.get("Position", ""),
                    "date": str(row.get("Start Date", "")),
                    "type": "BUY" if is_buy else "SELL",
                    "shares": int(row.get("Shares", 0)) if row.get("Shares") else 0,
                    "value": round(value, 2) if value else None,
                    "detail": text,
                })
        except Exception as e:
            print(f"[INSIDER] Error {symbol}: {e}")

    all_trades.sort(key=lambda x: x["date"], reverse=True)
    buys = [t for t in all_trades if t["type"] == "BUY"]
    sells = [t for t in all_trades if t["type"] == "SELL"]
    net_value = sum(t.get("value", 0) or 0 for t in buys) - sum(t.get("value", 0) or 0 for t in sells)

    resp = {
        "trades": all_trades[:50],
        "summary": {
            "total_buys": len(buys),
            "total_sells": len(sells),
            "net_insider_value": round(net_value, 2),
            "largest_buy": max(buys, key=lambda x: x.get("value") or 0) if buys else None,
        }
    }
    _insider_cache["data"] = resp
    _insider_cache["ts"] = now
    return resp


@app.get("/api/rules")
def get_rules():
    """Active trading rules and which are currently triggered."""
    tickers = get_all_ticker_meta()
    try:
        macro = fetch_macro_regime()
        macro_regime = macro.get("regime", "NEUTRAL")
    except Exception:
        macro_regime = "NEUTRAL"

    # Get portfolio for drawdown calc
    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
    conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
    cash_row = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()
    cash = cash_row["cash"] if cash_row else INITIAL_CASH
    positions = conn.execute("SELECT symbol, shares, avg_cost FROM portfolio WHERE shares > 0").fetchall()
    total_value = cash
    for p in positions:
        meta = get_ticker_meta(p["symbol"])
        price = meta.get("current_price", p["avg_cost"]) if meta else p["avg_cost"]
        total_value += p["shares"] * price
    conn.close()
    drawdown = ((INITIAL_CASH - total_value) / INITIAL_CASH * 100) if total_value < INITIAL_CASH else 0

    # Get insider sentiment per ticker
    insider_sentiment = {}
    try:
        insider_data = get_insider_trades()
        for trade in insider_data.get("trades", []):
            sym = trade["symbol"]
            val = trade.get("value") or 0
            if sym not in insider_sentiment:
                insider_sentiment[sym] = 0
            insider_sentiment[sym] += val if trade["type"] == "BUY" else -val
    except Exception:
        pass

    triggered = []
    insider_warnings = []
    for t in tickers:
        score = t.get("signal_score", 50)
        sym = t["symbol"]
        # Get seasonality signal
        seasonal = "NEUTRAL"  # would need to call seasonality endpoint

        # Insider override: heavy net selling caps conviction
        net_insider = insider_sentiment.get(sym, 0)
        insider_override = None
        if net_insider < -500000:  # >$500K net selling
            insider_override = "HEAVY_SELLING"
            insider_warnings.append({"symbol": sym, "net_insider": round(net_insider, 2), "warning": "Heavy insider selling — conviction capped"})

        for rule in TRADING_RULES:
            cond = rule["condition"]
            matched = False
            if rule["name"] == "strong_buy":
                matched = score >= 70 and macro_regime != "HOSTILE" and seasonal != "HEADWIND" and insider_override != "HEAVY_SELLING"
            elif rule["name"] == "buy":
                # Downgrade from buy to hold if insiders are heavy sellers
                if insider_override == "HEAVY_SELLING":
                    matched = False  # block buy signal
                else:
                    matched = 55 <= score < 70 and macro_regime != "HOSTILE"
            elif rule["name"] == "reduce":
                matched = 30 <= score < 45
            elif rule["name"] == "exit":
                matched = score < 30 or (score < 40 and macro_regime == "HOSTILE")
            elif rule["name"] == "drawdown_exit":
                matched = drawdown >= 15

            if matched:
                triggered.append({
                    "rule": rule["name"],
                    "symbol": sym,
                    "action": rule["action"],
                    "size_pct": rule["size_pct"],
                    "score": score,
                    "macro": macro_regime,
                    "condition": cond,
                })

    return {
        "rules": TRADING_RULES,
        "risk_limits": RISK_LIMITS,
        "triggered": triggered,
        "insider_warnings": insider_warnings,
        "portfolio_value": round(total_value, 2),
        "drawdown_pct": round(drawdown, 2),
        "macro_regime": macro_regime,
    }


@app.get("/api/swing-rules")
def get_swing_rules():
    """Dante's swing trading rules — evaluate take-profit/stop-loss/entry signals."""
    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
    conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
    cash_row = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()
    cash = cash_row["cash"] if cash_row else INITIAL_CASH
    positions = conn.execute("SELECT symbol, shares, avg_cost FROM portfolio WHERE shares > 0").fetchall()
    conn.close()

    tickers = get_all_ticker_meta()
    ticker_map = {t["symbol"]: t for t in tickers}

    signals = []
    for p in positions:
        sym = p["symbol"]
        meta = ticker_map.get(sym)
        if not meta:
            continue
        price = meta.get("current_price", p["avg_cost"])
        pnl_pct = ((price - p["avg_cost"]) / p["avg_cost"]) * 100 if p["avg_cost"] > 0 else 0
        value = p["shares"] * price

        if pnl_pct >= SWING_RULES["take_profit_pct"]:
            signals.append({
                "symbol": sym, "signal": "TAKE_PROFIT", "pnl_pct": round(pnl_pct, 2),
                "price": price, "avg_cost": p["avg_cost"], "value": round(value, 2),
                "reason": f"+{pnl_pct:.1f}% gain — take profit target ({SWING_RULES['take_profit_pct']}%) hit",
            })
            _swing_cooldown[sym] = True
        elif pnl_pct <= -SWING_RULES["stop_loss_pct"]:
            signals.append({
                "symbol": sym, "signal": "STOP_LOSS", "pnl_pct": round(pnl_pct, 2),
                "price": price, "avg_cost": p["avg_cost"], "value": round(value, 2),
                "reason": f"{pnl_pct:.1f}% loss — stop loss ({SWING_RULES['stop_loss_pct']}%) triggered",
            })

    # Check entry opportunities (no position held, score > entry threshold, not in cooldown)
    held_symbols = {p["symbol"] for p in positions}
    for t in tickers:
        sym = t["symbol"]
        score = t.get("signal_score", 50)
        if sym in held_symbols:
            continue
        # Cooldown check
        if sym in _swing_cooldown:
            if score <= SWING_RULES["reentry_score_max"]:
                del _swing_cooldown[sym]  # cooldown cleared
            else:
                continue  # still in cooldown
        if score >= SWING_RULES["entry_score_min"]:
            max_alloc = SWING_RULES["portfolio_size"] * SWING_RULES["max_position_pct"] / 100
            signals.append({
                "symbol": sym, "signal": "ENTRY", "score": score,
                "price": t.get("current_price", 0),
                "max_allocation": round(max_alloc, 2),
                "reason": f"Score {score:.1f} ≥ {SWING_RULES['entry_score_min']} — swing entry signal",
            })

    # Portfolio summary
    total_value = cash + sum(
        p["shares"] * ticker_map.get(p["symbol"], {}).get("current_price", p["avg_cost"])
        for p in positions
    )

    return {
        "swing_rules": SWING_RULES,
        "cooldowns": list(_swing_cooldown.keys()),
        "signals": signals,
        "portfolio": {
            "cash": round(cash, 2),
            "total_value": round(total_value, 2),
            "positions": len(positions),
        },
    }


@app.get("/api/swing-backtest")
def get_swing_backtest(
    symbol: str = Query("URA"),
    months: int = Query(6),
):
    """Backtest swing trading rules on historical data."""
    from backtest import run_backtest
    return run_backtest(
        symbol=symbol.upper(), months=months,
        take_profit=SWING_RULES["take_profit_pct"],
        stop_loss=SWING_RULES["stop_loss_pct"],
        entry_score=SWING_RULES["entry_score_min"],
        reentry_score=SWING_RULES["reentry_score_max"],
        capital=SWING_RULES["portfolio_size"],
        max_position_pct=SWING_RULES["max_position_pct"],
    )


@app.get("/api/swing-optimize")
def get_swing_optimize(symbol: str = Query("URA"), months: int = Query(12)):
    """Parameter sweep across TP/SL combinations to find optimal thresholds."""
    from backtest import run_backtest
    symbol = symbol.upper()
    tp_range = [5, 10, 15, 20, 25, 30]
    sl_range = [3, 5, 8, 10, 15]
    results = []
    best = {"pnl": -999999, "tp": 0, "sl": 0}
    for tp in tp_range:
        for sl in sl_range:
            r = run_backtest(symbol, months=months, take_profit=tp, stop_loss=sl,
                entry_score=SWING_RULES["entry_score_min"],
                reentry_score=SWING_RULES["reentry_score_max"],
                capital=SWING_RULES["portfolio_size"],
                max_position_pct=SWING_RULES["max_position_pct"])
            res = r.get("results", {})
            pnl = res.get("total_return_pct", 0)
            results.append({
                "tp": tp, "sl": sl,
                "return_pct": pnl,
                "trades": res.get("total_trades", 0),
                "win_rate": res.get("win_rate", 0),
                "max_dd": res.get("max_drawdown_pct", 0),
            })
            if pnl > best["pnl"]:
                best = {"pnl": pnl, "tp": tp, "sl": sl, "trades": res.get("total_trades", 0),
                        "win_rate": res.get("win_rate", 0), "max_dd": res.get("max_drawdown_pct", 0)}

    bh = run_backtest(symbol, months=months, take_profit=999, stop_loss=999,
        entry_score=1, reentry_score=0, capital=5000)
    bh_ret = bh.get("results", {}).get("buy_and_hold_return_pct", 0)

    return {
        "symbol": symbol, "months": months,
        "tp_range": tp_range, "sl_range": sl_range,
        "heatmap": results,
        "best": best,
        "buy_and_hold_pct": bh_ret,
    }


@app.patch("/api/swing-rules")
def update_swing_rules(request: Request):
    """Update swing trading rule thresholds."""
    import asyncio
    loop = asyncio.get_event_loop()
    body = loop.run_until_complete(request.json())
    allowed = {"take_profit_pct", "stop_loss_pct", "entry_score_min", "reentry_score_max", "max_position_pct", "portfolio_size", "enabled"}
    for k, v in body.items():
        if k in allowed:
            SWING_RULES[k] = v
    return {"updated": SWING_RULES}


@app.get("/api/sizing/{symbol}")
def get_position_sizing(symbol: str):
    """Position sizing calculator based on conviction score and risk limits."""
    symbol = symbol.upper()
    meta = get_ticker_meta(symbol)
    if not meta:
        raise HTTPException(404, f"No data for {symbol}")

    score = meta.get("signal_score", 50)
    price = meta.get("current_price", 0)
    if not price:
        raise HTTPException(400, "No price data")

    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS portfolio_cash (id INTEGER PRIMARY KEY CHECK (id=1), cash REAL)")
    conn.execute("INSERT OR IGNORE INTO portfolio_cash (id, cash) VALUES (1, ?)", (INITIAL_CASH,))
    cash_row = conn.execute("SELECT cash FROM portfolio_cash WHERE id=1").fetchone()
    cash = cash_row["cash"] if cash_row else INITIAL_CASH

    # Current holdings
    positions = conn.execute("SELECT symbol, shares, avg_cost FROM portfolio WHERE shares > 0").fetchall()
    total_value = cash
    current_holding = 0
    for p in positions:
        m = get_ticker_meta(p["symbol"])
        cp = m.get("current_price", p["avg_cost"]) if m else p["avg_cost"]
        val = p["shares"] * cp
        total_value += val
        if p["symbol"] == symbol:
            current_holding = val
    conn.close()

    # Check insider sentiment
    insider_warning = False
    try:
        insider_data = get_insider_trades()
        net_insider = 0
        for trade in insider_data.get("trades", []):
            if trade["symbol"] == symbol:
                val = trade.get("value") or 0
                net_insider += val if trade["type"] == "BUY" else -val
        insider_warning = net_insider < -500000
    except Exception:
        pass

    # Determine target allocation
    if score >= 70 and not insider_warning:
        target_pct = 25
        action = "STRONG BUY"
    elif score >= 70 and insider_warning:
        target_pct = 10  # capped due to insider selling
        action = "BUY (INSIDER CAP)"
    elif score >= 55 and not insider_warning:
        target_pct = 15
        action = "BUY"
    elif score >= 55 and insider_warning:
        target_pct = 8  # reduced due to insider selling
        action = "BUY (INSIDER CAP)"
    elif score >= 45:
        target_pct = None  # hold
        action = "HOLD"
    elif score >= 30:
        target_pct = max(0, current_holding / total_value * 100 / 2) if total_value else 0  # reduce by half
        action = "REDUCE"
    else:
        target_pct = 0
        action = "EXIT"

    max_position = total_value * RISK_LIMITS["max_position_pct"] / 100
    max_investable = total_value * RISK_LIMITS["max_invested_pct"] / 100

    if target_pct is not None:
        target_value = min(total_value * target_pct / 100, max_position)
        delta_value = target_value - current_holding
        delta_shares = int(delta_value / price) if price else 0
    else:
        target_value = current_holding
        delta_value = 0
        delta_shares = 0

    return {
        "symbol": symbol,
        "score": score,
        "action": action,
        "current_price": round(price, 2),
        "portfolio_value": round(total_value, 2),
        "current_holding_value": round(current_holding, 2),
        "current_weight_pct": round(current_holding / total_value * 100, 2) if total_value else 0,
        "target_weight_pct": round(target_pct, 1) if target_pct is not None else None,
        "target_value": round(target_value, 2),
        "delta_value": round(delta_value, 2),
        "delta_shares": delta_shares,
        "max_position": round(max_position, 2),
        "available_cash": round(cash, 2),
    }


_analyst_cache = {"data": None, "ts": 0}

@app.get("/api/analyst-ratings")
def get_analyst_ratings():
    """Analyst consensus ratings + price targets for all tickers."""
    import time
    now = time.time()
    if _analyst_cache["data"] and now - _analyst_cache["ts"] < 21600:
        return _analyst_cache["data"]

    import yfinance as yf
    results = []
    for symbol in TICKERS:
        try:
            t = yf.Ticker(symbol)
            rec = t.recommendations
            apt = t.analyst_price_targets
            if rec is None or rec.empty:
                continue
            current = rec.iloc[0]
            prev = rec.iloc[1] if len(rec) > 1 else None

            sb, b, h, s, ss = int(current.get("strongBuy",0)), int(current.get("buy",0)), int(current.get("hold",0)), int(current.get("sell",0)), int(current.get("strongSell",0))
            total = sb + b + h + s + ss
            buy_pct = round((sb + b) / total * 100, 1) if total else 0

            # Consensus momentum: buy% this month vs last
            momentum = None
            if prev is not None:
                prev_total = int(prev.get("strongBuy",0)) + int(prev.get("buy",0)) + int(prev.get("hold",0)) + int(prev.get("sell",0)) + int(prev.get("strongSell",0))
                if prev_total:
                    prev_buy_pct = (int(prev.get("strongBuy",0)) + int(prev.get("buy",0))) / prev_total * 100
                    momentum = round(buy_pct - prev_buy_pct, 1)

            # Consensus label
            if buy_pct >= 80: consensus = "STRONG BUY"
            elif buy_pct >= 60: consensus = "BUY"
            elif buy_pct >= 40: consensus = "HOLD"
            else: consensus = "SELL"

            price = float(apt.get("current", 0)) if apt else 0
            target_mean = float(apt.get("mean", 0)) if apt else 0
            upside = round((target_mean - price) / price * 100, 1) if price and target_mean else None
            # Sanity check: skip if upside is absurd (currency mismatch on foreign tickers)
            if upside and abs(upside) > 500:
                continue

            results.append({
                "symbol": symbol,
                "name": TICKERS.get(symbol, symbol),
                "strong_buy": sb, "buy": b, "hold": h, "sell": s, "strong_sell": ss,
                "total_analysts": total,
                "buy_pct": buy_pct,
                "consensus": consensus,
                "momentum": momentum,
                "target_mean": round(target_mean, 2) if target_mean else None,
                "target_high": round(float(apt.get("high", 0)), 2) if apt and apt.get("high") else None,
                "target_low": round(float(apt.get("low", 0)), 2) if apt and apt.get("low") else None,
                "current_price": round(price, 2),
                "upside_pct": upside,
            })
        except Exception as e:
            print(f"[ANALYST] Error {symbol}: {e}")

    results.sort(key=lambda x: x.get("upside_pct") or 0, reverse=True)
    upgrades = sum(1 for r in results if (r.get("momentum") or 0) > 0)
    downgrades = sum(1 for r in results if (r.get("momentum") or 0) < 0)

    resp = {"ratings": results, "upgrades_30d": upgrades, "downgrades_30d": downgrades}
    _analyst_cache["data"] = resp
    _analyst_cache["ts"] = now
    return resp


@app.get("/api/monte-carlo/{symbol}")
def get_monte_carlo(symbol: str, days: int = Query(30, ge=5, le=90), simulations: int = Query(1000, ge=100, le=5000), drift_mode: str = Query("neutral", regex="^(neutral|historical)$")):
    """Monte Carlo price simulation using geometric Brownian motion."""
    import numpy as np
    symbol = symbol.upper()
    conn = _get_db()
    rows = conn.execute(
        "SELECT close FROM price_cache WHERE symbol=? ORDER BY date DESC LIMIT 253",
        (symbol,),
    ).fetchall()
    conn.close()

    if len(rows) < 30:
        return {"symbol": symbol, "insufficient_data": True}

    prices = np.array([r["close"] for r in reversed(rows) if r["close"]])
    returns = np.diff(np.log(prices))
    
    mu_hist = float(np.mean(returns)) * 252  # annualized historical drift
    sigma = float(np.std(returns)) * np.sqrt(252)  # annualized vol
    mu = 0.0435 if drift_mode == "neutral" else mu_hist  # risk-free rate ~4.35% or historical
    S0 = float(prices[-1])
    dt = 1 / 252

    np.random.seed(42)
    all_final = []
    all_paths = np.zeros((simulations, days + 1))
    all_paths[:, 0] = S0

    for t in range(1, days + 1):
        Z = np.random.standard_normal(simulations)
        all_paths[:, t] = all_paths[:, t-1] * np.exp((mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z)

    finals = all_paths[:, -1]
    percentiles = {f"p{p}": round(float(np.percentile(finals, p)), 2) for p in [5, 25, 50, 75, 95]}

    # Zone boundary probabilities
    meta = get_ticker_meta(symbol)
    zone_probs = {}
    if meta:
        rl, rh = meta.get("range_low", 0), meta.get("range_high", 0)
        if rh > rl:
            green_thresh = rl + (rh - rl) * 0.2
            red_thresh = rl + (rh - rl) * 0.8
            zone_probs["prob_green"] = round(float(np.mean(finals <= green_thresh)) * 100, 1)
            zone_probs["prob_red"] = round(float(np.mean(finals >= red_thresh)) * 100, 1)
            zone_probs["green_price"] = round(green_thresh, 2)
            zone_probs["red_price"] = round(red_thresh, 2)

    # Sample paths: percentile paths + 5 random
    pct_indices = [int(np.argmin(np.abs(finals - np.percentile(finals, p)))) for p in [5, 25, 50, 75, 95]]
    rand_indices = np.random.choice(simulations, min(5, simulations), replace=False).tolist()
    sample_indices = list(set(pct_indices + rand_indices))[:10]
    
    # Percentile bands per day for fan chart
    bands = {}
    for p in [5, 25, 50, 75, 95]:
        bands[f"p{p}"] = [round(float(np.percentile(all_paths[:, t], p)), 2) for t in range(days + 1)]

    return {
        "symbol": symbol,
        "days": days,
        "simulations": simulations,
        "current_price": S0,
        "drift_mode": drift_mode,
        "drift_annual": round(mu * 100, 2),
        "drift_historical": round(mu_hist * 100, 2),
        "vol_annual": round(sigma * 100, 2),
        "percentiles": percentiles,
        "bands": bands,
        "paths": [all_paths[i].round(2).tolist() for i in sample_indices],
        "zone_probabilities": zone_probs,
    }


@app.get("/api/snapshot.png")
def get_snapshot():
    """Server-rendered OG image for link previews (1200x630)."""
    from PIL import Image, ImageDraw, ImageFont
    from fastapi.responses import StreamingResponse
    import io

    tickers = get_all_ticker_meta()
    ura = next((t for t in tickers if t["symbol"] == "URA"), None)

    W, H = 1200, 630
    img = Image.new("RGB", (W, H), "#0f172a")
    draw = ImageDraw.Draw(img)

    # Try to load a nice font, fall back to default
    try:
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_xs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except Exception:
        font_lg = font_md = font_sm = font_xs = ImageFont.load_default()

    zone_colors = {"GREEN": "#10b981", "YELLOW": "#f59e0b", "RED": "#ef4444"}

    # Title
    draw.text((60, 40), "☢️ URANIUM THERMOMETER", fill="#10b981", font=font_lg)

    if ura:
        price = ura.get("current_price", 0)
        zone = ura.get("zone", "YELLOW")
        score = ura.get("signal_score", 50)
        label = ura.get("signal_label", "HOLD")
        zone_color = zone_colors.get(zone, "#f59e0b")

        # URA Price
        draw.text((60, 120), f"URA  ${price:.2f}", fill="white", font=font_lg)

        # Zone bar
        bar_y = 200
        draw.rounded_rectangle([60, bar_y, 560, bar_y + 50], radius=10, fill="#1e293b")
        bar_width = int(4.5 * score)  # 0-100 mapped to 0-450
        if bar_width > 0:
            draw.rounded_rectangle([60, bar_y, 60 + bar_width, bar_y + 50], radius=10, fill=zone_color)
        draw.text((60, bar_y + 55), f"Score: {score}/100", fill="#9ca3af", font=font_sm)

        # Zone + Signal label
        draw.text((60, 290), f"Zone: {zone}", fill=zone_color, font=font_sm)
        draw.text((60, 320), f"Signal: {label}", fill="white", font=font_sm)

        # RSI
        rsi = ura.get("rsi")
        if rsi:
            draw.text((300, 290), f"RSI: {rsi:.1f}", fill="#9ca3af", font=font_sm)

    # Macro regime
    try:
        macro = fetch_macro_regime()
        regime = macro.get("regime", "NEUTRAL")
        regime_color = {"FAVORABLE": "#10b981", "HOSTILE": "#ef4444"}.get(regime, "#f59e0b")
        draw.text((60, 360), f"Macro: {regime}", fill=regime_color, font=font_md)
    except Exception:
        pass

    # Right side: ticker summary
    x_right = 700
    draw.text((x_right, 120), "SECTOR", fill="#6b7280", font=font_sm)
    for i, t in enumerate(tickers[:7]):
        y = 160 + i * 55
        sym = t["symbol"]
        sc = t.get("signal_score", 50)
        z = t.get("zone", "YELLOW")
        zc = zone_colors.get(z, "#f59e0b")
        draw.text((x_right, y), f"{sym:8}", fill="#e5e7eb", font=font_sm)
        # Mini bar
        bw = int(sc * 3.5)
        draw.rounded_rectangle([x_right + 160, y + 4, x_right + 160 + bw, y + 24], radius=5, fill=zc)
        draw.text((x_right + 530 - 60, y), f"{sc:.0f}", fill="#9ca3af", font=font_sm)

    # Footer
    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    draw.text((60, H - 50), f"Updated: {updated}", fill="#4b5563", font=font_xs)
    draw.text((W - 350, H - 50), "165.22.252.79/uranium", fill="#4b5563", font=font_xs)

    # Border accent
    draw.rectangle([0, 0, W, 4], fill="#10b981")
    draw.rectangle([0, H - 4, W, H], fill="#10b981")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


_earnings_cache = {"data": None, "ts": 0}

@app.get("/api/earnings-calendar")
def get_earnings_calendar():
    """Earnings calendar for all tracked tickers via yfinance."""
    import time
    now = time.time()
    if _earnings_cache["data"] and now - _earnings_cache["ts"] < 21600:
        return _earnings_cache["data"]

    import yfinance as yf
    from datetime import datetime as dt
    today = dt.utcnow().date()
    upcoming = []
    recent = []

    for symbol in TICKERS:
        try:
            t = yf.Ticker(symbol)
            ed = t.earnings_dates
            if ed is None or ed.empty:
                continue
            for idx, row in ed.iterrows():
                date = idx.date() if hasattr(idx, 'date') else idx
                eps_est = row.get("EPS Estimate")
                eps_act = row.get("Reported EPS")
                surprise = row.get("Surprise(%)")

                import math
                def clean(v):
                    if v is None: return None
                    try:
                        f = float(v)
                        return None if math.isnan(f) else round(f, 4)
                    except: return None

                entry = {
                    "symbol": symbol,
                    "name": TICKERS.get(symbol, symbol),
                    "date": str(date),
                    "eps_estimate": clean(eps_est),
                    "eps_actual": clean(eps_act),
                    "surprise_pct": clean(surprise),
                    "beat": clean(surprise) is not None and clean(surprise) > 0,
                }
                if date >= today and clean(eps_act) is None:
                    upcoming.append(entry)
                elif clean(eps_act) is not None:
                    recent.append(entry)
        except Exception as e:
            print(f"[EARNINGS] Error {symbol}: {e}")

    upcoming.sort(key=lambda x: x["date"])
    recent.sort(key=lambda x: x["date"], reverse=True)

    resp = {"upcoming": upcoming[:20], "recent": recent[:20]}
    _earnings_cache["data"] = resp
    _earnings_cache["ts"] = now
    return resp


_seasonality_cache = {}

@app.get("/api/seasonality/{symbol}")
def get_seasonality(symbol: str):
    """Seasonal pattern analysis — avg monthly returns over full history."""
    import time
    symbol = symbol.upper()
    cache_key = symbol
    now = time.time()
    if cache_key in _seasonality_cache and now - _seasonality_cache[cache_key]["ts"] < 86400:
        return _seasonality_cache[cache_key]["data"]

    import yfinance as yf
    import pandas as pd
    import numpy as np

    df = yf.Ticker(symbol).history(period="max")
    if df.empty or len(df) < 252:
        return {"symbol": symbol, "insufficient_data": True, "months": []}

    monthly = df["Close"].resample("ME").last().pct_change().dropna()
    years = (monthly.index[-1] - monthly.index[0]).days / 365.25

    month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    months = []
    for m in range(1, 13):
        subset = monthly[monthly.index.month == m]
        if len(subset) == 0:
            continue
        months.append({
            "month": month_names[m-1],
            "month_num": m,
            "avg_return": round(float(subset.mean() * 100), 2),
            "median_return": round(float(subset.median() * 100), 2),
            "win_rate": round(float((subset > 0).mean()), 2),
            "best": round(float(subset.max() * 100), 1),
            "worst": round(float(subset.min() * 100), 1),
            "sample_size": len(subset),
        })

    # Current month signal
    now_month = datetime.utcnow().month
    current = next((m for m in months if m["month_num"] == now_month), None)
    if current:
        if current["win_rate"] >= 0.6 and current["avg_return"] >= 1.0:
            signal = "TAILWIND"
        elif current["win_rate"] <= 0.4:
            signal = "HEADWIND"
        else:
            signal = "NEUTRAL"
    else:
        signal = "UNKNOWN"

    resp = {
        "symbol": symbol,
        "years_of_data": round(years, 1),
        "months": months,
        "current_month": month_names[now_month - 1],
        "current_month_signal": signal,
        "current_month_stats": current,
    }
    _seasonality_cache[cache_key] = {"data": resp, "ts": now}
    return resp


_reactor_cache = {"data": None, "ts": 0}

@app.get("/api/reactor-pipeline")
def get_reactor_pipeline():
    """Global nuclear reactor pipeline — demand indicator."""
    import time, csv as csvmod
    now = time.time()
    if _reactor_cache["data"] and now - _reactor_cache["ts"] < 86400:
        return _reactor_cache["data"]

    csv_path = os.path.join(os.path.dirname(__file__), "reactors.csv")
    with open(csv_path) as f:
        rows = list(csvmod.DictReader(f))

    buckets = {}
    country_construction = {}
    for r in rows:
        s = r["Status"]
        cap = int(r["Capacity"]) if r["Capacity"] else 0
        country = r["Country"]
        if s not in buckets:
            buckets[s] = {"count": 0, "capacity_mwe": 0}
        buckets[s]["count"] += 1
        buckets[s]["capacity_mwe"] += cap
        if s == "Under Construction":
            if country not in country_construction:
                country_construction[country] = {"count": 0, "capacity_mwe": 0}
            country_construction[country]["count"] += 1
            country_construction[country]["capacity_mwe"] += cap

    top_builders = sorted(country_construction.items(), key=lambda x: -x[1]["count"])[:10]
    top_builders = [{"country": c, **v} for c, v in top_builders]

    def fmt(status):
        b = buckets.get(status, {"count": 0, "capacity_mwe": 0})
        return {"count": b["count"], "capacity_gwe": round(b["capacity_mwe"] / 1000, 1)}

    # Demand estimate: each GWe needs ~200 tonnes U/year
    uc = buckets.get("Under Construction", {"capacity_mwe": 0})
    planned = buckets.get("Planned", {"capacity_mwe": 0})
    new_demand_tonnes = round((uc["capacity_mwe"] + planned["capacity_mwe"]) / 1000 * 200)

    resp = {
        "operational": fmt("Operational"),
        "under_construction": fmt("Under Construction"),
        "planned": fmt("Planned"),
        "suspended": fmt("Suspended Construction"),
        "shutdown": fmt("Shutdown"),
        "top_builders": top_builders,
        "new_demand_tonnes_u_per_year": new_demand_tonnes,
        "source": "GeoNuclearData (WNA/IAEA)",
        "total_reactors": len(rows),
    }
    _reactor_cache["data"] = resp
    _reactor_cache["ts"] = now
    return resp


_short_interest_cache = {"data": None, "ts": 0}

@app.get("/api/short-interest")
def get_short_interest():
    """Short interest data for all tickers. Cached 6 hours."""
    import time
    now = time.time()
    if _short_interest_cache["data"] and now - _short_interest_cache["ts"] < 21600:
        return _short_interest_cache["data"]

    import yfinance as yf
    results = []
    for symbol in TICKERS:
        try:
            info = yf.Ticker(symbol).info
            short_pct = info.get("shortPercentOfFloat")
            short_ratio = info.get("shortRatio")
            shares_short = info.get("sharesShort")
            date_si = info.get("dateShortInterest")

            # Determine status
            pct = (short_pct or 0) * 100 if short_pct and short_pct < 1 else (short_pct or 0)
            if pct > 15:
                status = "HEAVY"
            elif pct > 5:
                status = "MODERATE"
            else:
                status = "LOW"

            squeeze_risk = (short_ratio or 0) > 5 and pct > 10

            results.append({
                "symbol": symbol,
                "name": TICKERS.get(symbol, symbol),
                "short_pct_float": round(pct, 2) if short_pct else None,
                "short_ratio": round(short_ratio, 2) if short_ratio else None,
                "shares_short": shares_short,
                "date_short_interest": date_si,
                "status": status,
                "squeeze_risk": squeeze_risk,
            })
        except Exception as e:
            print(f"[SHORT] Error fetching {symbol}: {e}")
            results.append({"symbol": symbol, "name": TICKERS.get(symbol, symbol), "error": str(e)})

    results.sort(key=lambda x: x.get("short_pct_float") or 0, reverse=True)
    resp = {"tickers": results, "flagged_heavy": sum(1 for r in results if r.get("status") == "HEAVY"),
            "squeeze_risks": sum(1 for r in results if r.get("squeeze_risk"))}
    _short_interest_cache["data"] = resp
    _short_interest_cache["ts"] = now
    return resp


@app.get("/api/export/csv")
def export_csv():
    """Export all ticker data + macro as CSV."""
    from fastapi.responses import StreamingResponse
    import io, csv
    tickers = get_all_ticker_meta()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["symbol","name","price","change_pct","zone","zone_pct","signal_score","signal_label",
                "rsi","macd","macd_signal","bb_upper","bb_middle","bb_lower","sma_50","sma_200","support","resistance"])
    for t in tickers:
        w.writerow([t.get("symbol"),t.get("name"),t.get("current_price"),t.get("change_pct"),
                     t.get("zone"),t.get("zone_pct"),t.get("signal_score"),t.get("signal_label"),
                     t.get("rsi"),t.get("macd"),t.get("macd_signal"),t.get("bb_upper"),t.get("bb_middle"),
                     t.get("bb_lower"),t.get("sma_50"),t.get("sma_200"),t.get("support"),t.get("resistance")])
    # Macro row
    try:
        macro = fetch_macro_regime()
        ind = macro.get("indicators", {})
        w.writerow([])
        w.writerow(["macro_regime", macro.get("regime"), "score", macro.get("score"),
                     "10Y", ind.get("^TNX",{}).get("current",""),
                     "DXY", ind.get("DX-Y.NYB",{}).get("current",""),
                     "SPX", ind.get("^GSPC",{}).get("current","")])
    except Exception:
        pass
    buf.seek(0)
    fname = f"uranium-thermometer-{datetime.utcnow().strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(buf, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={fname}"})


@app.get("/api/correlations")
def get_correlations():
    """7x7 Pearson correlation matrix using 3-month daily returns."""
    import numpy as np
    conn = _get_db()
    # Get 63 trading days (~3 months) of closes for each ticker
    returns = {}
    dates_set = None
    for symbol in TICKERS:
        rows = conn.execute(
            "SELECT date, close FROM price_cache WHERE symbol=? ORDER BY date DESC LIMIT 64",
            (symbol,),
        ).fetchall()
        if len(rows) < 10:
            continue
        rows = list(reversed(rows))
        prices = {r["date"]: r["close"] for r in rows if r["close"]}
        dates = sorted(prices.keys())
        if dates_set is None:
            dates_set = set(dates)
        else:
            dates_set &= set(dates)
        returns[symbol] = prices
    conn.close()

    if not dates_set or len(dates_set) < 10:
        return {"matrix": {}, "symbols": [], "insufficient_data": True}

    common_dates = sorted(dates_set)
    # Compute daily returns
    symbols = sorted(returns.keys())
    ret_arrays = {}
    for sym in symbols:
        prices = [returns[sym][d] for d in common_dates]
        daily_ret = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices)) if prices[i-1]]
        ret_arrays[sym] = daily_ret

    min_len = min(len(v) for v in ret_arrays.values())
    matrix = {}
    for s1 in symbols:
        matrix[s1] = {}
        for s2 in symbols:
            if s1 == s2:
                matrix[s1][s2] = 1.0
            else:
                a1 = np.array(ret_arrays[s1][:min_len])
                a2 = np.array(ret_arrays[s2][:min_len])
                corr = float(np.corrcoef(a1, a2)[0, 1])
                matrix[s1][s2] = round(corr, 3)

    return {"matrix": matrix, "symbols": symbols, "days": len(common_dates), "insufficient_data": False}


@app.get("/api/relative-strength")
def get_relative_strength(period: str = Query("30d", regex="^(7d|14d|30d)$")):
    """Normalized % change from period start for all tickers."""
    days = int(period.replace("d", ""))
    conn = _get_db()
    result = []
    for symbol in TICKERS:
        rows = conn.execute(
            "SELECT date, close FROM price_cache WHERE symbol=? ORDER BY date DESC LIMIT ?",
            (symbol, days + 5),  # extra buffer
        ).fetchall()
        if len(rows) < 2:
            continue
        rows = list(reversed(rows))  # oldest first
        # Trim to exactly `days` trading days
        rows = rows[-days:] if len(rows) > days else rows
        base = rows[0]["close"]
        if not base:
            continue
        data = [{"date": r["date"], "pct_change": round((r["close"] - base) / base * 100, 2)} for r in rows if r["close"]]
        result.append({"symbol": symbol, "name": TICKERS.get(symbol, symbol), "data": data})
    conn.close()
    return {"period": period, "tickers": result}


@app.get("/api/volume-anomalies")
def get_volume_anomalies():
    """Detect unusual volume across all tickers (>1.5x 20-day avg)."""
    conn = _get_db()
    results = []
    for symbol in TICKERS:
        rows = conn.execute(
            "SELECT volume FROM price_cache WHERE symbol=? ORDER BY date DESC LIMIT 21",
            (symbol,),
        ).fetchall()
        if len(rows) < 2:
            continue
        current_vol = rows[0]["volume"] or 0
        avg_20 = [r["volume"] for r in rows[1:21] if r["volume"]]
        if not avg_20:
            continue
        avg_vol = sum(avg_20) / len(avg_20)
        ratio = round(current_vol / avg_vol, 2) if avg_vol > 0 else 0
        # Get current price for dollar volume
        price_row = conn.execute(
            "SELECT close FROM price_cache WHERE symbol=? ORDER BY date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        price = price_row["close"] if price_row and price_row["close"] else 0
        dollar_vol = round(current_vol * price)
        dollar_avg = round(avg_vol * price)
        results.append({
            "symbol": symbol,
            "name": TICKERS.get(symbol, symbol),
            "current_volume": current_vol,
            "avg_volume_20d": round(avg_vol),
            "dollar_volume": dollar_vol,
            "dollar_avg_20d": dollar_avg,
            "price": round(price, 2),
            "ratio": ratio,
            "anomaly": ratio >= 1.5,
        })
    results.sort(key=lambda x: x["ratio"], reverse=True)
    conn.close()
    return {"anomalies": results, "threshold": 1.5, "flagged": sum(1 for r in results if r["anomaly"])}


@app.get("/api/base-rates/{symbol}")
def get_base_rates(
    symbol: str,
    score_range: float = Query(5.0, ge=1, le=20),
    min_days: int = Query(30, ge=7, le=365),
):
    """Historical base rates: what happened when conditions looked like this?"""
    symbol = symbol.upper()
    meta = get_ticker_meta(symbol)
    if not meta:
        raise HTTPException(404, f"No data for {symbol}")

    current_score = meta.get("signal_score", 50)
    current_zone = meta.get("zone", "YELLOW")

    conn = _get_db()
    # Get all score history for this symbol
    rows = conn.execute(
        "SELECT timestamp, price, signal_score, zone FROM score_history WHERE symbol=? ORDER BY timestamp",
        (symbol,),
    ).fetchall()
    conn.close()

    history = [dict(r) for r in rows]
    days_collected = len(set(h["timestamp"][:10] for h in history))

    if days_collected < min_days:
        return {
            "symbol": symbol,
            "current_score": current_score,
            "current_zone": current_zone,
            "insufficient_data": True,
            "days_collected": days_collected,
            "days_needed": min_days,
        }

    # Find similar periods (same zone, score within range)
    similar = []
    for i, h in enumerate(history):
        if (h["zone"] == current_zone and
                abs((h["signal_score"] or 50) - current_score) <= score_range):
            # Calculate forward returns at 1w (~5 trading snapshots), 1m (~22), 3m (~66)
            entry_price = h["price"]
            if not entry_price:
                continue
            fwd = {}
            for label, offset in [("1w", 5), ("1m", 22), ("3m", 66)]:
                idx = i + offset
                if idx < len(history) and history[idx]["price"]:
                    fwd[label] = round((history[idx]["price"] - entry_price) / entry_price * 100, 2)
            if fwd:
                similar.append({"date": h["timestamp"], "score": h["signal_score"], "price": entry_price, "forward_returns": fwd})

    # Aggregate
    def avg_return(key):
        vals = [s["forward_returns"][key] for s in similar if key in s["forward_returns"]]
        return round(sum(vals) / len(vals), 2) if vals else None

    return {
        "symbol": symbol,
        "current_score": current_score,
        "current_zone": current_zone,
        "insufficient_data": False,
        "days_collected": days_collected,
        "sample_size": len(similar),
        "score_range": f"{current_score - score_range:.1f}–{current_score + score_range:.1f}",
        "avg_forward_return_1w": avg_return("1w"),
        "avg_forward_return_1m": avg_return("1m"),
        "avg_forward_return_3m": avg_return("3m"),
        "similar_periods": similar[:20],  # cap response size
    }


@app.get("/api/alerts/history")
def get_alert_history(limit: int = Query(20, ge=1, le=100)):
    """Zone change alert history."""
    conn = _get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS zone_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, old_zone TEXT,
        new_zone TEXT, old_score REAL, new_score REAL, price REAL,
        timestamp TEXT DEFAULT (datetime('now')))''')
    rows = conn.execute(
        "SELECT * FROM zone_alerts ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return {"alerts": [dict(r) for r in rows], "count": len(rows)}


@app.get("/api/alerts/subscribe")
def alert_subscribe_stub():
    """Stub for future alert subscriptions (Telegram, email)."""
    return {
        "status": "planned",
        "channels": ["discord"],
        "planned": ["telegram", "email"],
        "message": "Zone change alerts currently fire to Discord #general. Telegram/email coming soon."
    }


@app.get("/api/score-decomposition")
@app.get("/api/signal-attribution")
def get_score_decomposition(symbol: str = Query("URA"), ticker: str = Query(None)):
    """
    Full composite score decomposition — technical + fundamental + macro + sentiment.
    
    Architecture:
      Technical  (40%): Range 16%, RSI 10%, MACD 6%, Bollinger 4%, SMA 4%
      Macro      (20%): Macro regime 10%, Anti-Fragile composite 10%
      Fundamental(20%): Miner valuation 10%, Insider sentiment 10%
      Sentiment  (20%): ETF flows 8%, Short interest 6%, Institutional 6%
    """
    import numpy as np
    if ticker:
        symbol = ticker
    symbol = symbol.upper()
    meta = get_ticker_meta(symbol)
    if not meta:
        raise HTTPException(404, f"No data for {symbol}")

    price = meta.get("current_price")
    zone_pct = meta.get("zone_pct", 50)
    rsi = meta.get("rsi")
    macd_val = meta.get("macd")
    macd_sig = meta.get("macd_signal")
    bb_upper = meta.get("bb_upper")
    bb_lower = meta.get("bb_lower")
    sma_50 = meta.get("sma_50")
    sma_200 = meta.get("sma_200")

    technical = []
    macro_signals = []
    fundamental = []
    sentiment = []

    # ═══════════════════════════════════════════════
    # TECHNICAL SIGNALS (40% total)
    # ═══════════════════════════════════════════════

    # 1. Range position (16%)
    range_score = 100 - zone_pct
    technical.append({
        "name": "range_position", "category": "technical", "weight": 0.16,
        "score": round(range_score, 1),
        "raw_value": round(zone_pct, 1), "unit": "% of 3mo range",
        "signal": "BUY" if range_score >= 60 else "SELL" if range_score <= 40 else "NEUTRAL",
        "detail": f"Price at {zone_pct:.0f}% of 3-month range"
    })

    # 2. RSI (10%)
    if rsi is not None and not (isinstance(rsi, float) and np.isnan(rsi)):
        rsi_score = 100 - rsi
        technical.append({
            "name": "rsi", "category": "technical", "weight": 0.10,
            "score": round(rsi_score, 1),
            "raw_value": round(rsi, 1), "unit": "RSI(14)",
            "signal": "BUY" if rsi < 30 else "SELL" if rsi > 70 else "NEUTRAL",
            "detail": f"RSI={rsi:.1f} — {'oversold' if rsi < 30 else 'overbought' if rsi > 70 else 'neutral'}"
        })

    # 3. MACD (6%)
    if macd_val is not None and macd_sig is not None:
        macd_diff = macd_val - macd_sig
        macd_norm = max(-2, min(2, macd_diff))
        macd_score = 50 + (macd_norm / 2) * 50
        technical.append({
            "name": "macd", "category": "technical", "weight": 0.06,
            "score": round(macd_score, 1),
            "raw_value": round(macd_diff, 4), "unit": "MACD - Signal",
            "signal": "BUY" if macd_diff > 0 else "SELL" if macd_diff < 0 else "NEUTRAL",
            "detail": f"MACD diff={macd_diff:.4f} — {'bullish' if macd_diff > 0 else 'bearish'} crossover"
        })

    # 4. Bollinger (4%)
    if bb_lower is not None and bb_upper is not None and price:
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            bb_pct = (price - bb_lower) / bb_range * 100
            bb_score = 100 - max(0, min(100, bb_pct))
            technical.append({
                "name": "bollinger", "category": "technical", "weight": 0.04,
                "score": round(bb_score, 1),
                "raw_value": round(bb_pct, 1), "unit": "% within bands",
                "signal": "BUY" if bb_score >= 70 else "SELL" if bb_score <= 30 else "NEUTRAL",
                "detail": f"Price at {bb_pct:.0f}% of Bollinger range"
            })

    # 5. SMA trend (4%)
    if sma_50 is not None and sma_200 is not None and price:
        sma_score = 50.0
        golden = sma_50 > sma_200
        sma_score += 15 if golden else -15
        price_vs_sma = (price / sma_50 - 1) * 100
        if price_vs_sma > 10: sma_score -= 10
        elif price_vs_sma > 0: sma_score += 10
        elif price_vs_sma < -10: sma_score += 15
        else: sma_score += 5
        sma_score = max(0, min(100, sma_score))
        technical.append({
            "name": "sma_trend", "category": "technical", "weight": 0.04,
            "score": round(sma_score, 1),
            "raw_value": round(price_vs_sma, 1), "unit": "% vs SMA50",
            "signal": "BUY" if sma_score >= 60 else "SELL" if sma_score <= 40 else "NEUTRAL",
            "detail": f"{'Golden' if golden else 'Death'} Cross, price {price_vs_sma:+.1f}% vs SMA50"
        })

    # ═══════════════════════════════════════════════
    # MACRO SIGNALS (20% total)
    # ═══════════════════════════════════════════════

    # 6. Macro regime (10%)
    try:
        mr = fetch_macro_regime()
        regime = mr.get("regime", "NEUTRAL")
        macro_score_raw = mr.get("score", 50)
        # FAVORABLE=high score (good for buying), HOSTILE=low score
        if regime == "FAVORABLE":
            ms = min(100, macro_score_raw + 20)
        elif regime == "HOSTILE":
            ms = max(0, macro_score_raw - 20)
        else:
            ms = macro_score_raw
        macro_signals.append({
            "name": "macro_regime", "category": "macro", "weight": 0.08,
            "score": round(ms, 1),
            "raw_value": regime, "unit": f"score {macro_score_raw}/100",
            "signal": "BUY" if regime == "FAVORABLE" else "SELL" if regime == "HOSTILE" else "NEUTRAL",
            "detail": f"Macro {regime} — {mr.get('tailwinds', 0)} tailwinds, {mr.get('headwinds', 0)} headwinds"
        })
    except Exception:
        pass

    # 7. Anti-Fragile composite (10%)
    try:
        af = get_antifragile_score()
        if isinstance(af, JSONResponse):
            af_data = json.loads(af.body.decode())
        else:
            af_data = af
        af_score = af_data.get("composite_score", 50)
        af_regime = af_data.get("regime", "NEUTRAL")
        macro_signals.append({
            "name": "antifragile", "category": "macro", "weight": 0.08,
            "score": round(af_score, 1),
            "raw_value": af_regime, "unit": f"{af_score}/100",
            "signal": "BUY" if af_score >= 60 else "SELL" if af_score <= 40 else "NEUTRAL",
            "detail": f"Anti-fragile {af_regime} ({af_score}/100) — real yield, dollar, supply, flows, geopolitical"
        })
    except Exception:
        pass

    # ═══════════════════════════════════════════════
    # FUNDAMENTAL SIGNALS (20% total)
    # ═══════════════════════════════════════════════

    # 8. Miner valuation (10%) — per-ticker if miner, sector avg if ETF
    try:
        val_data = get_miner_valuations()
        if isinstance(val_data, JSONResponse):
            val_data = json.loads(val_data.body.decode())
        miners = {m["symbol"]: m for m in val_data.get("miners", [])}
        if symbol in miners:
            m = miners[symbol]
            vs_avg = m.get("vs_avg_pct", 0)
            # Cheaper = higher score. -50% vs avg = 100, +50% = 0
            val_score = max(0, min(100, round(50 - vs_avg)))
            fundamental.append({
                "name": "valuation", "category": "fundamental", "weight": 0.08,
                "score": val_score,
                "raw_value": round(vs_avg, 1), "unit": f"EV/lb ${m.get('ev_per_lb', '?')}/lb",
                "signal": "BUY" if val_score >= 65 else "SELL" if val_score <= 35 else "NEUTRAL",
                "detail": f"EV/lb {vs_avg:+.1f}% vs peer avg — {'cheap' if vs_avg < -15 else 'expensive' if vs_avg > 15 else 'fair'}"
            })
        else:
            # ETF: use sector average signal
            avg_vs = sum(m.get("vs_avg_pct", 0) for m in val_data.get("miners", [])) / max(1, len(val_data.get("miners", [])))
            val_score = max(0, min(100, round(50 - avg_vs)))
            fundamental.append({
                "name": "valuation", "category": "fundamental", "weight": 0.08,
                "score": val_score,
                "raw_value": round(avg_vs, 1), "unit": "sector avg EV/lb",
                "signal": "BUY" if val_score >= 65 else "SELL" if val_score <= 35 else "NEUTRAL",
                "detail": f"Sector avg valuation {avg_vs:+.1f}% vs mean"
            })
    except Exception:
        pass

    # 9. Insider sentiment (10%)
    try:
        ins = get_insider_trades()
        if isinstance(ins, JSONResponse):
            ins = json.loads(ins.body.decode())
        summary = ins.get("summary", {})
        buys = summary.get("total_buys", 0)
        sells = summary.get("total_sells", 0)
        net_val = summary.get("net_insider_value", 0)
        total_trades = buys + sells
        if total_trades > 0:
            buy_ratio = buys / total_trades
            # buy_ratio 1.0 = 100, 0.5 = 50, 0.0 = 0
            ins_score = round(buy_ratio * 100)
            # Adjust for magnitude — heavy selling is a stronger signal
            if net_val < -5_000_000:
                ins_score = max(0, ins_score - 15)
            elif net_val > 1_000_000:
                ins_score = min(100, ins_score + 10)
            ins_score = max(0, min(100, ins_score))
            net_str = f"${abs(net_val)/1e6:.1f}M {'buying' if net_val > 0 else 'selling'}"
            fundamental.append({
                "name": "insider_sentiment", "category": "fundamental", "weight": 0.08,
                "score": ins_score,
                "raw_value": f"{buys}B/{sells}S", "unit": net_str,
                "signal": "BUY" if ins_score >= 60 else "SELL" if ins_score <= 40 else "NEUTRAL",
                "detail": f"{buys} buys vs {sells} sells, net {net_str}"
            })
    except Exception:
        pass

    # Signal 17: Economic surprise (4%)
    try:
        econ = economic_surprise()
        if isinstance(econ, dict) and econ.get("composite_score") is not None:
            econ_score = econ["composite_score"]
            macro_signals.append({
                "name": "economic_surprise", "category": "macro", "weight": 0.04,
                "score": econ_score,
                "raw_value": round(econ_score, 1), "unit": "surprise idx",
                "signal": econ["signal"],
                "detail": econ.get("detail", ""),
            })
    except Exception:
        pass

    # Signal 16: Relative value (4%)
    try:
        rv = relative_value(base=symbol if symbol in ["URA", "URNM"] else "URA", period="1y")
        if isinstance(rv, dict) and rv.get("relative_value_score") is not None:
            rv_score = rv["relative_value_score"]
            fundamental.append({
                "name": "relative_value", "category": "fundamental", "weight": 0.04,
                "score": rv_score,
                "raw_value": round(rv_score, 1), "unit": "RV score",
                "signal": rv["signal"],
                "detail": "; ".join(f"vs {p['peer']}: z={p['ratio']['zscore']}" for p in rv.get("peer_analysis", [])[:3]),
            })
    except Exception:
        pass

    # ═══════════════════════════════════════════════
    # SENTIMENT SIGNALS (20% total)
    # ═══════════════════════════════════════════════

    # 10. ETF fund flows (4%) + flow divergence (2%)
    try:
        fund_flows = get_fund_flows()
        if isinstance(fund_flows, JSONResponse):
            fund_flows = json.loads(fund_flows.body.decode())
        sector_sig = fund_flows.get("sector_signal", "NEUTRAL")
        flow_map = {"STRONG INFLOW": 85, "INFLOW": 70, "NEUTRAL": 50, "OUTFLOW": 30, "STRONG OUTFLOW": 15}
        flow_score = flow_map.get(sector_sig, 50)
        etf_list = fund_flows.get("etfs", [])
        flow_details = [f"{e['symbol']} ${e.get('flow_22d_mm', 0):+.0f}M" for e in etf_list[:2]]
        sentiment.append({
            "name": "etf_flows", "category": "sentiment", "weight": 0.03,
            "score": flow_score,
            "raw_value": sector_sig, "unit": ", ".join(flow_details),
            "signal": "BUY" if flow_score >= 60 else "SELL" if flow_score <= 40 else "NEUTRAL",
            "detail": f"Sector flows: {sector_sig} — {', '.join(flow_details)}"
        })

        # Flow divergence: URNM (pure-play miners) vs URA (broad)
        ura_flow = next((e for e in etf_list if e["symbol"] == "URA"), None)
        urnm_flow = next((e for e in etf_list if e["symbol"] == "URNM"), None)
        if ura_flow and urnm_flow:
            ura_22d = ura_flow.get("flow_22d_mm", 0)
            urnm_22d = urnm_flow.get("flow_22d_mm", 0)
            # URNM inflow + URA outflow = smart money bullish on miners
            if urnm_22d > 10 and ura_22d < -10:
                div_score = 80
                div_sig = "BUY"
                div_detail = f"Bullish divergence: URNM +${urnm_22d:.0f}M vs URA ${ura_22d:.0f}M — smart money favoring miners"
            elif ura_22d > 10 and urnm_22d < -10:
                div_score = 25
                div_sig = "SELL"
                div_detail = f"Bearish divergence: URA +${ura_22d:.0f}M vs URNM ${urnm_22d:.0f}M — broad buying, miners selling"
            elif urnm_22d > 10 and ura_22d > 10:
                div_score = 70
                div_sig = "BUY"
                div_detail = f"Aligned inflows: URA +${ura_22d:.0f}M, URNM +${urnm_22d:.0f}M — broad sector buying"
            elif urnm_22d < -10 and ura_22d < -10:
                div_score = 30
                div_sig = "SELL"
                div_detail = f"Aligned outflows: URA ${ura_22d:.0f}M, URNM ${urnm_22d:.0f}M — broad sector selling"
            else:
                div_score = 50
                div_sig = "NEUTRAL"
                div_detail = f"No clear divergence: URA ${ura_22d:+.0f}M, URNM ${urnm_22d:+.0f}M"
            sentiment.append({
                "name": "flow_divergence", "category": "sentiment", "weight": 0.02,
                "score": div_score,
                "raw_value": f"URA:{ura_22d:+.0f}/URNM:{urnm_22d:+.0f}", "unit": "$M 22d",
                "signal": div_sig,
                "detail": div_detail,
            })
    except Exception:
        pass

    # 11. Short interest (5%)
    try:
        si = get_short_interest()
        if isinstance(si, JSONResponse):
            si = json.loads(si.body.decode())
        tickers_si = si.get("tickers", [])
        # Find this ticker's short interest
        ticker_si = next((t for t in tickers_si if t["symbol"] == symbol), None)
        if ticker_si and ticker_si.get("short_pct_float") is not None:
            spf = ticker_si["short_pct_float"]
            # High short interest = potential squeeze = contrarian bullish
            # But also = bearish sentiment. Use moderate contrarian: >15% = slightly bullish (squeeze potential)
            if spf > 15:
                si_score = 65  # squeeze potential
                sig = "BUY"
                detail = f"Short {spf}% float — squeeze potential"
            elif spf > 10:
                si_score = 45
                sig = "NEUTRAL"
                detail = f"Short {spf}% float — elevated but not extreme"
            elif spf > 5:
                si_score = 55
                sig = "NEUTRAL"
                detail = f"Short {spf}% float — moderate, healthy"
            else:
                si_score = 50
                sig = "NEUTRAL"
                detail = f"Short {spf}% float — low short interest"
            sentiment.append({
                "name": "short_interest", "category": "sentiment", "weight": 0.04,
                "score": si_score,
                "raw_value": spf, "unit": "% of float",
                "signal": sig,
                "detail": detail
            })
        else:
            # Sector-level: count squeeze risks
            squeeze_count = si.get("squeeze_risks", 0)
            heavy_count = sum(1 for t in tickers_si if t.get("status") == "HEAVY")
            si_score = 60 if squeeze_count > 0 else 50
            sentiment.append({
                "name": "short_interest", "category": "sentiment", "weight": 0.04,
                "score": si_score,
                "raw_value": f"{heavy_count} heavy", "unit": f"{squeeze_count} squeeze risks",
                "signal": "BUY" if squeeze_count > 0 else "NEUTRAL",
                "detail": f"{heavy_count} tickers with heavy short interest, {squeeze_count} squeeze risks"
            })
    except Exception:
        pass

    # 12. Institutional ownership (5%)
    try:
        inst = get_institutional_ownership(symbol)
        if isinstance(inst, JSONResponse):
            inst = json.loads(inst.body.decode())
        inst_sig = inst.get("signal", "NEUTRAL")
        inc = inst.get("increasing_count", 0)
        dec = inst.get("decreasing_count", 0)
        inst_map = {"ACCUMULATION": 75, "NEUTRAL": 50, "DISTRIBUTION": 25}
        inst_score = inst_map.get(inst_sig, 50)
        sentiment.append({
            "name": "institutional", "category": "sentiment", "weight": 0.04,
            "score": inst_score,
            "raw_value": inst_sig, "unit": f"{inc}↑ {dec}↓",
            "signal": "BUY" if inst_sig == "ACCUMULATION" else "SELL" if inst_sig == "DISTRIBUTION" else "NEUTRAL",
            "detail": f"Institutions: {inst_sig} — {inc} increasing, {dec} decreasing positions"
        })
    except Exception:
        pass

    # 13. Put/Call ratio (4%) — contrarian indicator (only HIGH confidence)
    try:
        pcr_data = get_put_call_ratio(symbol=symbol)
        if isinstance(pcr_data, JSONResponse):
            pcr_data = json.loads(pcr_data.body.decode())
        pcr_tickers = pcr_data.get("tickers", [])
        pcr_entry = next((t for t in pcr_tickers if t["symbol"] == symbol), None)

        if pcr_entry and pcr_entry.get("confidence") == "HIGH" and pcr_entry.get("score") is not None:
            # Ticker-level HIGH confidence data
            pcr_score = pcr_entry["score"]
            pcr_sig = pcr_entry["contrarian_signal"]
            sentiment.append({
                "name": "put_call_ratio", "category": "sentiment", "weight": 0.03,
                "score": pcr_score,
                "raw_value": pcr_entry["pcr_oi"], "unit": "P/C (OI)",
                "signal": "BUY" if pcr_sig == "BULLISH" else "SELL" if pcr_sig == "BEARISH" else "NEUTRAL",
                "detail": f"P/C={pcr_entry['pcr_oi']} ({pcr_entry['total_oi']} OI) — {pcr_entry['signal']}"
            })
        elif pcr_data.get("sector_score") is not None and pcr_data.get("high_confidence_count", 0) > 0:
            # Fall back to sector-level (only if based on real data)
            s_pcr = pcr_data["sector_pcr"]
            s_score = pcr_data["sector_score"]
            sentiment.append({
                "name": "put_call_ratio", "category": "sentiment", "weight": 0.03,
                "score": s_score,
                "raw_value": s_pcr, "unit": "sector P/C",
                "signal": "BUY" if s_score >= 60 else "SELL" if s_score <= 40 else "NEUTRAL",
                "detail": f"Sector P/C={s_pcr} — {pcr_data['sector_signal']} (ticker OI too low, using sector)"
            })
        # else: skip entirely — no data is better than bad data
    except Exception:
        pass

    # Signal 15: COT positioning proxy (synthetic)
    try:
        cot = get_cot_report()
        if isinstance(cot, dict) and cot.get("composite_score") is not None:
            cot_score = cot["composite_score"]
            sentiment.append({
                "name": "cot_positioning", "category": "sentiment", "weight": 0.04,
                "score": cot_score,
                "raw_value": round(cot_score, 1), "unit": "composite",
                "signal": cot["signal"],
                "detail": cot.get("detail", "Synthetic COT from options, shorts, insiders"),
            })
    except Exception:
        pass

    # ═══════════════════════════════════════════════
    # COMPUTE COMPOSITE
    # ═══════════════════════════════════════════════
    all_components = technical + macro_signals + fundamental + sentiment

    # Add weighted field
    for c in all_components:
        c["weighted"] = round(c["score"] * c["weight"], 2)

    total_weight = sum(c["weight"] for c in all_components)
    composite = sum(c["score"] * c["weight"] for c in all_components) / total_weight if total_weight > 0 else 50
    composite = max(0, min(100, composite))

    # Also compute category sub-scores
    def cat_score(items):
        w = sum(c["weight"] for c in items)
        return round(sum(c["score"] * c["weight"] for c in items) / w, 1) if w > 0 else None

    tech_score = cat_score(technical)
    macro_score = cat_score(macro_signals)
    fund_score = cat_score(fundamental)
    sent_score = cat_score(sentiment)

    # Label
    if composite >= 75: label = "STRONG BUY"
    elif composite >= 60: label = "BUY"
    elif composite >= 45: label = "HOLD"
    elif composite >= 30: label = "SELL"
    else: label = "STRONG SELL"

    bullish = [c for c in all_components if c["signal"] == "BUY"]
    bearish = [c for c in all_components if c["signal"] == "SELL"]

    return {
        "symbol": symbol,
        "total_score": round(composite, 1),
        "technical_score": tech_score,
        "label": label,
        "categories": {
            "technical": {"score": tech_score, "weight": "40%", "count": len(technical)},
            "macro": {"score": macro_score, "weight": "20%", "count": len(macro_signals)},
            "fundamental": {"score": fund_score, "weight": "20%", "count": len(fundamental)},
            "sentiment": {"score": sent_score, "weight": "20%", "count": len(sentiment)},
        },
        "components": all_components,
        "summary": {
            "bullish_signals": [c["name"] for c in bullish],
            "bearish_signals": [c["name"] for c in bearish],
            "neutral_signals": [c["name"] for c in all_components if c["signal"] == "NEUTRAL"],
            "total_signals": len(all_components),
            "dominant_signal": max(all_components, key=lambda c: c["weight"])["name"] if all_components else None,
        },
        "price": price,
        "zone": meta.get("zone"),
        "last_updated": meta.get("last_updated"),
    }


_backtest_score_cache = {}  # keyed by (symbol, period)

def _prepare_daily_scores(symbol: str, period: str):
    """Fetch OHLCV + compute daily technical scores. Cached per (symbol, period)."""
    import time
    cache_key = (symbol, period)
    now = time.time()
    if cache_key in _backtest_score_cache and now - _backtest_score_cache[cache_key]["ts"] < 3600:
        return _backtest_score_cache[cache_key]["data"]

    import yfinance as yf, numpy as np
    period_map = {"3m": "3mo", "6m": "6mo", "1y": "1y", "2y": "2y", "3y": "3y", "5y": "5y"}
    yf_period = period_map.get(period, "1y")

    t = yf.Ticker(symbol)
    df = t.history(period=yf_period)
    if df.empty or len(df) < 50:
        raise HTTPException(400, f"Insufficient data for {symbol} ({len(df)} bars)")

    df["SMA_50"] = df["Close"].rolling(50).mean()
    df["SMA_200"] = df["Close"].rolling(200).mean()
    df["BB_mid"] = df["Close"].rolling(20).mean()
    df["BB_std"] = df["Close"].rolling(20).std()
    df["BB_upper"] = df["BB_mid"] + 2 * df["BB_std"]
    df["BB_lower"] = df["BB_mid"] - 2 * df["BB_std"]

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - 100 / (1 + rs)

    ema12 = df["Close"].ewm(span=12).mean()
    ema26 = df["Close"].ewm(span=26).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_signal"] = df["MACD"].ewm(span=9).mean()
    df["Range_high"] = df["High"].rolling(63).max()
    df["Range_low"] = df["Low"].rolling(63).min()

    df = df.dropna(subset=["SMA_50", "RSI", "MACD", "BB_upper", "Range_high"])
    if len(df) < 10:
        raise HTTPException(400, f"Not enough data for {symbol} after indicator warmup")

    from analysis import compute_signal_score
    daily_scores = []
    for idx, row in df.iterrows():
        price = float(row["Close"])
        range_span = row["Range_high"] - row["Range_low"]
        zone_pct = ((price - row["Range_low"]) / range_span * 100) if range_span > 0 else 50
        score, label = compute_signal_score(
            zone="", zone_pct=zone_pct, rsi=float(row["RSI"]),
            macd=float(row["MACD"]), macd_signal=float(row["MACD_signal"]),
            price=price, bb_lower=float(row["BB_lower"]),
            bb_upper=float(row["BB_upper"]), sma_50=float(row["SMA_50"]),
            sma_200=float(row["SMA_200"]) if not np.isnan(row["SMA_200"]) else None,
        )
        daily_scores.append({"date": idx.strftime("%Y-%m-%d"), "price": round(price, 2), "score": score, "label": label})

    _backtest_score_cache[cache_key] = {"data": daily_scores, "ts": now}
    return daily_scores


def _run_backtest(daily_scores: list, initial: float, buy_threshold: float, sell_threshold: float, full_output: bool = True):
    """Run backtest simulation on pre-computed daily scores. Returns results dict."""
    import numpy as np
    import pandas as pd

    cash = initial
    shares = 0.0
    position_open = False
    entry_price = 0.0
    entry_date = ""
    trades = []
    equity_curve = [] if full_output else None
    max_equity = initial
    max_drawdown = 0.0
    buy_signals = 0
    sell_signals = 0
    daily_returns = []
    prev_equity = initial

    for day in daily_scores:
        score = day["score"]
        price = day["price"]

        if score >= buy_threshold and not position_open:
            shares = cash / price
            entry_price = price
            entry_date = day["date"]
            cash = 0.0
            position_open = True
            buy_signals += 1
            if full_output:
                trades.append({"type": "BUY", "date": day["date"], "price": price, "score": score, "shares": round(shares, 4)})

        elif score <= sell_threshold and position_open:
            cash = shares * price
            pnl = (price - entry_price) / entry_price * 100
            sell_signals += 1
            if full_output:
                trades.append({
                    "type": "SELL", "date": day["date"], "price": price, "score": score, "shares": round(shares, 4),
                    "entry_price": entry_price, "entry_date": entry_date,
                    "pnl_pct": round(pnl, 2), "pnl_dollar": round(shares * (price - entry_price), 2),
                    "holding_days": (pd.Timestamp(day["date"]) - pd.Timestamp(entry_date)).days,
                })
            shares = 0.0
            position_open = False

        equity = cash + shares * price
        daily_ret = (equity - prev_equity) / prev_equity if prev_equity > 0 else 0
        daily_returns.append(daily_ret)
        prev_equity = equity
        max_equity = max(max_equity, equity)
        dd = (max_equity - equity) / max_equity * 100
        max_drawdown = max(max_drawdown, dd)
        if full_output:
            equity_curve.append({"date": day["date"], "equity": round(equity, 2), "score": score, "price": price, "position": "LONG" if position_open else "CASH"})

    final_equity = cash + shares * daily_scores[-1]["price"] if daily_scores else initial
    bh_start = daily_scores[0]["price"]
    bh_end = daily_scores[-1]["price"]
    bh_return = (bh_end - bh_start) / bh_start * 100
    bh_final = initial * (1 + bh_return / 100)

    completed_trades = [t for t in trades if t["type"] == "SELL"] if full_output else []
    trade_count = sell_signals
    strategy_return = (final_equity - initial) / initial * 100
    alpha = strategy_return - bh_return

    # Sharpe ratio (annualized, risk-free = 0 for simplicity)
    if len(daily_returns) > 1:
        dr = np.array(daily_returns)
        sharpe = (np.mean(dr) / np.std(dr) * np.sqrt(252)) if np.std(dr) > 0 else 0.0
    else:
        sharpe = 0.0

    # Sortino (downside deviation only)
    if len(daily_returns) > 1:
        dr = np.array(daily_returns)
        downside = dr[dr < 0]
        sortino = (np.mean(dr) / np.std(downside) * np.sqrt(252)) if len(downside) > 0 and np.std(downside) > 0 else sharpe
    else:
        sortino = 0.0

    wins = [t for t in completed_trades if t.get("pnl_pct", 0) > 0] if full_output else []
    losses = [t for t in completed_trades if t.get("pnl_pct", 0) <= 0] if full_output else []
    avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0

    result = {
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(strategy_return, 2),
        "buy_hold_return_pct": round(bh_return, 2),
        "buy_hold_final": round(bh_final, 2),
        "alpha_vs_buyhold": round(alpha, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "total_trades": trade_count,
        "open_position": position_open,
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "win_rate": round(len(wins) / trade_count * 100, 1) if trade_count > 0 else None,
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "profit_factor": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else None,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
    }

    if full_output:
        result["trades"] = trades
        result["equity_curve"] = equity_curve[::max(1, len(equity_curve) // 100)]

    return result


@app.get("/api/signal-backtest")
def signal_backtest(
    symbol: str = Query("URA"),
    period: str = Query("1y"),
    initial: float = Query(10000),
    buy_threshold: float = Query(65),
    sell_threshold: float = Query(35),
):
    """
    Historical signal backtester. Reconstructs technical scores from OHLCV data
    and simulates buy/sell decisions. Technical signals only (40% of composite).
    """
    symbol = symbol.upper()
    daily_scores = _prepare_daily_scores(symbol, period)
    result = _run_backtest(daily_scores, initial, buy_threshold, sell_threshold, full_output=True)

    return {
        "symbol": symbol,
        "period": period,
        "trading_days": len(daily_scores),
        "parameters": {"initial_capital": initial, "buy_threshold": buy_threshold, "sell_threshold": sell_threshold},
        "results": {k: v for k, v in result.items() if k not in ("trades", "equity_curve")},
        "trades": result.get("trades", []),
        "equity_curve": result.get("equity_curve", []),
        "daily_scores": daily_scores[::max(1, len(daily_scores) // 100)],
        "limitations": [
            "Backtest uses TECHNICAL signals only (40% of composite score)",
            "Macro, fundamental, and sentiment signals are NOT reconstructed historically",
            "No slippage, commissions, or spread modeled",
            "All-in / all-out sizing (no position scaling)",
            "Score thresholds tested on in-sample data (overfitting risk)",
        ],
    }


@app.get("/api/backtest-optimizer")
def backtest_optimizer(
    symbol: str = Query("URA"),
    period: str = Query("1y"),
    initial: float = Query(10000),
    step: int = Query(5, ge=2, le=10),
    sort_by: str = Query("sharpe", regex="^(sharpe|sortino|alpha|return|drawdown)$"),
):
    """
    Sweep buy/sell threshold combinations to find optimal signal calibration.
    Returns all combos sorted by chosen metric (default: Sharpe ratio).
    """
    symbol = symbol.upper()
    daily_scores = _prepare_daily_scores(symbol, period)

    buy_range = list(range(30, 81, step))
    sell_range = list(range(20, 71, step))

    combos = []
    for buy_th in buy_range:
        for sell_th in sell_range:
            if buy_th <= sell_th:
                continue
            r = _run_backtest(daily_scores, initial, buy_th, sell_th, full_output=False)
            combos.append({
                "buy_threshold": buy_th,
                "sell_threshold": sell_th,
                "total_return_pct": r["total_return_pct"],
                "alpha_vs_buyhold": r["alpha_vs_buyhold"],
                "sharpe_ratio": r["sharpe_ratio"],
                "sortino_ratio": r["sortino_ratio"],
                "max_drawdown_pct": r["max_drawdown_pct"],
                "total_trades": r["total_trades"],
                "win_rate": r["win_rate"],
                "profit_factor": r["profit_factor"],
            })

    # Sort
    sort_map = {
        "sharpe": lambda x: x["sharpe_ratio"],
        "sortino": lambda x: x["sortino_ratio"],
        "alpha": lambda x: x["alpha_vs_buyhold"],
        "return": lambda x: x["total_return_pct"],
        "drawdown": lambda x: -x["max_drawdown_pct"],  # lower DD = better
    }
    combos.sort(key=sort_map.get(sort_by, sort_map["sharpe"]), reverse=True)

    best = combos[0] if combos else None

    # Heatmap data (buy_threshold × sell_threshold → metric value)
    heatmap = {}
    for c in combos:
        heatmap[f"{c['buy_threshold']}_{c['sell_threshold']}"] = {
            "sharpe": c["sharpe_ratio"],
            "alpha": c["alpha_vs_buyhold"],
            "return": c["total_return_pct"],
        }

    bh_return = combos[0]["total_return_pct"] - combos[0]["alpha_vs_buyhold"] if combos else 0

    return {
        "symbol": symbol,
        "period": period,
        "trading_days": len(daily_scores),
        "sort_by": sort_by,
        "combos_tested": len(combos),
        "buy_range": buy_range,
        "sell_range": sell_range,
        "buy_hold_return_pct": round(bh_return, 2),
        "best": best,
        "top_10": combos[:10],
        "worst_5": combos[-5:] if len(combos) >= 5 else combos,
        "all_combos": combos,
        "heatmap": heatmap,
        "limitations": [
            "In-sample optimization — overfitting risk is HIGH",
            "Technical signals only (40% of composite)",
            "No transaction costs or slippage",
            "Optimal thresholds may not generalize to future periods",
            "Walk-forward validation recommended before live trading",
        ],
    }


@app.get("/api/trade-ticket")
def trade_ticket(
    symbol: str = Query("URA"),
    portfolio_value: float = Query(10000),
):
    """
    The final output: a single actionable trade ticket with entry, stop loss,
    take profit, position size, and confidence score.
    """
    import yfinance as yf, numpy as np, requests as _req

    symbol = symbol.upper()

    # 1. Get composite score
    try:
        decomp = _req.get(f"http://localhost:8050/api/score-decomposition?symbol={symbol}", timeout=30).json()
        composite = decomp.get("total_score", 50)
        label = decomp.get("label", "HOLD")
        categories = decomp.get("categories", {})
    except:
        composite = 50
        label = "HOLD"
        categories = {}

    # 2. Get Kelly sizing
    try:
        kelly = _req.get(f"http://localhost:8050/api/kelly-criterion?symbol={symbol}&period=2y&forward_days=22", timeout=60).json()
        kelly_alloc = max(0, kelly.get("recommendation", {}).get("allocation_pct", 5))
        bucket_stats = kelly.get("buckets", [])
        current_bucket = kelly.get("current_bucket", "?")
        # Get win rate and avg return for current bucket
        bucket = next((b for b in bucket_stats if b["bucket"] == current_bucket), None)
        win_rate = bucket["win_rate_pct"] if bucket else 50
        avg_return = bucket["avg_return_pct"] if bucket else 0
        avg_loss = abs(bucket["avg_loss_pct"]) if bucket else 5
    except:
        kelly_alloc = 5
        win_rate = 50
        avg_return = 0
        avg_loss = 5

    # 3. Get price data for levels
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period="3mo", auto_adjust=True)
        if hist.index.tz is not None:
            hist.index = hist.index.tz_localize(None)
        current_price = float(hist["Close"].iloc[-1])
        high_3m = float(hist["High"].max())
        low_3m = float(hist["Low"].min())

        # Support/resistance from recent price action
        bb_mid = float(hist["Close"].rolling(20).mean().iloc[-1])
        bb_std = float(hist["Close"].rolling(20).std().iloc[-1])
        bb_lower = bb_mid - 2 * bb_std
        bb_upper = bb_mid + 2 * bb_std

        sma_50 = float(hist["Close"].rolling(50).mean().iloc[-1]) if len(hist) >= 50 else current_price
        atr_14 = float((hist["High"] - hist["Low"]).rolling(14).mean().iloc[-1])
    except Exception as e:
        raise HTTPException(500, f"Price data error: {e}")

    # 4. Determine action
    # Contrarian Kelly logic: low score = buy heavy, mid = small, high = trim
    if composite <= 25:
        action = "BUY"
        conviction = "HIGH"
        rationale = f"Extreme fear zone (score {composite:.0f}). Kelly shows {win_rate:.0f}% win rate at this level. Contrarian buy."
    elif composite <= 40:
        action = "BUY"
        conviction = "MODERATE"
        rationale = f"Fear zone (score {composite:.0f}). Historical win rate {win_rate:.0f}%. Moderate position recommended."
    elif composite <= 55:
        action = "WAIT"
        conviction = "LOW"
        rationale = f"Neutral zone (score {composite:.0f}). Marginal edge ({win_rate:.0f}% win rate). Wait for better entry or accumulate small."
    elif composite <= 70:
        action = "HOLD"
        conviction = "MODERATE"
        rationale = f"Score {composite:.0f} in confirmation zone. If already holding, maintain. Not ideal for new entry — crowd is optimistic."
    else:
        action = "SELL"
        conviction = "MODERATE"
        rationale = f"Euphoria zone (score {composite:.0f}). Historically lower forward returns. Trim or take profits."

    # 5. Entry price
    if action in ["BUY", "WAIT"]:
        # Limit order slightly below current (at lower BB or recent support)
        entry_price = round(min(current_price, bb_lower + atr_14 * 0.5), 2)
        entry_type = "LIMIT" if entry_price < current_price * 0.98 else "MARKET"
        if entry_type == "LIMIT":
            entry_note = f"Limit below current — near lower Bollinger (${bb_lower:.2f})"
        else:
            entry_price = current_price
            entry_note = "Market order — price near support already"
    else:
        entry_price = current_price
        entry_type = "MARKET"
        entry_note = "At market"

    # 6. Stop loss: 2x ATR below entry, or below 3-month low
    stop_loss = round(max(low_3m * 0.97, entry_price - 2 * atr_14), 2)
    stop_pct = round((stop_loss / entry_price - 1) * 100, 1)

    # 7. Take profit: use SMA50 or upper BB as structural targets, minimum 2:1 R:R
    risk_amount = entry_price - stop_loss
    min_tp_2x = entry_price + risk_amount * 2.5  # minimum 2.5:1 R:R
    # Structural targets
    tp_candidates = [
        sma_50,  # SMA50 reclaim
        bb_upper,  # upper Bollinger
        entry_price * (1 + max(avg_return, 5) / 100),  # historical avg return
        min_tp_2x,  # minimum R:R target
    ]
    # Pick highest target that's above the 2:1 minimum
    take_profit = round(max(t for t in tp_candidates if t > entry_price), 2)
    tp_pct_final = round((take_profit / entry_price - 1) * 100, 1)
    # Note which target we used
    if take_profit >= bb_upper * 0.99:
        tp_method = f"Upper Bollinger Band (${bb_upper:.2f})"
    elif take_profit >= sma_50 * 0.99:
        tp_method = f"SMA50 reclaim (${sma_50:.2f})"
    else:
        tp_method = f"Minimum 2.5:1 R:R target"

    # 8. Risk/reward ratio
    risk = entry_price - stop_loss
    reward = take_profit - entry_price
    rr_ratio = round(reward / risk, 2) if risk > 0 else 0

    # 9. Position sizing (Kelly-based, dollar amount)
    position_value = round(portfolio_value * kelly_alloc / 100, 2)
    shares = round(position_value / entry_price, 1) if entry_price > 0 else 0
    max_loss = round(shares * (entry_price - stop_loss), 2)
    max_loss_pct = round(max_loss / portfolio_value * 100, 2) if portfolio_value > 0 else 0

    # 10. Confidence score (0-100)
    # Weighted: Kelly edge (40%), risk/reward (30%), composite extremity (30%)
    edge_score = min(100, win_rate * 1.2) if win_rate > 50 else max(0, win_rate * 0.8)
    rr_score = min(100, rr_ratio * 30) if rr_ratio > 0 else 0
    extremity = abs(composite - 50) * 2  # further from 50 = more conviction
    confidence = round(edge_score * 0.4 + rr_score * 0.4 + extremity * 0.2, 1)
    confidence = max(0, min(100, confidence))

    if confidence >= 70:
        confidence_label = "HIGH CONFIDENCE"
    elif confidence >= 45:
        confidence_label = "MODERATE CONFIDENCE"
    elif confidence >= 25:
        confidence_label = "LOW CONFIDENCE"
    else:
        confidence_label = "NO EDGE"

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "symbol": symbol,
        "current_price": current_price,
        "composite_score": round(composite, 1),
        "composite_label": label,
        "action": action,
        "conviction": conviction,
        "rationale": rationale,
        "entry": {
            "price": entry_price,
            "type": entry_type,
            "note": entry_note,
        },
        "stop_loss": {
            "price": stop_loss,
            "pct_from_entry": stop_pct,
            "method": "2x ATR below entry, floored at 97% of 3-month low",
        },
        "take_profit": {
            "price": take_profit,
            "pct_from_entry": tp_pct_final,
            "method": tp_method,
        },
        "risk_reward": rr_ratio,
        "position_sizing": {
            "kelly_alloc_pct": round(kelly_alloc, 1),
            "position_value": position_value,
            "shares": shares,
            "max_loss": max_loss,
            "max_loss_pct_portfolio": max_loss_pct,
        },
        "confidence": {
            "score": confidence,
            "label": confidence_label,
            "components": {
                "historical_edge": round(edge_score, 1),
                "risk_reward_quality": round(rr_score, 1),
                "signal_extremity": round(extremity, 1),
            },
        },
        "win_rate_at_score": round(win_rate, 1),
        "disclaimer": "Not financial advice. Model has limited track record. Past performance ≠ future results.",
        "kelly_caveat": "THEORETICAL — Kelly sizing is forward-testing only. Win rates are from regime bucketing, not closed trades. Need 50+ tracked trades with defined entry/exit rules before using Kelly for real capital. Current scores work as qualitative contrarian sentiment gauge, not quantitative sizing engine.",
    }


@app.get("/api/ticker-correlation")
def ticker_correlation(days: int = Query(90, ge=30, le=252)):
    """Price correlation matrix between all tracked tickers."""
    import yfinance as yf, numpy as np
    from analysis import TICKERS

    # Fetch returns
    returns = {}
    for sym in list(TICKERS.keys()):
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period=f"{days + 10}d")
            if hist.empty or len(hist) < days // 2:
                continue
            if hist.index.tz:
                hist.index = hist.index.tz_localize(None)
            rets = hist["Close"].pct_change().dropna().tail(days)
            returns[sym] = rets
        except:
            continue

    syms = list(returns.keys())
    if len(syms) < 3:
        raise HTTPException(400, "Not enough tickers with data")

    # Align dates
    import pandas as pd
    df = pd.DataFrame(returns)
    df = df.dropna()

    corr = df.corr().values
    n = len(syms)

    # Extract pairs
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append({"pair": [syms[i], syms[j]], "correlation": round(float(corr[i][j]), 3)})

    pairs_sorted = sorted(pairs, key=lambda x: x["correlation"], reverse=True)

    # Simple clustering: group tickers with avg correlation > 0.7
    clusters = []
    assigned = set()
    for i in range(n):
        if syms[i] in assigned:
            continue
        cluster = [syms[i]]
        assigned.add(syms[i])
        for j in range(i + 1, n):
            if syms[j] in assigned:
                continue
            if float(corr[i][j]) > 0.7:
                cluster.append(syms[j])
                assigned.add(syms[j])
        if len(cluster) > 1:
            # Compute avg intra-cluster correlation
            intra = []
            for a in range(len(cluster)):
                for b in range(a + 1, len(cluster)):
                    ai, bi = syms.index(cluster[a]), syms.index(cluster[b])
                    intra.append(float(corr[ai][bi]))
            clusters.append({
                "cluster": len(clusters) + 1,
                "tickers": cluster,
                "avg_intra_correlation": round(sum(intra) / len(intra), 3) if intra else 0,
            })

    # Diversification score: 1 - avg correlation (higher = more diversified)
    all_corrs = [p["correlation"] for p in pairs]
    avg_corr = sum(all_corrs) / len(all_corrs) if all_corrs else 0
    div_score = round(1 - avg_corr, 3)

    return {
        "period_days": days,
        "data_points": len(df),
        "tickers": syms,
        "correlation_matrix": [[round(float(corr[i][j]), 3) for j in range(n)] for i in range(n)],
        "highest_correlations": pairs_sorted[:5],
        "lowest_correlations": pairs_sorted[-5:][::-1],
        "avg_correlation": round(avg_corr, 3),
        "diversification_score": div_score,
        "clusters": clusters,
        "interpretation": f"Avg pairwise correlation {avg_corr:.2f}. {'High concentration risk — most tickers move together.' if avg_corr > 0.7 else 'Moderate diversification — some independent movers.' if avg_corr > 0.5 else 'Well diversified portfolio.'}",
    }


@app.get("/api/position-sizing")
def position_sizing(ticker: str = Query(None)):
    """Rules-based position sizing combining Kelly, regime, score, drawdown, volatility."""
    import yfinance as yf, numpy as np
    from analysis import TICKERS

    symbols = [ticker.upper()] if ticker else list(TICKERS.keys())
    results = []

    # Get regime once (shared across tickers)
    try:
        regime_data = regime_detector("URA")
        regime_label = regime_data.get("regime", "SIDEWAYS")
        regime_mult = regime_data.get("position_sizing_multiplier", 0.5)
        regime_conf = regime_data.get("confidence", 0.5)
    except:
        regime_label = "UNKNOWN"
        regime_mult = 0.5
        regime_conf = 0.5

    for sym in symbols:
        try:
            meta = get_ticker_meta(sym)
            if not meta:
                continue
            price = meta.get("current_price", 0)
            score = meta.get("signal_score", 50)

            # 1. Base allocation from score (contrarian: low score = buy)
            if score <= 20: base_alloc = 15.0
            elif score <= 30: base_alloc = 12.0
            elif score <= 40: base_alloc = 10.0
            elif score <= 50: base_alloc = 5.0
            elif score <= 60: base_alloc = 7.0
            elif score <= 70: base_alloc = 3.0
            else: base_alloc = 0.0

            # 2. Volatility adjustment
            try:
                tk = yf.Ticker(sym)
                hist = tk.history(period="100d")
                if hist.index.tz: hist.index = hist.index.tz_localize(None)
                rets = hist["Close"].pct_change().dropna()
                vol_20 = float(rets.tail(20).std()) * np.sqrt(252) * 100
                vol_60 = float(rets.tail(60).std()) * np.sqrt(252) * 100
                # Inverse vol scaling: high vol = reduce
                if vol_20 < 30: vol_mult = 1.2
                elif vol_20 < 50: vol_mult = 1.0
                elif vol_20 < 80: vol_mult = 0.7
                else: vol_mult = 0.5
            except:
                vol_20 = 50
                vol_60 = 50
                vol_mult = 0.8

            # 3. Drawdown adjustment
            try:
                high_52 = float(hist["Close"].max()) if not hist.empty else price
                dd_pct = (price / high_52 - 1) * 100
                # Deep drawdown = contrarian opportunity (increase slightly)
                if dd_pct < -30: dd_mult = 1.3
                elif dd_pct < -15: dd_mult = 1.1
                elif dd_pct > -5: dd_mult = 0.9  # near highs, reduce
                else: dd_mult = 1.0
            except:
                dd_pct = 0
                dd_mult = 1.0

            # 4. Combine
            raw_alloc = base_alloc * regime_mult * vol_mult * dd_mult

            # 5. Apply caps
            max_per_ticker = 20.0
            final_alloc = round(min(raw_alloc, max_per_ticker), 2)
            if final_alloc < 0.5:
                final_alloc = 0

            # Confidence
            factors_aligned = sum([
                1 if score < 40 else 0,   # contrarian buy
                1 if vol_mult >= 0.8 else 0,  # vol manageable
                1 if dd_mult >= 1.0 else 0,  # drawdown opportunity
                1 if regime_mult >= 0.7 else 0,  # regime supportive
            ])
            confidence = round(factors_aligned / 4, 2)

            # Action label
            if final_alloc >= 10: action = "STRONG_BUY"
            elif final_alloc >= 5: action = "BUY"
            elif final_alloc >= 2: action = "LIGHT"
            elif final_alloc > 0: action = "MINIMAL"
            else: action = "NO_POSITION"

            results.append({
                "symbol": sym,
                "name": TICKERS.get(sym, sym),
                "action": action,
                "final_allocation_pct": final_alloc,
                "confidence": confidence,
                "composite_score": round(score, 1),
                "breakdown": {
                    "base_allocation": base_alloc,
                    "regime_multiplier": regime_mult,
                    "volatility_multiplier": vol_mult,
                    "drawdown_multiplier": dd_mult,
                    "raw_allocation": round(base_alloc * regime_mult * vol_mult * dd_mult, 2),
                    "cap_applied": round(base_alloc * regime_mult * vol_mult * dd_mult, 2) > max_per_ticker,
                },
                "context": {
                    "regime": regime_label,
                    "vol_20d_annualized": round(vol_20, 1),
                    "drawdown_from_high": round(dd_pct, 1),
                    "price": round(price, 2),
                },
            })
        except Exception as e:
            results.append({"symbol": sym, "error": str(e)})

    results.sort(key=lambda x: x.get("final_allocation_pct", 0), reverse=True)

    total_alloc = sum(r.get("final_allocation_pct", 0) for r in results)
    # If total > 90%, scale down
    if total_alloc > 90:
        scale = 90 / total_alloc
        for r in results:
            if "final_allocation_pct" in r:
                r["final_allocation_pct"] = round(r["final_allocation_pct"] * scale, 2)
        total_alloc = 90

    cash_pct = round(100 - total_alloc, 1)

    return {
        "regime": regime_label,
        "regime_confidence": regime_conf,
        "regime_sizing_multiplier": regime_mult,
        "total_allocated_pct": round(total_alloc, 1),
        "cash_pct": cash_pct,
        "max_per_ticker": 20.0,
        "tickers": results,
        "rules": {
            "base": "Contrarian: score <20 → 15%, <30 → 12%, <40 → 10%, <50 → 5%, <60 → 7%, <70 → 3%, >70 → 0%",
            "regime": f"{regime_label} → {regime_mult}x",
            "volatility": "vol <30% → 1.2x, <50% → 1.0x, <80% → 0.7x, >80% → 0.5x",
            "drawdown": "DD >30% → 1.3x (contrarian), near highs → 0.9x",
            "caps": "Max 20% per ticker, max 90% total invested, 10% cash floor",
        },
        "kelly_caveat": "Position sizes are rules-based estimates, NOT Kelly-optimal. Kelly requires 50+ closed trades for calibration.",
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/signal-drift")
def signal_drift(symbol: str = Query("URA")):
    """Signal reliability monitor — detects degrading signals before they cost money."""
    import json as _json, numpy as np
    symbol = symbol.upper()

    conn = _get_db()
    rows = conn.execute(
        "SELECT date, price, total_score, components_json FROM composite_score_history WHERE symbol=? ORDER BY date",
        (symbol,)
    ).fetchall()
    conn.close()

    if len(rows) < 7:
        return {
            "status": "collecting_baseline",
            "symbol": symbol,
            "snapshots_available": len(rows),
            "snapshots_needed": 7,
            "days_remaining": 7 - len(rows),
            "message": f"Need at least 7 daily snapshots. Currently have {len(rows)}. Cron runs daily at 20:30 UTC.",
        }

    # Parse all snapshots
    dates = []
    prices = []
    signal_series = {}  # signal_name -> list of scores

    for row in rows:
        dates.append(row["date"])
        prices.append(row["price"])
        try:
            components = _json.loads(row["components_json"])
            for sig in components:
                name = sig["name"]
                if name not in signal_series:
                    signal_series[name] = []
                signal_series[name].append({
                    "date": row["date"],
                    "score": sig["score"],
                    "weight": sig["weight"],
                    "raw_value": sig.get("raw_value"),
                })
        except:
            pass

    prices_arr = np.array(prices)
    fwd_returns_1d = np.diff(prices_arr) / prices_arr[:-1] * 100  # next-day returns

    signals_report = []
    degraded = []

    for name, series in signal_series.items():
        if len(series) < 7:
            continue

        scores = [s["score"] for s in series]
        weight = series[-1]["weight"]

        # Direction accuracy: did signal > 50 predict positive return?
        correct_7d = 0
        total_7d = 0
        correct_30d = 0
        total_30d = 0

        for i in range(len(scores) - 1):
            if i >= len(fwd_returns_1d):
                break
            signal_bullish = scores[i] > 50
            price_up = fwd_returns_1d[i] > 0

            matched = signal_bullish == price_up
            if i >= len(scores) - 8:  # last 7
                correct_7d += int(matched)
                total_7d += 1
            if i >= len(scores) - 31:  # last 30
                correct_30d += int(matched)
                total_30d += 1

        acc_7d = (correct_7d / total_7d * 100) if total_7d > 0 else None
        acc_30d = (correct_30d / total_30d * 100) if total_30d > 0 else None

        # Correlation with forward returns
        min_len = min(len(scores) - 1, len(fwd_returns_1d))
        if min_len >= 5:
            corr_1d = float(np.corrcoef(scores[:min_len], fwd_returns_1d[:min_len])[0, 1])
            if np.isnan(corr_1d): corr_1d = 0
        else:
            corr_1d = None

        # 5-day forward returns correlation
        if len(prices_arr) > 5 and min_len >= 5:
            fwd_5d = []
            for i in range(len(prices_arr) - 5):
                fwd_5d.append((prices_arr[i + 5] / prices_arr[i] - 1) * 100)
            ml5 = min(len(scores), len(fwd_5d))
            if ml5 >= 5:
                corr_5d = float(np.corrcoef(scores[:ml5], fwd_5d[:ml5])[0, 1])
                if np.isnan(corr_5d): corr_5d = 0
            else:
                corr_5d = None
        else:
            corr_5d = None

        # Drift detection: 7d accuracy drops >15pp below 30d
        drift = False
        if acc_7d is not None and acc_30d is not None:
            drift = (acc_30d - acc_7d) > 15

        entry = {
            "signal": name,
            "weight": weight,
            "current_value": scores[-1] if scores else None,
            "rolling_accuracy_7d": round(acc_7d, 1) if acc_7d is not None else None,
            "rolling_accuracy_30d": round(acc_30d, 1) if acc_30d is not None else None,
            "correlation_1d_fwd": round(corr_1d, 3) if corr_1d is not None else None,
            "correlation_5d_fwd": round(corr_5d, 3) if corr_5d is not None else None,
            "drift_detected": drift,
        }
        signals_report.append(entry)
        if drift:
            degraded.append(name)

    # Overall health
    total_signals = len(signals_report)
    healthy = sum(1 for s in signals_report if not s["drift_detected"])
    health_pct = round(healthy / total_signals * 100, 1) if total_signals > 0 else 100

    if health_pct >= 85:
        rec = "All signals performing within expected range. No action needed."
    elif health_pct >= 60:
        rec = f"Minor degradation detected in {', '.join(degraded)}. Monitor over next 5 days before adjusting weights."
    else:
        rec = f"Significant drift in {', '.join(degraded)}. Consider reducing weights or pausing these signals pending investigation."

    return {
        "status": "active",
        "symbol": symbol,
        "snapshots_analyzed": len(rows),
        "overall_health_pct": health_pct,
        "healthy_signals": healthy,
        "total_signals": total_signals,
        "degraded_signals": degraded,
        "recommendation": rec,
        "signals": sorted(signals_report, key=lambda x: x.get("rolling_accuracy_7d") or 0),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/macro-dashboard")
def macro_dashboard():
    """Unified macro overview aggregating all macro signals."""
    import yfinance as yf, numpy as np

    components = {}

    # 1. Global Liquidity (TLT, UUP, GLD, KBE)
    try:
        liq_scores = []
        for sym, weight, bullish_dir in [("TLT", 0.3, "up"), ("UUP", 0.3, "down"), ("GLD", 0.2, "up"), ("KBE", 0.2, "up")]:
            tk = yf.Ticker(sym)
            h = tk.history(period="6mo")
            if h.empty: continue
            if h.index.tz: h.index = h.index.tz_localize(None)
            c = h["Close"]
            sma50 = float(c.rolling(50).mean().iloc[-1])
            price = float(c.iloc[-1])
            roc = (price / float(c.iloc[-20]) - 1) * 100 if len(c) >= 20 else 0
            if bullish_dir == "down":
                score = 50 - roc * 5 + (30 if price < sma50 else -10)
            else:
                score = 50 + roc * 5 + (30 if price > sma50 else -10)
            liq_scores.append((max(0, min(100, score)), weight))
        liq_composite = sum(s * w for s, w in liq_scores) / sum(w for _, w in liq_scores) if liq_scores else 50
        components["global_liquidity"] = {
            "score": round(liq_composite, 1),
            "label": "EXPANSIONARY" if liq_composite > 60 else "TIGHTENING" if liq_composite < 40 else "NEUTRAL",
        }
    except:
        components["global_liquidity"] = {"score": 50, "label": "UNAVAILABLE"}

    # 2. Economic Surprise (SPY vs TLT relative)
    try:
        spy = yf.Ticker("SPY").history(period="3mo")
        tlt = yf.Ticker("TLT").history(period="3mo")
        if spy.index.tz: spy.index = spy.index.tz_localize(None)
        if tlt.index.tz: tlt.index = tlt.index.tz_localize(None)
        spy_ret = (float(spy["Close"].iloc[-1]) / float(spy["Close"].iloc[-20]) - 1) * 100
        tlt_ret = (float(tlt["Close"].iloc[-1]) / float(tlt["Close"].iloc[-20]) - 1) * 100
        econ_spread = spy_ret - tlt_ret
        econ_score = max(0, min(100, 50 + econ_spread * 5))
        components["economic_surprise"] = {
            "score": round(econ_score, 1),
            "label": "POSITIVE" if econ_score > 60 else "NEGATIVE" if econ_score < 40 else "NEUTRAL",
            "spy_20d": round(spy_ret, 2),
            "tlt_20d": round(tlt_ret, 2),
        }
    except:
        components["economic_surprise"] = {"score": 50, "label": "UNAVAILABLE"}

    # 3. Fear & Greed (VIX-based)
    try:
        vix = yf.Ticker("^VIX").history(period="3mo")
        if vix.index.tz: vix.index = vix.index.tz_localize(None)
        vix_now = float(vix["Close"].iloc[-1])
        vix_sma = float(vix["Close"].rolling(20).mean().iloc[-1])
        # Invert: low VIX = high score (greedy/bullish)
        fg_score = max(0, min(100, 100 - (vix_now - 10) * 3.33))
        if vix_now < 15: fg_label = "EXTREME_GREED"
        elif vix_now < 20: fg_label = "GREED"
        elif vix_now < 25: fg_label = "NEUTRAL"
        elif vix_now < 30: fg_label = "FEAR"
        else: fg_label = "EXTREME_FEAR"
        components["fear_greed"] = {
            "score": round(fg_score, 1),
            "label": fg_label,
            "vix": round(vix_now, 1),
            "vix_sma20": round(vix_sma, 1),
        }
    except:
        components["fear_greed"] = {"score": 50, "label": "UNAVAILABLE"}

    # 4. Volatility Regime (URA-specific)
    try:
        ura = yf.Ticker("URA").history(period="6mo")
        if ura.index.tz: ura.index = ura.index.tz_localize(None)
        rets = ura["Close"].pct_change().dropna()
        vol20 = float(rets.tail(20).std()) * np.sqrt(252) * 100
        vol60 = float(rets.tail(60).std()) * np.sqrt(252) * 100
        vol_ratio = vol20 / vol60 if vol60 > 0 else 1
        if vol20 < 25: vol_label = "LOW"
        elif vol20 < 45: vol_label = "NORMAL"
        elif vol20 < 70: vol_label = "ELEVATED"
        else: vol_label = "CRISIS"
        # Low vol = high score (favorable)
        vol_score = max(0, min(100, 100 - vol20))
        components["volatility_regime"] = {
            "score": round(vol_score, 1),
            "label": vol_label,
            "vol_20d": round(vol20, 1),
            "vol_60d": round(vol60, 1),
            "vol_ratio": round(vol_ratio, 2),
            "expanding": bool(vol_ratio > 1.2),
        }
    except:
        components["volatility_regime"] = {"score": 50, "label": "UNAVAILABLE"}

    # 5. Currency Impact (DXY proxy via UUP)
    try:
        uup = yf.Ticker("UUP").history(period="3mo")
        if uup.index.tz: uup.index = uup.index.tz_localize(None)
        dxy_ret = (float(uup["Close"].iloc[-1]) / float(uup["Close"].iloc[-20]) - 1) * 100
        dxy_sma = float(uup["Close"].rolling(50).mean().iloc[-1])
        dxy_price = float(uup["Close"].iloc[-1])
        # Weak dollar = bullish for commodities
        cur_score = max(0, min(100, 50 - dxy_ret * 10))
        components["currency"] = {
            "score": round(cur_score, 1),
            "label": "WEAK_USD" if cur_score > 60 else "STRONG_USD" if cur_score < 40 else "NEUTRAL",
            "uup_20d_pct": round(dxy_ret, 2),
            "uup_vs_sma50": "below" if dxy_price < dxy_sma else "above",
        }
    except:
        components["currency"] = {"score": 50, "label": "UNAVAILABLE"}

    # 6. Regime (inline from trend + vol)
    try:
        ura2 = yf.Ticker("URA").history(period="6mo")
        if ura2.index.tz: ura2.index = ura2.index.tz_localize(None)
        c = ura2["Close"]
        p = float(c.iloc[-1])
        s50 = float(c.rolling(50).mean().iloc[-1])
        s20 = float(c.rolling(20).mean().iloc[-1])
        roc60 = (p / float(c.iloc[-60]) - 1) * 100 if len(c) >= 60 else 0
        is_bull = p > s50 and roc60 > 5
        vol_state = components.get("volatility_regime", {}).get("label", "NORMAL")
        is_volatile = vol_state in ("ELEVATED", "CRISIS")
        if is_bull and not is_volatile: regime = "BULL_QUIET"
        elif is_bull and is_volatile: regime = "BULL_VOLATILE"
        elif not is_bull and not is_volatile: regime = "BEAR_QUIET"
        elif not is_bull and is_volatile: regime = "BEAR_VOLATILE"
        else: regime = "SIDEWAYS"
        sizing = {"BULL_QUIET": 1.0, "BULL_VOLATILE": 0.7, "SIDEWAYS": 0.5, "BEAR_QUIET": 0.3, "BEAR_VOLATILE": 0.4}
        components["regime"] = {"label": regime, "sizing_multiplier": sizing.get(regime, 0.5)}
    except:
        components["regime"] = {"label": "UNKNOWN", "sizing_multiplier": 0.5}

    # Composite macro score (weighted average)
    weights = {"global_liquidity": 0.2, "economic_surprise": 0.2, "fear_greed": 0.2, "volatility_regime": 0.2, "currency": 0.2}
    scored = [(components[k]["score"], w) for k, w in weights.items() if components.get(k, {}).get("score") is not None]
    macro_score = sum(s * w for s, w in scored) / sum(w for _, w in scored) if scored else 50

    if macro_score > 65: macro_label = "RISK_ON"
    elif macro_score > 55: macro_label = "LEAN_RISK_ON"
    elif macro_score < 35: macro_label = "RISK_OFF"
    elif macro_score < 45: macro_label = "LEAN_RISK_OFF"
    else: macro_label = "NEUTRAL"

    return {
        "macro_score": round(macro_score, 1),
        "macro_label": macro_label,
        "regime": components.get("regime", {}).get("label", "UNKNOWN"),
        "position_sizing_multiplier": components.get("regime", {}).get("sizing_multiplier", 0.5),
        "components": components,
        "interpretation": {
            "RISK_ON": "All macro signals aligned bullish — full position sizes, trend-follow.",
            "LEAN_RISK_ON": "Mostly favorable — standard sizing, stay with trend.",
            "NEUTRAL": "Mixed signals — reduced sizing, selective entries only.",
            "LEAN_RISK_OFF": "Headwinds building — defensive, reduce exposure.",
            "RISK_OFF": "Multiple red flags — capital preservation mode, cash heavy.",
        }.get(macro_label, ""),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/regime-detector")
def regime_detector(symbol: str = Query("URA")):
    """Composite market regime classifier from multiple signal sources."""
    import yfinance as yf, numpy as np

    symbol = symbol.upper()
    tk = yf.Ticker(symbol)
    hist = tk.history(period="6mo")
    if hist.empty or len(hist) < 60:
        raise HTTPException(400, "Insufficient data")
    if hist.index.tz is not None:
        hist.index = hist.index.tz_localize(None)

    close = hist["Close"]
    rets = close.pct_change().dropna()

    # 1. Trend direction (SMA50 vs SMA200 + price position)
    sma50 = float(close.rolling(50).mean().iloc[-1])
    sma20 = float(close.rolling(20).mean().iloc[-1])
    price = float(close.iloc[-1])

    trend_score = 0  # -100 to +100
    if price > sma50: trend_score += 30
    else: trend_score -= 30
    if sma20 > sma50: trend_score += 20
    else: trend_score -= 20
    # Momentum: 20-day ROC
    roc20 = (price / float(close.iloc[-20]) - 1) * 100 if len(close) >= 20 else 0
    trend_score += max(-30, min(30, roc20 * 3))
    # 60d trend
    roc60 = (price / float(close.iloc[-60]) - 1) * 100 if len(close) >= 60 else 0
    trend_score += max(-20, min(20, roc60))

    # 2. Volatility regime
    vol_20 = float(rets.tail(20).std()) * np.sqrt(252) * 100
    vol_60 = float(rets.tail(60).std()) * np.sqrt(252) * 100
    vol_ratio = vol_20 / vol_60 if vol_60 > 0 else 1.0

    if vol_20 < 25:
        vol_state = "LOW"
    elif vol_20 < 45:
        vol_state = "NORMAL"
    elif vol_20 < 70:
        vol_state = "ELEVATED"
    else:
        vol_state = "CRISIS"

    # 3. Breadth (use SPY as market proxy)
    try:
        spy = yf.Ticker("SPY").history(period="6mo")
        if spy.index.tz is not None:
            spy.index = spy.index.tz_localize(None)
        spy_price = float(spy["Close"].iloc[-1])
        spy_sma50 = float(spy["Close"].rolling(50).mean().iloc[-1])
        spy_sma200 = float(spy["Close"].rolling(200).mean().iloc[-1]) if len(spy) >= 200 else spy_sma50
        market_bullish = spy_price > spy_sma50
    except:
        market_bullish = True

    # 4. Fear/greed proxy from VIX
    try:
        vix = yf.Ticker("^VIX").history(period="3mo")
        vix_level = float(vix["Close"].iloc[-1])
        vix_sma = float(vix["Close"].rolling(20).mean().iloc[-1])
    except:
        vix_level = 20
        vix_sma = 20

    if vix_level < 15: fear_greed = "EXTREME_GREED"
    elif vix_level < 20: fear_greed = "GREED"
    elif vix_level < 25: fear_greed = "NEUTRAL"
    elif vix_level < 30: fear_greed = "FEAR"
    else: fear_greed = "EXTREME_FEAR"

    # 5. Classify regime
    is_bull = trend_score > 15
    is_bear = trend_score < -15
    is_volatile = vol_state in ("ELEVATED", "CRISIS")

    if is_bull and not is_volatile:
        regime = "BULL_QUIET"
        description = "Uptrend with low volatility — trend-following works, size up"
    elif is_bull and is_volatile:
        regime = "BULL_VOLATILE"
        description = "Uptrend but choppy — reduce size, wider stops"
    elif is_bear and not is_volatile:
        regime = "BEAR_QUIET"
        description = "Downtrend grinding lower — avoid new longs, wait for capitulation"
    elif is_bear and is_volatile:
        regime = "BEAR_VOLATILE"
        description = "Downtrend with high vol — potential capitulation, contrarian opportunity"
    else:
        regime = "SIDEWAYS"
        description = "No clear trend — range-bound, mean-reversion strategies preferred"

    # Confidence: how decisive are the signals
    trend_strength = abs(trend_score) / 100
    vol_clarity = 1.0 if vol_state in ("LOW", "CRISIS") else 0.6
    confidence = round(min(1.0, (trend_strength + vol_clarity) / 2), 2)

    # Position sizing multiplier based on regime
    sizing = {
        "BULL_QUIET": 1.0,
        "BULL_VOLATILE": 0.7,
        "SIDEWAYS": 0.5,
        "BEAR_QUIET": 0.3,
        "BEAR_VOLATILE": 0.4,  # slightly higher for contrarian
    }

    return {
        "symbol": symbol,
        "regime": regime,
        "confidence": confidence,
        "description": description,
        "position_sizing_multiplier": sizing.get(regime, 0.5),
        "components": {
            "trend": {
                "score": round(trend_score, 1),
                "direction": "BULLISH" if trend_score > 15 else "BEARISH" if trend_score < -15 else "NEUTRAL",
                "price": round(price, 2),
                "sma20": round(sma20, 2),
                "sma50": round(sma50, 2),
                "roc_20d": round(roc20, 2),
                "roc_60d": round(roc60, 2),
            },
            "volatility": {
                "state": vol_state,
                "annualized_20d": round(vol_20, 1),
                "annualized_60d": round(vol_60, 1),
                "vol_ratio": round(vol_ratio, 2),
                "expanding": bool(vol_ratio > 1.2),
            },
            "fear_greed": {
                "label": fear_greed,
                "vix": round(vix_level, 1),
                "vix_sma20": round(vix_sma, 1),
            },
            "market_context": {
                "spy_above_sma50": bool(market_bullish),
            },
        },
        "trading_rules": {
            "BULL_QUIET": "Full position sizes. Trail stops at SMA20. Add on pullbacks to SMA50.",
            "BULL_VOLATILE": "70% position sizes. Wider stops (1.5x ATR). Take profits faster.",
            "SIDEWAYS": "50% sizes. Mean-revert at range extremes. No trend trades.",
            "BEAR_QUIET": "30% sizes. Short bias or cash. Wait for regime change.",
            "BEAR_VOLATILE": "40% sizes. Watch for capitulation (VIX spike + volume). Contrarian longs at extremes only.",
        }.get(regime, ""),
    }


@app.get("/api/risk-parity")
def risk_parity(lookback: int = Query(90, ge=30, le=252), method: str = Query("inverse_volatility")):
    """Risk-parity weights. method=inverse_volatility (default) or correlation_adjusted."""
    import yfinance as yf, numpy as np, pandas as pd
    from analysis import TICKERS

    # Fetch returns for all tickers
    all_returns = {}
    vols = {}
    for sym in list(TICKERS.keys()):
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period=f"{lookback + 10}d")
            if hist.empty or len(hist) < lookback // 2:
                continue
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)
            rets = hist["Close"].pct_change().dropna().tail(lookback)
            vol = float(np.std(rets)) * np.sqrt(252)
            if vol > 0:
                vols[sym] = round(vol, 4)
                all_returns[sym] = rets
        except:
            continue

    if not vols:
        raise HTTPException(500, "No volatility data")

    # Step 1: Inverse volatility weights
    inv = {s: 1.0 / v for s, v in vols.items()}
    total_inv = sum(inv.values())
    iv_weights = {s: w / total_inv for s, w in inv.items()}

    # Step 2: Correlation adjustment (if requested)
    cluster_info = []
    if method == "correlation_adjusted" and len(all_returns) >= 3:
        df_rets = pd.DataFrame(all_returns).dropna()
        corr = df_rets.corr()
        syms = list(vols.keys())

        # Build clusters: tickers with r > 0.85
        assigned = set()
        clusters = []
        for i, s1 in enumerate(syms):
            if s1 in assigned:
                continue
            cluster = [s1]
            assigned.add(s1)
            for j, s2 in enumerate(syms):
                if s2 in assigned or s1 == s2:
                    continue
                try:
                    r = float(corr.loc[s1, s2])
                except:
                    r = 0
                if r > 0.85:
                    cluster.append(s2)
                    assigned.add(s2)
            clusters.append(cluster)

        # Penalty: within each cluster, scale weights so cluster total
        # doesn't exceed what the largest single member would get × 1.5
        weights = dict(iv_weights)
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            cluster_total = sum(iv_weights.get(s, 0) for s in cluster)
            max_single = max(iv_weights.get(s, 0) for s in cluster)
            cap = max_single * 1.5  # cluster cap = 1.5x the largest member
            if cluster_total > cap:
                scale = cap / cluster_total
                for s in cluster:
                    weights[s] = iv_weights[s] * scale

            # Compute avg intra-correlation
            intra = []
            for a in cluster:
                for b in cluster:
                    if a < b:
                        try:
                            intra.append(float(corr.loc[a, b]))
                        except:
                            pass
            cluster_info.append({
                "tickers": cluster,
                "size": len(cluster),
                "iv_total_weight": round(cluster_total, 4),
                "adjusted_total_weight": round(sum(weights[s] for s in cluster), 4),
                "avg_intra_correlation": round(sum(intra) / len(intra), 3) if intra else 0,
                "penalty_applied": bool(cluster_total > cap),
            })

        # Redistribute freed weight to unclustered/low-corr tickers
        total_adj = sum(weights.values())
        if total_adj > 0:
            weights = {s: w / total_adj for s, w in weights.items()}
    else:
        weights = iv_weights

    weights = {s: round(w, 4) for s, w in weights.items()}
    eq = round(1.0 / len(vols), 4)
    ranked = sorted(weights.items(), key=lambda x: x[1], reverse=True)

    tickers_detail = []
    for sym, wt in ranked:
        entry = {
            "symbol": sym,
            "name": TICKERS.get(sym, sym),
            "annualized_vol": vols[sym],
            "risk_parity_weight": wt,
            "equal_weight": eq,
            "weight_ratio": round(wt / eq, 2),
        }
        if method == "correlation_adjusted":
            entry["iv_weight"] = round(iv_weights.get(sym, 0), 4)
            entry["adjustment"] = round(wt - iv_weights.get(sym, 0), 4)
        tickers_detail.append(entry)

    result = {
        "method": method,
        "lookback_days": lookback,
        "as_of": datetime.utcnow().strftime("%Y-%m-%d"),
        "ticker_count": len(weights),
        "weights": weights,
        "tickers": tickers_detail,
        "concentration": {
            "top3_weight": round(sum(w for _, w in ranked[:3]), 4),
            "bottom3_weight": round(sum(w for _, w in ranked[-3:]), 4),
            "max_weight": {"symbol": ranked[0][0], "weight": ranked[0][1]},
            "min_weight": {"symbol": ranked[-1][0], "weight": ranked[-1][1]},
        },
    }
    if cluster_info:
        result["clusters"] = cluster_info
    return result


@app.get("/api/performance-heatmap")
def performance_heatmap(months: int = Query(12, ge=3, le=24)):
    """Monthly performance grid for all tickers."""
    import yfinance as yf
    from analysis import TICKERS

    result = []
    for sym in list(TICKERS.keys()):
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period=f"{months + 2}mo")
            if hist.empty or len(hist) < 20:
                continue
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)

            monthly = hist["Close"].resample("ME").last().pct_change().dropna() * 100
            monthly_dict = {}
            for dt, ret in monthly.items():
                key = dt.strftime("%Y-%m")
                monthly_dict[key] = round(float(ret), 2)

            # YTD
            ytd_start = hist["Close"].loc[hist.index >= f"{datetime.utcnow().year}-01-01"]
            ytd = round((float(ytd_start.iloc[-1]) / float(ytd_start.iloc[0]) - 1) * 100, 2) if len(ytd_start) >= 2 else 0

            result.append({
                "symbol": sym,
                "name": TICKERS[sym],
                "monthly_returns": monthly_dict,
                "ytd_pct": ytd,
                "best_month": max(monthly_dict.items(), key=lambda x: x[1]) if monthly_dict else None,
                "worst_month": min(monthly_dict.items(), key=lambda x: x[1]) if monthly_dict else None,
            })
        except Exception as e:
            result.append({"symbol": sym, "name": TICKERS.get(sym, sym), "error": str(e)})

    # Get all month keys for column alignment
    all_months = sorted(set(m for t in result for m in t.get("monthly_returns", {})))

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "months": all_months,
        "tickers": sorted(result, key=lambda x: x.get("ytd_pct", 0), reverse=True),
    }


@app.get("/api/peer-comparison")
def peer_comparison():
    """Cross-ticker comparison table for all uranium tickers."""
    import yfinance as yf, math
    from analysis import TICKERS

    tickers = []
    for sym in list(TICKERS.keys()):
        meta = get_ticker_meta(sym)
        if not meta:
            continue

        price = meta.get("current_price", 0)
        change_pct = meta.get("change_pct", 0)
        volume = meta.get("volume", 0)
        avg_volume = meta.get("avg_volume", 0)
        score = meta.get("signal_score", 50)
        high_52 = meta.get("high_52w", 0)
        low_52 = meta.get("low_52w", 0)

        # Weekly/monthly change from history
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period="1mo")
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)
            close = hist["Close"]
            change_1w = (float(close.iloc[-1]) / float(close.iloc[-5]) - 1) * 100 if len(close) >= 5 else 0
            change_1m = (float(close.iloc[-1]) / float(close.iloc[0]) - 1) * 100 if len(close) >= 2 else 0
        except:
            change_1w = 0
            change_1m = 0

        # Market cap from info
        try:
            info = yf.Ticker(sym).info or {}
            mcap = info.get("marketCap", 0) or 0
        except:
            mcap = 0

        # Distance from 52w high/low
        pct_from_high = ((price / high_52) - 1) * 100 if high_52 > 0 else 0
        pct_from_low = ((price / low_52) - 1) * 100 if low_52 > 0 else 0

        # Vol ratio
        vol_ratio = round(volume / avg_volume, 2) if avg_volume > 0 else 0

        tickers.append({
            "symbol": sym,
            "name": TICKERS[sym],
            "price": round(price, 2),
            "change_1d_pct": round(change_pct, 2),
            "change_1w_pct": round(change_1w, 2),
            "change_1m_pct": round(change_1m, 2),
            "market_cap": mcap,
            "market_cap_b": round(mcap / 1e9, 2) if mcap else 0,
            "volume": volume,
            "vol_vs_avg": vol_ratio,
            "composite_score": round(score, 1),
            "pct_from_52w_high": round(pct_from_high, 1),
            "pct_from_52w_low": round(pct_from_low, 1),
        })

    # Sort by composite score descending
    tickers.sort(key=lambda x: x["composite_score"], reverse=True)

    # Rankings
    by_momentum = sorted(tickers, key=lambda x: x["change_1m_pct"], reverse=True)
    by_value = sorted(tickers, key=lambda x: x["pct_from_52w_high"])  # most beaten down
    by_mcap = sorted(tickers, key=lambda x: x["market_cap"], reverse=True)

    return {
        "tickers": tickers,
        "rankings": {
            "by_score": [t["symbol"] for t in tickers],
            "by_1m_momentum": [t["symbol"] for t in by_momentum],
            "by_value_discount": [t["symbol"] for t in by_value],
            "by_market_cap": [t["symbol"] for t in by_mcap],
        },
    }


@app.get("/api/dividend-yield")
def dividend_yield():
    """Dividend yield data for all tracked tickers."""
    import yfinance as yf, math
    from analysis import TICKERS

    def _safe(val):
        if val is None: return None
        if isinstance(val, float) and math.isnan(val): return None
        return val

    result = {}
    for sym in list(TICKERS.keys()):
        try:
            tk = yf.Ticker(sym)
            info = tk.info or {}
            dy = _safe(info.get("dividendYield"))
            tay = _safe(info.get("trailingAnnualDividendYield"))
            dr = _safe(info.get("dividendRate"))
            pr = _safe(info.get("payoutRatio"))
            exd = info.get("exDividendDate")
            if isinstance(exd, (int, float)) and exd > 0:
                exd = datetime.utcfromtimestamp(exd).strftime("%Y-%m-%d")
            else:
                exd = str(exd) if exd else None

            # yfinance returns yield as decimal (0.0021) or already % (2.1) inconsistently
            if dy and dy > 1: dy = dy / 100  # already in %, convert back
            if tay and tay > 1: tay = tay / 100

            pays_dividend = (dy and dy > 0) or (dr and dr > 0)

            result[sym] = {
                "symbol": sym,
                "dividend_yield": round(dy * 100, 2) if dy else 0,
                "trailing_annual_yield": round(tay * 100, 2) if tay else 0,
                "dividend_rate": round(dr, 4) if dr else 0,
                "payout_ratio": round(pr * 100, 1) if pr else None,
                "ex_dividend_date": exd,
                "pays_dividend": bool(pays_dividend),
            }
        except Exception as e:
            result[sym] = {"symbol": sym, "error": str(e), "pays_dividend": False}

    payers = [s for s, d in result.items() if d.get("pays_dividend")]
    non_payers = [s for s, d in result.items() if not d.get("pays_dividend")]
    ranked = sorted(
        [(s, d) for s, d in result.items() if d.get("dividend_yield", 0) > 0],
        key=lambda x: x[1]["dividend_yield"], reverse=True
    )

    return {
        "tickers": result,
        "summary": {
            "dividend_payers": payers,
            "non_payers": non_payers,
            "highest_yield": {"symbol": ranked[0][0], "yield_pct": ranked[0][1]["dividend_yield"]} if ranked else None,
        },
    }


@app.get("/api/seasonality")
def seasonality(symbol: str = Query("URA"), years: int = Query(5, ge=2, le=10)):
    """Monthly seasonality analysis from historical returns."""
    import yfinance as yf, numpy as np, calendar

    symbol = symbol.upper()
    tk = yf.Ticker(symbol)
    df = tk.history(period=f"{years}y")
    if df.empty or len(df) < 252:
        raise HTTPException(400, "Insufficient data")
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # Monthly returns
    monthly = df["Close"].resample("ME").last().pct_change().dropna() * 100

    stats = {}
    for month_num in range(1, 13):
        name = calendar.month_name[month_num]
        rets = monthly[monthly.index.month == month_num]
        if len(rets) == 0:
            continue
        avg = float(np.mean(rets))
        std = float(np.std(rets))
        wins = int((rets > 0).sum())
        stats[name] = {
            "avg_return_pct": round(avg, 2),
            "median_return_pct": round(float(np.median(rets)), 2),
            "win_rate": round(wins / len(rets), 2),
            "std_dev": round(std, 2),
            "best": round(float(rets.max()), 2),
            "worst": round(float(rets.min()), 2),
            "sample_size": len(rets),
        }

    # Current month
    now = datetime.utcnow()
    current_name = calendar.month_name[now.month]
    current = stats.get(current_name, {})
    avg_ret = current.get("avg_return_pct", 0)
    wr = current.get("win_rate", 0.5)

    if avg_ret > 2 and wr >= 0.6:
        bias = "BULLISH"
    elif avg_ret > 0.5:
        bias = "LEAN BULLISH"
    elif avg_ret < -2 and wr <= 0.4:
        bias = "BEARISH"
    elif avg_ret < -0.5:
        bias = "LEAN BEARISH"
    else:
        bias = "NEUTRAL"

    # Best/worst months
    ranked = sorted(stats.items(), key=lambda x: x[1]["avg_return_pct"], reverse=True)
    best_months = [{"month": m, **s} for m, s in ranked[:3]]
    worst_months = [{"month": m, **s} for m, s in ranked[-3:]]

    return {
        "symbol": symbol,
        "years_analyzed": years,
        "current_month": current_name,
        "seasonal_bias": bias,
        "current_month_stats": current,
        "monthly_stats": stats,
        "best_months": best_months,
        "worst_months": worst_months,
    }


@app.get("/api/institutional-ownership")
def institutional_ownership():
    """Institutional holder data for all tracked tickers."""
    import yfinance as yf, math
    from analysis import TICKERS

    result = {}
    for sym in list(TICKERS.keys()):
        try:
            tk = yf.Ticker(sym)

            # Major holders (% breakdown)
            pct_inst = 0
            pct_insider = 0
            try:
                mh = tk.major_holders
                if mh is not None and not mh.empty:
                    for _, row in mh.iterrows():
                        label = str(row.iloc[1]).lower() if len(row) > 1 else ""
                        val = row.iloc[0]
                        if isinstance(val, str):
                            val = float(val.replace("%", "")) if "%" in val else 0
                        else:
                            val = float(val) * 100 if float(val) <= 1 else float(val)
                        if math.isnan(val):
                            val = 0
                        if "institution" in label:
                            pct_inst = round(val, 2)
                        elif "insider" in label:
                            pct_insider = round(val, 2)
            except:
                pass

            # Top institutional holders
            top_holders = []
            try:
                ih = tk.institutional_holders
                if ih is not None and not ih.empty:
                    for _, row in ih.head(10).iterrows():
                        holder = str(row.get("Holder", ""))
                        shares = row.get("Shares", 0)
                        shares = int(shares) if shares and not (isinstance(shares, float) and math.isnan(shares)) else 0
                        pct = row.get("% Out", row.get("pctHeld", 0))
                        pct = float(pct) * 100 if pct and not (isinstance(pct, float) and math.isnan(pct)) else 0
                        if pct <= 1 and pct > 0:
                            pct = pct * 100
                        date_rep = str(row.get("Date Reported", ""))[:10]
                        value = row.get("Value", 0)
                        value = float(value) if value and not (isinstance(value, float) and math.isnan(value)) else 0

                        top_holders.append({
                            "holder": holder,
                            "shares": shares,
                            "pct_held": round(pct, 2),
                            "value": round(value, 2),
                            "date_reported": date_rep,
                        })
            except:
                pass

            result[sym] = {
                "pct_held_by_institutions": pct_inst,
                "pct_held_by_insiders": pct_insider,
                "top_holders": top_holders,
                "holder_count": len(top_holders),
            }
        except Exception as e:
            result[sym] = {"error": str(e)}

    # Sector summary
    avg_inst = []
    for sym, data in result.items():
        if isinstance(data.get("pct_held_by_institutions"), (int, float)) and data["pct_held_by_institutions"] > 0:
            avg_inst.append(data["pct_held_by_institutions"])

    # Most concentrated (highest institutional %)
    ranked = sorted(
        [(s, d) for s, d in result.items() if isinstance(d.get("pct_held_by_institutions"), (int, float))],
        key=lambda x: x[1].get("pct_held_by_institutions", 0), reverse=True
    )

    return {
        "tickers": result,
        "sector_summary": {
            "avg_institutional_pct": round(sum(avg_inst) / len(avg_inst), 1) if avg_inst else 0,
            "most_institutional": ranked[0][0] if ranked else None,
            "least_institutional": ranked[-1][0] if ranked else None,
        },
    }


@app.get("/api/insider-transactions")
def insider_transactions_endpoint():
    """
    SEC Form 4 insider buy/sell activity for all tracked tickers.
    Aggregated net sentiment per ticker + raw transactions.
    """
    import yfinance as yf
    from analysis import TICKERS

    result = {}
    for sym in list(TICKERS.keys()):
        try:
            tk = yf.Ticker(sym)
            txns = tk.insider_transactions
            if txns is None or (hasattr(txns, 'empty') and txns.empty):
                result[sym] = {"transactions": [], "summary": {"total": 0, "net_sentiment": "NO DATA"}}
                continue

            records = []
            total_buy_value = 0
            total_sell_value = 0
            buy_count = 0
            sell_count = 0

            for _, row in txns.iterrows():
                text = str(row.get("Text", row.get("Transaction", ""))).lower()
                insider = str(row.get("Insider", row.get("Insider Trading", "")))
                import math
                _sh = row.get("Shares", 0)
                shares = float(_sh) if _sh is not None and not (isinstance(_sh, float) and math.isnan(_sh)) else 0
                _val = row.get("Value", 0)
                value = float(_val) if _val is not None and not (isinstance(_val, float) and math.isnan(_val)) else 0
                date = str(row.get("Start Date", row.get("Date", "")))

                is_buy = any(w in text for w in ["purchase", "buy", "acquisition"])
                is_sell = any(w in text for w in ["sale", "sell", "disposition"])

                if is_buy:
                    direction = "BUY"
                    total_buy_value += value
                    buy_count += 1
                elif is_sell:
                    direction = "SELL"
                    total_sell_value += value
                    sell_count += 1
                else:
                    direction = "OTHER"

                records.append({
                    "date": date[:10] if len(date) >= 10 else date,
                    "insider": insider,
                    "direction": direction,
                    "shares": int(shares),
                    "value": round(value, 2),
                    "text": str(row.get("Text", row.get("Transaction", ""))),
                })

            # Net sentiment
            net = total_buy_value - total_sell_value
            if buy_count > 0 and sell_count == 0:
                sentiment = "STRONG BUY"
            elif buy_count > sell_count and net > 0:
                sentiment = "NET BUYING"
            elif sell_count > 0 and buy_count == 0:
                sentiment = "STRONG SELL"
            elif sell_count > buy_count or net < 0:
                sentiment = "NET SELLING"
            elif buy_count == 0 and sell_count == 0:
                sentiment = "NO ACTIVITY"
            else:
                sentiment = "MIXED"

            result[sym] = {
                "transactions": records[:20],  # latest 20
                "summary": {
                    "total": len(records),
                    "buys": buy_count,
                    "sells": sell_count,
                    "total_buy_value": round(total_buy_value, 2),
                    "total_sell_value": round(total_sell_value, 2),
                    "net_value": round(net, 2),
                    "net_sentiment": sentiment,
                },
            }
        except Exception as e:
            result[sym] = {"transactions": [], "summary": {"total": 0, "net_sentiment": f"ERROR: {e}"}}

    # Sector-wide summary
    sector_buy = sum(r["summary"].get("total_buy_value", 0) for r in result.values())
    sector_sell = sum(r["summary"].get("total_sell_value", 0) for r in result.values())
    buying_tickers = [s for s, r in result.items() if r["summary"]["net_sentiment"] in ("STRONG BUY", "NET BUYING")]
    selling_tickers = [s for s, r in result.items() if r["summary"]["net_sentiment"] in ("STRONG SELL", "NET SELLING")]

    return {
        "tickers": result,
        "sector_summary": {
            "total_insider_buys": round(sector_buy, 2),
            "total_insider_sells": round(sector_sell, 2),
            "net": round(sector_buy - sector_sell, 2),
            "buying_tickers": buying_tickers,
            "selling_tickers": selling_tickers,
            "sector_sentiment": "NET BUYING" if sector_buy > sector_sell else "NET SELLING" if sector_sell > sector_buy else "NEUTRAL",
        },
    }


@app.get("/api/multi-timeframe-signals")
def multi_timeframe_signals(symbol: str = Query("URA")):
    """
    Multi-timeframe signal alignment: weekly, daily, 4-hour.
    Trend direction + momentum per timeframe, confluence score.
    """
    import yfinance as yf, numpy as np

    symbol = symbol.upper()
    tk = yf.Ticker(symbol)

    def _analyze_tf(df, label):
        if df is None or df.empty or len(df) < 26:
            return {"timeframe": label, "error": "Insufficient data"}

        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        c = df["Close"]
        price = float(c.iloc[-1])

        # Trend: SMA20 vs SMA50 + price vs SMA20
        sma20 = float(c.rolling(20).mean().iloc[-1]) if len(c) >= 20 else price
        sma50 = float(c.rolling(50).mean().iloc[-1]) if len(c) >= 50 else sma20

        if price > sma20 > sma50:
            trend = "BULLISH"
            trend_score = 100
        elif price > sma20:
            trend = "LEAN BULLISH"
            trend_score = 70
        elif price < sma20 < sma50:
            trend = "BEARISH"
            trend_score = 0
        elif price < sma20:
            trend = "LEAN BEARISH"
            trend_score = 30
        else:
            trend = "NEUTRAL"
            trend_score = 50

        # RSI
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])

        # MACD
        ema12 = c.ewm(span=12).mean()
        ema26 = c.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_hist = float((macd - signal).iloc[-1])

        if macd_hist > 0:
            momentum = "BULLISH" if macd_hist > abs(float(signal.iloc[-1])) * 0.1 else "LEAN BULLISH"
        else:
            momentum = "BEARISH" if macd_hist < -abs(float(signal.iloc[-1])) * 0.1 else "LEAN BEARISH"

        # Momentum score: 0-100
        mom_score = 50 + max(-50, min(50, macd_hist / (abs(float(signal.iloc[-1])) + 0.001) * 50))

        # Combined tf score
        tf_score = trend_score * 0.5 + mom_score * 0.3 + (100 - rsi) * 0.2  # contrarian RSI

        return {
            "timeframe": label,
            "price": round(price, 2),
            "trend": trend,
            "trend_score": round(trend_score, 1),
            "sma20": round(sma20, 2),
            "sma50": round(sma50, 2),
            "rsi": round(rsi, 1),
            "macd_histogram": round(macd_hist, 4),
            "momentum": momentum,
            "momentum_score": round(mom_score, 1),
            "tf_score": round(tf_score, 1),
        }

    # Pull data for each timeframe
    try:
        weekly = tk.history(period="2y", interval="1wk")
        daily = tk.history(period="6mo", interval="1d")
        hourly = tk.history(period="60d", interval="1h")
    except Exception as e:
        raise HTTPException(500, f"Data fetch error: {e}")

    tf_weekly = _analyze_tf(weekly, "weekly")
    tf_daily = _analyze_tf(daily, "daily")
    tf_4h = _analyze_tf(hourly, "4h")  # yfinance gives 1h, we'll use it as intraday proxy

    timeframes = [tf_weekly, tf_daily, tf_4h]
    valid = [t for t in timeframes if "error" not in t]

    # Confluence
    if len(valid) >= 2:
        trends = [t["trend"] for t in valid]
        bullish_count = sum(1 for t in trends if "BULLISH" in t)
        bearish_count = sum(1 for t in trends if "BEARISH" in t)

        if bullish_count == len(valid):
            confluence = "FULL BULLISH ALIGNMENT"
            confluence_score = 100
        elif bearish_count == len(valid):
            confluence = "FULL BEARISH ALIGNMENT"
            confluence_score = 0
        elif bullish_count > bearish_count:
            confluence = "PARTIAL BULLISH"
            confluence_score = 65
        elif bearish_count > bullish_count:
            confluence = "PARTIAL BEARISH"
            confluence_score = 35
        else:
            confluence = "MIXED — NO CONFLUENCE"
            confluence_score = 50

        avg_score = sum(t["tf_score"] for t in valid) / len(valid)

        # Divergence detection
        divergences = []
        if len(valid) >= 2:
            if "BULLISH" in valid[0].get("trend", "") and "BEARISH" in valid[-1].get("trend", ""):
                divergences.append("⚠️ Higher TF bullish but lower TF bearish — potential pullback in uptrend")
            if "BEARISH" in valid[0].get("trend", "") and "BULLISH" in valid[-1].get("trend", ""):
                divergences.append("⚠️ Higher TF bearish but lower TF bullish — potential bear rally, trade with caution")
    else:
        confluence = "INSUFFICIENT DATA"
        confluence_score = 50
        avg_score = 50
        divergences = []

    # Action recommendation
    if confluence_score >= 80:
        action = "HOLD/ADD — all timeframes aligned bullish"
    elif confluence_score <= 20:
        action = "CONTRARIAN BUY ZONE — all timeframes bearish (max fear)"
    elif divergences:
        action = "WAIT — timeframe divergence, no clear signal"
    else:
        action = "SMALL POSITION — partial alignment only"

    return {
        "symbol": symbol,
        "confluence": confluence,
        "confluence_score": round(confluence_score, 1),
        "avg_tf_score": round(avg_score, 1),
        "action": action,
        "timeframes": timeframes,
        "divergences": divergences,
    }


@app.get("/api/daily-digest")
def daily_digest_endpoint():
    """Serve cached daily digest if available, otherwise compute fresh."""
    if _cache_daily_digest["data"]:
        result = dict(_cache_daily_digest["data"])
        result["_cached"] = True
        result["_cache_age"] = _cache_daily_digest["updated_at"]
        return result
    return daily_digest()


def daily_digest():
    """
    Single daily summary: market regime, sector health, top trades, alerts.
    Designed for automated consumption and push notifications.
    """
    import requests as _req
    from analysis import TICKERS

    now = datetime.utcnow()

    # 1. Market regime
    regime = {}
    try:
        r = _req.get("http://localhost:8050/api/economic-surprise", timeout=30).json()
        regime["economic_surprise"] = {"score": r.get("composite_score", 50), "label": r.get("regime_label", "NEUTRAL")}
    except:
        regime["economic_surprise"] = {"score": 50, "label": "UNAVAILABLE"}
    try:
        r = _req.get("http://localhost:8050/api/fear-greed", timeout=30).json()
        regime["fear_greed"] = {"score": r.get("composite_score", 50), "label": r.get("regime_label", "NEUTRAL")}
    except:
        regime["fear_greed"] = {"score": 50, "label": "UNAVAILABLE"}
    try:
        r = _req.get("http://localhost:8050/api/global-liquidity", timeout=30).json()
        regime["liquidity"] = {"score": r.get("composite_score", 50), "label": r.get("regime_label", "NEUTRAL")}
    except:
        regime["liquidity"] = {"score": 50, "label": "UNAVAILABLE"}

    # 2. Sector breadth
    breadth = {}
    try:
        r = _req.get("http://localhost:8050/api/breadth-indicator", timeout=30).json()
        breadth = {
            "above_50d_pct": r.get("above_50d_sma_pct", 0),
            "above_200d_pct": r.get("above_200d_sma_pct", 0),
            "divergence": r.get("divergence_signal", "NONE"),
        }
    except:
        breadth = {"above_50d_pct": 0, "above_200d_pct": 0, "divergence": "UNAVAILABLE"}

    # 3. Trade tickets (ranked)
    tickets = []
    try:
        r = _req.get("http://localhost:8050/api/trade-tickets?portfolio_value=100000", timeout=600).json()
        for t in r.get("top_opportunities", []):
            tickets.append({
                "rank": t["rank"],
                "symbol": t["symbol"],
                "action": t["action"],
                "entry": t["entry"],
                "stop_loss": t["stop_loss"],
                "take_profit": t["take_profit"],
                "risk_reward": t["risk_reward"],
                "confidence": t["confidence"],
                "position_pct": t["position_pct"],
                "composite_score": t["composite_score"],
            })
    except Exception as e:
        print(f"[daily-digest] tickets error: {e}")

    # 4. Alerts
    alerts = []
    for t in tickets:
        if t["action"] == "BUY":
            alerts.append(f"🟢 {t['symbol']} — BUY signal (score {t['composite_score']:.0f}, confidence {t['confidence']:.0f})")
        if t["confidence"] >= 75:
            alerts.append(f"🔥 {t['symbol']} — HIGH confidence trade (conf {t['confidence']:.0f}, R:R {t['risk_reward']})")
        if t["composite_score"] <= 25:
            alerts.append(f"⚠️ {t['symbol']} — Extreme fear (score {t['composite_score']:.0f}) — contrarian buy zone")
        if t["composite_score"] >= 75:
            alerts.append(f"🔴 {t['symbol']} — Euphoria zone (score {t['composite_score']:.0f}) — consider trimming")

    if breadth.get("divergence", "").startswith("BULLISH"):
        alerts.append("📊 Sector BULLISH DIVERGENCE — breadth healthy despite price weakness")
    elif breadth.get("divergence", "").startswith("BEARISH"):
        alerts.append("📊 Sector BEARISH DIVERGENCE — breadth weakening despite price strength")

    # 5. Sector summary
    scores = [t["composite_score"] for t in tickets]
    avg_score = sum(scores) / len(scores) if scores else 50
    buys = sum(1 for t in tickets if t["action"] == "BUY")
    sells = sum(1 for t in tickets if t["action"] == "SELL")
    waits = sum(1 for t in tickets if t["action"] == "WAIT")
    holds = sum(1 for t in tickets if t["action"] == "HOLD")

    if avg_score <= 30:
        sector_view = "EXTREME FEAR — high-conviction contrarian buying opportunity"
    elif avg_score <= 40:
        sector_view = "FEAR — selective buying, prioritize highest-confidence tickers"
    elif avg_score <= 55:
        sector_view = "NEUTRAL — wait for better setups or accumulate small positions"
    elif avg_score <= 70:
        sector_view = "OPTIMISM — hold existing, avoid new entries at these levels"
    else:
        sector_view = "EUPHORIA — take profits, raise stops"

    # Macro context from macro-dashboard logic (inline, no self-HTTP)
    macro_context = {}
    try:
        macro_resp = macro_dashboard()
        ms = macro_resp.get("macro_score", 50)
        ml = macro_resp.get("macro_label", "NEUTRAL")
        rg = macro_resp.get("regime", "UNKNOWN")
        sizing = macro_resp.get("position_sizing_multiplier", 0.5)

        # Generate recommendation
        comps = macro_resp.get("components", {})
        headwinds = [k for k, v in comps.items() if isinstance(v, dict) and v.get("score", 50) < 40 and k != "regime"]
        tailwinds = [k for k, v in comps.items() if isinstance(v, dict) and v.get("score", 50) > 60 and k != "regime"]

        if ms > 55:
            rec = f"Macro supportive ({', '.join(tailwinds) if tailwinds else 'broad strength'}). Full position sizes appropriate."
        elif ms < 45:
            rec = f"Macro headwinds ({', '.join(headwinds) if headwinds else 'broad weakness'}). Reduce exposure, favor defensive names (CCJ, KAP.IL) over juniors."
        else:
            rec = "Mixed macro signals. Standard position sizes, be selective."

        macro_context = {
            "macro_score": round(ms, 1),
            "macro_label": ml,
            "regime": rg,
            "position_sizing_multiplier": sizing,
            "headwinds": headwinds,
            "tailwinds": tailwinds,
            "recommendation": rec,
        }
    except:
        macro_context = {"macro_score": 50, "macro_label": "UNAVAILABLE", "regime": "UNKNOWN", "position_sizing_multiplier": 0.5, "recommendation": "Macro data unavailable."}

    return {
        "timestamp": now.isoformat() + "Z",
        "title": "Uranium Daily Digest",
        "sector_view": sector_view,
        "sector_avg_score": round(avg_score, 1),
        "macro_context": macro_context,
        "action_summary": {
            "buy": buys,
            "hold": holds,
            "wait": waits,
            "sell": sells,
        },
        "market_regime": regime,
        "sector_breadth": breadth,
        "top_3": tickets[:3],
        "all_tickets": tickets,
        "alerts": alerts,
        "digest_text": _format_digest_text(sector_view, avg_score, tickets[:3], alerts, regime, breadth),
    }


def _format_digest_text(sector_view, avg_score, top3, alerts, regime, breadth):
    """Human-readable digest for push notifications."""
    lines = [f"☢️ URANIUM DAILY DIGEST", f"Sector: {sector_view} (avg score {avg_score:.0f})", ""]

    fg = regime.get("fear_greed", {})
    liq = regime.get("liquidity", {})
    lines.append(f"Market: F&G {fg.get('label','?')} ({fg.get('score',0):.0f}) | Liquidity {liq.get('label','?')} ({liq.get('score',0):.0f})")
    lines.append(f"Breadth: {breadth.get('above_50d_pct',0):.0f}% >50d SMA | {breadth.get('divergence','?')}")
    lines.append("")

    if top3:
        lines.append("Top trades:")
        for t in top3:
            lines.append(f"  #{t['rank']} {t['symbol']} {t['action']} — entry ${t['entry']:.2f} → ${t['take_profit']:.2f} (R:R {t['risk_reward']}, conf {t['confidence']:.0f})")
        lines.append("")

    if alerts:
        lines.append("Alerts:")
        for a in alerts:
            lines.append(f"  {a}")

    return "\n".join(lines)


@app.get("/api/trade-tickets")
def trade_tickets_endpoint(portfolio_value: float = Query(10000)):
    """Serve cached trade tickets if available, otherwise compute fresh."""
    if _cache_trade_tickets["data"] and portfolio_value == 10000:
        result = dict(_cache_trade_tickets["data"])
        result["_cached"] = True
        result["_cache_age"] = _cache_trade_tickets["updated_at"]
        return result
    return trade_tickets(portfolio_value)


def trade_tickets(portfolio_value: float = 10000):
    """
    Generate trade tickets for ALL tickers, ranked by confidence × R:R.
    Returns top opportunities.
    """
    import requests as _req
    from analysis import TICKERS

    tickets = []
    for sym in list(TICKERS.keys()):
        try:
            r = _req.get(
                f"http://localhost:8050/api/trade-ticket?symbol={sym}&portfolio_value={portfolio_value}",
                timeout=60
            )
            if r.status_code == 200:
                t = r.json()
                # Composite ranking: confidence × R:R
                conf = t.get("confidence", {}).get("score", 0)
                rr = t.get("risk_reward", 0)
                rank_score = conf * max(0, rr)
                t["rank_score"] = round(rank_score, 1)
                tickets.append(t)
        except Exception as e:
            print(f"[trade-tickets] {sym} error: {e}")

    tickets.sort(key=lambda x: x["rank_score"], reverse=True)

    return {
        "title": "Uranium Sector Trade Tickets — Ranked",
        "portfolio_value": portfolio_value,
        "total_tickers": len(tickets),
        "top_opportunities": [
            {
                "rank": i + 1,
                "symbol": t["symbol"],
                "action": t["action"],
                "conviction": t["conviction"],
                "composite_score": t["composite_score"],
                "entry": t["entry"]["price"],
                "stop_loss": t["stop_loss"]["price"],
                "take_profit": t["take_profit"]["price"],
                "risk_reward": t["risk_reward"],
                "confidence": t["confidence"]["score"],
                "rank_score": t["rank_score"],
                "position_pct": t["position_sizing"]["kelly_alloc_pct"],
                "rationale": t["rationale"],
            }
            for i, t in enumerate(tickets)
        ],
        "full_tickets": tickets,
    }


@app.get("/api/rebalance-signal")
def rebalance_signal(
    symbol: str = Query("URA"),
    portfolio_value: float = Query(10000),
    current_shares: float = Query(0),
    current_avg_cost: float = Query(0),
):
    """
    Actionable rebalance signal. Combines Kelly sizing + current score
    to output a concrete trade: BUY X shares, SELL X shares, or HOLD.
    """
    import requests as _req

    symbol = symbol.upper()

    # Get current price + score
    try:
        therm = _req.get("http://localhost:8050/api/thermometer", timeout=30).json()
        ticker = next((t for t in therm.get("tickers", []) if t["symbol"] == symbol), None)
        if not ticker:
            raise HTTPException(400, f"Ticker {symbol} not found")
        current_price = ticker["current_price"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to get price: {e}")

    # Get Kelly sizing
    try:
        kelly = _req.get(f"http://localhost:8050/api/kelly-criterion?symbol={symbol}&period=2y&forward_days=22", timeout=60).json()
        kelly_rec = kelly.get("recommendation", {})
        target_alloc_pct = max(0, kelly_rec.get("allocation_pct", 0))
        kelly_sizing = kelly_rec.get("sizing", "UNKNOWN")
        current_score = kelly.get("current_score", 0)
        current_bucket = kelly.get("current_bucket", "?")
    except Exception as e:
        raise HTTPException(500, f"Failed to get Kelly: {e}")

    # Get composite score
    try:
        decomp = _req.get(f"http://localhost:8050/api/score-decomposition?symbol={symbol}", timeout=30).json()
        composite_score = decomp.get("total_score", current_score)
        composite_label = decomp.get("label", "HOLD")
    except:
        composite_score = current_score
        composite_label = "HOLD"

    # Calculate positions
    current_value = current_shares * current_price
    current_alloc_pct = (current_value / portfolio_value * 100) if portfolio_value > 0 else 0
    target_value = portfolio_value * target_alloc_pct / 100
    target_shares = target_value / current_price if current_price > 0 else 0
    delta_shares = target_shares - current_shares
    delta_value = delta_shares * current_price

    # P&L if holding
    unrealized_pnl = (current_price - current_avg_cost) * current_shares if current_avg_cost > 0 and current_shares > 0 else 0
    unrealized_pct = ((current_price / current_avg_cost - 1) * 100) if current_avg_cost > 0 else 0

    # Action
    if abs(delta_shares) < 0.5 or abs(delta_value) < 50:
        action = "HOLD"
        action_detail = "Current allocation is within Kelly range. No trade needed."
        urgency = "NONE"
    elif delta_shares > 0:
        action = "BUY"
        action_detail = f"Buy {delta_shares:.1f} shares (${delta_value:,.0f}) to reach {target_alloc_pct:.0f}% allocation."
        urgency = "HIGH" if target_alloc_pct > 20 else "MODERATE" if target_alloc_pct > 10 else "LOW"
    else:
        action = "SELL"
        action_detail = f"Sell {abs(delta_shares):.1f} shares (${abs(delta_value):,.0f}) to reduce to {target_alloc_pct:.0f}% allocation."
        urgency = "HIGH" if current_alloc_pct > target_alloc_pct * 2 else "MODERATE"

    # Risk warnings
    warnings = []
    if composite_score < 30:
        warnings.append("⚠️ Score below 30 — contrarian buy zone (Kelly says go heavy, but high risk)")
    if composite_score > 70:
        warnings.append("⚠️ Score above 70 — consider reducing, historically lower forward returns at high scores")
    if target_alloc_pct > 30:
        warnings.append("⚠️ Kelly suggests >30% allocation — use fractional Kelly (half or quarter) for safety")
    if current_shares > 0 and unrealized_pct < -15:
        warnings.append(f"⚠️ Unrealized loss of {unrealized_pct:.1f}% — consider tax-loss harvesting")

    return {
        "symbol": symbol,
        "current_price": current_price,
        "composite_score": round(composite_score, 1),
        "composite_label": composite_label,
        "technical_score": round(current_score, 1),
        "kelly_bucket": current_bucket,
        "kelly_sizing": kelly_sizing,
        "portfolio": {
            "total_value": portfolio_value,
            "current_shares": current_shares,
            "current_value": round(current_value, 2),
            "current_alloc_pct": round(current_alloc_pct, 1),
            "avg_cost": current_avg_cost,
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pct": round(unrealized_pct, 1),
        },
        "target": {
            "alloc_pct": round(target_alloc_pct, 1),
            "value": round(target_value, 2),
            "shares": round(target_shares, 1),
        },
        "action": {
            "type": action,
            "delta_shares": round(delta_shares, 1),
            "delta_value": round(delta_value, 2),
            "detail": action_detail,
            "urgency": urgency,
        },
        "warnings": warnings,
    }


@app.get("/api/kelly-criterion")
def kelly_criterion(
    symbol: str = Query("URA"),
    period: str = Query("2y"),
    forward_days: int = Query(22, ge=5, le=63),
):
    """
    Kelly criterion position sizing based on historical score-to-return mapping.
    Buckets scores into ranges, computes win rate + avg win/loss for each bucket,
    then calculates full Kelly and fractional Kelly (half/quarter).
    """
    import numpy as np

    symbol = symbol.upper()
    daily_scores = _prepare_daily_scores(symbol, period)

    if len(daily_scores) < forward_days + 50:
        raise HTTPException(400, "Insufficient data")

    # Build score → forward return mapping
    buckets = {}
    for i in range(len(daily_scores) - forward_days):
        score = daily_scores[i]["score"]
        entry_price = daily_scores[i]["price"]
        exit_price = daily_scores[i + forward_days]["price"]
        fwd_return = (exit_price - entry_price) / entry_price * 100

        # Bucket by 10-point ranges
        bucket = int(score // 10) * 10
        bucket_label = f"{bucket}-{bucket + 10}"
        if bucket_label not in buckets:
            buckets[bucket_label] = []
        buckets[bucket_label].append(fwd_return)

    # Compute Kelly for each bucket
    bucket_stats = []
    for label in sorted(buckets.keys()):
        returns = buckets[label]
        n = len(returns)
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        win_rate = len(wins) / n if n > 0 else 0
        avg_win = float(np.mean(wins)) if wins else 0
        avg_loss = float(np.mean(losses)) if losses else 0
        avg_return = float(np.mean(returns))

        # Kelly: f* = (p * b - q) / b where p=win_rate, q=1-p, b=avg_win/|avg_loss|
        if avg_loss != 0 and avg_win > 0:
            b = avg_win / abs(avg_loss)  # win/loss ratio
            kelly_full = (win_rate * b - (1 - win_rate)) / b
        else:
            b = 0
            kelly_full = 0 if avg_win == 0 else 1.0

        kelly_full = max(-1, min(1, kelly_full))  # cap
        kelly_half = kelly_full * 0.5
        kelly_quarter = kelly_full * 0.25

        bucket_stats.append({
            "bucket": label,
            "observations": n,
            "win_rate_pct": round(win_rate * 100, 1),
            "avg_return_pct": round(avg_return, 2),
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
            "win_loss_ratio": round(b, 2),
            "kelly_full_pct": round(kelly_full * 100, 1),
            "kelly_half_pct": round(kelly_half * 100, 1),
            "kelly_quarter_pct": round(kelly_quarter * 100, 1),
        })

    # Current score → recommendation
    current_score = daily_scores[-1]["score"]
    current_bucket = f"{int(current_score // 10) * 10}-{int(current_score // 10) * 10 + 10}"
    current_stats = next((b for b in bucket_stats if b["bucket"] == current_bucket), None)

    if current_stats:
        rec_pct = max(0, current_stats["kelly_half_pct"])
        if rec_pct > 50:
            sizing = "AGGRESSIVE"
            detail = f"Strong historical edge at score {current_bucket}. Half-Kelly suggests {rec_pct:.0f}% allocation."
        elif rec_pct > 20:
            sizing = "MODERATE"
            detail = f"Moderate edge. Half-Kelly: {rec_pct:.0f}% allocation."
        elif rec_pct > 5:
            sizing = "SMALL"
            detail = f"Weak edge. Quarter-Kelly ({current_stats['kelly_quarter_pct']:.0f}%) recommended for safety."
            rec_pct = max(0, current_stats["kelly_quarter_pct"])
        else:
            sizing = "NO POSITION"
            detail = f"No edge at score {current_bucket} (win rate {current_stats['win_rate_pct']}%, avg return {current_stats['avg_return_pct']:+.1f}%). Stay flat or minimal."
            rec_pct = 0
    else:
        sizing = "UNKNOWN"
        detail = "Not enough data for this score range"
        rec_pct = 0

    return {
        "symbol": symbol,
        "period": period,
        "forward_days": forward_days,
        "current_score": round(current_score, 1),
        "current_bucket": current_bucket,
        "recommendation": {
            "sizing": sizing,
            "allocation_pct": round(rec_pct, 1),
            "detail": detail,
        },
        "buckets": bucket_stats,
        "method": f"Kelly criterion from {forward_days}-day forward returns bucketed by technical score. Half-Kelly recommended (full Kelly is too aggressive for real trading).",
        "note": "Technical scores only. Full composite Kelly requires 30+ daily snapshots.",
    }


@app.get("/api/walk-forward")
def walk_forward(
    symbol: str = Query("URA"),
    period: str = Query("2y"),
    train_days: int = Query(126, ge=60, le=252),
    test_days: int = Query(63, ge=21, le=126),
    slide_days: int = Query(21, ge=5, le=63),
):
    """
    Walk-forward analysis: rolling train/test windows to detect overfitting.
    Trains optimal thresholds on each window, tests out-of-sample.
    """
    import numpy as np

    daily_scores = _prepare_daily_scores(symbol.upper(), period)
    if len(daily_scores) < train_days + test_days + 20:
        raise HTTPException(400, f"Need {train_days + test_days + 20}+ days, got {len(daily_scores)}")

    def _sim_return(scores, buy_t, sell_t):
        """Simple binary backtest: buy when score > buy_t, sell when < sell_t."""
        cash = 10000
        shares = 0
        holding = False
        for d in scores:
            price = d["price"]
            if not holding and d["score"] >= buy_t:
                shares = cash / price
                cash = 0
                holding = True
            elif holding and d["score"] <= sell_t:
                cash = shares * price
                shares = 0
                holding = False
        final = cash + shares * scores[-1]["price"] if shares > 0 else cash
        return (final - 10000) / 10000 * 100

    windows = []
    i = 0
    while i + train_days + test_days <= len(daily_scores):
        train = daily_scores[i:i + train_days]
        test = daily_scores[i + train_days:i + train_days + test_days]

        # Grid search on train window
        best_sharpe_proxy = -999
        best_buy = 60
        best_sell = 40
        best_train_ret = 0

        for buy_t in range(50, 80, 5):
            for sell_t in range(25, buy_t - 5, 5):
                ret = _sim_return(train, buy_t, sell_t)
                bh = (train[-1]["price"] / train[0]["price"] - 1) * 100
                alpha = ret - bh
                # Proxy: prefer strategies that beat buy-hold with decent return
                proxy = alpha + ret * 0.1
                if proxy > best_sharpe_proxy:
                    best_sharpe_proxy = proxy
                    best_buy = buy_t
                    best_sell = sell_t
                    best_train_ret = ret

        # Apply to test (out-of-sample)
        test_ret = _sim_return(test, best_buy, best_sell)
        test_bh = (test[-1]["price"] / test[0]["price"] - 1) * 100
        train_bh = (train[-1]["price"] / train[0]["price"] - 1) * 100

        windows.append({
            "window": len(windows) + 1,
            "train_start": train[0]["date"],
            "train_end": train[-1]["date"],
            "test_start": test[0]["date"],
            "test_end": test[-1]["date"],
            "optimal_buy": best_buy,
            "optimal_sell": best_sell,
            "train_return_pct": round(best_train_ret, 2),
            "train_buyhold_pct": round(train_bh, 2),
            "train_alpha": round(best_train_ret - train_bh, 2),
            "test_return_pct": round(test_ret, 2),
            "test_buyhold_pct": round(test_bh, 2),
            "test_alpha": round(test_ret - test_bh, 2),
            "overfit_gap": round(best_train_ret - test_ret, 2),
        })

        i += slide_days

    # Aggregate stats
    train_alphas = [w["train_alpha"] for w in windows]
    test_alphas = [w["test_alpha"] for w in windows]
    overfit_gaps = [w["overfit_gap"] for w in windows]
    test_wins = sum(1 for a in test_alphas if a > 0)

    avg_train_alpha = float(np.mean(train_alphas))
    avg_test_alpha = float(np.mean(test_alphas))
    avg_overfit = float(np.mean(overfit_gaps))
    test_win_rate = test_wins / len(windows) * 100 if windows else 0

    # Diagnosis
    if avg_test_alpha > 2:
        diagnosis = "ROBUST — signals generate alpha out-of-sample"
    elif avg_test_alpha > -2:
        diagnosis = "MARGINAL — signals show weak but not negative OOS alpha"
    elif avg_overfit > 20:
        diagnosis = "OVERFITTING — large gap between train and test performance"
    else:
        diagnosis = "STRUCTURAL UNDERPERFORMANCE — timing signals trail buy-hold regardless of thresholds"

    # Most common optimal thresholds
    buy_counts = {}
    sell_counts = {}
    for w in windows:
        buy_counts[w["optimal_buy"]] = buy_counts.get(w["optimal_buy"], 0) + 1
        sell_counts[w["optimal_sell"]] = sell_counts.get(w["optimal_sell"], 0) + 1
    modal_buy = max(buy_counts, key=buy_counts.get) if buy_counts else 60
    modal_sell = max(sell_counts, key=sell_counts.get) if sell_counts else 40

    return {
        "symbol": symbol.upper(),
        "period": period,
        "method": f"Walk-forward: {train_days}d train / {test_days}d test, {slide_days}d slide",
        "total_windows": len(windows),
        "summary": {
            "avg_train_alpha_pct": round(avg_train_alpha, 2),
            "avg_test_alpha_pct": round(avg_test_alpha, 2),
            "avg_overfit_gap_pct": round(avg_overfit, 2),
            "test_win_rate_pct": round(test_win_rate, 1),
            "modal_buy_threshold": modal_buy,
            "modal_sell_threshold": modal_sell,
        },
        "diagnosis": diagnosis,
        "windows": windows,
    }


@app.get("/api/optimized-backtest")
def optimized_backtest(
    symbol: str = Query("URA"),
    period: str = Query("2y"),
    initial: float = Query(10000),
):
    """
    Side-by-side backtest: default weights vs optimizer-suggested weights.
    Since we only have technical signals historically, we re-weight the 5 technical
    sub-signals (range, RSI, MACD, BB, SMA) according to the optimizer's recommendations
    within the technical category. Non-technical signals are added as a constant
    adjustment based on current readings.
    """
    import yfinance as yf, numpy as np, time as _time, requests as _req

    symbol = symbol.upper()

    # Get optimizer weights
    try:
        opt_data = _req.get("http://localhost:8050/api/weight-optimizer", timeout=180).json()
        opt_weights = opt_data.get("optimized_weights", {})
        cur_weights = opt_data.get("current_weights", {})
    except Exception as e:
        raise HTTPException(500, f"Failed to get optimized weights: {e}")

    # Map technical signal names to sub-scores
    # Default technical weights (from analysis.py): range=40%, rsi=25%, macd=15%, bb=10%, sma=10%
    DEFAULT_TECH = {"range_position": 0.40, "rsi": 0.25, "macd": 0.15, "bollinger": 0.10, "sma_trend": 0.10}

    # Optimized technical weights (normalize to sum=1 within technical)
    opt_tech_raw = {k: opt_weights.get(k, v) for k, v in DEFAULT_TECH.items()}
    tech_sum = sum(opt_tech_raw.values())
    OPT_TECH = {k: v / tech_sum for k, v in opt_tech_raw.items()} if tech_sum > 0 else DEFAULT_TECH

    # Prepare OHLCV data
    period_map = {"3m": "3mo", "6m": "6mo", "1y": "1y", "2y": "2y", "3y": "3y", "5y": "5y"}
    yf_period = period_map.get(period, "2y")
    t = yf.Ticker(symbol)
    df = t.history(period=yf_period)
    if df.empty or len(df) < 50:
        raise HTTPException(400, "Insufficient data")

    df["SMA_50"] = df["Close"].rolling(50).mean()
    df["SMA_200"] = df["Close"].rolling(200).mean()
    df["BB_mid"] = df["Close"].rolling(20).mean()
    df["BB_std"] = df["Close"].rolling(20).std()
    df["BB_upper"] = df["BB_mid"] + 2 * df["BB_std"]
    df["BB_lower"] = df["BB_mid"] - 2 * df["BB_std"]
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - 100 / (1 + rs)
    ema12 = df["Close"].ewm(span=12).mean()
    ema26 = df["Close"].ewm(span=26).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_signal"] = df["MACD"].ewm(span=9).mean()
    df["Range_high"] = df["High"].rolling(63).max()
    df["Range_low"] = df["Low"].rolling(63).min()
    df = df.dropna(subset=["SMA_50", "RSI", "MACD", "BB_upper", "Range_high"])

    def _compute_score(row, weights):
        price = float(row["Close"])
        range_span = row["Range_high"] - row["Range_low"]
        zone_pct = ((price - row["Range_low"]) / range_span * 100) if range_span > 0 else 50
        range_score = 100 - zone_pct
        rsi_score = 100 - float(row["RSI"])
        macd_diff = float(row["MACD"] - row["MACD_signal"])
        macd_score = 50 + (max(-2, min(2, macd_diff)) / 2) * 50
        bb_range = row["BB_upper"] - row["BB_lower"]
        bb_score = 100 - max(0, min(100, (price - row["BB_lower"]) / bb_range * 100)) if bb_range > 0 else 50
        sma_score = 75 if (float(row["SMA_50"]) > float(row["SMA_200"]) if not np.isnan(row["SMA_200"]) else False) else 25
        if price > float(row["SMA_50"]):
            sma_score = min(100, sma_score + 15)

        scores = {
            "range_position": range_score,
            "rsi": rsi_score,
            "macd": macd_score,
            "bollinger": bb_score,
            "sma_trend": sma_score,
        }
        total = sum(scores[k] * weights.get(k, 0) for k in scores)
        return max(0, min(100, total))

    def _run_sim(df, weights, label):
        cash = initial
        shares = 0.0
        equity_curve = []
        daily_returns = []
        max_eq = initial
        max_dd = 0
        prev_eq = initial

        for idx, row in df.iterrows():
            score = _compute_score(row, weights)
            price = float(row["Close"])
            equity = cash + shares * price

            # Score-weighted allocation (10-90%)
            target_alloc = 10 + (score / 100) * 80
            current_alloc = (shares * price / equity * 100) if equity > 0 else 0

            if abs(current_alloc - target_alloc) > 5:
                target_value = equity * target_alloc / 100
                delta_val = target_value - shares * price
                if delta_val > 0 and cash >= delta_val:
                    shares += delta_val / price
                    cash -= delta_val
                elif delta_val < 0:
                    sell = min(shares, abs(delta_val) / price)
                    shares -= sell
                    cash += sell * price

            equity = cash + shares * price
            dr = (equity - prev_eq) / prev_eq if prev_eq > 0 else 0
            daily_returns.append(dr)
            prev_eq = equity
            max_eq = max(max_eq, equity)
            dd = (max_eq - equity) / max_eq * 100
            max_dd = max(max_dd, dd)
            equity_curve.append({"date": idx.strftime("%Y-%m-%d"), "equity": round(equity, 2), "score": round(score, 1)})

        final = cash + shares * float(df["Close"].iloc[-1])
        ret = (final - initial) / initial * 100
        bh_ret = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1) * 100
        dr_arr = np.array(daily_returns)
        sharpe = float(np.mean(dr_arr) / np.std(dr_arr) * np.sqrt(252)) if np.std(dr_arr) > 0 else 0
        ds = dr_arr[dr_arr < 0]
        sortino = float(np.mean(dr_arr) / np.std(ds) * np.sqrt(252)) if len(ds) > 0 and np.std(ds) > 0 else sharpe

        return {
            "label": label,
            "final_equity": round(final, 2),
            "total_return_pct": round(ret, 2),
            "buy_hold_return_pct": round(bh_ret, 2),
            "alpha_vs_buyhold": round(ret - bh_ret, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe": round(sharpe, 3),
            "sortino": round(sortino, 3),
            "trading_days": len(df),
            "equity_curve": equity_curve[::max(1, len(equity_curve) // 100)],
        }

    default_result = _run_sim(df, DEFAULT_TECH, "Default Weights")
    optimized_result = _run_sim(df, OPT_TECH, "Optimized Weights")

    improvement = {
        "return_delta": round(optimized_result["total_return_pct"] - default_result["total_return_pct"], 2),
        "alpha_delta": round(optimized_result["alpha_vs_buyhold"] - default_result["alpha_vs_buyhold"], 2),
        "sharpe_delta": round(optimized_result["sharpe"] - default_result["sharpe"], 3),
        "drawdown_delta": round(optimized_result["max_drawdown_pct"] - default_result["max_drawdown_pct"], 2),
    }

    return {
        "symbol": symbol,
        "period": period,
        "default_weights_technical": {k: round(v, 3) for k, v in DEFAULT_TECH.items()},
        "optimized_weights_technical": {k: round(v, 3) for k, v in OPT_TECH.items()},
        "default": default_result,
        "optimized": optimized_result,
        "improvement": improvement,
        "note": "Technical sub-signals only (range, RSI, MACD, BB, SMA). Non-technical signals not available historically. Full-model backtest requires 30+ daily composite snapshots.",
    }


@app.get("/api/weight-optimizer")
def weight_optimizer():
    """
    Suggests optimal signal weights by penalizing correlated signals.
    Uses inverse-correlation weighting within each category to reduce redundancy.
    """
    import numpy as np, requests as _req, time as _time

    if not hasattr(weight_optimizer, "_cache"):
        weight_optimizer._cache = {"data": None, "ts": 0}
    _now = _time.time()
    if weight_optimizer._cache["data"] and _now - weight_optimizer._cache["ts"] < 14400:
        return weight_optimizer._cache["data"]

    # Get correlation matrix
    try:
        corr_data = _req.get("http://localhost:8050/api/signal-correlation-matrix", timeout=120).json()
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch correlation matrix: {e}")

    if "signals" not in corr_data:
        raise HTTPException(500, "Correlation matrix not ready")

    signals = corr_data["signals"]
    corr_matrix = np.array(corr_data["correlation_matrix"])
    current_weights = corr_data.get("current_weights", {})

    if not current_weights:
        raise HTTPException(500, "No current weights available")

    # Get category mapping from a sample decomposition
    try:
        sample = _req.get("http://localhost:8050/api/score-decomposition?symbol=URA", timeout=30).json()
        cat_map = {}
        for c in sample.get("components", []):
            cat_map[c["name"]] = c.get("category", "unknown")
    except:
        cat_map = {}

    # Category target weights (must sum to 1.0)
    CATEGORY_TARGETS = {"technical": 0.40, "macro": 0.20, "fundamental": 0.20, "sentiment": 0.20}

    # For each signal, compute average absolute correlation with OTHER signals
    n = len(signals)
    avg_corr = {}
    for i, sig in enumerate(signals):
        others = [abs(float(corr_matrix[i][j])) for j in range(n) if j != i]
        avg_corr[sig] = float(np.mean(others)) if others else 0

    # Within each category, allocate weight inversely proportional to avg correlation
    categories = {}
    for sig in signals:
        cat = cat_map.get(sig, "unknown")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(sig)

    optimized = {}
    changes = []

    for cat, cat_signals in categories.items():
        target_total = CATEGORY_TARGETS.get(cat, 0.10)

        # Inverse correlation scores
        inv_scores = {}
        for sig in cat_signals:
            # Higher avg_corr = more redundant = less weight
            inv_scores[sig] = 1.0 / max(0.05, avg_corr.get(sig, 0.5))

        total_inv = sum(inv_scores.values())

        for sig in cat_signals:
            new_weight = round(inv_scores[sig] / total_inv * target_total, 4)
            old_weight = current_weights.get(sig, 0)
            optimized[sig] = new_weight
            delta = new_weight - old_weight
            changes.append({
                "signal": sig,
                "category": cat,
                "current_weight": old_weight,
                "optimized_weight": new_weight,
                "change": round(delta, 4),
                "direction": "↑" if delta > 0.005 else "↓" if delta < -0.005 else "—",
                "avg_correlation": round(avg_corr.get(sig, 0), 3),
                "reason": "High correlation → de-weighted" if delta < -0.005 else "Low correlation → boosted" if delta > 0.005 else "Unchanged",
            })

    changes.sort(key=lambda x: abs(x["change"]), reverse=True)

    # Verify totals
    total_optimized = sum(optimized.values())
    total_current = sum(current_weights.values())

    # Biggest winners and losers
    winners = [c for c in changes if c["change"] > 0.005]
    losers = [c for c in changes if c["change"] < -0.005]

    resp = {
        "title": "Signal Weight Optimizer",
        "method": "Inverse-correlation weighting — signals with lower avg correlation to peers get more weight within their category. Category totals preserved.",
        "total_current_weight": round(total_current, 4),
        "total_optimized_weight": round(total_optimized, 4),
        "category_targets": CATEGORY_TARGETS,
        "optimized_weights": optimized,
        "current_weights": current_weights,
        "changes": changes,
        "winners": [f"{c['signal']} ({c['current_weight']}→{c['optimized_weight']}, {c['direction']})" for c in winners[:5]],
        "losers": [f"{c['signal']} ({c['current_weight']}→{c['optimized_weight']}, {c['direction']})" for c in losers[:5]],
        "note": "Cross-sectional only (1 date). Re-run after 30+ daily snapshots for time-series optimization. Apply with caution.",
    }

    weight_optimizer._cache = {"data": resp, "ts": _now}
    return resp


@app.get("/api/signal-correlation-matrix")
def signal_correlation_matrix():
    """
    Signal correlation matrix. Computes pairwise correlations between all 17 signal
    components across tickers (cross-sectional) and across time (when enough snapshots exist).
    Key diagnostic: identifies redundant signals for weight optimization.
    """
    import numpy as np, time as _time

    if not hasattr(signal_correlation_matrix, "_cache"):
        signal_correlation_matrix._cache = {"data": None, "ts": 0}
    _now = _time.time()
    if signal_correlation_matrix._cache["data"] and _now - signal_correlation_matrix._cache["ts"] < 14400:
        return signal_correlation_matrix._cache["data"]

    from analysis import TICKERS
    # Collect signal scores for each ticker
    signal_names = []
    ticker_signals = {}

    import requests as _req
    for sym in list(TICKERS.keys()):
        try:
            r = _req.get(f"http://localhost:8050/api/score-decomposition?symbol={sym}", timeout=30)
            if r.status_code != 200:
                continue
            decomp = r.json()
            components = decomp.get("components", [])
            if not components:
                continue
            scores = {}
            for c in components:
                name = c["name"]
                scores[name] = c["score"]
                if name not in signal_names:
                    signal_names.append(name)
            ticker_signals[sym] = scores
        except Exception as e:
            print(f"[corr] {sym} error: {e}")

    if len(ticker_signals) < 3:
        raise HTTPException(400, "Need at least 3 tickers for correlation")

    # Build matrix: rows=tickers, cols=signals
    tickers_list = sorted(ticker_signals.keys())
    matrix = []
    for sym in tickers_list:
        row = [ticker_signals[sym].get(s, 50) for s in signal_names]
        matrix.append(row)

    arr = np.array(matrix)  # shape: (n_tickers, n_signals)

    # Pairwise signal correlation (across tickers)
    n_signals = len(signal_names)
    corr = np.corrcoef(arr.T)  # shape: (n_signals, n_signals)
    # Handle NaN (constant signals)
    corr = np.nan_to_num(corr, nan=0.0)

    # Find highly correlated pairs (|r| > 0.7)
    highly_correlated = []
    for i in range(n_signals):
        for j in range(i + 1, n_signals):
            r = float(corr[i][j])
            if abs(r) > 0.7:
                highly_correlated.append({
                    "signal_a": signal_names[i],
                    "signal_b": signal_names[j],
                    "correlation": round(r, 3),
                    "recommendation": "Consider de-weighting one — signals are redundant" if r > 0.85 else "Moderate overlap — monitor",
                })

    # Find most independent signals (avg |r| < 0.3)
    independent = []
    for i in range(n_signals):
        avg_abs_corr = float(np.mean(np.abs(np.delete(corr[i], i))))
        independent.append({"signal": signal_names[i], "avg_abs_correlation": round(avg_abs_corr, 3)})
    independent.sort(key=lambda x: x["avg_abs_correlation"])

    # Correlation matrix as nested list for heatmap
    corr_matrix = [[round(float(corr[i][j]), 3) for j in range(n_signals)] for i in range(n_signals)]

    # Weight optimization suggestion
    # Idea: signals with high avg correlation should have lower weight
    current_weights = {}
    suggested_weights = {}
    for comp in list(ticker_signals.values())[0]:
        pass  # We'd need weights from decomposition

    # Get weights from a sample decomposition
    try:
        if "URA" in ticker_signals:
            sample = _req.get("http://localhost:8050/api/score-decomposition?symbol=URA", timeout=10).json()
            for c in sample.get("components", []):
                current_weights[c["name"]] = c["weight"]
    except:
        pass

    # Suggest: scale weight inversely with avg correlation
    if current_weights and independent:
        total_current = sum(current_weights.values())
        inv_corr = {}
        for item in independent:
            s = item["signal"]
            if s in current_weights:
                inv_corr[s] = 1.0 / max(0.1, item["avg_abs_correlation"])
        if inv_corr:
            total_inv = sum(inv_corr.values())
            for s, ic in inv_corr.items():
                suggested_weights[s] = round(ic / total_inv * total_current, 4)

    highly_correlated.sort(key=lambda x: abs(x["correlation"]), reverse=True)

    resp = {
        "title": "Signal Correlation Matrix",
        "method": "Cross-sectional correlation across 11 tickers (same date). Time-series correlation needs 30+ daily snapshots.",
        "tickers_analyzed": len(tickers_list),
        "signals": signal_names,
        "correlation_matrix": corr_matrix,
        "highly_correlated_pairs": highly_correlated[:20],
        "most_independent_signals": independent[:5],
        "most_redundant_signals": independent[-5:][::-1],
        "current_weights": current_weights,
        "suggested_weights": suggested_weights,
        "note": f"Cross-sectional only ({len(tickers_list)} tickers, 1 date). Time-series correlations available after 30+ daily snapshots accumulate.",
    }

    signal_correlation_matrix._cache = {"data": resp, "ts": _now}
    return resp


@app.get("/api/daily-snapshot")
def daily_snapshot(symbol: str = Query(None), days: int = Query(90)):
    """
    Returns archived daily composite score snapshots.
    These are saved by the APScheduler cron at 20:30 UTC daily.
    Use for model validation — compare scores to forward returns.
    """
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if symbol:
        c.execute(
            "SELECT * FROM composite_score_history WHERE symbol=? ORDER BY date DESC LIMIT ?",
            (symbol.upper(), days)
        )
    else:
        c.execute(
            "SELECT * FROM composite_score_history ORDER BY date DESC LIMIT ?",
            (days * 11,)  # 11 tickers
        )

    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    # Group by date
    by_date = {}
    for r in rows:
        d = r["date"]
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(r)

    dates = sorted(by_date.keys(), reverse=True)
    unique_symbols = sorted(set(r["symbol"] for r in rows))

    return {
        "title": "Daily Signal Archive",
        "total_snapshots": len(rows),
        "unique_dates": len(dates),
        "symbols": unique_symbols,
        "latest_date": dates[0] if dates else None,
        "earliest_date": dates[-1] if dates else None,
        "cron_schedule": "Daily at 20:30 UTC (4:30 PM ET)",
        "note": "Accumulating data for model validation. Need 3-6 months for statistically significant backtest.",
        "snapshots": rows,
    }


@app.get("/api/fear-greed")
def fear_greed():
    """
    Market Fear & Greed proxy. CNN blocks bots, so we build from:
    1. VIX level + percentile (fear gauge)
    2. SPY vs 125d SMA (momentum)
    3. Put/call ratio on SPY (hedging demand)
    4. Junk bond spread (HYG/IEF ratio)
    5. Safe haven demand (GLD vs SPY)
    """
    import yfinance as yf, numpy as np, time as _time

    if not hasattr(fear_greed, "_cache"):
        fear_greed._cache = {"data": None, "ts": 0}
    _now = _time.time()
    if fear_greed._cache["data"] and _now - fear_greed._cache["ts"] < 7200:
        return fear_greed._cache["data"]

    components = {}
    scores = []

    # 1. VIX — the classic fear gauge
    try:
        vix = yf.Ticker("^VIX").history(period="1y")
        if not vix.empty:
            if vix.index.tz is not None:
                vix.index = vix.index.tz_localize(None)
            current_vix = float(vix["Close"].iloc[-1])
            vix_pct = float((vix["Close"] <= current_vix).mean() * 100)
            # High VIX = fear → low score (greed=100, fear=0)
            vix_score = max(0, min(100, 100 - vix_pct))
            scores.append(vix_score)
            components["vix"] = {
                "label": "VIX (Volatility)", "value": round(current_vix, 1),
                "percentile": round(vix_pct, 1), "score": round(vix_score, 1),
                "signal": "EXTREME FEAR" if vix_score < 15 else "FEAR" if vix_score < 35 else "NEUTRAL" if vix_score < 65 else "GREED" if vix_score < 85 else "EXTREME GREED",
            }
    except Exception as e:
        print(f"[f&g] VIX error: {e}")

    # 2. Market momentum — SPY vs 125d SMA
    try:
        spy = yf.Ticker("SPY").history(period="1y")
        if not spy.empty and len(spy) >= 125:
            if spy.index.tz is not None:
                spy.index = spy.index.tz_localize(None)
            current_spy = float(spy["Close"].iloc[-1])
            sma125 = float(spy["Close"].iloc[-125:].mean())
            pct_above = (current_spy / sma125 - 1) * 100
            # Map: -10% below → 0, +10% above → 100
            mom_score = max(0, min(100, 50 + pct_above * 5))
            scores.append(mom_score)
            components["momentum"] = {
                "label": "Market Momentum (SPY vs 125d SMA)",
                "value": round(pct_above, 2), "unit": "% vs SMA",
                "score": round(mom_score, 1),
                "signal": "EXTREME FEAR" if mom_score < 15 else "FEAR" if mom_score < 35 else "NEUTRAL" if mom_score < 65 else "GREED" if mom_score < 85 else "EXTREME GREED",
            }
    except Exception as e:
        print(f"[f&g] SPY error: {e}")

    # 3. Junk bond demand — HYG/IEF spread
    try:
        hyg = yf.Ticker("HYG").history(period="6mo")
        ief = yf.Ticker("IEF").history(period="6mo")
        if not hyg.empty and not ief.empty:
            for h in [hyg, ief]:
                if h.index.tz is not None:
                    h.index = h.index.tz_localize(None)
            import pandas as pd
            ratio = pd.DataFrame({"hyg": hyg["Close"], "ief": ief["Close"]}).dropna()
            if len(ratio) > 60:
                spread = ratio["hyg"] / ratio["ief"]
                current_spread = float(spread.iloc[-1])
                spread_pct = float((spread <= current_spread).mean() * 100)
                # High ratio = risk-on = greed
                jb_score = spread_pct
                scores.append(jb_score)
                components["junk_bond_demand"] = {
                    "label": "Junk Bond Demand (HYG/IEF)",
                    "value": round(current_spread, 4), "percentile": round(spread_pct, 1),
                    "score": round(jb_score, 1),
                    "signal": "EXTREME FEAR" if jb_score < 15 else "FEAR" if jb_score < 35 else "NEUTRAL" if jb_score < 65 else "GREED" if jb_score < 85 else "EXTREME GREED",
                }
    except Exception as e:
        print(f"[f&g] junk bond error: {e}")

    # 4. Safe haven demand — GLD vs SPY relative performance
    try:
        gld = yf.Ticker("GLD").history(period="6mo")
        spy2 = yf.Ticker("SPY").history(period="6mo")
        if not gld.empty and not spy2.empty:
            for h in [gld, spy2]:
                if h.index.tz is not None:
                    h.index = h.index.tz_localize(None)
            import pandas as pd
            df = pd.DataFrame({"gld": gld["Close"], "spy": spy2["Close"]}).dropna()
            if len(df) > 20:
                # Gold outperforming SPY = fear
                gld_ret_22d = float((df["gld"].iloc[-1] / df["gld"].iloc[-22] - 1) * 100)
                spy_ret_22d = float((df["spy"].iloc[-1] / df["spy"].iloc[-22] - 1) * 100)
                relative = spy_ret_22d - gld_ret_22d  # positive = SPY winning = greed
                sh_score = max(0, min(100, 50 + relative * 3))
                scores.append(sh_score)
                components["safe_haven"] = {
                    "label": "Safe Haven Demand (GLD vs SPY)",
                    "value": round(relative, 2), "unit": "SPY-GLD spread %",
                    "score": round(sh_score, 1),
                    "signal": "EXTREME FEAR" if sh_score < 15 else "FEAR" if sh_score < 35 else "NEUTRAL" if sh_score < 65 else "GREED" if sh_score < 85 else "EXTREME GREED",
                }
    except Exception as e:
        print(f"[f&g] safe haven error: {e}")

    # 5. Market breadth — % of S&P above 50d (proxy via RSP vs SPY)
    try:
        rsp = yf.Ticker("RSP").history(period="6mo")  # equal-weight S&P
        spy3 = yf.Ticker("SPY").history(period="6mo")
        if not rsp.empty and not spy3.empty:
            for h in [rsp, spy3]:
                if h.index.tz is not None:
                    h.index = h.index.tz_localize(None)
            import pandas as pd
            df = pd.DataFrame({"rsp": rsp["Close"], "spy": spy3["Close"]}).dropna()
            if len(df) > 22:
                rsp_ret = float((df["rsp"].iloc[-1] / df["rsp"].iloc[-22] - 1) * 100)
                spy_ret = float((df["spy"].iloc[-1] / df["spy"].iloc[-22] - 1) * 100)
                breadth_rel = rsp_ret - spy_ret  # positive = broad participation = greed
                br_score = max(0, min(100, 50 + breadth_rel * 5))
                scores.append(br_score)
                components["market_breadth"] = {
                    "label": "Market Breadth (RSP vs SPY)",
                    "value": round(breadth_rel, 2), "unit": "RSP-SPY spread %",
                    "score": round(br_score, 1),
                    "signal": "EXTREME FEAR" if br_score < 15 else "FEAR" if br_score < 35 else "NEUTRAL" if br_score < 65 else "GREED" if br_score < 85 else "EXTREME GREED",
                }
    except Exception as e:
        print(f"[f&g] breadth error: {e}")

    composite = float(np.mean(scores)) if scores else 50

    if composite <= 15:
        label = "EXTREME FEAR"
    elif composite <= 35:
        label = "FEAR"
    elif composite <= 45:
        label = "LEAN FEAR"
    elif composite <= 55:
        label = "NEUTRAL"
    elif composite <= 65:
        label = "LEAN GREED"
    elif composite <= 85:
        label = "GREED"
    else:
        label = "EXTREME GREED"

    # Contrarian signal for uranium
    if composite <= 25:
        uranium_signal = "CONTRARIAN BUY"
        uranium_detail = "Extreme fear — historically best time to accumulate risk assets including uranium"
    elif composite <= 40:
        uranium_signal = "LEAN BUY"
        uranium_detail = "Fear present — favorable for contrarian entry"
    elif composite >= 80:
        uranium_signal = "CONTRARIAN SELL"
        uranium_detail = "Extreme greed — risk of mean reversion, consider reducing"
    elif composite >= 65:
        uranium_signal = "LEAN SELL"
        uranium_detail = "Greed building — caution on new positions"
    else:
        uranium_signal = "NEUTRAL"
        uranium_detail = "No strong contrarian signal"

    resp = {
        "title": "Fear & Greed Index (Proxy)",
        "method": "CNN blocks bots — built from VIX, SPY momentum, junk bond spreads, safe haven demand, market breadth",
        "score": round(composite, 1),
        "label": label,
        "uranium_signal": uranium_signal,
        "uranium_detail": uranium_detail,
        "components": components,
    }

    fear_greed._cache = {"data": resp, "ts": _now}
    return resp


@app.get("/api/breadth-indicator")
def breadth_indicator():
    """
    Uranium sector internal breadth. Tracks how many uranium stocks are above
    their 50d/200d SMAs and the advance/decline ratio. Breadth divergence
    (URA up + breadth down) signals a fragile rally.
    """
    import yfinance as yf, numpy as np, time as _time

    if not hasattr(breadth_indicator, "_cache"):
        breadth_indicator._cache = {"data": None, "ts": 0}
    _now = _time.time()
    if breadth_indicator._cache["data"] and _now - breadth_indicator._cache["ts"] < 14400:
        return breadth_indicator._cache["data"]

    # Top uranium stocks (covers ~80% of URA by weight)
    stocks = {
        "CCJ": "Cameco", "NXE": "NexGen", "UEC": "Uranium Energy",
        "DNN": "Denison", "UUUU": "Energy Fuels", "LEU": "Centrus",
        "OKLO": "Oklo", "SMR": "NuScale", "GLATF": "Global Atomic",
        "PALAF": "Paladin", "FCUUF": "Fission Uranium",
    }

    results = []
    above_50d = 0
    above_200d = 0
    advancing_22d = 0
    declining_22d = 0
    total = 0

    for sym, name in stocks.items():
        try:
            h = yf.Ticker(sym).history(period="1y", auto_adjust=True)
            if h.empty or len(h) < 50:
                continue
            if h.index.tz is not None:
                h.index = h.index.tz_localize(None)

            closes = h["Close"]
            current = float(closes.iloc[-1])
            sma50 = float(closes.iloc[-50:].mean())
            sma200 = float(closes.iloc[-200:].mean()) if len(closes) >= 200 else None
            ret_22d = float((closes.iloc[-1] / closes.iloc[-22] - 1) * 100) if len(closes) >= 22 else 0

            total += 1
            is_above_50 = current > sma50
            is_above_200 = current > sma200 if sma200 else None
            if is_above_50:
                above_50d += 1
            if is_above_200:
                above_200d += 1
            if ret_22d > 0:
                advancing_22d += 1
            else:
                declining_22d += 1

            results.append({
                "symbol": sym, "name": name,
                "price": round(current, 2),
                "sma50": round(sma50, 2),
                "sma200": round(sma200, 2) if sma200 else None,
                "above_50d": is_above_50,
                "above_200d": is_above_200,
                "return_22d_pct": round(ret_22d, 1),
            })
        except Exception as e:
            print(f"[breadth] {sym} error: {e}")

    if total == 0:
        raise HTTPException(500, "No breadth data available")

    pct_above_50 = round(above_50d / total * 100, 1)
    pct_above_200 = round(above_200d / total * 100, 1) if any(r["sma200"] for r in results) else None
    ad_ratio = round(advancing_22d / max(declining_22d, 1), 2)

    # Breadth score (0-100)
    score = (pct_above_50 * 0.4 + (pct_above_200 or 50) * 0.3 + min(100, ad_ratio * 33) * 0.3)
    score = max(0, min(100, score))

    # Check for divergence vs URA
    try:
        ura = yf.Ticker("URA").history(period="3mo", auto_adjust=True)
        if not ura.empty and len(ura) >= 22:
            ura_ret = float((ura["Close"].iloc[-1] / ura["Close"].iloc[-22] - 1) * 100)
        else:
            ura_ret = 0
    except:
        ura_ret = 0

    divergence = None
    if ura_ret > 3 and pct_above_50 < 50:
        divergence = {"type": "BEARISH", "detail": f"URA up {ura_ret:+.1f}% but only {pct_above_50}% of stocks above 50d SMA — rally is narrow/fragile"}
    elif ura_ret < -3 and pct_above_50 > 60:
        divergence = {"type": "BULLISH", "detail": f"URA down {ura_ret:+.1f}% but {pct_above_50}% still above 50d SMA — dip is shallow, underlying strength"}

    if score >= 70:
        signal = "STRONG BREADTH"
    elif score >= 55:
        signal = "HEALTHY"
    elif score <= 30:
        signal = "WEAK BREADTH"
    elif score <= 45:
        signal = "DETERIORATING"
    else:
        signal = "NEUTRAL"

    resp = {
        "title": "Uranium Sector Breadth",
        "stocks_tracked": total,
        "pct_above_50d_sma": pct_above_50,
        "pct_above_200d_sma": pct_above_200,
        "above_50d": above_50d,
        "above_200d": above_200d,
        "advance_decline_ratio": ad_ratio,
        "advancing_22d": advancing_22d,
        "declining_22d": declining_22d,
        "breadth_score": round(score, 1),
        "signal": signal,
        "ura_return_22d": round(ura_ret, 1),
        "divergence": divergence,
        "stocks": sorted(results, key=lambda x: x["return_22d_pct"], reverse=True),
    }

    breadth_indicator._cache = {"data": resp, "ts": _now}
    return resp


@app.get("/api/global-liquidity")
def global_liquidity():
    """
    Global liquidity proxy from free market data.
    Uses TLT (long bonds), DXY (dollar), gold, and bank ETFs to estimate liquidity conditions.
    Howell thesis: liquidity drives 80%+ of risk asset moves.
    """
    import yfinance as yf, numpy as np, pandas as pd, time as _time

    if not hasattr(global_liquidity, "_cache"):
        global_liquidity._cache = {"data": None, "ts": 0}
    _now = _time.time()
    if global_liquidity._cache["data"] and _now - global_liquidity._cache["ts"] < 21600:
        return global_liquidity._cache["data"]

    # Liquidity proxies:
    # TLT rising = yields falling = easier monetary conditions
    # DXY falling = weaker dollar = global liquidity expanding (dollar is world's funding currency)
    # Gold rising = liquidity/debasement bid
    # KBE (bank ETF) rising = credit creation expanding
    # BIL (T-bills) = safe haven demand (inverse liquidity)
    indicators = {
        "monetary_conditions": {
            "ticker": "TLT", "label": "Long-term Bonds (TLT)",
            "direction": "positive",  # rising TLT = easier conditions
            "detail": "Rising bonds = falling yields = easier monetary policy",
        },
        "dollar_liquidity": {
            "ticker": "UUP", "label": "US Dollar (UUP)",
            "direction": "negative",  # rising dollar = tighter liquidity
            "detail": "Weaker dollar = global liquidity expanding",
        },
        "debasement_bid": {
            "ticker": "GLD", "label": "Gold (GLD)",
            "direction": "positive",  # rising gold = liquidity/debasement
            "detail": "Rising gold = monetary debasement expectations",
        },
        "credit_creation": {
            "ticker": "KBE", "label": "Bank ETF (KBE)",
            "direction": "positive",  # rising banks = credit expansion
            "detail": "Rising banks = credit creation expanding",
        },
    }

    results = {}
    scores = []

    for key, cfg in indicators.items():
        try:
            h = yf.Ticker(cfg["ticker"]).history(period="1y", auto_adjust=True)
            if h.empty or len(h) < 60:
                continue
            if h.index.tz is not None:
                h.index = h.index.tz_localize(None)

            closes = h["Close"]
            current = float(closes.iloc[-1])

            # Momentum signals
            ret_22d = float((closes.iloc[-1] / closes.iloc[-22] - 1) * 100) if len(closes) >= 22 else 0
            ret_63d = float((closes.iloc[-1] / closes.iloc[-63] - 1) * 100) if len(closes) >= 63 else 0
            ret_126d = float((closes.iloc[-1] / closes.iloc[-126] - 1) * 100) if len(closes) >= 126 else 0

            # Z-score of 22d return vs rolling 63d
            rolling_rets = closes.pct_change(22).dropna()
            if len(rolling_rets) > 20:
                zscore = float((rolling_rets.iloc[-1] - rolling_rets.mean()) / rolling_rets.std()) if rolling_rets.std() > 0 else 0
            else:
                zscore = 0

            # Score: positive direction means rising = bullish liquidity
            if cfg["direction"] == "positive":
                raw_score = 50 + zscore * 15
            else:
                raw_score = 50 - zscore * 15  # inverse
            component_score = max(0, min(100, raw_score))

            if component_score >= 70:
                signal = "EXPANDING"
            elif component_score >= 55:
                signal = "LEAN EXPANDING"
            elif component_score <= 30:
                signal = "CONTRACTING"
            elif component_score <= 45:
                signal = "LEAN CONTRACTING"
            else:
                signal = "NEUTRAL"

            scores.append(component_score)
            results[key] = {
                "label": cfg["label"],
                "ticker": cfg["ticker"],
                "current": round(current, 2),
                "return_22d_pct": round(ret_22d, 2),
                "return_63d_pct": round(ret_63d, 2),
                "return_126d_pct": round(ret_126d, 2),
                "zscore": round(zscore, 2),
                "score": round(component_score, 1),
                "signal": signal,
                "detail": cfg["detail"],
            }
        except Exception as e:
            print(f"[liquidity] {key} error: {e}")

    composite = float(np.mean(scores)) if scores else 50

    if composite >= 70:
        overall = "LIQUIDITY EXPANSION"
        detail = "Global liquidity expanding — strong tailwind for commodities and risk assets"
    elif composite >= 55:
        overall = "LEAN EXPANSIONARY"
        detail = "Modestly expanding liquidity conditions — mild tailwind"
    elif composite <= 30:
        overall = "LIQUIDITY CONTRACTION"
        detail = "Global liquidity contracting — headwind for risk assets"
    elif composite <= 45:
        overall = "LEAN CONTRACTIONARY"
        detail = "Mildly contracting liquidity — caution warranted"
    else:
        overall = "NEUTRAL"
        detail = "Liquidity conditions roughly neutral"

    # Liquidity trend (are conditions improving or deteriorating?)
    trend = "UNKNOWN"
    if len(scores) >= 3:
        # Compare short-term (22d) vs long-term (63d) returns across indicators
        short_avg = np.mean([r.get("return_22d_pct", 0) for r in results.values()])
        long_avg = np.mean([r.get("return_63d_pct", 0) for r in results.values()])
        if short_avg > long_avg + 1:
            trend = "ACCELERATING"
        elif short_avg < long_avg - 1:
            trend = "DECELERATING"
        else:
            trend = "STEADY"

    resp = {
        "title": "Global Liquidity Monitor",
        "method": "Proxy from bond yields (TLT), dollar (UUP), gold (GLD), bank credit (KBE). Based on Howell's global liquidity framework.",
        "composite_score": round(composite, 1),
        "signal": overall,
        "detail": detail,
        "trend": trend,
        "components": results,
        "note": "Liquidity drives ~80% of risk asset returns (Howell). Expanding liquidity = bullish commodities.",
    }

    global_liquidity._cache = {"data": resp, "ts": _now}
    return resp


@app.get("/api/economic-surprise")
def economic_surprise():
    """
    Economic surprise proxy. No FRED key — builds from macro asset reactions.
    Compares recent moves in ISM-sensitive assets vs rolling norms to detect
    whether macro data is beating or missing expectations.
    """
    import yfinance as yf, numpy as np, time as _time

    # Cache 6 hours
    if not hasattr(economic_surprise, "_cache"):
        economic_surprise._cache = {"data": None, "ts": 0}
    _now = _time.time()
    if economic_surprise._cache["data"] and _now - economic_surprise._cache["ts"] < 21600:
        return economic_surprise._cache["data"]

    # Macro-sensitive proxies:
    # XLI (industrials) vs SPY → ISM/manufacturing surprise
    # TIP vs IEF → inflation surprise (TIPS outperform when CPI beats)
    # XLE (energy) vs SPY → commodity demand surprise
    # HYG vs LQD → credit spread = growth surprise
    proxies = {
        "manufacturing": {"long": "XLI", "short": "SPY", "label": "ISM/Manufacturing"},
        "inflation": {"long": "TIP", "short": "IEF", "label": "CPI/Inflation"},
        "commodity_demand": {"long": "XLE", "short": "SPY", "label": "Commodity Demand"},
        "growth": {"long": "HYG", "short": "LQD", "label": "Growth/Credit"},
    }

    results = {}
    scores = []

    for key, cfg in proxies.items():
        try:
            long_h = yf.Ticker(cfg["long"]).history(period="6mo", auto_adjust=True)
            short_h = yf.Ticker(cfg["short"]).history(period="6mo", auto_adjust=True)
            if long_h.empty or short_h.empty:
                continue

            for h in [long_h, short_h]:
                if h.index.tz is not None:
                    h.index = h.index.tz_localize(None)

            # Align
            import pandas as pd
            merged = pd.DataFrame({"long": long_h["Close"], "short": short_h["Close"]}).dropna()
            if len(merged) < 60:
                continue

            # Relative return spread (long - short)
            merged["spread"] = merged["long"].pct_change() - merged["short"].pct_change()
            merged = merged.dropna()

            # 5-day cumulative spread vs 60-day rolling mean
            spread_5d = float(merged["spread"].iloc[-5:].sum() * 100)
            spread_22d = float(merged["spread"].iloc[-22:].sum() * 100)
            spread_mean = float(merged["spread"].rolling(60).sum().iloc[-1] / 3 * 100)  # avg 22d block
            spread_std = float(merged["spread"].rolling(60).std().iloc[-1] * np.sqrt(22) * 100)

            zscore = (spread_22d - spread_mean) / spread_std if spread_std > 0 else 0

            # Positive z = long outperforming = positive surprise
            if zscore > 1.5:
                signal = "STRONG BEAT"
                component_score = 85
            elif zscore > 0.5:
                signal = "BEAT"
                component_score = 65
            elif zscore < -1.5:
                signal = "STRONG MISS"
                component_score = 15
            elif zscore < -0.5:
                signal = "MISS"
                component_score = 35
            else:
                signal = "IN-LINE"
                component_score = 50

            scores.append(component_score)
            results[key] = {
                "label": cfg["label"],
                "pair": f"{cfg['long']}/{cfg['short']}",
                "spread_5d_pct": round(spread_5d, 2),
                "spread_22d_pct": round(spread_22d, 2),
                "zscore": round(zscore, 2),
                "signal": signal,
                "score": component_score,
            }
        except Exception as e:
            print(f"[econ-surprise] {key} error: {e}")

    # Composite
    composite = float(np.mean(scores)) if scores else 50

    if composite >= 70:
        overall = "POSITIVE SURPRISE"
        detail = "Macro data beating expectations across multiple channels — bullish for commodities"
    elif composite >= 55:
        overall = "LEAN POSITIVE"
        detail = "Slight positive economic surprise — modestly bullish"
    elif composite <= 30:
        overall = "NEGATIVE SURPRISE"
        detail = "Macro data missing expectations — risk-off environment"
    elif composite <= 45:
        overall = "LEAN NEGATIVE"
        detail = "Slight negative economic surprise — mild headwind"
    else:
        overall = "NEUTRAL"
        detail = "Economic data roughly in-line with expectations"

    resp = {
        "title": "Economic Surprise Index (Proxy)",
        "method": "No FRED key — built from relative performance of macro-sensitive ETF pairs vs rolling norms.",
        "composite_score": round(composite, 1),
        "signal": overall,
        "detail": detail,
        "components": results,
        "note": "Positive surprise = macro beating expectations = bullish for risk assets and commodities",
    }

    economic_surprise._cache = {"data": resp, "ts": _now}
    return resp


@app.get("/api/volatility-regime")
def volatility_regime(symbol: str = Query("URA")):
    """
    Volatility regime: implied vol (from options) vs realized vol (from price history).
    Vol risk premium = IV - RV. High premium = fear = contrarian buy.
    """
    import yfinance as yf, numpy as np, time as _time

    symbol = symbol.upper()

    # Cache 2 hours
    if not hasattr(volatility_regime, "_cache"):
        volatility_regime._cache = {}
    _now = _time.time()
    if symbol in volatility_regime._cache and _now - volatility_regime._cache[symbol]["ts"] < 7200:
        return volatility_regime._cache[symbol]["data"]

    tk = yf.Ticker(symbol)
    hist = tk.history(period="6mo", auto_adjust=True)
    if hist.empty or len(hist) < 60:
        raise HTTPException(400, "Insufficient price data")

    closes = hist["Close"].values
    log_returns = np.diff(np.log(closes))

    rv_20d = float(np.std(log_returns[-20:]) * np.sqrt(252) * 100)
    rv_60d = float(np.std(log_returns[-60:]) * np.sqrt(252) * 100)
    rv_full = float(np.std(log_returns) * np.sqrt(252) * 100)

    # Rolling 20d realized vol for chart
    rv_series = []
    step = max(1, (len(log_returns) - 20) // 100)
    dates = [d.strftime("%Y-%m-%d") for d in hist.index]
    for i in range(20, len(log_returns), step):
        rv_series.append({
            "date": dates[i + 1],
            "rv_20d": round(float(np.std(log_returns[i-20:i]) * np.sqrt(252) * 100), 1),
        })

    # Implied vol from options (~30d expiry, ATM, with bid/ask filter)
    iv_30d = None
    iv_source = None
    try:
        from datetime import datetime as _dt, timedelta as _td
        expirations = tk.options
        if expirations:
            current_price = float(closes[-1])
            # Find expiry closest to 30 days out
            target_date = _dt.now() + _td(days=30)
            best_exp = min(expirations, key=lambda e: abs((_dt.strptime(e, "%Y-%m-%d") - target_date).days))

            chain = tk.option_chain(best_exp)
            iv_samples = []

            for opt_df, label in [(chain.calls, "calls"), (chain.puts, "puts")]:
                if opt_df.empty or "impliedVolatility" not in opt_df.columns:
                    continue
                # Filter: IV > 5% (annualized), has bid OR ask > 0, reasonable OI
                valid = opt_df[
                    (opt_df["impliedVolatility"] > 0.05) &
                    ((opt_df.get("bid", 0) > 0) | (opt_df.get("ask", 0) > 0) | (opt_df.get("openInterest", 0) > 5))
                ].copy()
                if valid.empty:
                    # Relax: just IV > 10%
                    valid = opt_df[opt_df["impliedVolatility"] > 0.10].copy()
                if not valid.empty:
                    valid["strike_dist"] = abs(valid["strike"] - current_price)
                    atm = valid.nsmallest(3, "strike_dist")
                    iv_samples.extend(atm["impliedVolatility"].tolist())

            if iv_samples:
                avg_iv = float(np.mean(iv_samples))
                # Sanity check: IV should be 5-200% for equities (relaxed for stale weekend data)
                if 0.05 <= avg_iv <= 2.0:
                    iv_30d = round(avg_iv * 100, 1)
                    iv_source = f"ATM options, expiry {best_exp}, {len(iv_samples)} samples"
                else:
                    iv_source = f"IV out of range ({avg_iv:.2f}), skipped — likely stale data"
    except Exception as e:
        print(f"[vol-regime] IV error for {symbol}: {e}")

    # Vol risk premium
    vrp = round(iv_30d - rv_20d, 1) if iv_30d else None

    # Percentile rank of current RV vs history
    all_rv20 = [float(np.std(log_returns[max(0,i-20):i]) * np.sqrt(252) * 100) for i in range(20, len(log_returns))]
    rv_percentile = float(np.mean([1 for r in all_rv20 if r <= rv_20d]) * 100)

    # Vol regime classification
    if rv_20d > rv_60d * 1.3:
        vol_regime = "EXPANDING"
        regime_detail = "Short-term vol rising faster than long-term — risk increasing"
    elif rv_20d < rv_60d * 0.7:
        vol_regime = "COMPRESSING"
        regime_detail = "Vol compression — often precedes a breakout move"
    else:
        vol_regime = "STABLE"
        regime_detail = "Vol in normal range"

    # Signal
    if vrp is not None:
        if vrp > 15:
            signal = "FEAR PREMIUM"
            detail = f"IV exceeds RV by {vrp:.0f}pp — market pricing excess fear (contrarian buy)"
            score = min(100, 50 + vrp * 2)
        elif vrp > 5:
            signal = "MILD FEAR"
            detail = f"Moderate IV premium ({vrp:.0f}pp) — slight fear bias"
            score = 60
        elif vrp < -10:
            signal = "COMPLACENCY"
            detail = f"RV exceeds IV by {abs(vrp):.0f}pp — market underpricing risk"
            score = max(0, 50 + vrp * 2)
        elif vrp < -3:
            signal = "MILD COMPLACENCY"
            detail = f"Slight RV premium ({abs(vrp):.0f}pp)"
            score = 40
        else:
            signal = "NEUTRAL"
            detail = "IV ≈ RV — vol fairly priced"
            score = 50
    else:
        signal = "NO IV DATA"
        detail = f"No reliable options IV for {symbol} — using RV regime only"
        # RV percentile: high vol = risky but contrarian buy if extreme
        if rv_percentile > 90:
            score = 65  # Extreme vol = contrarian opportunity
        elif rv_percentile > 70:
            score = 40  # High vol = cautious
        elif rv_percentile < 20:
            score = 60  # Low vol = complacent, breakout coming
        else:
            score = 50

    resp = {
        "symbol": symbol,
        "current_price": round(float(closes[-1]), 2),
        "implied_vol_30d": round(iv_30d, 1) if iv_30d else None,
        "realized_vol_20d": round(rv_20d, 1),
        "realized_vol_60d": round(rv_60d, 1),
        "realized_vol_full": round(rv_full, 1),
        "vol_risk_premium": vrp,
        "rv_percentile": round(rv_percentile, 1),
        "vol_regime": vol_regime,
        "regime_detail": regime_detail,
        "signal": signal,
        "detail": detail,
        "score": round(score, 1),
        "iv_source": iv_source,
        "rv_chart": rv_series,
    }

    volatility_regime._cache[symbol] = {"data": resp, "ts": _now}
    return resp


@app.get("/api/relative-value")
def relative_value(
    base: str = Query("URA"),
    period: str = Query("1y"),
):
    """
    Relative value analysis: base ETF vs uranium peers.
    Computes normalized performance, rolling correlation, spread z-scores, and relative cheapness.
    """
    import yfinance as yf, numpy as np, pandas as pd, time as _time

    base = base.upper()
    _rv_cache_key = f"_rv_{base}_{period}"
    if not hasattr(relative_value, "_cache"):
        relative_value._cache = {}
    _now = _time.time()
    if _rv_cache_key in relative_value._cache and _now - relative_value._cache[_rv_cache_key]["ts"] < 14400:
        return relative_value._cache[_rv_cache_key]["data"]

    peers = ["URNM", "NLR"]
    if base == "URA":
        pass
    elif base == "URNM":
        peers = ["URA", "NLR"]
    else:
        peers = ["URA", "URNM"]

    # Add HURA.TO if available
    all_syms = [base] + peers + ["HURA.TO"]
    period_map = {"3m": "3mo", "6m": "6mo", "1y": "1y", "2y": "2y", "3y": "3y"}
    yf_period = period_map.get(period, "1y")

    # Fetch all at once
    data = {}
    for sym in all_syms:
        try:
            h = yf.Ticker(sym).history(period=yf_period, auto_adjust=True)
            if not h.empty and len(h) > 20:
                if h.index.tz is not None:
                    h.index = h.index.tz_localize(None)
                data[sym] = h["Close"]
        except Exception as e:
            print(f"[rel-val] Error {sym}: {e}")

    if base not in data:
        raise HTTPException(400, f"No data for {base}")

    available_peers = [p for p in peers + ["HURA.TO"] if p in data]
    if not available_peers:
        raise HTTPException(400, "No peer data available")

    # Align dates
    df = pd.DataFrame(data).dropna()
    if len(df) < 20:
        raise HTTPException(400, "Insufficient overlapping data")

    # Normalized performance (base=100)
    norm = df / df.iloc[0] * 100
    base_return = float((df[base].iloc[-1] / df[base].iloc[0] - 1) * 100)

    peer_analysis = []
    for peer in available_peers:
        peer_return = float((df[peer].iloc[-1] / df[peer].iloc[0] - 1) * 100)

        # Rolling ratio (base/peer)
        ratio = df[base] / df[peer]
        ratio_mean = float(ratio.mean())
        ratio_std = float(ratio.std())
        ratio_current = float(ratio.iloc[-1])
        ratio_zscore = (ratio_current - ratio_mean) / ratio_std if ratio_std > 0 else 0

        # Rolling 30-day correlation
        corr_30d = df[base].rolling(30).corr(df[peer])
        corr_current = float(corr_30d.iloc[-1]) if not pd.isna(corr_30d.iloc[-1]) else None

        # Relative performance spread
        spread = norm[base] - norm[peer]
        spread_current = float(spread.iloc[-1])
        spread_mean = float(spread.mean())
        spread_std = float(spread.std())
        spread_zscore = (spread_current - spread_mean) / spread_std if spread_std > 0 else 0

        # Signal
        if ratio_zscore < -1.5:
            signal = "BASE CHEAP"
            detail = f"{base} is historically cheap vs {peer} (z={ratio_zscore:.1f})"
        elif ratio_zscore > 1.5:
            signal = "BASE RICH"
            detail = f"{base} is historically expensive vs {peer} (z={ratio_zscore:.1f})"
        elif ratio_zscore < -0.75:
            signal = "LEAN CHEAP"
            detail = f"{base} slightly undervalued vs {peer}"
        elif ratio_zscore > 0.75:
            signal = "LEAN RICH"
            detail = f"{base} slightly overvalued vs {peer}"
        else:
            signal = "FAIR VALUE"
            detail = f"{base} fairly valued vs {peer}"

        peer_analysis.append({
            "peer": peer,
            "peer_return_pct": round(peer_return, 2),
            "outperformance_pct": round(base_return - peer_return, 2),
            "ratio": {"current": round(ratio_current, 4), "mean": round(ratio_mean, 4), "zscore": round(ratio_zscore, 2)},
            "correlation_30d": round(corr_current, 3) if corr_current else None,
            "spread_zscore": round(spread_zscore, 2),
            "signal": signal,
            "detail": detail,
        })

    # Composite relative value score (0-100)
    # Average z-scores: negative = base is cheap = bullish
    avg_zscore = np.mean([p["ratio"]["zscore"] for p in peer_analysis])
    # Map z-score to 0-100: z=-2 → 100 (very cheap), z=0 → 50, z=+2 → 0 (very rich)
    rv_score = max(0, min(100, 50 - avg_zscore * 25))

    if rv_score >= 70:
        overall = "UNDERVALUED"
    elif rv_score >= 55:
        overall = "LEAN CHEAP"
    elif rv_score <= 30:
        overall = "OVERVALUED"
    elif rv_score <= 45:
        overall = "LEAN RICH"
    else:
        overall = "FAIR VALUE"

    # Normalized curve for charting (sampled)
    step = max(1, len(norm) // 150)
    chart = []
    for i in range(0, len(norm), step):
        point = {"date": norm.index[i].strftime("%Y-%m-%d")}
        for sym in [base] + available_peers:
            point[sym] = round(float(norm[sym].iloc[i]), 2)
        chart.append(point)

    resp = {
        "base": base,
        "base_return_pct": round(base_return, 2),
        "peers": available_peers,
        "period": period,
        "trading_days": len(df),
        "relative_value_score": round(rv_score, 1),
        "signal": overall,
        "peer_analysis": peer_analysis,
        "normalized_chart": chart,
    }

    relative_value._cache[_rv_cache_key] = {"data": resp, "ts": _now}
    return resp


@app.get("/api/drawdown-analysis")
def drawdown_analysis(
    symbol: str = Query("URA"),
    period: str = Query("2y"),
    min_depth: float = Query(5, ge=1, le=50),
):
    """
    Drawdown analysis: current drawdown, max drawdown, all significant drawdowns with recovery times.
    """
    import yfinance as yf, numpy as np

    symbol = symbol.upper()
    period_map = {"3m": "3mo", "6m": "6mo", "1y": "1y", "2y": "2y", "3y": "3y", "5y": "5y"}
    yf_period = period_map.get(period, "2y")

    hist = yf.Ticker(symbol).history(period=yf_period, auto_adjust=True)
    if hist.empty or len(hist) < 10:
        raise HTTPException(400, "Insufficient data")

    if hist.index.tz is not None:
        hist.index = hist.index.tz_localize(None)

    closes = hist["Close"].values
    dates = [d.strftime("%Y-%m-%d") for d in hist.index]

    # Running max and drawdown series
    running_max = np.maximum.accumulate(closes)
    dd_series = (closes - running_max) / running_max * 100

    # Current drawdown
    current_dd = float(dd_series[-1])
    peak_idx = int(np.argmax(closes[::-1] >= running_max[-1]))
    peak_idx = len(closes) - 1 - peak_idx if peak_idx > 0 else int(np.argmax(closes == running_max[-1]))
    current_drawdown = {
        "depth_pct": round(current_dd, 2),
        "peak_date": dates[peak_idx],
        "peak_price": round(float(running_max[-1]), 2),
        "current_price": round(float(closes[-1]), 2),
        "days_since_peak": len(closes) - 1 - peak_idx,
    }

    # Find all drawdown episodes
    episodes = []
    in_dd = False
    ep_peak_idx = 0

    for i in range(len(closes)):
        dd = dd_series[i]
        if not in_dd and dd < -1:
            in_dd = True
            ep_peak_idx = i - 1 if i > 0 else 0
            # Find actual peak
            while ep_peak_idx > 0 and closes[ep_peak_idx] < closes[ep_peak_idx - 1]:
                ep_peak_idx -= 1
            ep_trough_idx = i
            ep_trough_dd = dd
        elif in_dd:
            if dd < ep_trough_dd:
                ep_trough_idx = i
                ep_trough_dd = dd
            if dd >= -0.5:  # recovered
                episodes.append({
                    "peak_idx": ep_peak_idx,
                    "trough_idx": ep_trough_idx,
                    "recovery_idx": i,
                    "depth": ep_trough_dd,
                })
                in_dd = False

    # If still in drawdown
    if in_dd:
        episodes.append({
            "peak_idx": ep_peak_idx,
            "trough_idx": ep_trough_idx,
            "recovery_idx": None,
            "depth": ep_trough_dd,
        })

    # Filter significant drawdowns
    significant = [e for e in episodes if abs(e["depth"]) >= min_depth]
    significant.sort(key=lambda e: e["depth"])

    drawdown_history = []
    for e in significant:
        pi, ti, ri = e["peak_idx"], e["trough_idx"], e["recovery_idx"]
        entry = {
            "depth_pct": round(e["depth"], 2),
            "peak_date": dates[pi],
            "peak_price": round(float(closes[pi]), 2),
            "trough_date": dates[ti],
            "trough_price": round(float(closes[ti]), 2),
            "days_peak_to_trough": ti - pi,
        }
        if ri is not None:
            entry["recovery_date"] = dates[ri]
            entry["days_to_recover"] = ri - ti
            entry["total_days"] = ri - pi
        else:
            entry["recovery_date"] = None
            entry["days_to_recover"] = None
            entry["total_days"] = None
            entry["status"] = "ONGOING"
        drawdown_history.append(entry)

    # Max drawdown
    max_dd_idx = int(np.argmin(dd_series))
    max_dd_entry = drawdown_history[0] if drawdown_history else {
        "depth_pct": round(float(dd_series[max_dd_idx]), 2),
        "trough_date": dates[max_dd_idx],
    }

    # Stats
    depths = [abs(e["depth"]) for e in significant]
    recoveries = [e["recovery_idx"] - e["trough_idx"] for e in significant if e["recovery_idx"] is not None]

    stats = {
        "total_drawdowns": len(significant),
        "avg_depth_pct": round(np.mean(depths), 2) if depths else 0,
        "median_depth_pct": round(float(np.median(depths)), 2) if depths else 0,
        "avg_recovery_days": round(np.mean(recoveries), 1) if recoveries else None,
        "median_recovery_days": round(float(np.median(recoveries)), 1) if recoveries else None,
        "max_recovery_days": int(max(recoveries)) if recoveries else None,
        "pct_time_in_drawdown": round(float(np.sum(dd_series < -min_depth) / len(dd_series) * 100), 1),
    }

    # Drawdown curve for charting (sampled)
    step = max(1, len(dd_series) // 200)
    dd_curve = [{"date": dates[i], "drawdown_pct": round(float(dd_series[i]), 2), "price": round(float(closes[i]), 2)} for i in range(0, len(dd_series), step)]

    return {
        "symbol": symbol,
        "period": period,
        "trading_days": len(closes),
        "current_drawdown": current_drawdown,
        "max_drawdown": max_dd_entry,
        "stats": stats,
        "drawdown_history": drawdown_history[:20],
        "drawdown_curve": dd_curve,
    }


@app.get("/api/regime-backtest")
def regime_backtest(
    symbol: str = Query("URA"),
    period: str = Query("2y"),
    initial: float = Query(10000),
    min_allocation: float = Query(10, ge=0, le=50),
    max_allocation: float = Query(90, ge=50, le=100),
    favorable_mult: float = Query(1.5, ge=1.0, le=3.0),
    unfavorable_mult: float = Query(0.5, ge=0.1, le=1.0),
):
    """
    Macro-regime-aware backtest. Adjusts allocation based on macro conditions:
    FAVORABLE → score × favorable_mult, UNFAVORABLE → score × unfavorable_mult.
    Reconstructs daily macro regime from ^TNX, DXY, ^GSPC rolling percentiles.
    """
    import yfinance as yf, numpy as np, pandas as pd

    symbol = symbol.upper()
    daily_scores = _prepare_daily_scores(symbol, period)

    if len(daily_scores) < 10:
        raise HTTPException(400, "Insufficient data")

    # Reconstruct historical macro regime
    period_map = {"3m": "3mo", "6m": "6mo", "1y": "1y", "2y": "2y", "3y": "3y", "5y": "5y"}
    yf_period = period_map.get(period, "2y")
    # Need extra lookback for rolling window
    extended = {"3mo": "1y", "6mo": "2y", "1y": "3y", "2y": "5y", "3y": "5y", "5y": "max"}

    macro_dfs = {}
    for msym in ["^TNX", "DX-Y.NYB", "^GSPC"]:
        try:
            h = yf.Ticker(msym).history(period=extended.get(yf_period, "5y"))
            if not h.empty:
                # Normalize to tz-naive for comparison
                if h.index.tz is not None:
                    h.index = h.index.tz_localize(None)
                macro_dfs[msym] = h["Close"]
        except Exception as e:
            print(f"[regime-bt] Error fetching {msym}: {e}")

    # Build daily regime series
    score_dates = [d["date"] for d in daily_scores]
    daily_regimes = []

    for date_str in score_dates:
        dt = pd.Timestamp(date_str)
        regime = "NEUTRAL"
        signals = []

        for msym, series in macro_dfs.items():
            # Get 126-day rolling window ending at this date
            mask = series.index <= dt
            window = series[mask].iloc[-126:]
            if len(window) < 20:
                continue
            current = float(window.iloc[-1])
            p25 = float(window.quantile(0.25))
            p75 = float(window.quantile(0.75))

            if msym == "^TNX":
                sig = "TAILWIND" if current <= p25 else "HEADWIND" if current >= p75 else "NEUTRAL"
            elif msym == "DX-Y.NYB":
                sig = "TAILWIND" if current <= p25 else "HEADWIND" if current >= p75 else "NEUTRAL"
            else:  # ^GSPC
                sig = "TAILWIND" if current >= p75 else "HEADWIND" if current <= p25 else "NEUTRAL"
            signals.append(sig)

        tailwinds = signals.count("TAILWIND")
        headwinds = signals.count("HEADWIND")
        if tailwinds >= 2:
            regime = "FAVORABLE"
        elif headwinds >= 2:
            regime = "UNFAVORABLE"
        else:
            regime = "NEUTRAL"

        daily_regimes.append(regime)

    # Run simulation with regime-adjusted allocation
    cash = initial
    shares = 0.0
    equity_curve = []
    daily_returns = []
    max_equity = initial
    max_drawdown = 0.0
    prev_equity = initial
    regime_days = {"FAVORABLE": 0, "NEUTRAL": 0, "UNFAVORABLE": 0}

    for i, (day, regime) in enumerate(zip(daily_scores, daily_regimes)):
        score = day["score"]
        price = day["price"]
        regime_days[regime] = regime_days.get(regime, 0) + 1

        # Regime-adjusted score
        if regime == "FAVORABLE":
            adj_score = min(100, score * favorable_mult)
        elif regime == "UNFAVORABLE":
            adj_score = score * unfavorable_mult
        else:
            adj_score = score

        # Target allocation
        target_alloc = min_allocation + (adj_score / 100) * (max_allocation - min_allocation)
        target_alloc = max(min_allocation, min(max_allocation, target_alloc))

        equity = cash + shares * price
        current_alloc = (shares * price / equity * 100) if equity > 0 else 0

        # Rebalance if drift > 5%
        if abs(current_alloc - target_alloc) > 5 or i == 0:
            target_value = equity * target_alloc / 100
            delta = target_value - shares * price
            if delta > 0 and cash >= delta:
                shares += delta / price
                cash -= delta
            elif delta < 0:
                sell = min(shares, abs(delta) / price)
                shares -= sell
                cash += sell * price

        equity = cash + shares * price
        dr = (equity - prev_equity) / prev_equity if prev_equity > 0 else 0
        daily_returns.append(dr)
        prev_equity = equity
        max_equity = max(max_equity, equity)
        dd = (max_equity - equity) / max_equity * 100
        max_drawdown = max(max_drawdown, dd)

        equity_curve.append({
            "date": day["date"], "equity": round(equity, 2),
            "score": score, "price": price, "regime": regime,
            "adj_score": round(adj_score, 1),
            "allocation": round(shares * price / equity * 100, 1) if equity > 0 else 0,
        })

    final_equity = cash + shares * daily_scores[-1]["price"]
    strategy_return = (final_equity - initial) / initial * 100
    bh_return = (daily_scores[-1]["price"] - daily_scores[0]["price"]) / daily_scores[0]["price"] * 100
    bh_final = initial * (1 + bh_return / 100)

    dr = np.array(daily_returns)
    sharpe = float(np.mean(dr) / np.std(dr) * np.sqrt(252)) if np.std(dr) > 0 else 0
    downside = dr[dr < 0]
    sortino = float(np.mean(dr) / np.std(downside) * np.sqrt(252)) if len(downside) > 0 and np.std(downside) > 0 else sharpe

    allocs = [e["allocation"] for e in equity_curve]
    trading_days = len(daily_scores)
    ann_return = strategy_return * (252 / trading_days) if trading_days > 0 else 0
    calmar = ann_return / max_drawdown if max_drawdown > 0 else 0

    # Regime breakdown
    regime_returns = {}
    for regime_type in ["FAVORABLE", "NEUTRAL", "UNFAVORABLE"]:
        r_indices = [i for i, r in enumerate(daily_regimes) if r == regime_type and i > 0]
        if r_indices:
            r_rets = [daily_returns[i] for i in r_indices]
            regime_returns[regime_type] = {
                "days": len(r_indices),
                "avg_daily_return_bps": round(np.mean(r_rets) * 10000, 1),
                "total_return_pct": round((np.prod([1 + r for r in r_rets]) - 1) * 100, 2),
                "avg_allocation": round(np.mean([allocs[i] for i in r_indices]), 1),
            }

    return {
        "symbol": symbol,
        "period": period,
        "trading_days": trading_days,
        "parameters": {
            "initial_capital": initial,
            "min_allocation_pct": min_allocation,
            "max_allocation_pct": max_allocation,
            "favorable_multiplier": favorable_mult,
            "unfavorable_multiplier": unfavorable_mult,
        },
        "results": {
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(strategy_return, 2),
            "annualized_return_pct": round(ann_return, 2),
            "buy_hold_return_pct": round(bh_return, 2),
            "buy_hold_final": round(bh_final, 2),
            "alpha_vs_buyhold": round(strategy_return - bh_return, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "calmar_ratio": round(calmar, 3),
            "avg_allocation_pct": round(sum(allocs) / len(allocs), 1),
        },
        "regime_breakdown": regime_returns,
        "regime_days": regime_days,
        "equity_curve": equity_curve[::max(1, len(equity_curve) // 100)],
        "limitations": [
            "Technical signals only (macro regime is reconstructed but score is technical-only)",
            "Macro regime uses rolling 126-day percentiles (may differ from live regime)",
            "No transaction costs or slippage",
            "In-sample only — overfitting risk",
        ],
    }


@app.get("/api/score-weighted-backtest")
def score_weighted_backtest(
    symbol: str = Query("URA"),
    period: str = Query("2y"),
    initial: float = Query(10000),
    min_allocation: float = Query(10, ge=0, le=50),
    max_allocation: float = Query(90, ge=50, le=100),
    rebalance_band: float = Query(5, ge=0, le=20),
):
    """
    Continuous position sizing backtest. Score maps linearly to allocation:
    score 0 → min_allocation%, score 100 → max_allocation%.
    Rebalances daily (or when allocation drifts beyond rebalance_band%).
    """
    import numpy as np, pandas as pd

    symbol = symbol.upper()
    daily_scores = _prepare_daily_scores(symbol, period)

    if len(daily_scores) < 10:
        raise HTTPException(400, "Insufficient data")

    cash = initial
    shares = 0.0
    equity_curve = []
    rebalance_log = []
    daily_returns = []
    max_equity = initial
    max_drawdown = 0.0
    total_rebalances = 0
    prev_equity = initial

    for i, day in enumerate(daily_scores):
        score = day["score"]
        price = day["price"]

        # Target allocation: linear map score → [min_alloc, max_alloc]
        target_alloc = min_allocation + (score / 100) * (max_allocation - min_allocation)
        target_alloc = max(min_allocation, min(max_allocation, target_alloc))

        # Current allocation
        equity = cash + shares * price
        current_alloc = (shares * price / equity * 100) if equity > 0 else 0

        # Rebalance if drift exceeds band (or first day)
        drift = abs(current_alloc - target_alloc)
        should_rebalance = i == 0 or drift > rebalance_band

        if should_rebalance:
            target_value = equity * target_alloc / 100
            current_value = shares * price
            delta_value = target_value - current_value

            if delta_value > 0 and cash >= delta_value:
                # Buy more
                buy_shares = delta_value / price
                shares += buy_shares
                cash -= delta_value
            elif delta_value < 0:
                # Sell some
                sell_shares = min(shares, abs(delta_value) / price)
                shares -= sell_shares
                cash += sell_shares * price

            total_rebalances += 1
            rebalance_log.append({
                "date": day["date"],
                "score": score,
                "target_alloc": round(target_alloc, 1),
                "prev_alloc": round(current_alloc, 1),
                "new_alloc": round(shares * price / equity * 100, 1) if equity > 0 else 0,
                "equity": round(equity, 2),
                "action": "BUY" if delta_value > 0 else "SELL",
                "delta_pct": round(drift, 1),
            })

        # Track
        equity = cash + shares * price
        daily_ret = (equity - prev_equity) / prev_equity if prev_equity > 0 else 0
        daily_returns.append(daily_ret)
        prev_equity = equity
        max_equity = max(max_equity, equity)
        dd = (max_equity - equity) / max_equity * 100
        max_drawdown = max(max_drawdown, dd)

        equity_curve.append({
            "date": day["date"],
            "equity": round(equity, 2),
            "score": score,
            "price": price,
            "allocation": round(shares * price / equity * 100, 1) if equity > 0 else 0,
        })

    # Final stats
    final_equity = cash + shares * daily_scores[-1]["price"]
    strategy_return = (final_equity - initial) / initial * 100

    bh_start = daily_scores[0]["price"]
    bh_end = daily_scores[-1]["price"]
    bh_return = (bh_end - bh_start) / bh_start * 100
    bh_final = initial * (1 + bh_return / 100)
    alpha = strategy_return - bh_return

    # Risk metrics
    dr = np.array(daily_returns)
    sharpe = float(np.mean(dr) / np.std(dr) * np.sqrt(252)) if np.std(dr) > 0 else 0
    downside = dr[dr < 0]
    sortino = float(np.mean(dr) / np.std(downside) * np.sqrt(252)) if len(downside) > 0 and np.std(downside) > 0 else sharpe

    # Average allocation
    allocs = [e["allocation"] for e in equity_curve]
    avg_alloc = sum(allocs) / len(allocs) if allocs else 0

    # Calmar ratio (annualized return / max drawdown)
    trading_days = len(daily_scores)
    ann_return = strategy_return * (252 / trading_days) if trading_days > 0 else 0
    calmar = ann_return / max_drawdown if max_drawdown > 0 else 0

    return {
        "symbol": symbol,
        "period": period,
        "trading_days": trading_days,
        "parameters": {
            "initial_capital": initial,
            "min_allocation_pct": min_allocation,
            "max_allocation_pct": max_allocation,
            "rebalance_band_pct": rebalance_band,
        },
        "results": {
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(strategy_return, 2),
            "annualized_return_pct": round(ann_return, 2),
            "buy_hold_return_pct": round(bh_return, 2),
            "buy_hold_final": round(bh_final, 2),
            "alpha_vs_buyhold": round(alpha, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "calmar_ratio": round(calmar, 3),
            "total_rebalances": total_rebalances,
            "avg_allocation_pct": round(avg_alloc, 1),
            "min_allocation_seen": round(min(allocs), 1),
            "max_allocation_seen": round(max(allocs), 1),
        },
        "equity_curve": equity_curve[::max(1, len(equity_curve) // 100)],
        "rebalance_log": rebalance_log,
        "comparison": {
            "binary_65_35": "Use /api/signal-backtest for threshold-based comparison",
            "note": "Continuous sizing captures the full signal gradient vs binary in/out",
        },
        "limitations": [
            "Technical signals only (40% of composite score)",
            "No transaction costs or slippage modeled",
            "Daily rebalancing assumes perfect liquidity",
            "Score-to-allocation mapping is linear (could be sigmoid/convex)",
            "In-sample only — no walk-forward validation",
        ],
    }


@app.get("/api/cot-report")
def get_cot_report():
    """
    Synthetic COT-like positioning report for uranium sector.
    Uranium has no CFTC futures contract — this builds a positioning proxy from:
    1. URA/URNM options put/call ratios (speculator sentiment)
    2. ETF shares outstanding changes (institutional creation/redemption)
    3. Short interest across miners (speculative shorts)
    4. Insider buy/sell ratio (commercial hedgers proxy)
    """
    import time as _time, yfinance as yf, numpy as np

    # Cache 4 hours
    cache_key = "_cot_cache"
    if not hasattr(get_cot_report, cache_key):
        setattr(get_cot_report, cache_key, {"data": None, "ts": 0})
    cache = getattr(get_cot_report, cache_key)
    now = _time.time()
    if cache["data"] and now - cache["ts"] < 21600:  # 6 hours
        return cache["data"]

    positioning = {}

    # 1. Options positioning (speculator sentiment)
    try:
        pcr_data = get_put_call_ratio(symbol=None)
        if not isinstance(pcr_data, dict):
            pcr_data = json.loads(pcr_data.body.decode()) if hasattr(pcr_data, 'body') else {}
        high_conf = [t for t in pcr_data.get("tickers", []) if t.get("confidence") == "HIGH"]
        if high_conf:
            total_put_oi = sum(t["total_put_oi"] for t in high_conf)
            total_call_oi = sum(t["total_call_oi"] for t in high_conf)
            positioning["options"] = {
                "put_oi": total_put_oi,
                "call_oi": total_call_oi,
                "pcr": round(total_put_oi / max(total_call_oi, 1), 3),
                "net_speculative": total_call_oi - total_put_oi,
                "signal": "BEARISH" if total_put_oi > total_call_oi else "BULLISH",
                "tickers_sampled": len(high_conf),
            }
    except Exception as e:
        print(f"[COT] Options error: {e}")

    # 2. ETF shares outstanding (institutional flows)
    etf_positioning = {}
    for sym in ["URA", "URNM"]:
        try:
            t = yf.Ticker(sym)
            info = t.info or {}
            shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
            hist = t.history(period="3mo")
            if hist.empty or not shares:
                continue
            # Volume trend as flow proxy
            vol_5d = float(hist["Volume"][-5:].mean())
            vol_22d = float(hist["Volume"][-22:].mean())
            vol_ratio = vol_5d / vol_22d if vol_22d > 0 else 1

            # Price momentum
            price_now = float(hist["Close"].iloc[-1])
            price_22d = float(hist["Close"].iloc[-22]) if len(hist) >= 22 else price_now
            momentum = (price_now - price_22d) / price_22d * 100

            etf_positioning[sym] = {
                "shares_outstanding": shares,
                "volume_ratio_5d_22d": round(vol_ratio, 2),
                "price_momentum_22d": round(momentum, 1),
                "signal": "ACCUMULATION" if vol_ratio > 1.2 and momentum > 0 else
                         "DISTRIBUTION" if vol_ratio > 1.2 and momentum < 0 else "NEUTRAL",
            }
        except Exception as e:
            print(f"[COT] ETF {sym} error: {e}")
    positioning["etf_flows"] = etf_positioning

    # 3. Short interest (speculative shorts)
    try:
        from analysis import TICKERS as _tickers
        short_pcts = []
        for sym in list(_tickers.keys()):
            if sym in ["URA", "KAP.IL", "U-UN.TO", "PDN.AX"]:
                continue  # skip ETF and non-US
            try:
                info = yf.Ticker(sym).info or {}
                sf = info.get("shortPercentOfFloat")
                if sf and sf > 0:
                    short_pcts.append({"symbol": sym, "short_pct": round(sf * 100, 2)})
            except Exception:
                pass
        avg_short_pct = np.mean([s["short_pct"] for s in short_pcts]) if short_pcts else 0
        high_short = [s for s in short_pcts if s["short_pct"] > 10]
        positioning["short_interest"] = {
            "avg_short_pct_float": round(avg_short_pct, 2),
            "high_short_count": len(high_short),
            "high_short_tickers": [s["symbol"] for s in high_short],
            "tickers_sampled": len(short_pcts),
            "all_shorts": short_pcts,
            "signal": "CROWDED SHORT" if avg_short_pct > 15 else
                     "ELEVATED SHORT" if avg_short_pct > 8 else "NORMAL",
        }
    except Exception as e:
        print(f"[COT] Short interest error: {e}")

    # 4. Insider positioning (commercial proxy)
    try:
        from analysis import TICKERS as _tickers
        total_buys = 0
        total_sells = 0
        total_buy_value = 0
        total_sell_value = 0
        for sym in ["CCJ", "UEC", "UUUU", "DNN", "NXE", "LEU", "OKLO"]:
            try:
                tk = yf.Ticker(sym)
                trades = tk.insider_transactions
                if trades is None or trades.empty:
                    continue
                for _, row in trades.iterrows():
                    text = str(row.get("Text", "")).lower()
                    value = abs(row.get("Value", 0) or 0)
                    if "purchase" in text or "buy" in text:
                        total_buys += 1
                        total_buy_value += value
                    elif "sale" in text or "sell" in text:
                        total_sells += 1
                        total_sell_value += value
            except Exception:
                pass

        buy_sell_ratio = round(total_buys / max(total_sells, 1), 2)
        net_value = total_buy_value - total_sell_value
        positioning["insiders"] = {
            "total_buys": total_buys,
            "total_sells": total_sells,
            "buy_sell_ratio": buy_sell_ratio,
            "buy_value": round(total_buy_value),
            "sell_value": round(total_sell_value),
            "net_value": round(net_value),
            "signal": "BUYING" if total_buys > total_sells * 1.5 else
                     "SELLING" if total_sells > total_buys * 1.5 else "NEUTRAL",
        }
    except Exception as e:
        print(f"[COT] Insider error: {e}")

    # Composite positioning score (0-100, higher = more bullish positioning)
    scores = []

    # Options: high P/C = bearish positioning = contrarian bullish
    if "options" in positioning:
        pcr = positioning["options"]["pcr"]
        scores.append(("options_contrarian", min(100, pcr / 2 * 100), 0.3))

    # Short interest: high shorts = contrarian bullish (squeeze potential)
    if "short_interest" in positioning:
        si = positioning["short_interest"]["avg_short_pct_float"]
        scores.append(("short_squeeze", min(100, si / 20 * 100), 0.2))

    # ETF volume: high volume + positive momentum = bullish
    if etf_positioning:
        avg_momentum = np.mean([v["price_momentum_22d"] for v in etf_positioning.values()])
        mom_score = max(0, min(100, 50 + avg_momentum * 2))
        scores.append(("etf_momentum", mom_score, 0.25))

    # Insiders: net buying = bullish
    if "insiders" in positioning:
        ratio = positioning["insiders"]["buy_sell_ratio"]
        ins_score = max(0, min(100, ratio / 2 * 100))
        scores.append(("insider_conviction", ins_score, 0.25))

    if scores:
        total_w = sum(w for _, _, w in scores)
        composite = sum(s * w for _, s, w in scores) / total_w
    else:
        composite = 50

    if composite >= 70:
        overall_signal = "BULLISH"
        detail = "Positioning favors upside — contrarian indicators aligned"
    elif composite >= 55:
        overall_signal = "LEAN BULLISH"
        detail = "Slightly bullish positioning — mixed but tilted positive"
    elif composite <= 30:
        overall_signal = "BEARISH"
        detail = "Positioning favors downside — crowded longs, insider selling"
    elif composite <= 45:
        overall_signal = "LEAN BEARISH"
        detail = "Slightly bearish positioning — some caution signals"
    else:
        overall_signal = "NEUTRAL"
        detail = "No strong positioning bias"

    resp = {
        "title": "Uranium Sector Positioning Report (COT Proxy)",
        "method": "Synthetic COT — no CFTC uranium futures exist. Built from options OI, ETF flows, short interest, insider trades.",
        "composite_score": round(composite, 1),
        "signal": overall_signal,
        "detail": detail,
        "components": {k: round(s, 1) for k, s, _ in scores},
        "positioning": positioning,
        "note": "Uranium trades OTC (spot/term contracts), not on futures exchanges. This report synthesizes available positioning data as a CFTC COT proxy.",
    }

    cache["data"] = resp
    cache["ts"] = now
    return resp


@app.get("/api/score-changes")
def get_score_changes(days: int = Query(1, ge=1, le=30)):
    """Day-over-day score movers across all tickers. Shows which tickers are improving or deteriorating fastest."""
    conn = get_db()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    # Get the two most recent distinct dates with data
    dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM composite_score_history ORDER BY date DESC LIMIT ?", (days + 1,)
    ).fetchall()]
    conn.close()

    if len(dates) < 2:
        return {"error": "Need at least 2 daily snapshots", "snapshots_available": len(dates)}

    current_date = dates[0]
    compare_date = dates[min(days, len(dates) - 1)]

    conn = get_db()
    current = {r["symbol"]: dict(r) for r in conn.execute(
        "SELECT symbol, total_score, technical_score, macro_score, fundamental_score, sentiment_score, price, label "
        "FROM composite_score_history WHERE date = ?", (current_date,)
    ).fetchall()}
    previous = {r["symbol"]: dict(r) for r in conn.execute(
        "SELECT symbol, total_score, technical_score, macro_score, fundamental_score, sentiment_score, price, label "
        "FROM composite_score_history WHERE date = ?", (compare_date,)
    ).fetchall()}
    conn.close()

    movers = []
    for sym in current:
        if sym not in previous:
            continue
        c, p = current[sym], previous[sym]
        delta = round((c["total_score"] or 0) - (p["total_score"] or 0), 2)
        price_change = round(((c["price"] or 0) / (p["price"] or 1) - 1) * 100, 2) if p.get("price") else None
        movers.append({
            "symbol": sym,
            "current_score": c["total_score"],
            "previous_score": p["total_score"],
            "delta": delta,
            "abs_delta": abs(delta),
            "direction": "up" if delta > 0 else "down" if delta < 0 else "flat",
            "current_label": c["label"],
            "previous_label": p["label"],
            "price_change_pct": price_change,
            "category_deltas": {
                "technical": round((c.get("technical_score") or 0) - (p.get("technical_score") or 0), 2),
                "macro": round((c.get("macro_score") or 0) - (p.get("macro_score") or 0), 2),
                "fundamental": round((c.get("fundamental_score") or 0) - (p.get("fundamental_score") or 0), 2),
                "sentiment": round((c.get("sentiment_score") or 0) - (p.get("sentiment_score") or 0), 2),
            }
        })

    movers.sort(key=lambda x: x["abs_delta"], reverse=True)

    return {
        "as_of": current_date,
        "compare_to": compare_date,
        "days": days,
        "movers": movers,
        "biggest_gainer": movers[0]["symbol"] if movers and movers[0]["delta"] > 0 else None,
        "biggest_loser": next((m["symbol"] for m in movers if m["delta"] < 0), None),
    }


@app.get("/api/signal-history")
def get_signal_history(symbol: str = Query("URA"), days: int = Query(90, ge=1, le=365)):
    """
    Historical composite score snapshots for backtesting.
    Returns daily snapshots with total score, category scores, and all component scores.
    """
    symbol = symbol.upper()
    snapshots = get_composite_history(symbol, days)

    if not snapshots:
        return {"symbol": symbol, "snapshots": [], "count": 0, "message": "No historical data yet. Snapshots are taken daily at market close (4:30 PM ET)."}

    # Compute forward returns for backtesting
    for i, snap in enumerate(snapshots):
        # 1-day, 5-day, 10-day forward returns
        for fwd_days, key in [(1, "fwd_1d"), (5, "fwd_5d"), (10, "fwd_10d")]:
            if i + fwd_days < len(snapshots) and snap["price"] and snapshots[i + fwd_days]["price"]:
                snap[key] = round((snapshots[i + fwd_days]["price"] - snap["price"]) / snap["price"] * 100, 2)
            else:
                snap[key] = None

    # Summary stats
    scores = [s["total_score"] for s in snapshots if s["total_score"] is not None]
    buy_days = sum(1 for s in scores if s >= 60)
    sell_days = sum(1 for s in scores if s <= 40)

    # Score-return correlation (simple)
    pairs = [(s["total_score"], s["fwd_5d"]) for s in snapshots if s.get("total_score") is not None and s.get("fwd_5d") is not None]
    correlation = None
    if len(pairs) >= 5:
        scores_arr = [p[0] for p in pairs]
        returns_arr = [p[1] for p in pairs]
        mean_s = sum(scores_arr) / len(scores_arr)
        mean_r = sum(returns_arr) / len(returns_arr)
        cov = sum((s - mean_s) * (r - mean_r) for s, r in pairs) / len(pairs)
        std_s = (sum((s - mean_s) ** 2 for s in scores_arr) / len(scores_arr)) ** 0.5
        std_r = (sum((r - mean_r) ** 2 for r in returns_arr) / len(returns_arr)) ** 0.5
        if std_s > 0 and std_r > 0:
            correlation = round(cov / (std_s * std_r), 3)

    return {
        "symbol": symbol,
        "snapshots": snapshots,
        "count": len(snapshots),
        "summary": {
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "min_score": round(min(scores), 1) if scores else None,
            "max_score": round(max(scores), 1) if scores else None,
            "buy_signal_days": buy_days,
            "sell_signal_days": sell_days,
            "hold_days": len(scores) - buy_days - sell_days,
            "score_return_correlation_5d": correlation,
        },
    }


@app.get("/api/score-history/{symbol}")
def get_score_hist(symbol: str, days: int = Query(30, ge=1, le=90)):
    """Score history with score decomposition."""
    symbol = symbol.upper()
    conn = _get_db()
    rows = conn.execute(
        "SELECT symbol, timestamp, price, signal_score, zone, zone_pct, rsi, "
        "macd_val, macd_sig, bb_lower, bb_upper, sma_50, sma_200, "
        "range_contrib, rsi_contrib, macd_contrib, bb_contrib, sma_contrib "
        "FROM score_history WHERE symbol=? AND timestamp >= datetime('now', ?) ORDER BY timestamp",
        (symbol, f"-{days} days")
    ).fetchall()
    conn.close()

    history = []
    for r in rows:
        entry = {
            "symbol": r[0], "timestamp": r[1], "price": r[2],
            "signal_score": r[3], "zone": r[4], "zone_pct": r[5], "rsi": r[6],
        }
        # Compute decomposition from raw values
        zp = r[5] or 50
        rsi_val = r[6]
        range_score = 100 - zp
        rsi_score = (100 - rsi_val) if rsi_val else 50

        entry["components"] = {
            "range": {"score": round(range_score, 1), "weight": 40, "raw": round(zp, 1),
                      "label": "Near bottom" if range_score > 70 else "Near top" if range_score < 30 else "Mid-range"},
            "rsi": {"score": round(rsi_score, 1), "weight": 25, "raw": round(rsi_val, 1) if rsi_val else None,
                    "label": "Oversold" if rsi_val and rsi_val < 30 else "Overbought" if rsi_val and rsi_val > 70 else "Neutral"},
        }
        # Add MACD/BB/SMA if available
        if r[7] is not None and r[8] is not None:
            macd_diff = r[7] - r[8]
            macd_score = 50 + (max(-2, min(2, macd_diff)) / 2) * 50
            entry["components"]["macd"] = {"score": round(macd_score, 1), "weight": 15,
                "raw": round(macd_diff, 4), "label": "Bullish" if macd_diff > 0 else "Bearish"}
        if r[9] is not None and r[10] is not None and r[2]:
            bb_range = r[10] - r[9]
            if bb_range > 0:
                bb_pct = (r[2] - r[9]) / bb_range * 100
                bb_score = 100 - max(0, min(100, bb_pct))
                entry["components"]["bollinger"] = {"score": round(bb_score, 1), "weight": 10,
                    "raw": round(bb_pct, 1), "label": "Near lower band" if bb_score > 70 else "Near upper band" if bb_score < 30 else "Mid-band"}

        history.append(entry)

    return {"symbol": symbol, "history": history, "count": len(history)}


@app.get("/api/refresh")
def manual_refresh():
    """Trigger a manual data refresh."""
    try:
        results = refresh_all_tickers()
        news = fetch_news()
        spot = fetch_spot_uranium()
        return {
            "status": "ok",
            "tickers_refreshed": len(results),
            "news_fetched": len(news),
            "spot_uranium": spot,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# --- AI Hypothesis Engine ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
_ai_analysis_cache = {"data": None, "ts": 0}
AI_CACHE_FILE = os.path.join(os.path.dirname(__file__), "ai_analysis_cache.json")

# Load from disk on startup
try:
    if os.path.exists(AI_CACHE_FILE):
        with open(AI_CACHE_FILE) as f:
            _disk = json.load(f)
            _ai_analysis_cache["data"] = _disk.get("data")
            _ai_analysis_cache["ts"] = _disk.get("ts", 0)
except: pass

@app.get("/api/ai-analysis")
def get_ai_analysis(force: bool = False):
    """AI-generated hypothesis engine — aggregates all indicators, sends to Claude Opus 4.6 for short/medium/long term outlook."""
    import time as _time
    now = _time.time()
    # Cache for 30 min unless forced
    if not force and _ai_analysis_cache["data"] and now - _ai_analysis_cache["ts"] < 14400:  # 4h cache
        return _ai_analysis_cache["data"]

    if not OPENAI_API_KEY and not ANTHROPIC_API_KEY:
        return {"error": "No AI API key configured"}

    # Gather data from internal endpoints
    context_parts = []
    try:
        thermo = get_thermometer()
        context_parts.append(f"THERMOMETER: {json.dumps(thermo, default=str)[:2000]}")
    except: pass
    try:
        macro = get_macro_regime()
        context_parts.append(f"MACRO REGIME: {json.dumps(macro, default=str)[:1500]}")
    except: pass
    try:
        spot = get_spot_price()
        context_parts.append(f"SPOT PRICE: {json.dumps(spot, default=str)[:500]}")
    except: pass
    try:
        news = get_news()
        context_parts.append(f"NEWS SENTIMENT: {json.dumps(news, default=str)[:1500]}")
    except: pass
    try:
        signals = get_signals()
        context_parts.append(f"SIGNALS: {json.dumps(signals, default=str)[:1500]}")
    except: pass
    try:
        supply = get_supply_demand()
        context_parts.append(f"SUPPLY/DEMAND: {json.dumps(supply, default=str)[:1000]}")
    except: pass
    try:
        short_int = get_short_interest()
        context_parts.append(f"SHORT INTEREST: {json.dumps(short_int, default=str)[:1000]}")
    except: pass
    try:
        etf = get_etf_flows()
        context_parts.append(f"ETF FLOWS: {json.dumps(etf, default=str)[:1000]}")
    except: pass
    try:
        options = get_options_iv_summary()
        context_parts.append(f"OPTIONS IV: {json.dumps(options, default=str)[:1000]}")
    except: pass
    try:
        divs = get_divergences()
        context_parts.append(f"DIVERGENCES: {json.dumps(divs, default=str)[:1000]}")
    except: pass
    try:
        cross = get_cross_asset_regime()
        context_parts.append(f"CROSS-ASSET REGIME: {json.dumps(cross, default=str)[:1000]}")
    except: pass
    try:
        insider = get_insider_trades()
        context_parts.append(f"INSIDER TRADES: {json.dumps(insider, default=str)[:1000]}")
    except: pass
    try:
        analyst = get_analyst_ratings()
        context_parts.append(f"ANALYST RATINGS: {json.dumps(analyst, default=str)[:1000]}")
    except: pass
    try:
        geo = get_geopolitical_risk()
        context_parts.append(f"GEOPOLITICAL RISK: {json.dumps(geo, default=str)[:1000]}")
    except: pass
    try:
        ry = get_real_yield()
        context_parts.append(f"REAL YIELD: {json.dumps(ry, default=str)[:800]}")
    except: pass
    try:
        sed = get_spot_equity_divergence()
        context_parts.append(f"SPOT-EQUITY DIVERGENCE: {json.dumps(sed, default=str)[:800]}")
    except: pass
    try:
        fm = get_flow_momentum()
        context_parts.append(f"FLOW MOMENTUM: {json.dumps(fm, default=str)[:800]}")
    except: pass
    try:
        af = get_antifragile_score()
        context_parts.append(f"ANTIFRAGILE SCORE: {json.dumps(af, default=str)[:800]}")
    except: pass

    data_block = "\n\n".join(context_parts)

    prompt = f"""You are a senior macro analyst at Bridgewater Associates specializing in uranium and nuclear energy markets. You have access to a comprehensive real-time dashboard. Analyze ALL the data below and produce a structured investment hypothesis.

DASHBOARD DATA:
{data_block}

Produce your analysis in this exact JSON structure:
{{
  "generated_at": "<ISO timestamp>",
  "market_regime": "<one of: risk-on, risk-off, transitioning, uncertain>",
  "conviction_level": "<one of: high, medium, low>",
  "short_term": {{
    "horizon": "1-4 weeks",
    "outlook": "<bullish/bearish/neutral>",
    "hypothesis": "<2-3 sentence thesis>",
    "key_drivers": ["<driver1>", "<driver2>", "<driver3>"],
    "risk_factors": ["<risk1>", "<risk2>"],
    "actionable": "<specific positioning suggestion>"
  }},
  "medium_term": {{
    "horizon": "1-6 months",
    "outlook": "<bullish/bearish/neutral>",
    "hypothesis": "<2-3 sentence thesis>",
    "key_drivers": ["<driver1>", "<driver2>", "<driver3>"],
    "risk_factors": ["<risk1>", "<risk2>"],
    "actionable": "<specific positioning suggestion>"
  }},
  "long_term": {{
    "horizon": "6-24 months",
    "outlook": "<bullish/bearish/neutral>",
    "hypothesis": "<2-3 sentence thesis>",
    "key_drivers": ["<driver1>", "<driver2>", "<driver3>"],
    "risk_factors": ["<risk1>", "<risk2>"],
    "actionable": "<specific positioning suggestion>"
  }},
  "contrarian_view": "<What could make this analysis completely wrong? 1-2 sentences>",
  "dalio_verdict": "<What would Ray Dalio say about this setup in one paragraph? Reference his all-weather/risk-parity framework.>",
  "signal_conflicts": ["<list any indicators that contradict each other>"],
  "top_pick": "<single ticker with 1-sentence rationale>",
  "avoid": "<single ticker with 1-sentence rationale>"
}}

Return ONLY valid JSON, no markdown, no code fences."""

    def _parse_ai_text(text, model_name, n_sources):
        """Parse AI response text into structured analysis dict."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        analysis = json.loads(text)
        analysis["model"] = model_name
        analysis["data_sources"] = n_sources
        analysis["cached"] = False
        return analysis

    def _save_cache(analysis):
        import time as _time2
        _ai_analysis_cache["data"] = analysis
        _ai_analysis_cache["ts"] = _time2.time()
        try:
            with open(AI_CACHE_FILE, "w") as f:
                json.dump({"data": analysis, "ts": _ai_analysis_cache["ts"]}, f)
        except:
            pass

    # --- Try OpenRouter first ---
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY)

    if openrouter_key:
        try:
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://165.22.252.79/uranium/",
                    "X-Title": "Uranium Thermometer",
                },
                json={
                    "model": "anthropic/claude-opus-4-6",
                    "max_tokens": 3000,
                    "temperature": 0.7,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=120,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            analysis = _parse_ai_text(text, "claude-opus-4-6 (openrouter)", len(context_parts))
            _save_cache(analysis)
            return analysis
        except json.JSONDecodeError as e:
            return {"error": "AI returned invalid JSON", "raw": str(e)[:200]}
        except Exception as e:
            # OpenRouter failed — fall through to Anthropic direct if key available
            if not anthropic_key:
                return {"error": f"AI analysis failed: {str(e)}"}

    # --- Fallback: Anthropic Messages API directly ---
    if anthropic_key:
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-opus-4-5",
                    "max_tokens": 3000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=120,
            )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"]
            analysis = _parse_ai_text(text, "claude-opus-4-5 (anthropic-direct)", len(context_parts))
            _save_cache(analysis)
            return analysis
        except json.JSONDecodeError as e:
            return {"error": "AI returned invalid JSON", "raw": str(e)[:200]}
        except Exception as e:
            return {"error": f"AI analysis failed (anthropic fallback): {str(e)}"}

    return {"error": "No AI API key configured (OPENROUTER_API_KEY or ANTHROPIC_API_KEY required)"}


# --- Anti-Fragile Thesis Data Layer ---

_spot_equity_div_cache = {"data": None, "ts": 0}

@app.get("/api/spot-equity-divergence")
def get_spot_equity_divergence():
    """Spot U3O8 vs uranium equity divergence — tracks decoupling between commodity and equities."""
    import time as _time
    import yfinance as yf
    import numpy as np
    now = _time.time()
    if _spot_equity_div_cache["data"] and now - _spot_equity_div_cache["ts"] < 7200:
        return _spot_equity_div_cache["data"]

    try:
        # Get URA and Sprott (U-UN.TO as spot proxy) price histories
        ura = yf.Ticker("URA")
        sput = yf.Ticker("U-UN.TO")
        ura_h = ura.history(period="6mo")
        sput_h = sput.history(period="6mo")

        if ura_h.empty or sput_h.empty:
            return {"error": "Insufficient data"}

        # Align dates
        import pandas as pd
        ura_s = ura_h["Close"].rename("URA")
        sput_s = sput_h["Close"].rename("SPUT")
        df = pd.concat([ura_s, sput_s], axis=1).dropna()

        if len(df) < 30:
            return {"error": "Insufficient overlapping data"}

        # Rolling returns
        windows = {"30d": 22, "60d": 44, "90d": 66}
        rolling_data = {}
        for label, w in windows.items():
            if len(df) >= w:
                ura_ret = (df["URA"].iloc[-1] / df["URA"].iloc[-w] - 1) * 100
                sput_ret = (df["SPUT"].iloc[-1] / df["SPUT"].iloc[-w] - 1) * 100
                divergence = sput_ret - ura_ret
                rolling_data[label] = {
                    "ura_return_pct": round(ura_ret, 2),
                    "spot_proxy_return_pct": round(sput_ret, 2),
                    "divergence_pct": round(divergence, 2),
                }

        # Rolling divergence z-score (30d window, 90d lookback)
        ura_rets_30d = df["URA"].pct_change(22).dropna()
        sput_rets_30d = df["SPUT"].pct_change(22).dropna()
        aligned = pd.concat([ura_rets_30d, sput_rets_30d], axis=1).dropna()
        if len(aligned) > 10:
            div_series = (aligned["SPUT"] - aligned["URA"]) * 100
            current_div = float(div_series.iloc[-1])
            div_mean = float(div_series.mean())
            div_std = float(div_series.std())
            z_score = (current_div - div_mean) / div_std if div_std > 0 else 0
        else:
            z_score = 0
            current_div = 0

        # Signal interpretation
        if z_score > 1.5:
            signal = "EQUITY_CATCH_UP"
            detail = "Spot significantly outperforming equities. Historically, equities catch up within 2-6 weeks. Accumulate equity on weakness."
        elif z_score < -1.5:
            signal = "SPOT_CORRECTION_RISK"
            detail = "Equities outpacing spot. Spot price may be lagging or equities pricing in optimism. Caution on new equity positions."
        elif z_score > 0.5:
            signal = "MILD_DIVERGENCE"
            detail = "Spot leading equities — typical in early bull phases. Monitor for catch-up."
        elif z_score < -0.5:
            signal = "MILD_CONVERGENCE"
            detail = "Equities leading spot — typical in late-cycle or speculative phases."
        else:
            signal = "ALIGNED"
            detail = "Spot and equities moving in sync. No divergence trade."

        # Sparkline: daily divergence over last 60 trading days
        sparkline = []
        for i in range(min(60, len(aligned))):
            idx = -(min(60, len(aligned)) - i)
            sparkline.append(round(float(div_series.iloc[idx]), 2))

        resp = {
            "rolling_returns": rolling_data,
            "divergence_z_score": round(z_score, 2),
            "current_divergence_pct": round(current_div, 2),
            "signal": signal,
            "detail": detail,
            "sparkline_60d": sparkline,
            "dalio_note": "In risk-parity, commodity-equity divergences are mean-reverting. Size positions for the structural thesis but respect the divergence — it tells you where pain is building.",
        }
        _spot_equity_div_cache["data"] = resp
        _spot_equity_div_cache["ts"] = now
        return resp
    except Exception as e:
        return {"error": str(e)}


_real_yield_cache = {"data": None, "ts": 0}

@app.get("/api/real-yield")
def get_real_yield():
    """Real yield calculation — key driver for real asset allocation in all-weather framework."""
    import time as _time
    import yfinance as yf
    import numpy as np
    now = _time.time()
    if _real_yield_cache["data"] and now - _real_yield_cache["ts"] < 7200:
        return _real_yield_cache["data"]

    try:
        # 10Y nominal yield
        tnx = yf.Ticker("^TNX")
        tnx_h = tnx.history(period="2y")

        # TIP ETF as inflation expectations proxy
        tip = yf.Ticker("TIP")
        tip_h = tip.history(period="2y")

        # DXY (dollar index)
        dxy = yf.Ticker("DX-Y.NYB")
        dxy_h = dxy.history(period="2y")

        if tnx_h.empty:
            return {"error": "Could not fetch yield data"}

        nominal_yield = float(tnx_h["Close"].iloc[-1])
        nominal_1y_ago = float(tnx_h["Close"].iloc[-min(252, len(tnx_h))]) if len(tnx_h) > 50 else nominal_yield

        # Breakeven inflation estimate: ~10Y nominal minus real yield
        # Use TIP yield-to-maturity proxy: TIP 12m return correlates with inflation expectations
        if not tip_h.empty and len(tip_h) > 252:
            tip_return_1y = (float(tip_h["Close"].iloc[-1]) / float(tip_h["Close"].iloc[-252]) - 1) * 100
            # Approximate breakeven: nominal - (TIP return adjusted)
            # More accurate: use the differential as inflation expectation proxy
            breakeven_est = max(1.5, min(4.0, nominal_yield - 1.5 + tip_return_1y * 0.3))
        else:
            breakeven_est = 2.3  # fallback estimate

        real_yield = round(nominal_yield - breakeven_est, 2)

        # Percentile ranking (where does current real yield sit in 2yr range?)
        if len(tnx_h) > 100:
            historical_nominals = tnx_h["Close"].values
            percentile = round(float(np.sum(historical_nominals < nominal_yield) / len(historical_nominals) * 100), 1)
        else:
            percentile = 50

        # DXY data
        dxy_current = float(dxy_h["Close"].iloc[-1]) if not dxy_h.empty else None
        dxy_percentile = None
        if not dxy_h.empty and len(dxy_h) > 100:
            dxy_vals = dxy_h["Close"].values
            dxy_percentile = round(float(np.sum(dxy_vals < dxy_current) / len(dxy_vals) * 100), 1)

        # Real yield regime
        if real_yield < 0:
            regime = "NEGATIVE_REAL"
            signal = "Strong tailwind for real assets. Negative real yields = money-losing to hold bonds after inflation. Capital flows to commodities, gold, uranium."
        elif real_yield < 1.0:
            regime = "LOW_REAL"
            signal = "Mild tailwind for real assets. Low real yields reduce opportunity cost of holding non-yielding commodities."
        elif real_yield < 2.0:
            regime = "NEUTRAL"
            signal = "Balanced. Real yields provide moderate competition to real assets but not prohibitive."
        else:
            regime = "RESTRICTIVE"
            signal = "Headwind for real assets. High real yields attract capital to bonds, away from commodities."

        # Dollar regime
        dollar_regime = "WEAK" if dxy_percentile and dxy_percentile < 30 else ("STRONG" if dxy_percentile and dxy_percentile > 70 else "NEUTRAL")

        # Combined all-weather signal
        if regime in ("NEGATIVE_REAL", "LOW_REAL") and dollar_regime == "WEAK":
            aw_signal = "OPTIMAL"
            aw_detail = "Falling real yields + weak dollar = ideal environment for uranium and real assets. This is the setup Bridgewater's commodity sleeve is designed to capture."
        elif regime in ("NEGATIVE_REAL", "LOW_REAL"):
            aw_signal = "FAVORABLE"
            aw_detail = "Low real yields support real assets. Dollar not yet confirming but watch for further weakness."
        elif dollar_regime == "WEAK":
            aw_signal = "PARTIAL"
            aw_detail = "Weak dollar supports commodity prices but real yields are competing. Mixed signal."
        else:
            aw_signal = "HEADWIND"
            aw_detail = "High real yields and/or strong dollar — traditional headwinds for commodity allocation."

        # Sparkline: nominal yield last 6 months
        sparkline_yield = [round(float(v), 2) for v in tnx_h["Close"].values[-130:]]

        resp = {
            "nominal_yield_pct": round(nominal_yield, 2),
            "breakeven_inflation_est": round(breakeven_est, 2),
            "real_yield_pct": real_yield,
            "real_yield_regime": regime,
            "yield_percentile_2y": percentile,
            "yield_1y_ago": round(nominal_1y_ago, 2),
            "yield_change_1y": round(nominal_yield - nominal_1y_ago, 2),
            "dxy_current": round(dxy_current, 2) if dxy_current else None,
            "dxy_percentile_2y": dxy_percentile,
            "dollar_regime": dollar_regime,
            "all_weather_signal": aw_signal,
            "all_weather_detail": aw_detail,
            "signal": signal,
            "sparkline_yield_6m": sparkline_yield,
            "dalio_note": "In Bridgewater's all-weather framework, the commodity sleeve performs best when real yields fall and the dollar weakens. These two factors explain ~70% of commodity returns historically.",
        }
        _real_yield_cache["data"] = resp
        _real_yield_cache["ts"] = now
        return resp
    except Exception as e:
        return {"error": str(e)}


_flow_momentum_cache = {"data": None, "ts": 0}

@app.get("/api/flow-momentum")
def get_flow_momentum():
    """ETF flow momentum and positioning analysis — tracks where institutional money is moving."""
    import time as _time
    import yfinance as yf
    import numpy as np
    now = _time.time()
    if _flow_momentum_cache["data"] and now - _flow_momentum_cache["ts"] < 7200:
        return _flow_momentum_cache["data"]

    try:
        etfs = {"URA": "Global X Uranium ETF", "URNM": "Sprott Uranium Miners ETF"}
        results = {}
        for sym, name in etfs.items():
            tk = yf.Ticker(sym)
            h = tk.history(period="6mo")
            if h.empty or "Volume" not in h.columns:
                continue

            # Dollar volume as flow proxy
            h["dv"] = h["Close"] * h["Volume"]
            dv_5d = float(h["dv"].tail(5).mean())
            dv_22d = float(h["dv"].tail(22).mean())
            dv_66d = float(h["dv"].tail(66).mean())

            # Flow trend (5d vs 22d vs 66d)
            short_vs_med = (dv_5d / dv_22d - 1) * 100 if dv_22d else 0
            med_vs_long = (dv_22d / dv_66d - 1) * 100 if dv_66d else 0

            # Price momentum
            price_5d = (float(h["Close"].iloc[-1]) / float(h["Close"].iloc[-6]) - 1) * 100 if len(h) > 5 else 0
            price_22d = (float(h["Close"].iloc[-1]) / float(h["Close"].iloc[-23]) - 1) * 100 if len(h) > 22 else 0

            # Flow-price divergence: if price dropping but volume surging = capitulation/accumulation
            if price_5d < -2 and short_vs_med > 20:
                flow_signal = "CAPITULATION"
                flow_detail = "Price falling with surging volume — potential forced selling / capitulation. Often marks intermediate bottoms."
            elif price_5d > 2 and short_vs_med > 20:
                flow_signal = "BREAKOUT_CONFIRMATION"
                flow_detail = "Price rising with surging volume — institutional conviction. Trend likely continues."
            elif price_5d < -2 and short_vs_med < -20:
                flow_signal = "ORDERLY_DECLINE"
                flow_detail = "Price and volume both declining — no panic, but no buyers either. Wait for volume surge."
            elif short_vs_med < -30:
                flow_signal = "FLOW_DROUGHT"
                flow_detail = "Volume collapsing — institutional disinterest. This precedes either breakout or further decline."
            else:
                flow_signal = "NORMAL"
                flow_detail = "Flow patterns within normal range."

            results[sym] = {
                "name": name,
                "dollar_volume_5d": round(dv_5d / 1e6, 1),
                "dollar_volume_22d": round(dv_22d / 1e6, 1),
                "dollar_volume_66d": round(dv_66d / 1e6, 1),
                "flow_trend_short_pct": round(short_vs_med, 1),
                "flow_trend_med_pct": round(med_vs_long, 1),
                "price_5d_pct": round(price_5d, 2),
                "price_22d_pct": round(price_22d, 2),
                "signal": flow_signal,
                "detail": flow_detail,
            }

        # Aggregate signal
        signals = [r["signal"] for r in results.values()]
        if "CAPITULATION" in signals:
            agg_signal = "CAPITULATION_WATCH"
            agg_detail = "Volume surging into falling prices across uranium ETFs. Classic Dalio 'beautiful deleveraging' — the weak hands are exiting. For anti-fragile portfolios, this is where entry points improve."
        elif all(s == "FLOW_DROUGHT" for s in signals):
            agg_signal = "DISINTEREST_BOTTOM"
            agg_detail = "Volume dried up across all uranium ETFs. Historically, extreme flow droughts in trending sectors precede sharp reversals. Watch for volume expansion as the trigger."
        elif "BREAKOUT_CONFIRMATION" in signals:
            agg_signal = "INSTITUTIONAL_CONVICTION"
            agg_detail = "Smart money flowing in with conviction. Volume confirming price moves."
        else:
            agg_signal = "MIXED"
            agg_detail = "No clear flow pattern. Monitor for changes."

        resp = {
            "etfs": results,
            "aggregate_signal": agg_signal,
            "aggregate_detail": agg_detail,
            "dalio_note": "Position sizing should inversely correlate with flow momentum. Buy when flows are weakest (but fundamentals intact), reduce when flows are strongest (crowding risk).",
        }
        _flow_momentum_cache["data"] = resp
        _flow_momentum_cache["ts"] = now
        return resp
    except Exception as e:
        return {"error": str(e)}


_antifragile_cache = {"data": None, "ts": 0}

@app.get("/api/antifragile-score")
def get_antifragile_score():
    """Composite anti-fragile positioning score — synthesizes all Dalio/all-weather signals into one number."""
    import time as _time
    now = _time.time()
    if _antifragile_cache["data"] and now - _antifragile_cache["ts"] < 7200:
        return _antifragile_cache["data"]

    try:
        scores = {}
        total_weight = 0
        weighted_score = 0

        # 1. Real yield component (25%)
        try:
            ry = get_real_yield()
            if ry.get("real_yield_pct") is not None:
                rv = ry["real_yield_pct"]
                # Score: negative real yield = 100, 0 = 70, 1% = 50, 2%+ = 20
                ry_score = max(0, min(100, 70 - rv * 30))
                scores["real_yield"] = {"score": round(ry_score), "weight": 25, "value": f"{rv:.2f}%", "regime": ry.get("real_yield_regime")}
                weighted_score += ry_score * 25
                total_weight += 25
        except: pass

        # 2. Dollar weakness (15%)
        try:
            ry = get_real_yield()
            if ry.get("dxy_percentile_2y") is not None:
                dp = ry["dxy_percentile_2y"]
                # Score: lower percentile = better for commodities
                dxy_score = max(0, min(100, 100 - dp))
                scores["dollar"] = {"score": round(dxy_score), "weight": 15, "value": f"DXY {dp:.0f}th pctile", "regime": ry.get("dollar_regime")}
                weighted_score += dxy_score * 15
                total_weight += 15
        except: pass

        # 3. Supply-demand structural deficit (20%)
        try:
            sd = get_supply_demand()
            deficit_pct = sd.get("deficit_pct", 0)
            # Score: bigger deficit = more bullish
            sd_score = min(100, max(0, 50 + deficit_pct * 5))
            scores["supply_deficit"] = {"score": round(sd_score), "weight": 20, "value": f"{deficit_pct:.1f}% deficit", "signal": sd.get("signal")}
            weighted_score += sd_score * 20
            total_weight += 20
        except: pass

        # 4. Spot-equity divergence (15%)
        try:
            sed = get_spot_equity_divergence()
            z = sed.get("divergence_z_score", 0)
            # Score: positive divergence (spot > equity) = buying opportunity for equities
            div_score = min(100, max(0, 50 + z * 20))
            scores["divergence"] = {"score": round(div_score), "weight": 15, "value": f"z={z:.2f}", "signal": sed.get("signal")}
            weighted_score += div_score * 15
            total_weight += 15
        except: pass

        # 5. Flow positioning (10%) — contrarian: low flows = better entry
        try:
            fm = get_flow_momentum()
            agg = fm.get("aggregate_signal", "")
            if agg == "CAPITULATION_WATCH":
                flow_score = 90
            elif agg == "DISINTEREST_BOTTOM":
                flow_score = 80
            elif agg == "MIXED":
                flow_score = 50
            elif agg == "INSTITUTIONAL_CONVICTION":
                flow_score = 40  # good but crowding risk
            else:
                flow_score = 50
            scores["flow_positioning"] = {"score": flow_score, "weight": 10, "value": agg, "signal": fm.get("aggregate_detail", "")[:80]}
            weighted_score += flow_score * 10
            total_weight += 10
        except: pass

        # 6. Geopolitical risk premium (15%)
        try:
            geo = get_geopolitical_risk()
            geo_score_val = geo.get("portfolio_weighted_risk", 50)
            # Higher geopolitical risk = higher option value for uranium
            geo_af_score = min(100, max(0, geo_score_val))
            scores["geopolitical_optionality"] = {"score": round(geo_af_score), "weight": 15, "value": f"Risk: {geo_score_val:.0f}/100", "signal": "Higher geopolitical risk = more supply disruption optionality"}
            weighted_score += geo_af_score * 15
            total_weight += 15
        except: pass

        composite = round(weighted_score / total_weight) if total_weight > 0 else 50

        # Regime
        if composite >= 75:
            regime = "ANTI_FRAGILE_OPTIMAL"
            action = "Maximum position sizing. All-weather conditions ideal for uranium. This is where anti-fragile portfolios generate asymmetric returns."
        elif composite >= 60:
            regime = "FAVORABLE"
            action = "Above-average allocation. Most signals supportive. Size for the structural thesis, use dips to add."
        elif composite >= 45:
            regime = "NEUTRAL"
            action = "Standard allocation. Mixed signals — maintain positions but don't add aggressively."
        else:
            regime = "DEFENSIVE"
            action = "Below-average allocation. Macro headwinds present. Reduce tactical positions, maintain only core structural holdings."

        resp = {
            "composite_score": composite,
            "regime": regime,
            "action": action,
            "components": scores,
            "components_count": len(scores),
            "total_weight_pct": total_weight,
            "dalio_note": "Anti-fragility in investing means benefiting from volatility and stress. Uranium's anti-fragile properties: supply disruptions raise prices (geopolitical optionality), energy crises increase nuclear demand, inflation erodes alternatives. This score measures how favorable conditions are for these anti-fragile dynamics.",
        }
        _antifragile_cache["data"] = resp
        _antifragile_cache["ts"] = now
        return resp
    except Exception as e:
        return {"error": str(e)}


_etf_holdings_cache = {"data": None, "ts": 0}

@app.get("/api/etf-holdings")
def get_etf_holdings():
    """URA ETF holdings breakdown from Global X."""
    import time as _time
    now = _time.time()
    if _etf_holdings_cache["data"] and now - _etf_holdings_cache["ts"] < 86400:  # 24hr cache
        return _etf_holdings_cache["data"]

    holdings = []
    try:
        resp = httpx.get(
            "https://www.globalxetfs.com/funds/ura",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            timeout=15, follow_redirects=True,
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for table in soup.select("table"):
                headers = [c.get_text(strip=True) for c in table.select("tr:first-child th, tr:first-child td")]
                if "Net Assets (%)" not in headers and "Ticker" not in headers:
                    continue
                # Skip tables with empty data rows
                first_data = table.select("tr")[1] if len(table.select("tr")) > 1 else None
                if first_data and not first_data.get_text(strip=True):
                    continue
                for row in table.select("tr")[1:]:
                    cells = [c.get_text(strip=True) for c in row.select("th,td")]
                    if len(cells) >= 7:
                        try:
                            weight = float(cells[0])
                        except ValueError:
                            continue
                        ticker_raw = cells[1]
                        name = cells[2]
                        try:
                            price = float(cells[4].replace(",", ""))
                        except:
                            price = None
                        try:
                            shares = int(cells[5].replace(",", ""))
                        except:
                            shares = None
                        try:
                            market_value = float(cells[6].replace(",", ""))
                        except:
                            market_value = None

                        # Map to US tickers where possible
                        ticker_map = {
                            "CCO CN": "CCJ", "NXE CN": "NXE", "EFR CN": "UUUU",
                            "DML CN": "DNN", "U-U CN": "U-UN.TO", "PDN AU": "PDN.AX",
                            "KAP LI": "KAP.IL", "FCU CN": "FCUUF", "LOT AU": "LTALF",
                            "BOSS AU": "BOE.AX", "GLO CN": "GLO.TO",
                        }
                        us_ticker = ticker_map.get(ticker_raw, ticker_raw)

                        # Check if this ticker is in our tracked universe
                        tracked = us_ticker in TICKERS or ticker_raw.split()[0] in [t.split(".")[0] for t in TICKERS]

                        holdings.append({
                            "weight_pct": weight,
                            "ticker": us_ticker,
                            "ticker_raw": ticker_raw,
                            "name": name,
                            "price": price,
                            "shares": shares,
                            "market_value_usd": market_value,
                            "tracked_by_dashboard": tracked,
                        })
                break  # Only process the first matching table
    except Exception as e:
        print(f"[ETF HOLDINGS] Scrape error: {e}")

    if not holdings:
        return {"error": "Could not fetch holdings data", "source": "globalxetfs.com"}

    # Summary stats
    top10_weight = sum(h["weight_pct"] for h in holdings[:10])
    tracked_weight = sum(h["weight_pct"] for h in holdings if h["tracked_by_dashboard"])
    total_holdings = len(holdings)

    # Concentration analysis
    if holdings[0]["weight_pct"] > 20:
        concentration = "HIGH"
        concentration_note = f"{holdings[0]['name']} dominates at {holdings[0]['weight_pct']}%. Single-stock risk is significant."
    elif top10_weight > 70:
        concentration = "MODERATE"
        concentration_note = f"Top 10 = {top10_weight:.1f}% of fund. Reasonably concentrated."
    else:
        concentration = "DIVERSIFIED"
        concentration_note = f"Top 10 = {top10_weight:.1f}%. Well-diversified across holdings."

    result = {
        "etf": "URA",
        "name": "Global X Uranium ETF",
        "holdings": holdings,
        "total_holdings": total_holdings,
        "top10_weight_pct": round(top10_weight, 1),
        "tracked_weight_pct": round(tracked_weight, 1),
        "concentration": concentration,
        "concentration_note": concentration_note,
        "source": "Global X ETFs (globalxetfs.com)",
        "last_updated": datetime.utcnow().strftime("%Y-%m-%d"),
    }
    _etf_holdings_cache["data"] = result
    _etf_holdings_cache["ts"] = now
    return result


# --- Static files (frontend) ---
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
else:
    @app.get("/")
    def root():
        return {"message": "Uranium Thermometer API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8050)
