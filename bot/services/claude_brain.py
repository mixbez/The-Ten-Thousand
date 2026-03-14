"""
Claude Brain - core intelligence service.
Receives sanitized input + user state and returns structured responses.
"""
import json
import logging
from typing import Optional, Dict
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from bot.config import settings
from bot.validators import ClaireBrainOutput, ClaudeNudge

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """Ты — мозг бота "10 000", сфокусированного на маргинальных улучшениях здоровья.
Твоя цель: помочь пользователю добавить 10 000 дополнительных дней жизни через микро-привычки.

Тон: прямой, эмпатичный, профессиональный. Без воды. Не повторяй пользователю то, что он уже знает.
Фокус: вмешательства с высокой отдачей. Всегда предлагай наименьшее эффективное действие.
ВАЖНО: все поля "message" и "nudge_text" пиши ТОЛЬКО на русском языке.

You ALWAYS respond with valid JSON matching the ClaireBrainOutput schema:
{
  "message": "Your response to the user",
  "next_interaction": {
    "nudge_text": "The actual nudge/question",
    "category": "sleep|nutrition|movement|stress",
    "delivery_time": "MORNING|EVENING",
    "difficulty": "easy|medium|hard",
    "score_delta": 0
  },
  "updated_scores": {"sleep": 0-100, "nutrition": 0-100, ...},
  "phase_transition": null or phase number
}

Fields can be null if not applicable."""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def call_claude(
    user_state: Dict,
    sanitized_input: Optional[str],
    history: list,
    instruction: str,
) -> ClaireBrainOutput:
    """
    Core Claude call. Takes user state, history, and cleaned input.
    Returns structured output with message + next scheduled interaction.
    """
    context = f"""User State:
- GUID: {user_state.get('guid', 'unknown')}
- Phase: {user_state.get('phase', 0)}
- Personality: {user_state.get('personality', 'unknown')}
- Coaching style: {user_state.get('coaching_style', 'balanced')}
- Health scores: {json.dumps(user_state.get('health_scores', {}))}
- Timezone: {user_state.get('timezone_name', 'UTC')}

Instruction: {instruction}
User input: {sanitized_input or '(no input, proactive nudge)'}"""

    messages = history[-6:] + [{"role": "user", "content": context}]

    response = await client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    raw = response.content[0].text.strip()
    try:
        data = json.loads(raw)
        return ClaireBrainOutput(**data)
    except Exception as e:
        logger.error(f"Failed to parse Claude output: {e}\nRaw: {raw}")
        raise


async def safe_claude_call(
    user_state: Dict,
    sanitized_input: Optional[str],
    history: list,
    instruction: str,
) -> ClaireBrainOutput:
    """Claude call with graceful fallback to hardcoded tip."""
    from bot.services.groq_sanitizer import get_fallback_tip
    try:
        return await call_claude(user_state, sanitized_input, history, instruction)
    except Exception as e:
        logger.error(f"Claude brain failed: {e}. Using fallback tip.")
        tip = get_fallback_tip()
        return ClaireBrainOutput(
            message=tip,
            next_interaction=ClaudeNudge(
                nudge_text=tip,
                category="movement",
                delivery_time="MORNING",
                difficulty="easy",
                score_delta=0,
            ),
        )
