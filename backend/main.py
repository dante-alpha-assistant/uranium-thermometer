"""Uranium Thermometer - FastAPI Backend."""
import os
import json
import sqlite3
import httpx
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, get_all_ticker_meta, get_ticker_meta, get_news, get_prices, get_spot_uranium, get_score_history, DB_PATH
from data_fetcher import refresh_all_tickers, fetch_news, fetch_spot_uranium, fetch_macro_regime
from analysis import TICKERS

DISCORD_CHANNEL_ID = "1471822299203371030"  # #general
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

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
    elif now.minute == 0:  # Off-hours: refresh news once per hour
        print(f"[{now.isoformat()}] Scheduled refresh (off-hours, news only)")
        fetch_news()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Initial data load
    print("Initial data fetch...")
    try:
        refresh_all_tickers()
        fetch_news()
        fetch_spot_uranium()
    except Exception as e:
        print(f"Initial fetch error (will retry): {e}")
    
    scheduler.add_job(scheduled_refresh, "interval", minutes=15)
    scheduler.start()
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
            detail += f" {macro_text} Sentiment confirms ({bullish_news} bullish articles) — conviction is high."
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


@app.get("/api/score-history/{symbol}")
def get_score_hist(symbol: str, days: int = Query(30, ge=1, le=90)):
    """Score history for a ticker over time."""
    symbol = symbol.upper()
    history = get_score_history(symbol, days=days)
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
