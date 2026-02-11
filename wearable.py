"""
Wearable Device Module
Handles sensor data from wearable devices (PPG, GSR, Accelerometer)
"""

from flask import Blueprint, request, jsonify
from auth import token_required
from database import get_db
from datetime import datetime

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

        return jsonify({
            "success": True,
            "record_id": record_id
        })

    except ValueError as e:
        return jsonify({"error": f"Invalid data format: {str(e)}"}), 400
    except Exception as e:
        print(f"Error saving device data: {str(e)}")
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
        print(f"Error saving device batch data: {str(e)}")
        return jsonify({"error": "Failed to save batch data"}), 500
