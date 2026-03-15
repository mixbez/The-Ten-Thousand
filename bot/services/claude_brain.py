"""
Claude Brain - Longevity Intelligence Core v2.1 (Medicine 3.0).
"""
import json
import logging
from typing import Optional, Dict
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from bot.config import settings
from bot.validators import LongevityBrainOutput, NextInteraction, InternalAnalysis

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """Ты — Longevity Intelligence Core проекта "10 000". Стратег долголетия на базе принципов Медицины 3.0 (Питер Аттиа, Морган Левин, Мэттью Уокер).
Твоя миссия: максимизировать healthspan и lifespan через высокоROI вмешательства.

# Стиль коммуникации
Радикальная прозрачность, медицинская точность, ноль воды.
Anti-Cringe Rule: никаких бытовых аналогий ("сердце — насос"). Не льсти. Используй биохимические и физиологические термины напрямую: метаболическая гибкость, гликирование, аутофагия, постпрандиальная сонливость.

# Основная философия
Приоритет 1: Data Discovery — заполни пробелы в данных.
Приоритет 2: Risk Mitigation — Четыре всадника (метаболический синдром, ССЗ, онкология, нейродегенерация).
Приоритет 3: Performance Optimization — VO2 Max, мышечная масса.

# Discovery Algorithm
Правило "Одного Вопроса": задавай только один глубокий вопрос за раз.
Second-Order Thinking: если пользователь даёт субъективный ответ ("чувствую себя нормально") — перекрёстно проверь с объективными трендами или задай уточняющий физиологический вопрос ("ты испытываешь постпрандиальную сонливость или ранние пробуждения в 3-4 ночи?").

# Stress Filter (ОБЯЗАТЕЛЬНО)
Если уровень стресса пользователя > 7/10 — переключись СТРОГО на Recovery ROI.
Запрещено: высокоинтенсивные / высококортизольные задания в фазе высокого стресса.
Разрешено: стабилизация сна, баланс магния/электролитов, Zone 2 активность.

# Objective Override
Объективные данные (HRV, глюкоза, АД) всегда перекрывают субъективные с весом 2.0x.

# Приоритизация Nudge-ов
1. Gap First: если нет липидного профиля или инсулина натощак — первоочередная задача — отправить на анализ (напр., Synlab).
2. Medication Awareness: учитывай влияние антидепрессантов на метаболические маркеры (вес, пролактин, глюкоза).
3. No Moralizing: если пользователь не выполнил задание — анализируй как системный сбой, не личный. Предложи альтернативу с меньшим барьером входа.

# Скоринг доменов
Sleep (35%), Metabolic (25%), Physical (20%), Mental Recovery (20%).
Objective data weight: 2.0x.

# ОБЯЗАТЕЛЬНЫЙ ФОРМАТ ОТВЕТА (строгий JSON, только на русском языке)
{
  "internal_analysis": {
    "detected_risks": ["список рисков"],
    "data_gaps": ["чего не хватает для полной картины"],
    "logic_chain": "краткая цепочка рассуждений за текущим выбором"
  },
  "updated_scores": {
    "biological_age_estimate": null,
    "domain_scores": {
      "sleep": 0.0,
      "metabolic": 0.0,
      "physical": 0.0,
      "mental_recovery": 0.0
    }
  },
  "message_to_user": "Прямой, data-driven инсайт. Свяжи действие с конкретным биологическим исходом.",
  "next_interaction": {
    "type": "ACTION" | "ASSESSMENT" | "REFLECTION",
    "content": "Конкретный nudge или глубокий вопрос",
    "schedule_tag": "MORNING" | "EVENING",
    "medical_flag": false
  }
}

updated_scores и next_interaction могут быть null если не применимы.
Язык: только русский. Возвращай ТОЛЬКО валидный JSON — без markdown, без текста вне JSON."""

FALLBACK_OUTPUTS = [
    LongevityBrainOutput(
        internal_analysis=InternalAnalysis(
            detected_risks=["Отсутствуют данные HOMA-IR"],
            data_gaps=["Глюкоза натощак", "Инсулин натощак"],
            logic_chain="Без HOMA-IR невозможно оценить инсулинорезистентность — ключевой маркер метаболического здоровья.",
        ),
        message_to_user="Запишись сдать анализ: глюкоза + инсулин натощак. Это позволит рассчитать HOMA-IR — единственный способ выявить инсулинорезистентность до появления симптомов. Норма HOMA-IR < 1.5; у большинства людей с 'нормальным' сахаром он уже 2-3.",
        next_interaction=NextInteraction(type="ACTION", content="Записаться на анализ: глюкоза + инсулин натощак (Synlab или аналог)", schedule_tag="MORNING", medical_flag=True),
    ),
    LongevityBrainOutput(
        internal_analysis=InternalAnalysis(
            detected_risks=["Низкий VO2 Max по косвенным признакам"],
            data_gaps=["VO2 Max", "Липидный профиль (ApoB)"],
            logic_chain="VO2 Max — сильнейший независимый предиктор смертности. Без базовых данных невозможно строить Physical план.",
        ),
        message_to_user="Сегодня — 12-минутный тест Купера. Пробеги максимальное расстояние за 12 минут и зафикси результат. Это даст оценку VO2 Max: <2 км = критически низкий, 2.4+ км = хороший уровень для долголетия.",
        next_interaction=NextInteraction(type="ACTION", content="12-минутный тест Купера — зафиксировать дистанцию в метрах", schedule_tag="MORNING", medical_flag=False),
    ),
    LongevityBrainOutput(
        internal_analysis=InternalAnalysis(
            detected_risks=["Высокая sedentary нагрузка", "Возможная митохондриальная дисфункция"],
            data_gaps=["HRV (rMSSD)", "hs-CRP"],
            logic_chain="Длительное сидение нарушает липопротеиновую липазу и глюкозный транспорт независимо от тренировок.",
        ),
        message_to_user="20 минут Zone 2 — ходьба в темпе, при котором можно говорить, но дыхание уже участилось. Zone 2 активирует митохондриальный биогенез и жировую оксидацию без кортизолового ответа.",
        next_interaction=NextInteraction(type="ACTION", content="20 мин Zone 2 ходьба — пульс 60-70% от максимального", schedule_tag="MORNING", medical_flag=False),
    ),
]
_fallback_index = 0


def get_fallback_output() -> LongevityBrainOutput:
    global _fallback_index
    output = FALLBACK_OUTPUTS[_fallback_index % len(FALLBACK_OUTPUTS)]
    _fallback_index += 1
    return output


def _parse_output(raw: str) -> LongevityBrainOutput:
    """Parse Claude JSON output into LongevityBrainOutput, handling schema variations."""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    data = json.loads(text)

    # Parse internal_analysis
    ia = data.get("internal_analysis")
    internal_analysis = InternalAnalysis(**ia) if ia else None

    # Parse next_interaction — tolerant of missing fields
    ni = data.get("next_interaction")
    next_interaction = None
    if ni and isinstance(ni, dict) and ni.get("content"):
        try:
            # Normalise type field
            ni_type = ni.get("type", "ACTION")
            if ni_type not in ("ACTION", "NUDGE", "REFLECTION", "ASSESSMENT"):
                ni_type = "ACTION"
            ni["type"] = ni_type
            # Normalise schedule_tag
            tag = ni.get("schedule_tag", "MORNING")
            if tag not in ("MORNING", "EVENING", "IMMEDIATE"):
                tag = "MORNING"
            ni["schedule_tag"] = tag
            next_interaction = NextInteraction(**ni)
        except Exception as e:
            logger.warning(f"Could not parse next_interaction: {e}")

    # Parse updated_scores — accept both v1.3 and legacy formats
    updated_scores = data.get("updated_scores") or data.get("update_user_state")

    return LongevityBrainOutput(
        internal_analysis=internal_analysis,
        updated_scores=updated_scores,
        message_to_user=data["message_to_user"],
        next_interaction=next_interaction,
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def call_claude(
    user_state: Dict,
    sanitized_input: Optional[str],
    history: list,
    instruction: str,
) -> LongevityBrainOutput:
    from bot.scoring_logic import normalize_health_scores
    scores = normalize_health_scores(user_state.get("health_scores", {}))

    context = f"""user_profile:
  name: {user_state.get('name', 'unknown')}
  coaching_style: {user_state.get('coaching_style', 'balanced')}
  goals: {user_state.get('motivation', 'not specified')}
  constraints: {user_state.get('assessment_data', {}).get('supplements', 'none')}
  stress_level: {user_state.get('stress_level', 'unknown')}

health_data:
  domain_scores: {json.dumps(scores, ensure_ascii=False)}
  bio_markers: {json.dumps(user_state.get('assessment_data', {}), ensure_ascii=False)}

nudge_history: []

instruction: {instruction}
user_input: {sanitized_input or '(no input — proactive delivery)'}"""

    messages = history[-6:] + [{"role": "user", "content": context}]

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    raw = response.content[0].text.strip()
    try:
        return _parse_output(raw)
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
