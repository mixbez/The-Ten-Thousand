"""
Health data parser — classifies if text is health-related, then extracts key info.
Uses Groq to decide: is this health data? If yes, condense it.
"""
import json
import logging
from groq import AsyncGroq
from tenacity import retry, stop_after_attempt, wait_exponential
from bot.config import settings
from bot.validators import HealthParserOutput

logger = logging.getLogger(__name__)

client = AsyncGroq(api_key=settings.groq_api_key)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def parse_health_data(user_text: str) -> HealthParserOutput:
    """
    Classify if text contains health/medical data.
    If yes: condense to key info. If no: return found=false.
    """
    prompt = f"""Ты — классификатор медицинских данных.

Прочитай текст пользователя и ответь ТОЛЬКО JSON:
1. Это медицинские/здоровейские данные? (анализы, вес, сон, тесты, давление, упражнения, и т.д.)
2. Если ДА → верни condensed_text: сокращённая версия текста с только значимым (без лишних слов)
3. Если НЕТ → верни пусто

Примеры ДА:
- "мой вес 62 килограмма" → condensed: "вес: 62 кг"
- "сдал тест купера - пробежал 2.5 км за 12 минут" → condensed: "Cooper test: 2.5 км"
- "давление 120 на 80" → condensed: "давление: 120/80"
- "сегодня спал 7.5 часов" → condensed: "сон: 7.5 ч"

Примеры НЕТ:
- "сегодня неплохой день" → не медицинское
- "как дела?" → не медицинское
- "завтра выходной" → не медицинское

Текст пользователя: "{user_text}"

Верни JSON:
{{"found": true, "condensed": "вес: 62 кг"}}
или
{{"found": false, "condensed": ""}}

ТОЛЬКО JSON без комментариев.
"""

    response = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=150,
    )
    raw = response.choices[0].message.content.strip()
    data = json.loads(raw)
    
    if data.get("found"):
        return HealthParserOutput(
            found=True,
            metrics={"health_data": data.get("condensed", "")},
            summary_line=data.get("condensed", "")
        )
    else:
        return HealthParserOutput(found=False)


async def safe_parse_health_data(user_text: str) -> HealthParserOutput:
    """Wrapper with graceful fallback."""
    try:
        return await parse_health_data(user_text)
    except Exception as e:
        logger.error(f"health_parser failed: {e}")
        return HealthParserOutput(found=False)


def merge_metrics_into_assessment(existing: dict, metrics: dict) -> dict:
    """Store condensed health data in assessment_data under 'health_data_log'."""
    updated = dict(existing)
    if "health_data" in metrics:
        # Store condensed text in health_data_log list
        log = updated.get("health_data_log", [])
        if not isinstance(log, list):
            log = []
        log.append(metrics["health_data"])
        updated["health_data_log"] = log
    return updated
