# Full Beck Protocol Integration Instructions

## ✅ SAFETY FIRST
- The existing 20-state cognitive restructuring flow (VALIDATE → COMPLETE) remains **UNTOUCHED**
- We are **WRAPPING** it with pre-session and post-session states
- All new code is in separate files - only 5 minimal changes to app.py

---

## Step 1: Add Imports (TOP of app.py, after existing imports)

Add these lines after the existing imports (around line 17):

```python
# === NEW IMPORTS FOR FULL BECK PROTOCOL ===
from patient_tracker import init_patient_tracking, get_patient_profile, update_patient_profile, add_bdi_score, get_previous_session
from full_protocol import (is_new_protocol_state, get_next_state_full_protocol,
                           get_post_complete_state, get_initial_state, is_session_complete)
from beck_agents import (bdi_assessment_agent, bridge_agent, homework_review_agent,
                         agenda_setting_agent, psychoeducation_agent, behavioural_activation_agent,
                         schema_agent, drdt_agent, summary_agent, feedback_agent,
                         relapse_prevention_agent)
from context_builder import build_patient_context, build_minimal_context
from bdi_scorer import score_bdi, get_next_item_index, is_bdi_complete
from severity_router import route_by_severity
import re
# === END NEW IMPORTS ===
```

---

## Step 2: Initialize Patient Tracking (app startup)

Add this line after `groq_client` initialization (around line 29):

```python
# Initialize patient tracking (adds new columns to beck_sessions table)
init_patient_tracking()
```

---

## Step 3: Add Full Protocol Intercept (INSIDE /api/chat function)

**Location**: Right AFTER getting the session (line 190), BEFORE crisis detection

Add this block:

```python
        # ========== FULL PROTOCOL INTERCEPT ==========
        # Check if session is using the full 32-state protocol
        beck_data = db.get_beck_session(session_id)

        if beck_data and beck_data.get('full_protocol_state'):
            full_state = beck_data['full_protocol_state']

            # If in a new protocol state, handle it with full protocol
            if is_new_protocol_state(full_state):
                return handle_full_beck_protocol(
                    full_state, user_message, session_id,
                    user["id"], user["name"], conversation_history, db
                )

        # ========== END FULL PROTOCOL INTERCEPT ==========
```

---

## Step 4: Hook Post-Session States (AFTER COMPLETE state)

**Location**: Find where `db.complete_beck_session(session_id)` is called (line 314)

**REPLACE** this block:

```python
                else:
                    # Protocol complete
                    db.complete_beck_session(session_id)
```

**WITH**:

```python
                else:
                    # Existing cognitive flow complete
                    db.complete_beck_session(session_id)

                    # === HOOK: Transition to post-session states ===
                    patient_profile = get_patient_profile(user["id"])
                    total_sessions = patient_profile.get('total_beck_sessions', 0)
                    bdi_score = beck_data.get('bdi_score')

                    post_state = get_post_complete_state(total_sessions, bdi_score)
                    db.update_beck_state(session_id, post_state, full_protocol_state=post_state)
```

---

## Step 5: Add Full Protocol Handler Function (END of app.py, before `if __name__ == "__main__"`)

Add this complete handler function:

```python
# ==================== FULL BECK PROTOCOL HANDLER ====================

def handle_full_beck_protocol(current_state: str, user_message: str, session_id: str,
                              user_id: str, user_name: str, conversation_history: list, db) -> dict:
    """
    Handle states from the full 32-state Beck protocol.

    This function handles:
    - Pre-session states (BDI, bridge, homework review, agenda, psychoeducation)
    - Behavioral activation states (for severe depression)
    - Post-session states (schema work, DRDT, summary, feedback)
    - Relapse prevention

    The existing 20-state cognitive flow (VALIDATE → COMPLETE) is NOT handled here.
    """

    # Get patient profile and session data
    patient_profile = get_patient_profile(user_id)
    beck_session = db.get_beck_session(session_id)
    previous_session = get_previous_session(user_id, session_id)

    # Build therapeutic context
    if patient_profile.get('total_beck_sessions', 0) > 0 and previous_session:
        context = build_patient_context(patient_profile, previous_session)
    else:
        context = build_minimal_context(
            patient_profile.get('total_beck_sessions', 0) + 1,
            beck_session.get('bdi_score'),
            beck_session.get('bdi_severity')
        )

    response_text = ""
    next_state = current_state
    metadata = {}

    # === ROUTING STATE (Logic only, no LLM) ===
    if current_state == "SEVERITY_ROUTING":
        bdi_score = beck_session.get('bdi_score', 15)
        bdi_history_raw = patient_profile.get('bdi_scores', [])

        if isinstance(bdi_history_raw, str):
            import json
            bdi_history_raw = json.loads(bdi_history_raw)

        bdi_history = [s.get('score') if isinstance(s, dict) else s for s in bdi_history_raw]

        route_result = route_by_severity(
            bdi_score,
            patient_profile.get('total_beck_sessions', 0) + 1,
            bdi_history
        )

        if route_result == "BEHAVIOURAL_ACTIVATION":
            next_state = "BA_MONITORING"
        elif route_result == "RELAPSE_PREVENTION":
            next_state = "RELAPSE_PREVENTION"
        else:
            # VALIDATE - hand off to existing cognitive flow
            next_state = "VALIDATE"
            db.update_beck_state(session_id, "VALIDATE", original_thought=user_message,
                               full_protocol_state="VALIDATE")
            # Let existing handler take over
            return jsonify({
                "response": "",
                "full_protocol_state": "VALIDATE",
                "beck_state": "VALIDATE",
                "auto_advance": True
            })

        # Update state and continue
        db.update_beck_state(session_id, next_state, full_protocol_state=next_state)

        # Recursively handle next state
        return handle_full_beck_protocol(
            next_state, user_message, session_id, user_id, user_name,
            conversation_history, db
        )

    # === BDI ASSESSMENT ===
    elif current_state == "BDI_ASSESSMENT":
        # Get current BDI progress
        bdi_responses_raw = beck_session.get('bdi_responses', '{}')
        if isinstance(bdi_responses_raw, str):
            import json
            bdi_responses = json.loads(bdi_responses_raw) if bdi_responses_raw != '{}' else {}
        else:
            bdi_responses = bdi_responses_raw or {}

        # Call BDI assessment agent
        response_text = bdi_assessment_agent(
            groq_client, conversation_history, bdi_responses, user_name, context
        )

        # Check for completion signal
        if "[BDI_COMPLETE:" in response_text:
            # Extract score from signal
            match = re.search(r'\[BDI_COMPLETE:(\d+)\]', response_text)
            if match:
                total_score = int(match.group(1))
                from bdi_scorer import get_severity
                severity = get_severity(total_score)

                # Save BDI results
                db.update_beck_state(session_id, "SEVERITY_ROUTING",
                                   bdi_score=total_score,
                                   bdi_severity=severity,
                                   bdi_responses=json.dumps(bdi_responses),
                                   bdi_completed_at=datetime.utcnow().isoformat(),
                                   full_protocol_state="SEVERITY_ROUTING")

                # Add to patient history
                add_bdi_score(user_id, total_score, severity, session_id)

                next_state = "SEVERITY_ROUTING"

                # Clean the signal from response
                response_text = re.sub(r'\[BDI_COMPLETE:\d+\]', '', response_text).strip()

        # Check for crisis signal
        elif "[CRISIS_FLAG]" in response_text:
            # Item 9 indicated suicidal thoughts
            # Trigger crisis response (existing crisis handler)
            from crisis_detector import get_crisis_response, get_crisis_resources
            crisis_response = get_crisis_response(user_name)

            return jsonify({
                "response": crisis_response,
                "is_crisis": True,
                "crisis_resources": get_crisis_resources(),
                "full_protocol_state": "CRISIS"
            })

        # Parse BDI response from user message
        else:
            # Extract score from user message (0-3)
            score_match = re.search(r'\b([0-3])\b', user_message)
            if score_match:
                score = int(score_match.group(1))
                next_item = get_next_item_index(bdi_responses)

                if next_item is not None:
                    bdi_responses[next_item] = score
                    db.update_beck_state(session_id, current_state,
                                       bdi_responses=json.dumps(bdi_responses),
                                       full_protocol_state=current_state)

    # === PRE-SESSION AGENTS ===
    elif current_state == "BRIDGE":
        response_text = bridge_agent(groq_client, user_message, conversation_history, user_name, context)
        if "[BRIDGE_COMPLETE]" in response_text:
            next_state = get_next_state_full_protocol(current_state, beck_session, patient_profile)
            db.update_beck_state(session_id, next_state, full_protocol_state=next_state)
            response_text = re.sub(r'\[BRIDGE_COMPLETE\]', '', response_text).strip()

    elif current_state == "HOMEWORK_REVIEW":
        response_text = homework_review_agent(groq_client, user_message, conversation_history, user_name, context)
        if "[HOMEWORK_REVIEW_COMPLETE]" in response_text:
            next_state = get_next_state_full_protocol(current_state, beck_session, patient_profile)
            db.update_beck_state(session_id, next_state, full_protocol_state=next_state,
                               homework_reviewed=1, homework_completion_notes=user_message)
            response_text = re.sub(r'\[HOMEWORK_REVIEW_COMPLETE\]', '', response_text).strip()

    elif current_state == "AGENDA_SETTING":
        response_text = agenda_setting_agent(groq_client, user_message, conversation_history, user_name, context)
        if "[AGENDA_SET:" in response_text:
            # Extract agenda
            match = re.search(r'\[AGENDA_SET:\s*([^\]]+)\]', response_text)
            agenda = match.group(1) if match else "Session focus"

            next_state = get_next_state_full_protocol(current_state, beck_session, patient_profile)
            db.update_beck_state(session_id, next_state, full_protocol_state=next_state,
                               agenda_items=agenda)
            response_text = re.sub(r'\[AGENDA_SET:[^\]]+\]', '', response_text).strip()

    elif current_state == "PSYCHOEDUCATION":
        response_text = psychoeducation_agent(groq_client, user_message, conversation_history, user_name, context)
        if "[PSYCHOEDUCATION_COMPLETE]" in response_text:
            next_state = get_next_state_full_protocol(current_state, beck_session, patient_profile)
            db.update_beck_state(session_id, next_state, full_protocol_state=next_state)
            response_text = re.sub(r'\[PSYCHOEDUCATION_COMPLETE\]', '', response_text).strip()

    # === BEHAVIORAL ACTIVATION ===
    elif current_state in ["BA_MONITORING", "BA_SCHEDULING", "BA_GRADED_TASK"]:
        ba_stage_map = {
            "BA_MONITORING": "monitoring",
            "BA_SCHEDULING": "scheduling",
            "BA_GRADED_TASK": "graded_task"
        }
        ba_stage = ba_stage_map[current_state]

        response_text = behavioural_activation_agent(
            groq_client, user_message, conversation_history, ba_stage, user_name, context
        )

        completion_signals = {
            "BA_MONITORING": "[BA_MONITORING_COMPLETE]",
            "BA_SCHEDULING": "[BA_SCHEDULING_COMPLETE]",
            "BA_GRADED_TASK": "[BA_GRADED_COMPLETE]"
        }

        if completion_signals[current_state] in response_text:
            next_state = get_next_state_full_protocol(current_state, beck_session, patient_profile)
            db.update_beck_state(session_id, next_state, full_protocol_state=next_state,
                               ba_stage=ba_stage, ba_activities=user_message)
            response_text = re.sub(r'\[BA_\w+_COMPLETE\]', '', response_text).strip()

    # === POST-SESSION AGENTS ===
    elif current_state == "SCHEMA_CHECK":
        response_text = schema_agent(groq_client, user_message, conversation_history, beck_session, user_name, context)

        if "[SCHEMA_IDENTIFIED:" in response_text:
            match = re.search(r'\[SCHEMA_IDENTIFIED:\s*([^\]]+)\]', response_text)
            schema = match.group(1) if match else "Core belief identified"

            # Add to patient profile
            core_beliefs = patient_profile.get('core_beliefs', [])
            if isinstance(core_beliefs, str):
                import json
                core_beliefs = json.loads(core_beliefs)
            if schema not in core_beliefs:
                core_beliefs.append(schema)
                update_patient_profile(user_id, core_beliefs=core_beliefs)

            next_state = "DRDT_OUTPUT"
            db.update_beck_state(session_id, next_state, full_protocol_state=next_state,
                               schema_identified=schema)
            response_text = re.sub(r'\[SCHEMA_IDENTIFIED:[^\]]+\]', '', response_text).strip()

        elif "[SCHEMA_SKIP]" in response_text:
            next_state = "DRDT_OUTPUT"
            db.update_beck_state(session_id, next_state, full_protocol_state=next_state)
            response_text = re.sub(r'\[SCHEMA_SKIP\]', '', response_text).strip()

    elif current_state == "DRDT_OUTPUT":
        response_text = drdt_agent(groq_client, beck_session, user_name)
        next_state = "SESSION_SUMMARY"
        db.update_beck_state(session_id, next_state, full_protocol_state=next_state,
                           drdt_output=response_text)
        response_text = re.sub(r'\[DRDT_COMPLETE\]', '', response_text).strip()

    elif current_state == "SESSION_SUMMARY":
        response_text = summary_agent(groq_client, user_message, conversation_history, user_name, context)
        if "[SUMMARY_COMPLETE]" in response_text:
            next_state = "SESSION_FEEDBACK"
            db.update_beck_state(session_id, next_state, full_protocol_state=next_state,
                               session_summary_text=user_message)
            response_text = re.sub(r'\[SUMMARY_COMPLETE\]', '', response_text).strip()

    elif current_state == "SESSION_FEEDBACK":
        response_text = feedback_agent(groq_client, user_message, conversation_history, user_name, context)
        if "[FEEDBACK_COMPLETE]" in response_text:
            next_state = "SESSION_DONE"
            db.update_beck_state(session_id, next_state, full_protocol_state=next_state,
                               patient_feedback=user_message, session_closed_at=datetime.utcnow().isoformat())

            # Increment session count
            from patient_tracker import increment_session_count
            increment_session_count(user_id)

            response_text = re.sub(r'\[FEEDBACK_COMPLETE\]', '', response_text).strip()

    # === RELAPSE PREVENTION ===
    elif current_state == "RELAPSE_PREVENTION":
        response_text = relapse_prevention_agent(groq_client, user_message, conversation_history, user_name, context)
        if "[RELAPSE_PLAN_COMPLETE]" in response_text:
            # Save relapse plan
            update_patient_profile(user_id, relapse_prevention_plan=user_message, in_relapse_prevention=1)

            next_state = "SESSION_SUMMARY"
            db.update_beck_state(session_id, next_state, full_protocol_state=next_state)
            response_text = re.sub(r'\[RELAPSE_PLAN_COMPLETE\]', '', response_text).strip()

    # === SESSION DONE ===
    elif current_state == "SESSION_DONE":
        response_text = f"Session complete! Take care, {user_name}. 💙"
        metadata["session_complete"] = True

    # Save messages to database
    db.add_message(session_id, user_id, "user", user_message)
    db.add_message(session_id, user_id, "assistant", response_text)

    return jsonify({
        "response": response_text,
        "full_protocol_state": next_state,
        "beck_state": beck_session.get('beck_state') if beck_session else None,
        "is_full_protocol": True,
        **metadata
    })


# ==================== NEW API ROUTES FOR FULL PROTOCOL ====================

@app.route("/api/patient/profile", methods=["GET"])
@token_required
def get_patient_profile_route():
    """Get patient profile with BDI trajectory and treatment phase."""
    user = request.current_user
    profile = get_patient_profile(user["id"])

    return jsonify({
        "profile": profile,
        "success": True
    })


@app.route("/api/patient/bdi-history", methods=["GET"])
@token_required
def get_bdi_history():
    """Get BDI score history for patient."""
    user = request.current_user
    profile = get_patient_profile(user["id"])

    bdi_scores = profile.get('bdi_scores', [])
    if isinstance(bdi_scores, str):
        import json
        bdi_scores = json.loads(bdi_scores)

    return jsonify({
        "bdi_history": bdi_scores,
        "current_phase": profile.get('current_treatment_phase'),
        "success": True
    })


@app.route("/api/session/start-full-protocol", methods=["POST"])
@token_required
def start_full_protocol_session():
    """
    Start a new session using the full 32-state Beck protocol.
    This is the entry point for new sessions that should use the extended protocol.
    """
    user = request.current_user
    db = get_db()

    # Create session
    session_id = db.create_session(user["id"])

    # Create Beck session with full protocol
    db.create_beck_session(session_id)

    # Set initial state
    initial_state = get_initial_state(0)  # Session 0 for new patients
    db.update_beck_state(session_id, initial_state, full_protocol_state=initial_state,
                       user_id_extended=user["id"])

    return jsonify({
        "session_id": session_id,
        "message": f"Hey {user['name']}! 👋 Let's start by checking in on how you've been feeling lately.",
        "full_protocol_state": initial_state,
        "is_full_protocol": True,
        "success": True
    })
```

---

## Step 6: Test the Integration

1. **Test existing system still works**:
   ```bash
   # Start session the old way
   POST /api/session/new
   POST /api/chat with a distorted thought

   # Should still use VALIDATE → COMPLETE flow
   ```

2. **Test new full protocol**:
   ```bash
   # Start session the new way
   POST /api/session/start-full-protocol

   # Should start with BDI_ASSESSMENT
   # Progress through full 32-state flow
   ```

---

## Verification Checklist

- [ ] Existing `/api/chat` still works for legacy sessions
- [ ] New `/api/session/start-full-protocol` creates sessions with BDI assessment
- [ ] BDI assessment completes and routes based on severity
- [ ] Severe depression (BDI >= 29) routes to behavioral activation
- [ ] Mild/moderate routes to existing VALIDATE flow
- [ ] After COMPLETE state, transitions to SCHEMA_CHECK or DRDT_OUTPUT
- [ ] Session closes with SUMMARY → FEEDBACK → SESSION_DONE
- [ ] Patient profile tracks BDI scores across sessions
- [ ] No errors in existing 20-state flow

---

## Rollback Plan

If anything breaks:

1. Comment out Step 3 (the full protocol intercept)
2. Comment out Step 4 (the post-session hook)
3. System reverts to original 20-state flow

All new code is in separate files - no existing code was modified except for these 5 integration points.
