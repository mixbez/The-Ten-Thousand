# Project "10,000" - Technical Manifesto & Guidelines

## 1. Vision & Persona
- **Goal:** Drive longevity through 10,000 micro-habits (Marginal Gains).
- **Core Strategy:** High-ROI health interventions. Minimum effort, maximum life extension.
- **Tone:** Direct, empathetic, and professional. Avoid fluff. Do not repeat known facts about the user back to them.

## 2. Interaction Architecture: "The Proactive Pinger"
- **Strict Initiation:** The bot is the primary initiator.
- **Input Filtering (Dual-LLM):** 1. **Groq (Sanitizer):** Every user text input must be validated against the current bot question. Strip off-topic chatter. If malicious or irrelevant, return `BLOCK`.
    2. **Claude (Brain):** Receives only "Sanitized" text. Responsible for logic, scoring, and planning.
- **State Machine (FSM):** - Phase 0: Personality (3-4 Qs)
    - Phase 1: Health Base Assessment (Score calculation)
    - Phase 2/3: Daily Loop (Morning Nudge / Evening Reflection)
    - Phase 4: Monthly Audit (/monthly command with 21-day cooldown)

## 3. Data Integrity & Security
- **Anonymity:** Primary Key is a `uuid4` GUID. Telegram IDs are optional and stored via explicit opt-in.
- **Persistence:** Use PostgreSQL with `JSONB` for `health_scores` to ensure schema flexibility.
- **Timezones:** Store all timestamps in `UTC`. Schedule nudges based on user's local offset (Morning: ~08:00, Evening: ~20:00).
- **Safety:** Use `Pydantic` for validating all AI outputs before processing.

## 4. Testing & Regression Standards (MANDATORY)
Every feature must adhere to the following testing tiers:

### Tier 1: Unit Tests (Zero-LLM)
- Mandatory for `scoring_logic.py`, `validators.py`, and `scheduler_math.py`.
- 100% coverage for health score calculation edge cases.

### Tier 2: Integration Tests
- Verify FSM state transitions (e.g., cannot get a Daily Nudge before Assessment).
- Mock database calls using `pytest-mock`.
- Ensure timezone scheduling logic works for both positive and negative offsets.

### Tier 3: LLM Evals (Regression Protection)
- **Golden Dataset:** Maintain a set of `Input -> Expected JSON` pairs.
- **Sanitizer Hardening:** Test the Groq filter with 50+ jailbreak/off-topic prompts. Must maintain 100% `BLOCK` rate for malicious inputs.
- **Versioning:** No prompt changes are allowed without a successful run of the `Golden Dataset` evaluation.

## 5. Development Rules for Claude Code
- **No Direct SQL:** Use SQLAlchemy and `alembic` for all migrations.
- **Error Handling:** Implement exponential backoff for all API calls (Anthropic, Groq, Telegram). 
- **Graceful Failures:** If an LLM fails, the bot must fallback to a hardcoded "safe" health tip from a local cache rather than crashing.
- **Modularization:** Separate handlers (Telegram), services (AI logic), and data (DB models).

## 6. Anti-Abuse Logic
- Users cannot use the bot as a general chat AI. 
- Implement rate-limiting (e.g., max 5 messages per 10 minutes per GUID).
- After 3 `BLOCK` responses from the Sanitizer, the bot must send a "Usage Policy" reminder and temporarily pause the dialogue.
