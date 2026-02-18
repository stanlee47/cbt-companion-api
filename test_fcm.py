"""
FCM Diagnostic Test
====================
Logs in as a real user, checks FCM status on backend, sends a test push,
then sends real stress sensor data as that user to trigger ML → FCM flow.

Usage:
    python test_fcm.py
"""

import json
import sys
import io
import requests
import csv
import time

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_URL = "https://santa47-cbt-companion-api.hf.space"

# ---------- credentials ----------
EMAIL    = "test@example.com"   # <-- your test account email
PASSWORD = "test123"             # <-- your test account password
# ---------------------------------

DATA_DIR = "data"
SEVERE_CSV = "sampled_data_DepressionLevel_Severe.csv"


def login(email, password):
    resp = requests.post(
        f"{BASE_URL}/api/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    if resp.status_code == 200 and resp.json().get("success"):
        return resp.json()["token"]
    raise RuntimeError(f"Login failed ({resp.status_code}): {resp.text}")


def auth_headers(token):
    return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}


def check_health():
    resp = requests.get(f"{BASE_URL}/health", timeout=10)
    return resp.json()


def check_fcm_status(token):
    resp = requests.get(
        f"{BASE_URL}/api/user/fcm-debug",
        headers=auth_headers(token),
        timeout=10,
    )
    return resp.json()


def send_test_push(token):
    resp = requests.get(
        f"{BASE_URL}/api/user/fcm-debug?send_test=1",
        headers=auth_headers(token),
        timeout=15,
    )
    return resp.json()


def load_severe_data():
    readings = []
    with open(f"{DATA_DIR}/{SEVERE_CSV}", "r") as f:
        for row in csv.DictReader(f):
            readings.append({
                "ppg":   float(row["PPG"]),
                "gsr":   float(row["GSR"]),
                "acc_x": float(row["ACC_X"]),
                "acc_y": float(row["ACC_Y"]),
                "acc_z": float(row["ACC_Z"]),
            })
    return readings


def send_sensor_reading(token, reading):
    resp = requests.post(
        f"{BASE_URL}/api/wearable/data",
        headers=auth_headers(token),
        json=reading,
        timeout=20,
    )
    return resp.json()


def main():
    print("\n" + "="*60)
    print("  CBT COMPANION — FCM DIAGNOSTIC TEST")
    print("="*60)

    # 1. Health check
    print("\n[1] Health check...")
    health = check_health()
    print(f"  Status:          {health.get('status')}")
    print(f"  ML model loaded: {health.get('ml_model_loaded')}")
    fcm_enabled = health.get("fcm_enabled")
    print(f"  FCM enabled:     {fcm_enabled}")
    if not fcm_enabled:
        print("\n  ❌ firebase-admin is NOT loaded on the server.")
        print("     → Check HuggingFace Space logs. The Space may still be building,")
        print("       or FIREBASE_SERVICE_ACCOUNT secret may be missing/invalid.")

    # 2. Login
    print(f"\n[2] Logging in as {EMAIL}...")
    try:
        token = login(EMAIL, PASSWORD)
        print("  ✅ Login OK — JWT acquired")
    except RuntimeError as e:
        print(f"  ❌ {e}")
        return

    # 3. FCM token check
    print("\n[3] Checking FCM token in database...")
    status = check_fcm_status(token)
    print(f"  FCM backend enabled: {status.get('fcm_backend_enabled')}")
    print(f"  User has token:      {status.get('user_has_token')}")
    print(f"  Token preview:       {status.get('token_preview', 'N/A')}")

    if not status.get("user_has_token"):
        print("\n  ❌ No FCM token stored for this user!")
        print("     → Open the new APK on your phone and LOG IN.")
        print("       The token uploads automatically when you log in.")
        print("     → Then run this script again.")
        print("\n  Aborting — cannot test FCM without a stored token.")
        return

    # 4. Test push
    print("\n[4] Sending test FCM push notification...")
    push_result = send_test_push(token)
    test_push = push_result.get("test_push", "unknown")
    print(f"  Result: {test_push}")
    if "SENT" in str(test_push):
        print("\n  ✅ Test push SENT! Check your phone now.")
        print("     If you don't see a notification:")
        print("      • Disable battery optimization for the app")
        print("      • Make sure notifications are allowed for the app")
        print("      • Try with app in background (not foreground)")
    elif "FAILED" in str(test_push):
        print("\n  ❌ FCM send FAILED. Check HuggingFace Space logs for details.")
        return

    time.sleep(3)

    # 5. Stress data trigger test
    print("\n[5] Sending severe stress sensor data as THIS user (ML → FCM flow)...")
    try:
        readings = load_severe_data()
    except FileNotFoundError:
        print(f"  ⚠️  {SEVERE_CSV} not found in {DATA_DIR}/  — skipping stress data step")
        print("     You can manually stress-test via the wearable or test_dry_run.py")
        print("     But make sure to use YOUR device API key (registered under this account).")
        print_summary()
        return

    alert_triggered = False
    for i, reading in enumerate(readings):
        result = send_sensor_reading(token, reading)
        ml = result.get("ml_prediction")
        if ml and isinstance(ml, dict) and ml.get("status") != "waiting":
            pred = ml.get("prediction", "?")
            conf = ml.get("confidence", 0)
            risk = ml.get("risk_level", -1)
            label = {"NORMAL": "[NORMAL]", "MILD_STRESS": "[MILD_STRESS]",
                     "HIGH_STRESS": "[HIGH_STRESS] !!!"}.get(pred, f"[{pred}]")
            print(f"  [{i+1:2d}/{len(readings)}] {label}  conf={conf:.0%}  risk={risk}")
            if risk >= 1:
                alert_triggered = True
                print(f"           ↑ FCM push should fire NOW to ...{status.get('token_preview', '?')}")
        elif ml and isinstance(ml, dict):
            cnt = ml.get("readings_count", "?")
            print(f"  [{i+1:2d}/{len(readings)}] waiting ({cnt}/25 readings)")
        time.sleep(0.3)

    print_summary(alert_triggered)


def print_summary(alert_triggered=None):
    print("\n" + "="*60)
    print("  SUMMARY")
    print("="*60)
    if alert_triggered is True:
        print("  ✅ Stress detected. If you got no push notification:")
        print("     1. Check phone notifications are allowed for the app")
        print("     2. Check HuggingFace Space logs for FCM errors")
        print("     3. The token may have rotated — log out/in on phone and retry")
    elif alert_triggered is False:
        print("  ⚠️  No stress alert triggered (not enough/wrong data)")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
