"""SQLite database for caching price data and news."""
import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "uranium.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS price_cache (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume INTEGER,
            PRIMARY KEY (symbol, date)
        );
        CREATE TABLE IF NOT EXISTS ticker_meta (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            last_updated TEXT,
            current_price REAL,
            range_low REAL,
            range_high REAL,
            zone TEXT,
            zone_pct REAL,
            signal_score REAL,
            signal_label TEXT,
            rsi REAL,
            macd REAL,
            macd_signal REAL,
            bb_upper REAL,
            bb_lower REAL,
            bb_middle REAL,
            sma_50 REAL,
            sma_200 REAL,
            support REAL,
            resistance REAL,
            change_pct REAL,
            extra_json TEXT
        );
        CREATE TABLE IF NOT EXISTS news_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            url TEXT UNIQUE,
            source TEXT,
            published TEXT,
            summary TEXT,
            sentiment TEXT,
            sentiment_score REAL,
            category TEXT,
            fetched_at TEXT
        );
        CREATE TABLE IF NOT EXISTS spot_uranium (
            date TEXT PRIMARY KEY,
            price REAL,
            source TEXT
        );
        CREATE TABLE IF NOT EXISTS score_history (
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            price REAL,
            signal_score REAL,
            zone TEXT,
            zone_pct REAL,
            rsi REAL,
            PRIMARY KEY (symbol, timestamp)
        );
        CREATE TABLE IF NOT EXISTS portfolio (
            symbol TEXT PRIMARY KEY,
            shares REAL DEFAULT 0,
            avg_cost REAL DEFAULT 0,
            last_updated TEXT
        );
        CREATE TABLE IF NOT EXISTS trade_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            action TEXT NOT NULL,
            symbol TEXT NOT NULL,
            shares REAL NOT NULL,
            price REAL NOT NULL,
            total REAL,
            reasoning TEXT,
            score_at_trade REAL,
            zone_at_trade TEXT,
            macro_at_trade TEXT
        );
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            total_value REAL,
            cash REAL,
            pnl REAL,
            pnl_pct REAL
        );
    """)
    conn.commit()
    conn.close()


def save_prices(symbol: str, rows: list[dict]):
    conn = get_db()
    for r in rows:
        conn.execute(
            "INSERT OR REPLACE INTO price_cache VALUES (?,?,?,?,?,?,?)",
            (symbol, r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"]),
        )
    conn.commit()
    conn.close()


def get_prices(symbol: str, days: int = 180) -> list[dict]:
    conn = get_db()
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT * FROM price_cache WHERE symbol=? AND date>=? ORDER BY date",
        (symbol, cutoff),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_ticker_meta(data: dict):
    conn = get_db()
    conn.execute(
        """INSERT OR REPLACE INTO ticker_meta 
        (symbol,name,last_updated,current_price,range_low,range_high,zone,zone_pct,
         signal_score,signal_label,rsi,macd,macd_signal,bb_upper,bb_lower,bb_middle,
         sma_50,sma_200,support,resistance,change_pct,extra_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["symbol"], data.get("name"), data.get("last_updated"),
            data.get("current_price"), data.get("range_low"), data.get("range_high"),
            data.get("zone"), data.get("zone_pct"), data.get("signal_score"),
            data.get("signal_label"), data.get("rsi"), data.get("macd"),
            data.get("macd_signal"), data.get("bb_upper"), data.get("bb_lower"),
            data.get("bb_middle"), data.get("sma_50"), data.get("sma_200"),
            data.get("support"), data.get("resistance"), data.get("change_pct"),
            json.dumps(data.get("extra", {})),
        ),
    )
    conn.commit()
    conn.close()


def get_all_ticker_meta() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM ticker_meta ORDER BY symbol").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ticker_meta(symbol: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM ticker_meta WHERE symbol=?", (symbol,)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_news(articles: list[dict]):
    conn = get_db()
    for a in articles:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO news_cache 
                (title,url,source,published,summary,sentiment,sentiment_score,category,fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (a["title"], a["url"], a.get("source"), a.get("published"),
                 a.get("summary"), a.get("sentiment"), a.get("sentiment_score"),
                 a.get("category"), datetime.utcnow().isoformat()),
            )
        except Exception:
            pass
    conn.commit()
    conn.close()


def get_news(limit: int = 50, category: str = None) -> list[dict]:
    conn = get_db()
    if category:
        rows = conn.execute(
            "SELECT * FROM news_cache WHERE category=? ORDER BY published DESC LIMIT ?",
            (category, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM news_cache ORDER BY published DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_spot_uranium(price: float, source: str):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO spot_uranium VALUES (?,?,?)",
        (datetime.utcnow().strftime("%Y-%m-%d"), price, source),
    )
    conn.commit()
    conn.close()


def save_score_snapshot(data: dict):
    conn = get_db()
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:00")  # hourly granularity
    conn.execute(
        "INSERT OR REPLACE INTO score_history (symbol, timestamp, price, signal_score, zone, zone_pct, rsi, "
        "macd_val, macd_sig, bb_lower, bb_upper, sma_50, sma_200) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (data["symbol"], ts, data.get("current_price"), data.get("signal_score"),
         data.get("zone"), data.get("zone_pct"), data.get("rsi"),
         data.get("macd"), data.get("macd_signal"),
         data.get("bb_lower"), data.get("bb_upper"),
         data.get("sma_50"), data.get("sma_200")),
    )
    conn.commit()
    conn.close()


def get_score_history(symbol: str, days: int = 30) -> list[dict]:
    conn = get_db()
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
    rows = conn.execute(
        "SELECT * FROM score_history WHERE symbol=? AND timestamp>=? ORDER BY timestamp",
        (symbol, cutoff),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_spot_uranium() -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM spot_uranium ORDER BY date DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None
