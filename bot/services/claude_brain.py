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

SYSTEM_PROMPT = """Ты — Longevity Intelligence Core, Медицина 3.0 (Аттиа, Левин, Уокер). Максимизируй healthspan через высокоROI вмешательства.

Стиль: радикальная прозрачность, биохимические термины (метаболическая гибкость, аутофагия, постпрандиальная сонливость), ноль воды, без аналогий, без лести.

Приоритеты: 1) Риски: 4 всадника (метаболический синдром, ССЗ, онкология, нейродегенерация) 2) Performance: VO2 Max, мышечная масса 3) Recovery: сон, стресс, восстановление.

Правила:
— Один вопрос за раз. Субъективный ответ → перекрести с физиологией (Second-order thinking).
— Stress Filter: самостоятельно оцени стресс из данных. >7/10 → только Recovery ROI (сон, магний, Zone 2); запрещены высокоинтенсивные задания.
— Объективные данные (HRV, глюкоза, АД) → вес 2.0x над субъективными.
— Лекарства: учитывай метаболические эффекты (антидепрессанты → вес, пролактин, глюкоза).
— Невыполнение = системный сбой. Предложи альтернативу с меньшим барьером входа.
— focus_domain в контексте — основной домен сегодня. Работай с ним, если нет критических data gaps.

Веса: sleep 35%, metabolic 25%, physical 20%, mental_recovery 20%.
medical-type nudges: когда есть data gaps (HOMA-IR, ApoB, VO2 Max, HRV отсутствуют), изредка (раз в 3-5 дней) генерируй запрос анализа вместо обычного совета. Но не зацикливайся на анализах — пользователь должен получать полезные советы по основным доменам, пока собирает данные.

ФОРМАТ (строгий JSON, только русский, без markdown вне JSON):
{"internal_analysis":{"detected_risks":[],"data_gaps":[],"logic_chain":""},"updated_scores":{"biological_age_estimate":null,"domain_scores":{"sleep":0,"metabolic":0,"physical":0,"mental_recovery":0}},"message_to_user":"","next_interaction":{"type":"ACTION","content":"","schedule_tag":"MORNING","medical_flag":false}}
updated_scores и next_interaction могут быть null."""

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
    ad = user_state.get("assessment_data", {})

    context = f"""user_profile:
  name: {user_state.get('name', 'unknown')}
  age: {ad.get('age', 'unknown')}
  sex: {ad.get('sex', 'unknown')}
  coaching_style: {user_state.get('coaching_style', 'balanced')}
  goals: {user_state.get('motivation', 'not specified')}
  occupation: {ad.get('occupation', 'unknown')}
  substances: {ad.get('substances', 'none')}
  medications: {ad.get('medications', 'none')}
  conditions: {ad.get('conditions', 'none')}

health_data:
  domain_scores: {json.dumps(scores, ensure_ascii=False)}
  bio_markers_self_reported:
    blood_work: {ad.get('blood_work', 'unknown')}
    morning_energy: {ad.get('morning_energy', 'unknown')}
    brain_fog_frequency: {ad.get('brain_fog', 'unknown')}
    sleep: {ad.get('avg_sleep', 'unknown')}h avg, variance {ad.get('sleep_variance', 'unknown')}h
    sedentary: {ad.get('sedentary_hours', 'unknown')}h/day
    exercise: {ad.get('exercise', 'unknown')}
    stress_detail: {ad.get('stress_detail', 'unknown')}

instruction: {instruction}
user_input: {sanitized_input or '(no input — proactive delivery)'}"""

    messages = history[-6:] + [{"role": "user", "content": context}]

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1600,
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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def call_claude_with_context(context_str: str, history: list) -> LongevityBrainOutput:
    """Call Claude with a pre-built compact context string."""
    messages = history[-6:] + [{"role": "user", "content": context_str}]
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1600,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    raw = response.content[0].text.strip()
    try:
        return _parse_output(raw)
    except Exception as e:
        logger.error(f"Failed to parse Claude output: {e}\nRaw: {raw}")
        raise


async def safe_claude_call_v2(context_str: str, history: list = None) -> LongevityBrainOutput:
    """Safe wrapper for call_claude_with_context."""
    try:
        return await call_claude_with_context(context_str, history or [])
    except Exception as e:
        logger.error(f"Claude brain v2 failed: {e}. Using fallback.")
        return get_fallback_output()


async def generate_nudge_plan(health_scores: Dict, assessment_data: Dict) -> list:
    """
    Generate a 30-day domain priority schedule using Claude Haiku (cheap).
    Returns list of 30 domain strings: sleep / metabolic / physical / stress.
    """
    scores_str = json.dumps(health_scores, ensure_ascii=False)
    conditions = assessment_data.get("conditions", "")
    medications = assessment_data.get("medications", "")
    stress_detail = assessment_data.get("stress_detail", "")

    prompt = (
        f"Составь список из ровно 30 доменов для ежедневных nudge.\n"
        f"Домены только из: sleep, metabolic, physical, mental_recovery.\n"
        f"Правила: самый слабый домен встречается чаще; не более 3 подряд одинаковых; "
        f"mental_recovery приоритетен при депрессии/тревожности или высоком субъективном стрессе.\n"
        f"scores={scores_str}\nconditions={conditions}\nrx={medications}\nstress={stress_detail}\n"
        f"Верни ТОЛЬКО валидный JSON массив из 30 строк. Без комментариев."
    )

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        plan = json.loads(raw.strip())
        # Validate — ensure all values are valid domains
        valid = {"sleep", "metabolic", "physical", "mental_recovery"}
        plan = [d if d in valid else "mental_recovery" for d in plan]
        return plan[:30]
    except Exception as e:
        logger.error(f"generate_nudge_plan failed: {e}. Using default cycle.")
        # Fallback: sensible default cycle
        return (["mental_recovery", "sleep", "mental_recovery", "metabolic", "physical", "sleep"] * 5)[:30]
