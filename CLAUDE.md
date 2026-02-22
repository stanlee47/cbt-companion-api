# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flask-based backend API for a CBT (Cognitive Behavioral Therapy) companion app. Deployed on HuggingFace Spaces via Docker. Uses Groq's LLaMA 3.3 70B model for LLM-powered therapeutic conversations and Turso (libSQL) for the database.

## Commands

```bash
# Run locally (dev)
python app.py                    # Starts on port 7860

# Run with gunicorn (production)
gunicorn -c gunicorn.conf.py app:app

# Run tests (no database needed)
python test_basic.py             # Pure logic tests (BDI scorer, severity router, etc.)
python test_beck_protocol.py     # Beck protocol state tests
python test_integration.py       # Integration tests

# Install dependencies
pip install -r requirements.txt
```

## Required Environment Variables

- `GROQ_API_KEY` - Groq API key for LLM calls
- `TURSO_DATABASE_URL` - Turso database URL
- `TURSO_AUTH_TOKEN` - Turso auth token
- `JWT_SECRET` - JWT signing key (has insecure default; must set in production)
- `ADMIN_EMAILS` - Comma-separated admin email addresses (optional)

## Architecture

### Beck Protocol State Machine (core logic)

The app implements a **32-state Beck CBT protocol** as a state machine, split into two layers:

1. **Original 20-state cognitive flow** (`prompts.py` states, handled in `app.py` main `chat()` route): `VALIDATE` → `RATE_BELIEF` → ... → `COMPLETE`. Uses a 3-agent system via `groq_client.py`.

2. **Extended full protocol** (`full_protocol.py` states, handled in `handle_full_beck_protocol()` in `app.py`):
   - Pre-session (6 states): BDI assessment, bridge, homework review, agenda setting, psychoeducation, severity routing
   - Post-session (5 states): schema check, DRDT output, summary, feedback, session done
   - Behavioral activation (3 states): for severe depression
   - Relapse prevention (1 state)

The extended protocol **wraps** the original cognitive flow. `SEVERITY_ROUTING` decides whether to enter the cognitive flow (`VALIDATE`), behavioral activation, or relapse prevention.

### 3-Agent LLM System (`groq_client.py`)

- **Agent 1 (Warm Questioner)**: Guides user through Beck's 6 questions
- **Agent 2 (Clinical Summarizer)**: Internal analysis, no user-facing output
- **Agent 3 (Treatment Agent)**: Delivers reframe, measures improvement, creates action plan

### Extended Protocol Agents (`beck_agents.py`)

Specialized agent functions for pre/post-session states (BDI assessment, bridge, homework review, etc.). Each returns text with completion signal tags like `[BDI_COMPLETE:score]`, `[BRIDGE_COMPLETE]` that the handler parses to advance state.

### Key Modules

- `app.py` - Flask routes and main state machine orchestration
- `database.py` - Turso DB wrapper class (`Database`), accessed via `get_db()` singleton
- `groq_client.py` - `GroqClient` class wrapping Groq SDK; contains the 3-agent system
- `auth.py` - JWT auth with `@token_required` decorator; sets `request.current_user`
- `crisis_detector.py` - Keyword-based crisis detection with resource responses
- `full_protocol.py` - State definitions and transition logic for extended protocol
- `severity_router.py` - Routes patients by BDI score to cognitive, behavioral, or relapse track
- `bdi_scorer.py` - BDI-II scoring and severity classification
- `patient_tracker.py` - Patient profile persistence (BDI history, core beliefs, session counts)
- `context_builder.py` - Builds therapeutic context strings for LLM prompts
- `wearable.py` - Wearable device data integration (Flask Blueprint)
- `admin.py` - Admin dashboard routes (Flask Blueprint)
- `ml_inference.py` - ML model for depression detection (lazy-loaded)

### State Advancement Pattern

State transitions in the full protocol follow a consistent pattern: agent functions embed completion signal tags (e.g., `[BRIDGE_COMPLETE]`) in their response text. The handler in `app.py` checks for these tags, strips them from the response, updates the DB state via `db.update_beck_state()`, and returns the cleaned response to the client.

### Database

Single `Database` class using `libsql_experimental` to connect to Turso. Tables are auto-created on init. Beck session data (state, BDI responses, scores, protocol fields) is stored as columns on the `beck_sessions` table with JSON-serialized fields for complex data.

## Deployment

Deployed to HuggingFace Spaces as a Docker container. Port 7860. Gunicorn with 2 sync workers, 180s timeout (for slow Groq API calls), worker recycling at 100 requests.
