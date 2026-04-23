# Hedged Lock Bot - Version 6.0

A professional arbitrage trading bot with a React dashboard for monitoring and control.

## Features

- **Real-time Dashboard**: Monitor HFM and Equiti prices, arbitrage gaps, and P&L
- **User Authentication**: Secure login/signup with JWT tokens
- **Cloud Database**: All settings and trade history saved to PostgreSQL
- **News Scheduler**: Block trading during high-impact news events
- **Trade History**: Complete record of all trades with profit tracking

## Requirements

- **Python 3.10+** with pip
- **Node.js 18+** (only for building, not required to run)
- **PostgreSQL Database** (cloud or local)
- **MT5 Terminals**: HFM and Equiti installed

## Quick Start

### 1. Setup Database

Create a PostgreSQL database (Supabase, Render, or local). Then configure:

```bash
# Copy the environment template
copy server\.env.example server\.env

# Edit .env with your database URL
notepad server\.env
```

### 2. Install & Run

Simply double-click `start.bat` or run:

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
cd server
python app.py
```

### 3. Access Dashboard

Open http://localhost:5000 in your browser.

## For Distribution (Friends Package)

### Building for Distribution

1. Run `build_dashboard.bat` to compile the React app
2. The `client\dist\` folder now contains the static files
3. You can now zip the entire `version-6.0` folder

### What Friends Need

Friends only need **Python** installed. They:
1. Extract the zip
2. Run `start.bat`
3. Open their browser to localhost:5000

## Project Structure

```
version-6.0/
├── client/                 # React Dashboard
│   ├── src/
│   │   ├── components/     # UI Components
│   │   ├── context/        # React Context (Auth, Socket)
│   │   ├── pages/          # Page Components
│   │   └── styles/         # CSS Styles
│   └── dist/               # Built static files
├── server/                 # Python Backend
│   ├── app.py              # Flask server
│   ├── auth.py             # Authentication routes
│   ├── api.py              # API routes
│   ├── database.py         # Database models
│   └── bot_manager.py      # Bot control wrapper
├── master.py               # Trading bot core
├── worker.py               # MT5 worker process
├── strategy.py             # Arbitrage strategy logic
├── config.py               # Default configuration
├── start.bat               # Main launcher
└── requirements.txt        # Python dependencies
```

## Configuration

All configuration is done through the dashboard Settings page:

- **Terminal Paths**: Path to your HFM and Equiti MT5 terminals
- **Trading Symbols**: Symbol names for each broker
- **Lot Sizing**: Auto-calculation parameters
- **Entry/Exit**: Gap thresholds and timing

## Support

For issues or questions, contact the developer.
