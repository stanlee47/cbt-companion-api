"""
Therapeutic Context Builder
Builds context strings to inject into agent system prompts for continuity
"""

import json


def build_patient_context(patient_profile: dict, previous_session: dict = None) -> str:
    """
    Build therapeutic context from patient history.

    Args:
        patient_profile: Patient profile dict from patient_tracker
        previous_session: Previous beck_session dict (optional)

    Returns:
        Formatted context string for agent prompts
    """
    ctx_parts = []

    ctx_parts.append("=== THERAPEUTIC CONTEXT ===")

    # Session history
    total_sessions = patient_profile.get('total_beck_sessions', 0)
    ctx_parts.append(f"Beck Protocol Sessions Completed: {total_sessions}")

    if total_sessions == 0:
        ctx_parts.append("This is the patient's FIRST Beck protocol session.")

    # Treatment phase
    phase = patient_profile.get('current_treatment_phase', 'assessment')
    phase_labels = {
        'assessment': 'Initial Assessment',
        'behavioral_activation': 'Behavioral Activation (Severe Depression)',
        'cognitive_restructuring': 'Cognitive Restructuring',
        'schema_work': 'Cognitive Restructuring + Schema Exploration',
        'relapse_prevention': 'Relapse Prevention & Maintenance'
    }
    ctx_parts.append(f"Current Phase: {phase_labels.get(phase, phase)}")

    # BDI trajectory
    bdi_scores = patient_profile.get('bdi_scores', [])
    if isinstance(bdi_scores, str):
        try:
            bdi_scores = json.loads(bdi_scores)
        except:
            bdi_scores = []

    if bdi_scores and len(bdi_scores) > 0:
        recent_scores = bdi_scores[-5:]  # Last 5 sessions
        score_str = " → ".join([str(s.get('score', s) if isinstance(s, dict) else s) for s in recent_scores])
        ctx_parts.append(f"BDI Trajectory (last {len(recent_scores)} sessions): {score_str}")

        if len(recent_scores) >= 2:
            # Calculate trend
            try:
                latest = recent_scores[-1].get('score') if isinstance(recent_scores[-1], dict) else recent_scores[-1]
                previous = recent_scores[-2].get('score') if isinstance(recent_scores[-2], dict) else recent_scores[-2]
                change = latest - previous
                if change < -3:
                    ctx_parts.append("  → Improving trend ✓")
                elif change > 3:
                    ctx_parts.append("  → Worsening trend - needs attention")
                else:
                    ctx_parts.append("  → Stable")
            except:
                pass

    # Core beliefs identified
    core_beliefs = patient_profile.get('core_beliefs', [])
    if isinstance(core_beliefs, str):
        try:
            core_beliefs = json.loads(core_beliefs)
        except:
            core_beliefs = []

    if core_beliefs:
        ctx_parts.append(f"Core Beliefs Identified: {', '.join(core_beliefs)}")

    # Intermediate beliefs
    intermediate_beliefs = patient_profile.get('intermediate_beliefs', [])
    if isinstance(intermediate_beliefs, str):
        try:
            intermediate_beliefs = json.loads(intermediate_beliefs)
        except:
            intermediate_beliefs = []

    if intermediate_beliefs:
        ctx_parts.append(f"Intermediate Beliefs: {', '.join(intermediate_beliefs[:3])}")

    # Recurring distortion patterns
    distortions = patient_profile.get('recurring_distortions', {})
    if isinstance(distortions, str):
        try:
            distortions = json.loads(distortions)
        except:
            distortions = {}

    if distortions:
        sorted_distortions = sorted(distortions.items(), key=lambda x: x[1], reverse=True)
        if sorted_distortions:
            top_distortion = sorted_distortions[0]
            distortion_labels = {
                'G1': 'All-or-nothing thinking',
                'G2': 'Overgeneralization',
                'G3': 'Mental filter',
                'G4': 'Emotional reasoning'
            }
            ctx_parts.append(f"Most Common Pattern: {distortion_labels.get(top_distortion[0], top_distortion[0])} ({top_distortion[1]}x)")

    # Homework status
    homework = patient_profile.get('homework_pending')
    if homework and homework != 'null':
        try:
            hw = json.loads(homework) if isinstance(homework, str) else homework
            ctx_parts.append(f"Pending Homework: {hw.get('description', 'assigned')}")
        except:
            pass

    # Previous session summary
    if previous_session:
        ctx_parts.append("\n--- PREVIOUS SESSION ---")

        # What they worked on
        if previous_session.get('original_thought'):
            ctx_parts.append(f"Worked on: \"{previous_session['original_thought'][:100]}...\"")

        # Reframe
        if previous_session.get('adaptive_thought'):
            ctx_parts.append(f"Reframe: \"{previous_session['adaptive_thought'][:100]}...\"")

        # Action plan
        if previous_session.get('action_plan'):
            ctx_parts.append(f"Action Plan: {previous_session['action_plan'][:100]}")

        # Improvement
        if previous_session.get('belief_improvement'):
            ctx_parts.append(f"Belief Improvement: {previous_session['belief_improvement']}%")

        # Session summary
        if previous_session.get('session_summary_text'):
            ctx_parts.append(f"Summary: {previous_session['session_summary_text'][:150]}...")

    ctx_parts.append("=== END CONTEXT ===\n")

    return "\n".join(ctx_parts)


def build_minimal_context(session_number: int, bdi_score: int = None, severity: str = None) -> str:
    """Build minimal context for early sessions."""
    ctx = "=== THERAPEUTIC CONTEXT ===\n"
    ctx += f"Session Number: {session_number}\n"

    if bdi_score is not None:
        ctx += f"BDI-II Score: {bdi_score} ({severity})\n"

    if session_number == 1:
        ctx += "This is the patient's FIRST Beck protocol session.\n"

    ctx += "=== END CONTEXT ===\n"
    return ctx


# Test if run directly
if __name__ == "__main__":
    print("Testing context builder:\n")

    # Mock patient profile
    mock_profile = {
        'total_beck_sessions': 5,
        'current_treatment_phase': 'cognitive_restructuring',
        'bdi_scores': [
            {'score': 35, 'severity': 'severe'},
            {'score': 28, 'severity': 'moderate'},
            {'score': 22, 'severity': 'moderate'},
            {'score': 18, 'severity': 'mild'},
            {'score': 15, 'severity': 'mild'}
        ],
        'core_beliefs': ['I am incompetent', 'I am unlovable'],
        'recurring_distortions': {'G1': 8, 'G2': 5, 'G4': 3}
    }

    mock_previous = {
        'original_thought': 'I am a complete failure at my job',
        'adaptive_thought': 'I struggle with some tasks but I am learning and improving',
        'action_plan': 'Ask for feedback from manager this week',
        'belief_improvement': 25
    }

    context = build_patient_context(mock_profile, mock_previous)
    print(context)
