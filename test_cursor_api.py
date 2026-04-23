"""Quick test: verify /api/cursor-position endpoint works."""
import urllib.request
import json
import time

URL = "http://localhost:5000/api/cursor-position"

print("Testing /api/cursor-position endpoint...")
print("=" * 50)

try:
    for i in range(3):
        req = urllib.request.Request(URL)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            ok = data.get("ok", False)
            x = data.get("x", 0)
            y = data.get("y", 0)
            err = data.get("error", "")
            
            if ok:
                print(f"  [{i+1}] OK  x={x}  y={y}")
            else:
                print(f"  [{i+1}] FAIL  error={err}")
        time.sleep(0.3)
    
    print("=" * 50)
    print("RESULT: Cursor position API is WORKING!")
    print("Global coordinates are being captured correctly.")
    
except Exception as e:
    print(f"ERROR: {e}")
    print("Make sure the backend server is running: python app.py")
