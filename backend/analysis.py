"""Technical analysis engine for uranium stocks."""
import numpy as np
import pandas as pd
from datetime import datetime


TICKERS = {
    "URA": "Global X Uranium ETF",
    "CCJ": "Cameco Corporation",
    "KAP.IL": "Kazatomprom",
    "UEC": "Uranium Energy Corp",
    "UUUU": "Energy Fuels",
    "DNN": "Denison Mines",
    "NXE": "NexGen Energy",
}


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_bollinger(series: pd.Series, period: int = 20, std_mult: float = 2.0):
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    return upper, middle, lower


def compute_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def find_support_resistance(df: pd.DataFrame, lookback: int = 60):
    """Find support/resistance from recent pivots."""
    if len(df) < lookback:
        lookback = len(df)
    recent = df.tail(lookback)
    lows = recent["low"].nsmallest(5).mean()
    highs = recent["high"].nlargest(5).mean()
    return round(lows, 2), round(highs, 2)


def classify_zone(price: float, range_low: float, range_high: float) -> tuple[str, float]:
    """Classify into GREEN/YELLOW/RED zone. Returns (zone, pct_in_range)."""
    if range_high == range_low:
        return "YELLOW", 50.0
    pct = (price - range_low) / (range_high - range_low) * 100
    pct = max(0, min(100, pct))
    if pct <= 20:
        zone = "GREEN"
    elif pct >= 80:
        zone = "RED"
    else:
        zone = "YELLOW"
    return zone, round(pct, 1)


def compute_signal_score(zone: str, zone_pct: float, rsi: float, macd: float, 
                          macd_signal: float, price: float, bb_lower: float, 
                          bb_upper: float, sma_50: float, sma_200: float) -> tuple[float, str]:
    """
    Compute 0-100 signal score. Continuous, not bucketed.
    Higher = stronger BUY signal (price cheap, oversold, momentum turning up).
    Lower = stronger SELL signal (price expensive, overbought, momentum fading).
    
    Weights: Range position 40%, RSI 25%, MACD 15%, Bollinger 10%, SMA 10%
    """
    components = []
    
    # 1. Range position (40% weight) — continuous linear mapping
    # zone_pct 0 = bottom of range (max buy), 100 = top of range (max sell)
    range_score = 100 - zone_pct  # invert: low position = high score
    components.append(('range', range_score, 0.40))
    
    # 2. RSI (25% weight) — continuous
    if rsi is not None and not np.isnan(rsi):
        # RSI 0-30 → score 100-70 (oversold = buy), 30-50 → 70-50, 50-70 → 50-30, 70-100 → 30-0
        rsi_score = 100 - rsi  # invert: low RSI = high score
        components.append(('rsi', rsi_score, 0.25))
    
    # 3. MACD (15% weight) — distance from signal line, normalized
    if macd is not None and macd_signal is not None and not (np.isnan(macd) or np.isnan(macd_signal)):
        macd_diff = macd - macd_signal
        # Normalize: clip to reasonable range and map to 0-100
        # Positive diff (bullish crossover) → higher score
        macd_norm = max(-2, min(2, macd_diff))  # clip
        macd_score = 50 + (macd_norm / 2) * 50  # map -2..2 → 0..100
        components.append(('macd', macd_score, 0.15))
    
    # 4. Bollinger position (10% weight) — where price sits in BB range
    if bb_lower is not None and bb_upper is not None and not (np.isnan(bb_lower) or np.isnan(bb_upper)):
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            bb_pct = (price - bb_lower) / bb_range * 100
            bb_score = 100 - max(0, min(100, bb_pct))  # invert: near lower band = buy
            components.append(('bb', bb_score, 0.10))
    
    # 5. SMA trend (10% weight) — price vs SMA50, SMA50 vs SMA200
    if sma_50 is not None and sma_200 is not None and not (np.isnan(sma_50) or np.isnan(sma_200)):
        sma_score = 50.0
        # Golden cross bonus
        if sma_50 > sma_200:
            sma_score += 15
        else:
            sma_score -= 15
        # Price relative to SMA50
        if price and sma_50 > 0:
            price_vs_sma = (price / sma_50 - 1) * 100  # % above/below
            # Above SMA50 = bullish momentum, but also means less upside
            # Use moderate penalty: slightly above is good, way above is extended
            if price_vs_sma > 10:
                sma_score -= 10  # extended
            elif price_vs_sma > 0:
                sma_score += 10  # healthy uptrend
            elif price_vs_sma < -10:
                sma_score += 15  # deeply below, potential buy
            else:
                sma_score += 5  # slightly below
        sma_score = max(0, min(100, sma_score))
        components.append(('sma', sma_score, 0.10))
    
    # Weighted average
    if not components:
        return 50.0, "HOLD"
    
    total_weight = sum(w for _, _, w in components)
    score = sum(s * w for _, s, w in components) / total_weight
    score = max(0, min(100, score))
    
    # Labels with conviction
    if score >= 75:
        label = "STRONG BUY"
    elif score >= 60:
        label = "BUY"
    elif score >= 45:
        label = "HOLD"
    elif score >= 30:
        label = "SELL"
    else:
        label = "STRONG SELL"
    
    return round(score, 1), label


def analyze_ticker(symbol: str, df: pd.DataFrame) -> dict:
    """Full analysis for a single ticker. df must have OHLCV columns."""
    if df.empty or len(df) < 5:
        return {"symbol": symbol, "error": "Insufficient data"}
    
    close = df["close"]
    price = close.iloc[-1]
    
    # 6-month range (context)
    six_mo = df.tail(126)
    range_low_6m = float(six_mo["low"].min()) if len(six_mo) > 0 else float(df["low"].min())
    range_high_6m = float(six_mo["high"].max()) if len(six_mo) > 0 else float(df["high"].max())
    
    # 3-month range (primary for zone classification — more tactical)
    three_mo = df.tail(63)
    range_low = float(three_mo["low"].min()) if len(three_mo) > 0 else range_low_6m
    range_high = float(three_mo["high"].max()) if len(three_mo) > 0 else range_high_6m
    
    zone, zone_pct = classify_zone(price, range_low, range_high)
    
    # Technicals
    rsi_series = compute_rsi(close)
    rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else None
    
    bb_upper, bb_middle, bb_lower = compute_bollinger(close)
    macd_line, signal_line = compute_macd(close)
    sma_50 = compute_sma(close, 50)
    sma_200 = compute_sma(close, 200)
    
    support, resistance = find_support_resistance(df)
    
    bb_u = float(bb_upper.iloc[-1]) if not bb_upper.empty else None
    bb_m = float(bb_middle.iloc[-1]) if not bb_middle.empty else None
    bb_l = float(bb_lower.iloc[-1]) if not bb_lower.empty else None
    macd_val = float(macd_line.iloc[-1]) if not macd_line.empty else None
    macd_sig = float(signal_line.iloc[-1]) if not signal_line.empty else None
    sma50 = float(sma_50.iloc[-1]) if not sma_50.empty else None
    sma200 = float(sma_200.iloc[-1]) if not sma_200.empty else None
    
    signal_score, signal_label = compute_signal_score(
        zone, zone_pct, rsi, macd_val, macd_sig, price, bb_l, bb_u, sma50, sma200
    )
    
    prev_close = float(close.iloc[-2]) if len(close) > 1 else price
    change_pct = round((price - prev_close) / prev_close * 100, 2)
    
    return {
        "symbol": symbol,
        "name": TICKERS.get(symbol, symbol),
        "last_updated": datetime.utcnow().isoformat(),
        "current_price": round(float(price), 2),
        "change_pct": change_pct,
        "range_low": round(range_low, 2),
        "range_high": round(range_high, 2),
        "range_low_3m": round(range_low, 2),
        "range_high_3m": round(range_high, 2),
        "zone": zone,
        "zone_pct": zone_pct,
        "signal_score": signal_score,
        "signal_label": signal_label,
        "rsi": round(rsi, 2) if rsi and not np.isnan(rsi) else None,
        "macd": round(macd_val, 4) if macd_val and not np.isnan(macd_val) else None,
        "macd_signal": round(macd_sig, 4) if macd_sig and not np.isnan(macd_sig) else None,
        "bb_upper": round(bb_u, 2) if bb_u and not np.isnan(bb_u) else None,
        "bb_lower": round(bb_l, 2) if bb_l and not np.isnan(bb_l) else None,
        "bb_middle": round(bb_m, 2) if bb_m and not np.isnan(bb_m) else None,
        "sma_50": round(sma50, 2) if sma50 and not np.isnan(sma50) else None,
        "sma_200": round(sma200, 2) if sma200 and not np.isnan(sma200) else None,
        "support": support,
        "resistance": resistance,
        "extra": {
            "range_low_6m": round(range_low_6m, 2),
            "range_high_6m": round(range_high_6m, 2),
        },
    }
