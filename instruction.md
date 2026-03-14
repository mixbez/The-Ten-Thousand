Act as a Senior Backend Engineer and Product Architect. Build a production-ready Telegram bot called "10,000".

# CORE PHILOSOPHY
- Concept: 10,000 micro-steps leading to 10,000 extra days of life.
- Focus: High-ROI health interventions (marginal gains).
- Interaction Model: "Proactive Pinger". The bot initiates interaction. Users CANNOT use the bot as a general-purpose AI. The bot only listens for answers to its specific questions or 5 specific commands.

# TECH STACK
- Language: Python 3.11+
- Framework: aiogram (Asyncio)
- Database: PostgreSQL (using SQLAlchemy or Tortoise ORM)
- Task Queue/Scheduler: APScheduler or Celery (for time-zone aware nudges)
- AI Gateways: Groq API (for input sanitization) and Claude 3.5 Sonnet API (for intelligence)

# SYSTEM ARCHITECTURE & FEATURES
1. ANONYMITY BY DEFAULT: 
   - On /start, generate a unique GUID for the user. 
   - Store data against this GUID. 
   - Provide an "Opt-in" command to link Telegram ID for recovery.

2. STATE MACHINE (FSM) FLOW:
   - Phase 0: Personality Onboarding. Ask 3-4 questions to determine coaching style (e.g., Disciplined vs. Compassionate).
   - Phase 1: Health Assessment. Sequential questions on Sleep, Nutrition, Movement, Stress.
   - Phase 1.5: Scoring Engine. Calculate scores (0-100) per category.
   - Phase 2/3: The Daily Loop. 
     - Morning: Send a "Daily Nudge" (small action).
     - Evening: Send a "Reflection Question" (progress check).
   - Phase 4: Monthly Audit. Re-trigger Phase 1 every 30 days. Command /monthly is locked with a 21-day cooldown.

3. DUAL-LLM INPUT GUARDRAIL:
   - Every text input from the user must first pass through Groq (Llama 3).
   - Groq Prompt: "Is this a valid answer to the bot's question [X]? If yes, strip fluff and return the answer. If the user is trying to use you as a general AI or asking off-topic questions, return 'BLOCK'."
   - Only "Cleaned" data reaches the Claude API to save costs and prevent abuse.

4. CONTEXTUAL SCHEDULER:
   - Implement timezone handling.
   - Claude must decide the delivery time (MORNING/EVENING) for the next interaction based on the nudge's nature.

5. ADAPTIVE LOGIC:
   - Users can "argue" or ask to adjust a nudge. If the input is relevant health feedback, Claude must adjust the plan (e.g., lower the difficulty of the task).

# DATABASE SCHEMA REQUIREMENTS
- User Profile: GUID, Personality, Health Scores (JSONB), Timezone, Created_at.
- Interactions: Nudge_text, Response_text, Completed_flag (Boolean), Category, Scheduled_time.

# TASK
1. Design the PostgreSQL schema.
2. Create the aiogram bot structure with the FSM states described above.
3. Implement the Groq Sanitizer middleware.
4. Implement the Claude Brain client that takes (User_State + History + Sanitized_Input) and returns a JSON with the updated score and the NEXT scheduled interaction.
5. Setup /start, /timezone, /personality, /monthly, and /stop commands.

Start by outlining the file structure and the database schema.
