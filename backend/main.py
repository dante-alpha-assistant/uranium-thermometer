"""Uranium Thermometer - FastAPI Backend."""
import os
import json
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, get_all_ticker_meta, get_ticker_meta, get_news, get_prices, get_spot_uranium, get_score_history
from data_fetcher import refresh_all_tickers, fetch_news, fetch_spot_uranium
from analysis import TICKERS


scheduler = BackgroundScheduler()


def scheduled_refresh():
    """Refresh data - runs every 15 min during market hours."""
    now = datetime.utcnow()
    # Market hours: Mon-Fri, 13:30-20:00 UTC (9:30-4:00 ET)
    if now.weekday() < 5 and 13 <= now.hour <= 20:
        print(f"[{now.isoformat()}] Scheduled refresh (market hours)")
        refresh_all_tickers()
        fetch_news()
        fetch_spot_uranium()
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
    
    return {
        "ura": ura,
        "tickers": tickers,
        "spot_uranium": spot,
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
