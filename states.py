"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  STATE DEFINITIONS - HEDGED LOCK ARBITRAGE BOT                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  This module contains all enums and state definitions used by the bot.       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from enum import Enum


class State(Enum):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ BOT STATE MACHINE                                                       │
    │                                                                         │
    │ Normal Flow: INITIALIZING → SCANNING → EXECUTING → HOLDING → EXIT →    │
    │              SCANNING                                                   │
    │                                                                         │
    │ Recovery Flow: EXECUTING (failure) → CLOSING_RECOVERY → SCANNING       │
    │                                                                         │
    │ INITIALIZING:     Starting up, connecting to brokers                    │
    │ SCANNING:         Looking for arbitrage opportunities                   │
    │ EXECUTING:        Trade orders sent, waiting for confirmation           │
    │ HOLDING:          Positions open, monitoring for exit                   │
    │ EXIT:             Closing positions                                     │
    │ CLOSING_RECOVERY: Waiting for all positions to close after failure     │
    │ SHUTDOWN:         Shutting down the bot                                 │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    INITIALIZING = "INITIALIZING"
    SCANNING = "SCANNING"
    EXECUTING = "EXECUTING"
    HOLDING = "HOLDING"
    EXIT = "EXIT"
    CLOSING_RECOVERY = "CLOSING_RECOVERY"
    SHUTDOWN = "SHUTDOWN"


class OpportunityType(Enum):
    """
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║  OPPORTUNITY TYPES - WHICH DIRECTION ARE WE TRADING?                     ║
    ╠══════════════════════════════════════════════════════════════════════════╣
    ║                                                                          ║
    ║  ALPHA (Long Broker A / Short Broker B):                                 ║
    ║  ───────────────────────────────────────                                 ║
    ║  • We BUY at Broker A's ASK price (what we PAY to enter long)            ║
    ║  • We SELL at Broker B's BID price (what we RECEIVE to enter short)      ║
    ║  • Entry Profit = Bid_B - Ask_A                                          ║
    ║  • Triggers when: HFM is lagging (too low) OR Equiti spiked up           ║
    ║                                                                          ║
    ║  BETA (Long Broker B / Short Broker A):                                  ║
    ║  ───────────────────────────────────────                                 ║
    ║  • We BUY at Broker B's ASK price (what we PAY to enter long)            ║
    ║  • We SELL at Broker A's BID price (what we RECEIVE to enter short)      ║
    ║  • Entry Profit = Bid_A - Ask_B                                          ║
    ║  • Triggers when: Equiti is lagging (too low) OR HFM spiked up           ║
    ║                                                                          ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    ALPHA = "ALPHA"
    BETA = "BETA"
