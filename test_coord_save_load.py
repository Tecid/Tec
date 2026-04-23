"""
Test: Verify coordinate save/load cycle through the API.
Simulates what the Settings page does when saving and loading coordinates.
"""
import urllib.request
import json
import sys

BASE = "http://localhost:5000/api"

# Step 1: Signup and Login
print("=" * 60)
print("STEP 1: Setting up test user...")
EMAIL = "test_coord_bot@example.com"
PASSWORD = "password123"
USERNAME = "test_coord_bot"

# Try signup first
signup_data = json.dumps({"email": EMAIL, "password": PASSWORD, "username": USERNAME}).encode()
req = urllib.request.Request(f"{BASE}/auth/signup", data=signup_data, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        print("  OK: Signup successful")
except urllib.error.HTTPError as e:
    if e.code == 409:
        print("  INFO: User already exists, proceeding to login")
    else:
        print(f"  FAIL: Signup error {e.code}: {e.read().decode()}")
        sys.exit(1)

# Login to get JWT token
login_data = json.dumps({"email": EMAIL, "password": PASSWORD}).encode()
req = urllib.request.Request(f"{BASE}/auth/login", data=login_data, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
        token = data.get("token") # auth.py returns 'token' not 'access_token'
        if not token:
            print(f"  FAIL: No token returned. Response: {data}")
            sys.exit(1)
        print(f"  OK: Got JWT token")
except Exception as e:
    print(f"  FAIL: Login failed: {e}")
    sys.exit(1)

auth_header = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Step 2: GET current settings and check coordinate fields
print("\nSTEP 2: Loading current settings...")
req = urllib.request.Request(f"{BASE}/settings", headers=auth_header)
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        settings = json.loads(resp.read().decode())
        coord_fields = [
            'hfm_buy_x', 'hfm_buy_y', 'hfm_sell_x', 'hfm_sell_y',
            'hfm_volume_x', 'hfm_volume_y',
            'equiti_buy_x', 'equiti_buy_y', 'equiti_sell_x', 'equiti_sell_y',
            'equiti_volume_x', 'equiti_volume_y'
        ]
        print("  Current coordinate values:")
        missing = []
        for f in coord_fields:
            val = settings.get(f, "MISSING")
            if val == "MISSING":
                missing.append(f)
            print(f"    {f}: {val}")
        if missing:
            print(f"\n  WARNING: Missing fields in GET response: {missing}")
        else:
            print(f"\n  OK: All 12 coordinate fields present")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# Step 3: PUT test coordinates
print("\nSTEP 3: Saving test coordinates...")
test_coords = {
    'hfm_buy_x': 500, 'hfm_buy_y': 300,
    'hfm_sell_x': 400, 'hfm_sell_y': 300,
    'hfm_volume_x': 450, 'hfm_volume_y': 280,
    'equiti_buy_x': 1500, 'equiti_buy_y': 300,
    'equiti_sell_x': 1400, 'equiti_sell_y': 300,
    'equiti_volume_x': 1450, 'equiti_volume_y': 280,
}
# Merge test coords into full settings to simulate what the frontend does
save_data = {**settings, **test_coords}
put_data = json.dumps(save_data).encode()
req = urllib.request.Request(f"{BASE}/settings", data=put_data, method='PUT', headers=auth_header)
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        result = json.loads(resp.read().decode())
        print(f"  Response: {result}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"  FAIL: HTTP {e.code} — {body}")
    sys.exit(1)
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# Step 4: GET settings again and verify coordinates persisted
print("\nSTEP 4: Reloading settings to verify persistence...")
req = urllib.request.Request(f"{BASE}/settings", headers=auth_header)
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        reloaded = json.loads(resp.read().decode())
        print("  Reloaded coordinate values:")
        all_match = True
        for f in coord_fields:
            expected = test_coords.get(f, 0)
            actual = reloaded.get(f, "MISSING")
            match = "OK" if actual == expected else "MISMATCH"
            if match != "OK":
                all_match = False
            print(f"    {f}: {actual} (expected {expected}) [{match}]")
        
        if all_match:
            print(f"\n  RESULT: ALL COORDINATES SAVED AND LOADED CORRECTLY!")
        else:
            print(f"\n  RESULT: SOME COORDINATES DID NOT PERSIST — DATABASE ISSUE!")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
