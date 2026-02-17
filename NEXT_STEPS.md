# 🚀 Next Steps: Integrating Full Beck Protocol

## ✅ What's Been Created

You now have **7 new files** that implement the full Beck Cognitive Therapy protocol:

1. **bdi_scorer.py** - BDI-II scoring logic
2. **severity_router.py** - Treatment routing based on severity
3. **patient_tracker.py** - Multi-session patient tracking
4. **context_builder.py** - Therapeutic context for continuity
5. **beck_agents.py** - 13 new agents (BDI, bridge, BA, schema, summary, etc.)
6. **full_protocol.py** - 32-state protocol controller
7. **INTEGRATION_INSTRUCTIONS.md** - Step-by-step integration guide

Plus documentation:
- **FULL_BECK_PROTOCOL_SUMMARY.md** - Complete architecture overview
- **NEXT_STEPS.md** - This file

## 🎯 Your Task: Integration

Follow these steps **in order**:

### Step 1: Review the Architecture (5 minutes)

Read: **`FULL_BECK_PROTOCOL_SUMMARY.md`**
- Understand how the new system wraps the existing one
- See the 32-state flow diagram
- Review treatment pathways

### Step 2: Apply Integration (15-20 minutes)

Follow: **`INTEGRATION_INSTRUCTIONS.md`** exactly

You'll make **5 minimal changes** to `app.py`:
1. Add imports (3 lines)
2. Initialize patient tracking (1 line)
3. Add full protocol intercept (5 lines)
4. Hook post-session states (4 lines)
5. Add handler function (~300 lines)

**CRITICAL**: Copy-paste carefully. The integration instructions show EXACTLY where each block goes.

### Step 3: Test Existing System (5 minutes)

```bash
# Start the backend
python app.py

# Test existing session creation
curl -X POST http://localhost:7860/api/session/new \
  -H "Authorization: Bearer YOUR_TOKEN"

# Send a message
curl -X POST http://localhost:7860/api/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "session_id": "...",
    "message": "I am a complete failure",
    "conversation_history": []
  }'

# Should get VALIDATE state response ✓
```

### Step 4: Test New Full Protocol (10 minutes)

```bash
# Start a full protocol session
curl -X POST http://localhost:7860/api/session/start-full-protocol \
  -H "Authorization: Bearer YOUR_TOKEN"

# Should return BDI_ASSESSMENT state ✓

# Send first BDI response
curl -X POST http://localhost:7860/api/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "session_id": "...",
    "message": "1",
    "conversation_history": []
  }'

# Should ask next BDI item ✓
```

### Step 5: Test All Three Pathways

**Test Pathway 1: Severe Depression → Behavioral Activation**
- Complete BDI with high scores (total >= 29)
- Should route to "BA_MONITORING"
- Agent should ask about daily activities

**Test Pathway 2: Moderate Depression → Cognitive Restructuring**
- Complete BDI with moderate scores (14-28)
- Should route to "VALIDATE"
- Existing 20-state flow should run

**Test Pathway 3: Recovered → Relapse Prevention**
- Requires patient with 3+ previous sessions with BDI < 14
- Should route to "RELAPSE_PREVENTION"
- Agent should discuss maintaining gains

### Step 6: Deploy to HuggingFace Spaces

```bash
# Commit changes
git add backend/*.py
git commit -m "Add full Beck protocol (32 states, BDI-II, BA, schema work)"

# Push to HuggingFace
git push
```

---

## 🐛 Troubleshooting

### Error: "Module not found: patient_tracker"
**Fix**: Make sure all 7 new files are in `backend/` folder

### Error: "Column already exists"
**Fix**: Safe to ignore - `patient_tracker.py` uses ALTER TABLE ADD COLUMN which is idempotent

### Error: "GroqClient object has no attribute 'client'"
**Fix**: The `beck_agents.py` calls should use `groq_client.client` not `groq_client`. Check line 23 of `beck_agents.py`:
```python
response = groq_client.client.chat.completions.create(**kwargs)
```

### Error: "No such table: patient_profiles"
**Fix**: Call `init_patient_tracking()` in app.py startup (Step 2 of integration)

### Existing sessions break
**Fix**: The intercept should ONLY trigger if `full_protocol_state` exists in beck_session. Check Step 3 integration carefully.

### BDI assessment doesn't progress
**Check**: Are BDI responses being saved to database? Add debug logging:
```python
print(f"BDI responses: {bdi_responses}")
```

---

## 📊 Verification Checklist

Before deploying, verify:

- [ ] Existing `/api/session/new` + `/api/chat` still works
- [ ] BDI assessment completes (all 21 items)
- [ ] Severe depression routes to BA_MONITORING
- [ ] Moderate depression routes to VALIDATE
- [ ] After COMPLETE, transitions to SCHEMA_CHECK or DRDT
- [ ] Session closes with FEEDBACK → SESSION_DONE
- [ ] Patient profile tracks BDI scores
- [ ] Previous session data bridges correctly
- [ ] Homework assignment and review works
- [ ] No crashes or 500 errors

---

## 🎓 Understanding the Flow

### First Session (New Patient)

```
1. User calls: POST /api/session/start-full-protocol
2. Backend creates session, sets state = "BDI_ASSESSMENT"
3. Returns: "Let's start by checking in on how you've been feeling..."

4. User sends: "1" (BDI item 1 response)
5. Backend:
   - Saves response to bdi_responses[0] = 1
   - Calls bdi_assessment_agent for next item
   - Returns: "And how have you been feeling about the future?"

6. ... (repeat for 21 items)

7. When item 21 complete:
   - Calculates total score
   - Determines severity
   - Transitions to "SEVERITY_ROUTING"

8. If score >= 29:
   - Routes to "BA_MONITORING"
   - Agent asks about daily activities

9. Else if score 14-28:
   - Routes to "VALIDATE"
   - Existing cognitive flow runs

10. Cognitive flow completes at "COMPLETE"
    - Transitions to "SCHEMA_CHECK" (if session 4+) or "DRDT_OUTPUT"

11. Final states:
    - DRDT_OUTPUT → SESSION_SUMMARY → SESSION_FEEDBACK → SESSION_DONE
```

### Second Session (Returning Patient)

```
1. User calls: POST /api/session/start-full-protocol
2. Backend creates session, sets state = "BDI_ASSESSMENT"

3. BDI completes → "BRIDGE"
   - Agent: "Last time we worked on [previous thought]..."
   - Agent: "How have things been since we last talked?"

4. BRIDGE → "HOMEWORK_REVIEW"
   - Agent: "Did you try [action plan from last session]?"

5. HOMEWORK_REVIEW → "AGENDA_SETTING"
   - Agent: "What would be most helpful to focus on today?"

6. AGENDA_SETTING → "SEVERITY_ROUTING" → VALIDATE
   - Runs cognitive restructuring on today's thought

7. COMPLETE → "SCHEMA_CHECK"
   - Agent: "I've noticed a pattern... If [automatic thought] were true, what would it mean about you?"
   - Downward arrow to find core belief

8. SCHEMA_CHECK → DRDT → SUMMARY → FEEDBACK → DONE
```

---

## 🔧 Customization

### Changing Agent Prompts

Edit: `backend/beck_agents.py`

Example - Make BDI assessment less formal:
```python
# Line ~45 in bdi_assessment_agent()
system_prompt = f"""... YOUR CUSTOM PROMPT ..."""
```

### Changing Severity Cutoffs

Edit: `backend/severity_router.py`

Example - Lower threshold for behavioral activation:
```python
def route_by_severity(bdi_score, session_number, bdi_history):
    if bdi_score >= 25:  # Changed from 29
        return "BEHAVIOURAL_ACTIVATION"
```

### Adding New States

1. Add state to `full_protocol.py` (in appropriate list)
2. Add agent function to `beck_agents.py`
3. Add case to `handle_full_beck_protocol()` in `app.py`
4. Add transition rule to `get_next_state_full_protocol()`

---

## 📈 Monitoring

### Track Success Metrics

```sql
-- BDI improvement over time
SELECT user_id, AVG(bdi_score) as avg_bdi, COUNT(*) as sessions
FROM beck_sessions
WHERE bdi_score IS NOT NULL
GROUP BY user_id;

-- Common treatment pathways
SELECT protocol_branch, COUNT(*) as count
FROM beck_sessions
WHERE protocol_branch IS NOT NULL
GROUP BY protocol_branch;

-- Core beliefs identified
SELECT schema_identified, COUNT(*) as count
FROM beck_sessions
WHERE schema_identified IS NOT NULL
GROUP BY schema_identified;
```

---

## 🆘 Getting Help

1. **Integration Issues**: Re-read `INTEGRATION_INSTRUCTIONS.md`
2. **Architecture Questions**: See `FULL_BECK_PROTOCOL_SUMMARY.md`
3. **State Flow Confusion**: Check `full_protocol.py` state transitions
4. **Agent Behavior**: Review agent prompts in `beck_agents.py`

---

## 🎉 Success!

When you see:
- ✅ BDI assessment completing
- ✅ Severity-based routing working
- ✅ Session bridging from previous sessions
- ✅ Homework review functioning
- ✅ Post-session summary and feedback
- ✅ Patient profiles tracking BDI trajectory

**You have successfully integrated the full Beck protocol!**

Your CBT companion now implements evidence-based, multi-session therapy with:
- Standardized assessment (BDI-II)
- Severity-appropriate treatment
- Behavioral activation for severe depression
- Cognitive restructuring for moderate depression
- Schema work for deeper beliefs
- Relapse prevention for recovered patients
- Full session continuity

---

## 📚 Further Reading

- Beck, A. T. (1979). *Cognitive Therapy of Depression*
- Beck, J. S. (1995). *Cognitive Therapy: Basics and Beyond*
- Martell, C. R., et al. (2001). *Behavioral Activation for Depression*

---

**Ready to integrate?**

👉 Start with **`INTEGRATION_INSTRUCTIONS.md`**
