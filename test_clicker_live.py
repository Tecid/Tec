"""
═══════════════════════════════════════════════════════════════════════════════
  CLICKER MODE — LIVE TESTING SCRIPT
  Run this BEFORE starting the bot to verify everything works.
═══════════════════════════════════════════════════════════════════════════════

Usage:
  python test_clicker_live.py

This script tests each component in isolation:
  Phase 1: MT5 API connection (read-only — safe)
  Phase 2: Window detection (finds MT5 terminals — safe)
  Phase 3: Coordinate detection (finds Buy/Sell buttons — safe)
  Phase 4: Lot size typing test (types into volume field — safe, just types a number)
  Phase 5: LIVE CLICK TEST (actually clicks Buy/Sell — OPENS A REAL TRADE!)

You'll be prompted before each dangerous step.
"""

import sys
import time
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def print_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_result(test_name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}  {test_name}")
    if details:
        print(f"         → {details}")


def ask_continue(msg="Continue?"):
    resp = input(f"\n  {msg} (y/n): ").strip().lower()
    return resp in ('y', 'yes', '')


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: MT5 API Connection
# ═══════════════════════════════════════════════════════════════════════════════
def test_mt5_connection():
    print_header("PHASE 1: MT5 API Connection (Read-Only — Safe)")
    
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print_result("Import MetaTrader5", False, "pip install MetaTrader5")
        return False, None, None
    
    import config
    
    # Test HFM
    print(f"\n  Testing HFM terminal: {config.HFM_TERMINAL}")
    hfm_ok = mt5.initialize(path=config.HFM_TERMINAL, portable=True)
    hfm_info = None
    if hfm_ok:
        hfm_info = mt5.account_info()
        if hfm_info:
            print_result("HFM Connection", True, 
                        f"Account: {hfm_info.login}, Balance: ${hfm_info.balance:.2f}")
            
            # Test tick data
            tick = mt5.symbol_info_tick(config.HFM_SYMBOL)
            if tick:
                print_result("HFM Tick Data", True, 
                           f"{config.HFM_SYMBOL} Bid: {tick.bid}, Ask: {tick.ask}")
            else:
                # Try selecting symbol first
                mt5.symbol_select(config.HFM_SYMBOL, True)
                tick = mt5.symbol_info_tick(config.HFM_SYMBOL)
                print_result("HFM Tick Data", tick is not None,
                           f"Symbol: {config.HFM_SYMBOL}" + (f" Bid: {tick.bid}" if tick else " — Not found"))
        else:
            print_result("HFM Connection", False, "Connected but no account info")
        mt5.shutdown()
    else:
        print_result("HFM Connection", False, f"Error: {mt5.last_error()}")
    
    # Test Equiti
    print(f"\n  Testing Equiti terminal: {config.EQUITI_TERMINAL}")
    eq_ok = mt5.initialize(path=config.EQUITI_TERMINAL, portable=True)
    eq_info = None
    if eq_ok:
        eq_info = mt5.account_info()
        if eq_info:
            print_result("Equiti Connection", True,
                        f"Account: {eq_info.login}, Balance: ${eq_info.balance:.2f}")
            
            tick = mt5.symbol_info_tick(config.EQUITI_SYMBOL)
            if tick:
                print_result("Equiti Tick Data", True,
                           f"{config.EQUITI_SYMBOL} Bid: {tick.bid}, Ask: {tick.ask}")
            else:
                mt5.symbol_select(config.EQUITI_SYMBOL, True)
                tick = mt5.symbol_info_tick(config.EQUITI_SYMBOL)
                print_result("Equiti Tick Data", tick is not None,
                           f"Symbol: {config.EQUITI_SYMBOL}" + (f" Bid: {tick.bid}" if tick else " — Not found"))
        else:
            print_result("Equiti Connection", False, "Connected but no account info")
        mt5.shutdown()
    else:
        print_result("Equiti Connection", False, f"Error: {mt5.last_error()}")
    
    return hfm_ok and eq_ok, hfm_info, eq_info


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: Window Detection
# ═══════════════════════════════════════════════════════════════════════════════
def test_window_detection():
    print_header("PHASE 2: MT5 Window Detection (Safe)")
    
    try:
        import win32gui
    except ImportError:
        print_result("Import win32api", False, "pip install pywin32")
        return False
    
    from mt5_clicker import find_all_mt5_windows
    
    windows = find_all_mt5_windows()
    print_result("Find MT5 Windows", len(windows) > 0, f"Found {len(windows)} window(s)")
    
    for i, w in enumerate(windows):
        print(f"\n  Window {i+1}:")
        print(f"    Title:  {w['title']}")
        print(f"    Handle: {w['handle']}")
        print(f"    Rect:   L={w['rect']['left']}, T={w['rect']['top']}, "
              f"R={w['rect']['right']}, B={w['rect']['bottom']}")
        print(f"    Size:   {w['width']}x{w['height']}")
    
    if len(windows) < 2:
        print(f"\n  ⚠️  Expected 2 MT5 windows (HFM + Equiti), found {len(windows)}")
        print(f"      Make sure both terminals are open and NOT minimized")
    
    return len(windows) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: Clicker Connection & Coordinate Detection
# ═══════════════════════════════════════════════════════════════════════════════
def test_clicker_connection():
    print_header("PHASE 3: Clicker Connection & Coordinates (Safe)")
    
    import config
    from mt5_clicker import MT5Clicker
    
    results = {}
    
    for broker, terminal, symbol in [
        ("HFM", config.HFM_TERMINAL, config.HFM_SYMBOL),
        ("EQUITI", config.EQUITI_TERMINAL, config.EQUITI_SYMBOL)
    ]:
        print(f"\n  --- {broker} ---")
        clicker = MT5Clicker(broker, terminal, symbol)
        
        # Test connection
        connected = clicker.connect()
        print_result(f"{broker} Clicker Connect", connected,
                    clicker._window_title if connected else "Window not found")
        
        if not connected:
            results[broker] = None
            continue
        
        # Test coordinate auto-detection
        cached = clicker.cache_coordinates()
        print_result(f"{broker} Coordinate Cache", cached)
        
        if cached:
            print(f"    Buy coords:    {clicker._buy_coords}")
            print(f"    Sell coords:   {clicker._sell_coords}")
            print(f"    Volume coords: {clicker._volume_coords}")
            print(f"    Source:         {clicker._get_coord_source()}")
        
        # Check for dashboard coordinates
        buy_x = getattr(config, f'{broker}_BUY_X', 0)
        buy_y = getattr(config, f'{broker}_BUY_Y', 0)
        sell_x = getattr(config, f'{broker}_SELL_X', 0)
        sell_y = getattr(config, f'{broker}_SELL_Y', 0)
        
        has_dashboard = buy_x > 0 and sell_x > 0
        print_result(f"{broker} Dashboard Coords", has_dashboard,
                    f"Buy=({buy_x},{buy_y}), Sell=({sell_x},{sell_y})" if has_dashboard 
                    else "Not set — calibrate in Dashboard Settings")
        
        status = clicker.get_status()
        results[broker] = clicker
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4: Lot Size Typing Test
# ═══════════════════════════════════════════════════════════════════════════════
def test_lot_size_typing(clickers):
    print_header("PHASE 4: Lot Size Typing Test")
    print("  This will TYPE a lot size into the MT5 volume field.")
    print("  It does NOT open any trades — it just types a number.")
    
    if not ask_continue("Type lot size into MT5 volume fields?"):
        print("  Skipped.")
        return
    
    test_volume = 0.01  # Smallest possible lot
    
    for broker, clicker in clickers.items():
        if clicker is None or not clicker.has_coordinates():
            print(f"\n  ⚠️  {broker}: Skipped (no coordinates)")
            continue
        
        print(f"\n  Testing {broker}...")
        success = clicker.set_lot_size(test_volume)
        print_result(f"{broker} Set Lot Size", success, 
                    f"Typed {test_volume:.2f}" if success else "Failed to type")
        
        if success:
            print(f"    → Check the {broker} MT5 terminal — volume should show {test_volume:.2f}")
        
        time.sleep(1)  # Pause between terminals


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 5: LIVE CLICK TEST (⚠️ OPENS REAL TRADES!)
# ═══════════════════════════════════════════════════════════════════════════════
def test_live_click(clickers):
    print_header("PHASE 5: LIVE CLICK TEST ⚠️")
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║  WARNING: This will CLICK Buy/Sell on your MT5 terminal ║")
    print("  ║  This OPENS A REAL TRADE with real money!               ║")
    print("  ║  Use the SMALLEST lot size (0.01) for testing.          ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    
    # Pick which broker to test
    available = [b for b, c in clickers.items() if c and c.has_coordinates()]
    if not available:
        print("  ❌ No brokers with coordinates available. Run calibration first.")
        return
    
    print(f"\n  Available brokers: {', '.join(available)}")
    broker_choice = input(f"  Which broker to test? ({'/'.join(available)}): ").strip().upper()
    
    if broker_choice not in available:
        print("  Invalid choice. Skipped.")
        return
    
    clicker = clickers[broker_choice]
    
    # Confirm trade direction
    direction = input("  Trade direction (BUY/SELL): ").strip().upper()
    if direction not in ("BUY", "SELL"):
        print("  Invalid direction. Skipped.")
        return
    
    volume = 0.01
    print(f"\n  About to {direction} {volume} lots on {broker_choice}")
    print(f"  Coordinates: {'Buy' if direction == 'BUY' else 'Sell'} = "
          f"{clicker._buy_coords if direction == 'BUY' else clicker._sell_coords}")
    
    if not ask_continue(f"EXECUTE {direction} CLICK on {broker_choice}? (THIS IS REAL!)"):
        print("  Cancelled.")
        return
    
    # Set lot size first
    print(f"\n  Step 1: Setting lot size to {volume}...")
    clicker.set_lot_size(volume)
    time.sleep(0.5)
    
    # Execute the click
    print(f"  Step 2: Clicking {direction}...")
    start = time.time()
    result = clicker.execute_click_trade(direction, volume)
    elapsed = (time.time() - start) * 1000
    
    print_result(f"{broker_choice} {direction} Click", result["success"],
                f"Time: {result.get('time_ms', 0):.1f}ms, Total: {elapsed:.1f}ms")
    
    if result["success"]:
        print(f"\n  ✅ Click executed successfully!")
        print(f"     Method: {result.get('method', 'unknown')}")
        print(f"     Coords: {result.get('coords', 'unknown')}")
        print(f"\n  NOW CHECK YOUR MT5 TERMINAL:")
        print(f"  → A new {direction} position should appear in the Trade tab")
        print(f"  → Close it manually if this was just a test")
    else:
        print(f"\n  ❌ Click failed: {result.get('error', 'unknown')}")
        print(f"     Troubleshooting:")
        print(f"     1. Is the MT5 window visible and not minimized?")
        print(f"     2. Is One-Click Trading enabled? (Alt+T)")
        print(f"     3. Are the coordinates correct?")
        print(f"     4. Is there a dialog or popup blocking the button?")


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 6: Full Verification (Click + API Verification)
# ═══════════════════════════════════════════════════════════════════════════════
def test_full_verification(clickers):
    print_header("PHASE 6: Full Click + API Verification ⚠️")
    print("  This simulates what the bot does:")
    print("  1. Click Buy/Sell (clicker)")
    print("  2. Verify trade via API (mt5.positions_get)")
    print("  3. Get fill price from deal history")
    print("  4. Close the trade via API (mt5.order_send)")
    
    available = [b for b, c in clickers.items() if c and c.has_coordinates()]
    if not available:
        print("  ❌ No brokers available.")
        return
    
    print(f"\n  Available: {', '.join(available)}")
    broker_choice = input(f"  Which broker? ({'/'.join(available)}): ").strip().upper()
    
    if broker_choice not in available:
        print("  Invalid. Skipped.")
        return
    
    if not ask_continue(f"RUN FULL TEST on {broker_choice}? (Opens AND closes a 0.01 trade)"):
        print("  Cancelled.")
        return
    
    import MetaTrader5 as mt5
    import config
    
    clicker = clickers[broker_choice]
    terminal = config.HFM_TERMINAL if broker_choice == "HFM" else config.EQUITI_TERMINAL
    symbol = config.HFM_SYMBOL if broker_choice == "HFM" else config.EQUITI_SYMBOL
    
    # Initialize MT5 API
    print(f"\n  Connecting to MT5 API for {broker_choice}...")
    if not mt5.initialize(path=terminal, portable=True):
        print_result("MT5 API Connect", False, str(mt5.last_error()))
        return
    
    # Get positions before
    positions_before = mt5.positions_get(symbol=symbol)
    tickets_before = set(p.ticket for p in positions_before) if positions_before else set()
    print(f"  Positions before: {len(tickets_before)}")
    
    # Set lot size
    volume = 0.01
    clicker.set_lot_size(volume)
    time.sleep(0.3)
    
    # Click BUY
    print(f"\n  CLICKING BUY...")
    click_start = time.time()
    click_result = clicker.execute_click_trade("BUY", volume)
    click_ms = (time.time() - click_start) * 1000
    
    print_result("Click BUY", click_result["success"],
                f"Click time: {click_result.get('time_ms', 0):.1f}ms")
    
    if not click_result["success"]:
        print(f"  ❌ Click failed. Aborting test.")
        mt5.shutdown()
        return
    
    # Verify via API
    print(f"\n  Verifying via API...")
    new_position = None
    for attempt in range(15):
        time.sleep(0.15)
        positions_after = mt5.positions_get(symbol=symbol)
        if positions_after:
            for pos in positions_after:
                if pos.ticket not in tickets_before:
                    new_position = pos
                    break
        if new_position:
            break
        print(f"    Attempt {attempt+1}/15...")
    
    if new_position:
        print_result("API Verification", True,
                    f"Ticket: {new_position.ticket}, Price: {new_position.price_open}, "
                    f"Volume: {new_position.volume}")
        
        # Get deal history
        time.sleep(0.1)
        deals = mt5.history_deals_get(position=new_position.ticket)
        if deals:
            for deal in deals:
                if deal.entry == 0:
                    print_result("Deal History", True,
                               f"Deal price: {deal.price}, Commission: {deal.commission}")
        
        # Close via API
        print(f"\n  Closing trade via API...")
        symbol_info = mt5.symbol_info(symbol)
        filling = mt5.ORDER_FILLING_FOK
        if symbol_info:
            fill_mode = symbol_info.filling_mode
            if fill_mode & 1:
                filling = mt5.ORDER_FILLING_FOK
            elif fill_mode & 2:
                filling = mt5.ORDER_FILLING_IOC
        
        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": new_position.volume,
            "type": mt5.ORDER_TYPE_SELL,  # Opposite of BUY
            "position": new_position.ticket,
            "price": mt5.symbol_info_tick(symbol).bid,
            "slippage": 10,
            "magic": 0,
            "comment": "",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        
        close_result = mt5.order_send(close_request)
        if close_result and close_result.retcode == mt5.TRADE_RETCODE_DONE:
            # Get close price from deal history
            time.sleep(0.1)
            close_price = close_result.price
            if hasattr(close_result, 'deal') and close_result.deal > 0:
                close_deals = mt5.history_deals_get(ticket=close_result.deal)
                if close_deals:
                    close_price = close_deals[0].price
            
            print_result("API Close", True,
                        f"Close price: {close_price}, "
                        f"P&L: {close_result.profit if hasattr(close_result, 'profit') else 'N/A'}")
        else:
            error = close_result.comment if close_result else "None returned"
            print_result("API Close", False, f"Error: {error}")
    else:
        print_result("API Verification", False, "No new position found after 15 attempts")
    
    total_ms = (time.time() - click_start) * 1000
    print(f"\n  Total test time: {total_ms:.0f}ms")
    
    mt5.shutdown()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("\n" + "═"*70)
    print("  HEDGED LOCK BOT — CLICKER MODE LIVE TEST")
    print("  Tests each component step by step.")
    print("  You'll be prompted before any action that touches real money.")
    print("═"*70)
    
    # Phase 1: MT5 API
    api_ok, hfm_info, eq_info = test_mt5_connection()
    if not api_ok:
        print("\n  ⚠️  MT5 API connection failed. Fix this before continuing.")
        if not ask_continue("Continue anyway?"):
            return
    
    # Phase 2: Window Detection
    windows_ok = test_window_detection()
    if not windows_ok:
        print("\n  ⚠️  Could not find 2 MT5 windows.")
        if not ask_continue("Continue anyway?"):
            return
    
    # Phase 3: Clicker Connection
    clickers = test_clicker_connection()
    any_connected = any(c is not None for c in clickers.values())
    if not any_connected:
        print("\n  ❌ No clickers connected. Cannot proceed with click tests.")
        return
    
    any_coords = any(c is not None and c.has_coordinates() for c in clickers.values())
    if not any_coords:
        print("\n  ⚠️  No coordinates found on any terminal.")
        print("     → Set coordinates in Dashboard Settings first")
        print("     → Or ensure One-Click Trading panel is visible (Alt+T)")
        if not ask_continue("Continue to lot size test?"):
            return
    
    # Phase 4: Lot Size Typing
    test_lot_size_typing(clickers)
    
    # Phase 5: Live Click
    if ask_continue("\nProceed to LIVE CLICK TEST? (Opens a real trade)"):
        test_live_click(clickers)
    
    # Phase 6: Full Verification
    if ask_continue("\nProceed to FULL VERIFICATION TEST? (Opens and closes a trade)"):
        test_full_verification(clickers)
    
    # Summary
    print_header("TEST COMPLETE")
    print("  If all phases passed, your clicker setup is ready!")
    print("  Start the bot from the Dashboard to begin live trading.")
    print()
    
    # Cleanup
    for c in clickers.values():
        if c:
            c.close()


if __name__ == "__main__":
    main()
