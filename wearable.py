"""
Wearable Device Module
Handles sensor data from wearable devices (PPG, GSR, Accelerometer)
Includes ML-based depression risk prediction
"""

from flask import Blueprint, request, jsonify
from auth import token_required
from database import get_db
from datetime import datetime

try:
    from fcm_push import send_stress_alert as fcm_send
    FCM_ENABLED = True
except Exception as _fcm_err:
    print(f"⚠️  FCM not available: {_fcm_err}")
    FCM_ENABLED = False

# Import ML inference (will be initialized at startup)
try:
    from ml_inference import predict_risk
    ML_ENABLED = True
except Exception as e:
    print(f"⚠️  ML inference not available: {str(e)}")
    ML_ENABLED = False

wearable_bp = Blueprint('wearable', __name__)


# ==================== ML INFERENCE HELPER ====================

def run_ml_inference_and_alert(user_id: str, record_id: str, db):
    """
    Run ML inference on recent sensor data and trigger alerts if needed.
    This runs after each new sensor reading is saved.
    Returns the prediction result dict or None.
    """
    if not ML_ENABLED:
        return None

    try:
        # Get recent readings (need at least 25 for 5 windows of 5 samples)
        recent_readings = db.get_recent_readings_for_ml(user_id, limit=50)

        if len(recent_readings) < 25:
            # Not enough data yet
            return {"status": "waiting", "readings_count": len(recent_readings), "needed": 25}

        # Run ML prediction
        prediction_result = predict_risk(recent_readings)

        if not prediction_result:
            return None

        prediction = prediction_result["prediction"]
        confidence = prediction_result["confidence"]
        risk_level = prediction_result["risk_level"]

        # Update the wearable record with prediction
        db.update_ml_prediction(record_id, prediction, confidence, risk_level)

        # Handle depression episodes based on risk level
        if risk_level >= 1:  # MILD_STRESS or HIGH_STRESS
            # Send FCM push notification to user's phone
            if FCM_ENABLED:
                try:
                    fcm_token = db.get_fcm_token(user_id)
                    if fcm_token and db.fcm_cooldown_ok(user_id, cooldown_minutes=30):
                        condition = 'HIGH_STRESS' if risk_level == 2 else 'MILD_STRESS'
                        sent = fcm_send(
                            fcm_token=fcm_token,
                            alert_id=record_id,
                            condition=condition,
                            dri_score=float(confidence),
                        )
                        if sent:
                            db.update_fcm_sent_time(user_id)
                    elif fcm_token:
                        print(f"ℹ️  FCM skipped for {user_id} — still in 30-min cooldown")
                except Exception as fcm_err:
                    print(f"⚠️  FCM push failed (non-fatal): {fcm_err}")

            # Check if there's an active episode
            active_episode = db.get_active_depression_episode(user_id)

            if active_episode:
                # Update existing episode
                db.update_depression_episode(active_episode["id"], risk_level, confidence)
            else:
                # Start new episode
                db.start_depression_episode(user_id, risk_level, confidence)

            # Create crisis flag for high stress
            if risk_level == 2:  # HIGH_STRESS
                # Get user info
                user = db.get_user_by_id(user_id)
                if user:
                    # Create crisis flag for admin monitoring
                    db.flag_crisis(
                        user_id=user_id,
                        user_name=user.get("name", "Unknown"),
                        user_email=user.get("email", ""),
                        session_id="wearable_ml_detection",
                        message_content=f"ML Model detected HIGH STRESS: {prediction} (confidence: {confidence:.2%})",
                        trigger_word="HIGH_STRESS_ML"
                    )

                print(f"🚨 HIGH STRESS ALERT for user {user_id}: {prediction} ({confidence:.2%})")

        else:  # NORMAL
            # Check if we should end an active episode
            active_episode = db.get_active_depression_episode(user_id)

            if active_episode:
                # Count consecutive normal readings
                # End episode if user has been normal for last 5 readings
                recent_predictions = db.get_ml_prediction_history(user_id, limit=5)
                if len(recent_predictions) >= 5:
                    all_normal = all(p["risk_level"] == 0 for p in recent_predictions)
                    if all_normal:
                        db.end_depression_episode(active_episode["id"])
                        print(f"✅ Depression episode ended for user {user_id}")

        return prediction_result

    except Exception as e:
        print(f"❌ Error in ML inference: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


# ==================== SENSOR DATA ENDPOINTS ====================

@wearable_bp.route("/api/wearable/data", methods=["POST"])
@token_required
def receive_sensor_data():
    """
    Receive sensor data from wearable device.

    Expected JSON payload:
    {
        "ppg": 75.5,           # Photoplethysmography value (heart rate/pulse)
        "gsr": 2.3,            # Galvanic Skin Response (skin conductance)
        "acc_x": 0.12,         # Accelerometer X-axis
        "acc_y": -0.05,        # Accelerometer Y-axis
        "acc_z": 9.81,         # Accelerometer Z-axis
        "timestamp": "2024-01-31T12:00:00Z"  # Optional: device timestamp
    }
    """
    try:
        user = request.current_user
        db = get_db()

        data = request.json

        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Extract sensor values
        ppg = data.get("ppg")
        gsr = data.get("gsr")
        acc_x = data.get("acc_x")
        acc_y = data.get("acc_y")
        acc_z = data.get("acc_z")
        device_timestamp = data.get("timestamp")

        # Validate required fields
        if ppg is None or gsr is None:
            return jsonify({"error": "ppg and gsr values are required"}), 400

        if acc_x is None or acc_y is None or acc_z is None:
            return jsonify({"error": "acc_x, acc_y, and acc_z values are required"}), 400

        # Save to database
        record_id = db.save_wearable_data(
            user_id=user["id"],
            ppg=float(ppg),
            gsr=float(gsr),
            acc_x=float(acc_x),
            acc_y=float(acc_y),
            acc_z=float(acc_z),
            device_timestamp=device_timestamp
        )

        # Run ML inference and check for depression risk
        run_ml_inference_and_alert(user["id"], record_id, db)

        return jsonify({
            "success": True,
            "record_id": record_id,
            "message": "Sensor data saved successfully"
        })

    except ValueError as e:
        return jsonify({"error": f"Invalid data format: {str(e)}"}), 400
    except Exception as e:
        print(f"Error saving wearable data: {str(e)}")
        return jsonify({"error": "Failed to save sensor data"}), 500


@wearable_bp.route("/api/wearable/batch", methods=["POST"])
@token_required
def receive_batch_data():
    """
    Receive batch sensor data from wearable device.
    Useful for sending multiple readings at once (e.g., when device reconnects).

    Expected JSON payload:
    {
        "readings": [
            {"ppg": 75.5, "gsr": 2.3, "acc_x": 0.1, "acc_y": -0.05, "acc_z": 9.81, "timestamp": "..."},
            {"ppg": 76.0, "gsr": 2.4, "acc_x": 0.2, "acc_y": -0.04, "acc_z": 9.80, "timestamp": "..."},
            ...
        ]
    }
    """
    try:
        user = request.current_user
        db = get_db()

        data = request.json
        readings = data.get("readings", [])

        if not readings:
            return jsonify({"error": "No readings provided"}), 400

        if len(readings) > 1000:
            return jsonify({"error": "Maximum 1000 readings per batch"}), 400

        saved_count = 0
        errors = []

        for i, reading in enumerate(readings):
            try:
                ppg = reading.get("ppg")
                gsr = reading.get("gsr")
                acc_x = reading.get("acc_x")
                acc_y = reading.get("acc_y")
                acc_z = reading.get("acc_z")
                device_timestamp = reading.get("timestamp")

                if None in (ppg, gsr, acc_x, acc_y, acc_z):
                    errors.append(f"Reading {i}: missing required fields")
                    continue

                db.save_wearable_data(
                    user_id=user["id"],
                    ppg=float(ppg),
                    gsr=float(gsr),
                    acc_x=float(acc_x),
                    acc_y=float(acc_y),
                    acc_z=float(acc_z),
                    device_timestamp=device_timestamp
                )
                saved_count += 1

            except (ValueError, TypeError) as e:
                errors.append(f"Reading {i}: {str(e)}")

        # Run ML inference after batch save (uses latest 25+ readings)
        if saved_count > 0:
            try:
                last_record_id = db.conn.execute(
                    """SELECT id FROM wearable_data
                       WHERE user_id = ? ORDER BY recorded_at DESC LIMIT 1""",
                    (user["id"],)
                ).fetchone()
                if last_record_id:
                    run_ml_inference_and_alert(user["id"], last_record_id[0], db)
            except Exception as ml_err:
                print(f"ML inference after batch failed: {str(ml_err)}")

        return jsonify({
            "success": True,
            "saved_count": saved_count,
            "total_readings": len(readings),
            "errors": errors if errors else None
        })

    except Exception as e:
        print(f"Error saving batch wearable data: {str(e)}")
        return jsonify({"error": "Failed to save batch data"}), 500


@wearable_bp.route("/api/wearable/history", methods=["GET"])
@token_required
def get_sensor_history():
    """
    Get user's sensor data history.

    Query parameters:
    - limit: Number of records to return (default: 100, max: 1000)
    - offset: Number of records to skip (for pagination)
    - start_date: Filter records from this date (ISO format)
    - end_date: Filter records until this date (ISO format)
    """
    try:
        user = request.current_user
        db = get_db()

        limit = min(int(request.args.get("limit", 100)), 1000)
        offset = int(request.args.get("offset", 0))
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")

        records = db.get_wearable_history(
            user_id=user["id"],
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date
        )

        return jsonify({
            "records": records,
            "count": len(records),
            "limit": limit,
            "offset": offset
        })

    except Exception as e:
        print(f"Error fetching wearable history: {str(e)}")
        return jsonify({"error": "Failed to fetch sensor history"}), 500


@wearable_bp.route("/api/wearable/latest", methods=["GET"])
@token_required
def get_latest_reading():
    """Get the most recent sensor reading for the user."""
    try:
        user = request.current_user
        db = get_db()

        record = db.get_latest_wearable_data(user["id"])

        if not record:
            return jsonify({
                "record": None,
                "message": "No sensor data found"
            })

        return jsonify({
            "record": record
        })

    except Exception as e:
        print(f"Error fetching latest wearable data: {str(e)}")
        return jsonify({"error": "Failed to fetch latest reading"}), 500


@wearable_bp.route("/api/wearable/stats", methods=["GET"])
@token_required
def get_sensor_stats():
    """
    Get aggregated statistics for user's sensor data.

    Query parameters:
    - period: 'day', 'week', 'month' (default: 'day')
    """
    try:
        user = request.current_user
        db = get_db()

        period = request.args.get("period", "day")
        if period not in ("day", "week", "month"):
            return jsonify({"error": "Invalid period. Use 'day', 'week', or 'month'"}), 400

        stats = db.get_wearable_stats(user["id"], period)

        return jsonify({
            "period": period,
            "stats": stats
        })

    except Exception as e:
        print(f"Error fetching wearable stats: {str(e)}")
        return jsonify({"error": "Failed to fetch sensor statistics"}), 500


# ==================== DEVICE API KEY ENDPOINTS ====================

@wearable_bp.route("/api/wearable/device/register", methods=["POST"])
@token_required
def register_device():
    """
    Generate a new device API key for the authenticated user.
    This key can be used by ESP32 to send data without JWT.

    Optional JSON payload:
    {
        "device_name": "My ESP32 Wearable"  # Optional, defaults to "ESP32 Wearable"
    }

    Returns the API key - SAVE IT, it won't be shown again in full!
    """
    try:
        user = request.current_user
        db = get_db()

        data = request.json or {}
        device_name = data.get("device_name", "ESP32 Wearable")

        # Limit to 5 active devices per user
        existing_keys = db.get_user_device_keys(user["id"])
        active_keys = [k for k in existing_keys if k["is_active"]]
        if len(active_keys) >= 5:
            return jsonify({
                "error": "Maximum 5 active devices allowed. Please revoke an existing device first."
            }), 400

        result = db.create_device_key(user["id"], device_name)

        return jsonify({
            "success": True,
            "message": "Device registered successfully. Save the API key - it won't be shown again!",
            "device": {
                "id": result["id"],
                "api_key": result["api_key"],
                "device_name": result["device_name"],
                "created_at": result["created_at"]
            }
        })

    except Exception as e:
        print(f"Error registering device: {str(e)}")
        return jsonify({"error": "Failed to register device"}), 500


@wearable_bp.route("/api/wearable/device/keys", methods=["GET"])
@token_required
def list_device_keys():
    """Get all device keys for the authenticated user (API keys are masked)."""
    try:
        user = request.current_user
        db = get_db()

        keys = db.get_user_device_keys(user["id"])

        return jsonify({
            "devices": keys
        })

    except Exception as e:
        print(f"Error listing device keys: {str(e)}")
        return jsonify({"error": "Failed to list devices"}), 500


@wearable_bp.route("/api/wearable/device/<key_id>", methods=["DELETE"])
@token_required
def revoke_device(key_id):
    """Revoke a device API key."""
    try:
        user = request.current_user
        db = get_db()

        success = db.revoke_device_key(key_id, user["id"])

        if success:
            return jsonify({
                "success": True,
                "message": "Device revoked successfully"
            })
        else:
            return jsonify({"error": "Device not found or already revoked"}), 404

    except Exception as e:
        print(f"Error revoking device: {str(e)}")
        return jsonify({"error": "Failed to revoke device"}), 500


@wearable_bp.route("/api/wearable/device/data", methods=["POST"])
def receive_device_data():
    """
    Receive sensor data from ESP32 using device API key.
    NO JWT required - uses X-Device-Key header instead.

    Required Header:
        X-Device-Key: <your_device_api_key>

    Expected JSON payload:
    {
        "ppg": 75.5,
        "gsr": 2.3,
        "acc_x": 0.12,
        "acc_y": -0.05,
        "acc_z": 9.81,
        "timestamp": "2024-01-31T12:00:00Z"  # Optional
    }
    """
    try:
        # Get device API key from header
        api_key = request.headers.get("X-Device-Key")

        if not api_key:
            return jsonify({"error": "X-Device-Key header is required"}), 401

        db = get_db()

        # Validate API key and get user
        user = db.get_user_by_device_key(api_key)

        if not user:
            return jsonify({"error": "Invalid or revoked device key"}), 401

        data = request.json

        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Extract sensor values
        ppg = data.get("ppg")
        gsr = data.get("gsr")
        acc_x = data.get("acc_x")
        acc_y = data.get("acc_y")
        acc_z = data.get("acc_z")
        device_timestamp = data.get("timestamp")

        # Validate required fields
        if ppg is None or gsr is None:
            return jsonify({"error": "ppg and gsr values are required"}), 400

        if acc_x is None or acc_y is None or acc_z is None:
            return jsonify({"error": "acc_x, acc_y, and acc_z values are required"}), 400

        # Save to database
        record_id = db.save_wearable_data(
            user_id=user["id"],
            ppg=float(ppg),
            gsr=float(gsr),
            acc_x=float(acc_x),
            acc_y=float(acc_y),
            acc_z=float(acc_z),
            device_timestamp=device_timestamp
        )

        # Run ML inference and check for depression risk
        ml_result = run_ml_inference_and_alert(user["id"], record_id, db)

        response_data = {
            "success": True,
            "record_id": record_id
        }
        if ml_result:
            response_data["ml_prediction"] = ml_result

        return jsonify(response_data)

    except ValueError as e:
        return jsonify({"error": f"Invalid data format: {str(e)}"}), 400
    except Exception as e:
        print(f"Error saving device data: {str(e)}")
        return jsonify({"error": "Failed to save sensor data"}), 500


# ==================== ALERT ENDPOINTS ====================

@wearable_bp.route("/api/wearable/alerts/latest", methods=["GET"])
@token_required
def get_latest_alert():
    """
    Get the latest unacknowledged HIGH_STRESS or MILD_STRESS alert.
    Used by the Flutter app for polling-based alert detection.
    """
    try:
        user = request.current_user
        db = get_db()

        # Find the latest unacknowledged stress reading
        result = db.conn.execute(
            """SELECT id, risk_level, ml_confidence, ml_prediction, ppg, gsr,
                      recorded_at, condition
               FROM wearable_data
               WHERE user_id = ?
                 AND risk_level >= 1
                 AND (acknowledged = 0 OR acknowledged IS NULL)
               ORDER BY recorded_at DESC
               LIMIT 1""",
            (user["id"],)
        ).fetchone()

        if not result:
            return jsonify({"has_alert": False, "alert": None})

        alert = {
            "id": result[0],
            "dri_score": result[2] if result[2] else 0.0,
            "condition": result[7] if result[7] else ("HIGH_STRESS" if result[1] == 2 else "MILD_STRESS"),
            "ppg": result[4],
            "gsr": result[5],
            "recorded_at": result[6],
        }

        return jsonify({"has_alert": True, "alert": alert})

    except Exception as e:
        print(f"Error fetching latest alert: {str(e)}")
        return jsonify({"error": "Failed to fetch alert"}), 500


@wearable_bp.route("/api/wearable/alerts", methods=["GET"])
@token_required
def get_all_alerts():
    """
    Get all unacknowledged stress alerts for the user.
    """
    try:
        user = request.current_user
        db = get_db()

        results = db.conn.execute(
            """SELECT id, risk_level, ml_confidence, ml_prediction, ppg, gsr,
                      recorded_at, condition
               FROM wearable_data
               WHERE user_id = ?
                 AND risk_level >= 1
                 AND (acknowledged = 0 OR acknowledged IS NULL)
               ORDER BY recorded_at DESC
               LIMIT 50""",
            (user["id"],)
        ).fetchall()

        alerts = []
        high_count = 0
        mild_count = 0
        for r in results:
            condition = r[7] if r[7] else ("HIGH_STRESS" if r[1] == 2 else "MILD_STRESS")
            alerts.append({
                "id": r[0],
                "dri_score": r[2] if r[2] else 0.0,
                "condition": condition,
                "ppg": r[4],
                "gsr": r[5],
                "recorded_at": r[6],
            })
            if r[1] == 2:
                high_count += 1
            elif r[1] == 1:
                mild_count += 1

        return jsonify({
            "alerts": alerts,
            "count": len(alerts),
            "high_stress_count": high_count,
            "mild_stress_count": mild_count,
            "has_critical": high_count > 0,
        })

    except Exception as e:
        print(f"Error fetching alerts: {str(e)}")
        return jsonify({"error": "Failed to fetch alerts"}), 500


@wearable_bp.route("/api/wearable/alerts/acknowledge", methods=["POST"])
@token_required
def acknowledge_alerts():
    """
    Acknowledge stress alerts. If alert_id is provided, acknowledge that specific alert.
    Otherwise, acknowledge all unacknowledged alerts for the user.
    """
    try:
        user = request.current_user
        db = get_db()

        data = request.json or {}
        alert_id = data.get("alert_id")

        if alert_id:
            db.conn.execute(
                """UPDATE wearable_data SET acknowledged = 1
                   WHERE id = ? AND user_id = ?""",
                (alert_id, user["id"])
            )
        else:
            db.conn.execute(
                """UPDATE wearable_data SET acknowledged = 1
                   WHERE user_id = ? AND risk_level >= 1
                     AND (acknowledged = 0 OR acknowledged IS NULL)""",
                (user["id"],)
            )

        db.conn.commit()

        return jsonify({"success": True, "message": "Alerts acknowledged"})

    except Exception as e:
        print(f"Error acknowledging alerts: {str(e)}")
        return jsonify({"error": "Failed to acknowledge alerts"}), 500


# ==================== ML STATUS ENDPOINTS ====================

@wearable_bp.route("/api/wearable/ml/status", methods=["GET"])
@token_required
def get_ml_status():
    """
    Get current ML-based depression risk status for the user.
    Returns latest prediction and depression episode information.
    """
    try:
        user = request.current_user
        db = get_db()

        # Get depression statistics
        stats = db.get_user_depression_stats(user["id"])

        # Get active episode details if any
        active_episode = db.get_active_depression_episode(user["id"]) if stats.get("has_active_episode") else None

        # Get recent prediction history
        recent_predictions = db.get_ml_prediction_history(user["id"], limit=10)

        return jsonify({
            "ml_enabled": ML_ENABLED,
            "current_status": stats.get("latest_prediction"),
            "has_active_episode": stats.get("has_active_episode"),
            "active_episode": active_episode,
            "statistics": {
                "total_episodes": stats.get("total_episodes"),
                "episodes_last_7_days": stats.get("episodes_last_7_days"),
                "peak_risk_last_7_days": stats.get("peak_risk_last_7_days")
            },
            "recent_predictions": recent_predictions
        })

    except Exception as e:
        print(f"Error fetching ML status: {str(e)}")
        return jsonify({"error": "Failed to fetch ML status"}), 500


@wearable_bp.route("/api/wearable/ml/episodes", methods=["GET"])
@token_required
def get_depression_episodes():
    """Get all depression episodes for the user."""
    try:
        user = request.current_user
        db = get_db()

        limit = min(int(request.args.get("limit", 50)), 100)
        episodes = db.get_all_depression_episodes(user["id"], limit=limit)

        return jsonify({
            "episodes": episodes,
            "count": len(episodes)
        })

    except Exception as e:
        print(f"Error fetching depression episodes: {str(e)}")
        return jsonify({"error": "Failed to fetch episodes"}), 500


@wearable_bp.route("/api/wearable/device/batch", methods=["POST"])
def receive_device_batch():
    """
    Receive batch sensor data from ESP32 using device API key.
    Useful when device stores readings and sends in bulk.

    Required Header:
        X-Device-Key: <your_device_api_key>

    Expected JSON payload:
    {
        "readings": [
            {"ppg": 75.5, "gsr": 2.3, "acc_x": 0.1, "acc_y": -0.05, "acc_z": 9.81, "timestamp": "..."},
            ...
        ]
    }
    """
    try:
        # Get device API key from header
        api_key = request.headers.get("X-Device-Key")

        if not api_key:
            return jsonify({"error": "X-Device-Key header is required"}), 401

        db = get_db()

        # Validate API key and get user
        user = db.get_user_by_device_key(api_key)

        if not user:
            return jsonify({"error": "Invalid or revoked device key"}), 401

        data = request.json
        readings = data.get("readings", [])

        if not readings:
            return jsonify({"error": "No readings provided"}), 400

        if len(readings) > 1000:
            return jsonify({"error": "Maximum 1000 readings per batch"}), 400

        saved_count = 0
        errors = []

        for i, reading in enumerate(readings):
            try:
                ppg = reading.get("ppg")
                gsr = reading.get("gsr")
                acc_x = reading.get("acc_x")
                acc_y = reading.get("acc_y")
                acc_z = reading.get("acc_z")
                device_timestamp = reading.get("timestamp")

                if None in (ppg, gsr, acc_x, acc_y, acc_z):
                    errors.append(f"Reading {i}: missing required fields")
                    continue

                db.save_wearable_data(
                    user_id=user["id"],
                    ppg=float(ppg),
                    gsr=float(gsr),
                    acc_x=float(acc_x),
                    acc_y=float(acc_y),
                    acc_z=float(acc_z),
                    device_timestamp=device_timestamp
                )
                saved_count += 1

            except (ValueError, TypeError) as e:
                errors.append(f"Reading {i}: {str(e)}")

        # Run ML inference after batch save (uses latest 25+ readings)
        if saved_count > 0:
            try:
                last_record_id = db.conn.execute(
                    """SELECT id FROM wearable_data
                       WHERE user_id = ? ORDER BY recorded_at DESC LIMIT 1""",
                    (user["id"],)
                ).fetchone()
                if last_record_id:
                    run_ml_inference_and_alert(user["id"], last_record_id[0], db)
            except Exception as ml_err:
                print(f"ML inference after device batch failed: {str(ml_err)}")

        return jsonify({
            "success": True,
            "saved_count": saved_count,
            "total_readings": len(readings),
            "errors": errors if errors else None
        })

    except Exception as e:
        print(f"Error saving device batch data: {str(e)}")
        return jsonify({"error": "Failed to save batch data"}), 500
