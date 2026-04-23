"""
MT5 Ultra-Low Latency Clicker
Uses win32api raw mouse injection for ~6-10ms click-to-click execution.

Detection Priority:
  1. Dashboard-configured coordinates (user calibrated — most reliable)
  2. UIA-based detection (pywinauto — automatic)
  3. Color-based pixel scanning (fallback — for custom One-Click panels)

IMPORTANT:
  - All trade OPENING uses clicker (appears manual to broker)
  - All trade CLOSING uses API (fast and reliable)
  - All data reads use API (invisible to broker)
"""

import time
import os
import ctypes
import ctypes.wintypes
from typing import Dict, Tuple, Optional

# ═══════════════════════════════════════════════════════════════════════════════
# WIN32API - RAW MOUSE INJECTION (Ultra-Low Latency)
# ═══════════════════════════════════════════════════════════════════════════════
try:
    import win32api
    import win32con
    import win32gui
    import win32process
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    print("[CLICKER] WARNING: pywin32 not installed. Run: pip install pywin32")

# ═══════════════════════════════════════════════════════════════════════════════
# DPI AWARENESS — must be set before any window operations
# Without this, SetCursorPos coordinates may be silently scaled on Server 2019
# ═══════════════════════════════════════════════════════════════════════════════
try:
    ctypes.windll.user32.SetProcessDPIAware()
except:
    pass

# ═══════════════════════════════════════════════════════════════════════════════
# SENDINPUT API — Windows 11 compatible input injection (ctypes)
# ═══════════════════════════════════════════════════════════════════════════════
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYUP = 0x0002

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", _INPUTunion),
    ]

def _make_mouse_input(dx, dy, flags, data=0):
    """Create a MOUSEINPUT SendInput structure."""
    mi = MOUSEINPUT(dx, dy, data, flags, 0, ctypes.pointer(ctypes.c_ulong(0)))
    inp = INPUT(type=INPUT_MOUSE)
    inp.union.mi = mi
    return inp

def _make_key_input(vk, flags=0):
    """Create a KEYBDINPUT SendInput structure."""
    ki = KEYBDINPUT(vk, 0, flags, 0, ctypes.pointer(ctypes.c_ulong(0)))
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = ki
    return inp

def _send_inputs(*inputs):
    """Send an array of INPUT structs via SendInput."""
    arr = (INPUT * len(inputs))(*inputs)
    ctypes.windll.user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))

# ═══════════════════════════════════════════════════════════════════════════════
# PYWINAUTO - For UIA detection fallback only (NOT used for clicking)
# ═══════════════════════════════════════════════════════════════════════════════
try:
    from pywinauto import Desktop
    from pywinauto.application import Application
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False
    print("[CLICKER] WARNING: pywinauto not installed. UIA detection unavailable.")


class MT5Clicker:
    """
    Ultra-Low Latency MT5 Auto-Clicker.
    
    Uses win32api for raw mouse injection instead of pywinauto.mouse.
    Click-to-click latency target: 6-10ms (vs 300-500ms with pywinauto).
    
    Coordinate Sources (priority order):
      1. Dashboard-configured coordinates (from DB, set by user)
      2. UIA auto-detection (pywinauto finds buttons)
      3. Color-based pixel scanning (finds red/blue One-Click panel buttons)
    """
    
    def __init__(self, broker_name: str, terminal_path: str, symbol: str, input_method: str = 'legacy'):
        self.broker_name = broker_name
        self.terminal_path = terminal_path
        self.symbol = symbol
        self.input_method = input_method  # 'legacy' (Win10) or 'sendinput' (Win11)
        
        # Cached coordinates (screen-absolute X, Y)
        self._buy_coords: Optional[Tuple[int, int]] = None
        self._sell_coords: Optional[Tuple[int, int]] = None
        self._volume_coords: Optional[Tuple[int, int]] = None
        self._close_x_coords: Optional[Tuple[int, int]] = None  # Close X button in Trades tab
        
        # Dashboard-configured coordinates (highest priority)
        self._dashboard_buy_coords: Optional[Tuple[int, int]] = None
        self._dashboard_sell_coords: Optional[Tuple[int, int]] = None
        self._dashboard_volume_coords: Optional[Tuple[int, int]] = None
        self._dashboard_close_x_coords: Optional[Tuple[int, int]] = None
        
        # MT5 window handle
        self._hwnd: Optional[int] = None
        self._window_title: str = ""
        
        # Lot size tracking for pre-typing
        self._current_lot_size: float = 0.0
        self._last_maintain_time: float = 0.0
        self._maintain_interval: float = 2.0  # Check every 2 seconds
        
        # pywinauto app reference (for UIA detection only)
        self._app = None
        self._main_window = None
        
        # Connection state
        self._connected = False
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CONNECTION & WINDOW MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    
    def connect(self) -> bool:
        """
        Find and connect to the MT5 terminal window.
        Returns True if window found and accessible.
        """
        if not WIN32_AVAILABLE:
            print(f"[{self.broker_name} CLICKER] ERROR: pywin32 not installed")
            return False
        
        # Find MT5 window by enumerating all windows
        self._hwnd = None
        
        def enum_callback(hwnd, results):
            """Collect all MT5-like windows."""
            try:
                title = win32gui.GetWindowText(hwnd)
                if not title:
                    return True
                # Match windows containing "MetaTrader" OR broker name
                # (some MT5 builds don't include "MetaTrader" in the title)
                title_lower = title.lower()
                is_mt5 = ("metatrader" in title_lower or 
                          self.broker_name.lower() in title_lower)
                if is_mt5:
                    is_visible = win32gui.IsWindowVisible(hwnd)
                    is_match = self.broker_name.lower() in title_lower
                    results.append((hwnd, title, is_visible, is_match))
            except:
                pass
            return True
        
        # Retry up to 3 times (MT5 window may not be ready yet during startup)
        for attempt in range(3):
            candidates = []
            try:
                win32gui.EnumWindows(enum_callback, candidates)
            except Exception as e:
                print(f"[{self.broker_name} CLICKER] Window enumeration error: {e}")
                return False
            
            if candidates:
                print(f"[{self.broker_name} CLICKER] Found {len(candidates)} candidate window(s):")
                for hwnd, title, visible, match in candidates:
                    print(f"  hwnd={hwnd}, match={match}, visible={visible}, title='{title[:60]}'")
                
                # Priority: visible + broker-name match > visible > any match > any
                best = None
                for hwnd, title, visible, match in candidates:
                    if visible and match:
                        best = (hwnd, title)
                        break
                if not best:
                    for hwnd, title, visible, match in candidates:
                        if match:
                            best = (hwnd, title)
                            break
                if not best:
                    best = (candidates[0][0], candidates[0][1])
                
                self._hwnd = best[0]
                self._window_title = best[1]
                break
            
            if attempt < 2:
                print(f"[{self.broker_name} CLICKER] MT5 window not found yet, retrying in 2s... (attempt {attempt + 1}/3)")
                time.sleep(2)
        
        # Fallback: find window by matching terminal executable path to process
        if self._hwnd is None:
            print(f"[{self.broker_name} CLICKER] Title matching failed, trying process-based lookup...")
            result = self._find_window_by_process()
            if result:
                self._hwnd, self._window_title = result
                print(f"[{self.broker_name} CLICKER] ✅ Found via process match: {self._window_title}")
            else:
                print(f"[{self.broker_name} CLICKER] ERROR: MT5 window not found (title and process match both failed)")
                return False
        
        # Also initialize pywinauto for UIA detection (fallback)
        if PYWINAUTO_AVAILABLE:
            try:
                self._app = Application(backend="uia").connect(handle=self._hwnd)
                self._main_window = self._app.window(handle=self._hwnd)
            except Exception as e:
                print(f"[{self.broker_name} CLICKER] UIA init warning: {e}")
                self._app = None
                self._main_window = None
        
        self._connected = True
        print(f"[{self.broker_name} CLICKER] ✅ Connected to: {self._window_title}")
        return True
    
    def is_connected(self) -> bool:
        """Check if the MT5 window is still valid and accessible."""
        # Dashboard-only mode: coordinates are set but no window handle
        if self._connected and self._hwnd is None and self.has_coordinates():
            return True
        if not self._connected or self._hwnd is None:
            return False
        try:
            return win32gui.IsWindow(self._hwnd)
        except:
            return False
    
    def close(self):
        """Clean up resources."""
        self._connected = False
        self._app = None
        self._main_window = None
        self._hwnd = None
        print(f"[{self.broker_name} CLICKER] Closed")
    
    def _find_window_by_process(self):
        """Find MT5 window by matching terminal_path to a running process.
        
        This works even when the window title doesn't contain 'MetaTrader'
        or the broker name. Uses the terminal executable path to find the
        correct process, then its main window.
        
        Returns (hwnd, title) tuple or None.
        """
        if not WIN32_AVAILABLE:
            return None
        
        try:
            target = os.path.normpath(self.terminal_path).lower()
            results = []
            
            def enum_cb(hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    title = win32gui.GetWindowText(hwnd)
                    if not title:
                        return True
                    
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    
                    # Get the executable path of this PID
                    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                    h = ctypes.windll.kernel32.OpenProcess(
                        PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                    if h:
                        buf = ctypes.create_unicode_buffer(512)
                        size = ctypes.wintypes.DWORD(512)
                        ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(
                            h, 0, buf, ctypes.byref(size))
                        ctypes.windll.kernel32.CloseHandle(h)
                        if ok:
                            exe_path = os.path.normpath(buf.value).lower()
                            if exe_path == target:
                                results.append((hwnd, title))
                except:
                    pass
                return True
            
            win32gui.EnumWindows(enum_cb, None)
            
            if results:
                print(f"[{self.broker_name} CLICKER] Process match found {len(results)} window(s):")
                for hwnd, title in results:
                    print(f"  hwnd={hwnd}, title='{title[:60]}'")
                return results[0]
            else:
                print(f"[{self.broker_name} CLICKER] No windows found for process: {target}")
                return None
        except ImportError:
            print(f"[{self.broker_name} CLICKER] win32process not available for process-based lookup")
            return None
        except Exception as e:
            print(f"[{self.broker_name} CLICKER] Process-based lookup error: {e}")
            return None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DASHBOARD COORDINATE CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def set_dashboard_coordinates(self, buy_x: int, buy_y: int, 
                                   sell_x: int, sell_y: int,
                                   volume_x: int = 0, volume_y: int = 0,
                                   close_x_x: int = 0, close_x_y: int = 0):
        """
        Set coordinates from the dashboard (user-calibrated).
        These take HIGHEST priority over auto-detection.
        
        Args:
            buy_x, buy_y: Screen coordinates of BUY button center
            sell_x, sell_y: Screen coordinates of SELL button center
            volume_x, volume_y: Screen coordinates of volume input field (0,0 = auto-detect)
            close_x_x, close_x_y: Screen coordinates of close X button in Trades tab
        """
        if buy_x > 0 and buy_y > 0:
            self._dashboard_buy_coords = (buy_x, buy_y)
            self._buy_coords = (buy_x, buy_y)
            
        if sell_x > 0 and sell_y > 0:
            self._dashboard_sell_coords = (sell_x, sell_y)
            self._sell_coords = (sell_x, sell_y)
            
        if volume_x > 0 and volume_y > 0:
            self._dashboard_volume_coords = (volume_x, volume_y)
            self._volume_coords = (volume_x, volume_y)
        
        if close_x_x > 0 and close_x_y > 0:
            self._dashboard_close_x_coords = (close_x_x, close_x_y)
            self._close_x_coords = (close_x_x, close_x_y)
        
        print(f"[{self.broker_name} CLICKER] 📍 Dashboard coordinates set:")
        print(f"  Buy:     {self._dashboard_buy_coords}")
        print(f"  Sell:    {self._dashboard_sell_coords}")
        print(f"  Volume:  {self._dashboard_volume_coords}")
        print(f"  Close X: {self._dashboard_close_x_coords}")
    
    def has_coordinates(self) -> bool:
        """Check if both buy and sell coordinates are available."""
        return self._buy_coords is not None and self._sell_coords is not None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # COORDINATE DETECTION (Auto-detection fallbacks)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def cache_coordinates(self) -> bool:
        """
        Find and cache Buy/Sell button coordinates.
        
        Priority:
          1. Dashboard coordinates (already set via set_dashboard_coordinates)
          2. UIA-based detection (pywinauto)
          3. Color-based pixel scanning
        
        Returns True if coordinates are successfully cached.
        """
        print(f"[{self.broker_name} CLICKER] Caching coordinates...")
        
        # Priority 1: Dashboard coordinates — work even WITHOUT window handle
        if self._dashboard_buy_coords and self._dashboard_sell_coords:
            self._buy_coords = self._dashboard_buy_coords
            self._sell_coords = self._dashboard_sell_coords
            if self._dashboard_volume_coords:
                self._volume_coords = self._dashboard_volume_coords
            # Mark as connected in dashboard-only mode
            self._connected = True
            print(f"[{self.broker_name} CLICKER] ✅ Using DASHBOARD coordinates (no window handle needed)")
            print(f"  Buy:  {self._buy_coords}")
            print(f"  Sell: {self._sell_coords}")
            return True
        
        # For auto-detection, we need the window handle
        if not self.is_connected():
            if not self.connect():
                return False
        
        # Priority 2: UIA-based detection
        if self._try_uia_detection():
            print(f"[{self.broker_name} CLICKER] ✅ UIA detection successful")
            return True
        
        # Priority 3: Color-based pixel scanning
        if self._try_color_detection():
            print(f"[{self.broker_name} CLICKER] ✅ Color scan detection successful")
            return True
        
        print(f"[{self.broker_name} CLICKER] ❌ All detection methods failed!")
        print(f"  → Set coordinates manually in Dashboard Settings")
        print(f"  → Or enable One-Click Trading panel (Alt+T)")
        return False
    
    def _try_uia_detection(self) -> bool:
        """Try to find buttons using pywinauto UIA backend."""
        if not PYWINAUTO_AVAILABLE or self._main_window is None:
            return False
        
        try:
            # Search for Buy button
            buy_btn = None
            sell_btn = None
            
            # Try common patterns for MT5 One-Click Trading buttons
            for pattern in ["Buy", "BUY", "buy"]:
                try:
                    btn = self._main_window.child_window(title_re=f".*{pattern}.*", 
                                                          control_type="Button")
                    if btn.exists(timeout=1):
                        buy_btn = btn
                        break
                except:
                    continue
            
            for pattern in ["Sell", "SELL", "sell"]:
                try:
                    btn = self._main_window.child_window(title_re=f".*{pattern}.*", 
                                                          control_type="Button")
                    if btn.exists(timeout=1):
                        sell_btn = btn
                        break
                except:
                    continue
            
            if buy_btn and sell_btn:
                buy_rect = buy_btn.rectangle()
                sell_rect = sell_btn.rectangle()
                
                self._buy_coords = (
                    (buy_rect.left + buy_rect.right) // 2,
                    (buy_rect.top + buy_rect.bottom) // 2
                )
                self._sell_coords = (
                    (sell_rect.left + sell_rect.right) // 2,
                    (sell_rect.top + sell_rect.bottom) // 2
                )
                
                print(f"  Buy:  {self._buy_coords}")
                print(f"  Sell: {self._sell_coords}")
                return True
                
        except Exception as e:
            print(f"[{self.broker_name} CLICKER] UIA detection error: {e}")
        
        return False
    
    def _try_color_detection(self) -> bool:
        """
        Find Buy/Sell buttons by scanning for their colors.
        MT5 One-Click panel: SELL = RED, BUY = BLUE
        """
        if not WIN32_AVAILABLE:
            return False
        
        try:
            # Get MT5 window rectangle
            rect = win32gui.GetWindowRect(self._hwnd)
            left, top, right, bottom = rect
            width = right - left
            height = bottom - top
            
            # Scan the top-left area where One-Click panel typically appears
            # Usually within top 15% of the chart area
            scan_left = left + int(width * 0.01)
            scan_right = left + int(width * 0.5)
            scan_top = top + int(height * 0.05)
            scan_bottom = top + int(height * 0.15)
            
            # Get device context for reading pixels
            hdc = win32gui.GetDC(0)  # Screen DC
            
            red_pixels = []  # SELL button pixels
            blue_pixels = []  # BUY button pixels
            
            # Scan with step size for speed
            step = 3
            for y in range(scan_top, scan_bottom, step):
                for x in range(scan_left, scan_right, step):
                    try:
                        color = win32gui.GetPixel(hdc, x, y)
                        r = color & 0xFF
                        g = (color >> 8) & 0xFF
                        b = (color >> 16) & 0xFF
                        
                        # RED region (SELL button)
                        if r > 150 and g < 80 and b < 80:
                            red_pixels.append((x, y))
                        
                        # BLUE region (BUY button)
                        if b > 150 and r < 80 and g < 120:
                            blue_pixels.append((x, y))
                    except:
                        continue
            
            win32gui.ReleaseDC(0, hdc)
            
            # Calculate center of each button cluster
            min_pixels = 10  # Need at least this many matching pixels
            
            if len(red_pixels) >= min_pixels and len(blue_pixels) >= min_pixels:
                sell_x = sum(p[0] for p in red_pixels) // len(red_pixels)
                sell_y = sum(p[1] for p in red_pixels) // len(red_pixels)
                buy_x = sum(p[0] for p in blue_pixels) // len(blue_pixels)
                buy_y = sum(p[1] for p in blue_pixels) // len(blue_pixels)
                
                self._sell_coords = (sell_x, sell_y)
                self._buy_coords = (buy_x, buy_y)
                
                # Estimate volume field position (typically between the two buttons)
                vol_x = (sell_x + buy_x) // 2
                vol_y = sell_y  # Same Y as buttons
                self._volume_coords = (vol_x, vol_y)
                
                print(f"  Buy:  {self._buy_coords} ({len(blue_pixels)} pixels)")
                print(f"  Sell: {self._sell_coords} ({len(red_pixels)} pixels)")
                return True
            else:
                print(f"  Color scan: Red={len(red_pixels)}, Blue={len(blue_pixels)} (need {min_pixels}+)")
                
        except Exception as e:
            print(f"[{self.broker_name} CLICKER] Color detection error: {e}")
        
        return False
    
    # ═══════════════════════════════════════════════════════════════════════════
    # RAW MOUSE INJECTION (win32api — Ultra-Low Latency)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _raw_click(self, x: int, y: int) -> bool:
        """
        Perform a raw mouse click at screen coordinates.
        Routes to legacy (Win10) or SendInput (Win11) based on self.input_method.
        """
        if self.input_method == 'sendinput':
            return self._raw_click_sendinput(x, y)
        # Legacy (Win10)
        if not WIN32_AVAILABLE:
            return False
        try:
            win32api.SetCursorPos((x, y))
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return True
        except Exception as e:
            print(f"[{self.broker_name} CLICKER] Raw click error at ({x},{y}): {e}")
            return False
    
    def _raw_double_click(self, x: int, y: int) -> bool:
        """Double-click at coordinates. Routes based on input_method."""
        if self.input_method == 'sendinput':
            return self._raw_double_click_sendinput(x, y)
        # Legacy (Win10)
        if not WIN32_AVAILABLE:
            return False
        try:
            win32api.SetCursorPos((x, y))
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return True
        except Exception as e:
            print(f"[{self.broker_name} CLICKER] Double-click error: {e}")
            return False
    
    def _raw_type_text(self, text: str):
        """
        Type text into the focused field. Routes based on input_method.
        Uses VK_DECIMAL (0x6E) for period — works in MT5's custom volume spinner.
        """
        if self.input_method == 'sendinput':
            return self._raw_type_text_sendinput(text)
        # Legacy (Win10) — keybd_event
        if not WIN32_AVAILABLE:
            return
        # Clear existing text: End → Backspace×10
        win32api.keybd_event(win32con.VK_END, 0, 0, 0)
        win32api.keybd_event(win32con.VK_END, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.03)
        for _ in range(10):
            win32api.keybd_event(win32con.VK_BACK, 0, 0, 0)
            win32api.keybd_event(win32con.VK_BACK, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)
        VK_MAP = {
            '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
            '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
            '.': 0x6E,
        }
        for char in text:
            vk = VK_MAP.get(char)
            if vk is None:
                print(f"[{self.broker_name} CLICKER] WARNING: No VK code for '{char}', skipping")
                continue
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.04)
        print(f"[{self.broker_name} CLICKER] Typed '{text}' via keybd_event (VK_DECIMAL for period)")
    
    def _send_key(self, vk: int):
        """Send a single key press+release using the active input method."""
        if self.input_method == 'sendinput':
            _send_inputs(_make_key_input(vk), _make_key_input(vk, KEYEVENTF_KEYUP))
        elif WIN32_AVAILABLE:
            win32api.keybd_event(vk, 0, 0, 0)
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    
    # ─── SendInput implementations (Windows 11) ──────────────────────────────
    
    def _pixel_to_absolute(self, x: int, y: int):
        """Convert pixel coordinates to MOUSEEVENTF_ABSOLUTE range (0-65535).
        
        Uses center-of-pixel formula to avoid off-by-one rounding errors.
        Old: round(x * 65536 / screen) targets edge of pixel range, can round wrong
        New: (x * 65536 + 32768) / screen targets center, always hits correct pixel
        """
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        abs_x = int((x * 65536 + 32768) / screen_w)
        abs_y = int((y * 65536 + 32768) / screen_h)
        return abs_x, abs_y
    
    def _raw_click_sendinput(self, x: int, y: int) -> bool:
        """Click at screen coordinates using SendInput (Win11 compatible).
        
        Uses ONLY MOUSEEVENTF_MOVE|ABSOLUTE — no SetCursorPos.
        SetCursorPos generates separate WM_MOUSEMOVE/WM_MOUSELEAVE messages
        that disrupt Close X hover state when two workers click simultaneously.
        ABSOLUTE SendInput moves + clicks in a single atomic kernel call.
        """
        try:
            abs_x, abs_y = self._pixel_to_absolute(x, y)
            
            # Single atomic SendInput: MOVE + CLICK — no separate cursor events
            _send_inputs(
                _make_mouse_input(abs_x, abs_y, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE),
                _make_mouse_input(abs_x, abs_y, MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE),
                _make_mouse_input(abs_x, abs_y, MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE),
            )
            return True
        except Exception as e:
            print(f"[{self.broker_name} CLICKER] SendInput click error at ({x},{y}): {e}")
            return False
    
    def _raw_double_click_sendinput(self, x: int, y: int) -> bool:
        """Double-click at coordinates using SendInput (Win11 compatible)."""
        try:
            abs_x, abs_y = self._pixel_to_absolute(x, y)
            
            _send_inputs(
                _make_mouse_input(abs_x, abs_y, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE),
                _make_mouse_input(abs_x, abs_y, MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE),
                _make_mouse_input(abs_x, abs_y, MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE),
                _make_mouse_input(abs_x, abs_y, MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE),
                _make_mouse_input(abs_x, abs_y, MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE),
            )
            return True
        except Exception as e:
            print(f"[{self.broker_name} CLICKER] SendInput double-click error: {e}")
            return False
    
    def _raw_type_text_sendinput(self, text: str):
        """Type text using SendInput KEYBDINPUT (Win11 compatible)."""
        VK_END = 0x23
        VK_BACK = 0x08
        VK_MAP = {
            '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
            '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
            '.': 0x6E,  # VK_DECIMAL (numpad period) — MT5 spinner compatible
        }
        try:
            # End key to move cursor to end
            _send_inputs(_make_key_input(VK_END), _make_key_input(VK_END, KEYEVENTF_KEYUP))
            time.sleep(0.03)
            
            # Backspace 10 times to clear
            for _ in range(10):
                _send_inputs(_make_key_input(VK_BACK), _make_key_input(VK_BACK, KEYEVENTF_KEYUP))
                time.sleep(0.02)
            
            # Type each character
            for char in text:
                vk = VK_MAP.get(char)
                if vk is None:
                    print(f"[{self.broker_name} CLICKER] WARNING: No VK code for '{char}', skipping")
                    continue
                _send_inputs(_make_key_input(vk))
                time.sleep(0.03)
                _send_inputs(_make_key_input(vk, KEYEVENTF_KEYUP))
                time.sleep(0.04)
            
            print(f"[{self.broker_name} CLICKER] Typed '{text}' via SendInput (Win11 mode)")
        except Exception as e:
            print(f"[{self.broker_name} CLICKER] SendInput type error: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # LOT SIZE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    
    def set_lot_size(self, volume: float) -> bool:
        """
        Set the lot size in the MT5 One-Click Trading panel's volume field.
        
        Strategy:
          1. Click on the volume field to focus it
          2. Use _raw_type_text to clear and type new value
          
        Returns True if successful.
        """
        if not self.has_coordinates():
            return False
        
        # Format volume (MT5 uses format like "0.35")
        vol_text = f"{volume:.2f}"
        
        # Try to find volume field coordinates
        vol_coords = self._get_volume_coords()
        if vol_coords is None:
            print(f"[{self.broker_name} CLICKER] Volume field not found")
            return False
        
        try:
            # Make window topmost so clicks land on it (NOT blocked like SetForegroundWindow)
            self._bring_to_front()
            time.sleep(0.015)  # 15ms for window to render on top
            
            # Click on volume field — this ALSO activates the window (gives it keyboard focus)
            self._raw_click(vol_coords[0], vol_coords[1])
            time.sleep(0.015)  # 15ms for field to activate
            
            # VERIFY the click activated our window (foreground check)
            if self._hwnd and WIN32_AVAILABLE:
                fg_hwnd = win32gui.GetForegroundWindow()
                if fg_hwnd != self._hwnd:
                    # Click didn't activate — retry
                    print(f"[{self.broker_name} CLICKER] Focus not gained after click, retrying...")
                    self._raw_click(vol_coords[0], vol_coords[1])
                    time.sleep(0.03)
                    fg_hwnd = win32gui.GetForegroundWindow()
                    if fg_hwnd != self._hwnd:
                        print(f"[{self.broker_name} CLICKER] ABORT: Window not activated after 2 clicks!")
                        self._remove_topmost()
                        return False
            
            # Type new volume (keybd_event goes to the now-focused window)
            self._raw_type_text(vol_text)
            time.sleep(0.01)  # 10ms for text to register
            
            # Press Tab to commit the value and move focus away from field
            self._send_key(0x09)  # VK_TAB — routed via input_method
            time.sleep(0.01)
            
            self._remove_topmost()
            self._current_lot_size = volume
            print(f"[{self.broker_name} CLICKER] ✅ Lot size set to {vol_text}")
            return True
            
        except Exception as e:
            print(f"[{self.broker_name} CLICKER] Set lot size error: {e}")
            return False
    
    def _get_volume_coords(self) -> Optional[Tuple[int, int]]:
        """Get the volume field coordinates from available sources."""
        # Priority 1: Dashboard configured
        if self._dashboard_volume_coords:
            return self._dashboard_volume_coords
        
        # Priority 2: Previously detected
        if self._volume_coords:
            return self._volume_coords
        
        # Priority 3: UIA detection
        if PYWINAUTO_AVAILABLE and self._main_window:
            try:
                # Look for edit/text controls near the Buy/Sell buttons
                for ctrl_type in ["Edit", "Text"]:
                    try:
                        edits = self._main_window.descendants(control_type=ctrl_type)
                        for edit in edits:
                            try:
                                text = edit.window_text().strip()
                                # Volume fields typically show numbers like "0.01", "0.35", "1.00"
                                if text and '.' in text:
                                    try:
                                        val = float(text.replace(',', '.'))
                                        if 0.001 <= val <= 999.99:
                                            rect = edit.rectangle()
                                            self._volume_coords = (
                                                (rect.left + rect.right) // 2,
                                                (rect.top + rect.bottom) // 2
                                            )
                                            return self._volume_coords
                                    except ValueError:
                                        continue
                            except:
                                continue
                    except:
                        continue
            except:
                pass
        
        # Priority 4: Estimate from button positions
        if self._sell_coords and self._buy_coords:
            # Volume field is typically between Sell and Buy buttons on One-Click panel
            mid_x = (self._sell_coords[0] + self._buy_coords[0]) // 2
            mid_y = self._sell_coords[1]  # Same Y level
            self._volume_coords = (mid_x, mid_y)
            return self._volume_coords
        
        return None
    
    def maintain_lot_size(self, target_volume: float) -> bool:
        """
        Background task: Periodically ensure lot size is correct.
        Called during scanning phase to pre-type the lot size.
        
        This means when an opportunity appears, the lot is ALREADY typed
        and we only need to click Buy/Sell (~6ms instead of ~200ms).
        """
        # Rate limit to avoid spamming
        now = time.time()
        if now - self._last_maintain_time < self._maintain_interval:
            return True
        self._last_maintain_time = now
        
        # Skip if already correct
        if abs(self._current_lot_size - target_volume) < 0.001:
            return True
        
        # Check we have coordinates (window handle not needed for dashboard coords)
        if not self.has_coordinates():
            return False
        
        # Set the lot size
        return self.set_lot_size(target_volume)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # WINDOW MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _bring_to_front(self):
        """Make the MT5 window topmost so clicks and keystrokes land on it.
        
        Uses SetWindowPos(HWND_TOPMOST) instead of SetForegroundWindow.
        SetForegroundWindow is BLOCKED on Windows Server 2019 for cross-process
        calls. SetWindowPos changes visual Z-order and is NOT restricted.
        
        After making topmost, a mouse click on the window will also activate it
        (giving it keyboard focus), enabling keybd_event for lot typing.
        """
        if not WIN32_AVAILABLE:
            return
        
        # Auto-reconnect if we don't have a window handle
        if not self._hwnd:
            self.connect()
        
        if not self._hwnd:
            print(f"[{self.broker_name} CLICKER] WARNING: Cannot bring to front — no window handle")
            return
        
        try:
            # Only restore if actually minimized — SW_RESTORE on a maximized
            # window will UN-MAXIMIZE it and snap it to its last normal position
            if win32gui.IsIconic(self._hwnd):
                win32gui.ShowWindow(self._hwnd, win32con.SW_RESTORE)
            
            # Make window TOPMOST — this is NOT restricted like SetForegroundWindow
            # MUST use win32gui.SetWindowPos (not ctypes) — ctypes breaks HWND_TOPMOST
            # on 64-bit Python because it passes -1 as 32-bit int, not 64-bit HWND
            win32gui.SetWindowPos(
                self._hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
            
        except Exception as e:
            print(f"[{self.broker_name} CLICKER] _bring_to_front error: {e}")
    
    def _remove_topmost(self):
        """Remove TOPMOST flag after clicking, so other windows can take Z-order."""
        if not WIN32_AVAILABLE or not self._hwnd:
            return
        
        try:
            win32gui.SetWindowPos(
                self._hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        except:
            pass
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TRADE EXECUTION (Core — Ultra-Low Latency)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def click_buy(self) -> bool:
        """Click the BUY button using cached coordinates."""
        if not self._buy_coords:
            print(f"[{self.broker_name} CLICKER] ERROR: No BUY coordinates cached")
            return False
        
        success = self._raw_click(self._buy_coords[0], self._buy_coords[1])
        if success:
            print(f"[{self.broker_name} CLICKER] ⚡ BUY CLICK at {self._buy_coords}")
        return success
    
    def click_sell(self) -> bool:
        """Click the SELL button using cached coordinates."""
        if not self._sell_coords:
            print(f"[{self.broker_name} CLICKER] ERROR: No SELL coordinates cached")
            return False
        
        success = self._raw_click(self._sell_coords[0], self._sell_coords[1])
        if success:
            print(f"[{self.broker_name} CLICKER] ⚡ SELL CLICK at {self._sell_coords}")
        return success
    
    def click_close_position(self) -> Dict:
        """
        Close a position by clicking the X button in MT5's Trades tab.
        
        Makes window topmost first (same as execute_click_trade) so the 
        click lands on the correct window even if it's behind another.
        
        Returns:
            Dict with success status and timing
        """
        start_ms = time.time() * 1000
        
        if not self._close_x_coords:
            return {
                "success": False,
                "error": "No Close X coordinates. Set them in Dashboard Settings.",
                "time_ms": 0
            }
        
        # Bring window to front so close X click registers on the correct terminal
        self._bring_to_front()
        time.sleep(0.03)  # 30ms for Z-order to settle
        
        success = self._raw_click(self._close_x_coords[0], self._close_x_coords[1])
        
        # Remove topmost so other worker's window can take Z-order next
        self._remove_topmost()
        
        elapsed_ms = time.time() * 1000 - start_ms
        
        if success:
            print(f"[{self.broker_name} CLICKER] ⚡ CLOSE X CLICK at {self._close_x_coords}")
            return {
                "success": True,
                "time_ms": round(elapsed_ms, 1),
                "method": "click_close_x"
            }
        else:
            return {
                "success": False,
                "error": "Close X click failed",
                "time_ms": round(elapsed_ms, 1)
            }
    
    def execute_click_trade(self, order_type: str, volume: float) -> Dict:
        """
        Execute a trade by clicking Buy/Sell button on the MT5 terminal.
        
        FAST PATH (lot size pre-typed):
          1. Click Buy/Sell → ~2ms
          Total: ~2ms
          
        SLOW PATH (lot size needs typing):
          1. Type lot size → ~50ms
          2. Click Buy/Sell → ~2ms
          Total: ~52ms
        
        Returns:
            Dict with success, time_ms, method
        """
        start_ms = time.time() * 1000
        
        if not self.has_coordinates():
            return {"success": False, "error": "No button coordinates. Set them in Dashboard Settings.", "time_ms": 0}
        
        # Log coordinate source and exact values for verification
        coord_source = self._get_coord_source()
        target_coords = self._buy_coords if order_type.upper() == "BUY" else self._sell_coords
        print(f"[{self.broker_name} CLICKER] Executing {order_type} | Source: {coord_source} | Target: {target_coords} | Volume: {volume}")
        
        # Check if lot size needs updating (safety fallback)
        # Lot SHOULD be pre-typed via MAINTAIN_LOT before scanning, but if it
        # failed or got corrupted, we must re-type here to avoid 0.00 lot trades.
        if abs(self._current_lot_size - volume) > 0.001:
            print(f"[{self.broker_name} CLICKER] Lot mismatch ({self._current_lot_size} → {volume}), typing new volume...")
            if not self.set_lot_size(volume):
                return {"success": False, "error": "Failed to set lot size", "time_ms": 0}
        
        # Bring window to front so the click registers on the correct MT5 terminal
        self._bring_to_front()
        time.sleep(0.03)  # 30ms for Z-order to settle
        
        if order_type.upper() == "BUY":
            success = self.click_buy()
        elif order_type.upper() == "SELL":
            success = self.click_sell()
        else:
            self._remove_topmost()
            return {"success": False, "error": f"Unknown order type: {order_type}", "time_ms": 0}
        
        # Remove topmost so other worker's window can take Z-order next
        self._remove_topmost()

        elapsed_ms = time.time() * 1000 - start_ms
        
        if success:
            return {
                "success": True,
                "time_ms": round(elapsed_ms, 1),
                "method": f"{'sendinput' if self.input_method == 'sendinput' else 'win32api_raw'}",
                "coords": target_coords
            }
        else:
            return {
                "success": False,
                "error": "Click failed",
                "time_ms": round(elapsed_ms, 1)
            }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DIAGNOSTICS & TESTING
    # ═══════════════════════════════════════════════════════════════════════════
    
    def test_click(self, target: str) -> Dict:
        """
        Test a click without executing a real trade.
        Used by dashboard to verify coordinates are correct.
        
        Args:
            target: "buy", "sell", or "volume"
            
        Returns:
            Dict with success, coordinates used, window info
        """
        result = {
            "success": False,
            "target": target,
            "coordinates": None,
            "window_title": self._window_title,
            "window_visible": self.is_connected()
        }
        
        if target == "buy" and self._buy_coords:
            result["coordinates"] = self._buy_coords
            result["success"] = True
            result["message"] = f"BUY button at {self._buy_coords}"
        elif target == "sell" and self._sell_coords:
            result["coordinates"] = self._sell_coords
            result["success"] = True
            result["message"] = f"SELL button at {self._sell_coords}"
        elif target == "volume":
            vol_coords = self._get_volume_coords()
            if vol_coords:
                result["coordinates"] = vol_coords
                result["success"] = True
                result["message"] = f"Volume field at {vol_coords}"
            else:
                result["message"] = "Volume field not found"
        else:
            result["message"] = f"No coordinates for '{target}'"
        
        return result
    
    def get_status(self) -> Dict:
        """Get comprehensive status for dashboard display."""
        return {
            "connected": self._connected,
            "window_title": self._window_title,
            "window_visible": self.is_connected(),
            "buy_coords": self._buy_coords,
            "sell_coords": self._sell_coords,
            "volume_coords": self._volume_coords,
            "dashboard_buy_coords": self._dashboard_buy_coords,
            "dashboard_sell_coords": self._dashboard_sell_coords,
            "dashboard_volume_coords": self._dashboard_volume_coords,
            "current_lot_size": self._current_lot_size,
            "has_coordinates": self.has_coordinates(),
            "coord_source": self._get_coord_source()
        }
    
    def _get_coord_source(self) -> str:
        """Identify which source provided the current coordinates."""
        if self._dashboard_buy_coords and self._buy_coords == self._dashboard_buy_coords:
            return "dashboard"
        elif self._buy_coords is not None:
            return "auto-detected"
        return "none"


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def find_all_mt5_windows() -> list:
    """
    Find all running MT5 terminal windows.
    Returns list of dicts with window info.
    """
    if not WIN32_AVAILABLE:
        print("ERROR: pywin32 is not installed. Run: pip install pywin32")
        return []
    
    mt5_windows = []
    
    def enum_callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            try:
                title = win32gui.GetWindowText(hwnd)
                if title and ("MetaTrader" in title or "metatrader" in title.lower()):
                    rect = win32gui.GetWindowRect(hwnd)
                    mt5_windows.append({
                        "title": title,
                        "handle": hwnd,
                        "rect": {"left": rect[0], "top": rect[1], 
                                 "right": rect[2], "bottom": rect[3]},
                        "width": rect[2] - rect[0],
                        "height": rect[3] - rect[1]
                    })
            except:
                pass
        return True
    
    try:
        win32gui.EnumWindows(enum_callback, None)
    except Exception as e:
        print(f"ERROR scanning windows: {e}")
    
    return mt5_windows


def get_cursor_position() -> Tuple[int, int]:
    """Get current mouse cursor position. Used for coordinate calibration."""
    if WIN32_AVAILABLE:
        return win32api.GetCursorPos()
    return (0, 0)
