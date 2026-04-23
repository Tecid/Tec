# -*- coding: utf-8 -*-
"""Verify coordinate persistence: signup/login, save coords, fetch and confirm."""
import urllib.request
import json
import sys

BASE = "http://localhost:5000/api"
EMAIL = "test_calibration@test.com"
PASSWORD = "TestPass123"

def api_call(url, data=None, method="GET", headers=None):
    if headers is None:
        headers = {}
    if data:
        data = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req)
        raw = resp.read().decode()
        try:
            return resp.getcode(), json.loads(raw)
        except:
            return resp.getcode(), {"raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except:
            return e.code, {"raw": raw[:200]}

print("=" * 60)
print("STEP 1: Signup or Login test user")

# Try signup first (correct endpoint is /signup, not /register)
code, body = api_call(f"{BASE}/auth/signup", {
    "email": EMAIL, "username": "test_cal", "password": PASSWORD
}, method="POST")

if code == 201:
    token = body.get("token")
    print(f"  Signed up new user.")
elif code == 409:
    # Already exists, login
    code2, body2 = api_call(f"{BASE}/auth/login", {
        "email": EMAIL, "password": PASSWORD
    }, method="POST")
    if code2 == 200:
        token = body2.get("token")
        print(f"  Logged in existing user.")
    else:
        print(f"  Login FAILED: {body2}")
        sys.exit(1)
else:
    print(f"  Signup unexpected ({code}): {body}")
    sys.exit(1)

auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Step 2: Save coordinates
print("\nSTEP 2: Save coordinates via PUT /settings")
test_coords = {
    "hfm_buy_x": 500, "hfm_buy_y": 300,
    "hfm_sell_x": 400, "hfm_sell_y": 300,
    "hfm_volume_x": 450, "hfm_volume_y": 300,
    "equiti_buy_x": 1200, "equiti_buy_y": 350,
    "equiti_sell_x": 1100, "equiti_sell_y": 350,
    "equiti_volume_x": 1150, "equiti_volume_y": 350,
}
code, body = api_call(f"{BASE}/settings", test_coords, method="PUT", headers=auth)
if code == 200:
    print(f"  Saved OK: {body}")
else:
    print(f"  Save FAILED ({code}): {body}")
    sys.exit(1)

# Step 3: Fetch and verify
print("\nSTEP 3: Verify via GET /settings")
code, saved = api_call(f"{BASE}/settings", headers=auth)
if code != 200:
    print(f"  Fetch FAILED ({code}): {saved}")
    sys.exit(1)

all_ok = True
for key, expected in test_coords.items():
    actual = saved.get(key, "MISSING")
    status = "OK" if actual == expected else "FAIL"
    if actual != expected:
        all_ok = False
    print(f"  [{status}] {key}: expected={expected}, got={actual}")

print("\n" + "=" * 60)
if all_ok:
    print("ALL COORDINATES PERSISTED CORRECTLY!")
    print("Coordinates will survive page reloads.")
else:
    print("SOME COORDINATES FAILED!")
    sys.exit(1)
print("=" * 60)
