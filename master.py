"""
MT5 Hedged Lock Arbitrage Bot - Master Orchestrator
Main entry point that coordinates worker processes and executes the strategy.
"""

import multiprocessing
multiprocessing.freeze_support()  # Required for PyInstaller on Windows

import time
import random
from multiprocessing import Pipe

import config
from worker import create_worker_process, Command
from states import State, OpportunityType
from strategy import (
    check_spread_filter, calculate_gaps, check_entry_trigger,
    get_trade_actions, calculate_reversal_gap, calculate_net_pnl,
    check_exit_conditions
)
from display import (
    print_banner, print_scanning, print_spread_filter, print_cooldown,
    print_opportunity, print_holding, print_exit, print_trade_result,
    print_close_result, print_cycle_complete
)




class HedgedLockBot:
    """Main bot orchestrator implementing the Hedged Lock strategy."""
    
    def __init__(self):
        self.state = State.INITIALIZING
        self.running = True
        self.paused = False
        
        # Trade delay between cycles
        self.min_trade_delay = 0.0
        self.max_trade_delay = 0.0
        
        # Worker processes and IPC
        self.hfm_process = None
        self.equiti_process = None
        self.hfm_cmd_send = None
        self.hfm_data_recv = None
        self.equiti_cmd_send = None
        self.equiti_data_recv = None
        
        # Price data
        self.hfm_tick = None
        self.equiti_tick = None
        
        # Trade state
        self.hfm_ticket = None
        self.equiti_ticket = None
        self.hfm_entry_price = 0.0
        self.equiti_entry_price = 0.0
        self.hfm_trade_type = None
        self.equiti_trade_type = None
        self.trade_start_time = None
        self.opportunity_type = None
        self.execution_aborted = False  # Flag to ignore late trade results after timeout
        
        # PnL tracking
        self.hfm_pnl = None
        self.equiti_pnl = None
        
        # Tick volume (windowed average)
        self.hfm_tick_volume = None
        self.equiti_tick_volume = None
        
        # Cooldown
        self.last_failure_time = None
        self.cooldown_seconds = getattr(config, 'FAILURE_COOLDOWN', 30)
        self.last_cooldown_print = 0  # Throttle cooldown print to 1/sec
        
        # Callback for persistence
        self.on_trade_update = None
        self.entry_gap_pts = 0
        self.exit_gap_pts = 0
        
        # Lot recovery mode: trade with small fixed lot after bad entry
        self.lot_recovery_mode = False
        self.lot_recovery_remaining = 0
        self.recovery_lot_size = getattr(config, 'RECOVERY_LOT_SIZE', 0.05)
        self.recovery_trade_count = getattr(config, 'RECOVERY_TRADE_COUNT', 2)
        self.shutdown_after_trade = False  # Shutdown if recovery fails
        
        # Opportunity confirmation tracking
        self.pending_opportunity = None
        self.pending_opportunity_time = None
        self.pending_gap = None
        self.opportunity_confirm_delay = getattr(config, 'OPPORTUNITY_CONFIRM_DELAY', 0.1)
        
        # Exit confirmation tracking
        self.pending_exit = False
        self.pending_exit_time = None
        self.pending_exit_reason = None
        self.pending_exit_details = None
        self.exit_confirm_delay = getattr(config, 'EXIT_CONFIRM_DELAY', 0.5)
        
        # Recovery state tracking (for CLOSING_RECOVERY phase)
        self.recovery_hfm_closed = False
        self.recovery_equiti_closed = False
        self.recovery_start_time = None
        self.recovery_hfm_ticket = None
        self.recovery_equiti_ticket = None
        self.recovery_last_retry_time = None
        
        # Lot size configuration
        self.min_lot_size = getattr(config, 'MIN_LOT_SIZE', 0.01)
        self.max_lot_size = getattr(config, 'MAX_LOT_SIZE', 4.8)
        self.lot_per_base = getattr(config, 'LOT_PER_BASE', 0.35)
        self.lot_base_amount = getattr(config, 'LOT_BASE_AMOUNT', 100)
        self.hfm_balance = 0
        self.equiti_balance = 0
        self.calculated_lot = 0.01  # Will be calculated via ratio + range logic
        self._lot_synced_to_terminals = False  # Track if lot has been pre-typed to terminal volume fields
        
        # Connection tracking — workers send CONNECTION_LOST/RECONNECTED messages
        self.hfm_connected = True
        self.equiti_connected = True
        
        # Config - separate symbols per broker for flexibility
        # lot_size and target_profit are shown as range/max for display, but randomized per trade
        self.config = {
            "hfm_symbol": getattr(config, 'HFM_SYMBOL', 'EURUSD'),
            "equiti_symbol": getattr(config, 'EQUITI_SYMBOL', 'EURUSD'),
            "lot_size": 0.01,  # Will be randomized per trade
            "min_lot_size": self.min_lot_size,
            "max_lot_size": self.max_lot_size,
            "magic": config.MAGIC_NUMBER,
            "slippage": config.SLIPPAGE,
            "min_gap": config.MIN_ENTRY_GAP,
            "max_spread": getattr(config, 'MAX_SPREAD', 0.00020),
            "exit_reversal_gap": getattr(config, 'EXIT_REVERSAL_GAP', config.MIN_ENTRY_GAP),
            "min_hold": config.MIN_HOLD_TIME,
            "target_profit": config.TARGET_NET_PROFIT,  # 0 = disabled (use point-based exit)
            "exit_slippage_buffer": getattr(config, 'EXIT_SLIPPAGE_BUFFER', 0.0),
            "execution_timeout": getattr(config, 'EXECUTION_TIMEOUT', 1.0),
            "trade_mode": "CLICK",  # Always CLICK mode
            "tick_volume_interval": getattr(config, 'TICK_VOLUME_INTERVAL', 200),
            "tick_volume_lookback": getattr(config, 'TICK_VOLUME_LOOKBACK', 100),
        }
        
        # Create separate config dicts for each worker with their respective symbol
        # Include per-terminal clicker coordinates from dashboard
        self.hfm_config = {
            **self.config,
            "symbol": self.config["hfm_symbol"],
            "clicker_buy_x": getattr(config, 'HFM_BUY_X', 0),
            "clicker_buy_y": getattr(config, 'HFM_BUY_Y', 0),
            "clicker_sell_x": getattr(config, 'HFM_SELL_X', 0),
            "clicker_sell_y": getattr(config, 'HFM_SELL_Y', 0),
            "clicker_volume_x": getattr(config, 'HFM_VOLUME_X', 0),
            "clicker_volume_y": getattr(config, 'HFM_VOLUME_Y', 0),
            "clicker_close_x_x": getattr(config, 'HFM_CLOSE_X_X', 0),
            "clicker_close_x_y": getattr(config, 'HFM_CLOSE_X_Y', 0),
            "input_method": getattr(config, 'INPUT_METHOD', 'legacy'),
        }
        self.equiti_config = {
            **self.config,
            "symbol": self.config["equiti_symbol"],
            "clicker_buy_x": getattr(config, 'EQUITI_BUY_X', 0),
            "clicker_buy_y": getattr(config, 'EQUITI_BUY_Y', 0),
            "clicker_sell_x": getattr(config, 'EQUITI_SELL_X', 0),
            "clicker_sell_y": getattr(config, 'EQUITI_SELL_Y', 0),
            "clicker_volume_x": getattr(config, 'EQUITI_VOLUME_X', 0),
            "clicker_volume_y": getattr(config, 'EQUITI_VOLUME_Y', 0),
            "clicker_close_x_x": getattr(config, 'EQUITI_CLOSE_X_X', 0),
            "clicker_close_x_y": getattr(config, 'EQUITI_CLOSE_X_Y', 0),
            "input_method": getattr(config, 'INPUT_METHOD', 'legacy'),
        }
    
    def start(self):
        """Initialize and start the bot."""
        print_banner(self.config)
        
        # Create IPC pipes
        hfm_cmd_recv, self.hfm_cmd_send = Pipe(duplex=False)
        self.hfm_data_recv, hfm_data_send = Pipe(duplex=False)
        equiti_cmd_recv, self.equiti_cmd_send = Pipe(duplex=False)
        self.equiti_data_recv, equiti_data_send = Pipe(duplex=False)
        
        # Create worker processes with their respective symbol configs
        self.hfm_process = create_worker_process(
            "HFM", config.HFM_TERMINAL,
            hfm_cmd_recv, hfm_data_send, self.hfm_config
        )
        self.equiti_process = create_worker_process(
            "EQUITI", config.EQUITI_TERMINAL,
            equiti_cmd_recv, equiti_data_send, self.equiti_config
        )
        
        # Start workers
        print("\n[MASTER] Starting worker processes...")
        self.hfm_process.start()
        self.equiti_process.start()
        
        if not self._wait_for_workers():
            self.shutdown()
            return
        
        print("[MASTER] All workers ready. Starting main loop...\n")
        
        # Initial setup before scanning
        self.reload_settings()
        self._calculate_lot_from_balances()
        self.hfm_config["lot_size"] = self.calculated_lot
        self.equiti_config["lot_size"] = self.calculated_lot
        
        # Pre-type lot size into terminals BEFORE entering scanning
        # (this takes ~4s but only runs once at startup, not in the scanning hot path)
        self._sync_lot_to_terminals()
        
        self.state = State.SCANNING
        
        try:
            while self.running:
                self._main_loop()
        except KeyboardInterrupt:
            print("\n[MASTER] Keyboard interrupt received")
        finally:
            self.shutdown()
    
    def _wait_for_workers(self, timeout: float = 45.0) -> bool:
        """Wait for both workers to signal ready and capture balances."""
        start = time.time()
        hfm_ready = equiti_ready = False
        
        while time.time() - start < timeout:
            if self.hfm_data_recv.poll(0.5):
                msg = self.hfm_data_recv.recv()
                if msg.get("type") == "READY":
                    hfm_ready = True
                    self.hfm_balance = msg.get("balance", 0)
                    print(f"[MASTER] HFM worker ready (Balance: ${self.hfm_balance:.2f})")
                elif msg.get("type") == "ERROR":
                    print(f"[MASTER] HFM error: {msg.get('error')}")
                    return False
            
            if self.equiti_data_recv.poll(0.5):
                msg = self.equiti_data_recv.recv()
                if msg.get("type") == "READY":
                    equiti_ready = True
                    self.equiti_balance = msg.get("balance", 0)
                    print(f"[MASTER] EQUITI worker ready (Balance: ${self.equiti_balance:.2f})")
                elif msg.get("type") == "ERROR":
                    print(f"[MASTER] EQUITI error: {msg.get('error')}")
                    return False
            
            if hfm_ready and equiti_ready:
                # Calculate lot using ratio + range logic
                self.calculated_lot = self._ratio_lot_calculation()
                self.config["lot_size"] = self.calculated_lot
                self._lot_synced_to_terminals = False  # Will be synced on first scanning tick
                return True
        
        print("[MASTER] Timeout waiting for workers")
        return False
    
    def _ratio_lot_calculation(self) -> float:
        """Calculate lot size using ratio condition + 3-scenario range logic.
        
        Step 1: ratio_lot = (lower_balance / LOT_BASE_AMOUNT) * LOT_PER_BASE
        Step 2:
          - If ratio_lot > max_lot → random(min_lot, max_lot)
          - If min_lot < ratio_lot <= max_lot → random(min_lot, ratio_lot)
          - If ratio_lot <= min_lot → use ratio_lot directly
        """
        lower_balance = min(self.hfm_balance, self.equiti_balance)
        
        # Guard: prevent division by zero if LOT_BASE_AMOUNT is misconfigured
        if self.lot_base_amount <= 0:
            print(f"[MASTER] WARNING: LOT_BASE_AMOUNT is {self.lot_base_amount}, using min lot {self.min_lot_size}")
            return self.min_lot_size
        
        ratio_lot = round((lower_balance / self.lot_base_amount) * self.lot_per_base, 2)
        ratio_lot = max(0.01, ratio_lot)  # Floor at 0.01
        
        if ratio_lot > self.max_lot_size:
            # Scenario 1: Ratio exceeds max range → random within full range
            trade_lot = round(random.uniform(self.min_lot_size, self.max_lot_size), 2)
            scenario = f"Scenario 1: ratio {ratio_lot} > max {self.max_lot_size} → random({self.min_lot_size}-{self.max_lot_size})"
        elif ratio_lot > self.min_lot_size:
            # Scenario 2: Ratio within range → random between min and ratio
            trade_lot = round(random.uniform(self.min_lot_size, ratio_lot), 2)
            scenario = f"Scenario 2: {self.min_lot_size} < ratio {ratio_lot} <= {self.max_lot_size} → random({self.min_lot_size}-{ratio_lot})"
        else:
            # Scenario 3: Ratio below min → use ratio directly
            trade_lot = ratio_lot
            scenario = f"Scenario 3: ratio {ratio_lot} <= min {self.min_lot_size} → using ratio directly"
        
        trade_lot = max(0.01, trade_lot)  # Safety floor
        print(f"[MASTER] Lot calculation: {scenario}")
        print(f"[MASTER] → Lot: {trade_lot} lots (Balance: HFM=${self.hfm_balance:.2f}, EQ=${self.equiti_balance:.2f}, Lower=${lower_balance:.2f})")
        return trade_lot
    
    def _calculate_lot_from_balances(self) -> float:
        """Fetch fresh balances and calculate lot using ratio + range logic."""
        # Request balances
        self.hfm_cmd_send.send({"action": Command.GET_BALANCE.value})
        self.equiti_cmd_send.send({"action": Command.GET_BALANCE.value})
        
        hfm_balance = None
        equiti_balance = None
        timeout = 1.0  # 1 second timeout
        start = time.time()
        
        # Wait for both balance responses
        while (hfm_balance is None or equiti_balance is None) and time.time() - start < timeout:
            if self.hfm_data_recv.poll(0.01):
                msg = self.hfm_data_recv.recv()
                if msg.get("type") == "BALANCE":
                    hfm_balance = msg.get("balance", 0)
            
            if self.equiti_data_recv.poll(0.01):
                msg = self.equiti_data_recv.recv()
                if msg.get("type") == "BALANCE":
                    equiti_balance = msg.get("balance", 0)
        
        # Use received balances or fall back to stored ones
        if hfm_balance is not None:
            self.hfm_balance = hfm_balance
        if equiti_balance is not None:
            self.equiti_balance = equiti_balance
        
        # Check if in recovery mode - use fixed small lot
        if self.lot_recovery_mode:
            trade_lot = self.recovery_lot_size
            print(f"[MASTER] RECOVERY MODE: Using fixed lot {trade_lot} ({self.lot_recovery_remaining} recovery trade(s) remaining, HFM: ${self.hfm_balance:.2f}, EQ: ${self.equiti_balance:.2f})")
        else:
            # Calculate lot using ratio + range logic
            trade_lot = self._ratio_lot_calculation()
        
        # Save to instance variable
        self.calculated_lot = trade_lot
        self.config["lot_size"] = trade_lot
        self._lot_synced_to_terminals = False  # Mark as needing sync to terminal volume fields
        
        return trade_lot
    
    def _sync_lot_to_terminals(self):
        """Send MAINTAIN_LOT command to both workers to pre-type the lot into terminal volume fields.
        
        Sends sequentially and WAITS for confirmation from each worker before
        proceeding. This guarantees lot typing is 100% complete before scanning.
        """
        if self._lot_synced_to_terminals:
            return  # Already synced this lot
        
        lot = self.calculated_lot
        print(f"[MASTER] 📝 Pre-typing lot size {lot} into both terminals...")
        
        # Send to HFM first, wait for confirmation, then send to Equiti
        self.hfm_cmd_send.send({"action": "MAINTAIN_LOT", "volume": lot})
        self._wait_for_lot_sync("HFM", self.hfm_data_recv, timeout=10.0)
        
        self.equiti_cmd_send.send({"action": "MAINTAIN_LOT", "volume": lot})
        self._wait_for_lot_sync("EQUITI", self.equiti_data_recv, timeout=10.0)
        
        self._lot_synced_to_terminals = True
    
    def _wait_for_lot_sync(self, broker: str, data_recv, timeout: float = 10.0) -> bool:
        """Wait for LOT_SYNC_DONE confirmation from worker. Drains ticks while waiting."""
        start = time.time()
        while time.time() - start < timeout:
            if data_recv.poll(0.1):
                msg = data_recv.recv()
                if msg["type"] == "LOT_SYNC_DONE":
                    print(f"[MASTER] ✅ {broker} lot sync confirmed")
                    return True
                elif msg["type"] == "TICK":
                    # Keep tick data fresh while waiting
                    if broker == "HFM":
                        self.hfm_tick = msg["data"]
                    else:
                        self.equiti_tick = msg["data"]
        print(f"[MASTER] ⚠️ {broker} lot sync timeout after {timeout}s")
        return False
    
    def _main_loop(self):
        """Main state machine loop."""
        self._receive_data()
        
        if self.state == State.SCANNING:
            self._phase_scanning()
        elif self.state == State.EXECUTING:
            self._phase_executing()
        elif self.state == State.HOLDING:
            self._phase_holding()
        elif self.state == State.EXIT:
            self._phase_exit()
        elif self.state == State.CLOSING_RECOVERY:
            self._phase_closing_recovery()
        
        time.sleep(0.05)
    
    def _receive_data(self):
        """Receive and process data from workers."""
        # HFM data
        while self.hfm_data_recv.poll(0):
            msg = self.hfm_data_recv.recv()
            if msg["type"] == "TICK":
                self.hfm_tick = msg["data"]
            elif msg["type"] == "TRADE_RESULT":
                self._handle_trade_result("HFM", msg["result"])
            elif msg["type"] == "CLOSE_RESULT":
                self._handle_close_result("HFM", msg["result"])
            elif msg["type"] == "POSITION_PNL":
                self.hfm_pnl = msg["data"]
            elif msg["type"] == "CONNECTION_LOST":
                self.hfm_connected = False
                print("[MASTER] *** HFM CONNECTION LOST *** Worker is reconnecting...")
            elif msg["type"] == "RECONNECTED":
                self.hfm_connected = True
                self.hfm_balance = msg.get("balance", self.hfm_balance)
                self._lot_synced_to_terminals = False  # Force lot re-sync after reconnect
                print(f"[MASTER] *** HFM RECONNECTED *** Balance: ${self.hfm_balance:.2f}")
            elif msg["type"] == "TICK_VOLUME":
                self.hfm_tick_volume = msg["data"]
        
        # Equiti data
        while self.equiti_data_recv.poll(0):
            msg = self.equiti_data_recv.recv()
            if msg["type"] == "TICK":
                self.equiti_tick = msg["data"]
            elif msg["type"] == "TRADE_RESULT":
                self._handle_trade_result("EQUITI", msg["result"])
            elif msg["type"] == "CLOSE_RESULT":
                self._handle_close_result("EQUITI", msg["result"])
            elif msg["type"] == "POSITION_PNL":
                self.equiti_pnl = msg["data"]
            elif msg["type"] == "CONNECTION_LOST":
                self.equiti_connected = False
                print("[MASTER] *** EQUITI CONNECTION LOST *** Worker is reconnecting...")
            elif msg["type"] == "RECONNECTED":
                self.equiti_connected = True
                self.equiti_balance = msg.get("balance", self.equiti_balance)
                self._lot_synced_to_terminals = False  # Force lot re-sync after reconnect
                print(f"[MASTER] *** EQUITI RECONNECTED *** Balance: ${self.equiti_balance:.2f}")
            elif msg["type"] == "TICK_VOLUME":
                self.equiti_tick_volume = msg["data"]
    
    def _phase_scanning(self):
        """SCANNING phase - look for entry opportunities."""
        # Check if paused (e.g. for news events or market close)
        if self.paused:
            return
        
        # Guard: skip scanning if either broker is disconnected
        if not self.hfm_connected or not self.equiti_connected:
            disconnected = []
            if not self.hfm_connected:
                disconnected.append("HFM")
            if not self.equiti_connected:
                disconnected.append("EQUITI")
            return

        # Bug #7 fix: Defensive guard - don't scan if we still have tracked positions
        if self.hfm_ticket is not None or self.equiti_ticket is not None:
            print("[MASTER] WARNING: Still have tracked positions, cannot scan!")
            return
        
        # Lot sync is done at startup / after lot randomization — NOT here in the hot path
        
        if self.hfm_tick is None or self.equiti_tick is None:
            return
        
        # Check cooldown
        if self.last_failure_time:
            remaining = self.cooldown_seconds - (time.time() - self.last_failure_time)
            if remaining > 0:
                # Only print cooldown once per second to avoid log spam
                now = time.time()
                if now - self.last_cooldown_print >= 1.0:
                    print_cooldown(remaining)
                    self.last_cooldown_print = now
                return
            # Cooldown expired - check for orphan positions before scanning
            self.last_failure_time = None
            print("\n[MASTER] Cooldown complete. Checking for orphan positions...")
            if self._check_and_close_orphans():
                return  # Found orphans, will handle in CLOSING_RECOVERY
        
        # Check spread filter
        passes, wide_brokers = check_spread_filter(
            self.hfm_tick, self.equiti_tick, self.config["max_spread"]
        )
        if not passes:
            max_pts = int(self.config["max_spread"] * 100000)
            print_spread_filter(
                self.hfm_tick["bid"], self.hfm_tick["ask"],
                self.equiti_tick["bid"], self.equiti_tick["ask"],
                wide_brokers, max_pts
            )
            # Clear pending opportunity if spread became too wide
            self.pending_opportunity = None
            self.pending_opportunity_time = None
            self.pending_gap = None
            return
        
        # Calculate gaps
        gap_a, gap_b, pts_a, pts_b = calculate_gaps(self.hfm_tick, self.equiti_tick)
        min_pts = round(self.config["min_gap"] * 100000)  # Bug #1 fix: use round()
        
        # Display scanning status
        print_scanning(
            self.hfm_tick["bid"], self.hfm_tick["ask"],
            self.equiti_tick["bid"], self.equiti_tick["ask"],
            pts_a, pts_b, min_pts
        )
        
        # Check for entry trigger
        opp = check_entry_trigger(gap_a, gap_b, self.config["min_gap"])
        
        if opp:
            current_gap = gap_a if opp == OpportunityType.ALPHA else gap_b


            
            # If delay is 0, execute immediately without confirmation
            if self.opportunity_confirm_delay <= 0:
                gap_pts = round(current_gap * 100000)
                print(f"[MASTER] *** OPPORTUNITY ({opp.value}) *** Gap: {gap_pts} pts - Executing...")
                self._execute_entry(opp, current_gap)
            # Check if this is a new opportunity or continuation
            elif self.pending_opportunity is None:
                # First detection - store and wait for confirmation
                self.pending_opportunity = opp
                self.pending_opportunity_time = time.time()
                self.pending_gap = current_gap
                gap_pts = round(current_gap * 100000)
                print(f"[MASTER] *** OPPORTUNITY DETECTED ({opp.value}) *** Gap: {gap_pts} pts - Waiting {self.opportunity_confirm_delay}s for confirmation...")
            
            elif self.pending_opportunity == opp:
                # Same opportunity type - check if confirmation delay has passed
                elapsed = time.time() - self.pending_opportunity_time
                remaining = self.opportunity_confirm_delay - elapsed
                
                if remaining > 0:
                    # Still waiting for confirmation
                    gap_pts = round(current_gap * 100000)
                    print(f"[MASTER] *** CONFIRMING ({opp.value}) *** Gap: {gap_pts} pts - Confirming in {remaining:.1f}s...")
                else:
                    # Confirmation delay passed - opportunity still valid, execute!
                    gap_pts = round(current_gap * 100000)
                    print(f"[MASTER] *** CONFIRMED ({opp.value}) *** Gap: {gap_pts} pts - Opportunity persisted for {self.opportunity_confirm_delay}s! Executing...")
                    self.pending_opportunity = None
                    self.pending_opportunity_time = None
                    self.pending_gap = None
                    self._execute_entry(opp, current_gap)
            else:
                # Different opportunity type - reset and start fresh
                gap_pts = round(current_gap * 100000)
                print(f"[MASTER] *** OPPORTUNITY CHANGED ({self.pending_opportunity.value} -> {opp.value}) *** Resetting confirmation timer...")
                self.pending_opportunity = opp
                self.pending_opportunity_time = time.time()
                self.pending_gap = current_gap
        else:
            # No opportunity - clear pending state
            if self.pending_opportunity is not None:
                print(f"[MASTER] Opportunity {self.pending_opportunity.value} disappeared before confirmation, resetting...")
                self.pending_opportunity = None
                self.pending_opportunity_time = None
                self.pending_gap = None
    
    def _wait_for_trade_result(self, broker: str, timeout: float = 3.0) -> dict | None:
        """
        Wait for a TRADE_RESULT from a specific broker's data pipe.
        Drains tick data while waiting to keep pipes from backing up.
        Returns the trade result dict, or None on timeout.
        """
        data_recv = self.hfm_data_recv if broker == "HFM" else self.equiti_data_recv
        other_recv = self.equiti_data_recv if broker == "HFM" else self.hfm_data_recv
        start = time.time()
        
        while time.time() - start < timeout:
            # Check target broker pipe
            while data_recv.poll(0.01):
                msg = data_recv.recv()
                if msg["type"] == "TRADE_RESULT":
                    return msg["result"]
                elif msg["type"] == "TICK":
                    if broker == "HFM":
                        self.hfm_tick = msg["data"]
                    else:
                        self.equiti_tick = msg["data"]
                # Discard other messages during execution wait
            
            # Also drain the OTHER broker's tick data to prevent pipe backup
            while other_recv.poll(0):
                msg = other_recv.recv()
                if msg["type"] == "TICK":
                    if broker == "HFM":
                        self.equiti_tick = msg["data"]
                    else:
                        self.hfm_tick = msg["data"]
                # Discard other messages
        
        return None  # Timeout
    
    def _drain_fresh_ticks(self):
        """Drain both data pipes for the freshest tick data.
        
        Call this right before gap re-checks to ensure we're using
        the most recent prices, not stale cached values.
        """
        # Drain HFM pipe
        while self.hfm_data_recv.poll(0):
            msg = self.hfm_data_recv.recv()
            if msg["type"] == "TICK":
                self.hfm_tick = msg["data"]
            elif msg["type"] == "TRADE_RESULT":
                self._handle_trade_result("HFM", msg["result"])
        
        # Drain Equiti pipe
        while self.equiti_data_recv.poll(0):
            msg = self.equiti_data_recv.recv()
            if msg["type"] == "TICK":
                self.equiti_tick = msg["data"]
            elif msg["type"] == "TRADE_RESULT":
                self._handle_trade_result("EQUITI", msg["result"])

    def _recheck_gap(self, opp_type: OpportunityType) -> tuple:
        """Re-check the gap using freshest tick data.
        
        Returns (gap_ok, current_gap_pts) where gap_ok is True if
        the gap still meets the minimum threshold.
        """
        self._drain_fresh_ticks()
        
        if self.hfm_tick is None or self.equiti_tick is None:
            return False, 0
        
        gap_a, gap_b, pts_a, pts_b = calculate_gaps(self.hfm_tick, self.equiti_tick)
        min_pts = round(self.config["min_gap"] * 100000)
        
        if opp_type == OpportunityType.ALPHA:
            return pts_a >= min_pts, pts_a
        else:
            return pts_b >= min_pts, pts_b

    def _wait_for_both_results(self, timeout: float = 1.5) -> tuple:
        """Wait for TRADE_RESULT from BOTH brokers simultaneously.
        
        Polls both pipes in parallel, collecting results as they arrive.
        Returns (hfm_result, equiti_result) — either may be None on timeout.
        """
        hfm_result = None
        equiti_result = None
        start = time.time()
        
        while time.time() - start < timeout:
            # Check HFM pipe
            while self.hfm_data_recv.poll(0.01):
                msg = self.hfm_data_recv.recv()
                if msg["type"] == "TRADE_RESULT":
                    hfm_result = msg["result"]
                elif msg["type"] == "TICK":
                    self.hfm_tick = msg["data"]
            
            # Check Equiti pipe
            while self.equiti_data_recv.poll(0.01):
                msg = self.equiti_data_recv.recv()
                if msg["type"] == "TRADE_RESULT":
                    equiti_result = msg["result"]
                elif msg["type"] == "TICK":
                    self.equiti_tick = msg["data"]
            
            # Both received — done!
            if hfm_result is not None and equiti_result is not None:
                break
        
        return hfm_result, equiti_result

    def _execute_entry(self, opp_type: OpportunityType, gap: float):
        """Execute trade entry for the detected opportunity."""
        # Bug #3 fix: Prevent entering new trades if existing positions are tracked
        if self.hfm_ticket is not None or self.equiti_ticket is not None:
            print("[MASTER] WARNING: Cannot enter - existing positions still tracked!")
            return
        
        # Reset abort flag for new execution
        self.execution_aborted = False
        
        # NOTE: Lot size is calculated BEFORE scanning
        trade_lot = self.hfm_config["lot_size"]
        # target_profit stays at config.TARGET_NET_PROFIT (0 = disabled for point-based exit)
        
        # Update worker configs with lot size
        self.hfm_config["lot_size"] = trade_lot
        self.equiti_config["lot_size"] = trade_lot
        
        gap_pts = round(gap * 100000)  # Bug #1 fix: use round()
        self.entry_gap_pts = gap_pts  # Store for history
        min_pts = round(self.config["min_gap"] * 100000)
        hfm_action, eq_action = get_trade_actions(opp_type)
        
        if opp_type == OpportunityType.ALPHA:
            price_a, price_b = self.hfm_tick["ask"], self.equiti_tick["bid"]
        else:
            price_a, price_b = self.hfm_tick["bid"], self.equiti_tick["ask"]


        
        print_opportunity(
            opp_type.value, gap, gap_pts, self.config["min_gap"], min_pts,
            hfm_action, price_a, eq_action, price_b
        )
        exit_pts = round(self.config["exit_reversal_gap"] * 100000)
        print(f"[MASTER] Trade lot size: {trade_lot} lots | Exit at: {exit_pts} pts reversal")
        
        self.opportunity_type = opp_type
        self.hfm_trade_type = hfm_action
        self.equiti_trade_type = eq_action
        
        # ══════════════════════════════════════════════════════════════════════
        # FIRE-AND-FORGET CLICK EXECUTION
        # Click both terminals within 200ms, THEN verify both trades together.
        # This minimizes price drift between the two fills (~1 pt vs ~5 pts).
        # ══════════════════════════════════════════════════════════════════════
        
        self.hfm_ticket = None
        self.equiti_ticket = None
        self.execution_start_time = time.time()
        
        leg_timeout = self._get_execution_timeout()
        
        # ── GAP RE-CHECK before firing clicks ─────────────────────────────
        gap_ok, fresh_pts = self._recheck_gap(opp_type)
        if not gap_ok:
            print(f"[MASTER] ❌ Gap re-check FAILED! Gap now {fresh_pts} pts (need {min_pts} pts). ABORTING entry.")
            return
        print(f"[MASTER] ✅ Gap re-check OK: {fresh_pts} pts (need {min_pts} pts)")
        
        # ── FIRE BOTH CLICKS (200ms apart) ────────────────────────────────
        # Click HFM first
        print(f"[MASTER] ⚡ FIRE: {hfm_action} → HFM...")
        self.hfm_cmd_send.send({"action": hfm_action, "volume": trade_lot})
        
        # 100ms gap — window needs time for _bring_to_front + click + _remove_topmost
        # before the second worker brings its window to front
        time.sleep(0.10)
        
        # Click Equiti immediately after
        print(f"[MASTER] ⚡ FIRE: {eq_action} → EQUITI...")
        self.equiti_cmd_send.send({"action": eq_action, "volume": trade_lot})
        
        # ── WAIT FOR BOTH CONFIRMATIONS ───────────────────────────────────
        print(f"[MASTER] ⏳ Waiting for both confirmations (timeout: {leg_timeout}s)...")
        hfm_result, equiti_result = self._wait_for_both_results(timeout=leg_timeout)
        
        # Process HFM result
        if hfm_result is None:
            print(f"[MASTER] *** TIMEOUT *** HFM did not respond in {leg_timeout}s!")
            self.hfm_ticket = -1
            self.execution_aborted = True
        else:
            self._handle_trade_result("HFM", hfm_result)
        
        # Process Equiti result
        if equiti_result is None:
            print(f"[MASTER] *** TIMEOUT *** EQUITI did not respond in {leg_timeout}s!")
            self.equiti_ticket = -1
            self.execution_aborted = True
        else:
            self._handle_trade_result("EQUITI", equiti_result)
        
        # Check outcomes
        hfm_ok = self.hfm_ticket is not None and self.hfm_ticket > 0
        equiti_ok = self.equiti_ticket is not None and self.equiti_ticket > 0
        
        elapsed_ms = int((time.time() - self.execution_start_time) * 1000)
        
        if hfm_ok and equiti_ok:
            print(f"[MASTER] ✅ Both legs filled in {elapsed_ms}ms!")
            self.state = State.EXECUTING
        elif not hfm_ok and not equiti_ok:
            print(f"[MASTER] *** BOTH LEGS FAILED *** Entering recovery...")
            self._enter_closing_recovery()
        else:
            failed = "HFM" if not hfm_ok else "EQUITI"
            print(f"[MASTER] *** {failed} FAILED *** Entering recovery to close the other leg...")
            self._enter_closing_recovery()
    
    def _handle_trade_result(self, broker: str, result: dict):
        """Handle trade execution result from worker."""
        # If execution was aborted (timeout), close any late-arriving successful trades
        if self.execution_aborted:
            if result["success"]:
                print(f"[MASTER] Late {broker} trade arrived after abort - closing immediately!")
                ticket = result["ticket"]
                if broker == "HFM":
                    self.hfm_cmd_send.send({"action": Command.CLOSE.value, "ticket": ticket})
                else:
                    self.equiti_cmd_send.send({"action": Command.CLOSE.value, "ticket": ticket})
            return  # Don't update state after abort
        
        if result["success"]:
            print_trade_result(broker, True, result["ticket"], result["price"])
            if broker == "HFM":
                self.hfm_ticket = result["ticket"]
                self.hfm_entry_price = result["price"]
            else:
                self.equiti_ticket = result["ticket"]
                self.equiti_entry_price = result["price"]
        else:
            print_trade_result(broker, False, error=result["error"])
            if broker == "HFM":
                self.hfm_ticket = -1
            else:
                self.equiti_ticket = -1
    
    def _phase_executing(self):
        """EXECUTING phase - wait for both trades to complete with timeout."""
        # Check if we've exceeded the execution timeout
        elapsed = time.time() - self.execution_start_time
        timeout = self._get_execution_timeout()
        
        # Still waiting for responses
        hfm_pending = self.hfm_ticket is None
        equiti_pending = self.equiti_ticket is None
        
        if hfm_pending or equiti_pending:
            # Check if timeout exceeded while waiting
            if elapsed >= timeout:
                print(f"[MASTER] *** TIMEOUT *** Waited {timeout}s, one leg still pending!")
                self.execution_aborted = True  # Mark as aborted to handle late results
                # Enter recovery to properly close any open positions
                self._enter_closing_recovery()
            return
        
        # Both have responded - check for failures
        hfm_failed = self.hfm_ticket == -1
        equiti_failed = self.equiti_ticket == -1
        
        if hfm_failed or equiti_failed:
            print("[MASTER] *** TRADE FAILED *** Entering recovery to close any open legs!")
            # Enter recovery to properly close any open positions
            self._enter_closing_recovery()
            return
        
        # Both trades succeeded!



        print(f"[MASTER] Both legs opened ({self.opportunity_type.value}). Starting HOLD...")
        self.trade_start_time = time.time()
        
        # Safety check: Entry point difference threshold → activate recovery mode
        min_entry_point_diff = getattr(config, 'MIN_ENTRY_POINT_DIFF', 0)
        if min_entry_point_diff > 0:
            self.actual_entry_diff_pts = round(abs(self.hfm_entry_price - self.equiti_entry_price) * 100000)
            if self.actual_entry_diff_pts <= min_entry_point_diff:
                if not self.lot_recovery_mode:
                    # First bad trade → enter recovery mode
                    self.lot_recovery_mode = True
                    self.lot_recovery_remaining = self.recovery_trade_count
                    print(f"[MASTER] *** RECOVERY MODE ACTIVATED *** Entry gap ({self.actual_entry_diff_pts} pts) at/below threshold ({min_entry_point_diff} pts). Next {self.recovery_trade_count} trades will use {self.recovery_lot_size} lots.")
                else:
                    # Already in recovery and got another bad trade → shutdown after this trade
                    self.shutdown_after_trade = True
                    print(f"[MASTER] *** RECOVERY FAILED *** Bad entry ({self.actual_entry_diff_pts} pts) during recovery. Bot will shutdown after this trade.")
        
        # Notify callback to save to DB
        if self.on_trade_update:
            try:
                # Calculate ACTUAL entry gap from execution prices
                if self.opportunity_type == OpportunityType.ALPHA:
                    # Alpha: Long HFM, Short Equiti -> Gap = Equiti(Bid) - HFM(Ask)
                    actual_entry_gap = self.equiti_entry_price - self.hfm_entry_price
                else:
                    # Beta: Short HFM, Long Equiti -> Gap = HFM(Bid) - Equiti(Ask)
                    actual_entry_gap = self.hfm_entry_price - self.equiti_entry_price
                
                actual_entry_gap_pts = round(actual_entry_gap * 100000)
                
                self.on_trade_update(
                    opportunity_type=self.opportunity_type.value,
                    hfm_ticket=self.hfm_ticket,
                    equiti_ticket=self.equiti_ticket,
                    hfm_entry_price=self.hfm_entry_price,
                    equiti_entry_price=self.equiti_entry_price,
                    lot_size=self.calculated_lot,
                    entry_gap=actual_entry_gap_pts,  # Actual execution gap
                    status='OPEN'
                )
            except Exception as e:
                print(f"[MASTER] Warning: Failed to save trade update: {e}")
                
        self.state = State.HOLDING

    def _get_execution_timeout(self) -> float:
        """Return runtime execution timeout from dashboard/DB-backed settings."""
        timeout = self.config.get("execution_timeout", 1.0)
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            return 1.0
        return timeout if timeout > 0 else 1.0
    
    def _handle_close_result(self, broker: str, result: dict):
        """Handle close result from worker."""
        if result["success"]:
            print_close_result(broker, True, result["close_price"])
            
            # CRITICAL: Update recovery flags if in CLOSING_RECOVERY state
            # This ensures we recognize closes even when _receive_data consumes the message
            if self.state == State.CLOSING_RECOVERY:
                if broker == "HFM":
                    self.recovery_hfm_closed = True
                elif broker == "EQUITI":
                    self.recovery_equiti_closed = True
        else:
            print_close_result(broker, False, error=result["error"])
    
    def _phase_holding(self):
        """HOLDING phase - wait for timer, profit target, or reversal."""
        if self.hfm_ticket is None or self.equiti_ticket is None:
            self.state = State.SCANNING
            return
        
        # Request PnL updates
        self.hfm_cmd_send.send({"action": Command.GET_POSITION.value, "ticket": self.hfm_ticket})
        self.equiti_cmd_send.send({"action": Command.GET_POSITION.value, "ticket": self.equiti_ticket})
        
        # Wait for FRESH PnL data (with short timeout)
        # This ensures we don't use stale cached values for exit decisions
        pnl_timeout = 0.5  # 500ms max wait
        pnl_start = time.time()
        hfm_pnl_fresh = False
        equiti_pnl_fresh = False
        
        while (time.time() - pnl_start) < pnl_timeout:
            # Check HFM pipe for fresh PnL
            while self.hfm_data_recv.poll(0.01):
                msg = self.hfm_data_recv.recv()
                if msg["type"] == "POSITION_PNL":
                    self.hfm_pnl = msg["data"]
                    hfm_pnl_fresh = True
                elif msg["type"] == "TICK":
                    self.hfm_tick = msg["data"]
            
            # Check Equiti pipe for fresh PnL
            while self.equiti_data_recv.poll(0.01):
                msg = self.equiti_data_recv.recv()
                if msg["type"] == "POSITION_PNL":
                    self.equiti_pnl = msg["data"]
                    equiti_pnl_fresh = True
                elif msg["type"] == "TICK":
                    self.equiti_tick = msg["data"]
            
            # Exit wait loop if both are fresh
            if hfm_pnl_fresh and equiti_pnl_fresh:
                break
        
        elapsed = time.time() - self.trade_start_time
        net_pnl = calculate_net_pnl(self.hfm_pnl, self.equiti_pnl)
        
        # Calculate reversal gap
        reversal, reversal_pts = (0.0, 0)
        if self.hfm_tick and self.equiti_tick:
            reversal, reversal_pts = calculate_reversal_gap(
                self.hfm_tick, self.equiti_tick, self.opportunity_type
            )
        
        # Display status
        hfm_pnl_val = self.hfm_pnl.get("net_profit", 0) if self.hfm_pnl else 0
        eq_pnl_val = self.equiti_pnl.get("net_profit", 0) if self.equiti_pnl else 0
        exit_pts = int(self.config["exit_reversal_gap"] * 100000)
        
        print_holding(
            elapsed, self.config["min_hold"], self.opportunity_type.value,
            self.hfm_trade_type, hfm_pnl_val,
            self.equiti_trade_type, eq_pnl_val,
            net_pnl, self.config["target_profit"], reversal_pts, exit_pts
        )
        
        # Check exit conditions (profit target + buffer for slippage, OR reversal)
        exit_threshold = self.config["target_profit"] + self.config["exit_slippage_buffer"]
        should_exit, reason, details = check_exit_conditions(
            elapsed, self.config["min_hold"], net_pnl,
            exit_threshold, reversal, self.config["exit_reversal_gap"]
        )
        
        if should_exit:


            # If delay is 0, exit immediately without confirmation
            if self.exit_confirm_delay <= 0:
                print_exit(reason, details)
                self.exit_gap_pts = reversal_pts
                self.state = State.EXIT
            # Check if this is a new exit signal or continuation
            elif not self.pending_exit:
                # First detection - store and wait for confirmation
                self.pending_exit = True
                self.pending_exit_time = time.time()
                self.pending_exit_reason = reason
                self.pending_exit_details = details
                print(f"[MASTER] *** EXIT DETECTED ({reason}) *** Waiting {self.exit_confirm_delay}s for confirmation...")
            else:
                # Check if confirmation delay has passed
                exit_elapsed = time.time() - self.pending_exit_time
                remaining = self.exit_confirm_delay - exit_elapsed
                
                if remaining > 0:
                    # Still waiting for confirmation
                    print(f"[MASTER] *** CONFIRMING EXIT ({reason}) *** Confirming in {remaining:.1f}s...")
                else:
                    # Confirmation delay passed - exit condition still valid, execute!
                    print(f"[MASTER] *** EXIT CONFIRMED ({reason}) *** Condition persisted for {self.exit_confirm_delay}s! Closing...")
                    self.pending_exit = False
                    self.pending_exit_time = None
                    print_exit(reason, details)
                    self.exit_gap_pts = reversal_pts
                    self.state = State.EXIT
        else:
            # Exit condition no longer met - clear pending state
            if self.pending_exit:
                print(f"[MASTER] Exit condition {self.pending_exit_reason} disappeared before confirmation, resetting...")
                self.pending_exit = False
                self.pending_exit_time = None
                self.pending_exit_reason = None
                self.pending_exit_details = None
    
    def _close_one_leg(self, broker: str, ticket: int, cmd_send, data_recv, other_data_recv, timeout: float = 3.0, max_retries: int = 3) -> dict:
        """Close a single leg sequentially. Returns dict with close_price, realized_profit, success.
        
        Sends the CLOSE command once, waits for the CLOSE_RESULT. If it fails
        or times out, retries up to max_retries times — each retry re-sends the
        close click command.
        """
        for attempt in range(max_retries + 1):
            if attempt > 0:
                print(f"[MASTER] {broker} close retry {attempt}/{max_retries}...")
            
            cmd_send.send({"action": Command.CLOSE.value, "ticket": ticket})
            start = time.time()
            
            while time.time() - start < timeout:
                # Check this broker's pipe for CLOSE_RESULT
                while data_recv.poll(0.01):
                    msg = data_recv.recv()
                    if msg["type"] == "CLOSE_RESULT":
                        if msg["result"]["success"]:
                            print_close_result(broker, True, msg["result"]["close_price"])
                            return {
                                "success": True,
                                "close_price": msg["result"]["close_price"],
                                "realized_profit": msg["result"].get("realized_profit", 0.0)
                            }
                        else:
                            print_close_result(broker, False, error=msg["result"]["error"])
                            break  # Failed — will retry
                    elif msg["type"] == "TICK":
                        if broker == "HFM":
                            self.hfm_tick = msg["data"]
                        else:
                            self.equiti_tick = msg["data"]
                
                # Drain the OTHER broker's pipe to prevent backup
                while other_data_recv.poll(0):
                    msg = other_data_recv.recv()
                    if msg["type"] == "TICK":
                        if broker == "HFM":
                            self.equiti_tick = msg["data"]
                        else:
                            self.hfm_tick = msg["data"]
        
        return {"success": False, "close_price": 0.0, "realized_profit": 0.0}

    def _phase_exit(self):
        """EXIT phase - close both positions SEQUENTIALLY.
        
        Closes one leg at a time to avoid Z-order race conditions where both
        MT5 windows fight for TOPMOST status and clicks land on the wrong window.
        EQUITI closes first, then HFM. Each leg gets its own retry loop.
        """
        print("[MASTER] Closing both positions (sequential)...")
        
        # Track which positions need to be closed
        hfm_needs_close = self.hfm_ticket and self.hfm_ticket > 0
        equiti_needs_close = self.equiti_ticket and self.equiti_ticket > 0
        
        hfm_realized_profit = 0.0
        equiti_realized_profit = 0.0
        hfm_close_price = 0.0
        equiti_close_price = 0.0
        hfm_closed = not hfm_needs_close
        equiti_closed = not equiti_needs_close
        
        # ── STEP 1: Close EQUITI first (no Z-order conflict) ──────────────
        if equiti_needs_close:
            result = self._close_one_leg(
                "EQUITI", self.equiti_ticket,
                self.equiti_cmd_send, self.equiti_data_recv, self.hfm_data_recv,
                timeout=3.0, max_retries=3
            )
            if result["success"]:
                equiti_closed = True
                equiti_close_price = result["close_price"]
                equiti_realized_profit = result["realized_profit"]
        
        # ── STEP 2: Close HFM (EQUITI is done, no Z-order conflict) ──────
        if hfm_needs_close:
            result = self._close_one_leg(
                "HFM", self.hfm_ticket,
                self.hfm_cmd_send, self.hfm_data_recv, self.equiti_data_recv,
                timeout=3.0, max_retries=3
            )
            if result["success"]:
                hfm_closed = True
                hfm_close_price = result["close_price"]
                hfm_realized_profit = result["realized_profit"]
        
        # ── Check if both closed ──────────────────────────────────────────
        if not (hfm_closed and equiti_closed):
            print("[MASTER] *** CRITICAL *** Sequential close failed, entering CLOSING_RECOVERY...")
            self._enter_closing_recovery()
            return
        
        # Calculate final PnL from ACTUAL realized profits (not cached values)
        final_pnl = hfm_realized_profit + equiti_realized_profit
        print_cycle_complete(self.opportunity_type.value, final_pnl)
        
        # Notify callback to save to DB
        if self.on_trade_update:
            try:
                hold_duration = time.time() - self.trade_start_time if self.trade_start_time else 0
                
                # Calculate ACTUAL exit gap from close prices
                # Guard: if either close price is 0.0 (close failed), use reversal-based gap
                if hfm_close_price > 0 and equiti_close_price > 0:
                    if self.opportunity_type == OpportunityType.ALPHA:
                        # Alpha Exit: Sell HFM, Buy Equiti -> Gap = HFM(Bid) - Equiti(Ask)
                        actual_exit_gap = hfm_close_price - equiti_close_price
                    else:
                        # Beta Exit: Buy HFM, Sell Equiti -> Gap = Equiti(Bid) - HFM(Ask)
                        actual_exit_gap = equiti_close_price - hfm_close_price
                    actual_exit_gap_pts = round(actual_exit_gap * 100000)
                else:
                    # Fallback: use reversal gap from HOLDING phase (last known good value)
                    actual_exit_gap_pts = self.exit_gap_pts
                    print(f"[MASTER] WARNING: Close price missing (HFM={hfm_close_price}, EQ={equiti_close_price}), using reversal gap: {actual_exit_gap_pts} pts")
                
                self.on_trade_update(
                    hfm_profit=hfm_realized_profit,
                    equiti_profit=equiti_realized_profit,
                    hfm_exit_price=hfm_close_price,
                    equiti_exit_price=equiti_close_price,
                    hold_duration=hold_duration,
                    exit_gap=actual_exit_gap_pts,  # Actual close gap
                    status='CLOSED' if (hfm_closed and equiti_closed) else 'PARTIAL_CLOSE'
                )
            except Exception as e:
                print(f"[MASTER] Warning: Failed to save trade close: {e}")
        
        # Recovery mode: decrement counter if we were in recovery and this trade was good
        min_entry_point_diff = getattr(config, 'MIN_ENTRY_POINT_DIFF', 0)
        if self.lot_recovery_mode and min_entry_point_diff > 0:
            actual_diff_pts = getattr(self, 'actual_entry_diff_pts', self.entry_gap_pts)  # Use ACTUAL execution gap, not scanning gap
            if actual_diff_pts > min_entry_point_diff:
                self.lot_recovery_remaining -= 1
                print(f"[MASTER] Recovery trade GOOD ({actual_diff_pts} pts > {min_entry_point_diff} pts). {self.lot_recovery_remaining} recovery trade(s) remaining.")
                if self.lot_recovery_remaining <= 0:
                    self.lot_recovery_mode = False
                    self.lot_recovery_remaining = 0
                    print(f"[MASTER] *** RECOVERY MODE COMPLETE *** Reverting to normal lot range ({self.min_lot_size}-{self.max_lot_size}).")
            # Note: bad trades during recovery trigger shutdown (handled in _phase_executing)
        
        self._reset_trade_state()
        
        # Shutdown if recovery failed (bad trade while already in recovery)
        if self.shutdown_after_trade:
            print("[MASTER] *** SAFETY SHUTDOWN *** Recovery mode failed - bad entries persist. Stopping bot.")
            self.running = False
            self.shutdown_after_trade = False
            return
        
        # Apply trade delay BEFORE reloading settings and typing lots
        if self.max_trade_delay > 0:
            delay = round(random.uniform(self.min_trade_delay, self.max_trade_delay), 1)
            if delay > 0:
                print(f"[MASTER] ⏱️ Trade delay: waiting {delay}s before next cycle (range: {self.min_trade_delay}-{self.max_trade_delay}s)")
                time.sleep(delay)
        
        # Reload settings from config module for next trade
        self.reload_settings()
        
        # Calculate fresh lot size for NEXT trade using updated balances
        self._calculate_lot_from_balances()
        self.hfm_config["lot_size"] = self.calculated_lot
        self.equiti_config["lot_size"] = self.calculated_lot
        self._sync_lot_to_terminals()  # Pre-type new lot into terminals
        
        self.state = State.SCANNING
    
    def _enter_closing_recovery(self):
        """Transition to CLOSING_RECOVERY - wait for all legs to close."""
        print("[MASTER] Entering CLOSING_RECOVERY - waiting for all positions to close...")
        
        # Track which positions need closing
        self.recovery_hfm_ticket = self.hfm_ticket if self.hfm_ticket and self.hfm_ticket > 0 else None
        self.recovery_equiti_ticket = self.equiti_ticket if self.equiti_ticket and self.equiti_ticket > 0 else None
        self.recovery_hfm_closed = self.recovery_hfm_ticket is None
        self.recovery_equiti_closed = self.recovery_equiti_ticket is None
        self.recovery_start_time = time.time()
        self.recovery_last_retry_time = time.time()
        self.recovery_retry_count = 0  # Track retry attempts for progressive backoff
        
        # Equiti first, then HFM (HFM needs focus last)
        if self.recovery_equiti_ticket:
            self.equiti_cmd_send.send({"action": Command.CLOSE.value, "ticket": self.recovery_equiti_ticket})
        if self.recovery_hfm_ticket and self.recovery_equiti_ticket:
            time.sleep(0.02)  # 20ms gap
        if self.recovery_hfm_ticket:
            self.hfm_cmd_send.send({"action": Command.CLOSE.value, "ticket": self.recovery_hfm_ticket})
        
        self._reset_trade_state()  # Clear trade state but keep recovery tracking
        self.state = State.CLOSING_RECOVERY
    
    def _phase_closing_recovery(self):
        """CLOSING_RECOVERY phase - persist until all positions are confirmed closed."""
        RETRY_INTERVAL = 5.0  # Retry close command every 5 seconds
        
        elapsed = time.time() - self.recovery_start_time
        
        # Process incoming messages from HFM
        while self.hfm_data_recv.poll(0):
            msg = self.hfm_data_recv.recv()
            if msg["type"] == "CLOSE_RESULT":
                if msg["result"]["success"]:
                    print("[MASTER] HFM recovery close confirmed!")
                    self.recovery_hfm_closed = True
                else:
                    error_msg = str(msg['result']['error']).lower()
                    print(f"[MASTER] HFM recovery close failed: {msg['result']['error']}")
                    # If position not found, wait up to 60s before assuming closed
                    if "not found" in error_msg or "invalid ticket" in error_msg:
                        if elapsed >= 60:
                            print("[MASTER] Position not found after 60s - assuming already closed.")
                            self.recovery_hfm_closed = True
                        else:
                            print(f"[MASTER] Position not found, will retry until 60s (elapsed: {elapsed:.0f}s)")
            elif msg["type"] == "TRADE_RESULT" and msg["result"]["success"]:
                # Late trade arrived - need to close it too!
                late_ticket = msg["result"]["ticket"]
                print(f"[MASTER] Late HFM trade arrived (#{late_ticket}) - closing immediately!")
                self.recovery_hfm_ticket = late_ticket
                self.recovery_hfm_closed = False
                self.hfm_cmd_send.send({"action": Command.CLOSE.value, "ticket": late_ticket})
            elif msg["type"] == "TICK":
                self.hfm_tick = msg["data"]  # Keep tick data fresh
        
        # Process incoming messages from Equiti
        while self.equiti_data_recv.poll(0):
            msg = self.equiti_data_recv.recv()
            if msg["type"] == "CLOSE_RESULT":
                if msg["result"]["success"]:
                    print("[MASTER] EQUITI recovery close confirmed!")
                    self.recovery_equiti_closed = True
                else:
                    error_msg = str(msg['result']['error']).lower()
                    print(f"[MASTER] EQUITI recovery close failed: {msg['result']['error']}")
                    # If position not found, wait up to 60s before assuming closed
                    if "not found" in error_msg or "invalid ticket" in error_msg:
                        if elapsed >= 60:
                            print("[MASTER] Position not found after 60s - assuming already closed.")
                            self.recovery_equiti_closed = True
                        else:
                            print(f"[MASTER] Position not found, will retry until 60s (elapsed: {elapsed:.0f}s)")
            elif msg["type"] == "TRADE_RESULT" and msg["result"]["success"]:
                # Late trade arrived - need to close it too!
                late_ticket = msg["result"]["ticket"]
                print(f"[MASTER] Late EQUITI trade arrived (#{late_ticket}) - closing immediately!")
                self.recovery_equiti_ticket = late_ticket
                self.recovery_equiti_closed = False
                self.equiti_cmd_send.send({"action": Command.CLOSE.value, "ticket": late_ticket})
            elif msg["type"] == "TICK":
                self.equiti_tick = msg["data"]  # Keep tick data fresh
        
        # Check if both closed
        if self.recovery_hfm_closed and self.recovery_equiti_closed:
            print("\n[MASTER] All recovery closes confirmed!")
            
            # SAFETY: Final inline orphan check before entering cooldown
            # We do NOT call _check_and_close_orphans() here because it calls
            # _enter_closing_recovery() which would overwrite the orphan tickets.
            self.hfm_cmd_send.send({"action": "CHECK_ORPHANS"})
            self.equiti_cmd_send.send({"action": "CHECK_ORPHANS"})
            orphan_found = False
            check_start = time.time()
            hfm_chk = False
            eq_chk = False
            while time.time() - check_start < 1.0 and not (hfm_chk and eq_chk):
                if self.hfm_data_recv.poll(0.01):
                    msg = self.hfm_data_recv.recv()
                    if msg["type"] == "ORPHAN_POSITIONS":
                        hfm_chk = True
                        for ticket in msg["tickets"]:
                            print(f"[MASTER] ⚠️ Orphan found: HFM #{ticket}")
                            self.recovery_hfm_ticket = ticket
                            self.recovery_hfm_closed = False
                            orphan_found = True
                    elif msg["type"] == "TICK":
                        self.hfm_tick = msg["data"]
                if self.equiti_data_recv.poll(0.01):
                    msg = self.equiti_data_recv.recv()
                    if msg["type"] == "ORPHAN_POSITIONS":
                        eq_chk = True
                        for ticket in msg["tickets"]:
                            print(f"[MASTER] ⚠️ Orphan found: EQUITI #{ticket}")
                            self.recovery_equiti_ticket = ticket
                            self.recovery_equiti_closed = False
                            orphan_found = True
                    elif msg["type"] == "TICK":
                        self.equiti_tick = msg["data"]
            
            if orphan_found:
                # Send close commands for orphans (staggered)
                print("[MASTER] Orphans found after recovery! Closing them...")
                self.recovery_start_time = time.time()
                self.recovery_last_retry_time = time.time()
                self.recovery_retry_count = 0
                if self.recovery_equiti_ticket and not self.recovery_equiti_closed:
                    self.equiti_cmd_send.send({"action": Command.CLOSE.value, "ticket": self.recovery_equiti_ticket})
                if (self.recovery_hfm_ticket and not self.recovery_hfm_closed) and (self.recovery_equiti_ticket and not self.recovery_equiti_closed):
                    time.sleep(0.02)
                if self.recovery_hfm_ticket and not self.recovery_hfm_closed:
                    self.hfm_cmd_send.send({"action": Command.CLOSE.value, "ticket": self.recovery_hfm_ticket})
                return  # Stay in CLOSING_RECOVERY
            
            print("[MASTER] No orphans found. Entering cooldown...")
            self.last_failure_time = time.time()
            self._reset_recovery_state()
            
            # Refresh settings and lot before returning to scanning
            self.reload_settings()
            self._calculate_lot_from_balances()
            self.hfm_config["lot_size"] = self.calculated_lot
            self.equiti_config["lot_size"] = self.calculated_lot
            self._sync_lot_to_terminals()  # Pre-type new lot into terminals
            
            self.state = State.SCANNING
            return
        
        # HARD TIMEOUT: Force exit after 60 seconds no matter what
        if elapsed >= 60:
            pending = []
            if not self.recovery_hfm_closed: pending.append("HFM")
            if not self.recovery_equiti_closed: pending.append("EQUITI")
            print(f"\n[MASTER] *** RECOVERY TIMEOUT *** 60s elapsed. Force-closing: {', '.join(pending)}")
            
            # SAFETY: Inline orphan check — don't just assume closed
            self.hfm_cmd_send.send({"action": "CHECK_ORPHANS"})
            self.equiti_cmd_send.send({"action": "CHECK_ORPHANS"})
            orphan_found = False
            check_start = time.time()
            hfm_chk = False
            eq_chk = False
            while time.time() - check_start < 1.0 and not (hfm_chk and eq_chk):
                if self.hfm_data_recv.poll(0.01):
                    msg = self.hfm_data_recv.recv()
                    if msg["type"] == "ORPHAN_POSITIONS":
                        hfm_chk = True
                        for ticket in msg["tickets"]:
                            print(f"[MASTER] ⚠️ Orphan found: HFM #{ticket}")
                            self.recovery_hfm_ticket = ticket
                            self.recovery_hfm_closed = False
                            orphan_found = True
                    elif msg["type"] == "TICK":
                        self.hfm_tick = msg["data"]
                if self.equiti_data_recv.poll(0.01):
                    msg = self.equiti_data_recv.recv()
                    if msg["type"] == "ORPHAN_POSITIONS":
                        eq_chk = True
                        for ticket in msg["tickets"]:
                            print(f"[MASTER] ⚠️ Orphan found: EQUITI #{ticket}")
                            self.recovery_equiti_ticket = ticket
                            self.recovery_equiti_closed = False
                            orphan_found = True
                    elif msg["type"] == "TICK":
                        self.equiti_tick = msg["data"]
            
            if orphan_found:
                # Send close commands for orphans (staggered)
                print("[MASTER] Orphans found after timeout! Closing them...")
                self.recovery_start_time = time.time()
                self.recovery_last_retry_time = time.time()
                self.recovery_retry_count = 0
                if self.recovery_equiti_ticket and not self.recovery_equiti_closed:
                    self.equiti_cmd_send.send({"action": Command.CLOSE.value, "ticket": self.recovery_equiti_ticket})
                if (self.recovery_hfm_ticket and not self.recovery_hfm_closed) and (self.recovery_equiti_ticket and not self.recovery_equiti_closed):
                    time.sleep(0.02)
                if self.recovery_hfm_ticket and not self.recovery_hfm_closed:
                    self.hfm_cmd_send.send({"action": Command.CLOSE.value, "ticket": self.recovery_hfm_ticket})
                return  # Stay in CLOSING_RECOVERY
            
            print("[MASTER] No orphans found. Moving to scanning...")
            self.last_failure_time = time.time()
            self._reset_recovery_state()
            
            # Refresh settings and lot before returning to scanning
            self.reload_settings()
            self._calculate_lot_from_balances()
            self.hfm_config["lot_size"] = self.calculated_lot
            self.equiti_config["lot_size"] = self.calculated_lot
            self._sync_lot_to_terminals()  # Pre-type new lot into terminals
            
            self.state = State.SCANNING
            return
        
        # Retry logic - Progressive backoff (10s -> 15s -> 20s)
        # Initial attempt was at 0s (on entry)
        time_since_retry = time.time() - self.recovery_last_retry_time
        
        # Determine current interval based on attempt count
        # Attempt 0 was the initial entry
        if self.recovery_retry_count == 0:
            current_interval = 10.0
        elif self.recovery_retry_count == 1:
            current_interval = 15.0
        else:
            current_interval = 20.0  # Max out at 20s
            
        if time_since_retry >= current_interval:
            print(f"\n[MASTER] Retrying recovery closes (elapsed: {elapsed:.0f}s, interval: {current_interval}s)...")
            if not self.recovery_equiti_closed and self.recovery_equiti_ticket:
                self.equiti_cmd_send.send({"action": Command.CLOSE.value, "ticket": self.recovery_equiti_ticket})
            if (not self.recovery_hfm_closed and self.recovery_hfm_ticket) and (not self.recovery_equiti_closed and self.recovery_equiti_ticket):
                time.sleep(0.02)  # 20ms gap
            if not self.recovery_hfm_closed and self.recovery_hfm_ticket:
                self.hfm_cmd_send.send({"action": Command.CLOSE.value, "ticket": self.recovery_hfm_ticket})
            
            self.recovery_last_retry_time = time.time()
            self.recovery_retry_count += 1
        
        # Print status (throttled to avoid spam)
        hfm_status = "CLOSED" if self.recovery_hfm_closed else "pending"
        eq_status = "CLOSED" if self.recovery_equiti_closed else "pending"
        print(f"\r[CLOSING_RECOVERY] HFM: {hfm_status} | EQUITI: {eq_status} | Elapsed: {elapsed:.0f}s   ", end="", flush=True)
    
    def _reset_recovery_state(self):
        """Reset recovery tracking state."""
        self.recovery_hfm_closed = False
        self.recovery_equiti_closed = False
        self.recovery_start_time = None
        self.recovery_hfm_ticket = None
        self.recovery_equiti_ticket = None
        self.recovery_last_retry_time = None
        self.recovery_retry_count = 0
    
    def _check_and_close_orphans(self) -> bool:
        """Check for and close any orphan positions. Returns True if orphans found."""
        # This runs AFTER cooldown to catch any positions that slipped through
        # Uses symbol-based lookup (since magic=0 is used to hide expert origin)
        
        # Request position check from both workers
        self.hfm_cmd_send.send({"action": "CHECK_ORPHANS"})
        self.equiti_cmd_send.send({"action": "CHECK_ORPHANS"})
        
        # Process responses with short timeout
        orphan_found = False
        timeout = 1.0
        start = time.time()
        hfm_responded = False
        equiti_responded = False
        
        while time.time() - start < timeout and not (hfm_responded and equiti_responded):
            if self.hfm_data_recv.poll(0.01):
                msg = self.hfm_data_recv.recv()
                if msg["type"] == "ORPHAN_POSITIONS":
                    hfm_responded = True
                    for ticket in msg["tickets"]:
                        print(f"[MASTER] Found HFM orphan position #{ticket} - will close")
                        self.recovery_hfm_ticket = ticket
                        orphan_found = True
                elif msg["type"] == "TICK":
                    self.hfm_tick = msg["data"]
            
            if self.equiti_data_recv.poll(0.01):
                msg = self.equiti_data_recv.recv()
                if msg["type"] == "ORPHAN_POSITIONS":
                    equiti_responded = True
                    for ticket in msg["tickets"]:
                        print(f"[MASTER] Found EQUITI orphan position #{ticket} - will close")
                        self.recovery_equiti_ticket = ticket
                        orphan_found = True
                elif msg["type"] == "TICK":
                    self.equiti_tick = msg["data"]
        
        if orphan_found:
            print("[MASTER] Orphan positions found! Entering CLOSING_RECOVERY...")
            self._enter_closing_recovery()
        
        return orphan_found
    
    def reload_settings(self):
        """
        Reload settings from the global config module.
        Must be called before entering SCANNING phase to ensure fresh settings.
        """
        import config
        
        # 1. Update master config dict
        self.config["min_gap"] = config.MIN_ENTRY_GAP
        self.config["max_spread"] = getattr(config, 'MAX_SPREAD', 0.00020)
        self.config["exit_reversal_gap"] = getattr(config, 'EXIT_REVERSAL_GAP', config.MIN_ENTRY_GAP)
        self.config["min_hold"] = config.MIN_HOLD_TIME
        self.config["target_profit"] = config.TARGET_NET_PROFIT
        self.config["exit_slippage_buffer"] = getattr(config, 'EXIT_SLIPPAGE_BUFFER', 0.0)
        self.config["execution_timeout"] = getattr(config, 'EXECUTION_TIMEOUT', 1.0)
        self.config["min_entry_point_diff"] = getattr(config, 'MIN_ENTRY_POINT_DIFF', 0)
        self.config["slippage"] = config.SLIPPAGE
        
        # Update delays
        self.opportunity_confirm_delay = getattr(config, 'OPPORTUNITY_CONFIRM_DELAY', 0.1)
        self.exit_confirm_delay = getattr(config, 'EXIT_CONFIRM_DELAY', 0.5)
        self.cooldown_seconds = getattr(config, 'FAILURE_COOLDOWN', 30)
        
        # Update trade delay
        self.min_trade_delay = getattr(config, 'MIN_TRADE_DELAY', 0.0)
        self.max_trade_delay = getattr(config, 'MAX_TRADE_DELAY', 0.0)
        
        # Update lot sizing (so dashboard changes take effect between trades)
        self.min_lot_size = getattr(config, 'MIN_LOT_SIZE', 0.01)
        self.max_lot_size = getattr(config, 'MAX_LOT_SIZE', 4.8)
        self.lot_per_base = getattr(config, 'LOT_PER_BASE', 0.35)
        self.lot_base_amount = getattr(config, 'LOT_BASE_AMOUNT', 100)
        self.config["min_lot_size"] = self.min_lot_size
        self.config["max_lot_size"] = self.max_lot_size
        
        # Update recovery config
        self.recovery_lot_size = getattr(config, 'RECOVERY_LOT_SIZE', 0.05)
        self.recovery_trade_count = getattr(config, 'RECOVERY_TRADE_COUNT', 2)
        
        # Update trade execution mode
        self.config["trade_mode"] = getattr(config, 'TRADE_MODE', 'API')
        
        # 2. Update worker configs
        self.hfm_config.update(self.config)
        self.equiti_config.update(self.config)
        
        print(f"[MASTER] Settings Reloaded! Min Gap: {self.config['min_gap']:.5f}, Hold: {self.config['min_hold']}s")

    def _reset_trade_state(self):
        """Reset trade state for next cycle."""
        self.hfm_ticket = None
        self.equiti_ticket = None
        self.hfm_trade_type = None
        self.equiti_trade_type = None
        self.trade_start_time = None
        self.hfm_pnl = None
        self.equiti_pnl = None
        self.opportunity_type = None
        # Reset exit confirmation state
        self.pending_exit = False
        self.pending_exit_time = None
        self.pending_exit_reason = None
        self.pending_exit_details = None
        # Note: lot_recovery_mode and shutdown_after_trade are NOT reset here - they persist across trades
    
    def shutdown(self):
        """Gracefully shut down the bot."""
        print("\n[MASTER] Initiating shutdown...")
        self.running = False
        
        if self.hfm_cmd_send:
            try:
                self.hfm_cmd_send.send({"action": Command.SHUTDOWN.value})
            except:
                pass
        
        if self.equiti_cmd_send:
            try:
                self.equiti_cmd_send.send({"action": Command.SHUTDOWN.value})
            except:
                pass
        
        if self.hfm_process and self.hfm_process.is_alive():
            self.hfm_process.join(timeout=5)
            if self.hfm_process.is_alive():
                self.hfm_process.terminate()
        
        if self.equiti_process and self.equiti_process.is_alive():
            self.equiti_process.join(timeout=5)
            if self.equiti_process.is_alive():
                self.equiti_process.terminate()
        
        print("[MASTER] Shutdown complete")


def main():
    bot = HedgedLockBot()
    bot.start()


if __name__ == "__main__":
    main()
