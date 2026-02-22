"""Fetch price data via yfinance and news via RSS."""
import yfinance as yf
import pandas as pd
import httpx
import feedparser
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from analysis import TICKERS, analyze_ticker
from database import (
    save_prices, get_prices, save_ticker_meta, save_news, save_spot_uranium, save_score_snapshot
)

URANIUM_RSS_FEEDS = [
    ("https://news.google.com/rss/search?q=uranium+nuclear+energy&hl=en-US&gl=US&ceid=US:en", "Google News"),
    ("https://news.google.com/rss/search?q=uranium+ETF+mining&hl=en-US&gl=US&ceid=US:en", "Google News"),
    ("https://www.world-nuclear-news.org/feed", "World Nuclear News"),
]

SENTIMENT_BULLISH = [
    "approve", "approval", "restart", "extend", "new build", "contract", "award",
    "bullish", "surge", "rally", "demand", "shortage", "deficit", "upside",
    "record", "milestone", "breakout", "AI", "data center", "power purchase",
    "SMR", "small modular", "positive", "upgrade", "buy",
]
SENTIMENT_BEARISH = [
    "shut down", "shutdown", "cancel", "delay", "bearish", "decline", "sell",
    "oversupply", "surplus", "downgrade", "risk", "accident", "leak",
    "protest", "ban", "moratorium", "negative", "concern",
]

CATEGORIES = {
    "nuclear approvals": ["approve", "approval", "license", "permit", "NRC", "regulatory"],
    "AI energy demand": ["AI", "data center", "artificial intelligence", "compute", "hyperscale"],
    "US/EU policy": ["policy", "congress", "senate", "EU", "legislation", "IRA", "subsidy", "DOE"],
    "utility contracts": ["contract", "utility", "PPA", "purchase agreement", "offtake"],
    "supply/mining": ["mine", "mining", "production", "supply", "Kazakh", "Cameco", "yellowcake"],
}


def fetch_ticker_data(symbol: str, period: str = "1y") -> pd.DataFrame:
    """Fetch OHLCV from yfinance."""
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(period=period, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return pd.DataFrame()


def refresh_all_tickers():
    """Fetch and analyze all tracked tickers."""
    results = []
    for symbol in TICKERS:
        df = fetch_ticker_data(symbol)
        if df.empty:
            continue
        
        # Cache prices
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "date": r.get("date", ""),
                "open": r.get("open"),
                "high": r.get("high"),
                "low": r.get("low"),
                "close": r.get("close"),
                "volume": r.get("volume"),
            })
        save_prices(symbol, rows)
        
        # Analyze
        result = analyze_ticker(symbol, df)
        if "error" not in result:
            save_ticker_meta(result)
            save_score_snapshot(result)
            results.append(result)
    
    return results


def classify_sentiment(text: str) -> tuple[str, float]:
    """Simple keyword-based sentiment."""
    text_lower = text.lower()
    bull = sum(1 for w in SENTIMENT_BULLISH if w.lower() in text_lower)
    bear = sum(1 for w in SENTIMENT_BEARISH if w.lower() in text_lower)
    total = bull + bear
    if total == 0:
        return "neutral", 0.0
    score = (bull - bear) / total
    if score > 0.2:
        return "bullish", round(score, 2)
    elif score < -0.2:
        return "bearish", round(score, 2)
    return "neutral", round(score, 2)


def classify_category(text: str) -> str:
    text_lower = text.lower()
    best_cat = "general"
    best_count = 0
    for cat, keywords in CATEGORIES.items():
        count = sum(1 for k in keywords if k.lower() in text_lower)
        if count > best_count:
            best_count = count
            best_cat = cat
    return best_cat


def fetch_news():
    """Fetch uranium/nuclear news from RSS feeds."""
    articles = []
    for url, source in URANIUM_RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                text = f"{title} {summary}"
                sentiment, score = classify_sentiment(text)
                category = classify_category(text)
                published = entry.get("published", "")
                # Parse date
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    from time import mktime
                    published = datetime.fromtimestamp(mktime(entry.published_parsed)).isoformat()
                
                articles.append({
                    "title": title,
                    "url": entry.get("link", ""),
                    "source": source,
                    "published": published,
                    "summary": BeautifulSoup(summary, "html.parser").get_text()[:300] if summary else "",
                    "sentiment": sentiment,
                    "sentiment_score": score,
                    "category": category,
                })
        except Exception as e:
            print(f"Error fetching news from {source}: {e}")
    
    if articles:
        save_news(articles)
    return articles


def fetch_spot_uranium():
    """Try to get spot uranium price from Cameco or fallback."""
    try:
        # Use URA NAV as a proxy combined with known correlation
        tk = yf.Ticker("URA")
        info = tk.info
        price = info.get("navPrice") or info.get("regularMarketPrice")
        if price:
            # Rough correlation: spot ≈ URA * 3.2 (approximation for display)
            spot_approx = round(price * 3.2, 2)
            save_spot_uranium(spot_approx, "URA-derived estimate")
            return {"price": spot_approx, "source": "URA-derived estimate", "date": datetime.utcnow().strftime("%Y-%m-%d")}
    except Exception as e:
        print(f"Error fetching spot uranium: {e}")
    
    # Fallback: try scraping
    try:
        async_client = httpx.Client(timeout=10)
        resp = async_client.get("https://tradingeconomics.com/commodity/uranium")
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            price_el = soup.select_one("#p")
            if price_el:
                price = float(price_el.text.strip())
                save_spot_uranium(price, "tradingeconomics")
                return {"price": price, "source": "tradingeconomics", "date": datetime.utcnow().strftime("%Y-%m-%d")}
    except Exception:
        pass
    
    return None
