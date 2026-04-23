"""
MT5 Control Discovery Script
Run this script with MT5 terminals open to discover the exact control names
for Buy/Sell buttons and volume fields.

Usage:
    python discover_mt5_controls.py

Output:
    Lists all MT5 windows and their control trees.
    Look for Buy/Sell buttons and Edit/ComboBox fields near them.
"""

import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mt5_clicker import MT5Clicker, find_all_mt5_windows, PYWINAUTO_AVAILABLE

def main():
    if not PYWINAUTO_AVAILABLE:
        print("=" * 60)
        print("ERROR: pywinauto is not installed!")
        print("Run: pip install pywinauto")
        print("=" * 60)
        return
    
    print("=" * 60)
    print("  MT5 CONTROL DISCOVERY TOOL")
    print("=" * 60)
    print()
    print("Scanning for MetaTrader 5 windows...")
    print()
    
    # Find all MT5 windows
    windows = find_all_mt5_windows()
    
    if not windows:
        print("[X] No MetaTrader 5 windows found!")
        print()
        print("Make sure:")
        print("  1. MT5 terminals are running")
        print("  2. The terminals are not minimized to system tray")
        print("  3. This script is run as the same user as MT5")
        return
    
    print(f"[OK] Found {len(windows)} MT5 window(s):")
    print()
    
    for i, win_info in enumerate(windows):
        print(f"  [{i + 1}] {win_info['title']}")
        print(f"      Handle: {win_info['handle']}")
        print(f"      PID: {win_info['process_id']}")
        rect = win_info['rect']
        print(f"      Position: ({rect.left}, {rect.top}) - ({rect.right}, {rect.bottom})")
        print()
    
    # Inspect each window
    for i, win_info in enumerate(windows):
        print("=" * 60)
        print(f"  INSPECTING WINDOW [{i + 1}]: {win_info['title']}")
        print("=" * 60)
        print()
        
        # Create a clicker instance just for inspection
        clicker = MT5Clicker(
            broker_name=f"Window_{i + 1}",
            terminal_path="",  # Not used for inspection
            symbol="EURUSD"
        )
        
        # Connect using the window handle
        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(handle=win_info['handle'])
            clicker.app = app
            clicker.main_window = app.window(handle=win_info['handle'])
            clicker._connected = True
        except Exception as e:
            print(f"  [X] Cannot connect: {e}")
            continue
        
        # Look for specific trading controls
        print("  [i] SEARCHING FOR TRADING CONTROLS...")
        print()
        
        try:
            descendants = clicker.main_window.descendants()
            
            buy_buttons = []
            sell_buttons = []
            edit_fields = []
            
            for child in descendants:
                try:
                    text = child.window_text().strip()
                    control_type = child.element_info.control_type
                    class_name = child.element_info.class_name or ""
                    rect = child.rectangle()
                    
                    # Check for Buy buttons
                    if text and "buy" in text.lower() and control_type == "Button":
                        buy_buttons.append({
                            "text": text,
                            "type": control_type,
                            "class": class_name,
                            "rect": f"({rect.left},{rect.top})-({rect.right},{rect.bottom})"
                        })
                    
                    # Check for Sell buttons
                    if text and "sell" in text.lower() and control_type == "Button":
                        sell_buttons.append({
                            "text": text,
                            "type": control_type,
                            "class": class_name,
                            "rect": f"({rect.left},{rect.top})-({rect.right},{rect.bottom})"
                        })
                    
                    # Check for Edit fields (potential volume inputs)
                    if control_type in ["Edit", "ComboBox"] and text:
                        try:
                            float(text.replace(",", "."))
                            edit_fields.append({
                                "text": text,
                                "type": control_type,
                                "class": class_name,
                                "rect": f"({rect.left},{rect.top})-({rect.right},{rect.bottom})"
                            })
                        except ValueError:
                            pass
                            
                except Exception:
                    continue
            
            # Print results
            if buy_buttons:
                print(f"  [OK] BUY BUTTONS FOUND ({len(buy_buttons)}):")
                for btn in buy_buttons:
                    print(f"     Text: '{btn['text']}' | Type: {btn['type']} | Class: {btn['class']} | Rect: {btn['rect']}")
            else:
                print("  [X] No Buy buttons found")
            print()
            
            if sell_buttons:
                print(f"  [OK] SELL BUTTONS FOUND ({len(sell_buttons)}):")
                for btn in sell_buttons:
                    print(f"     Text: '{btn['text']}' | Type: {btn['type']} | Class: {btn['class']} | Rect: {btn['rect']}")
            else:
                print("  [X] No Sell buttons found")
            print()
            
            if edit_fields:
                print(f"  [OK] NUMERIC EDIT FIELDS ({len(edit_fields)}):")
                for field in edit_fields:
                    print(f"     Value: '{field['text']}' | Type: {field['type']} | Class: {field['class']} | Rect: {field['rect']}")
            else:
                print("  [!!]  No numeric edit fields found")
            print()
            
            if not buy_buttons and not sell_buttons:
                print("  [!!]  ONE-CLICK TRADING PANEL may not be enabled!")
                print("  To enable: Right-click on the chart → One-Click Trading")
                print("  Or press Alt+T in the MT5 terminal")
                print()
            
        except Exception as e:
            print(f"  [X] Error scanning controls: {e}")
        
        # Optionally dump full control tree
        print("-" * 40)
        user_input = input(f"  Dump full control tree for Window [{i + 1}]? (y/n): ").strip().lower()
        if user_input == 'y':
            print()
            print(clicker.get_control_tree())
        print()
        
        clicker.close()
    
    print("=" * 60)
    print("  DISCOVERY COMPLETE")
    print("=" * 60)
    print()
    print("If buttons were found, the clicker bot should work with your terminals.")
    print("If not, enable One-Click Trading: Right-click chart → One-Click Trading")


if __name__ == "__main__":
    main()
