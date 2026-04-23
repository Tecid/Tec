# Clicker Mode Guide — Ultra-Low Latency Trade Execution

## Overview

The Hedged Lock Bot uses an **optimized clicker system** that physically clicks the Buy/Sell buttons on your MT5 terminals. Trades opened this way appear as **100% manual** in broker logs — no API trace.

### Execution Model
| Operation | Method | Why |
|-----------|--------|-----|
| **Open Trades** | GUI Clicker (win32api) | Appears manual in broker logs |
| **Close Trades** | MT5 API (order_send) | Fast, reliable, low detection risk |
| **Read Data** | MT5 API (read-only) | Invisible to broker — no detection |

### Latency Targets
- **Click execution**: ~6-10ms (win32api raw mouse injection)
- **Click-to-click** (both terminals): ~10-20ms
- **Total including MT5 verification**: ~200-500ms (server-side processing)

---

## Setup Instructions

### Step 1: Install Dependencies

```bash
pip install pywin32
```

> `pywinauto` is optional — only needed for auto-detection fallback.

### Step 2: Arrange MT5 Terminals

1. Open **both** MT5 terminals (HFM and Equiti)
2. Arrange them **side by side** on your screen
3. Do **NOT** minimize or overlap them
4. Do **NOT** move them after calibration

### Step 3: Enable One-Click Trading

On **each** MT5 terminal:
1. Press `Alt+T` to toggle the One-Click Trading panel
2. **Accept** the confirmation dialog if prompted
3. Verify the Buy (blue) and Sell (red) buttons appear at the top-left of the chart

### Step 4: Calibrate Button Positions (Dashboard)

1. Open the bot dashboard at `http://localhost:3000`
2. Go to **Settings** page
3. Scroll to the **"🎯 Clicker Button Calibration"** section
4. For each terminal (HFM and Equiti):
   - Click **"🎯 Pick"** next to each button (Sell, Buy, Volume)
   - Move your mouse to the **center** of that button on the MT5 terminal
   - Click **"📍 Capture"** to record the coordinates
5. Click **"Save Settings"**

### Step 5: Start the Bot

The bot will automatically:
- Load your calibrated coordinates from the database
- Connect to both MT5 terminals via API (for data reading)
- Initialize the clicker on each terminal
- Pre-type the lot size during scanning phases

---

## How It Works

### Coordinate Priority

The bot tries to find button positions in this order:

1. **Dashboard Coordinates** (highest priority) — manually calibrated by you
2. **UIA Auto-Detection** — pywinauto scans the MT5 window
3. **Color Scanning** — detects red (sell) and blue (buy) button colors

For maximum reliability, **always calibrate from the dashboard**.

### Pre-typed Lot Sizes

During the scanning phase (when the bot is looking for trading opportunities), it **continuously maintains** the lot size in both terminals. When an opportunity appears:

- **If lot is already typed**: Only needs to click Buy/Sell (~6ms)
- **If lot needs updating**: Types the lot first (~50ms), then clicks

### Trade Verification

After clicking, the bot verifies the trade was opened by:
1. Polling `mt5.positions_get()` to detect a new position
2. Checking `mt5.history_deals_get()` for the actual fill price
3. Returning the confirmed ticket, price, and volume

---

## Troubleshooting

### "Clicker not ready" Error
- **Cause**: Button coordinates not set
- **Fix**: Go to Dashboard → Settings → Calibrate coordinates

### "Click executed but no new position detected"
- **Cause**: MT5 didn't process the click (window blocked, dialog open, etc.)
- **Fix**: 
  - Ensure MT5 is **not minimized** and is **visible** on screen
  - Clear any dialogs or popups on the MT5 terminal
  - Ensure One-Click Trading is enabled (`Alt+T`)
  - Re-calibrate coordinates

### "pywin32 not installed"
- **Fix**: Run `pip install pywin32`

### Coordinates seem wrong after monitor change
- **Cause**: Screen resolution or DPI changed, or MT5 windows were moved
- **Fix**: Re-calibrate from Dashboard → Settings

---

## Important Notes

1. **Do not move MT5 windows** after calibration (coordinates are screen-absolute)
2. **Do not minimize MT5** while the bot is running
3. **Do not use the mouse** on calibrated areas while the bot is active
4. **One-Click Trading must stay enabled** — the bot clicks those panel buttons
5. **Run on a dedicated PC or VPS** for best results
6. The bot will **always** use API for closing trades — this is safer and faster
