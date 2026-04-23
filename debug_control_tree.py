"""
Quick test: Run the color-based pixel scan on both MT5 terminals.
This verifies whether the new fallback detection in mt5_clicker.py works.

Run while both MT5 terminals are OPEN with One-Click Trading panel visible.
"""
import sys
sys.path.insert(0, '.')
from mt5_clicker import MT5Clicker

HFM_TERMINAL = r"C:\MT5_HFM\terminal64.exe"
EQUITI_TERMINAL = r"C:\MT5_Equiti\terminal64.exe"

def test_clicker(name, terminal_path, symbol):
    print(f"\n{'='*50}")
    print(f"  Testing {name}")
    print(f"{'='*50}")
    
    clicker = MT5Clicker(name, terminal_path, symbol)
    
    # Connect
    if not clicker.connect():
        print(f"FAILED to connect to {name}")
        return
    
    print(f"Connected! Window: {clicker.main_window.window_text()}")
    
    # Try caching coordinates (this now uses color scan as fallback)
    success = clicker.cache_coordinates()
    
    if success:
        print(f"\n✅ SUCCESS! Cached coordinates:")
        print(f"   SELL: {clicker._cached_sell_coords}")
        print(f"   BUY:  {clicker._cached_buy_coords}")
        
        # Calculate volume field position
        if clicker._cached_sell_coords and clicker._cached_buy_coords:
            vol_x = (clicker._cached_sell_coords[0] + clicker._cached_buy_coords[0]) // 2
            vol_y = clicker._cached_sell_coords[1]
            print(f"   VOL:  ({vol_x}, {vol_y})")
    else:
        print(f"\n❌ FAILED to detect buttons")
    
    clicker.close()

if __name__ == "__main__":
    test_clicker("HFM", HFM_TERMINAL, "EURUSDb")
    test_clicker("EQUITI", EQUITI_TERMINAL, "EURUSD.pr")
    print("\nDone!")
    input("Press Enter to exit...")
