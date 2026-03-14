"""
Groq-based input sanitizer middleware.
Every user text input passes through this before reaching Claude.
"""
import logging
from groq import AsyncGroq
from tenacity import retry, stop_after_attempt, wait_exponential
from bot.config import settings
from bot.validators import SanitizerOutput

logger = logging.getLogger(__name__)

FALLBACK_TIPS = [
    "Выпей стакан воды прямо сейчас.",
    "Сделай 3 глубоких вдоха.",
    "Встань и потянись в течение 60 секунд.",
    "Выйди на свежий воздух.",
    "Запиши одну вещь, за которую ты благодарен.",
]

_fallback_index = 0

client = AsyncGroq(api_key=settings.groq_api_key)


def get_fallback_tip() -> str:
    global _fallback_index
    tip = FALLBACK_TIPS[_fallback_index % len(FALLBACK_TIPS)]
    _fallback_index += 1
    return tip


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def sanitize_input(user_text: str, current_question: str) -> SanitizerOutput:
    """
    Validate user input against the current bot question.
    Returns PASS with cleaned text or BLOCK if irrelevant/malicious.
    """
    prompt = f"""You are a strict input validator for a health coaching bot.

Current bot question: "{current_question}"
User response: "{user_text}"

Rules:
1. If the response is a valid answer to the question, return JSON: {{"result": "PASS", "cleaned_text": "<stripped answer>"}}
2. If the user is trying to use you as a general AI, asking off-topic questions, or being malicious, return JSON: {{"result": "BLOCK", "reason": "<brief reason>"}}
3. Be strict. Only allow direct answers to the question.

Return ONLY valid JSON, no markdown."""

    try:
        response = await client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=150,
        )
        raw = response.choices[0].message.content.strip()
        import json
        data = json.loads(raw)
        return SanitizerOutput(**data)
    except Exception as e:
        logger.error(f"Groq sanitizer error: {e}")
        raise


async def safe_sanitize(user_text: str, current_question: str) -> SanitizerOutput:
    """Wrapper with graceful fallback."""
    try:
        return await sanitize_input(user_text, current_question)
    except Exception as e:
        logger.error(f"Groq sanitizer failed after retries: {e}. Allowing input through.")
        return SanitizerOutput(result="PASS", cleaned_text=user_text)
