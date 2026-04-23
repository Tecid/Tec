"""
HedgedLock Bot - Main Launcher
Entry point for the executable. Starts Flask server and opens browser.
"""

import multiprocessing
import os
import sys
import ctypes

# CRITICAL: Set DPI awareness BEFORE anything else.
# Without this, GetCursorPos (calibration) and SetCursorPos (clicking) use different
# coordinate spaces at 125% DPI, causing clicks to miss by 25%.
try:
    ctypes.windll.user32.SetProcessDPIAware()
except:
    pass

# CRITICAL: freeze_support() must be called FIRST for multiprocessing to work in frozen exe
# This prevents worker processes from re-executing the entire launcher
if __name__ == '__main__':
    multiprocessing.freeze_support()

# CRITICAL: Set up paths before any other imports
# When running as exe, files are in sys._MEIPASS
if getattr(sys, 'frozen', False):
    # Running as compiled exe
    BASE_DIR = sys._MEIPASS  # PyInstaller extracts files here
    EXE_DIR = os.path.dirname(sys.executable)  # Where the exe is located
else:
    # Running as script
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = BASE_DIR

# Add paths for imports
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'server'))

# Set working directory to where the exe is (for .env.enc access)
os.chdir(EXE_DIR)

# Only run the main launcher logic if this is the main process
# Worker processes spawned by multiprocessing should NOT run this
if __name__ == '__main__':
    import webbrowser
    import threading
    import time
    
    # Now load encrypted config from exe directory
    from server.config_loader import load_encrypted_env
    load_encrypted_env()

    def open_browser_delayed(url, delay=2):
        """Open browser after a short delay to let server start."""
        def _open():
            time.sleep(delay)
            print(f"[LAUNCHER] Opening browser: {url}")
            webbrowser.open(url)
        
        thread = threading.Thread(target=_open, daemon=True)
        thread.start()


    def main():
        print("=" * 60)
        print("  HEDGED LOCK BOT")
        print("  Version 6.0 - Dashboard Server")
        print("=" * 60)
        print()
        
        # Determine the port
        port = int(os.environ.get('PORT', 5000))
        url = f"http://localhost:{port}"
        
        print(f"[LAUNCHER] Starting server on {url}")
        print(f"[LAUNCHER] Press Ctrl+C to stop")
        print()
        
        # Open browser after server starts
        open_browser_delayed(url, delay=2)
        
        # Set environment variable for Flask to find static files
        # The client/dist folder is bundled at BASE_DIR/client/dist
        static_folder = os.path.join(BASE_DIR, 'client', 'dist')
        os.environ['STATIC_FOLDER'] = static_folder
        
        # Import the app module (this triggers eventlet monkey patching)
        # We import here to ensure paths are set up first
        from server.app import app, socketio
        from server.database import init_db
        
        # Override Flask static folder to point to bundled files
        app.static_folder = static_folder
        
        # Initialize database
        print("[LAUNCHER] Initializing database...")
        init_db()
        
        # Run the server
        print(f"[LAUNCHER] Server running on {url}")
        socketio.run(app, host='0.0.0.0', port=port, debug=False)


    try:
        main()
    except KeyboardInterrupt:
        print("\n[LAUNCHER] Shutting down...")
    except Exception as e:
        print(f"\n[LAUNCHER] Error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
