"""
Health data parser — extracts structured metrics from free-form user text via Groq.
Does NOT use Claude (cost optimization).
"""
import json
import logging
from groq import AsyncGroq
from tenacity import retry, stop_after_attempt, wait_exponential
from bot.config import settings
from bot.validators import HealthParserOutput

logger = logging.getLogger(__name__)

client = AsyncGroq(api_key=settings.groq_api_key)

# Map Groq-extracted keys to assessment_data field names
METRIC_KEY_MAP = {
    "vo2_max": "vo2_max",
    "vo2": "vo2_max",
    "homa_ir": "homa_ir",
    "homa": "homa_ir",
    "apob": "apob",
    "hba1c": "hba1c",
    "a1c": "hba1c",
    "hrv": "hrv",
    "rmssd": "hrv",
    "cooper_distance_km": "cooper_test_km",
    "cooper": "cooper_test_km",
    "glucose_fasting": "glucose_fasting",
    "glucose": "glucose_fasting",
    "insulin_fasting": "insulin_fasting",
    "insulin": "insulin_fasting",
    "blood_pressure": "blood_pressure",
    "bp": "blood_pressure",
    "sleep_hours": "sleep_hours",
    "weight_kg": "weight_kg",
    "weight": "weight_kg",
}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def parse_health_data(user_text: str) -> HealthParserOutput:
    """Extract structured health metrics from free-form user text via Groq."""
    prompt = f"""Ты — парсер медицинских данных. Извлеки из текста пользователя числовые данные о здоровье.

Ищи эти метрики (только если упомянуты):
- vo2_max: число в мл/кг/мин
- homa_ir: число
- apob: число в мг/дл или ммоль/л
- hba1c: число в %
- hrv: число в мс
- glucose_fasting: число в ммоль/л или мг/дл
- insulin_fasting: число в мкМЕ/мл
- blood_pressure: строка типа "120/80"
- cooper_distance_km: число (дистанция за 12 минут в км)
- weight_kg: число в кг
- sleep_hours: число в часах

Если нашёл метрики — верни JSON:
{{"found": true, "metrics": {{"metric_name": value, "unit": "...", ...}}, "summary_line": "VO2 Max = 48 мл/кг/мин"}}

Если НЕ нашёл — верни JSON:
{{"found": false, "metrics": {{}}, "summary_line": ""}}

Верни ТОЛЬКО валидный JSON. Никаких комментариев.

Текст: "{user_text}"
"""

    response = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=200,
    )
    raw = response.choices[0].message.content.strip()
    data = json.loads(raw)
    return HealthParserOutput(**data)


async def safe_parse_health_data(user_text: str) -> HealthParserOutput:
    """Wrapper with graceful fallback."""
    try:
        return await parse_health_data(user_text)
    except Exception as e:
        logger.error(f"health_parser failed: {e}")
        return HealthParserOutput(found=False)


def merge_metrics_into_assessment(existing: dict, metrics: dict) -> dict:
    """Incrementally merge parsed metrics into assessment_data."""
    updated = dict(existing)
    for raw_key, value in metrics.items():
        canonical = METRIC_KEY_MAP.get(raw_key.lower(), raw_key.lower())
        updated[canonical] = value
    return updated
