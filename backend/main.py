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

from database import init_db, get_all_ticker_meta, get_ticker_meta, get_news, get_prices, get_spot_uranium, get_score_history, DB_PATH
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


@app.get("/api/portfolio/journal")
def get_trade_journal(limit: int = Query(50, ge=1, le=200)):
    """Full trade history."""
    conn = _get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS trade_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime('now')), action TEXT, symbol TEXT, shares REAL, price REAL, total REAL, reasoning TEXT, score_at_trade REAL, zone_at_trade TEXT, macro_at_trade TEXT)")
    rows = conn.execute("SELECT * FROM trade_journal ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"trades": [dict(r) for r in rows], "count": len(rows)}


_iv_cache = {}
OPTIONS_TICKERS = ["CCJ", "UEC", "UUUU", "DNN", "NXE"]

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


_custom_alerts = []  # [{id, type, symbol, operator, value, channel, enabled, last_fired, was_triggered}]
_custom_alert_counter = 0

@app.get("/api/alerts/custom")
def list_custom_alerts():
    return {"alerts": _custom_alerts}

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
        results.append({
            "symbol": symbol,
            "name": TICKERS.get(symbol, symbol),
            "current_volume": current_vol,
            "avg_volume_20d": round(avg_vol),
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

    try:
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
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
        result = resp.json()
        text = result["choices"][0]["message"]["content"].strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        analysis = json.loads(text)
        analysis["model"] = "claude-opus-4-6"
        analysis["data_sources"] = len(context_parts)
        analysis["cached"] = False

        _ai_analysis_cache["data"] = analysis
        _ai_analysis_cache["ts"] = now
        try:
            with open(AI_CACHE_FILE, "w") as f:
                json.dump({"data": analysis, "ts": now}, f)
        except: pass
        return analysis
    except json.JSONDecodeError:
        return {"error": "AI returned invalid JSON", "raw": text[:500]}
    except Exception as e:
        return {"error": f"AI analysis failed: {str(e)}"}


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
