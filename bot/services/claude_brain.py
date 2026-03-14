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
from bot.validators import LongevityBrainOutput, NextInteraction

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """Ты — элитный советник по здоровью и долголетию в боте "10 000". Твоя цель — добавить пользователю 10 000 дней жизни через 10 000 микро-привычек.

# Стиль
- **Адаптивный:** используй выбранный пользователем стиль (Сбалансированный / Дисциплинированный / Участливый).
- **Без мета-разговоров:** НИКОГДА не упоминай "Фазы", "FSM" или "логику бота". Говори с живым человеком.
- **Прямой и проницательный:** не просто собирай данные — сразу интерпретируй их.
- **Язык:** всегда отвечай только на русском языке.

# Анализ корреляций (Phase 1.5 — "Момент озарения")
Когда ассессмент завершён, проведи корреляционный анализ:
- Свяжи самые низкие показатели с главной мотивацией пользователя.
- Пример: "Михаил, твои перепады сна (4–12 часов) вместе с уровнем стресса 8/10 — это главная причина 'тумана в голове'. Невозможно добиться ясности ума, пока кортизол скачет в 3 ночи."
- Будь конкретным. Называй пользователя по имени. Делай связи очевидными.

# Ежедневный цикл
- Утро: давай Nudge (конкретное действие на ≤15 минут), который устраняет главную "утечку" (самый низкий показатель).
- Вечер: задавай вопрос для рефлексии — что получилось, что нет.

# ОБЯЗАТЕЛЬНЫЙ ФОРМАТ ОТВЕТА (строгий JSON)
{
  "update_user_state": { "scores": {}, "insights": [] },
  "message_to_user": "Твой эмпатичный/прямой ответ здесь.",
  "next_interaction": {
    "type": "NUDGE" | "REFLECTION" | "ASSESSMENT",
    "content": "Текст следующего взаимодействия",
    "schedule_tag": "MORNING" | "EVENING" | "IMMEDIATE"
  }
}

Поля update_user_state и next_interaction могут быть null если не применимы.
Возвращай ТОЛЬКО валидный JSON — без markdown, без пояснений вне JSON."""

FALLBACK_OUTPUTS = [
    LongevityBrainOutput(
        message_to_user="Выпей стакан воды прямо сейчас. Обезвоживание на 2% снижает когнитивные функции на 20%.",
        next_interaction=NextInteraction(type="NUDGE", content="Выпей стакан воды", schedule_tag="MORNING"),
    ),
    LongevityBrainOutput(
        message_to_user="Сделай 3 глубоких вдоха через нос (4 сек) — задержи (4 сек) — выдох (6 сек). Это сбрасывает кортизол.",
        next_interaction=NextInteraction(type="NUDGE", content="Дыхательное упражнение 4-4-6", schedule_tag="MORNING"),
    ),
    LongevityBrainOutput(
        message_to_user="Встань и пройдись 5 минут. Каждый час сидения укорачивает жизнь на 22 минуты.",
        next_interaction=NextInteraction(type="NUDGE", content="5-минутная прогулка", schedule_tag="MORNING"),
    ),
]
_fallback_index = 0


def get_fallback_output() -> LongevityBrainOutput:
    global _fallback_index
    output = FALLBACK_OUTPUTS[_fallback_index % len(FALLBACK_OUTPUTS)]
    _fallback_index += 1
    return output


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def call_claude(
    user_state: Dict,
    sanitized_input: Optional[str],
    history: list,
    instruction: str,
) -> LongevityBrainOutput:
    """
    Core Claude call. Takes user state, history, and cleaned input.
    Returns structured LongevityBrainOutput.
    """
    context = f"""Состояние пользователя:
- Имя: {user_state.get('name', 'неизвестно')}
- Стиль коучинга: {user_state.get('coaching_style', 'balanced')}
- Мотивация: {user_state.get('motivation', 'не указана')}
- Показатели здоровья: {json.dumps(user_state.get('health_scores', {}), ensure_ascii=False)}
- Данные ассессмента: {json.dumps(user_state.get('assessment_data', {}), ensure_ascii=False)}
- Часовой пояс: {user_state.get('timezone_name', 'UTC')}

Инструкция: {instruction}
Ввод пользователя: {sanitized_input or '(нет ввода — проактивное уведомление)'}"""

    messages = history[-6:] + [{"role": "user", "content": context}]

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    raw = response.content[0].text.strip()
    try:
        data = json.loads(raw)
        return LongevityBrainOutput(**data)
    except Exception as e:
        logger.error(f"Failed to parse Claude output: {e}\nRaw: {raw}")
        raise


async def safe_claude_call(
    user_state: Dict,
    sanitized_input: Optional[str],
    history: list,
    instruction: str,
) -> LongevityBrainOutput:
    """Claude call with graceful fallback."""
    try:
        return await call_claude(user_state, sanitized_input, history, instruction)
    except Exception as e:
        logger.error(f"Claude brain failed: {e}. Using fallback.")
        return get_fallback_output()
