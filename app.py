"""
CBT Companion - Backend API
Multi-user version with authentication and database
Hosted on HuggingFace Spaces
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from classifier import DistortionClassifier
from groq_client import GroqClient
from database import get_db
from auth import register_user, login_user, token_required
from crisis_detector import check_for_crisis, get_crisis_response, get_crisis_resources
from prompts import STAGE_GOALS, SUMMARIES, NATURAL_ENDINGS
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
classifier = DistortionClassifier()
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
    Main chat endpoint.
    Handles classification, stage tracking, crisis detection, and response generation.
    """
    try:
        user = request.current_user
        db = get_db()
        
        data = request.json
        user_message = data.get("message", "").strip()
        session_id = data.get("session_id")
        conversation_history = data.get("conversation_history", [])  # Get history from client

        if not user_message:
            return jsonify({"error": "Message is required"}), 400
        
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        
        # Get session
        session = db.get_session(session_id)
        if not session:
            return jsonify({"error": "Session not found"}), 404
        
        if session["user_id"] != user["id"]:
            return jsonify({"error": "Unauthorized"}), 403
        
        # ========== CRISIS DETECTION ==========
        is_crisis, trigger_word = check_for_crisis(user_message)
        
        if is_crisis:
            # Flag in database
            db.flag_crisis(
                user_id=user["id"],
                user_name=user["name"],
                user_email=user["email"],
                session_id=session_id,
                message_content=user_message,
                trigger_word=trigger_word
            )
            
            # Save user message
            db.add_message(session_id, user["id"], "user", user_message)
            
            # Get crisis response
            crisis_response = get_crisis_response(user["name"])
            db.add_message(session_id, user["id"], "assistant", crisis_response)
            
            return jsonify({
                "response": crisis_response,
                "is_crisis": True,
                "crisis_resources": get_crisis_resources(),
                "session_state": session["state"],
                "current_stage": session["current_stage"]
            })
        
        # ========== NATURAL EXIT CHECK ==========
        if is_natural_exit(user_message):
            response = handle_natural_exit(session, user, db, session_id)
            # Only save to DB if crisis - skip normal messages
            return jsonify(response)
        
        # ========== CLASSIFICATION ==========
        locked_group = session["locked_group"]
        current_stage = session["current_stage"]
        
        if session["state"] == "WAITING_FOR_PROBLEM" or locked_group == "G0":
            # Run classifier
            classification = classifier.classify(user_message)
            detected_group = classification["group"]
            confidence = classification["confidence"]
            
            if detected_group == "G0":
                # No distortion - listen supportively
                db.update_session(session_id, locked_group="G0")

                response_text = groq_client.generate_supportive_response(
                    user_message=user_message,
                    conversation_history=conversation_history[-6:],  # From client
                    user_name=user["name"]
                )

                # Don't save to DB - only save crisis messages

                return jsonify({
                    "response": response_text,
                    "detected_group": "G0",
                    "group_name": "No Distortion Detected",
                    "confidence": confidence,
                    "current_stage": None,
                    "total_stages": None,
                    "session_state": "LISTENING"
                })
            
            else:
                # Distortion detected - LOCK the group
                db.update_session(
                    session_id,
                    locked_group=detected_group,
                    stages_reached=1,
                    messages_in_current_stage=0
                )
                locked_group = detected_group
                current_stage = 1
        
        # ========== THERAPEUTIC RESPONSE ==========
        
        # Increment message counter
        messages_in_stage = db.increment_stage_messages(session_id)
        
        # Get stage info
        stage_info = STAGE_GOALS[locked_group][current_stage]
        
        # Generate response (use client-provided history, not DB)
        llm_response = groq_client.generate_therapeutic_response(
            user_message=user_message,
            conversation_history=conversation_history[-6:],  # Last 6 messages from client
            user_name=user["name"],
            user_context=user["context"],
            detected_group=locked_group,
            current_stage=current_stage,
            stage_goal=stage_info["goal"],
            stage_instruction=stage_info["instruction"]
        )
        
        response_text = llm_response["response"]
        should_advance = llm_response.get("advance_to_next_stage", False)
        
        # ========== STAGE ADVANCEMENT LOGIC ==========
        MIN_MESSAGES_PER_STAGE = 3
        MAX_MESSAGES_PER_STAGE = 8
        
        if messages_in_stage < MIN_MESSAGES_PER_STAGE:
            should_advance = False
        elif current_stage < 3 and messages_in_stage >= MAX_MESSAGES_PER_STAGE:
            should_advance = True
        # Stage 3: NO auto-advance
        
        # Handle advancement
        if should_advance and current_stage < 3:
            current_stage += 1
            db.update_session(session_id, stages_reached=current_stage, messages_in_current_stage=0)
        
        # Check if session complete
        session_complete = should_advance and current_stage >= 3
        
        if session_complete:
            db.update_session(session_id, completed=1)
            summary = SUMMARIES[locked_group]
            response_text = response_text + "\n\n---\n\n" + summary

        # Don't save to DB - only crisis messages are saved

        # Group display names
        group_names = {
            "G1": "Binary & Absolute Thinking",
            "G2": "Overgeneralized Beliefs",
            "G3": "Attention & Focus Bias",
            "G4": "Emotion-Driven Reasoning"
        }
        
        return jsonify({
            "response": response_text,
            "detected_group": locked_group,
            "group_name": group_names.get(locked_group, locked_group),
            "current_stage": current_stage,
            "total_stages": 3,
            "stage_name": STAGE_GOALS[locked_group][current_stage]["name"],
            "session_state": "COMPLETED" if session_complete else "IN_PROGRESS",
            "session_complete": session_complete
        })
        
    except Exception as e:
        print(f"Error in /api/chat: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


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
    
    locked_group = session.get("locked_group")
    current_stage = session.get("current_stage")
    
    # If exiting from Stage 3, add summary
    if current_stage == 3 and locked_group and locked_group != "G0":
        summary = SUMMARIES.get(locked_group, "")
        if summary:
            response = summary + "\n\n" + response
    
    # Update session and stats
    db.update_session(session_id, completed=1 if current_stage == 3 else 0)
    db.update_user_stats_on_session_end(user["id"], locked_group)
    
    return {
        "response": response,
        "session_state": "COMPLETED" if current_stage == 3 else "ENDED",
        "detected_group": locked_group,
        "current_stage": current_stage,
        "natural_exit": True,
        "session_complete": current_stage == 3,
        "suggest_exercise": current_stage == 3 and locked_group != "G0"
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=True)
