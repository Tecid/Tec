"""
MT5 Worker Process
Handles connection to a single MT5 terminal and executes trading commands.

EXECUTION MODEL (Full Stealth — Clicker Mode):
  - OPENING trades: GUI clicker (win32api raw mouse injection)
  - CLOSING trades: GUI clicker (click Close X button) with API fallback
  - DATA reads: Always uses API (mt5.symbol_info_tick, positions_get — invisible to broker)

Both open and close appear 100% manual in broker logs.
If Close X coordinates are not set, closing falls back to API automatically.
"""

import MetaTrader5 as mt5

import time
from multiprocessing import Process
from enum import Enum


class Command(Enum):
    """Commands that can be sent to the worker."""
    GET_TICK = "GET_TICK"
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"
    GET_POSITION = "GET_POSITION"
    GET_BALANCE = "GET_BALANCE"
    MAINTAIN_LOT = "MAINTAIN_LOT"
    SHUTDOWN = "SHUTDOWN"


def initialize_terminal(broker_name: str, terminal_path: str) -> bool:
    """
    Initialize MT5 terminal connection.
    MT5 API is used for read-only data access and closing trades.
    """
    print(f"[{broker_name}] Initializing MT5 terminal: {terminal_path}")
    
    if not mt5.initialize(path=terminal_path, portable=True):
        error = mt5.last_error()
        print(f"[{broker_name}] Failed to initialize: {error}")
        return False
    
    # Verify connection
    account_info = mt5.account_info()
    if account_info is None:
        print(f"[{broker_name}] Failed to get account info")
        mt5.shutdown()
        return False
    
    print(f"[{broker_name}] Connected to account: {account_info.login}")
    print(f"[{broker_name}] Balance: ${account_info.balance:.2f}")
    return True


def _reconnect_mt5(broker_name: str, terminal_path: str, data_pipe, command_pipe) -> bool:
    """Reconnect to MT5 terminal indefinitely with exponential backoff.
    
    Called when connection loss is detected (consecutive None ticks).
    Sends CONNECTION_LOST on first call, RECONNECTED on success.
    Drains command pipe during reconnect (honors SHUTDOWN).
    Returns False only if SHUTDOWN was received during reconnect.
    """
    data_pipe.send({"type": "CONNECTION_LOST", "broker": broker_name})
    print(f"[{broker_name}] *** CONNECTION LOST *** Starting reconnection...")
    
    # Shutdown existing connection
    try:
        mt5.shutdown()
    except:
        pass
    
    backoff = 2  # Start at 2 seconds
    max_backoff = 30  # Cap at 30 seconds
    attempt = 0
    
    while True:
        attempt += 1
        
        # Drain command pipe — honor SHUTDOWN, discard others
        while command_pipe.poll(0):
            try:
                cmd = command_pipe.recv()
                if cmd.get("action") == Command.SHUTDOWN.value:
                    print(f"[{broker_name}] SHUTDOWN received during reconnect")
                    return False
            except:
                pass
        
        print(f"[{broker_name}] Reconnect attempt #{attempt} (backoff: {backoff}s)...")
        
        try:
            if mt5.initialize(path=terminal_path, portable=True):
                account_info = mt5.account_info()
                if account_info is not None:
                    balance = account_info.balance
                    print(f"[{broker_name}] *** RECONNECTED *** Account: {account_info.login}, Balance: ${balance:.2f}")
                    data_pipe.send({
                        "type": "RECONNECTED",
                        "broker": broker_name,
                        "balance": balance
                    })
                    return True
                else:
                    print(f"[{broker_name}] MT5 initialized but account_info is None")
                    mt5.shutdown()
            else:
                error = mt5.last_error()
                print(f"[{broker_name}] Initialize failed: {error}")
        except Exception as e:
            print(f"[{broker_name}] Reconnect error: {e}")
        
        # Wait with backoff (check for SHUTDOWN during wait)
        wait_end = time.time() + backoff
        while time.time() < wait_end:
            if command_pipe.poll(0.5):
                try:
                    cmd = command_pipe.recv()
                    if cmd.get("action") == Command.SHUTDOWN.value:
                        print(f"[{broker_name}] SHUTDOWN received during reconnect wait")
                        return False
                except:
                    pass
        
        # Exponential backoff: 2 → 4 → 8 → 16 → 30 (capped)
        backoff = min(backoff * 2, max_backoff)


def get_tick_data(symbol: str) -> dict | None:
    """
    Fetch latest tick data for a symbol.
    (Read-only API — invisible to broker)
    """
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        if mt5.symbol_select(symbol, True):
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
        else:
            return None
    
    return {
        "bid": tick.bid,
        "ask": tick.ask,
        "time": tick.time,
        "last": tick.last,
        "volume": tick.volume
    }


def get_avg_tick_volume(symbol: str, window_seconds: int) -> dict | None:
    """
    Calculate average tick volume per minute over a rolling time window.
    
    Uses M1 (1-minute) bars from MT5 for efficiency — even a 1-hour window
    only needs 60 bars instead of potentially millions of raw ticks.
    
    Args:
        symbol: Trading symbol (e.g., 'EURUSD')
        window_seconds: Lookback window in seconds (e.g., 200)
    
    Returns:
        Dict with avg_tick_vol, total_ticks, bars_used, window_seconds
        or None if data is unavailable.
    """
    import math
    bars_needed = max(1, math.ceil(window_seconds / 60))
    
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, bars_needed)
    if rates is None or len(rates) == 0:
        return None
    
    total_ticks = 0
    bars_used = 0
    for rate in rates:
        total_ticks += int(rate['tick_volume'])
        bars_used += 1
    
    avg_per_min = round(total_ticks / bars_used, 1) if bars_used > 0 else 0
    
    return {
        "avg_tick_vol": avg_per_min,
        "total_ticks": total_ticks,
        "bars_used": bars_used,
        "window_seconds": window_seconds
    }


def execute_trade_click(symbol: str, order_type: str, volume: float,
                        broker_name: str, clicker,
                        entry_id: str | None = None,
                        decision_ts_ms: int | None = None) -> dict:
    """
    Execute a market order by clicking Buy/Sell on the MT5 One-Click panel.
    
    Flow:
      1. Snapshot current positions (to detect new one)
      2. Click Buy/Sell via win32api (~6ms)
      3. Verify trade via MT5 API (read-only)
      4. Get actual fill price from deal history
    
    Returns:
        Dict with success, ticket, price, volume
    """
    if clicker is None:
        return {"success": False, "error": "MT5 Clicker not initialized"}
    
    recv_ts_ms = int(time.time() * 1000)
    
    # Step 1: Snapshot positions BEFORE click
    positions_before = mt5.positions_get(symbol=symbol)
    tickets_before = set()
    if positions_before:
        tickets_before = {p.ticket for p in positions_before}
    
    # Step 2: Execute the click (ultra-fast — ~6ms with win32api)
    print(f"[{broker_name}] ⚡ CLICKER: Clicking {order_type} for {volume} lots...")
    click_result = clicker.execute_click_trade(order_type, volume)
    
    if not click_result["success"]:
        return {
            "success": False,
            "error": f"Click failed: {click_result.get('error', 'unknown')}"
        }
    
    click_time = click_result.get("time_ms", 0)
    print(f"[{broker_name}] ⚡ Click executed in {click_time}ms ({click_result.get('method', 'unknown')})")
    
    # Step 3: Verify — wait for MT5 to process, then find new position
    verification_delay = 0.15  # 150ms initial wait (MT5 server processing)
    max_verification_attempts = 15
    verification_interval = 0.1  # 100ms between retries
    
    time.sleep(verification_delay)
    
    new_position = None
    for attempt in range(max_verification_attempts):
        positions_after = mt5.positions_get(symbol=symbol)
        if positions_after:
            for pos in positions_after:
                if pos.ticket not in tickets_before:
                    expected_type = mt5.POSITION_TYPE_BUY if order_type == "BUY" else mt5.POSITION_TYPE_SELL
                    if pos.type == expected_type:
                        new_position = pos
                        break
        
        if new_position:
            break
        
        if attempt < max_verification_attempts - 1:
            time.sleep(verification_interval)
            if attempt > 2:  # Only log after initial attempts
                print(f"[{broker_name}] CLICKER: Waiting for position... (attempt {attempt + 2}/{max_verification_attempts})")
    
    if new_position is None:
        print(f"[{broker_name}] CLICKER: *** WARNING *** Click executed but no new position detected!")
        return {
            "success": False,
            "error": "Click executed but no new position detected after verification"
        }
    
    # Step 4: Get actual price from deal history
    actual_price = new_position.price_open
    price_source = "position"
    
    time.sleep(0.05)
    deals = mt5.history_deals_get(position=new_position.ticket)
    if deals and len(deals) > 0:
        for deal in deals:
            if deal.entry == 0:  # Entry deal
                actual_price = deal.price
                price_source = "deal_history"
                break
    
    elapsed_ms = int(time.time() * 1000) - recv_ts_ms
    print(f"[{broker_name}] ✅ Trade confirmed! Ticket: {new_position.ticket}, "
          f"Price: {actual_price} (source: {price_source}), Total: {elapsed_ms}ms (click: {click_time}ms)")
    
    return {
        "success": True,
        "ticket": new_position.ticket,
        "price": actual_price,
        "volume": new_position.volume
    }


def get_filling_mode(symbol_info):
    """Detect the correct filling mode for a symbol."""
    filling = symbol_info.filling_mode
    if filling & 1:
        return mt5.ORDER_FILLING_FOK
    elif filling & 2:
        return mt5.ORDER_FILLING_IOC
    else:
        return mt5.ORDER_FILLING_RETURN


def close_position(ticket: int, symbol: str) -> dict:
    """
    Close a specific position by ticket using API.
    (API close is kept — fast, reliable, and low detection risk)
    """
    position = None
    
    for attempt in range(3):
        position = mt5.positions_get(ticket=ticket)
        if position and len(position) > 0:
            break
        all_positions = mt5.positions_get(symbol=symbol)
        if all_positions and len(all_positions) > 0:
            position = [all_positions[0]]
            print(f"[WORKER] Position {ticket} not found by ticket, using symbol lookup (found {all_positions[0].ticket})")
            break
        if attempt < 2:
            time.sleep(0.1)
    
    if position is None or len(position) == 0:
        try:
            from datetime import datetime, timedelta
            history_deals = mt5.history_deals_get(
                datetime.now() - timedelta(days=1),
                datetime.now()
            )
            if history_deals:
                for deal in history_deals:
                    if deal.position_id == ticket and deal.entry == 1:
                        print(f"[WORKER] Position {ticket} found in history - already closed at {deal.price}")
                        return {
                            "success": True,
                            "close_price": deal.price,
                            "realized_profit": deal.profit,
                            "already_closed": True
                        }
        except Exception as e:
            print(f"[WORKER] History check failed: {e}")
        
        return {"success": False, "error": f"Position {ticket} not found after 3 attempts"}
    
    position = position[0]
    
    symbol_info = mt5.symbol_info(symbol)
    filling_mode = get_filling_mode(symbol_info) if symbol_info else mt5.ORDER_FILLING_FOK
    
    if position.type == mt5.POSITION_TYPE_BUY:
        trade_type = mt5.ORDER_TYPE_SELL
        price = mt5.symbol_info_tick(symbol).bid
    else:
        trade_type = mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).ask
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": position.volume,
        "type": trade_type,
        "position": position.ticket,
        "price": price,
        "slippage": 10,
        "magic": 0,
        "comment": "",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }
    
    result = mt5.order_send(request)
    
    if result is None:
        return {"success": False, "error": "Close order returned None"}
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {
            "success": False,
            "error": f"Close failed: {result.retcode} - {result.comment}"
        }
    
    # Get actual close price from deal history
    close_price = None
    actual_profit = None
    
    for attempt in range(3):
        time.sleep(0.05)
        
        if hasattr(result, 'deal') and result.deal > 0:
            deals = mt5.history_deals_get(ticket=result.deal)
            if deals and len(deals) > 0:
                close_price = deals[0].price
                actual_profit = deals[0].profit
                break
        
        deals = mt5.history_deals_get(position=position.ticket)
        if deals and len(deals) > 0:
            for deal in reversed(deals):
                if deal.entry == 1:
                    close_price = deal.price
                    actual_profit = deal.profit
                    break
        
        if close_price is not None and close_price != 0:
            break
    
    if close_price is None or close_price == 0:
        close_price = result.price if result.price != 0 else price
        print(f"[WORKER] WARNING: Close price from fallback ({close_price}), deal history lookup failed!")
    
    realized_profit = actual_profit if actual_profit is not None else position.profit
    
    return {
        "success": True,
        "close_price": close_price,
        "realized_profit": realized_profit
    }


def close_position_click(ticket: int, symbol: str, broker_name: str, clicker) -> dict:
    """
    Close a position by clicking the Close X button in MT5's Trades tab.
    
    Flow:
      1. Snapshot current positions (to detect disappearance)
      2. Click Close X via win32api (~2ms)
      3. Verify position is gone via MT5 API polling (read-only)
      4. Get actual close price from deal history
    
    Returns:
        Dict with success, close_price, realized_profit
    """
    if clicker is None:
        return {"success": False, "error": "Clicker not initialized"}
    
    recv_ts_ms = int(time.time() * 1000)
    
    # Step 1: Snapshot — confirm position exists before attempting close
    position = mt5.positions_get(ticket=ticket)
    if not position or len(position) == 0:
        # Position is already gone — it was closed by a previous click
        # Try to get the actual close price from deal history
        close_price = 0
        realized_profit = 0
        try:
            from datetime import datetime, timedelta
            history_deals = mt5.history_deals_get(
                datetime.now() - timedelta(days=1),
                datetime.now()
            )
            if history_deals:
                for deal in history_deals:
                    if deal.position_id == ticket and deal.entry == 1:
                        close_price = deal.price
                        realized_profit = deal.profit
                        break
        except Exception as e:
            print(f"[{broker_name}] History check failed: {e}")
        
        # Fallback price from market tick if deal history didn't have it yet
        if close_price == 0:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                close_price = tick.bid  # Best guess
        
        print(f"[{broker_name}] Position {ticket} already closed at {close_price}")
        return {
            "success": True,
            "close_price": close_price,
            "realized_profit": realized_profit,
            "already_closed": True
        }
    
    pos = position[0]
    original_volume = pos.volume
    original_profit = pos.profit
    
    # Step 2: Click Close X (~2ms with win32api)
    print(f"[{broker_name}] ⚡ CLICKER: Clicking Close X for ticket #{ticket}...")
    click_result = clicker.click_close_position()
    
    if not click_result["success"]:
        return {
            "success": False,
            "error": f"Click-close failed: {click_result.get('error', 'unknown')}"
        }
    
    click_time = click_result.get("time_ms", 0)
    print(f"[{broker_name}] ⚡ Close X clicked in {click_time}ms")
    
    # Step 3: Verify — wait for position to disappear from MT5
    # MT5 takes ~300-500ms to update its position list after a click-close
    verification_delay = 0.10  # 100ms initial wait
    max_verification_attempts = 15
    verification_interval = 0.10  # 100ms between retries (~1600ms total)
    
    time.sleep(verification_delay)
    
    position_gone = False
    for attempt in range(max_verification_attempts):
        check = mt5.positions_get(ticket=ticket)
        if check is None or len(check) == 0:
            position_gone = True
            break
        
        if attempt < max_verification_attempts - 1:
            time.sleep(verification_interval)
            if attempt > 3:
                print(f"[{broker_name}] CLICKER: Waiting for close... (attempt {attempt + 1}/{max_verification_attempts})")
    
    if not position_gone:
        print(f"[{broker_name}] CLICKER: Close X clicked but position still open!")
        return {
            "success": False,
            "error": "Close X clicked but position still open after verification"
        }
    
    # Step 4: Get actual close price from deal history
    close_price = None
    actual_profit = None
    
    time.sleep(0.05)  # 50ms for deal history to settle
    
    for attempt in range(3):
        deals = mt5.history_deals_get(position=ticket)
        if deals and len(deals) > 0:
            for deal in reversed(deals):
                if deal.entry == 1:  # Exit deal
                    close_price = deal.price
                    actual_profit = deal.profit
                    break
        
        if close_price is not None and close_price != 0:
            break
        
        if attempt < 2:
            time.sleep(0.05)
    
    if close_price is None or close_price == 0:
        # Fallback: use last known price
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            close_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        else:
            close_price = 0
        print(f"[{broker_name}] WARNING: Close price from fallback ({close_price})")
    
    realized_profit = actual_profit if actual_profit is not None else original_profit
    
    elapsed_ms = int(time.time() * 1000) - recv_ts_ms
    print(f"[{broker_name}] ✅ Close confirmed! Ticket: #{ticket}, "
          f"Price: {close_price}, P/L: {realized_profit:.2f}, Total: {elapsed_ms}ms (click: {click_time}ms)")
    
    return {
        "success": True,
        "close_price": close_price,
        "realized_profit": realized_profit
    }


def get_position_pnl(ticket: int) -> dict | None:
    """
    Get position PnL including commission and swap.
    (Read-only API — invisible to broker)
    """
    position = mt5.positions_get(ticket=ticket)
    if position is None or len(position) == 0:
        return None
    
    pos = position[0]
    
    gross_profit = pos.profit
    commission = abs(pos.commission) if hasattr(pos, 'commission') else 0
    swap = pos.swap if hasattr(pos, 'swap') else 0
    net_profit = gross_profit - commission + swap
    
    return {
        "ticket": ticket,
        "gross_profit": gross_profit,
        "commission": commission,
        "swap": swap,
        "net_profit": net_profit,
        "volume": pos.volume,
        "type": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
        "open_price": pos.price_open,
        "current_price": pos.price_current
    }


def run_worker(broker_name: str, terminal_path: str,
               command_pipe, data_pipe, config: dict):
    """
    Main worker loop - handles commands from master.
    
    EXECUTION MODEL (Full Stealth):
      - BUY/SELL: GUI clicker (win32api raw mouse injection)
      - CLOSE: GUI clicker (Close X button) with API fallback
      - Data reads: Always uses API (invisible to broker)
    
    The clicker is initialized with coordinates from the dashboard config.
    If dashboard coordinates are available, they take priority over auto-detection.
    """
    print(f"[{broker_name}] Worker starting...")
    print(f"[{broker_name}] Trade execution mode: FULL STEALTH (open + close via clicker)")
    
    # Initialize MT5 terminal (needed for data reads + closing)
    if not initialize_terminal(broker_name, terminal_path):
        data_pipe.send({"type": "ERROR", "error": "Failed to initialize"})
        return
    
    # Initialize MT5 Clicker (for opening trades)
    clicker = None
    clicker_ready = False
    
    try:
        from mt5_clicker import MT5Clicker
        symbol = config.get("symbol", "EURUSD")
        clicker = MT5Clicker(broker_name, terminal_path, symbol, input_method=config.get("input_method", "legacy"))
        
        # Step 1: Try to find MT5 window (optional — not needed when dashboard coords are set)
        if clicker.connect():
            print(f"[{broker_name}] ✅ MT5 Clicker connected — GUI click mode active")
        else:
            print(f"[{broker_name}] ⚠️ MT5 window not found (will use dashboard coordinates if set)")
        
        # Step 2: Always load dashboard coordinates (works even without window handle)
        buy_x = config.get("clicker_buy_x", 0)
        buy_y = config.get("clicker_buy_y", 0)
        sell_x = config.get("clicker_sell_x", 0)
        sell_y = config.get("clicker_sell_y", 0)
        vol_x = config.get("clicker_volume_x", 0)
        vol_y = config.get("clicker_volume_y", 0)
        close_x_x = config.get("clicker_close_x_x", 0)
        close_x_y = config.get("clicker_close_x_y", 0)
        
        if buy_x > 0 and sell_x > 0:
            clicker.set_dashboard_coordinates(buy_x, buy_y, sell_x, sell_y, vol_x, vol_y, close_x_x, close_x_y)
            print(f"[{broker_name}] 📍 Dashboard coordinates loaded")
        
        # Step 3: Cache coordinates (dashboard coords bypass connect requirement)
        if clicker.cache_coordinates():
            clicker_ready = True
            print(f"[{broker_name}] ⚡ Clicker READY — coordinates cached")
        else:
            print(f"[{broker_name}] ⚠️ Could not cache coordinates — set them in Dashboard Settings")
            
    except ImportError:
        print(f"[{broker_name}] ⚠️ pywin32 not installed — clicker unavailable")
        print(f"[{broker_name}] Run: pip install pywin32")
    except Exception as e:
        print(f"[{broker_name}] ⚠️ Clicker init error: {e}")
    
    # Get account balance
    account_info = mt5.account_info()
    balance = account_info.balance if account_info else 0
    
    data_pipe.send({
        "type": "READY",
        "broker": broker_name,
        "balance": balance,
        "clicker_ready": clicker_ready
    })
    
    symbol = config.get("symbol", "EURUSD")
    running = True
    null_tick_count = 0  # Track consecutive None ticks for connection loss detection
    NULL_TICK_THRESHOLD = 50  # ~50ms at 1ms loop = trigger reconnect after 50ms of no ticks
    
    # Tick volume periodic calculation
    tick_vol_interval = config.get("tick_volume_interval", 200)  # how often to check (seconds)
    tick_vol_lookback = config.get("tick_volume_lookback", 100)  # how far back to read (seconds)
    last_tick_vol_time = time.time()  # Start from bot start — first calc after interval elapses
    
    while running:
        try:
            if command_pipe.poll(0.01):  # 10ms timeout
                cmd = command_pipe.recv()
                
                if cmd["action"] == Command.SHUTDOWN.value:
                    print(f"[{broker_name}] Shutdown received")
                    running = False
                    continue
                
                elif cmd["action"] == Command.BUY.value:
                    entry_id = cmd.get("entry_id")
                    decision_ts_ms = cmd.get("decision_ts_ms")
                    volume = cmd.get("volume", config.get("lot_size", 0.01))
                    
                    if clicker is not None and clicker_ready:
                        result = execute_trade_click(
                            symbol=symbol,
                            order_type="BUY",
                            volume=volume,
                            broker_name=broker_name,
                            clicker=clicker,
                            entry_id=entry_id,
                            decision_ts_ms=decision_ts_ms
                        )
                    else:
                        result = {
                            "success": False,
                            "error": "Clicker not ready — set button coordinates in Dashboard Settings"
                        }
                    data_pipe.send({"type": "TRADE_RESULT", "result": result})
                
                elif cmd["action"] == Command.SELL.value:
                    entry_id = cmd.get("entry_id")
                    decision_ts_ms = cmd.get("decision_ts_ms")
                    volume = cmd.get("volume", config.get("lot_size", 0.01))
                    
                    if clicker is not None and clicker_ready:
                        result = execute_trade_click(
                            symbol=symbol,
                            order_type="SELL",
                            volume=volume,
                            broker_name=broker_name,
                            clicker=clicker,
                            entry_id=entry_id,
                            decision_ts_ms=decision_ts_ms
                        )
                    else:
                        result = {
                            "success": False,
                            "error": "Clicker not ready — set button coordinates in Dashboard Settings"
                        }
                    data_pipe.send({"type": "TRADE_RESULT", "result": result})
                
                elif cmd["action"] == Command.CLOSE.value:
                    # CLICK-ONLY CLOSE: No API fallback
                    if clicker and clicker_ready and clicker._close_x_coords:
                        result = close_position_click(
                            ticket=cmd["ticket"],
                            symbol=symbol,
                            broker_name=broker_name,
                            clicker=clicker
                        )
                    else:
                        result = {
                            "success": False,
                            "error": "No Close X coordinates — set them in Dashboard Settings"
                        }
                    data_pipe.send({"type": "CLOSE_RESULT", "result": result})
                
                elif cmd["action"] == Command.GET_POSITION.value:
                    pnl = get_position_pnl(cmd["ticket"])
                    data_pipe.send({"type": "POSITION_PNL", "data": pnl})
                
                elif cmd["action"] == Command.GET_BALANCE.value:
                    account_info = mt5.account_info()
                    balance = account_info.balance if account_info else 0
                    data_pipe.send({"type": "BALANCE", "balance": balance})
                
                elif cmd["action"] == "CHECK_ORPHANS":
                    positions = mt5.positions_get(symbol=symbol)
                    orphan_tickets = []
                    if positions:
                        for pos in positions:
                            orphan_tickets.append(pos.ticket)
                            print(f"[{broker_name}] Found orphan position: #{pos.ticket} ({symbol})")
                    data_pipe.send({"type": "ORPHAN_POSITIONS", "tickets": orphan_tickets})
                
                elif cmd["action"] == Command.MAINTAIN_LOT.value:
                    # Lot sync from master — uses maintain_lot_size to skip if already correct
                    if clicker and clicker_ready:
                        new_lot = cmd.get("volume", 0.01)
                        print(f"[{broker_name}] ⚡ Lot sync request: {new_lot} (current: {clicker._current_lot_size})")
                        clicker.maintain_lot_size(new_lot)
                        config["lot_size"] = new_lot
                    # ALWAYS confirm back — master is waiting for this before proceeding
                    data_pipe.send({"type": "LOT_SYNC_DONE", "broker": broker_name})
            
            # Periodic tick volume calculation (every tick_vol_interval seconds)
            # Placed BEFORE tick data so it always runs even when continue skips later code
            now_tv = time.time()
            if now_tv - last_tick_vol_time >= tick_vol_interval:
                last_tick_vol_time = now_tv
                tick_vol_data = get_avg_tick_volume(symbol, tick_vol_lookback)
                if tick_vol_data:
                    tick_vol_data["interval_seconds"] = tick_vol_interval
                    data_pipe.send({
                        "type": "TICK_VOLUME",
                        "broker": broker_name,
                        "data": tick_vol_data
                    })
            
            # Always send tick data (read-only API — invisible to broker)
            tick = get_tick_data(symbol)
            if tick:
                null_tick_count = 0  # Reset on good tick
                data_pipe.send({
                    "type": "TICK",
                    "broker": broker_name,
                    "data": tick
                })
            else:
                null_tick_count += 1
                if null_tick_count >= NULL_TICK_THRESHOLD:
                    # Before reconnecting, check if MT5 API is still alive
                    # (market close/weekend = no ticks but connection is fine)
                    try:
                        account_check = mt5.account_info()
                        if account_check is not None:
                            # Connection alive — market is just closed, no ticks expected
                            null_tick_count = 0  # Reset to avoid re-triggering every 50ms
                            continue
                    except:
                        pass
                    
                    # Connection truly lost — attempt reconnection
                    print(f"[{broker_name}] {null_tick_count} consecutive null ticks + account_info failed — connection lost")
                    if not _reconnect_mt5(broker_name, terminal_path, data_pipe, command_pipe):
                        # SHUTDOWN received during reconnect
                        running = False
                        continue
                    # Reconnected — reset counter and re-select symbol
                    null_tick_count = 0
                    mt5.symbol_select(symbol, True)
                    
                    # Re-init clicker window handle (MT5 may have restarted with new HWND)
                    if clicker:
                        try:
                            if clicker.connect():
                                print(f"[{broker_name}] ✅ Clicker re-connected after MT5 reconnect")
                            else:
                                print(f"[{broker_name}] ⚠️ Clicker reconnect failed — dashboard coordinates still active")
                        except Exception as e:
                            print(f"[{broker_name}] ⚠️ Clicker reconnect error: {e}")
            
            time.sleep(0.001)  # 1ms loop delay (was 10ms — 5x faster reaction)
            
            # Lot size syncing is handled by master's _sync_lot_to_terminals() via MAINTAIN_LOT command
            # (removed idle maintain_lot_size loop that was causing repeated field corruption)
        except EOFError:
            # Pipe closed — master process died
            print(f"[{broker_name}] Command pipe closed — master process died, shutting down")
            running = False
        except BrokenPipeError:
            print(f"[{broker_name}] Broken pipe — master process died, shutting down")
            running = False
        except Exception as e:
            print(f"[{broker_name}] Error: {e}")
            data_pipe.send({"type": "ERROR", "error": str(e)})
    
    # Cleanup
    if clicker:
        clicker.close()
        print(f"[{broker_name}] MT5 Clicker closed")
    print(f"[{broker_name}] Shutting down MT5...")
    mt5.shutdown()
    print(f"[{broker_name}] Worker stopped")

def create_worker_process(broker_name: str, terminal_path: str,
                         command_pipe, data_pipe, config: dict) -> Process:
    """Factory function to create a worker process."""
    return Process(
        target=run_worker,
        args=(broker_name, terminal_path, command_pipe, data_pipe, config),
        name=f"Worker-{broker_name}"
    )
