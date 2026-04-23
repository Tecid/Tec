"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  TRADING STRATEGY LOGIC - HEDGED LOCK ARBITRAGE BOT                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  This module contains all the core calculations and decision-making.         ║
║  All functions are PURE (no side effects) making them easy to test.          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from states import OpportunityType


# ═══════════════════════════════════════════════════════════════════════════════
# SPREAD CALCULATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_spreads(tick_a: dict, tick_b: dict) -> tuple:
    """
    Calculate spreads for both brokers.
    
    Spread = Ask - Bid (what the broker takes as their cut)
    
    Returns:
        (spread_a, spread_b, spread_a_points, spread_b_points)
    """
    spread_a = tick_a["ask"] - tick_a["bid"]
    spread_b = tick_b["ask"] - tick_b["bid"]
    return (
        spread_a, 
        spread_b, 
        round(spread_a * 100000),  # Bug #1 fix: round() instead of int()
        round(spread_b * 100000)
    )


def check_spread_filter(tick_a: dict, tick_b: dict, max_spread: float) -> tuple:
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ MAX SPREAD FILTER                                                       │
    │ If EITHER broker's spread exceeds the limit, we do NOT trade.           │
    │                                                                         │
    │ This protects against:                                                  │
    │   - Low liquidity periods (Asian session, holidays)                     │
    │   - Volatile news events where spreads widen                            │
    │   - Broker issues or requotes                                           │
    └─────────────────────────────────────────────────────────────────────────┘
    
    Returns:
        (passes_filter: bool, wide_brokers: list[str])
    """
    spread_a, spread_b, pts_a, pts_b = calculate_spreads(tick_a, tick_b)
    
    wide_brokers = []
    if spread_a > max_spread:
        wide_brokers.append(f"HFM:{pts_a}pts")
    if spread_b > max_spread:
        wide_brokers.append(f"EQ:{pts_b}pts")
    
    return (len(wide_brokers) == 0, wide_brokers)


# ═══════════════════════════════════════════════════════════════════════════════
# GAP CALCULATIONS - THE HEART OF UNIVERSAL ARBITRAGE LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_gaps(tick_a: dict, tick_b: dict) -> tuple:
    """
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  UNIVERSAL ARBITRAGE LOGIC - GAP CALCULATION                             ║
    ╠══════════════════════════════════════════════════════════════════════════╣
    ║                                                                          ║
    ║  We calculate TWO potential profit opportunities every tick:             ║
    ║                                                                          ║
    ║  ┌────────────────────────────────────────────────────────────────────┐  ║
    ║  │ OPPORTUNITY ALPHA (Long A / Short B):                              │  ║
    ║  │   Gap_Alpha = Bid_B - Ask_A                                        │  ║
    ║  │                                                                    │  ║
    ║  │   "Can I BUY on HFM and SELL on Equiti profitably?"                │  ║
    ║  │   • We PAY Ask_A (HFM's ask price to go long)                      │  ║
    ║  │   • We RECEIVE Bid_B (Equiti's bid price to go short)              │  ║
    ║  │   • If Gap_Alpha > 0, we make money!                               │  ║
    ║  │                                                                    │  ║
    ║  │   WHY IT WORKS:                                                    │  ║
    ║  │   If HFM has a 5-point spread, Ask_A is HIGH, so Gap_Alpha         │  ║
    ║  │   goes NEGATIVE → Bot does NOT trade → Saves us from loss!         │  ║
    ║  └────────────────────────────────────────────────────────────────────┘  ║
    ║                                                                          ║
    ║  ┌────────────────────────────────────────────────────────────────────┐  ║
    ║  │ OPPORTUNITY BETA (Long B / Short A):                               │  ║
    ║  │   Gap_Beta = Bid_A - Ask_B                                         │  ║
    ║  │                                                                    │  ║
    ║  │   "Can I BUY on Equiti and SELL on HFM profitably?"                │  ║
    ║  │   • We PAY Ask_B (Equiti's ask price to go long)                   │  ║
    ║  │   • We RECEIVE Bid_A (HFM's bid price to go short)                 │  ║
    ║  │   • If Gap_Beta > 0, we make money!                                │  ║
    ║  │                                                                    │  ║
    ║  │   WHY IT WORKS:                                                    │  ║
    ║  │   If Equiti suddenly gets a spread, Ask_B goes UP, so Gap_Beta     │  ║
    ║  │   goes NEGATIVE → Bot does NOT trade → Saves us from loss!         │  ║
    ║  └────────────────────────────────────────────────────────────────────┘  ║
    ║                                                                          ║
    ║  A positive gap means PURE PROFIT after spread costs are paid!           ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    
    Returns:
        (gap_alpha, gap_beta, gap_alpha_points, gap_beta_points)
    """
    gap_alpha = tick_b["bid"] - tick_a["ask"]
    gap_beta = tick_a["bid"] - tick_b["ask"]
    return (
        gap_alpha,
        gap_beta,
        round(gap_alpha * 100000),  # Bug #1 fix: round() instead of int()
        round(gap_beta * 100000)
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY TRIGGER DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def check_entry_trigger(gap_alpha: float, gap_beta: float, 
                        min_gap: float) -> OpportunityType | None:
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ TRIGGER CONDITION                                                       │
    │                                                                         │
    │ Gap >= MIN_ENTRY_GAP (e.g., 5 points = 0.00005)                         │
    │                                                                         │
    │ IMPORTANT: We use INTEGER POINT comparison to avoid floating-point      │
    │ precision issues. 0.00004999 should NOT trigger a 5-point threshold!    │
    │                                                                         │
    │ Because we use execution prices (Bid - Ask), a positive gap means       │
    │ PURE PROFIT after spread costs. The math has already accounted for      │
    │ the spread!                                                             │
    └─────────────────────────────────────────────────────────────────────────┘
    
    Returns:
        OpportunityType.ALPHA, OpportunityType.BETA, or None
    """
    # Bug #1 fix: Compare integer points to ensure display matches logic
    gap_alpha_pts = round(gap_alpha * 100000)
    gap_beta_pts = round(gap_beta * 100000)
    min_gap_pts = round(min_gap * 100000)
    
    if gap_alpha_pts >= min_gap_pts:
        return OpportunityType.ALPHA
    elif gap_beta_pts >= min_gap_pts:
        return OpportunityType.BETA
    return None


def get_trade_actions(opp_type: OpportunityType) -> tuple:
    """
    Get the trade actions for each broker based on opportunity type.
    
    ALPHA: BUY HFM (Long A), SELL Equiti (Short B)
    BETA:  SELL HFM (Short A), BUY Equiti (Long B)
    
    Returns:
        (hfm_action, equiti_action) - "BUY" or "SELL"
    """
    if opp_type == OpportunityType.ALPHA:
        return ("BUY", "SELL")
    else:
        return ("SELL", "BUY")


# ═══════════════════════════════════════════════════════════════════════════════
# EXIT LOGIC - PRICE REVERSAL DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_reversal_gap(tick_a: dict, tick_b: dict, 
                           opp_type: OpportunityType) -> tuple:
    """
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  PRICE REVERSAL DETECTION                                                ║
    ╠══════════════════════════════════════════════════════════════════════════╣
    ║                                                                          ║
    ║  After entry, we wait for prices to converge. If they converge AND       ║
    ║  flip in our direction, we can exit at profit.                           ║
    ║                                                                          ║
    ║  ┌────────────────────────────────────────────────────────────────────┐  ║
    ║  │ If we are ALPHA (Long A / Short B):                                │  ║
    ║  │   Reversal Gap = Bid_A - Ask_B                                     │  ║
    ║  │   (Now we could profit by doing the OPPOSITE - BETA)               │  ║
    ║  │   The lag has caught up and PASSED the other broker!               │  ║
    ║  ├────────────────────────────────────────────────────────────────────┤  ║
    ║  │ If we are BETA (Long B / Short A):                                 │  ║
    ║  │   Reversal Gap = Bid_B - Ask_A                                     │  ║
    ║  │   (Same logic - prices have now reversed)                          │  ║
    ║  └────────────────────────────────────────────────────────────────────┘  ║
    ║                                                                          ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    
    Returns:
        (reversal_gap, reversal_gap_points)
    """
    if opp_type == OpportunityType.ALPHA:
        gap = tick_a["bid"] - tick_b["ask"]
    else:
        gap = tick_b["bid"] - tick_a["ask"]
    
    return (gap, round(gap * 100000))  # Bug #1 fix: round() instead of int()


def calculate_net_pnl(pnl_a: dict | None, pnl_b: dict | None) -> float:
    """
    Calculate combined net PnL from both positions.
    
    Net PnL = HFM profit + Equiti profit
    
    Returns:
        Combined net profit in dollars
    """
    net = 0.0
    if pnl_a:
        net += pnl_a.get("net_profit", 0)
    if pnl_b:
        net += pnl_b.get("net_profit", 0)
    return net


def check_exit_conditions(elapsed: float, min_hold: float, net_pnl: float,
                          target_profit: float, reversal_gap: float = 0,
                          exit_reversal_gap: float = 0) -> tuple:
    """
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  EXIT CONDITIONS                                                         ║
    ╠══════════════════════════════════════════════════════════════════════════╣
    ║                                                                          ║
    ║  CONSTRAINTS:                                                            ║
    ║    • Must hold for minimum hold time (MIN_HOLD_TIME seconds)             ║
    ║                                                                          ║
    ║  EXIT TRIGGERS (after min hold time) - whichever comes first:            ║
    ║                                                                          ║
    ║    1. NET PROFIT TARGET:                                                 ║
    ║       Combined PnL from both positions >= TARGET_NET_PROFIT              ║
    ║                                                                          ║
    ║    2. PRICE REVERSAL:                                                    ║
    ║       Gap has reversed by EXIT_REVERSAL_GAP (10pt total swing)           ║
    ║                                                                          ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    
    Returns:
        (should_exit: bool, reason: str, details: str)
    """
    timer_ok = elapsed >= min_hold
    
    if not timer_ok:
        return (False, None, None)
    
    # Exit condition 1 (PRIMARY): Price reversal / Gap convergence
    # This is the DETERMINISTIC exit - based purely on price action
    # BUG FIX: Use integer point comparison (like entry) to avoid floating-point drift
    reversal_pts = round(reversal_gap * 100000)
    exit_pts = round(exit_reversal_gap * 100000)
    if exit_pts > 0 and reversal_pts >= exit_pts:
        return (
            True,
            "PRICE REVERSAL DETECTED", 
            f"Timer: {elapsed:.0f}s | Reversal: {reversal_pts} pts >= {exit_pts} pts"
        )
    
    # Exit condition 2 (SECONDARY): Dollar profit target
    # Only used if TARGET_NET_PROFIT > 0 (disabled by default for point-based strategy)
    if target_profit > 0 and net_pnl >= target_profit:
        return (
            True, 
            "PROFIT TARGET REACHED",
            f"Timer: {elapsed:.0f}s | Net PnL: ${net_pnl:.2f} >= ${target_profit:.2f}"
        )
    
    return (False, None, None)
