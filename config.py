# =============================================================================
# MT5 HEDGED LOCK ARBITRAGE BOT - CONFIGURATION
# =============================================================================
# This configuration file controls all parameters for the latency arbitrage bot.
# The bot implements a "Hedged Lock" strategy between two MT5 brokers.
# =============================================================================

# =============================================================================
# TERMINAL PATHS - Update these to match your MT5 installations
# =============================================================================
# These must point to the terminal64.exe files of your two broker installations.
# Each terminal should be logged into a different broker account.
HFM_TERMINAL = r"C:\MT5_HFM\terminal64.exe"
EQUITI_TERMINAL = r"C:\MT5_Equiti\terminal64.exe"

# =============================================================================
# TRADING PARAMETERS
# =============================================================================
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ SYMBOLS PER BROKER                                                      │
# │ Different brokers may have different symbol names for the same pair.    │
# │ For example: HFM uses "EURUSD" while Equiti uses "EURUSD.x"             │
# │                                                                         │
# │ Make sure both symbols represent the SAME underlying instrument!        │
# └─────────────────────────────────────────────────────────────────────────┘
HFM_SYMBOL = "EURUSDb"         # Symbol on HFM broker
EQUITI_SYMBOL = "EURUSD.pr"    # Symbol on Equiti broker (low spread variant!)

LOT_PER_BASE = 0.35          # Lot size per base amount (e.g., 0.35 lots per $100)
LOT_BASE_AMOUNT = 100        # Base amount for lot calculation (e.g., $100)
MIN_LOT_SIZE = 0.01          # Minimum lot size for random range
MAX_LOT_SIZE = 4.8           # Maximum lot size for random range
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ LOT SIZING LOGIC (Ratio + Range)                                       │
# │                                                                         │
# │ Step 1: Calculate ratio_lot from the lower balance:                     │
# │   ratio_lot = (lower_balance / LOT_BASE_AMOUNT) * LOT_PER_BASE         │
# │   Example: $178 balance → (178/100) * 0.35 = 0.62 lots                 │
# │                                                                         │
# │ Step 2: Apply one of three scenarios:                                   │
# │   1. ratio_lot > MAX_LOT_SIZE → random(MIN_LOT_SIZE, MAX_LOT_SIZE)     │
# │   2. MIN_LOT_SIZE < ratio_lot < MAX_LOT_SIZE → random(MIN, ratio_lot)  │
# │   3. ratio_lot < MIN_LOT_SIZE → use ratio_lot directly                 │
# └─────────────────────────────────────────────────────────────────────────┘

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ LOT RECOVERY MODE                                                       │
# │ When a trade enters at or below MIN_ENTRY_POINT_DIFF, instead of        │
# │ shutting down, the bot enters "recovery mode":                           │
# │   - Next N trades use a fixed small lot size                             │
# │   - If those trades are good (entry gap > threshold), revert to normal   │
# │   - If any recovery trade is bad, the recovery counter resets            │
# └─────────────────────────────────────────────────────────────────────────┘
RECOVERY_LOT_SIZE = 0.05         # Fixed lot size during recovery mode
RECOVERY_TRADE_COUNT = 2         # Number of good recovery trades before reverting
MAGIC_NUMBER = 123456        # Unique identifier for bot's trades

# =============================================================================
# STRATEGY PARAMETERS - UNIVERSAL LOGIC
# =============================================================================
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ ENTRY GAP THRESHOLD                                                     │
# │ This is the minimum price difference (in price units) required to enter.│
# │                                                                         │
# │ For a 5-digit broker (EURUSD quoted as 1.12345):                        │
# │   - 1 point = 0.00001                                                   │
# │   - 5 points = 0.00005                                                  │
# │                                                                         │
# │ IMPORTANT: The universal logic uses Ask/Bid properly, so this gap       │
# │ represents PURE PROFIT after spread costs are paid. If the math shows   │
# │ +5 points, that's 5 points of real profit (before commission only).     │
# └─────────────────────────────────────────────────────────────────────────┘
MIN_ENTRY_GAP = 0.00005      # 7 points (Entry 7 + Exit 3 = 10 pts = $10/lot)

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ MAX SPREAD FILTER                                                       │
# │ If EITHER broker's spread exceeds this value, the bot will NOT trade.   │
# │ This prevents trading during volatile/illiquid periods when spreads     │
# │ are abnormally wide.                                                    │
# │                                                                         │
# │ For a 5-digit broker (EURUSD):                                          │
# │   - 1 pip = 10 points = 0.00010                                         │
# │   - 2 pips = 20 points = 0.00020                                        │
# │                                                                         │
# │ IMPACT ON WINRATE:                                                      │
# │   - Fewer trades (skips wide-spread periods)                            │
# │   - Higher quality entries (better execution prices)                    │
# │   - Better risk/reward on each trade                                    │
# └─────────────────────────────────────────────────────────────────────────┘
MAX_SPREAD = 0.00003         # 0.3 pips = 3 points (Strict filter for raw spreads)

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ EXIT REVERSAL GAP (POINT-BASED EXIT)                                    │
# │ Exit when the price gap REVERSES by this amount (prices crossed over).  │
# │                                                                         │
# │ PROFIT FORMULA: Total Points = MIN_ENTRY_GAP + EXIT_REVERSAL_GAP        │
# │   Example: 7 pts entry + 3 pts exit = 10 pts total = $10 per lot        │
# │                                                                         │
# │ STRATEGY TIP:                                                           │
# │   - Higher ENTRY = Fewer but safer entries (more divergence required)   │
# │   - Lower EXIT = Easier to close (less convergence needed)              │
# │   - Recommended: Entry >= Exit for reliable exits                       │
# │                                                                         │
# │ Set to 0 to DISABLE reversal exit (only use profit target).             │
# └─────────────────────────────────────────────────────────────────────────┘
EXIT_REVERSAL_GAP = 0.00004  # 3 points (Entry 7 + Exit 3 = 10 pts = $10/lot)

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ MINIMUM HOLD TIME                                                       │
# │ The bot will NOT exit trades before this time has elapsed.              │
# │ This prevents rapid in/out trades and gives the arbitrage time to work. │
# └─────────────────────────────────────────────────────────────────────────┘
MIN_HOLD_TIME = 180          # 4 minutes in seconds (240s)

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ TARGET NET PROFIT (DOLLAR-BASED EXIT) - CURRENTLY DISABLED              │
# │                                                                         │
# │ Set to 0 to disable dollar-based exits and use ONLY point-based exits.  │
# │ Point-based (EXIT_REVERSAL_GAP) is more reliable and deterministic.     │
# │                                                                         │
# │ If enabled (> 0): Bot exits when combined PnL >= this value.            │
# │ Formula: LOT_SIZE × PROFIT_PER_LOT = Target                             │
# └─────────────────────────────────────────────────────────────────────────┘
TARGET_NET_PROFIT = 0  # DISABLED - using point-based exit instead

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ EXIT SLIPPAGE BUFFER                                                    │
# │ Extra profit buffer to account for slippage when closing positions.     │
# │                                                                         │
# │ The bot will wait until: Net PnL >= Target + Buffer before closing.     │
# │ This helps ensure the ACTUAL final profit meets or exceeds target.      │
# │                                                                         │
# │ Example: If target is $0.64 and buffer is $0.15:                        │
# │   - Bot waits until Net PnL reaches $0.79 before closing                │
# │   - Even with $0.10 slippage, final profit should be ~$0.69             │
# │                                                                         │
# │ Set to 0 to disable buffer (close exactly at target, accept slippage)   │
# └─────────────────────────────────────────────────────────────────────────┘
EXIT_SLIPPAGE_BUFFER = 0  # $0.05 buffer above target before closing

# =============================================================================
# EXECUTION SETTINGS
# =============================================================================
SLIPPAGE = 10                # Max slippage in points allowed during execution
RETRY_ATTEMPTS = 3           # Number of retries for failed trade execution
RETRY_DELAY = 0.5            # Seconds between retry attempts
TICK_TIMEOUT = 5.0           # Seconds to wait for tick data before timeout

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ EXECUTION TIMEOUT                                                       │
# │ How long to wait for BOTH trades to execute before giving up.           │
# │ If one trade succeeds but the other hasn't responded after this time,   │
# │ the bot will close the successful trade and go back to scanning.        │
# │                                                                         │
# │ Set higher (e.g., 3-5s) if brokers are slow to respond.                 │
# │ Set lower (e.g., 1s) for faster reaction to failed executions.          │
# └─────────────────────────────────────────────────────────────────────────┘
EXECUTION_TIMEOUT = 1      # Seconds to wait for both trades to complete

# =============================================================================
# COOLDOWN SETTINGS
# =============================================================================
# After a failed trade (one leg fails), the bot waits before trying again.
# This prevents rapid consecutive losses from repeated failures.
FAILURE_COOLDOWN = 30        # Seconds to wait after a failed trade attempt

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ OPPORTUNITY CONFIRMATION DELAY                                          │
# │ When an opportunity is detected, the bot will wait this many seconds    │
# │ and then RECHECK if the opportunity still exists before executing.      │
# │                                                                         │
# │ This prevents false triggers from momentary price spikes/noise.         │
# │   - Higher values = more conservative, fewer false entries              │
# │   - Lower values = faster entry, but more risk of noise trades          │
# │                                                                         │
# │ Set to 0 to disable confirmation and execute immediately (old behavior) │
# └─────────────────────────────────────────────────────────────────────────┘
OPPORTUNITY_CONFIRM_DELAY = 0.1  # Seconds to wait and reconfirm opportunity (was 0.5)

# ┌─────────────────────────────────────────────────────────────────────────┐
# │ EXIT CONFIRMATION DELAY                                                 │
# │ When an exit condition is met (profit target), the bot will wait this   │
# │ many seconds and then RECHECK if the exit condition still exists.       │
# │                                                                         │
# │ This prevents exiting on momentary profit spikes that quickly reverse.  │
# │   - Higher values = more conservative, might miss peak profit           │
# │   - Lower values = faster exit, but more risk of exiting on noise       │
# │                                                                         │
# │ Set to 0 to disable confirmation and exit immediately (old behavior)    │
# └─────────────────────────────────────────────────────────────────────────┘
EXIT_CONFIRM_DELAY = 0.3  # Seconds to wait and reconfirm exit condition

# =============================================================================
# TRADE EXECUTION MODE — CLICKER ONLY
# =============================================================================
# All trade OPENING uses GUI clicker (win32api raw mouse injection).
# All trade CLOSING uses API (fast, reliable, low detection risk).
# All data reads use API (invisible to broker — they can't detect read-only calls).
#
# Trades appear as 100% manual in broker logs — no API trace for opening.
TRADE_MODE = "CLICK"  # Always CLICK — do not change

# Input method for clicker: 'legacy' (Win10) or 'sendinput' (Win11)
# Legacy uses mouse_event/keybd_event — fast on Win10, fails on Win11
# SendInput uses ctypes SendInput API — compatible with Win11 UIPI
INPUT_METHOD = "legacy"

# Trade delay: random wait between trades (seconds)
# 0 = no delay (immediate next scan)
MIN_TRADE_DELAY = 0.0
MAX_TRADE_DELAY = 0.0

# =============================================================================
# CLICKER BUTTON COORDINATES (Dashboard Calibration)
# =============================================================================
# These are screen-absolute X,Y coordinates for Buy/Sell buttons on each terminal.
# Set to 0 to use auto-detection (UIA or color scanning).
# For best reliability, calibrate these from the Dashboard Settings page.
#
# HFM Terminal Button Coordinates
HFM_BUY_X = 0     # X coordinate of HFM Buy button center
HFM_BUY_Y = 0     # Y coordinate of HFM Buy button center
HFM_SELL_X = 0    # X coordinate of HFM Sell button center
HFM_SELL_Y = 0    # Y coordinate of HFM Sell button center
HFM_VOLUME_X = 0  # X coordinate of HFM volume input field
HFM_VOLUME_Y = 0  # Y coordinate of HFM volume input field
HFM_CLOSE_X_X = 0  # X coordinate of HFM close X button in Trades tab
HFM_CLOSE_X_Y = 0  # Y coordinate of HFM close X button in Trades tab

# Equiti Terminal Button Coordinates
EQUITI_BUY_X = 0     # X coordinate of Equiti Buy button center
EQUITI_BUY_Y = 0     # Y coordinate of Equiti Buy button center
EQUITI_SELL_X = 0    # X coordinate of Equiti Sell button center
EQUITI_SELL_Y = 0    # Y coordinate of Equiti Sell button center
EQUITI_VOLUME_X = 0  # X coordinate of Equiti volume input field
EQUITI_VOLUME_Y = 0  # Y coordinate of Equiti volume input field
EQUITI_CLOSE_X_X = 0  # X coordinate of Equiti close X button in Trades tab
EQUITI_CLOSE_X_Y = 0  # Y coordinate of Equiti close X button in Trades tab
