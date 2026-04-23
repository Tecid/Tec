"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  DISPLAY FUNCTIONS - HEDGED LOCK ARBITRAGE BOT                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  This module contains all console output functions.                          ║
║  All print/stdout operations are centralized here for clean separation.      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys


# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def print_banner(config: dict):
    """Print the startup banner with configuration."""
    print("=" * 70)
    print("  HEDGED LOCK LATENCY ARBITRAGE BOT")
    print("=" * 70)
    print(f"  HFM Symbol:    {config.get('hfm_symbol', config.get('symbol', 'N/A'))}")
    print(f"  Equiti Symbol: {config.get('equiti_symbol', config.get('symbol', 'N/A'))}")
    min_lot = config.get('min_lot_size', 0.01)
    max_lot = config.get('max_lot_size', 4.8)
    print(f"  Lot Range:     {min_lot} - {max_lot} (random per trade)")
    print(f"  Min Entry Gap: {config['min_gap']:.5f} ({int(config['min_gap'] * 100000)} pts)")
    print(f"  Max Spread:    {config['max_spread']:.5f} ({int(config['max_spread'] * 100000)} pts)")
    print(f"  Exit Reversal: {config['exit_reversal_gap']:.5f} ({int(config['exit_reversal_gap'] * 100000)} pts)")
    print(f"  Min Hold:      {config['min_hold']}s")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════════════════════
# SCANNING PHASE DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def print_scanning(hfm_bid, hfm_ask, eq_bid, eq_ask, gap_alpha, gap_beta, min_gap):
    """
    Print real-time scanning status (single line, updates in place).
    
    Format: [SCANNING] HFM: bid/ask (sp:X) | EQ: bid/ask (sp:X) | α=+X β=-X (need Y)
    """
    hfm_spread = int((hfm_ask - hfm_bid) * 100000)
    eq_spread = int((eq_ask - eq_bid) * 100000)
    
    sys.stdout.write("\r")
    sys.stdout.write(
        f"[SCANNING] HFM: {hfm_bid:.5f}/{hfm_ask:.5f} (sp:{hfm_spread}) | "
        f"EQ: {eq_bid:.5f}/{eq_ask:.5f} (sp:{eq_spread}) | "
        f"α={gap_alpha:+d} β={gap_beta:+d} (need {min_gap})   "
    )
    sys.stdout.flush()


def print_spread_filter(hfm_bid, hfm_ask, eq_bid, eq_ask, wide_brokers, max_spread_pts):
    """Print spread filter warning when spreads are too wide."""
    sys.stdout.write("\r")
    sys.stdout.write(
        f"[SPREAD FILTER] Skipping - {', '.join(wide_brokers)} > {max_spread_pts}pts. "
        f"HFM:{hfm_bid:.5f}/{hfm_ask:.5f} | EQ:{eq_bid:.5f}/{eq_ask:.5f}   "
    )
    sys.stdout.flush()


def print_cooldown(remaining: float):
    """Print cooldown status after failed trade."""
    sys.stdout.write("\r")
    sys.stdout.write(f"[COOLDOWN] Waiting {remaining:.0f}s before retry...   ")
    sys.stdout.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# TRADE EXECUTION DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def print_opportunity(opp_type: str, gap: float, gap_pts: int, min_gap: float, 
                      min_gap_pts: int, action_a: str, price_a: float,
                      action_b: str, price_b: float):
    """
    Print opportunity detection message with full details.
    
    ══════════════════════════════════════════════════════════════════════════
      *** OPPORTUNITY ALPHA/BETA DETECTED ***
      Gap = X.XXXXX (XX pts) >= Y.YYYYY (YY pts)
      Action: BUY/SELL HFM @ X.XXXXX | SELL/BUY EQUITI @ Y.YYYYY
    ══════════════════════════════════════════════════════════════════════════
    """
    print(f"\n{'='*70}")
    print(f"  *** OPPORTUNITY {opp_type} DETECTED ***")
    print(f"  Gap = {gap:.5f} ({gap_pts} pts) >= {min_gap:.5f} ({min_gap_pts} pts)")
    print(f"  Intended: {action_a} HFM @ {price_a:.5f} | {action_b} EQUITI @ {price_b:.5f}")
    print(f"  (Actual fill prices will be reported after execution)")
    print(f"{'='*70}")


def print_trade_result(broker: str, success: bool, ticket: int = None, 
                       price: float = None, error: str = None):
    """Print trade execution result."""
    if success:
        print(f"[MASTER] {broker} FILLED: Ticket #{ticket} @ {price:.5f} (actual fill)")
    else:
        print(f"[MASTER] {broker} trade FAILED: {error}")


def print_close_result(broker: str, success: bool, price: float = None, error: str = None):
    """Print position close result."""
    if success:
        print(f"[MASTER] {broker} position closed @ {price:.5f}")
    else:
        print(f"[MASTER] {broker} close FAILED: {error}")


# ═══════════════════════════════════════════════════════════════════════════════
# HOLDING PHASE DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def print_holding(elapsed: float, min_hold: float, opp_type: str,
                  hfm_type: str, hfm_pnl: float, eq_type: str, eq_pnl: float,
                  net_pnl: float, target: float, reversal_pts: int = 0, exit_pts: int = 0):
    """
    Print holding status with PnL info (single line, updates in place).
    
    Format: [HOLD M:SS/M:SS] TYPE | Rev: X/Y pts | HFM: $+X | EQ: $+X | NET: $+X
    """
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    hold_mins = int(min_hold // 60)
    hold_secs = int(min_hold % 60)
    
    # Show OK when reversal target is met
    rev_status = "[OK]" if reversal_pts >= exit_pts and exit_pts > 0 else ""
    
    sys.stdout.write("\r")
    sys.stdout.write(
        f"[HOLD {mins}:{secs:02d}/{hold_mins}:{hold_secs:02d}] {opp_type} | "
        f"Rev: {reversal_pts:+d}/{exit_pts} pts {rev_status} | "
        f"HFM({hfm_type}): ${hfm_pnl:+.2f} | EQ({eq_type}): ${eq_pnl:+.2f} | "
        f"NET: ${net_pnl:+.2f}   "
    )
    sys.stdout.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# EXIT PHASE DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def print_exit(reason: str, details: str):
    """
    Print exit trigger message.
    
    ══════════════════════════════════════════════════════════════════════════
      *** EXIT: REASON ***
      Details...
    ══════════════════════════════════════════════════════════════════════════
    """
    print(f"\n{'='*70}")
    print(f"  *** EXIT: {reason} ***")
    print(f"  {details}")
    print(f"{'='*70}")


def print_cycle_complete(opp_type: str, final_pnl: float):
    """Print trade cycle completion message."""
    print(f"[MASTER] Trade cycle complete ({opp_type}). Final Net PnL: ${final_pnl:.2f}")
    print("=" * 70)
