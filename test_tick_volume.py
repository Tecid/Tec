"""
Standalone Tick Volume Test
===========================
Tests the get_avg_tick_volume() logic for both HFM and Equiti terminals.
"""

import MetaTrader5 as mt5
import math
import argparse
import time
import sys

def get_avg_tick_volume(symbol: str, window_seconds: int) -> dict | None:
    """
    Calculate average tick volume per minute over a rolling time window.
    Uses M1 (1-minute) bars for efficiency.
    """
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
        "window_seconds": window_seconds,
        "raw_rates": rates
    }

def fetch_broker_data(name, path, symbol, window):
    print(f"\n  [{name}] Connecting to {path}...")
    if not mt5.initialize(path=path):
        print(f"  ❌ MT5 initialization failed: {mt5.last_error()}")
        return
    
    info = mt5.terminal_info()
    print(f"  ✅ Connected! Company: {info.company}")
    
    result = get_avg_tick_volume(symbol, window)
    if result is None:
        print(f"  ❌ No data returned for {symbol} (market may be closed or symbol incorrect)")
    else:
        print(f"    Symbol:            {symbol}")
        print(f"    Average Tick Vol:  {result['avg_tick_vol']} ticks/min")
        print(f"    Total Ticks:       {result['total_ticks']}")
        print(f"    Bars Used:         {result['bars_used']} (M1 bars)")
        
        print(f"\n    Raw M1 bar tick volumes:")
        from datetime import datetime
        for i, rate in enumerate(result['raw_rates']):
            bar_time = datetime.fromtimestamp(rate['time']).strftime('%H:%M')
            print(f"      Bar {i+1} ({bar_time}): {int(rate['tick_volume'])} ticks")
            
    mt5.shutdown()

def main():
    parser = argparse.ArgumentParser(description="Test tick volume calculation")
    parser.add_argument("--window", type=int, default=200, help="Window in seconds (default: 200)")
    parser.add_argument("--repeat", type=int, default=1, help="Number of times to repeat (use 0 for continuous)")
    args = parser.parse_args()

    print("=" * 60)
    print("  DUAL BROKER TICK VOLUME TEST")
    print("=" * 60)
    print(f"   Window: {args.window} seconds ({args.window / 60:.1f} minutes)")
    
    brokers = [
        {"name": "HFM", "path": r"C:\MT5_HFM\terminal64.exe", "symbol": "EURUSDb"},
        {"name": "Equiti", "path": r"C:\MT5_Equiti\terminal64.exe", "symbol": "EURUSD.pr"}
    ]
    
    iteration = 0
    try:
        while True:
            iteration += 1
            print(f"\n{'─' * 60}")
            print(f"  Calculation #{iteration}  |  {time.strftime('%H:%M:%S')}")
            print(f"{'─' * 60}")
            
            for broker in brokers:
                fetch_broker_data(broker["name"], broker["path"], broker["symbol"], args.window)
            
            if args.repeat != 0 and iteration >= args.repeat:
                break
            
            print(f"\n  ⏳ Next calculation in {args.window}s... (Ctrl+C to stop)")
            time.sleep(args.window)
            
    except KeyboardInterrupt:
        print("\n\n  Stopped by user.")

if __name__ == "__main__":
    main()
