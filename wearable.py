"""
Wearable Device Module
Handles sensor data from wearable devices (PPG, GSR, Accelerometer)
Includes DRI (Depression Risk Index) tracking and alert system
"""

import logging
from flask import Blueprint, request, jsonify
from auth import token_required
from database import get_db
from datetime import datetime

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | WEARABLE | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('wearable')

wearable_bp = Blueprint('wearable', __name__)


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
        "dri_score": 0.45,     # Optional: Depression Risk Index
        "condition": "NORMAL", # Optional: NORMAL, MILD_STRESS, HIGH_STRESS
        "timestamp": "2024-01-31T12:00:00Z"  # Optional: device timestamp
    }
    """
    try:
        user = request.current_user
        db = get_db()

        data = request.json
        logger.info(f"📥 Received data from user {user['name']} ({user['email']})")

        if not data:
            logger.warning(f"❌ No data provided by user {user['email']}")
            return jsonify({"error": "No data provided"}), 400

        # Extract sensor values
        ppg = data.get("ppg")
        gsr = data.get("gsr")
        acc_x = data.get("acc_x")
        acc_y = data.get("acc_y")
        acc_z = data.get("acc_z")
        dri_score = data.get("dri_score")
        condition = data.get("condition")
        device_timestamp = data.get("timestamp")

        # Validate required fields
        if ppg is None or gsr is None:
            logger.warning(f"❌ Missing ppg/gsr from user {user['email']}")
            return jsonify({"error": "ppg and gsr values are required"}), 400

        if acc_x is None or acc_y is None or acc_z is None:
            logger.warning(f"❌ Missing accelerometer data from user {user['email']}")
            return jsonify({"error": "acc_x, acc_y, and acc_z values are required"}), 400

        # Log sensor data
        logger.info(f"📊 Sensors: PPG={ppg:.2f}, GSR={gsr:.2f}, ACC=({acc_x:.2f}, {acc_y:.2f}, {acc_z:.2f})")
        if dri_score is not None:
            logger.info(f"🧠 DRI Score: {dri_score:.3f} | Condition: {condition}")
            if condition == "HIGH_STRESS":
                logger.warning(f"🚨 HIGH STRESS DETECTED for user {user['name']} ({user['email']}) - DRI: {dri_score:.3f}")

        # Save to database
        record_id = db.save_wearable_data(
            user_id=user["id"],
            ppg=float(ppg),
            gsr=float(gsr),
            acc_x=float(acc_x),
            acc_y=float(acc_y),
            acc_z=float(acc_z),
            dri_score=float(dri_score) if dri_score is not None else None,
            condition=condition,
            device_timestamp=device_timestamp
        )

        logger.info(f"✅ Data saved successfully - Record ID: {record_id}")

        return jsonify({
            "success": True,
            "record_id": record_id,
            "message": "Sensor data saved successfully"
        })

    except ValueError as e:
        logger.error(f"❌ Invalid data format: {str(e)}")
        return jsonify({"error": f"Invalid data format: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"❌ Error saving wearable data: {str(e)}")
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
        "dri_score": 0.45,     # Optional: from ESP32 calculation
        "condition": "NORMAL", # Optional: NORMAL, MILD_STRESS, HIGH_STRESS
        "timestamp": "2024-01-31T12:00:00Z"  # Optional
    }
    """
    try:
        # Get device API key from header
        api_key = request.headers.get("X-Device-Key")
        logger.info(f"📥 Incoming ESP32 request - API Key: {api_key[:8]}..." if api_key else "📥 Incoming ESP32 request - NO API KEY")

        if not api_key:
            logger.warning("❌ Missing X-Device-Key header")
            return jsonify({"error": "X-Device-Key header is required"}), 401

        db = get_db()

        # Validate API key and get user
        user = db.get_user_by_device_key(api_key)

        if not user:
            logger.warning(f"❌ Invalid or revoked device key: {api_key[:8]}...")
            return jsonify({"error": "Invalid or revoked device key"}), 401

        logger.info(f"✅ Authenticated device for user: {user['name']} ({user['email']})")

        data = request.json

        if not data:
            logger.warning(f"❌ No data in request body")
            return jsonify({"error": "No data provided"}), 400

        # Extract sensor values
        ppg = data.get("ppg")
        gsr = data.get("gsr")
        acc_x = data.get("acc_x")
        acc_y = data.get("acc_y")
        acc_z = data.get("acc_z")
        dri_score = data.get("dri_score")
        condition = data.get("condition")
        device_timestamp = data.get("timestamp")

        # Validate required fields
        if ppg is None or gsr is None:
            logger.warning(f"❌ Missing ppg/gsr values")
            return jsonify({"error": "ppg and gsr values are required"}), 400

        if acc_x is None or acc_y is None or acc_z is None:
            logger.warning(f"❌ Missing accelerometer values")
            return jsonify({"error": "acc_x, acc_y, and acc_z values are required"}), 400

        # Log the incoming sensor data
        logger.info(f"📊 SENSOR DATA | PPG: {ppg:.2f} | GSR: {gsr:.2f} | ACC: ({acc_x:.2f}, {acc_y:.2f}, {acc_z:.2f})")

        if dri_score is not None and condition:
            logger.info(f"🧠 MENTAL STATE | DRI: {dri_score:.3f} | Condition: {condition}")

            # Alert on HIGH_STRESS
            if condition == "HIGH_STRESS":
                logger.warning(f"🚨🚨🚨 HIGH STRESS ALERT 🚨🚨🚨")
                logger.warning(f"🚨 User: {user['name']} ({user['email']})")
                logger.warning(f"🚨 DRI Score: {dri_score:.3f}")
                logger.warning(f"🚨 This user may need immediate attention!")

        # Save to database
        record_id = db.save_wearable_data(
            user_id=user["id"],
            ppg=float(ppg),
            gsr=float(gsr),
            acc_x=float(acc_x),
            acc_y=float(acc_y),
            acc_z=float(acc_z),
            dri_score=float(dri_score) if dri_score is not None else None,
            condition=condition,
            device_timestamp=device_timestamp
        )

        logger.info(f"✅ Data saved | Record ID: {record_id}")

        return jsonify({
            "success": True,
            "record_id": record_id
        })

    except ValueError as e:
        logger.error(f"❌ Invalid data format: {str(e)}")
        return jsonify({"error": f"Invalid data format: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"❌ Error saving device data: {str(e)}")
        return jsonify({"error": "Failed to save sensor data"}), 500


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

        return jsonify({
            "success": True,
            "saved_count": saved_count,
            "total_readings": len(readings),
            "errors": errors if errors else None
        })

    except Exception as e:
        logger.error(f"❌ Error saving device batch data: {str(e)}")
        return jsonify({"error": "Failed to save batch data"}), 500


# ==================== ALERT ENDPOINTS ====================

@wearable_bp.route("/api/wearable/alerts", methods=["GET"])
@token_required
def get_alerts():
    """
    Get unacknowledged stress alerts for the user.
    Used by Flutter app to check for HIGH_STRESS conditions.

    Returns alerts that need user attention.
    """
    try:
        user = request.current_user
        db = get_db()

        logger.info(f"📋 Checking alerts for user: {user['name']} ({user['email']})")

        alerts = db.get_unacknowledged_alerts(user["id"])

        # Count by severity
        high_stress_count = sum(1 for a in alerts if a["condition"] == "HIGH_STRESS")
        mild_stress_count = sum(1 for a in alerts if a["condition"] == "MILD_STRESS")

        if high_stress_count > 0:
            logger.warning(f"🚨 User {user['name']} has {high_stress_count} HIGH_STRESS alerts!")
        elif mild_stress_count > 0:
            logger.info(f"⚠️ User {user['name']} has {mild_stress_count} MILD_STRESS alerts")
        else:
            logger.info(f"✅ No unacknowledged alerts for user {user['name']}")

        return jsonify({
            "alerts": alerts,
            "count": len(alerts),
            "high_stress_count": high_stress_count,
            "mild_stress_count": mild_stress_count,
            "has_critical": high_stress_count > 0
        })

    except Exception as e:
        logger.error(f"❌ Error fetching alerts: {str(e)}")
        return jsonify({"error": "Failed to fetch alerts"}), 500


@wearable_bp.route("/api/wearable/alerts/latest", methods=["GET"])
@token_required
def get_latest_alert():
    """
    Get the most recent HIGH_STRESS alert for triggering full-screen notification.
    """
    try:
        user = request.current_user
        db = get_db()

        alert = db.get_latest_high_stress_alert(user["id"])

        if alert:
            logger.warning(f"🚨 Returning HIGH_STRESS alert for {user['name']}: DRI={alert['dri_score']:.3f}")
            return jsonify({
                "has_alert": True,
                "alert": alert
            })
        else:
            return jsonify({
                "has_alert": False,
                "alert": None
            })

    except Exception as e:
        logger.error(f"❌ Error fetching latest alert: {str(e)}")
        return jsonify({"error": "Failed to fetch alert"}), 500


@wearable_bp.route("/api/wearable/alerts/acknowledge", methods=["POST"])
@token_required
def acknowledge_alerts():
    """
    Acknowledge alerts so they don't trigger again.

    JSON payload:
    {
        "alert_id": "specific-alert-id"  # Optional: acknowledge specific alert
    }

    If alert_id is not provided, acknowledges ALL alerts for the user.
    """
    try:
        user = request.current_user
        db = get_db()

        data = request.json or {}
        alert_id = data.get("alert_id")

        if alert_id:
            # Acknowledge specific alert
            success = db.acknowledge_alert(alert_id, user["id"])
            if success:
                logger.info(f"✅ Alert {alert_id} acknowledged by {user['name']}")
                return jsonify({
                    "success": True,
                    "message": "Alert acknowledged"
                })
            else:
                logger.warning(f"❌ Alert {alert_id} not found for user {user['name']}")
                return jsonify({"error": "Alert not found"}), 404
        else:
            # Acknowledge all alerts
            count = db.acknowledge_all_alerts(user["id"])
            logger.info(f"✅ {count} alerts acknowledged by {user['name']}")
            return jsonify({
                "success": True,
                "acknowledged_count": count,
                "message": f"{count} alerts acknowledged"
            })

    except Exception as e:
        logger.error(f"❌ Error acknowledging alerts: {str(e)}")
        return jsonify({"error": "Failed to acknowledge alerts"}), 500
