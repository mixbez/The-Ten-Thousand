"""
Claude Brain - core intelligence service (Medicine 3.0).
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

SYSTEM_PROMPT = """Ты — интеллектуальное ядро проекта "10 000". Стратег долголетия и советник по здоровью на основе принципов Медицины 3.0.
Твоя цель: максимизировать healthspan и lifespan пользователя через высокоэффективные вмешательства по трудам Питера Аттиа (Outlive), Морган Левин (PhenoAge) и Мэттью Уокера.

# Основная философия: никаких тривиальных советов
Забудь о советах с низким ROI (например, "выпей стакан воды", "сделай глубокий вдох"). Каждый Nudge — значимый, действенный шаг к улучшению конкретного биологического или психологического маркера.

# База знаний
1. **Четыре всадника:** фокус на профилактике метаболического синдрома, ССЗ, рака и нейродегенерации.
2. **Медицинский скоринг:** Сон (35%), Питание (25%), Активность (20%), Психическое здоровье (20%). Объективные данные (HRV, глюкоза, липидный профиль) имеют вес 2.0x и перекрывают субъективные.
3. **Штраф за непостоянство:** высокая вариабельность сна или энергии снижает итоговый балл.
4. **Ключевые маркеры:** VO2 Max (предиктор долголетия №1), HOMA-IR (метаболическое здоровье), rMSSD (HRV/восстановление), hs-CRP (воспаление).

# Иерархия Nudge-ов (от наивысшего приоритета)
1. **Медицинский:** "Запишись сдать анализ на глюкозу + инсулин натощак для расчёта HOMA-IR — единственный способ увидеть реальное метаболическое здоровье."
2. **Физический:** "Сегодня сделай 12-минутный тест Купера для оценки VO2 Max — сильнейший предиктор продолжительности жизни."
3. **Восстановление:** "По высокому стрессу и низкому HRV: отмени высокоинтенсивную тренировку. Замени на 20 мин Zone 2 ходьбы."
4. **Сон:** "Вариабельность сна слишком высока. Сегодня жёсткий Digital Sunset в 21:00. Никаких экранов, 15 мин мобильности."

# Логика "Сдвига"
Если пользователь сопротивляется или не выполнил задание — предложи альтернативу с меньшим барьером входа, но без потери медицинской значимости.

# Анализ корреляций (после ассессмента)
Свяжи самые низкие показатели с мотивацией пользователя. Называй по имени. Будь конкретен.
Пример: "Михаил, твои перепады сна (4–12 ч) + стресс 8/10 — главная причина тумана в голове. Невозможно достичь ясности ума, пока кортизол скачет в 3 ночи."

# ОБЯЗАТЕЛЬНЫЙ ФОРМАТ ОТВЕТА (строгий JSON)
{
  "updated_scores": { "biological_age": null, "domain_scores": {} },
  "message_to_user": "Стратегический инсайт, связывающий мотивацию пользователя с конкретным маркером.",
  "next_interaction": {
    "type": "ACTION" | "ASSESSMENT" | "REFLECTION",
    "content": "Конкретное, действенное задание.",
    "schedule_tag": "MORNING" | "EVENING",
    "medical_flag": false
  }
}

updated_scores и next_interaction могут быть null если не применимы.
Язык: только русский. Возвращай ТОЛЬКО валидный JSON — без markdown, без текста вне JSON."""

FALLBACK_OUTPUTS = [
    LongevityBrainOutput(
        message_to_user="Сегодняшнее задание: сделай 12-минутный тест Купера — пробеги максимальное расстояние за 12 минут. Это позволит оценить твой VO2 Max — сильнейший предиктор продолжительности жизни.",
        next_interaction=NextInteraction(type="ACTION", content="12-минутный тест Купера", schedule_tag="MORNING"),
    ),
    LongevityBrainOutput(
        message_to_user="Запишись сдать анализ крови натощак: глюкоза + инсулин. Это позволит рассчитать HOMA-IR и увидеть реальное метаболическое здоровье — то, что недоступно по симптомам.",
        next_interaction=NextInteraction(type="ACTION", content="Записаться на анализ: глюкоза + инсулин натощак", schedule_tag="MORNING"),
    ),
    LongevityBrainOutput(
        message_to_user="Сегодня 20 минут Zone 2 — ходьба в темпе, при котором можно говорить, но уже с усилием. Это фундамент митохондриального здоровья и жировой адаптации.",
        next_interaction=NextInteraction(type="ACTION", content="20 мин Zone 2 ходьба", schedule_tag="MORNING"),
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
    context = f"""Профиль пользователя:
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
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw)
        # Map v1.2 schema fields to LongevityBrainOutput
        if "updated_scores" in data and "message_to_user" not in data:
            raise ValueError("Missing message_to_user")
        return LongevityBrainOutput(
            update_user_state=data.get("updated_scores"),
            message_to_user=data["message_to_user"],
            next_interaction=data.get("next_interaction"),
        )
    except Exception as e:
        logger.error(f"Failed to parse Claude output: {e}\nRaw: {raw}")
        raise


async def safe_claude_call(
    user_state: Dict,
    sanitized_input: Optional[str],
    history: list,
    instruction: str,
) -> LongevityBrainOutput:
    try:
        return await call_claude(user_state, sanitized_input, history, instruction)
    except Exception as e:
        logger.error(f"Claude brain failed: {e}. Using fallback.")
        return get_fallback_output()
