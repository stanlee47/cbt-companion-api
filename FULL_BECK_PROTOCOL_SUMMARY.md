## 📚 Full Beck Protocol Implementation Summary

### Overview

The backend has been extended from a **20-state cognitive restructuring protocol** to a **full 32-state Beck Cognitive Therapy protocol** WITHOUT modifying any existing code. The extension **wraps around** the existing system.

---

## Architecture Changes

### Original System (PRESERVED)
```
User message → Crisis check → Distortion classification (G0-G4)
    ↓
If G1-G4: 20-state protocol
    VALIDATE → RATE_BELIEF → CAPTURE_EMOTION → RATE_EMOTION →
    Q1_EVIDENCE_FOR → Q1_EVIDENCE_AGAINST → Q2_ALTERNATIVE →
    Q3_WORST → Q3_BEST → Q3_REALISTIC → Q4_EFFECT → Q5_FRIEND → Q6_ACTION →
    SUMMARIZING →
    DELIVER_REFRAME → RATE_NEW_THOUGHT → RERATE_ORIGINAL →
    RERATE_EMOTION → ACTION_PLAN → COMPLETE
```

### New Extended System (WRAPS THE ORIGINAL)
```
SESSION START
    ↓
BDI-II ASSESSMENT (21 items, conversational)
    ↓
BRIDGE (if not first session - review previous session)
    ↓
HOMEWORK REVIEW (if homework was assigned)
    ↓
AGENDA SETTING (collaborative - what to focus on today)
    ↓
PSYCHOEDUCATION (first session only - teach cognitive model)
    ↓
SEVERITY ROUTING (based on BDI score):
    ├─ BDI >= 29 (Severe) → BEHAVIORAL ACTIVATION
    │   └─ BA_MONITORING → BA_SCHEDULING → BA_GRADED_TASK → Close session
    │
    ├─ BDI < 14 for 3+ sessions (Recovered) → RELAPSE PREVENTION → Close session
    │
    └─ BDI 14-28 (Mild-Moderate) → EXISTING 20-STATE COGNITIVE FLOW
            ↓
       [VALIDATE → ... → COMPLETE] ← PRESERVED EXACTLY AS-IS
            ↓
       SCHEMA CHECK (session 4+ only - downward arrow technique)
            ↓
       DRDT OUTPUT (format thought record)
            ↓
       SESSION SUMMARY (capsule + patient takeaways)
            ↓
       SESSION FEEDBACK (what worked, what didn't)
            ↓
       SESSION_DONE
```

---

## New Files Created (7 Total)

### 1. **bdi_scorer.py** (Pure Logic)
- Scores BDI-II responses (0-63 scale)
- Severity classification: minimal, mild, moderate, severe
- Crisis detection (Item 9 >= 2)
- **No LLM, no database** - just logic

### 2. **severity_router.py** (Routing Logic)
- Routes patient to appropriate treatment branch based on:
  - BDI score
  - Session number
  - BDI trajectory
- Returns: "BEHAVIOURAL_ACTIVATION", "RELAPSE_PREVENTION", or "VALIDATE"

### 3. **patient_tracker.py** (Database Extension)
- Adds `patient_profiles` table for cross-session tracking
- Adds columns to `beck_sessions` table via ALTER TABLE (safe, non-destructive)
- Tracks:
  - BDI scores over time
  - Core beliefs identified
  - Homework assignments
  - Treatment phase
  - Relapse prevention status

### 4. **context_builder.py** (Therapeutic Context)
- Builds context strings for agent prompts
- Includes:
  - Session history
  - BDI trajectory
  - Previous session summary
  - Identified core beliefs
  - Recurring distortion patterns
- Enables continuity across sessions

### 5. **beck_agents.py** (13 New Agents)
**Pre-session:**
- `bdi_assessment_agent` - Administers BDI-II conversationally
- `bridge_agent` - Bridges from previous session
- `homework_review_agent` - Reviews homework completion
- `agenda_setting_agent` - Collaborative agenda setting
- `psychoeducation_agent` - Teaches cognitive model (Socratic)

**Behavioral Activation:**
- `behavioural_activation_agent` - 3 stages: monitoring, scheduling, graded tasks

**Schema Work:**
- `schema_agent` - Downward arrow technique to identify core beliefs

**Post-session:**
- `drdt_agent` - Formats Daily Record of Dysfunctional Thoughts
- `summary_agent` - Session summary
- `feedback_agent` - Gets patient feedback

**Relapse Prevention:**
- `relapse_prevention_agent` - Builds maintenance plan

**Quality:**
- `supervisor_agent` - Optional quality check (uses cheaper 8b model)

### 6. **full_protocol.py** (State Controller)
- Manages 32-state protocol flow
- Routes between branches (cognitive, behavioral, relapse)
- Preserves existing 20-state flow as "cognitive branch"
- Handles state transitions

### 7. **INTEGRATION_INSTRUCTIONS.md** (This Guide)
- Step-by-step integration instructions
- Minimal changes to app.py (5 integration points)

---

## Changes to Existing Files

### app.py (5 Minimal Changes)

**Change 1: Imports** (3 lines added)
- Import new modules

**Change 2: Initialization** (1 line added)
- Call `init_patient_tracking()` on startup

**Change 3: Protocol Intercept** (5 lines added)
- Check if session uses full protocol
- Route to full protocol handler if needed

**Change 4: Post-Session Hook** (4 lines added)
- After COMPLETE state, transition to post-session states

**Change 5: Handler Function** (~300 lines added)
- `handle_full_beck_protocol()` function
- New API routes

### database.py (NO CHANGES)
- `patient_tracker.py` uses ALTER TABLE to add columns
- No modifications to existing schema or functions

### groq_client.py (NO CHANGES)
- Existing 3 agents remain untouched
- New agents in `beck_agents.py` import and use the existing Groq client

### prompts.py (NO CHANGES)
- Existing 20-state definitions preserved
- New states defined in `full_protocol.py`

---

## Database Changes

### New Table: `patient_profiles`
```sql
CREATE TABLE patient_profiles (
    user_id TEXT PRIMARY KEY,
    total_beck_sessions INTEGER DEFAULT 0,
    bdi_scores TEXT DEFAULT '[]',  -- JSON array
    core_beliefs TEXT DEFAULT '[]',
    intermediate_beliefs TEXT DEFAULT '[]',
    recurring_distortions TEXT DEFAULT '{}',
    current_treatment_phase TEXT,
    homework_pending TEXT,
    homework_history TEXT DEFAULT '[]',
    relapse_prevention_plan TEXT,
    ...
)
```

### New Columns in `beck_sessions` (via ALTER TABLE)
- `user_id_extended` - Denormalized user ID
- `session_number` - Session count for this patient
- `previous_session_id` - Link to previous session
- `bdi_responses`, `bdi_score`, `bdi_severity` - BDI data
- `agenda_items` - Session focus
- `homework_reviewed`, `homework_completion_notes`
- `session_summary_text`, `patient_feedback`
- `drdt_output` - Formatted thought record
- `schema_identified` - Core belief found
- `ba_stage`, `ba_activities` - Behavioral activation data
- `full_protocol_state` - Current state in 32-state protocol
- `protocol_branch` - cognitive/behavioral/relapse

---

## API Changes

### New Routes

**`POST /api/session/start-full-protocol`**
- Starts a new session with full 32-state protocol
- Returns session_id and initial BDI prompt
- Use this instead of `/api/session/new` for full protocol

**`GET /api/patient/profile`**
- Returns patient profile with:
  - Total sessions
  - BDI trajectory
  - Treatment phase
  - Core beliefs
  - Homework status

**`GET /api/patient/bdi-history`**
- Returns BDI score history (all sessions)
- Includes severity labels

### Existing Routes (PRESERVED)

**`POST /api/session/new`** - Still works for legacy 20-state flow
**`POST /api/chat`** - Enhanced to handle both old and new protocol

---

## Usage Patterns

### Starting a Full Protocol Session

```javascript
// New way - full 32-state protocol
POST /api/session/start-full-protocol
{
  // No body needed
}

Response:
{
  "session_id": "uuid",
  "message": "Hey Alice! 👋 Let's start by checking in...",
  "full_protocol_state": "BDI_ASSESSMENT",
  "is_full_protocol": true
}

// Then use /api/chat as normal
POST /api/chat
{
  "session_id": "uuid",
  "message": "1",  // BDI response
  "conversation_history": [...]
}
```

### Starting a Legacy Session (20-state only)

```javascript
// Old way - still works
POST /api/session/new
{
  "mood": 5  // optional
}

// Uses existing VALIDATE → COMPLETE flow
```

---

## Treatment Pathways

### Pathway 1: Severe Depression (BDI >= 29)
```
BDI (score: 35) → SEVERITY_ROUTING → BA_MONITORING
    ↓
"Walk me through a typical day..."
    ↓
BA_SCHEDULING → "Let's schedule one small activity"
    ↓
BA_GRADED_TASK → "Build up in small steps"
    ↓
DRDT → SUMMARY → FEEDBACK → DONE
```
**Rationale**: Too depressed for cognitive work. Activity scheduling comes first (Beck et al., 1979).

### Pathway 2: Mild-Moderate Depression (BDI 14-28)
```
BDI (score: 22) → SEVERITY_ROUTING → VALIDATE (existing flow)
    ↓
[20-state cognitive restructuring]
    ↓
COMPLETE → SCHEMA_CHECK (if session 4+) → DRDT → SUMMARY → FEEDBACK → DONE
```
**Rationale**: Ready for cognitive restructuring using existing protocol.

### Pathway 3: Recovered (BDI < 14 for 3+ sessions)
```
BDI (score: 10) → SEVERITY_ROUTING → RELAPSE_PREVENTION
    ↓
"What situations might bring old thoughts back?"
    ↓
Build coping plan → SUMMARY → FEEDBACK → DONE
```
**Rationale**: Focus on maintaining gains and preventing relapse.

---

## Key Features

### ✅ Backwards Compatible
- Existing sessions continue to work
- Legacy 20-state flow preserved exactly
- No breaking changes

### ✅ Severity-Appropriate Treatment
- Behavioral activation for severe cases
- Cognitive work for moderate cases
- Relapse prevention for recovered patients

### ✅ Multi-Session Continuity
- BDI trajectory tracking
- Previous session bridging
- Homework assignment and review
- Core belief accumulation

### ✅ Evidence-Based
- BDI-II assessment (Beck et al., 1996)
- Behavioral activation (Martell et al., 2001)
- Cognitive restructuring (Beck, 1979)
- Downward arrow for schema work (Beck, 1995)
- Relapse prevention (Teasdale et al., 2000)

### ✅ Warm & Collaborative
- All agents maintain the warm "Aria" personality
- Socratic questioning, not lecturing
- Collaborative agenda setting
- Patient feedback encouraged

---

## Testing

### Test Script

```python
# Test 1: Full protocol with severe depression
session = start_full_protocol_session()
# Complete BDI with high scores (total >= 29)
# Should route to BA_MONITORING

# Test 2: Full protocol with moderate depression
session = start_full_protocol_session()
# Complete BDI with moderate scores (14-28)
# Should route to VALIDATE (existing flow)

# Test 3: Legacy session
session = create_session_old_way()
# Should use existing VALIDATE → COMPLETE flow

# Test 4: Multi-session patient
profile = get_patient_profile(user_id)
# Check BDI trajectory, core beliefs, homework
```

---

## Performance Considerations

### LLM Calls per Session

**Behavioral Activation Session** (~10-12 calls):
1. BDI assessment (3-5 calls - conversational)
2. Bridge (1-2 calls if returning patient)
3. Agenda (1-2 calls)
4. BA Monitoring (2 calls)
5. BA Scheduling (2 calls)
6. DRDT (1 call)
7. Summary (1 call)
8. Feedback (1 call)

**Cognitive Restructuring Session** (~25-30 calls):
- Pre-session: 5-8 calls
- Existing flow: 13 calls (Agent 1: 12, Agent 2: 1)
- Existing Agent 3: 5 calls
- Post-session: 4-5 calls

### Cost Optimization
- Supervisor agent uses cheaper `llama-3.1-8b-instant` (optional quality check)
- BDI scoring uses pure logic (no LLM)
- Routing uses pure logic (no LLM)
- Can cache patient context between calls

---

## Next Steps

1. **Apply Integration** - Follow `INTEGRATION_INSTRUCTIONS.md`
2. **Test Locally** - Verify existing flow still works
3. **Test New Protocol** - Try all 3 pathways (severe, moderate, recovered)
4. **Deploy** - Push to HuggingFace Spaces
5. **Monitor** - Watch for errors in new states
6. **Iterate** - Tune agent prompts based on real usage

---

## Support

- **Integration Issues**: Check `INTEGRATION_INSTRUCTIONS.md`
- **Agent Behavior**: Tune prompts in `beck_agents.py`
- **Routing Logic**: Modify `severity_router.py`
- **State Flow**: Adjust `full_protocol.py`

All new code is modular and isolated - easy to modify without breaking existing system.

---

## Credits

Based on:
- Beck, A. T. (1979). *Cognitive Therapy of Depression*
- Beck, J. S. (1995). *Cognitive Therapy: Basics and Beyond*
- Beck, A. T., et al. (1996). *Beck Depression Inventory-II*
- Martell, C. R., et al. (2001). *Behavioral Activation for Depression*

Implementation follows evidence-based CBT protocols while maintaining the warm, supportive "Aria" personality from the original system.
