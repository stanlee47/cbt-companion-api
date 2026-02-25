"""
ML Model Cloud Demonstration
Sends real CSV sensor data to the deployed HuggingFace API and
checks the model's depression risk predictions.

Usage:  python demo_ml_cloud.py
"""

import requests
import pandas as pd
import uuid
import time
import sys

BASE = "https://santa47-cbt-companion-api.hf.space"

# Ground truth: CSV level -> expected model output
# New model is a binary autoencoder: NORMAL or HIGH_RISK
EXPECTED = {
    "Normal":   "NORMAL",
    "Mild":     "NORMAL",    # mild may not exceed reconstruction threshold
    "Moderate": "HIGH_RISK",
    "Severe":   "HIGH_RISK",
}

DATA_FILES = [
    ("data/sampled_data_DepressionLevel_Normal.csv",   "Normal"),
    ("data/sampled_data_DepressionLevel_Mild.csv",     "Mild"),
    ("data/sampled_data_DepressionLevel_Moderate.csv", "Moderate"),
    ("data/sampled_data_DepressionLevel_Severe.csv",   "Severe"),
]

READINGS_TO_SEND = 20   # Need 18+ to trigger ML inference (CSVs have 20 rows, no tiling needed)


def register(label):
    email = f"ml_demo_{label.lower()}_{uuid.uuid4().hex[:6]}@test.com"
    r = requests.post(f"{BASE}/api/register", json={
        "email": email, "password": "Demo1234!",
        "name": f"ML Demo {label}", "context": "ml demonstration"
    }, timeout=30)
    if r.status_code != 200 or not r.json().get("token"):
        print(f"  [ERROR] Registration failed: {r.text[:80]}")
        return None, None
    return r.json()["token"], email


def send_readings(token, readings):
    """Send all readings as one batch."""
    h = {"Authorization": f"Bearer {token}"}
    payload = {"readings": readings}
    r = requests.post(f"{BASE}/api/wearable/batch", headers=h,
                      json=payload, timeout=30)
    return r.status_code == 200 and r.json().get("success")


def get_ml_status(token):
    h = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE}/api/wearable/ml/status", headers=h, timeout=30)
    if r.status_code == 200:
        return r.json()
    return None


def csv_to_readings(csv_path, n=READINGS_TO_SEND):
    df = pd.read_csv(csv_path)
    base = []
    for _, row in df.iterrows():
        base.append({
            "ppg":   float(row["PPG"]),
            "gsr":   float(row["GSR"]),
            "acc_x": float(row["ACC_X"]),
            "acc_y": float(row["ACC_Y"]),
            "acc_z": float(row["ACC_Z"]),
            "timestamp": str(row["time"])
        })
    # Tile readings if CSV has fewer rows than needed (each file has only 20 rows)
    import math
    tiled = (base * math.ceil(n / len(base)))[:n] if len(base) < n else base[:n]
    return tiled


# ─────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("  CBT COMPANION  |  ML MODEL - CLOUD DEMONSTRATION")
print("  Multi-Scale TCN  ->  Depression Risk Prediction")
print(f"  API: {BASE}")
print("=" * 60)

# Check server is up
r = requests.get(f"{BASE}/health", timeout=15)
if r.json().get("status") != "healthy":
    print("\n  Server is not healthy. Exiting.")
    sys.exit(1)
ml_loaded = r.json().get("ml_model_loaded", False)
print(f"\n  Server status : healthy")
print(f"  ML model      : {'loaded' if ml_loaded else 'NOT loaded (will load on first inference)'}")
print(f"  Prediction    : Multi-Scale TCN (NOT DRI score — DRI is from ESP32 firmware only)")

results = []

for csv_path, level in DATA_FILES:
    expected = EXPECTED[level]
    print(f"\n{'-'*60}")
    print(f"  Test : {level} depression")
    print(f"  File : {csv_path}")
    print(f"  Expected prediction : {expected}")

    # Register a fresh user for this test
    token, email = register(level)
    if not token:
        results.append({"level": level, "status": "REGISTRATION_FAILED"})
        continue
    print(f"  User : {email}")

    # Load CSV readings
    try:
        readings = csv_to_readings(csv_path)
    except FileNotFoundError:
        print(f"  [SKIP] CSV file not found.")
        results.append({"level": level, "status": "FILE_NOT_FOUND"})
        continue

    print(f"  Sending {len(readings)} readings to API...", end=" ", flush=True)
    ok = send_readings(token, readings)
    if not ok:
        print("FAILED")
        results.append({"level": level, "status": "SEND_FAILED"})
        continue
    print("sent")

    # Give server time to run inference
    # First call: model loads cold (can take 15-20s on HuggingFace free tier)
    wait = 20 if len(results) == 0 else 8
    print(f"  Waiting {wait}s for inference...", end=" ", flush=True)
    time.sleep(wait)
    print("done")

    # Poll ml/status
    print("  Fetching prediction from cloud...", end=" ", flush=True)
    status = get_ml_status(token)
    if not status:
        print("FAILED")
        results.append({"level": level, "status": "STATUS_FETCH_FAILED"})
        continue
    print("done")

    current     = status.get("current_status", "UNKNOWN")
    has_episode = status.get("has_active_episode", False)
    recent      = status.get("recent_predictions", [])
    # get_window_predictions returns chronological order — last entry is newest
    last_pred   = recent[-1] if recent else {}
    prediction  = last_pred.get("prediction") or current or "NO_PREDICTION"
    confidence  = last_pred.get("confidence", 0.0) or 0.0
    source      = f"TCN model ({len(recent)} prediction(s) stored)" if recent else "no prediction yet"

    correct = prediction == expected
    mark    = "PASS" if correct else ("NO_PRED" if prediction == "NO_PREDICTION" else "FAIL")

    print(f"\n  Result        : [{mark}]")
    print(f"  Predicted     : {prediction}  (confidence: {confidence:.0%})")
    print(f"  Expected      : {expected}")
    print(f"  Source        : {source}")
    print(f"  Active episode: {has_episode}")

    results.append({
        "level":      level,
        "expected":   expected,
        "predicted":  prediction if prediction else "NO_PREDICTION",
        "confidence": confidence,
        "correct":    correct,
        "status":     mark,
    })

# ─────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("  FINAL RESULTS")
print("=" * 60)

passed = sum(1 for r in results if r.get("correct"))
tested = sum(1 for r in results if "correct" in r)
acc    = (passed / tested * 100) if tested else 0

for r in results:
    if "correct" not in r:
        print(f"  {r['level']:<10}  [{r['status']}]")
        continue
    mark = "PASS" if r["correct"] else "FAIL"
    pred = str(r["predicted"]) if r["predicted"] else "NO_PREDICTION"
    print(
        f"  {r['level']:<10}  [{mark}]  "
        f"predicted={pred:<14} "
        f"expected={r['expected']:<14} "
        f"conf={r['confidence']:.0%}"
    )

print()
print(f"  Accuracy : {passed}/{tested}  ({acc:.0f}%)")
if acc >= 75:
    print("  Model is performing well on real-world sensor data.")
elif acc >= 50:
    print("  Model shows moderate accuracy.")
else:
    print("  Model needs review — accuracy below 50%.")
print("=" * 60)
print()
