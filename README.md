# ☢️ Uranium Thermometer

A sophisticated investment dashboard for tracking uranium ETFs (URA) and related stocks. Bloomberg Terminal aesthetic with real-time technical analysis.

![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Thermometer Gauge**: Visual indicator showing URA's position in its 6-month range (green/yellow/red zones)
- **Multi-Ticker Dashboard**: Track URA, CCJ, KAP, UEC, UUUU, DNN, NXE
- **Technical Analysis**: RSI(14), MACD(12/26/9), Bollinger Bands(20,2), SMA(50/200)
- **Signal Scoring**: 0-100 composite buy/sell score with reasoning
- **Macro News Feed**: Aggregated uranium/nuclear news with sentiment analysis
- **Zone Classification**: GREEN (buy), YELLOW (hold), RED (sell) based on range position
- **Interactive Charts**: Price history with technical overlays
- **Auto-Refresh**: Every 15 minutes during market hours

## Tech Stack

- **Backend**: Python 3, FastAPI, yfinance, pandas, numpy
- **Frontend**: React 19, Vite, Tailwind CSS, Recharts
- **Database**: SQLite for caching

## Quick Start

```bash
# Install backend dependencies
pip install -r backend/requirements.txt

# Build frontend
cd frontend && npm install && npm run build
cp -r dist ../backend/static

# Run
cd backend && python3 main.py
# Visit http://localhost:8050
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/thermometer` | Main dashboard data |
| `GET /api/ticker/{symbol}` | Detailed ticker view |
| `GET /api/news` | Macro news feed |
| `GET /api/history/{symbol}` | Price history |
| `GET /api/signals` | Current signals |
| `GET /api/refresh` | Manual data refresh |

## Methodology

### Zone Classification
- **GREEN** (Buy Zone): Price in bottom 20% of 6-month range
- **YELLOW** (Hold/Wait): Middle 60% of range
- **RED** (Sell Zone): Top 20% of range

### Signal Score (0-100)
Composite score combining:
- Zone position (±25 pts)
- RSI oversold/overbought (±15 pts)
- MACD crossover (±10 pts)
- Bollinger Band position (±10 pts)
- SMA 50/200 relationship (±10 pts)

## Deployment

```bash
# Install systemd service
sudo cp uranium-thermometer.service /etc/systemd/system/
sudo systemctl enable uranium-thermometer
sudo systemctl start uranium-thermometer
```

## Disclaimer

This is not financial advice. For educational and informational purposes only.
