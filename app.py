"""
CBT Companion - Backend API
Multi-user version with authentication and database
Hosted on HuggingFace Spaces
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from groq_client import GroqClient
from database import get_db
from auth import register_user, login_user, token_required
from crisis_detector import check_for_crisis, get_crisis_response, get_crisis_resources
from prompts import NATURAL_ENDINGS
from exercises import get_exercise_for_group
from wearable import wearable_bp
from admin import admin_bp
import os

app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
CORS(app)

# Register blueprints
app.register_blueprint(wearable_bp)
app.register_blueprint(admin_bp)

# Initialize components
groq_client = GroqClient(api_key=os.environ.get("GROQ_API_KEY"))


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "app": "CBT Companion",
        "version": "2.1.0",
        "features": ["multi-user", "auth", "crisis-detection", "wearable-integration"]
    })


# ==================== AUTH ROUTES ====================

@app.route("/api/register", methods=["POST"])
def register():
    """Register a new user."""
    data = request.json
    
    result = register_user(
        email=data.get("email", ""),
        password=data.get("password", ""),
        name=data.get("name", ""),
        context=data.get("context", "person")
    )
    
    if "error" in result:
        return jsonify(result), 400
    
    return jsonify(result)


@app.route("/api/login", methods=["POST"])
def login():
    """Login user."""
    data = request.json
    
    result = login_user(
        email=data.get("email", ""),
        password=data.get("password", "")
    )
    
    if "error" in result:
        return jsonify(result), 401
    
    return jsonify(result)


@app.route("/api/me", methods=["GET"])
@token_required
def get_me():
    """Get current user info."""
    user = request.current_user
    return jsonify({
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "context": user["context"]
    })


# ==================== SESSION ROUTES ====================

@app.route("/api/session/new", methods=["POST"])
@token_required
def new_session():
    """Start a new chat session."""
    user = request.current_user
    db = get_db()
    
    session_id = db.create_session(user["id"])
    
    # Set initial mood if provided
    data = request.json or {}
    if "mood" in data:
        db.update_session(session_id, mood_start=data["mood"])
    
    return jsonify({
        "session_id": session_id,
        "message": f"Hey {user['name']}! 👋 What's on your mind today?",
        "user_name": user["name"]
    })


@app.route("/api/session/status", methods=["GET"])
@token_required
def session_status():
    """Get current session status."""
    session_id = request.args.get("session_id")
    
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    
    db = get_db()
    session = db.get_session(session_id)
    
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    # Verify session belongs to user
    if session["user_id"] != request.current_user["id"]:
        return jsonify({"error": "Unauthorized"}), 403
    
    return jsonify({
        "session_id": session["id"],
        "state": session["state"],
        "locked_group": session["locked_group"],
        "current_stage": session["current_stage"],
        "completed": session["completed"]
    })


@app.route("/api/sessions", methods=["GET"])
@token_required
def get_sessions():
    """Get user's past sessions."""
    user = request.current_user
    db = get_db()
    
    sessions = db.get_user_sessions(user["id"])
    
    return jsonify({"sessions": sessions})


# ==================== CHAT ROUTE ====================

@app.route("/api/chat", methods=["POST"])
@token_required
def chat():
    """
    Main chat endpoint using Beck's 3-Agent Protocol.
    """
    try:
        user = request.current_user
        db = get_db()

        data = request.json
        user_message = data.get("message", "").strip()
        session_id = data.get("session_id")
        conversation_history = data.get("conversation_history", [])

        if not user_message or not session_id:
            return jsonify({"error": "Message and session_id required"}), 400

        # Get session
        session = db.get_session(session_id)
        if not session or session["user_id"] != user["id"]:
            return jsonify({"error": "Session not found"}), 404

        # ========== CRISIS DETECTION ==========
        is_crisis, trigger_word = check_for_crisis(user_message)
        if is_crisis:
            db.flag_crisis(user["id"], user["name"], user["email"],
                          session_id, user_message, trigger_word)
            crisis_response = get_crisis_response(user["name"])
            return jsonify({
                "response": crisis_response,
                "is_crisis": True,
                "crisis_resources": get_crisis_resources()
            })

        # ========== NATURAL EXIT CHECK ==========
        if is_natural_exit(user_message):
            return jsonify(handle_natural_exit(session, user, db, session_id))

        # ========== GET OR CREATE BECK SESSION ==========
        beck_data = db.get_beck_session(session_id)

        if not beck_data:
            # First message - check if distorted using LLM
            classification = groq_client.classify_distortion(user_message)

            if classification["group"] == "G0":
                # No distortion - supportive listening
                response_text = groq_client.generate_supportive_response(
                    user_message=user_message,
                    conversation_history=conversation_history[-6:],
                    user_name=user["name"]
                )
                return jsonify({
                    "response": response_text,
                    "beck_state": None,
                    "is_beck_protocol": False
                })
            else:
                # Distortion detected - START BECK PROTOCOL
                db.create_beck_session(session_id)
                db.update_beck_state(session_id, "VALIDATE",
                                    original_thought=user_message)
                beck_data = db.get_beck_session(session_id)

        # ========== BECK PROTOCOL STATE MACHINE ==========
        from prompts import BECK_STATES, AGENT1_STATES, AGENT3_STATES, get_next_state, get_field_to_save

        current_state = beck_data["beck_state"]

        # Determine which agent handles this state
        if current_state in AGENT1_STATES:
            # Agent 1: Warm Questioner
            response_text = groq_client.agent1_warm_questioner(
                current_state=current_state,
                user_message=user_message,
                beck_data=beck_data,
                user_name=user["name"],
                conversation_history=conversation_history[-6:]
            )

            # Save user's response to appropriate field
            field_to_save = get_field_to_save(current_state)
            next_state = get_next_state(current_state)

            # Extract rating if this is a rating state
            if field_to_save and ('rating' in field_to_save or 'intensity' in field_to_save):
                rating = extract_rating(user_message)
                if rating is not None:
                    db.update_beck_state(session_id, next_state, **{field_to_save: rating})
                else:
                    db.update_beck_state(session_id, next_state)
            elif field_to_save:
                db.update_beck_state(session_id, next_state, **{field_to_save: user_message})
            else:
                db.update_beck_state(session_id, next_state)

        elif current_state == "SUMMARIZING":
            # Agent 2: Clinical Summarizer (internal)
            clinical_summary = groq_client.agent2_clinical_summarizer(beck_data)

            # Move to Agent 3
            db.update_beck_state(session_id, "DELIVER_REFRAME")

            # Get updated beck_data and call Agent 3
            beck_data = db.get_beck_session(session_id)
            response_text = groq_client.agent3_treatment_agent(
                current_state="DELIVER_REFRAME",
                user_message=user_message,
                beck_data=beck_data,
                clinical_summary=clinical_summary,
                user_name=user["name"],
                conversation_history=conversation_history[-6:]
            )

        elif current_state in AGENT3_STATES:
            # Agent 3: Treatment Agent
            # Need clinical summary - regenerate if needed
            clinical_summary = groq_client.agent2_clinical_summarizer(beck_data)

            response_text = groq_client.agent3_treatment_agent(
                current_state=current_state,
                user_message=user_message,
                beck_data=beck_data,
                clinical_summary=clinical_summary,
                user_name=user["name"],
                conversation_history=conversation_history[-6:]
            )

            # Save response and advance state
            field_to_save = get_field_to_save(current_state)
            next_state = get_next_state(current_state)

            if field_to_save and ('rating' in field_to_save or 'belief' in field_to_save or 'intensity' in field_to_save):
                rating = extract_rating(user_message)
                if rating is not None:
                    db.update_beck_state(session_id, next_state, **{field_to_save: rating})
                else:
                    db.update_beck_state(session_id, next_state)
            elif field_to_save:
                db.update_beck_state(session_id, next_state, **{field_to_save: user_message})
            else:
                if next_state:
                    db.update_beck_state(session_id, next_state)
                else:
                    # Protocol complete
                    db.complete_beck_session(session_id)

        else:
            # Fallback
            response_text = groq_client.generate_supportive_response(
                user_message, conversation_history[-6:], user["name"]
            )

        # Get updated state for response
        beck_data = db.get_beck_session(session_id)

        return jsonify({
            "response": response_text,
            "beck_state": beck_data["beck_state"] if beck_data else None,
            "is_beck_protocol": beck_data is not None,
            "protocol_complete": beck_data["beck_state"] == "COMPLETE" if beck_data else False,
            "belief_improvement": calculate_improvement(beck_data) if beck_data else None
        })

    except Exception as e:
        print(f"Error in /api/chat: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Something went wrong"}), 500


# ==================== EXERCISE ROUTES ====================

@app.route("/api/exercise", methods=["GET"])
@token_required
def get_exercise():
    """Get a CBT exercise for the current session."""
    session_id = request.args.get("session_id")
    
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    
    db = get_db()
    session = db.get_session(session_id)
    
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    group = session["locked_group"]
    if not group or group == "G0":
        return jsonify({
            "exercise": None,
            "message": "No specific exercise needed for this session."
        })
    
    exercise = get_exercise_for_group(group)
    
    return jsonify({
        "exercise": exercise,
        "group": group
    })


@app.route("/api/exercise/complete", methods=["POST"])
@token_required
def complete_exercise():
    """Mark an exercise as completed."""
    user = request.current_user
    db = get_db()
    
    data = request.json
    session_id = data.get("session_id")
    exercise_id = data.get("exercise_id")
    exercise_name = data.get("exercise_name", "")
    
    if not exercise_id:
        return jsonify({"error": "exercise_id is required"}), 400
    
    session = db.get_session(session_id) if session_id else None
    group_type = session["locked_group"] if session else None
    
    db.log_exercise_completed(
        user_id=user["id"],
        session_id=session_id,
        exercise_id=exercise_id,
        exercise_name=exercise_name,
        group_type=group_type
    )
    
    return jsonify({
        "success": True,
        "message": f"Great job completing the exercise, {user['name']}! 🎉"
    })


# ==================== STATS ROUTES ====================

@app.route("/api/stats", methods=["GET"])
@token_required
def get_stats():
    """Get user's statistics."""
    user = request.current_user
    db = get_db()
    
    stats = db.get_user_stats(user["id"])
    
    # Get most common distortion
    distortion_counts = stats["distortion_counts"]
    most_common = None
    if distortion_counts:
        most_common = max(distortion_counts, key=distortion_counts.get)
    
    return jsonify({
        "total_sessions": stats["total_sessions"],
        "total_exercises": stats["total_exercises"],
        "current_streak": stats["current_streak"],
        "distortion_counts": distortion_counts,
        "most_common_distortion": most_common
    })


# ==================== RESOURCES ROUTE ====================

@app.route("/api/resources", methods=["GET"])
def get_resources():
    """Get crisis resources (public endpoint)."""
    return jsonify({
        "resources": get_crisis_resources(),
        "message": "You're not alone. Help is always available. 💙"
    })


# ==================== HELPER FUNCTIONS ====================

def is_natural_exit(message: str) -> bool:
    """Check if message indicates user wants to end conversation."""
    exit_phrases = [
        "thanks", "thank you", "bye", "goodbye", "see you",
        "i feel better", "that helps", "i'm good", "im good",
        "gotta go", "have to go", "talk later", "gtg"
    ]
    message_lower = message.lower().strip()
    return any(phrase in message_lower for phrase in exit_phrases)


def handle_natural_exit(session: dict, user: dict, db, session_id: str) -> dict:
    """Handle natural conversation exit."""
    import random

    endings = NATURAL_ENDINGS
    response = random.choice(endings).replace("{name}", user["name"])

    # Check if Beck protocol was completed
    beck_data = db.get_beck_session(session_id)
    if beck_data and beck_data.get("beck_state") == "COMPLETE":
        # Get improvement stats
        improvement = calculate_improvement(beck_data)
        if improvement:
            improvement_msg = "You made real progress today! "
            if improvement.get('belief_change', 0) >= 10:
                improvement_msg += f"Your belief shifted by {improvement['belief_change']}%. "
            if improvement.get('emotion_change', 0) >= 10:
                improvement_msg += f"Your emotion intensity dropped by {improvement['emotion_change']}%. "
            response = improvement_msg + "\n\n" + response

    # Update session
    db.update_session(session_id, completed=1)

    return {
        "response": response,
        "session_state": "COMPLETED",
        "natural_exit": True,
        "session_complete": True
    }


def extract_rating(message: str) -> int:
    """Extract a 0-100 rating from user message."""
    import re
    # Look for numbers
    numbers = re.findall(r'\d+', message)
    for num in numbers:
        n = int(num)
        if 0 <= n <= 100:
            return n
    return None


def calculate_improvement(beck_data: dict) -> dict:
    """Calculate belief and emotion improvement."""
    if not beck_data:
        return None

    result = {}
    if beck_data.get('initial_belief_rating') and beck_data.get('final_belief_rating'):
        result['belief_change'] = beck_data['initial_belief_rating'] - beck_data['final_belief_rating']
    if beck_data.get('initial_emotion_intensity') and beck_data.get('final_emotion_intensity'):
        result['emotion_change'] = beck_data['initial_emotion_intensity'] - beck_data['final_emotion_intensity']

    return result if result else None


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=True)
