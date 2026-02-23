"""Swing trading backtest engine — replays scoring formula on historical data."""
import numpy as np
import yfinance as yf
from analysis import compute_signal_score


def compute_technicals(df):
    """Calculate all technicals needed for scoring from a price DataFrame."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    
    # RSI(14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # MACD(12,26,9)
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9).mean()
    
    # Bollinger Bands(20,2)
    bb_middle = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_middle + 2 * bb_std
    bb_lower = bb_middle - 2 * bb_std
    
    # SMA 50/200
    sma_50 = close.rolling(50).mean()
    sma_200 = close.rolling(200).mean()
    
    # 52-week high/low for zone_pct
    high_52w = high.rolling(252, min_periods=50).max()
    low_52w = low.rolling(252, min_periods=50).min()
    zone_pct = ((close - low_52w) / (high_52w - low_52w) * 100).clip(0, 100)
    
    return {
        "rsi": rsi, "macd": macd, "macd_signal": macd_signal,
        "bb_upper": bb_upper, "bb_lower": bb_lower, "bb_middle": bb_middle,
        "sma_50": sma_50, "sma_200": sma_200, "zone_pct": zone_pct,
    }


def run_backtest(symbol: str, months: int = 6, take_profit: float = 10.0,
                 stop_loss: float = 5.0, entry_score: int = 65,
                 reentry_score: int = 50, capital: float = 5000.0,
                 max_position_pct: float = 25.0):
    """Run swing trading backtest on historical data."""
    # Need extra history for SMA200 warmup
    period = f"{months + 12}mo"
    df = yf.Ticker(symbol).history(period=period)
    if df.empty or len(df) < 200:
        return {"error": f"Insufficient data for {symbol}"}
    
    tech = compute_technicals(df)
    
    # Compute daily scores
    scores = []
    for i in range(len(df)):
        try:
            zp = float(tech["zone_pct"].iloc[i])
            zone = "GREEN" if zp < 33 else ("YELLOW" if zp < 66 else "RED")
            score, _ = compute_signal_score(
                zone=zone, zone_pct=zp,
                rsi=float(tech["rsi"].iloc[i]),
                macd=float(tech["macd"].iloc[i]),
                macd_signal=float(tech["macd_signal"].iloc[i]),
                price=float(df["Close"].iloc[i]),
                bb_lower=float(tech["bb_lower"].iloc[i]),
                bb_upper=float(tech["bb_upper"].iloc[i]),
                sma_50=float(tech["sma_50"].iloc[i]),
                sma_200=float(tech["sma_200"].iloc[i]),
            )
        except Exception:
            score = 50.0
        scores.append(score)
    
    # Trim to requested months
    trim_start = len(df) - int(months * 21)  # ~21 trading days/month
    if trim_start < 0:
        trim_start = 0
    
    # Simulate trading
    cash = capital
    position = 0  # shares held
    avg_cost = 0.0
    in_cooldown = False
    trades = []
    equity_curve = []
    max_equity = capital
    max_drawdown = 0
    
    for i in range(trim_start, len(df)):
        date = df.index[i].strftime("%Y-%m-%d")
        price = float(df["Close"].iloc[i])
        score = scores[i]
        equity = cash + position * price
        equity_curve.append({"date": date, "equity": round(equity, 2), "score": round(score, 1), "price": round(price, 2)})
        
        max_equity = max(max_equity, equity)
        dd = (max_equity - equity) / max_equity * 100
        max_drawdown = max(max_drawdown, dd)
        
        if position > 0:
            pnl_pct = ((price - avg_cost) / avg_cost) * 100
            
            # Take profit
            if pnl_pct >= take_profit:
                sell_value = position * price
                cash += sell_value
                trades.append({
                    "date": date, "action": "TAKE_PROFIT", "symbol": symbol,
                    "price": round(price, 2), "shares": round(position, 2),
                    "pnl_pct": round(pnl_pct, 2), "pnl_usd": round(sell_value - position * avg_cost, 2),
                    "score": round(score, 1),
                })
                position = 0
                avg_cost = 0
                in_cooldown = True
                continue
            
            # Stop loss
            if pnl_pct <= -stop_loss:
                sell_value = position * price
                cash += sell_value
                trades.append({
                    "date": date, "action": "STOP_LOSS", "symbol": symbol,
                    "price": round(price, 2), "shares": round(position, 2),
                    "pnl_pct": round(pnl_pct, 2), "pnl_usd": round(sell_value - position * avg_cost, 2),
                    "score": round(score, 1),
                })
                position = 0
                avg_cost = 0
                in_cooldown = False  # stop loss doesn't trigger cooldown
                continue
        
        else:
            # Cooldown check
            if in_cooldown:
                if score <= reentry_score:
                    in_cooldown = False
                else:
                    continue
            
            # Entry signal
            if score >= entry_score and cash > 100:
                alloc = min(cash, capital * max_position_pct / 100)
                shares = alloc / price
                position = shares
                avg_cost = price
                cash -= alloc
                trades.append({
                    "date": date, "action": "BUY", "symbol": symbol,
                    "price": round(price, 2), "shares": round(shares, 2),
                    "score": round(score, 1),
                })
    
    # Close any open position at end
    final_price = float(df["Close"].iloc[-1])
    if position > 0:
        pnl_pct = ((final_price - avg_cost) / avg_cost) * 100
        cash += position * final_price
        trades.append({
            "date": df.index[-1].strftime("%Y-%m-%d"), "action": "CLOSE_EOB",
            "symbol": symbol, "price": round(final_price, 2),
            "shares": round(position, 2), "pnl_pct": round(pnl_pct, 2),
            "pnl_usd": round(position * (final_price - avg_cost), 2),
            "score": round(scores[-1], 1),
        })
    
    # Stats
    completed = [t for t in trades if t["action"] in ("TAKE_PROFIT", "STOP_LOSS", "CLOSE_EOB")]
    wins = [t for t in completed if t.get("pnl_pct", 0) > 0]
    losses = [t for t in completed if t.get("pnl_pct", 0) <= 0]
    total_pnl = cash - capital
    
    return {
        "symbol": symbol,
        "period_months": months,
        "rules": {
            "take_profit_pct": take_profit, "stop_loss_pct": stop_loss,
            "entry_score": entry_score, "reentry_score": reentry_score,
        },
        "results": {
            "starting_capital": capital,
            "ending_capital": round(cash, 2),
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": round(total_pnl / capital * 100, 2),
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(completed) * 100, 1) if completed else 0,
            "avg_win_pct": round(sum(t.get("pnl_pct", 0) for t in wins) / len(wins), 2) if wins else 0,
            "avg_loss_pct": round(sum(t.get("pnl_pct", 0) for t in losses) / len(losses), 2) if losses else 0,
            "max_drawdown_pct": round(max_drawdown, 2),
            "buy_and_hold_return_pct": round((final_price / float(df["Close"].iloc[trim_start]) - 1) * 100, 2),
        },
        "trades": trades,
        "equity_curve": equity_curve[::max(1, len(equity_curve) // 60)],  # sample ~60 points
    }
